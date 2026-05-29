import datetime
import json
import urllib.request
import ssl
import re

_SSL_CTX = ssl.create_default_context()
try:
    _SSL_CTX.set_ciphers("DEFAULT@SECLEVEL=1")
except Exception:
    pass

def _http_get_json(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
        return json.loads(r.read().decode("utf-8"))

def _get_twse_holidays(ad_year):
    roc_year = ad_year - 1911
    url = f"https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=json&queryYear={roc_year}"
    data = _http_get_json(url, timeout=20)
    out = set()
    for row in data.get("data", []):
        if not row:
            continue
        day = str(row[0]).strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", day):
            out.add(day)
    return out

target = datetime.date(2026, 5, 11)
try:
    holidays = _get_twse_holidays(target.year)
    is_holiday = target.strftime("%Y-%m-%d") in holidays
    print(f"May 11, 2026 weekday: {target.weekday()} (0=Mon, 5=Sat, 6=Sun)")
    print(f"May 11, 2026 in TWSE holidays: {is_holiday}")
    if is_holiday:
        print("Result: May 11 is a market HOLIDAY - program did NOT run because of is_tw_trading_day check")
    else:
        print("Result: May 11 should have been a trading day - check if scheduled execution failed")
except Exception as e:
    print(f"Error: {e}")
