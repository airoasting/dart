#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data.json 조립기. 숫자는 사람이 옮겨 적지 않고 원천에서 계산한다.

왜
  리포트 시간의 일부는 에이전트 결과를 data.json으로 옮겨 적는 데 들었고, 손으로 쓴 meta 숫자(증감률·이익률·
  목표가 평균)가 게이트에서 반올림 차이로 걸리곤 했다. 이 스크립트는 DART·KRX에서 직접 숫자를 만들고,
  에이전트들이 파일로 남긴 조각과 검증 장부를 합쳐 data.json을 쓴다.

사용
  # 0) 어느 기간으로 만들지 (가장 최근에 제출된 정기보고서). 출력의 "args"를 1)·2)에 그대로 붙인다
  python3 assemble_report.py period --corp-code 00164742

  # 1) 에이전트에게 넘길 사실 (게이트와 같은 표기)
  python3 assemble_report.py facts --corp-code 00164742 --year 2026 --reprt 11012

  # 2) 조각 파일이 다 모이면 data.json 조립
  python3 assemble_report.py build --corp-code 00164742 --year 2026 --reprt 11012 --parts <dir> -o <data.json>

연결재무제표가 없으면(status 013) 개별재무제표로 자동 전환하고 그 사실을 알린다. 둘 다 없으면 그 분기
정기보고서가 아직 안 나온 것이다. 멈추고 references/provisional.md(잠정실적 경로)를 안내한다.
결산월(--fiscal-month)을 주지 않으면 상장사 목록의 결산월을 쓴다.

조각 파일 (<dir> 안, 모두 순수 JSON)
  A1.json  {"NEWS": [...]}                                           뉴스 에이전트
  A2.json  {"ANALYSTS": [...], "SEGS": [...], "filter_cats": [...]}      증권사·부문 에이전트
           (CONS·커버리지 문구는 이 스크립트가 ANALYSTS에서 만든다)
  B.json   [... 13개 PERSONAS ...]                                    페르소나 에이전트
  C.json   {"BULLS": [...], "BEARS": [...], "CHIPS": [...]}            강세·약세 에이전트
  V1.json  {"web": [...], "claims": [...]}                            A1 출처 검증 (선택)
  V2.json  {"web": [...], "claims": [...]}                            A2 출처 검증 (선택)

검증 장부의 corrected 항목에 "patch": {필드: 값}을 넣으면 해당 항목(ANALYSTS는 firm, NEWS는 url,
SEGS는 name으로 찾는다)에 그대로 반영한다. 사람이 다시 옮겨 적지 않는다.

옵션: --fs-div OFS · --scope annual · --np-basis parent · --fiscal-month 3 · --period-note "FY25 1Q (2025.04~06)"
잠정실적(kind=provisional) 리포트는 이 스크립트 대상이 아니다. references/provisional.md대로 만든다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dart_client import REPRT_Q, DartClient, fiscal_label_year  # noqa: E402
from verify_report import fetch_dart                 # noqa: E402  (게이트와 같은 숫자)
import corp_registry                                  # noqa: E402
from price import get_prev_close                      # noqa: E402

BS_KEYS = ("자산총계", "부채총계", "자본총계", "현금및현금성자산")
CHIP_DOT = {"co": "var(--coral)", "gn": "var(--grn)", "dn": "var(--dn)"}   # template.html에 있는 색만 쓴다


def _pct(c, p):
    return None if not p else (c - p) / abs(p) * 100


def _src(a) -> dict:
    s = {"corp_code": a.corp_code, "year": str(a.year), "reprt_code": str(a.reprt), "fs_div": a.fs_div}
    if a.scope == "annual":
        s["scope"] = "annual"
    if a.np_basis == "parent":
        s["np_basis"] = "parent"
    if a.fiscal_month != 12:
        s["fiscal_month"] = a.fiscal_month
    return s


def _corp(corp_code: str) -> dict:
    res = corp_registry.resolve(corp_code)
    if res["status"] != "ok":
        sys.exit(f"corp_code {corp_code}를 상장사 목록에서 찾지 못했다: {res['message']}")
    return res["corp"]


