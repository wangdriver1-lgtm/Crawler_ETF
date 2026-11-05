"""Dated official issuer APIs used by their public ETF pages."""
import datetime
from decimal import Decimal, InvalidOperation
import json
import re
import urllib.request


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
