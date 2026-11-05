"""Dated public holdings backup, explicitly attributed to ETF資訊網.

Read the same SSR payload used by the public holdings page, including its
pagination data. No authentication, premium history or protected API is used.
"""
import datetime
from decimal import Decimal, InvalidOperation
import json
import re
import urllib.request

from bs4 import BeautifulSoup

SOURCE_NAME = "ETF資訊網（公開持股備援）"


def decode_payload(nodes, index, depth=0):
    if depth > 35 or not isinstance(index, int) or index >= len(nodes):
        raise ValueError("備援頁面資料結構異常")
    if index < 0:
        return None
    value = nodes[index]
    if isinstance(value, dict):
        return {key: decode_payload(nodes, ref, depth + 1) for key, ref in value.items()}
    if isinstance(value, list):
        if value and isinstance(value[0], str):
            if value[0] not in ('ShallowReactive', 'Reactive', 'Ref', 'ShallowRef') or len(value) != 2:
                raise ValueError("備援資料包含不支援的結構")
            return decode_payload(nodes, value[1], depth + 1)
        return [decode_payload(nodes, ref, depth + 1) for ref in value]
    return value


def parse_holdings(html, code, today=None):
    soup = BeautifulSoup(html, 'html.parser')
    script = soup.find('script', id='__NUXT_DATA__', type='application/json')
    if script is None:
        raise ValueError('備援頁面沒有公開持股資料')
    nodes = json.loads(script.string or script.get_text())
    # Resolve only this ETF's public data; ignore unrelated state and login data.
    root = nodes[nodes[0][1]]
    data = nodes[root['data']]
    if isinstance(data, list) and data[0] == 'ShallowReactive':
        data = nodes[data[1]]
    ref = data.get(f'etf-detail-base-{code}')
    if ref is None:
        raise ValueError('備援頁面 ETF 代號不符')
    detail = nodes[ref]
    info = decode_payload(nodes, detail['info'])
    snapshot = decode_payload(nodes, detail['holdings'])
    if not snapshot or snapshot.get('etfCode') != code or info.get('code') != code:
        raise ValueError('備援持股的 ETF 身分不符或尚無快照')
    date = datetime.date.fromisoformat(str(snapshot.get('snapshotDate')))
    limit = today or datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()
    if date > limit:
        raise ValueError('拒絕未來日期的持股資料')
    rows = []
    seen = set()
    for item in snapshot.get('holdings') or []:
        stock = str(item.get('code') or '').strip()
        name = str(item.get('name') or '').strip()
        unit = item.get('unit')
        # Cash balances and receivables are not stock quantities.
        if not stock or not name or stock in seen or stock.upper().startswith(('C_', 'RDI_', 'RPI_')):
            continue
        quantity = None
        try:
            number = Decimal(str(item.get('shares')).replace(',', ''))
            if unit == '股' and number.is_finite() and number >= 0 and number == number.to_integral_value():
                quantity = str(int(number))
        except (ValueError, InvalidOperation):
            pass
        weight = item.get('weight')
        if weight is not None:
            weight = Decimal(str(weight))
            if not weight.is_finite() or weight < 0 or weight > 100:
                raise ValueError('備援持股權重無效')
        seen.add(stock)
        rows.append({'股票代號': stock, '股票名稱': name, '股數': quantity,
                     '持股比例': f'{weight}%' if weight is not None else '',
                     'ETF股票代號': code, '原始數量': item.get('shares'), '數量單位': unit})
    if not rows:
        raise ValueError('備援來源尚無可用持股明細')
    return {'stocks': rows, 'date': date.strftime('%Y%m%d'), 'source_name': SOURCE_NAME,
            'source_url': f'https://www.etfinfo.tw/etf/{code}/holdings',
            'source_kind': 'backup', 'upstream_source': snapshot.get('source'),
            'date_basis': snapshot.get('snapshotDateSource', 'provider')}


def fetch_holdings(code, today=None):
    if not re.fullmatch(r'\d{5}[AD]', code):
        raise ValueError('ETF 代號無效')
    url = f'https://www.etfinfo.tw/etf/{code}/holdings'
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'text/html'})
    with urllib.request.urlopen(request, timeout=15) as response:
        html = response.read(6_000_001)
    if len(html) > 6_000_000:
        raise ValueError('備援回應大小異常')
    return parse_holdings(html.decode('utf-8'), code, today)
