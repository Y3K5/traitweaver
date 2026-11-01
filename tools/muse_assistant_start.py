"""Copied local terminal entry point. No key read before exact batch approval."""
import hashlib
import importlib.util
from pathlib import Path
import sys


def main():
    packet=Path(__file__).resolve().parent
    # Do not load copied executable code until its pins match the manifest.
    import json
    plan_path=packet/'PUBLIC_BATCH.json'
    if plan_path.is_symlink() or not plan_path.is_file() or plan_path.stat().st_size>128*1024:raise ValueError('Unsafe manifest')
    plan=json.loads(plan_path.read_bytes())
    # Bind executable pins to the actual owner's grant before importing code.
    canonical=json.dumps({k:v for k,v in plan.items() if k!='approval_sha256'},sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    if hashlib.sha256(canonical.encode()).hexdigest()!=plan['approval_sha256']:raise ValueError('Manifest changed')
    approval_path=packet/'OWNER_APPROVAL.json'
    if approval_path.is_symlink() or not approval_path.is_file() or approval_path.stat().st_size>4096:raise ValueError('Approval missing')
    expected={'approved':True,'approval_sha256':plan['approval_sha256'],'destination':'https://api.meta.ai/v1/responses','model':'muse-spark-1.3',
              'maximum_spend_usd':'0.20','max_requests':4,'max_output_tokens_each':8192,'retries':0,'fallback':False}
    if json.loads(approval_path.read_bytes())!=expected:raise ValueError('Exact approval required')
    for name in ('muse_assistant_batch.py','muse_assistant_start.py','muse_diagnostics.py'):
        p=packet/name
        if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=plan['execution']['runner_files'][name]:raise ValueError('Reviewed code changed')
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=plan['execution']['runner_files']['muse_assistant_start.py']:raise ValueError('Starter changed')
    if not (sys.stdin.isatty() and sys.stderr.isatty()):raise ValueError('A real interactive terminal is required')
    spec=importlib.util.spec_from_file_location('reviewed_assistant_batch',packet/'muse_assistant_batch.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    try:
        result=module.run(packet,allow_live=True)
        print('Four-case batch completed. Inspect MONITOR.html, accepted case reviews and usage. No more calls.');return 0
    except module.BatchStopped as exc:
        print('Stopped: '+module.canonical(exc.state['failure'])+'. Inspect STATUS.json/MONITOR.html. No retries.',file=sys.stderr);return 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except (Exception,KeyboardInterrupt):
        raise SystemExit('Local approval/terminal/code check failed. No implicit send or retry. Never paste credentials into chat.')
