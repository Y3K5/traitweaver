"""Single-request adapter acceptance checks; sockets and credentials stay blocked."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('intelligence_smoke_test', ROOT/'tools/muse_intelligence_smoke.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.fixed_now = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
        clock = patch.object(b, 'now', return_value=self.fixed_now)
        clock.start(); self.addCleanup(clock.stop)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.packet = Path(self.tmp.name)/'packet'
        self.socket = patch('socket.socket', side_effect=AssertionError('No network'))
        self.socket.start(); self.addCleanup(self.socket.stop)
        self.key = patch.object(b.helper, 'credential', side_effect=AssertionError('No credentials'))
        self.credential = self.key.start(); self.addCleanup(self.key.stop)
        self.plan = b.prepare(self.packet)

    def grant(self, live=False):
        name = 'OWNER_APPROVAL.json' if live else 'OFFLINE_APPROVAL.json'
        b.helper.atomic(self.packet/name, b.approval_for(self.plan, approved=True, offline=not live))

    def fake(self, raw):
        self.assertEqual(b.helper.sha(raw), self.plan['request_sha256'])
        _, request, source, bundle = b.verify_packet(self.packet)
        reply = b.v2.synthetic_reply(request, 'combination_coverage')
        reply['usage'] = {'input_tokens': 100, 'output_tokens': 200, 'total_tokens': 300}
        return b.study.canonical(reply).encode()

    def run_fake(self, fake=None):
        return b.run(self.packet, approval_sha256=self.plan['approval_sha256'], fake_transport=fake or self.fake)

    def test_prepare_is_unsigned_deterministic_exact_and_public(self):
        other = b.prepare(Path(self.tmp.name)/'second')
        self.assertEqual(other['request_sha256'], self.plan['request_sha256'])
        self.assertNotEqual(other['approval_sha256'], self.plan['approval_sha256'])
        self.assertFalse((self.packet/'OWNER_APPROVAL.json').exists())
        self.assertFalse(b.helper.read(self.packet/'UNSIGNED_APPROVAL.json')['approved'])
        plan, request, source, bundle = b.verify_packet(self.packet)
        self.assertEqual((self.packet/'REQUEST.json').read_bytes(), b.study.canonical(request['body']).encode())
        self.assertEqual(request['eligible_checks'], ['combination_coverage', 'transfer_coverage'])
        self.assertEqual(request['body']['max_output_tokens'], 1024)
        self.assertFalse(request['body']['store']); self.assertNotIn('tools', request['body'])
        self.assertEqual(source['revisions'][-1]['state']['cycles'][0]['decision']['accepted_reply']['receipt']['provenance'], 'synthetic_fixture')
        self.assertTrue(b.study.decode(request['body']['input'])['continuation_context']['unresolved_requirements'])
        self.assertLessEqual(b.Decimal(plan['reserved_estimate_usd']), b.CAP)
        for excluded in ('SYNTHETIC_SMOKE', 'saved_utc', 'study_id', '/workspace/', 'MODEL_API_KEY'):
            self.assertNotIn(excluded, request['body']['input'])
        self.credential.assert_not_called()

    def test_disabled_wrong_approval_and_nonterminal_never_read_key(self):
        with self.assertRaises(ValueError): b.run(self.packet, approval_sha256=self.plan['approval_sha256'])
        self.grant(live=True)
        with patch.object(b.sys.stdin, 'isatty', return_value=False):
            with self.assertRaises(ValueError): b.run(self.packet, allow_live=True, approval_sha256=self.plan['approval_sha256'])
        self.grant()
        with self.assertRaises(ValueError): b.run(self.packet, approval_sha256='0'*64, fake_transport=self.fake)
        with self.assertRaises(ValueError): b.run(self.packet, allow_live=True, approval_sha256=self.plan['approval_sha256'], fake_transport=self.fake)
        self.credential.assert_not_called(); self.assertFalse((self.packet/'ATTEMPT.started').exists())

    def test_approval_budget_fields_and_body_tampering_block(self):
        self.grant(); grant = b.helper.read(self.packet/'OFFLINE_APPROVAL.json')
        grant['approved'] = 1; b.helper.atomic(self.packet/'OFFLINE_APPROVAL.json', grant)
        with self.assertRaises(ValueError): self.run_fake()
        grant['approved'] = True
        grant['maximum_spend_usd'] = '999'; b.helper.atomic(self.packet/'OFFLINE_APPROVAL.json', grant)
        with self.assertRaises(ValueError): self.run_fake()
        self.grant(); body = b.helper.read(self.packet/'REQUEST.json'); body['store'] = True
        b.helper.atomic(self.packet/'REQUEST.json', body)
        with self.assertRaises(ValueError): self.run_fake()
        self.assertFalse((self.packet/'ATTEMPT.started').exists())

    def test_lineage_and_code_pins_reject_changes_without_dispatch(self):
        source = b.helper.read(self.packet/'SOURCE.json')
        source['revisions'][-1]['state']['scope']['recipient'] = 'study_uvm4'
        b.helper.atomic(self.packet/'SOURCE.json', source)
        with self.assertRaises(ValueError): b.verify_packet(self.packet)
        with patch.object(b, 'dependencies', return_value={}):
            with self.assertRaises(ValueError): b.verify_packet(self.packet)

    def test_success_has_separate_fake_receipt_and_no_following_check(self):
        self.grant()
        with patch.object(b.model, 'run_check', side_effect=AssertionError('No dispatch after prepare')):
            result = self.run_fake()
            b.verify_packet(self.packet)
            package = b.helper.read(self.packet/'PROPOSAL_REVIEW.json')
            self.assertEqual(b.v2.validate_package(package, b.model.catalog()), package)
            session = b.v2.Session(); session.open(None, package, b.model.catalog())
            self.assertTrue(session.read_only)
        self.assertEqual(result['status'], 'valid_proposal_only')
        self.assertEqual(result['transport'], 'offline_fake_transport')
        self.assertEqual(result['requests_started'], 1); self.assertEqual(result['live_transport_calls'], 0)
        self.assertEqual(result['estimated_token_cost_usd'], '0.000975')
        self.assertEqual(result['reserved_estimate_usd'], '0')
        self.assertEqual(package['proposal_review']['receipt']['provenance'], 'synthetic_fixture')
        with self.assertRaises(ValueError): self.run_fake()
        self.credential.assert_not_called()

    def test_fake_unmarked_response_cannot_become_authentic(self):
        self.grant()
        def unmarked(raw):
            reply = b.study.decode(self.fake(raw)); del reply['traitweaver_synthetic']
            return b.study.canonical(reply).encode()
        result = self.run_fake(unmarked)
        self.assertEqual(result['status'], 'stopped')
        self.assertFalse((self.packet/'PROPOSAL_REVIEW.json').exists())

    def test_incomplete_usage_accounted_and_raw_reasoning_not_saved(self):
        self.grant()
        def incomplete(raw):
            reply = b.study.decode(self.fake(raw)); reply.update(status='incomplete', private_detail='DO_NOT_SAVE')
            return b.study.canonical(reply).encode()
        result = self.run_fake(incomplete)
        self.assertEqual(result['status'], 'stopped')
        self.assertEqual(result['estimated_token_cost_usd'], '0.000975')
        self.assertEqual(result['reserved_estimate_usd'], '0')
        self.assertNotIn('DO_NOT_SAVE', (self.packet/'RECEIPT.json').read_text())
        self.assertFalse((self.packet/'PROPOSAL_REVIEW.json').exists())
        with self.assertRaises(ValueError): self.run_fake()

    def test_partial_usage_retains_reservation_and_unknown_is_not_zero(self):
        self.grant()
        def partial(raw):
            reply = b.study.decode(self.fake(raw)); reply['usage'] = {'input_tokens': 0}
            return b.study.canonical(reply).encode()
        result = self.run_fake(partial)
        self.assertEqual(result['status'], 'stopped'); self.assertEqual(result['reported_usage'], {'input_tokens': 0})
        self.assertIsNone(result['estimated_token_cost_usd'])
        self.assertEqual(result['reserved_estimate_usd'], self.plan['reserved_estimate_usd'])

    def test_transport_failure_is_sanitized_and_never_retried(self):
        self.grant(); calls = []
        def fail(raw):
            calls.append(raw); raise OSError('DO_NOT_SAVE')
        result = self.run_fake(fail)
        self.assertEqual(result['status'], 'stopped'); self.assertEqual(len(calls), 1)
        self.assertNotIn('DO_NOT_SAVE', str(result))
        self.assertEqual(result['reserved_estimate_usd'], self.plan['reserved_estimate_usd'])
        with self.assertRaises(ValueError): self.run_fake(fail)

    def test_expiry_stop_copy_and_symlink_guards(self):
        self.grant()
        later = self.fixed_now + timedelta(days=2)
        with patch.object(b, 'now', return_value=later):
            with self.assertRaises(ValueError): self.run_fake()
        (self.packet/'STOP.requested').touch()
        with self.assertRaises(ValueError): self.run_fake()
        import shutil
        moved = Path(self.tmp.name)/'copy'; shutil.copytree(self.packet, moved)
        with self.assertRaises(ValueError): b.verify_packet(moved)
        alias = Path(self.tmp.name)/'alias'; alias.symlink_to(self.packet, target_is_directory=True)
        with self.assertRaises(ValueError): b.verify_packet(alias)

    def test_expired_pricing_cannot_prepare_or_execute(self):
        self.grant()
        with patch.object(b, 'now', return_value=self.fixed_now+timedelta(days=8)):
            with self.assertRaisesRegex(ValueError, 'price'):
                b.prepare(Path(self.tmp.name)/'expired')
            with self.assertRaises(ValueError): self.run_fake()
        self.assertFalse((Path(self.tmp.name)/'expired').exists())
        self.assertFalse((self.packet/'ATTEMPT.started').exists())

    def test_lowest_send_gate_cannot_bypass_approval(self):
        with self.assertRaises(ValueError): b.send(self.packet, b'{}', 'fake-test-key')
        self.assertFalse((self.packet/'POST.started').exists())

    def test_lowest_send_checks_exact_reservation_and_body_then_allows_only_one_post(self):
        # Synthetic grant and in-memory HTTP only; never call credential().
        import io
        self.grant(live=True)
        b.marker(self.packet/'ATTEMPT.started', self.plan['approval_sha256']+'\n')
        receipt = b.initial_receipt(self.plan, False)
        b.helper.atomic(self.packet/'RECEIPT.json', receipt)
        calls = []
        class Capture:
            def __init__(self, core): pass
            def open(inner, request, timeout):
                calls.append(request)
                self.assertEqual(request.full_url, b.v1.DESTINATION)
                self.assertEqual(request.get_method(), 'POST')
                self.assertEqual(request.data, (self.packet/'REQUEST.json').read_bytes())
                self.assertEqual(timeout, 60)
                return io.BytesIO(b'{}')
        with patch.object(b.sys.stdin, 'isatty', return_value=True), patch.object(b.sys.stderr, 'isatty', return_value=True), patch.object(b, 'Capture', Capture):
            with self.assertRaises(ValueError): b.send(self.packet, b'{}', 'fake-test-key')
            receipt['reserved_estimate_usd'] = '0'; b.helper.atomic(self.packet/'RECEIPT.json', receipt)
            with self.assertRaises(ValueError): b.send(self.packet, (self.packet/'REQUEST.json').read_bytes(), 'fake-test-key')
            b.helper.atomic(self.packet/'RECEIPT.json', b.initial_receipt(self.plan, False))
            self.assertEqual(b.send(self.packet, (self.packet/'REQUEST.json').read_bytes(), 'fake-test-key'), b'{}')
            with self.assertRaises(ValueError): b.send(self.packet, (self.packet/'REQUEST.json').read_bytes(), 'fake-test-key')
        self.assertEqual(len(calls), 1); self.credential.assert_not_called()

    def test_output_overrun_invalid_totals_and_known_failure_counts_are_not_accepted(self):
        for i, usage in enumerate(({'input_tokens': 10, 'output_tokens': 1025, 'total_tokens': 1035},
                                   {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 0},
                                   {'input_tokens': True, 'output_tokens': 20, 'total_tokens': 21})):
            if i:
                self.packet = Path(self.tmp.name)/('packet'+str(i)); self.plan = b.prepare(self.packet)
            self.grant()
            def invalid(raw):
                reply = b.study.decode(self.fake(raw)); reply['usage'] = usage
                return b.study.canonical(reply).encode()
            result = self.run_fake(invalid)
            self.assertEqual(result['status'], 'stopped')
            self.assertFalse((self.packet/'PROPOSAL_REVIEW.json').exists())
            if i: self.assertEqual(result['reserved_estimate_usd'], self.plan['reserved_estimate_usd'])

    def test_provider_safe_failure_preserves_partial_counts_without_error_text(self):
        self.grant()
        def failed(raw):
            raise b.helper.diagnostics.SafeFailure({'reported_usage': {'input_tokens': 13}, 'message': 'DO_NOT_SAVE'})
        result = self.run_fake(failed)
        self.assertEqual(result['reported_usage'], {'input_tokens': 13})
        self.assertIsNone(result['estimated_token_cost_usd']); self.assertNotIn('DO_NOT_SAVE', str(result))
        self.assertEqual(result['reserved_estimate_usd'], self.plan['reserved_estimate_usd'])

    def test_http_error_records_known_usage_without_body_or_retry(self):
        import io
        import urllib.error
        from types import SimpleNamespace
        self.grant()
        response = b.study.canonical({'usage': {'input_tokens': 100, 'output_tokens': 200},
                                      'error': {'message': 'DO_NOT_SAVE'}}).encode()
        class Opener:
            def open(inner, request, timeout):
                raise urllib.error.HTTPError(b.v1.DESTINATION, 400, 'DO_NOT_SAVE', {}, io.BytesIO(response))
        def failed(raw):
            capture = b.Capture(SimpleNamespace(DESTINATION=b.v1.DESTINATION, MODEL=b.v1.MODEL,
                                               MAX_RESPONSE=b.v1.MAX_RESPONSE, study=b.study), Opener())
            return capture.open(b.urllib.request.Request(b.v1.DESTINATION, data=raw, method='POST'), timeout=60)
        result = self.run_fake(failed)
        self.assertEqual(result['reported_usage'], {'input_tokens': 100, 'output_tokens': 200})
        self.assertEqual(result['estimated_token_cost_usd'], '0.000975')
        self.assertEqual(result['reserved_estimate_usd'], self.plan['reserved_estimate_usd'])
        self.assertEqual(result['status'], 'stopped'); self.assertNotIn('DO_NOT_SAVE', str(result))

    def proxy_fixture(self, proxy='http://proxy:8080', version=1):
        policy = Path(self.tmp.name)/'network-policy.json'
        b.helper.atomic(policy, {'version': version, 'http_proxy': proxy,
                               'http_network_policy': {'type': 'restricted', 'egress_rules': []}})
        return policy

    def test_runtime_proxy_routes_only_exact_meta_request_and_keeps_tls(self):
        import ssl
        policy = self.proxy_fixture()
        with patch.object(b, 'NETWORK_POLICY', policy), patch.object(b.os, 'environ', {'HTTPS_PROXY': 'http://proxy:8080'}):
            opener = b.runtime_proxy_opener()
            proxy = next(h for h in opener.handlers if isinstance(h, b.RequiredProxy))
            self.assertEqual(sum(isinstance(h, b.urllib.request.ProxyHandler) for h in opener.handlers), 1)
            request = b.urllib.request.Request(b.v1.DESTINATION, data=b'{}', method='POST')
            proxy.https_open(request)
            self.assertEqual(request.host, 'proxy:8080')
            self.assertEqual(request._tunnel_host, 'api.meta.ai')
            self.assertEqual(request.full_url, b.v1.DESTINATION)
            https = next(h for h in opener.handlers if isinstance(h, b.urllib.request.HTTPSHandler))
            self.assertTrue(https._context.check_hostname)
            self.assertEqual(https._context.verify_mode, ssl.CERT_REQUIRED)
            for url in ('https://example.invalid/v1/responses', 'https://api.meta.ai/v1/models'):
                with self.assertRaises(ValueError):
                    proxy.https_open(b.urllib.request.Request(url, data=b'{}', method='POST'))
            with self.assertRaises(ValueError): proxy.https_open(b.urllib.request.Request(b.v1.DESTINATION))
            self.assertFalse(any(isinstance(h, b.urllib.request.HTTPCookieProcessor) for h in opener.handlers))

    def test_missing_changed_malformed_or_bypassed_proxy_fails_closed(self):
        policy = self.proxy_fixture()
        for env in ({}, {'HTTPS_PROXY': 'http://other.invalid:8080'},
                    {'HTTPS_PROXY': 'http://proxy:8080', 'NO_PROXY': '*'},
                    {'HTTPS_PROXY': 'http://proxy:8080', 'no_proxy': 'api.meta.ai'},
                    {'HTTPS_PROXY': 'http://proxy:8080', 'https_proxy': 'http://other.invalid:8080'}):
            with patch.object(b, 'NETWORK_POLICY', policy), patch.object(b.os, 'environ', env):
                with self.assertRaises(ValueError): b.runtime_proxy_opener()
        for proxy, version in (('http://user:private@proxy:8080', 1), ('https://proxy:8080', 1),
                               ('http://proxy:8080/path', 1), ('http://proxy:8080', 2), ('http://proxy:8080', True)):
            policy = self.proxy_fixture(proxy, version)
            with patch.object(b, 'NETWORK_POLICY', policy), patch.object(b.os, 'environ', {'HTTPS_PROXY': proxy}):
                with self.assertRaises(ValueError): b.runtime_proxy_opener()
        with patch.object(b, 'NETWORK_POLICY', Path(self.tmp.name)/'missing'):
            with self.assertRaises(ValueError): b.runtime_proxy_opener()

    def test_proxy_configuration_change_after_creation_cannot_fall_back(self):
        policy = self.proxy_fixture(); env = {'HTTPS_PROXY': 'http://proxy:8080'}
        with patch.object(b, 'NETWORK_POLICY', policy), patch.object(b.os, 'environ', env):
            opener = b.runtime_proxy_opener()
            proxy = next(h for h in opener.handlers if isinstance(h, b.RequiredProxy))
            env['NO_PROXY'] = 'api.meta.ai'
            with self.assertRaises(ValueError):
                proxy.https_open(b.urllib.request.Request(b.v1.DESTINATION, data=b'{}', method='POST'))
            self.assertEqual(env['NO_PROXY'], 'api.meta.ai')

    def test_actual_urllib_chain_connects_only_to_proxy_and_tunnels_meta_offline(self):
        import io
        from email.message import Message
        from types import SimpleNamespace
        policy = self.proxy_fixture(); calls = []
        raw = b.study.canonical({'model': b.v1.MODEL, 'status': 'completed', 'output': []}).encode()
        class Response(io.BytesIO):
            code = status = 200
            reason = 'OK'
            headers = Message()
            def info(inner): return inner.headers
        class Connection:
            sock = None
            debuglevel = 0
            def __init__(inner, host, timeout, **kwargs):
                calls.append(('connect', host))
                self.assertTrue(kwargs['context'].check_hostname)
            def set_debuglevel(inner, level): pass
            def set_tunnel(inner, host, **kwargs): calls.append(('tunnel', host))
            def request(inner, method, selector, data, headers, **kwargs): calls.append(('request', method, selector))
            def getresponse(inner): return Response(raw)
            def close(inner): pass
        with patch.object(b, 'NETWORK_POLICY', policy), patch.object(b.os, 'environ', {'HTTPS_PROXY': 'http://proxy:8080'}), patch('http.client.HTTPSConnection', Connection):
            capture = b.Capture(SimpleNamespace(DESTINATION=b.v1.DESTINATION, MODEL=b.v1.MODEL,
                                              MAX_RESPONSE=b.v1.MAX_RESPONSE, study=b.study))
            request = b.urllib.request.Request(b.v1.DESTINATION, data=b'{}', method='POST')
            with capture.open(request, 60) as response: self.assertEqual(response.read(b.v1.MAX_RESPONSE+1), raw)
        self.assertEqual(calls, [('connect', 'proxy:8080'), ('tunnel', 'api.meta.ai'), ('request', 'POST', '/v1/responses')])
        calls.clear()
        with patch.object(b, 'NETWORK_POLICY', policy), patch.object(b.os, 'environ', {'HTTPS_PROXY': 'http://proxy:8080'}), patch('http.client.HTTPSConnection', Connection), patch.object(Connection, 'request', side_effect=OSError('private denied CONNECT')):
            capture = b.Capture(SimpleNamespace(DESTINATION=b.v1.DESTINATION, MODEL=b.v1.MODEL,
                                              MAX_RESPONSE=b.v1.MAX_RESPONSE, study=b.study))
            request = b.urllib.request.Request(b.v1.DESTINATION, data=b'{}', method='POST')
            with self.assertRaises(b.helper.diagnostics.SafeFailure) as failed: capture.open(request, 60)
        self.assertEqual(calls, [('connect', 'proxy:8080'), ('tunnel', 'api.meta.ai')])
        self.assertEqual(failed.exception.diagnostic['code'], 'network_error')
        self.assertNotIn('private denied', str(failed.exception.diagnostic))

    def test_proxy_denial_and_redirect_do_not_retry_or_switch_routes(self):
        import io
        import urllib.error
        from types import SimpleNamespace
        policy = self.proxy_fixture(); attempts = []
        with patch.object(b, 'NETWORK_POLICY', policy), patch.object(b.os, 'environ', {'HTTPS_PROXY': 'http://proxy:8080'}):
            capture = b.Capture(SimpleNamespace(DESTINATION=b.v1.DESTINATION, MODEL=b.v1.MODEL,
                                              MAX_RESPONSE=b.v1.MAX_RESPONSE, study=b.study))
            redirect = next(h for h in capture.opener.handlers if isinstance(h, b.urllib.request.HTTPRedirectHandler))
            request = b.urllib.request.Request(b.v1.DESTINATION, data=b'{}', method='POST')
            self.assertIsNone(redirect.redirect_request(request, None, 302, 'Found', {}, 'https://example.invalid'))
            def reject(request, timeout):
                attempts.append(request.full_url)
                raise urllib.error.HTTPError(request.full_url, 403, 'private denial', {}, io.BytesIO(b'{}'))
            with patch.object(capture.opener, 'open', side_effect=reject):
                with self.assertRaises(b.helper.diagnostics.SafeFailure) as failed:
                    capture.open(request, 60)
            self.assertEqual(attempts, [b.v1.DESTINATION])
            self.assertEqual(failed.exception.diagnostic['code'], 'http_permission_rejected')
            self.assertNotIn('private denial', str(failed.exception.diagnostic))

    def test_proxy_preflight_blocks_before_credentials_or_attempt_marker(self):
        self.grant(live=True)
        with patch.object(b.sys.stdin, 'isatty', return_value=True), patch.object(b.sys.stderr, 'isatty', return_value=True), patch.object(b, 'runtime_proxy_opener', side_effect=ValueError('Missing proxy')):
            with self.assertRaises(ValueError):
                b.run(self.packet, approval_sha256=self.plan['approval_sha256'], allow_live=True)
        self.credential.assert_not_called()
        self.assertFalse((self.packet/'ATTEMPT.started').exists())

    def test_transport_policy_is_bound_to_fresh_unsigned_review(self):
        self.assertEqual(self.plan['transport_policy'], b.TRANSPORT_POLICY)
        plan = deepcopy(self.plan); del plan['transport_policy']
        plan['approval_sha256'] = b.study.digest({k: v for k, v in plan.items() if k != 'approval_sha256'})
        b.helper.atomic(self.packet/'PLAN.json', plan)
        with self.assertRaises(ValueError): b.verify_packet(self.packet)


if __name__ == '__main__': unittest.main()
