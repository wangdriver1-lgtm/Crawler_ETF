"""Recheck a completed run after at least 30 minutes, then dispatch recovery.

Only the trusted main-branch crawler workflow is retried. A newer run always
supersedes an older timer, and explicit cancellations are never restarted.
"""
import datetime
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.request

from ci_health import failed_codes

DELAY_SECONDS = 30 * 60


def retry_plan(run, payload, latest_run_id, now):
    if run['id'] != latest_run_id or run.get('conclusion') in ('cancelled', 'skipped', 'neutral'):
        return {'pending': False, 'wait_seconds': 0, 'reason': '已被較新執行取代或使用者已取消'}
    missing = failed_codes(payload)
    pending = run.get('conclusion') != 'success' or bool(missing)
    finished = datetime.datetime.fromisoformat(run['updated_at'].replace('Z', '+00:00'))
    due = finished.timestamp() + DELAY_SECONDS
    return {'pending': pending, 'wait_seconds': max(0, math.ceil(due - now.timestamp())) if pending else 0,
            'reason': ','.join(missing) if missing else '抓取或部署流程失敗' if pending else '資料與部署均成功'}


def api(path, body=None, raw=False):
    repository = os.environ['GITHUB_REPOSITORY']
    headers = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'User-Agent': 'ETF-recovery',
               'Accept': 'application/vnd.github.raw+json' if raw else 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json'}
    request = urllib.request.Request(f'https://api.github.com/repos/{repository}{path}', headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
    # Retry read-only API errors briefly; never blindly duplicate a dispatch POST.
    for attempt in range(3 if body is None else 1):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                data = response.read()
                return json.loads(data) if data else {}
        except OSError:
            if attempt + 1 == (3 if body is None else 1):
                raise
            time.sleep(2 ** (attempt + 1))


def check():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    run = event['workflow_run']
    if (run.get('head_branch') != 'main'
            or run.get('head_repository', {}).get('full_name') != os.environ['GITHUB_REPOSITORY']):
        raise ValueError('拒絕重試其他分支或外部儲存庫')
    runs = api('/actions/workflows/crawler.yml/runs?branch=main&per_page=5')['workflow_runs']
    latest = runs[0]['id'] if runs else None
    payload = api('/contents/etf/all_stocks.json?ref=main', raw=True)
    now = datetime.datetime.now(datetime.timezone.utc)
    return retry_plan(run, payload, latest, now)


def main():
    plan = check()
    print(plan['reason'])
    if sys.argv[1] == 'plan':
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write(f"pending={str(plan['pending']).lower()}\nwait_seconds={plan['wait_seconds']}\n")
    elif sys.argv[1] == 'dispatch':
        if plan['pending'] and not plan['wait_seconds']:
            api('/actions/workflows/crawler.yml/dispatches', {'ref': 'main', 'inputs': {'recover_only': True}})
            print('已觸發缺漏資料及網站部署重試。')
        else:
            print('無須重試、已有較新執行，或尚未滿 30 分鐘；不重複觸發。')
    else:
        raise ValueError('未知指令')


if __name__ == '__main__':
    main()
