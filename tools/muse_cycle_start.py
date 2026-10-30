"""Copied into a reviewed packet; local hidden-key entry point, no retries."""
import getpass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys


def main():
    packet = Path(__file__).resolve().parent
    control=json.loads((packet/'LOCAL_CONTROL.json').read_text())
    runner=packet/'muse_cycle.py'
    if hashlib.sha256(runner.read_bytes()).hexdigest()!=control['runner_sha256']:
        raise ValueError('Reviewed runner changed; no code was loaded')
    spec = importlib.util.spec_from_file_location('approved_muse_cycle', runner)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plan, _ = module.verify_packet(packet)
    if (packet / 'CYCLE.started').exists():
        raise ValueError('Cycle already started; no retry or resume is permitted')
    approval = module.load(packet / 'OWNER_APPROVAL.json')
    expected = {'approved': True, 'approval_sha256': plan['approval_sha256'],
                'destination': plan['destination'], 'model': plan['model'],
                'maximum_spend_usd': '0.05', 'max_requests': 2}
    if approval != expected:
        raise ValueError('Exact owner approval is missing')
    if not sys.stdin.isatty():
        raise ValueError('A local interactive terminal is required for live sending')
    if not os.environ.get('MODEL_API_KEY'):
        key = getpass.getpass('Meta MODEL_API_KEY (hidden; never saved): ')
        if not key.strip():
            raise ValueError('No key supplied; no attempt made')
        os.environ['MODEL_API_KEY'] = key
        del key
    try:
        try:
            result = module.run(packet, packet / 'OWNER_APPROVAL.json', allow_live=True)
            print(json.dumps(result, indent=2))
        except module.CycleStopped as exc:
            print('Stopped: '+module.diagnostics.describe(exc.diagnostic), file=sys.stderr)
            print('Inspect FAILURE-*.json and MONITOR.html. No retry or resume.', file=sys.stderr)
            return 1
    finally:
        os.environ.pop('MODEL_API_KEY', None)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyboardInterrupt):
        sys.exit('Local approval/credential/startup check failed. No implicit send or retry. Inspect the packet; do not paste credentials into chat.')