def _fetch(a):
    """연결 → (013이면) 개별 순서로 부른다. 둘 다 없으면 정기보고서 미제출이다."""
    try:
        return fetch_dart(_src(a))
    except ConnectionError as e:   # DartError: 재시도 후에도 네트워크·DART 장애
        sys.exit(f"DART에 접속하지 못했다({e}). 잠시 뒤 다시 실행한다.")
    except LookupError as e:
        if "020" in str(e):
            sys.exit("DART 일일 호출 한도(2만 건)를 넘었다(status 020). 내일 다시 하거나 다른 키를 쓴다.")
        if "800" in str(e):
            sys.exit("DART 시스템 점검 중이다(status 800). 잠시 뒤 다시 실행한다.")
        if "013" in str(e) and a.fs_div == "CFS":
            a.fs_div = "OFS"
            try:
                out = fetch_dart(_src(a))
                print("ℹ️  연결재무제표가 없어 개별재무제표(OFS)로 만든다(build도 자동으로 같게 처리한다).", file=sys.stderr)
                return out
            except LookupError:
                pass
        sys.exit(f"DART 재무제표를 받지 못했다({e}). 이 분기 정기보고서가 아직 제출되지 않았을 수 있다. "
                 "period 명령으로 최근 제출 보고서를 확인하거나, 잠정실적으로 만들려면 references/provisional.md를 따른다.")


def collect(a) -> dict:
    """DART·주가에서 리포트의 모든 숫자를 만든다. facts와 build가 같은 값을 쓴다."""
    corp = _corp(a.corp_code)
    if a.fiscal_month is None:
        a.fiscal_month = corp["fiscal_month"] or 12
    vals, items, _div, _bs = _fetch(a)
    np_key = "np_parent" if a.np_basis == "parent" else "np_total"
    miss = [k for k in ("rev", "op", np_key) if k not in vals or None in vals[k]]
    if miss:
        sys.exit(f"DART에 핵심 계정이 없다: {miss}. 게이트를 통과할 수 없으니 사용자에게 알리고 중단한다.")
    raw = {"rev": vals["rev"], "op": vals["op"], "np": vals[np_key]}
    r = {k: (round(c), round(p)) for k, (c, p) in raw.items()}

    q = REPRT_Q[str(a.reprt)]
    fy = fiscal_label_year(a.year, a.reprt, a.fiscal_month)
    if a.scope == "annual":
        cur_full, prv_full, cur_s, prv_s, nav = f"FY {fy}", f"FY {fy - 1}", f"FY{fy % 100:02d}", f"FY{(fy - 1) % 100:02d}", f"{fy % 100:02d} FY"
    else:
        cur_full, prv_full = f"{q} {fy}", f"{q} {fy - 1}"
        cur_s, prv_s, nav = f"{q}{fy % 100:02d}", f"{q}{(fy - 1) % 100:02d}", f"{fy % 100:02d} {q}"

    bs = {}
    for it in items:
        nm = it.get("account_nm", "").strip()
        if it.get("sj_div") == "BS" and nm in BS_KEYS and nm not in bs:
            def jo(v):
                try:
                    return round(int(str(v).replace(",", "")) / 1e12, 1)
                except (TypeError, ValueError):
                    return None
            bs[nm] = (jo(it.get("thstrm_amount")), jo(it.get("frmtrm_amount")))

    px = get_prev_close(corp["stock_code"])
    if not px:
        sys.exit("KRX 일봉을 받지 못했다(price.py). 잠시 뒤 다시 실행한다. 다른 소스로 채우지 않는다.")

    def line(k, label):
        c, p = r[k]
        y = _pct(*raw[k])
        return f"{label} {p:,}억 → {c:,}억 ({c - p:+,}억, {y:+.1f}%)"

    opm = (raw["op"][1] / raw["rev"][1] * 100, raw["op"][0] / raw["rev"][0] * 100)
    npm = (raw["np"][1] / raw["rev"][1] * 100, raw["np"][0] / raw["rev"][0] * 100)
    d = px["date"]
    facts = {
        "회사": f"{corp['corp_name']} ({corp['stock_code']}, {corp['market_label']})",
        "기간": f"{prv_full} → {cur_full}" + (" (연결)" if a.fs_div == "CFS" else " (개별)"),
        "매출": line("rev", "매출"),
        "영업이익": line("op", "영업이익") + f", OPM {opm[0]:.1f}% → {opm[1]:.1f}% ({opm[1] - opm[0]:+.1f}pp)",
        "순이익": line("np", "순이익") + f", NPM {npm[0]:.1f}% → {npm[1]:.1f}%",
        "재무상태(조)": {k: f"{v[1]}조 → {v[0]}조" for k, v in bs.items() if None not in v},
        "주가": f"{px['close']:,}원 ({int(d[4:6])}/{int(d[6:])} 종가, {px['change_pct']:+.2f}%), 52주 {px['w52_range']}원",
    }
    return {"corp": corp, "raw": raw, "r": r, "opm": opm, "npm": npm, "px": px, "facts": facts,
            "labels": {"cur_full": cur_full, "prv_full": prv_full, "cur_s": cur_s, "prv_s": prv_s, "nav": nav, "fy": fy}}


