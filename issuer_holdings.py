"""Dated official issuer APIs used by their public ETF pages."""
import datetime
import html
from decimal import Decimal, InvalidOperation
import json
import re
import urllib.request
from urllib.parse import urlparse, urlencode

SCHRODERS_PRODUCTS = {'00419A': 'SCHDR_F00002KHVY'}


def schroders_url(code):
    if code not in SCHRODERS_PRODUCTS:
        raise ValueError('施羅德 ETF 尚無官方工具代號')
    return 'https://www.schroders.com/zh-tw/tw/individual/fund-centre/etf/?' + urlencode({
        'language': 'zh-tw', 'location': 'tw', 'channel': 'etf', 'clientId': 'schdr', 'clientVersion': 'v1',
        'externalId': SCHRODERS_PRODUCTS[code], 'r': f'/fund/{SCHRODERS_PRODUCTS[code]}/'})


def parse_schroders_holdings(payload, code, today=None):
    if code not in SCHRODERS_PRODUCTS:
        raise ValueError('施羅德 ETF 代號未受支援')
    section = payload.get('fxPcfSubscriptionRedemptionSection')
    if not isinstance(section, dict):
        raise ValueError('施羅德尚未提供持股資料')
    dates = {datetime.datetime.strptime(item['asOfDate'], '%d.%m.%Y').date()
             for item in section['subscriptionRedemption']['items']
             if item.get('attribute') in ('netAssets', 'navPerUnitTMinus1') and item.get('asOfDate')}
    if len(dates) != 1:
        raise ValueError('施羅德持股基準日缺漏或不一致')
    date = dates.pop()
    limit = today or datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()
    if date > limit:
        raise ValueError('拒絕未來日期的施羅德持股')
    def text(value):
        return html.unescape(re.sub(r'<[^>]+>', '', str(value))).strip()
    rows, seen = [], set()
    for group in section.get('holdings', {}).get('groups', []):
        if text(group.get('title')) != '股票':
            continue
        columns = [text(value) for value in group['columns']]
        expected = ['股票代號', '股票名稱', '股數', '總金額', '權重 (%)']
        if columns != expected:
            raise ValueError('施羅德持股欄位已變更')
        for item in group.get('rows', []):
            if len(item) != len(expected):
                raise ValueError('施羅德持股欄位不完整')
            stock = re.sub(r'\.(TW|TWO)$', '', text(item[0]))
            if not re.fullmatch(r'\d{4,6}', stock) or stock in seen:
                raise ValueError('施羅德股票代號重複或格式不符')
            quantity = Decimal(text(item[2]).replace(',', ''))
            weight = Decimal(text(item[4]).replace('%', ''))
            if not quantity.is_finite() or quantity < 0 or quantity != quantity.to_integral_value() or not weight.is_finite():
                raise ValueError('施羅德股數或持股比例無效')
            seen.add(stock)
            rows.append({'股票代號': stock, '股票名稱': text(item[1]), '股數': str(int(quantity)),
                         '持股比例': f'{weight}%', 'ETF股票代號': code})
    if not rows:
        raise ValueError('施羅德官方股票清單為空')
    return {'date': date.strftime('%Y%m%d'), 'stocks': rows, 'source_kind': 'official',
            'source_name': '施羅德官方基金中心每日完整持股', 'source_url': schroders_url(code), 'date_basis': 'issuer'}


def fetch_schroders_holdings(code, today=None):
    schroders_url(code)  # Validate before constructing the public tool request.
    query = urlencode({'isin': taiwan_isin(code), 'externalId': SCHRODERS_PRODUCTS[code],
                       'location': 'tw', 'channel': 'etf', 'language': 'zh-tw'})
    url = 'https://fev2-vite.schdr.eu-central-1.isgdigital.com/api/v1/getEtfPcfAndFundHoldings?' + query
    return parse_schroders_holdings(request_json(url), code, today)


