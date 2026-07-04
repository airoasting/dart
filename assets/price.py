#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전일(최근 거래일) 종가와 52주 범위를 신뢰할 수 있는 소스에서 가져온다.

웹 검색 현재가는 출처마다 값이 달라 부정확하므로, 주가는 항상 이 모듈로 채운다.
소스 우선순위: Naver 금융 siseJson(requests만 필요) → pykrx(설치돼 있으면 폴백).

CLI:  python3 price.py 035720   →  JSON 한 줄
"""
from __future__ import annotations
import sys, json, datetime
import requests


def _naver_daily(stock_code: str, days: int = 400):
    """Naver 금융 일봉. [(YYYYMMDD, close, high, low), ...] 오래된→최신 순."""
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    r = requests.get(
        "https://api.finance.naver.com/siseJson.naver",
        params={"symbol": stock_code, "requestType": "1",
                "startTime": start.strftime("%Y%m%d"),
                "endTime": end.strftime("%Y%m%d"), "timeframe": "day"},
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"},
    )
    r.raise_for_status()
    rows = json.loads(r.text.strip().replace("'", '"'))  # header + data, JS→JSON
    out = []
    for d in rows[1:]:                                    # [날짜,시가,고가,저가,종가,...]
        if d and d[4]:
            out.append((str(d[0]), int(d[4]), int(d[2]), int(d[3])))
    return out


def _pykrx_daily(stock_code: str, days: int = 400):
    from pykrx import stock
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    df = stock.get_market_ohlcv(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), stock_code)
    return [(idx.strftime("%Y%m%d"), int(row["종가"]), int(row["고가"]), int(row["저가"]))
            for idx, row in df.iterrows()]


def get_prev_close(stock_code: str) -> dict | None:
    """최근 거래일 종가 기준 요약. 실패 시 None."""
    rows = None
    for fetch in (_naver_daily, _pykrx_daily):
        try:
            rows = fetch(stock_code)
            if rows:
                break
        except Exception:
            rows = None
    if not rows:
        return None
    highs = [r[2] for r in rows]
    lows = [r[3] for r in rows]
    last_date, last_close = rows[-1][0], rows[-1][1]
    prev = rows[-2][1] if len(rows) >= 2 else last_close
    chg = (last_close - prev) / prev * 100 if prev else 0.0
    d = last_date
    return {
        "date": last_date,                                   # YYYYMMDD
        "date_dot": f"{d[:4]}.{d[4:6]}.{d[6:]}",             # YYYY.MM.DD
        "close": last_close,
        "prev_close": prev,
        "change_pct": round(chg, 2),
        "w52_high": max(highs),
        "w52_low": min(lows),
        "w52_range": f"{min(lows):,} ~ {max(highs):,}",
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 price.py <stock_code>", file=sys.stderr)
        sys.exit(1)
    res = get_prev_close(sys.argv[1])
    if res is None:
        print(json.dumps({"error": "주가를 가져오지 못했습니다"}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(res, ensure_ascii=False))
