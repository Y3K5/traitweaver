"""Allowlisted diagnostics around the unchanged, approved Muse boundary.

Never retain exception strings, provider messages, response bodies, arbitrary
headers, URLs, cookies or credentials. Injected transports are for offline tests.
"""
import socket
import ssl
import time
import urllib.error
import urllib.request

PROVIDER_CODES = frozenset({
    'invalid_api_key', 'authentication_error', 'permission_denied',
    'insufficient_quota', 'rate_limit_exceeded', 'invalid_request_error',
    'invalid_request', 'model_not_found', 'unsupported_parameter',
    'invalid_json_schema', 'context_length_exceeded', 'server_error',
    'invalid_model', 'billing_error', 'account_deactivated', 'access_denied',
    'content_policy_violation', 'overloaded_error',
})
PARAMETERS = frozenset({'model', 'input', 'store', 'max_output_tokens',
                        'text', 'text.format', 'text.format.schema'})
STATUSES = frozenset({'completed', 'incomplete', 'failed', 'cancelled',
                      'queued', 'in_progress'})


def numeric_usage(value):
    if not isinstance(value, dict): return None
    out = {k: value[k] for k in ('input_tokens', 'output_tokens')
           if type(value.get(k)) is int and 0 <= value[k] <= 1_000_000_000}
    return out or None


class SafeFailure(ValueError):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__('Muse attempt stopped; safe diagnostic recorded')


def base(stage, code, dispatched=False, **fields):
    return {'schema_version': 'traitweaver.safe_failure.v1', 'stage': stage,
            'code': code, 'dispatch_attempted': dispatched, **fields}


def network_code(exc):
    # Inspect types only. Exception messages/reason strings can contain secrets.
    if isinstance(exc, urllib.error.URLError):
        exc = exc.reason
    if isinstance(exc, ssl.SSLCertVerificationError): return 'tls_certificate_verification_failed'
    if isinstance(exc, ssl.SSLError): return 'tls_error'
    if isinstance(exc, socket.gaierror): return 'dns_resolution_failed'
    if isinstance(exc, TimeoutError): return 'timeout'
    if isinstance(exc, ConnectionRefusedError): return 'connection_refused'
    if isinstance(exc, ConnectionResetError): return 'connection_reset'
    if isinstance(exc, (OSError, urllib.error.URLError)): return 'network_error'
    return 'transport_error'


def provider_fields(value):
    """Only exact enum values survive, never arbitrary error text or identifiers."""
    if not isinstance(value, dict): return {}
    error = value.get('error')
    if not isinstance(error, dict): return {}
    out = {}
    for source, target, allowed in [('code', 'provider_error_code', PROVIDER_CODES),
                                    ('type', 'provider_error_type', PROVIDER_CODES),
                                    ('param', 'provider_error_parameter', PARAMETERS)]:
        candidate = error.get(source)
        if isinstance(candidate, str) and candidate in allowed:
            out[target] = candidate
        elif candidate is not None:
            out[target] = 'unrecognized_value_withheld'
    return out


def exception_diagnostic(exc, stage):
    if isinstance(exc, SafeFailure): return dict(exc.diagnostic)
    dispatched = stage in ('structured_reply_validation', 'usage_validation',
                           'receipt_save', 'accepted_reply_save', 'local_check', 'export')
    if isinstance(exc, KeyboardInterrupt): return base(stage, 'operator_interrupted', dispatched)
    # These are exact application-owned literals, never fragments of exception text.
    reasons = {
        'Unknown, missing or duplicated source citations': 'invalid_citations',
        'Unavailable action or altered arguments': 'unavailable_action_or_arguments',
        'Rationale/citation exceeds the admitted check context': 'unsupported_rationale',
        'Reassessment exceeds the recorded result or claim ceiling': 'unsupported_reassessment',
        'Provider refused this request': 'provider_refusal',
        'Unexpected provider tool/action output': 'unexpected_provider_action',
        'Reported token usage unavailable': 'missing_or_invalid_usage',
        'Reported tokens exceed the approved conservative allowance': 'usage_exceeds_allowance',
    }
    text = exc.args[0] if isinstance(exc, ValueError) and exc.args else None
    code = reasons.get(text, 'validation_failed' if 'validation' in stage else 'local_stage_failed') if isinstance(text, str) else 'local_stage_failed'
    return base(stage, code, dispatched)


def describe(value):
    parts = [value['stage'], value['code']]
    for field in ('http_status', 'provider_error_code', 'provider_error_type', 'provider_error_parameter', 'provider_status', 'incomplete_reason'):
        if field in value: parts.append(field+'='+str(value[field]))
    return '; '.join(parts)


