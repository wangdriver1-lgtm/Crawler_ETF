"""Shared data-completeness check for deployment and delayed recovery."""
import json
import re
import sys
from pathlib import Path


def failed_codes(payload):
    funds = payload.get('etfs')
    if not isinstance(funds, dict) or not funds:
        raise ValueError('ETF 資料清單為空或格式異常')
    failed = []
    for code, info in funds.items():
        if not re.fullmatch(r'\d{5}[AD]', code):
            raise ValueError('ETF 清單包含無效代號')
        if (not isinstance(info, dict) or info.get('status') != 'fresh' or not info.get('stocks')
                or not re.fullmatch(r'\d{8}', str(info.get('date') or ''))):
            failed.append(code)
    return sorted(failed)


if __name__ == '__main__':
    payload = json.loads(Path('etf/all_stocks.json').read_text(encoding='utf-8'))
    failed = failed_codes(payload)
    print('待補抓 ETF：' + (', '.join(failed) if failed else '無'))
    if '--outputs' in sys.argv:
        import os
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write(f'needs_retry={str(bool(failed)).lower()}\n')
            output.write('failed_codes=' + ','.join(failed) + '\n')
    else:
        raise SystemExit(bool(failed))