def request_json(url, body=None):
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def parse_capital_holdings(payload, code, today=None):
    if payload.get('code') != 200 or not isinstance(payload.get('data'), dict):
        raise ValueError('群益官方持股 API 回應異常')
    data = payload['data']
    # date1 is the NEXT dealing day's PCF; date2 is the underlying valuation date.
    date = datetime.date.fromisoformat(data['pcf']['date2'])
    limit = today or datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()
    if date > limit:
        raise ValueError('拒絕未來日期的群益持股資料')
    rows, seen = [], set()
    for item in data.get('stocks') or []:
        stock = str(item.get('stocNo') or '').strip()
        name = str(item.get('stocName') or '').strip()
        if not stock or not name or stock in seen:
            raise ValueError('群益持股代碼缺漏或重複')
        quantity = Decimal(str(item.get('share')))
        weight = Decimal(str(item.get('weight')))
        if not quantity.is_finite() or quantity < 0 or quantity != quantity.to_integral_value() or not weight.is_finite():
            raise ValueError('群益持股股數或權重無效')
        seen.add(stock)
        rows.append({'股票代號': stock, '股票名稱': name, '股數': str(int(quantity)),
                     '持股比例': f'{weight}%', 'ETF股票代號': code})
    if not rows:
        raise ValueError('群益官方尚無完整股票清單')
    return {'date': date.strftime('%Y%m%d'), 'stocks': rows, 'source_kind': 'official',
            'source_name': '群益投信官方完整投資組合 API', 'date_basis': 'issuer',
            'pcf_effective_date': data['pcf'].get('date1')}


def fetch_capital_holdings(code, official_url, today=None):
    parsed = urlparse(official_url)
    match = re.fullmatch(r'/etf/product/detail/(\d+)/portfolio', parsed.path)
    if parsed.hostname != 'www.capitalfund.com.tw' or not match:
        raise ValueError('群益基金網址格式不符')
    fund_id = match[1]
    base = 'https://www.capitalfund.com.tw/CFWeb/api/etf'
    identity = request_json(f'{base}/detail/{fund_id}')
    if identity.get('code') != 200 or identity.get('data', {}).get('stockCode') != code:
        raise ValueError('群益基金代號與請求不符')
    payload = request_json(base + '/buyback', {'fundId': fund_id, 'date': None})
    result = parse_capital_holdings(payload, code, today)
    result['source_url'] = official_url
    return result


def taiwan_isin(code):
    if not re.fullmatch(r'\d{5}[AD]', code):
        raise ValueError('ETF 代碼無效')
    prefix = 'TW000' + code
    digits = ''.join(str(ord(char) - 55) if char.isalpha() else char for char in prefix) + '0'
    total = sum(sum(divmod(int(char) * (2 if index % 2 else 1), 10)) for index, char in enumerate(reversed(digits)))
    return prefix + str(-total % 10)


def ab_url(code):
    return f'https://www.abfunds.com.tw/zh-tw/etfs/pcf.{taiwan_isin(code)}.html'


def parse_ab_holdings(payload, code, today=None):
    dates, rows = set(), []
    for section in payload.get('domesticHoldings') or []:
        holdings = section.get('holdings') or []
        if not holdings:
            continue
        dates.add(datetime.datetime.strptime(section['asOfDate'], '%m/%d/%Y').date())
        category = section.get('holdingCategory')
        unit = {'holdings-section-bond': '面額', 'holdings-section-equity': '股',
                'holdings-section-futures': '口', 'holdings-section-fund': '單位'}.get(category, '來源未提供')
        for item in holdings:
            name = str(item.get('holding') or '').strip()
            if not name:
                continue
            stock = str(item.get('holdingCode') or '').strip() or '未提供代碼：' + name
            quantity = item.get('holdingShares')
            share_count = None
            if unit == '股':
                try:
                    value = Decimal(str(quantity))
                    if value.is_finite() and value >= 0 and value == value.to_integral_value():
                        share_count = str(int(value))
                except InvalidOperation:
                    pass
            weight = Decimal(str(item.get('holdingPerc')))
            if not weight.is_finite():
                raise ValueError('官方持有比例無效')
            rows.append({'股票代號': stock, '股票名稱': name, '股數': share_count,
                         '持股比例': f'{weight}%', 'ETF股票代號': code,
                         '原始數量': quantity, '數量單位': unit})
    if not rows or len(dates) != 1:
        raise ValueError('聯博官方明細為空或各類資產的日期不一致')
    date = dates.pop()
    limit = today or datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()
    if date > limit:
        raise ValueError('拒絕未來日期的官方持有明細')
    return {'date': date.strftime('%Y%m%d'), 'stocks': rows, 'source_kind': 'official',
            'source_name': '聯博投信官方每日持有明細', 'source_url': ab_url(code), 'date_basis': 'issuer'}


def fetch_ab_holdings(code, today=None):
    isin = taiwan_isin(code)
    url = f'https://webapi.alliancebernstein.com/v2/funds/tw/zh-tw/investor/{isin}/holdings'
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    return parse_ab_holdings(payload, code, today)