class CaptureOpener:
    def __init__(self, muse, opener=None):
        self.muse = muse
        self.diagnostic = None
        self.last_response = {}
        self.dispatched = False
        if opener is None:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs): return None
            # Do not inherit machine proxy routing or load cookie handlers.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.opener = opener

    def fail(self, stage, code, **fields):
        self.diagnostic = base(stage, code, self.dispatched, **fields)
        raise SafeFailure(self.diagnostic) from None

    def http_failure(self, status, response):
        fields = {'http_status': status}
        if status in (301, 302, 303, 307, 308): code = 'redirect_blocked'
        elif status == 401: code = 'http_authentication_rejected'
        elif status == 403: code = 'http_permission_rejected'
        elif status == 429: code = 'http_rate_or_quota_rejected'
        elif 400 <= status < 500: code = 'http_request_rejected'
        elif status >= 500: code = 'http_provider_error'
        else: code = 'unexpected_http_status'
        # Bounded inspection, then discard. No body, message or header is logged.
        try:
            raw = response.read(8193)
            if len(raw) <= 8192:
                fields.update(provider_fields(self.muse.study.decode(raw)))
        except Exception:
            pass
        self.fail('http_response', code, **fields)

    def open(self, request, timeout):
        if request.full_url != self.muse.DESTINATION or request.get_method() != 'POST':
            self.fail('request_preparation', 'destination_or_method_mismatch')
        self.dispatched = True
        try:
            response = self.opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            try:
                self.http_failure(exc.code, exc)
            finally:
                exc.close()
        except (OSError, urllib.error.URLError) as exc:
            self.fail('transport_open', network_code(exc))
        status = getattr(response, 'status', None)
        if type(status) is not int:
            response.close()
            self.fail('http_response', 'missing_http_status')
        if status != 200:
            try:
                self.http_failure(status, response)
            finally:
                response.close()
        self.last_response = {'http_status': 200}
        return CaptureResponse(response, self)


class CaptureResponse:
    def __init__(self, response, capture):
        self.response = response
        self.capture = capture
        self.status = 200

    def __enter__(self): return self

    def __exit__(self, *args):
        self.response.close()

    def read(self, size):
        c = self.capture
        try:
            raw = self.response.read(size)
        except (OSError, urllib.error.URLError) as exc:
            c.fail('response_read', network_code(exc), http_status=200)
        if len(raw) > c.muse.MAX_RESPONSE:
            c.fail('response_read', 'response_too_large', http_status=200)
        try:
            value = c.muse.study.decode(raw)
        except (ValueError, UnicodeError):
            c.fail('response_decode', 'malformed_json', http_status=200)
        if not isinstance(value, dict):
            c.fail('response_decode', 'response_not_object', http_status=200)
        c.last_response.update(provider_fields(value))
        c.last_response['reported_usage'] = numeric_usage(value.get('usage'))
        status = value.get('status')
        c.last_response['provider_status'] = status if isinstance(status, str) and status in STATUSES else 'unrecognized_value_withheld'
        if value.get('model') != c.muse.MODEL:
            c.fail('provider_envelope_validation', 'model_mismatch', **c.last_response)
        if status != 'completed':
            details = value.get('incomplete_details')
            reason = details.get('reason') if isinstance(details, dict) else None
            if isinstance(reason, str) and reason in ('max_output_tokens', 'content_filter'):
                c.last_response['incomplete_reason'] = reason
            c.fail('provider_envelope_validation', 'provider_not_completed', **c.last_response)
        return raw


def send_approved(muse, preview, grant, ledger, allow_live=False, opener=None):
    """Use the existing grant/key/reservation boundary; capture safe failures."""
    capture = CaptureOpener(muse, opener)
    started = time.monotonic()
    try:
        response, receipt = muse.send_approved(preview, grant, ledger, allow_live=allow_live, opener=capture)
        receipt['safe_transport'] = dict(capture.last_response)
        return response, receipt
    except (Exception, KeyboardInterrupt) as exc:
        if capture.diagnostic:
            raise SafeFailure({**capture.diagnostic, 'elapsed_seconds': round(time.monotonic()-started, 3)}) from None
        if isinstance(exc, KeyboardInterrupt):
            code = 'operator_interrupted'
        elif not capture.dispatched:
            # Boundary-owned static messages. Never persist arbitrary exceptions.
            known = {
                'Live transport disabled': 'live_transport_disabled',
                'Credential unavailable; reservation retained': 'credential_unavailable',
                'Request already attempted; ledger retained, no retry': 'duplicate_attempt_blocked',
            }
            text = exc.args[0] if isinstance(exc, ValueError) and exc.args else None
            code = known.get(text, 'pre_dispatch_rejected') if isinstance(text, str) else 'pre_dispatch_rejected'
        else:
            code = 'response_safety_or_transport_failure'
        stage = 'pre_dispatch' if not capture.dispatched else 'response_safety_validation'
        raise SafeFailure(base(stage, code, capture.dispatched, elapsed_seconds=round(time.monotonic()-started, 3), **capture.last_response)) from None