def _load(p: pathlib.Path, need=True):
    if not p.exists():
        if need:
            sys.exit(f"조각 파일이 없다: {p}")
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _apply_patches(js: dict, ledgers: list[dict]) -> None:
    """검증 장부의 patch를 본문에 반영한다. 키 필드(url·firm·name)를 고치면 장부의 key도 따라 옮긴다."""
    keyf = {"ANALYSTS": "firm", "NEWS": "url", "SEGS": "name"}
    for led in ledgers:
        for e in led.get("web", []):
            patch, sec = e.get("patch"), e.get("sec")
            if not patch or sec not in keyf:
                continue
            for item in js.get(sec, []):
                if item.get(keyf[sec]) == e.get("key"):
                    item.update(patch)
                    if keyf[sec] in patch:
                        e["key"] = patch[keyf[sec]]
                        if sec == "NEWS":
                            e["url"] = patch["url"]


def build(a) -> None:
    c = collect(a)
    parts = pathlib.Path(a.parts)
    A1, A2, B, C = (_load(parts / f) for f in ("A1.json", "A2.json", "B.json", "C.json"))
    ledgers = [x for x in (_load(parts / "V1.json", False), _load(parts / "V2.json", False)) if x]
    corp, r, raw, lb, px = c["corp"], c["r"], c["raw"], c["labels"], c["px"]

    # 1) 조각을 화면 데이터 모양으로 → 2) 검증 patch 반영 → 3) 그 결과로 검사·계산 (patch가 계산에 들어가야 한다)
    segs = [{"name": s["name"], "sub": s.get("sub", ""), "cat": s.get("cat", "other"), "q25": s["q25"], "q26": s["q26"],
             "est": s.get("est", True)} for s in A2["SEGS"]]          # est가 없으면 추정으로 본다(보수적)
    analysts = [{k: x.get(k) for k in ("firm", "r", "tp", "from", "date", "note")} for x in A2["ANALYSTS"]]
    chips = [{"cls": c_["cls"], "dot": CHIP_DOT.get(c_["cls"], "var(--coral)"), "txt": c_["txt"]} for c_ in C["CHIPS"]]
    js = {"CHIPS": chips, "SEGS": segs, "TOT25": r["rev"][1], "TOT26": r["rev"][0], "DELTA": [],
          "CURR": px["close"], "NAME": corp["corp_name"], "CONS": {},
          "ANALYSTS": analysts, "BULLS": C["BULLS"], "BEARS": C["BEARS"], "NEWS": A1["NEWS"], "PERSONAS": B}
    _apply_patches(js, ledgers)

    s25, s26 = sum(s["q25"] for s in segs), sum(s["q26"] for s in segs)
    if abs(s25 - r["rev"][1]) > len(segs) or abs(s26 - r["rev"][0]) > len(segs):
        sys.exit(f"SEGS 합계가 총매출과 다르다: 전년 {s25} vs {r['rev'][1]}, 당기 {s26} vs {r['rev'][0]}. "
                 "A2.json의 부문 숫자를 고치거나 차이를 연결조정 행(est: true)으로 넣고 다시 조립한다.")
    delta = [{"name": s["name"], "d": s["q26"] - s["q25"], "est": s["est"]} for s in segs]
    delta.append({"name": "합계", "d": sum(x["d"] for x in delta), "tot": True})
    js["DELTA"] = delta
    up = sum(x["d"] for x in delta[:-1] if x["d"] > 0)
    dn = sum(x["d"] for x in delta[:-1] if x["d"] < 0)

    bad = [x["firm"] for x in js["ANALYSTS"] if not isinstance(x.get("tp"), (int, float)) or x["tp"] <= 0]
    if bad:
        sys.exit(f"증권사 목표가가 없다: {bad}. A2.json에서 목표가(tp, 원 단위 정수)가 확인된 증권사만 남기고 다시 조립한다.")
    # ANALYSTS가 비어 있으면 '커버리지 없음' 리포트다(중소형주에 흔하다). 목표가 칸은 숫자 없이 표시한다
    # 컨센 수는 표의 의견에서 다시 센다 (patch로 의견이 바뀌어도 맞도록)
    js["CONS"] = {k: sum(1 for x in js["ANALYSTS"] if x["r"].lower() == k) for k in ("buy", "hold", "sell")}

    tps = [x["tp"] for x in js["ANALYSTS"]]
    tp_avg = round(sum(tps) / len(tps)) if tps else None
    cons, n = js["CONS"], sum(js["CONS"].values()) or 1

    def yoy_text(k):
        cur, prv = r[k]
        return f"{cur - prv:+,}억 &nbsp;({_pct(*raw[k]):+.1f}% YoY)"

    def margin(label, pair):
        return f"{label} &nbsp;{pair[0]:.1f}%<span class=\"arr\"> → </span><span class=\"b\">{pair[1]:.1f}%</span>"

    d = px["date"]
    fy = lb["fy"]
    meta = {
        "name": corp["corp_name"], "base_date": dt.date.today().strftime("%Y.%m.%d"), "code": corp["stock_code"],
        "period_full": a.period_note or f"{lb['prv_full']} vs {lb['cur_full']}",
        "basis": ("연결" if a.fs_div == "CFS" else "개별") + " · 전년은 이번 보고서의 비교 수치(재작성 반영)",
        "price": f"{px['close']:,}", "price_chg": f"{px['change_pct']:+.2f}% ({int(d[4:6])}/{int(d[6:])} 종가)",
        "w52_range": px["w52_range"],
        "nav_label": f"{lb['nav']} 실적", "kpi_label": f"{lb['nav']} 실적 요약",
        "rev_val": f"{r['rev'][0]:,}", "rev_dir": "up" if r["rev"][0] >= r["rev"][1] else "down",
        "rev_yoy": yoy_text("rev"), "rev_sub": f"{lb['prv_s']} &nbsp;{r['rev'][1]:,}억",
        "op_val": f"{r['op'][0]:,}", "op_dir": "up" if r["op"][0] >= r["op"][1] else "down",
        "op_yoy": yoy_text("op"), "op_sub": margin("OPM", c["opm"]),
        "np_val": f"{r['np'][0]:,}", "np_dir": "up" if r["np"][0] >= r["np"][1] else "down",
        "np_yoy": yoy_text("np"), "np_sub": margin("NPM", c["npm"]),
        "g_net": f"{delta[-1]['d']:+,}억", "g_up": f"{up:+,}억", "g_dn": f"{dn:+,}억",
        "q_prev_full": lb["prv_full"], "q_cur_full": lb["cur_full"], "q_prev_short": lb["prv_s"], "q_cur_short": lb["cur_s"],
        "mix_prev": f"비중{(fy - 1) % 100:02d}", "mix_cur": f"비중{fy % 100:02d}",
        "coverage_note": (f"표의 {len(tps)}개 증권사 기준 (전체 커버리지 집계는 미확인)" if tps else
                          "실적 발표 뒤 나온 증권사 보고서를 찾지 못했다 (커버리지 없음, 미확인)"),   # 실제 건수로 만든다
        "cons_buy_pct": f"{cons['buy'] / n * 100:.1f}%", "cons_buy": str(cons["buy"]),
        "cons_hold_pct": f"{cons['hold'] / n * 100:.1f}%", "cons_hold": str(cons["hold"]),
        "cons_sell_pct": f"{cons['sell'] / n * 100:.1f}%", "cons_sell": str(cons["sell"]),
        "tp_cur": f"{px['close']:,}원",
        "tp_low": f"{min(tps):,}원" if tps else "없음", "tp_avg": f"{tp_avg:,}원" if tps else "없음",
        "tp_high": f"{max(tps):,}원" if tps else "없음",
        "tp_upside": f"{(tp_avg - px['close']) / px['close'] * 100:+.1f}%" if tps else "해당 없음",
        "filter_cats": A2.get("filter_cats", []),
    }
    web = [e for led in ledgers for e in led.get("web", [])]
    if not any(e.get("sec") == "CONS" for e in web):
        web.append({"sec": "CONS", "key": "coverage", "status": "corrected", "url": "",
                    "note": f"전체 집계 출처 없음 → 표 {len(tps)}개사 기준"})
    if tps and not any(e.get("sec") == "meta" and e.get("key") == "tp_avg" for e in web):
        web.append({"sec": "meta", "key": "tp_avg", "status": "confirmed", "url": "",
                    "note": f"표 {len(tps)}개사 단순평균 (assemble_report.py 계산)"})
    data = {"meta": meta, "js": js,
            "audit": {"src": _src(a), "web": web, "claims": [x for led in ledgers for x in led.get("claims", [])]}}
    ex = set(json.loads((HERE / "data.example.json").read_text(encoding="utf-8"))["meta"])
    if ex ^ set(meta):
        sys.exit(f"meta 키가 data.example.json과 다르다: {sorted(ex ^ set(meta))}")
    if len(B) != 13:
        sys.exit(f"PERSONAS가 13인이 아니다: {len(B)}")
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    missing = [v for v in ("V1", "V2") if not (parts / f"{v}.json").exists()]
    print(f"✅ {out}  (검증 장부 {len(web)}건" + (f", 아직 없는 출처 검증: {', '.join(missing)})" if missing else ")"))


def period(a) -> dict:
    """가장 최근에 제출된 정기보고서로 기간을 정한다. 결산월·코넥스 여부는 상장사 목록에서 읽는다."""
    corp = _corp(a.corp_code)
    fm = corp["fiscal_month"] or 12
    konex = corp["market"] == "코넥스"
    rep = DartClient().latest_periodic_report(a.corp_code, fiscal_month=fm, annual_only=konex)
    if not rep:
        sys.exit("최근 460일 안에 제출된 정기보고서가 없다. 사용자에게 알리고 중단한다.")
    args = f"--year {rep['bsns_year']} --reprt {rep['reprt_code']}"
    if fm != 12:
        args += f" --fiscal-month {fm}"
    if konex:
        args += " --scope annual"
    return {**rep, "fiscal_month": fm, "konex": konex, "args": args}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="DART 리포트 data.json 조립")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("period")
    pp.add_argument("--corp-code", required=True)
    for name in ("facts", "build"):
        p = sub.add_parser(name)
        p.add_argument("--corp-code", required=True)
        p.add_argument("--year", required=True)
        p.add_argument("--reprt", required=True, choices=list(REPRT_Q))
        p.add_argument("--fs-div", default="CFS", choices=["CFS", "OFS"])
        p.add_argument("--scope", default="quarter", choices=["quarter", "annual"])
        p.add_argument("--np-basis", default="total", choices=["total", "parent"])
        p.add_argument("--fiscal-month", type=int, default=None, help="생략하면 상장사 목록의 결산월")
        if name == "build":
            p.add_argument("--parts", required=True)
            p.add_argument("--period-note", default="")
            p.add_argument("-o", "--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "period":
        print(json.dumps(period(a), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "facts":
        print(json.dumps(collect(a)["facts"], ensure_ascii=False, indent=1))
    else:
        build(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
