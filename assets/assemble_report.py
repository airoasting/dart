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
  A2a.json {"ANALYSTS": [...]}                                       증권사 에이전트
           (CONS·커버리지 문구는 이 스크립트가 ANALYSTS에서 만든다)
  A2b.json {"SEGS": [...], "filter_cats": [...]}                     부문 매출 에이전트
           (예전 형식인 A2.json 하나에 셋을 다 담아도 된다. A2a·A2b가 있으면 그쪽을 쓴다)
  B.json   [... 13개 PERSONAS ...]                                    페르소나 에이전트
  C.json   {"BULLS": [...], "BEARS": [...], "CHIPS": [...]}            강세·약세 에이전트
  V1.json  {"web": [...], "claims": [...]}                            A1 출처 검증 (선택)
  V2a.json {"web": [...], "claims": [...]}                            A2a 출처 검증 (선택)
  V2b.json {"web": [...], "claims": [...]}                            A2b 출처 검증 (선택, 예전 형식은 V2.json)

검증 장부의 corrected 항목에 "patch": {필드: 값}을 넣으면 해당 항목(ANALYSTS는 firm, NEWS는 url,
SEGS는 name으로 찾는다)에 그대로 반영한다. 사람이 다시 옮겨 적지 않는다.

옵션: --fs-div OFS · --scope annual · --np-basis parent · --fiscal-month 3
잠정실적(kind=provisional) 리포트는 이 스크립트 대상이 아니다. references/provisional.md대로 만든다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dart_client import REPRT_OFFSET, REPRT_Q, DartClient, fiscal_label, fiscal_label_year  # noqa: E402
from verify_report import fetch_dart, review_problems, turn_label   # noqa: E402  (게이트와 같은 숫자·표기·형식)
import corp_registry                                  # noqa: E402
from price import get_prev_close                      # noqa: E402

BS_KEYS = ("자산총계", "부채총계", "자본총계", "지배주주자본", "비지배지분", "현금및현금성자산",
           "단기차입금", "장기차입금", "미지급법인세", "이연법인세부채", "이익잉여금", "예수부채")
# 이름이 회사마다 달라 account_id로 고정한다 (카카오 2Q26 실측 id)
BS_IDS = {"ifrs-full_EquityAttributableToOwnersOfParent": "지배주주자본",
          "ifrs-full_NoncontrollingInterests": "비지배지분",
          "ifrs-full_CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings": "단기차입금",
          "ifrs-full_ShorttermBorrowings": "단기차입금",
          "ifrs-full_LongtermBorrowings": "장기차입금",
          "ifrs-full_CurrentTaxLiabilitiesCurrent": "미지급법인세",
          "ifrs-full_CurrentTaxLiabilities": "미지급법인세",
          "ifrs-full_CurrentDepositsFromCustomers": "예수부채",
          "ifrs-full_DeferredTaxLiabilities": "이연법인세부채",
          "ifrs-full_RetainedEarnings": "이익잉여금"}
CHIP_DOT = {"co": "var(--coral)", "gn": "var(--up)", "dn": "var(--dn)"}   # 좋음은 오름 색, 나쁨은 내림 색   # template.html에 있는 색만 쓴다


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


def pp_shown(prv, cur) -> float:
    """화면에 찍힌 마진(소수 한 자리)끼리의 차이. 2.75% → 5.25%는 '2.7% → 5.3%'로 보이니 +2.6pp로 쓴다(원값 차이 2.5는 읽는 사람에게 틀려 보인다)."""
    return round(float(f"{cur:.1f}") - float(f"{prv:.1f}"), 1)


def _amt_won(v):
    try:
        return int(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _bs_fmt(*won):
    """재무상태 표기. 1조가 넘으면 조(소수 한 자리), 아니면 억(정수). 소형사가 '0.0조'로 찍히지 않게 둘을 같은 단위로 맞춘다."""
    if max(abs(w) for w in won) >= 1e12:
        return [f"{w / 1e12:.1f}조" for w in won]
    return [f"{round(w / 1e8):,}억" for w in won]


def fiscal_period_note(q: str, fy: int, fm: int, annual: bool) -> str | None:
    """결산월이 12월이 아니면 실제 달력 기간을 밝힌다: 'FY25 1Q (2025.04~06)', 'FY25 (2025.04~2026.03)'. 12월 결산은 None."""
    fm = int(fm or 12)
    if fm == 12:
        return None
    n = 4 if annual else int(q[0])
    first = 1 if annual else n
    sm, em = (fm + 3 * (first - 1)) % 12 + 1, (fm + 3 * n - 1) % 12 + 1     # 기간 첫 달, 끝 달
    sy, ey = fy + (0 if sm > fm else 1), fy + (0 if em > fm else 1)
    span = f"{sy}.{sm:02d}~{em:02d}" if sy == ey else f"{sy}.{sm:02d}~{ey}.{em:02d}"
    return f"FY{fy % 100:02d}{'' if annual else ' ' + q} ({span})"


def collect(a) -> dict:
    """DART·주가에서 리포트의 모든 숫자를 만든다. facts와 build가 같은 값을 쓴다."""
    corp = _corp(a.corp_code)
    if a.fiscal_month is None:
        a.fiscal_month = corp["fiscal_month"] or 12
    vals, items, _div, prev = _fetch(a)
    cur = sorted({it.get("currency") for it in items if it.get("currency")} - {"KRW"})
    if cur:   # 국내 상장 외국 기업(950xxx 등)은 달러 등으로 공시한다. 원 단위로 읽으면 모든 숫자가 틀린다
        sys.exit(f"이 회사는 재무제표를 {', '.join(cur)}로 공시한다. 원화(억원) 기준인 이 리포트로는 만들 수 없다. "
                 "사용자에게 알리고 중단한다.")
    np_key = "np_parent" if a.np_basis == "parent" else "np_total"
    miss = [k for k in ("rev", "op", np_key) if k not in vals or None in vals[k]]
    if miss:
        sys.exit(f"DART에 핵심 계정이 없다: {miss}. 게이트를 통과할 수 없으니 사용자에게 알리고 중단한다.")
    raw = {"rev": vals["rev"], "op": vals["op"], "np": vals[np_key]}
    r = {k: (round(c), round(p)) for k, (c, p) in raw.items()}

    q = REPRT_Q[str(a.reprt)]
    fy = fiscal_label_year(a.year, a.reprt, a.fiscal_month)
    if a.scope == "annual":
        cur_full, prv_full, cur_s, prv_s, nav = f"FY {fy}", f"FY {fy - 1}", f"FY{fy % 100:02d}", f"FY{(fy - 1) % 100:02d}", f"FY{fy % 100:02d}"
    else:
        cur_full, prv_full = f"{q} {fy}", f"{q} {fy - 1}"
        cur_s, prv_s = f"{q}{fy % 100:02d}", f"{q}{(fy - 1) % 100:02d}"
        nav = cur_s

    note = fiscal_period_note(q, fy, a.fiscal_month, a.scope == "annual")

    bs = {}
    for it in items:
        nm = it.get("account_nm", "").strip()
        nm = BS_IDS.get(it.get("account_id"), nm)
        if it.get("sj_div") == "BS" and nm in BS_KEYS and nm not in bs:
            bs[nm] = (_amt_won(it.get("thstrm_amount")), _amt_won(it.get("frmtrm_amount")))
    (sy, sm), (py, pm), (ey, em) = period_bounds(a.year, a.reprt, a.fiscal_month)
    bs_label = f"재무상태 ({py}.{pm:02d}말 → {ey}.{em:02d}말)"     # 비교는 전기말이다(전년 동기말이 아니다)
    cum = f"{sy}.{sm:02d}~{ey}.{em:02d} 누적"
    bridge = pl_bridge(items, a, raw["np"])
    cash = cash_flow(items)
    scope = scope_notes(items, bridge)
    restated = restatement(prev, raw, a)

    px = _price(corp["stock_code"], getattr(a, "parts", None), fresh=getattr(a, "cmd", None) == "facts")
    if not px:
        sys.exit("KRX 일봉을 받지 못했다(price.py). 잠시 뒤 다시 실행한다. 다른 소스로 채우지 않는다.")

    def chg(k):
        """증감률 표기: 적자가 끼면 흑자 전환·적자 축소 등, 아니면 +N.N%. 화면·facts·게이트가 같은 규칙을 쓴다."""
        lab = turn_label(*r[k])
        if lab:
            return lab
        y = _pct(*raw[k])
        return "N/A" if y is None else f"{y:+.1f}%"

    def line(k, label):
        c, p = r[k]
        return f"{label} {p:,}억 → {c:,}억 ({c - p:+,}억, {chg(k)})"

    opm = (raw["op"][1] / raw["rev"][1] * 100, raw["op"][0] / raw["rev"][0] * 100)
    npm = (raw["np"][1] / raw["rev"][1] * 100, raw["np"][0] / raw["rev"][0] * 100)
    d = px["date"]
    facts = {
        "회사": f"{corp['corp_name']} ({corp['stock_code']}, {corp['market_label']})",
        "기간": f"{prv_full} → {cur_full}" + (" (연결)" if a.fs_div == "CFS" else " (개별)"),
        "매출": line("rev", "매출"),
        "영업이익": line("op", "영업이익") + f", 영업이익률 {opm[0]:.1f}% → {opm[1]:.1f}% ({pp_shown(*opm):+.1f}%p)",
        "순이익": line("np", "순이익") + f", 순이익률 {npm[0]:.1f}% → {npm[1]:.1f}%",
        bs_label: {k: f"{_bs_fmt(v[1], v[0])[0]} → {_bs_fmt(v[1], v[0])[1]}" for k, v in bs.items() if None not in v},
        "주가": f"{px['close']:,}원 ({int(d[4:6])}/{int(d[6:])} 종가, {px['change_pct']:+.2f}%), 52주 {px['w52_range']}원",
    }
    if bridge:
        facts["순이익 구성"] = bridge["lines"]
    if cash:
        facts[f"현금흐름 ({cum})"] = cash
    if scope:
        facts["함께 읽을 것"] = scope
    if restated:
        facts["전년 수치 재작성"] = restated
    qoq = prev_quarter(a, raw)
    if qoq:
        facts[f"직전 분기({qoq['label']}) 대비"] = qoq["lines"]
    val = valuation(a, px, items)
    if val:
        facts["시가총액"] = val
    return {"corp": corp, "raw": raw, "r": r, "opm": opm, "npm": npm, "px": px, "facts": facts,
            "bridge": bridge, "restated": restated, "restated_raw": getattr(restatement, "last", []) if restated else [],
            "chg": {k: chg(k) for k in ("rev", "op", "np")},
            "labels": {"note": note, "cur_full": cur_full, "prv_full": prv_full, "cur_s": cur_s, "prv_s": prv_s, "nav": nav, "fy": fy}}


def period_bounds(year, reprt, fiscal_month):
    """(누적 시작 연·월, 전기말 연·월, 당기말 연·월). DART bsns_year는 기간 끝 월의 연도다."""
    fm = int(fiscal_month or 12)
    em = (fm + REPRT_OFFSET[str(reprt)] - 1) % 12 + 1
    ey = int(year)
    sm = fm % 12 + 1
    sy = ey if sm <= em else ey - 1
    py, pm = (sy - 1, 12) if sm == 1 else (sy, sm - 1)
    return (sy, sm), (py, pm), (ey, em)


def _by_id(items, *sj):
    return {it.get("account_id"): it for it in items if it.get("sj_div") in sj}


def _qpair(it, a):
    """facts의 매출·이익과 같은 기간의 (당기, 전년) 원 단위. 4Q 단독은 3Q 누적을 빼야 해서 None."""
    if str(a.reprt) == "11011" and a.scope == "quarter":
        return None
    cur = _amt_won(it.get("thstrm_amount"))
    prv = _amt_won(it.get("frmtrm_q_amount")) if str(a.reprt) != "11011" else None
    if prv is None:
        prv = _amt_won(it.get("frmtrm_amount"))
    return None if None in (cur, prv) else (cur, prv)


def pl_bridge(items, a, np_raw):
    """영업이익 아래에서 순이익까지: 세전이익, 법인세, 계속영업, 중단영업, 지배주주순이익.
    순이익이 크게 바뀐 원인이 공시 숫자에 있을 때 에이전트가 '원인 확인 필요'로 남기지 않게 한다."""
    ids = _by_id(items, "IS", "CIS")
    rows = (("세전이익", "ifrs-full_ProfitLossBeforeTax"), ("법인세", "ifrs-full_IncomeTaxExpenseContinuingOperations"),
            ("계속영업이익", "ifrs-full_ProfitLossFromContinuingOperations"),
            ("중단영업이익", "ifrs-full_ProfitLossFromDiscontinuedOperations"),
            ("계속영업이익 지배주주 몫", "ifrs-full_IncomeFromContinuingOperationsAttributableToOwnersOfParent"),
            ("중단영업이익 지배주주 몫", "ifrs-full_IncomeFromDiscontinuedOperationsAttributableToOwnersOfParent"),
            ("지배주주순이익", "ifrs-full_ProfitLossAttributableToOwnersOfParent"))
    got = {}
    for label, aid in rows:
        pr = _qpair(ids[aid], a) if aid in ids else None
        if pr:
            got[label] = pr
    if len(got) < 2:
        return None
    eok = lambda v: round(v / 1e8)
    lines = [f"{k} {eok(p):,}억 → {eok(c):,}억" for k, (c, p) in got.items()]
    if "세전이익" in got and "법인세" in got and all(got["세전이익"]):
        (tc, tp), (bc, bp) = got["법인세"], got["세전이익"]
        lines.insert(2, f"실효세율(법인세 ÷ 세전이익) {tp / bp * 100:.1f}% → {tc / bc * 100:.1f}%")
    parent = getattr(a, "np_basis", "total") == "parent"     # 순이익 기준과 같은 기준의 중단영업으로 나눈다
    dkey, ckey = ("중단영업이익 지배주주 몫", "계속영업이익 지배주주 몫") if parent else ("중단영업이익", "계속영업이익")
    if dkey in got:
        dc, dp = got[dkey]
        npc, npp = np_raw
        lines.append(f"{'지배주주' if parent else ''}순이익 증감 {round(npc - npp):+,}억 가운데 {dkey} 증감 {eok(dc - dp):+,}억")
    if not parent:   # 연결 기준이면 지배주주 몫 줄은 참고로만 (계속영업 지배주주 몫은 생략해 줄 수를 줄인다)
        lines = [x for x in lines if not x.startswith("계속영업이익 지배주주 몫")]
    return {"lines": lines, "rows": got, "keys": (ckey, dkey)}


CF_TOTALS = {"Operating": "ifrs-full_CashFlowsFromUsedInOperatingActivities",
             "Investing": "ifrs-full_CashFlowsFromUsedInInvestingActivities",
             "Financing": "ifrs-full_CashFlowsFromUsedInFinancingActivities"}
SCOPE_IDS = ("ifrs-full_CashFlowsFromLosingControlOfSubsidiariesOrOtherBusinessesClassifiedAsInvestingActivities",)


def _cf_sections(items):
    """현금흐름표를 활동별로 나눈다. 하위 줄은 회사마다 dart_·비표준 id라 id가 아니라 표 순서(소계 뒤 다음 소계 전)로 묶는다."""
    cf = [it for it in items if it.get("sj_div") == "CF"]
    cf.sort(key=lambda it: int(it.get("ord") or 0))
    out, cur = {}, None
    for it in cf:
        key = next((k for k, aid in CF_TOTALS.items() if it.get("account_id") == aid), None)
        if key:
            cur = key
            out[key] = {"total": it, "subs": []}
        elif cur and not str(it.get("account_id", "")).startswith(("ifrs-full_IncreaseDecrease", "ifrs-full_EffectOfExchange")):
            out[cur]["subs"].append(it)
    return out


def cash_flow(items):
    """영업·투자·재무활동 현금흐름(누적), 투자·재무활동에서 가장 큰 항목, 차입·상환 합계, 배당금 지급."""
    sec = _cf_sections(items)
    out = []
    for label, key in (("영업활동", "Operating"), ("투자활동", "Investing"), ("재무활동", "Financing")):
        if key not in sec:
            continue
        v = _amt_won(sec[key]["total"].get("thstrm_amount"))
        if v is None:
            continue
        txt = f"{label} {_bs_fmt(v, v)[0]}"
        subs = [(abs(_amt_won(it.get("thstrm_amount")) or 0), it) for it in sec[key]["subs"]]
        if key != "Operating" and subs:
            big = max(subs, key=lambda x: x[0])[1]
            bv = _amt_won(big.get("thstrm_amount"))
            txt += f" (가장 큰 항목: {big.get('account_nm', '').strip()} {_bs_fmt(bv, bv)[0]})"
        out.append(txt)
    fin = sec.get("Financing", {}).get("subs", [])
    borrow = sum(_amt_won(it.get("thstrm_amount")) or 0 for it in fin if "차입" in it.get("account_nm", "") and "상환" not in it.get("account_nm", ""))
    repay = sum(_amt_won(it.get("thstrm_amount")) or 0 for it in fin if "상환" in it.get("account_nm", "") and "차입" in it.get("account_nm", ""))
    if borrow or repay:
        out.append(f"차입금 차입 {_bs_fmt(borrow, borrow)[0]}, 상환 {_bs_fmt(repay, repay)[0]}")
    div = next((it for it in fin if it.get("account_id") == "ifrs-full_DividendsPaidClassifiedAsFinancingActivities"), None)
    dv = _amt_won(div.get("thstrm_amount")) if div else None
    if dv:
        out.append(f"배당금 지급 {_bs_fmt(dv, dv)[0]}")
    return out or None


def scope_notes(items, bridge):
    """연결 범위 변동·자본 직접 처분손익·중단영업 귀속 비율처럼 따로 읽으면 오독하는 줄을 묶어 밝힌다."""
    out = []
    cf = [it for it in items if it.get("sj_div") == "CF"]
    sc = next((it for it in cf if it.get("account_id") in SCOPE_IDS), None)
    v = _amt_won(sc.get("thstrm_amount")) if sc else None
    if v:
        out.append(f"연결 범위가 바뀌었다({sc.get('account_nm', '').strip()} {_bs_fmt(v, v)[0]}). 재무상태의 차입금·무형자산·비지배지분 증감에는 "
                   "연결에서 빠진 회사 몫이 섞여 있어, 상환·개선이나 악화로 읽지 않는다.")
    fv = next((it for it in cf if "FairValueThroughOtherComprehensiveIncome" in (it.get("account_id") or "")
               and "Proceeds" in (it.get("account_id") or "")), None)
    fvv = _amt_won(fv.get("thstrm_amount")) if fv else None
    if fvv and fvv >= 1e11:
        out.append(f"기타포괄손익-공정가치 금융자산을 {_bs_fmt(fvv, fvv)[0]} 처분했다. 이 처분손익은 손익계산서가 아니라 자본(이익잉여금 등)에 바로 반영되고, "
                   "관련 세금은 이연법인세부채 감소와 미지급법인세 증가로 나타날 수 있다.")
    rows = (bridge or {}).get("rows", {})
    if "중단영업이익" in rows and "중단영업이익 지배주주 몫" in rows:
        (tc, tp), (pc, pp_) = rows["중단영업이익"], rows["중단영업이익 지배주주 몫"]
        if tc and tp and abs(pc / tc - pp_ / tp) * 100 >= 20:
            out.append(f"중단영업 손실 가운데 지배주주 몫 비율이 {pp_ / tp * 100:.0f}% → {pc / tc * 100:.0f}%로 바뀌었다. "
                       "지분율과 다르게 움직이면 처분·재측정 손실이 섞였을 수 있으나, 공시 주석을 확인하기 전에는 단정하지 않는다.")
    return out or None


def _np_bridge_text(bridge):
    """KPI 순이익 칸 아래 한 줄. 중단영업이 있을 때만."""
    rows = (bridge or {}).get("rows", {})
    ckey, dkey = (bridge or {}).get("keys", ("계속영업이익", "중단영업이익"))
    if ckey not in rows or dkey not in rows:
        return ""
    who = "지배주주 " if "지배주주" in dkey else ""
    return f"{who}계속영업 {round(rows[ckey][0] / 1e8):,}억 · 중단영업 {round(rows[dkey][0] / 1e8):,}억"


def prev_quarter_src(a):
    """직전 분기 보고서의 (bsns_year, reprt_code). 연간 리포트면 None."""
    if a.scope == "annual":
        return None
    _, _, (ey, em) = period_bounds(a.year, a.reprt, a.fiscal_month)
    pm, py = (em - 3, ey) if em > 3 else (em + 9, ey - 1)
    cyc = {"11013": "11011", "11012": "11013", "11014": "11012", "11011": "11014"}
    return str(py), cyc[str(a.reprt)]


def prev_quarter(a, raw):
    """직전 분기 대비(전 분기 단독 값). 4Q는 연간 − 3Q 누적을 fetch_dart가 계산한다. 못 받으면 넣지 않는다."""
    src = prev_quarter_src(a)
    if not src:
        return None
    try:
        pv, *_ = fetch_dart({**_src(a), "year": src[0], "reprt_code": src[1], "scope": "quarter"})
    except Exception:
        return None
    lines = []
    for k, label in (("rev", "매출"), ("op", "영업이익")):
        c_, p_ = raw[k][0], (pv.get(k) or (None,))[0]
        if p_ is None:
            continue
        lab = turn_label(c_, p_)
        y = _pct(c_, p_)
        lines.append(f"{label} {round(p_):,}억 → {round(c_):,}억 ({lab or (f'{y:+.1f}%' if y is not None else 'N/A')})")
    lab = fiscal_label(src[0], src[1], a.fiscal_month)
    return {"label": lab, "lines": lines} if lines else None


def valuation(a, px, items):
    """시가총액 = 발행주식총수(보통주, 보고서 기준일) × 전 거래일 종가, PBR = 시가총액 ÷ 지배주주자본."""
    try:
        r = DartClient(timeout=15)._get("stockTotqySttus.json", corp_code=a.corp_code, bsns_year=str(a.year),
                                        reprt_code=str(a.reprt))
        row = next(x for x in r.get("list", []) if x.get("se") == "보통주")
        shares = _amt_won(row.get("istc_totqy"))
    except Exception:
        return None
    eq = next((_amt_won(it.get("thstrm_amount")) for it in items
               if it.get("account_id") == "ifrs-full_EquityAttributableToOwnersOfParent"), None)
    if not shares:
        return None
    cap = shares * px["close"]
    d = px["date"]
    out = f"{_bs_fmt(cap, cap)[0]} ({int(d[4:6])}/{int(d[6:])} 종가 × 보고서 기준일 보통주 {shares:,}주)"
    if eq:
        out += f", 지배주주자본 대비 PBR {cap / eq:.2f}배"
    return out


def _restated_note(c):
    """KPI 맨 아래 각주 한 문장. 중단영업이 있으면 재작성 이유로 밝힌다."""
    rs = c.get("restated_raw") or []
    if not rs:
        return []
    why = "중단영업 재분류 등" if (c.get("bridge") or {}).get("rows", {}).get("중단영업이익") else "회계 기준 변경 등"
    parts = ", ".join(f"{label} {y:+.1f}%" for label, y in rs)
    return [f"전년 숫자는 이번 보고서에 다시 실린 값이다({why}). 기사의 증가율({parts})은 처음 발표한 전년과 견준 것이라 "
            "연결 범위가 달라 같은 기준의 성장률로 보지 않는다."]


def restatement(prev, raw, a):
    """작년 보고서에 처음 실린 전년 숫자와 이번 보고서의 비교 숫자가 다르면(중단영업 재분류 등) 한 줄로 밝힌다.
    기사는 처음 발표한 숫자 기준 증가율을 쓰는 일이 많아, 밝히지 않으면 독자가 두 증가율을 맞춰 보지 못한다."""
    if str(a.reprt) == "11011" and a.scope == "quarter":
        return None
    from verify_report import _find
    out, raw_out = [], []
    for k, label in (("rev", "매출"), ("op", "영업이익")):
        it = _find(prev, k)
        p0 = _amt_won(it.get("thstrm_amount")) if it else None
        cur, prv = raw[k]
        if p0 is None or abs(p0 / 1e8 - prv) < 1:
            continue
        y0 = _pct(cur, p0 / 1e8)
        out.append(f"{label}: 처음 발표한 전년 {round(p0 / 1e8):,}억, 이번 보고서의 전년 {round(prv):,}억. "
                   f"처음 발표한 전년과 견주면 {y0:+.1f}%(기사 증가율이 다른 이유. 연결 범위가 달라 성장률이 아니다)")
        raw_out.append((label, y0))
    restatement.last = raw_out
    return out or None


PRICE_PIN = "_price.json"
PIN_MAX_DAYS = 14


def _price(code: str, parts: str | None, fresh: bool) -> dict | None:
    """facts가 받은 종가를 조각 폴더에 고정하고, build는 그 값을 다시 쓴다.
    facts와 build 사이에 날짜가 바뀌어도(16시를 넘기거나 다음 날 다시 조립) 본문 숫자와 게이트 기준이 같다."""
    pin = pathlib.Path(parts) / PRICE_PIN if parts else None
    if pin and pin.exists() and not fresh:
        px = json.loads(pin.read_text(encoding="utf-8"))
        age = (dt.date.today() - dt.date.fromisoformat(px.get("saved", "1970-01-01"))).days
        if px.get("code") == code and age <= PIN_MAX_DAYS:
            return px
        print(f"ℹ️  {pin}이 다른 종목이거나 {PIN_MAX_DAYS}일보다 오래돼 종가를 새로 받는다.", file=sys.stderr)
    px = get_prev_close(code)
    if px and pin:
        pin.parent.mkdir(parents=True, exist_ok=True)
        px = {**px, "code": code, "saved": dt.date.today().isoformat()}
        pin.write_text(json.dumps(px, ensure_ascii=False), encoding="utf-8")
    return px


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


def _load_a2(parts: pathlib.Path) -> tuple[dict, tuple[str, ...]]:
    """증권사(A2a)와 부문(A2b)을 따로 조사하면 둘을 합친다. 예전 A2.json 하나도 읽는다. (조사 결과, 있어야 할 검증 장부)"""
    if (parts / "A2a.json").exists() or (parts / "A2b.json").exists():
        return {**_load(parts / "A2a.json"), **_load(parts / "A2b.json")}, ("V1", "V2a", "V2b")
    return _load(parts / "A2.json"), ("V1", "V2")


def build(a) -> None:
    c = collect(a)
    parts = pathlib.Path(a.parts)
    A1, B, C = (_load(parts / f) for f in ("A1.json", "B.json", "C.json"))
    A2, ledger_names = _load_a2(parts)
    review = _load(parts / "R.json", False)   # 전문가 평가는 조립된 data.json을 읽고 쓰므로 첫 조립에는 없다
    if review is None:
        print("ℹ️  R.json 없음: 전문가 평가 없이 조립했다. 이 data.json으로 R 에이전트를 돌리고 다시 조립한다.", file=sys.stderr)
    elif review_problems(review):
        sys.exit("R.json 형식이 맞지 않다: " + "; ".join(review_problems(review)) + ". 같은 템플릿으로 R을 다시 띄운다.")
    ledgers = [x for x in (_load(parts / f"{v}.json", False) for v in ledger_names) if x]
    stale = False
    if review is not None:
        body = [parts / f for f in ("A1.json", "A2a.json", "A2b.json", "A2.json", "B.json", "C.json") if (parts / f).exists()]
        stale = max(f.stat().st_mtime for f in body) > (parts / "R.json").stat().st_mtime
        if stale:
            print("⚠️  R.json이 본문 조각보다 오래됐다. 고친 본문을 평가하려면 R을 다시 띄우고 다시 조립한다.", file=sys.stderr)
    corp, r, raw, lb, px = c["corp"], c["r"], c["raw"], c["labels"], c["px"]

    # 1) 조각을 화면 데이터 모양으로 → 2) 검증 patch 반영 → 3) 그 결과로 검사·계산 (patch가 계산에 들어가야 한다)
    segs = [{"name": s["name"], "sub": s.get("sub", ""), "cat": s.get("cat", "other"), "q25": s["q25"], "q26": s["q26"],
             "est": s.get("est", True)} for s in A2["SEGS"]]          # est가 없으면 추정으로 본다(보수적)
    analysts = [{k: x.get(k) for k in ("firm", "r", "tp", "from", "dir", "date", "note")} for x in A2["ANALYSTS"]]
    chips = [{"cls": c_["cls"], "dot": CHIP_DOT.get(c_["cls"], "var(--coral)"), "txt": c_["txt"]} for c_ in C["CHIPS"]]
    if not (C.get("HEADLINE") or "").strip():
        sys.exit("C.json에 HEADLINE(맨 위 결론 2문장)이 없다. agent-prompts.md의 C 템플릿으로 C를 다시 띄운다.")
    n_sent = len([x for x in re.split(r"(?<=다)\.\s*", C["HEADLINE"].strip()) if x.strip()])
    if n_sent > 2 or len(C["HEADLINE"]) > 220:
        print(f"⚠️  HEADLINE이 {n_sent}문장·{len(C['HEADLINE'])}자다. 회의에서 그대로 말할 2문장으로 줄이도록 C를 다시 띄운다.", file=sys.stderr)
    js = {"HEADLINE": C["HEADLINE"].strip(), "WATCH": C.get("WATCH", [])[:3],
          "NOTES": _restated_note(c), "NP_BRIDGE": _np_bridge_text(c["bridge"]),
          "CHIPS": chips, "SEGS": segs, "TOT25": r["rev"][1], "TOT26": r["rev"][0], "DELTA": [],
          "CURR": px["close"], "NAME": corp["corp_name"], "CONS": {},
          "ANALYSTS": analysts, "BULLS": C["BULLS"], "BEARS": C["BEARS"], "NEWS": A1["NEWS"], "PERSONAS": B,
          "REVIEW": review and {"scene": review["scene"], "stale": stale, "reviews": sorted(
              review["reviews"], key=lambda x: ("RED", "SILVER", "GOLD").index(x["role"]))}}
    _apply_patches(js, ledgers)

    s25, s26 = sum(s["q25"] for s in segs), sum(s["q26"] for s in segs)
    d25, d26 = r["rev"][1] - s25, r["rev"][0] - s26
    if (d25 or d26) and abs(d25) <= len(segs) and abs(d26) <= len(segs):
        # 부문별 억 반올림에서 생긴 작은 차이는 연결조정 행에 모아 합계를 총매출과 정확히 맞춘다(게이트는 ±1억)
        adj = next((s for s in segs if s["name"] == "연결조정"), None)
        if adj is None:
            adj = {"name": "연결조정", "sub": "부문 간 거래·반올림", "cat": "other", "q25": 0, "q26": 0, "est": True}
            segs.append(adj)
        adj["q25"] += d25; adj["q26"] += d26; adj["est"] = True
        s25, s26 = s25 + d25, s26 + d26
    if abs(s25 - r["rev"][1]) > len(segs) or abs(s26 - r["rev"][0]) > len(segs):
        sys.exit(f"SEGS 합계가 총매출과 다르다: 전년 {s25} vs {r['rev'][1]}, 당기 {s26} vs {r['rev'][0]}. "
                 "A2b.json(예전 형식은 A2.json)의 부문 숫자를 고치거나 차이를 연결조정 행(est: true)으로 넣고 다시 조립한다.")
    delta = [{"name": s["name"], "d": s["q26"] - s["q25"], "est": s["est"]} for s in segs]
    delta.append({"name": "합계", "d": sum(x["d"] for x in delta), "tot": True})
    js["DELTA"] = delta
    up = sum(x["d"] for x in delta[:-1] if x["d"] > 0)
    dn = sum(x["d"] for x in delta[:-1] if x["d"] < 0)

    bad = [x["firm"] for x in js["ANALYSTS"] if not isinstance(x.get("tp"), (int, float)) or x["tp"] <= 0]
    if bad:
        sys.exit(f"증권사 목표가가 없다: {bad}. A2a.json(예전 형식은 A2.json)에서 목표가(tp, 원 단위 정수)가 확인된 증권사만 남기고 다시 조립한다.")
    # ANALYSTS가 비어 있으면 '커버리지 없음' 리포트다(중소형주에 흔하다). 목표가 칸은 숫자 없이 표시한다
    # 컨센 수는 표의 의견에서 다시 센다 (patch로 의견이 바뀌어도 맞도록)
    js["CONS"] = {k: sum(1 for x in js["ANALYSTS"] if x["r"].lower() == k) for k in ("buy", "hold", "sell")}

    tps = [x["tp"] for x in js["ANALYSTS"]]
    flow = {"상향": 0, "하향": 0, "유지": 0, "직전 목표가 없음": 0}
    for x in js["ANALYSTS"]:
        f, dr = x.get("from"), x.get("dir")
        if not f:   # 직전 목표가 숫자는 없어도 원문이 방향을 말하면 그 방향으로 센다(폭은 미확인)
            flow[{"up": "상향", "down": "하향", "same": "유지"}.get(dr, "직전 목표가 없음")] += 1
        else:
            flow["상향" if x["tp"] > f else "하향" if x["tp"] < f else "유지"] += 1
    dates = sorted(x["date"] for x in js["ANALYSTS"] if x.get("date"))
    tp_avg = round(sum(tps) / len(tps)) if tps else None
    cons, n = js["CONS"], sum(js["CONS"].values()) or 1

    def yoy_text(k):
        cur, prv = r[k]
        ch = c["chg"][k]
        return f"{cur - prv:+,}억 &nbsp;({'전년 대비 ' if ch.endswith('%') else ''}{ch})"

    def margin(label, pair):
        cls = "b" if pair[1] >= pair[0] else "b dn"      # 이익률이 내려가면 빨강
        return f"{label} &nbsp;{pair[0]:.1f}%<span class=\"arr\"> → </span><span class=\"{cls}\">{pair[1]:.1f}%</span>"

    d = px["date"]
    fy = lb["fy"]
    meta = {
        "name": corp["corp_name"], "base_date": dt.date.today().strftime("%Y.%m.%d"), "code": corp["stock_code"],
        "period_full": a.period_note or lb["note"] or f"{lb['prv_full']} vs {lb['cur_full']}",
        "basis": ("연결" if a.fs_div == "CFS" else "개별") + " 기준(전년은 이번 보고서에 다시 실린 수치)",
        "nav_label": f"{lb['nav']} 실적", "kpi_label": f"{lb['nav']} 실적 요약",
        "rev_val": f"{r['rev'][0]:,}", "rev_dir": "up" if r["rev"][0] >= r["rev"][1] else "down",
        "rev_yoy": yoy_text("rev"), "rev_sub": f"{lb['prv_s']} &nbsp;{r['rev'][1]:,}억",
        "op_val": f"{r['op'][0]:,}", "op_dir": "up" if r["op"][0] >= r["op"][1] else "down",
        "op_yoy": yoy_text("op"), "op_sub": margin("영업이익률", c["opm"]),
        "np_val": f"{r['np'][0]:,}", "np_dir": "up" if r["np"][0] >= r["np"][1] else "down",
        "np_yoy": yoy_text("np"), "np_sub": margin("순이익률", c["npm"]),
        "g_net": f"{delta[-1]['d']:+,}억", "g_up": f"{up:+,}억", "g_dn": f"{dn:+,}억" if dn else "0억",
        "q_prev_full": lb["prv_full"], "q_cur_full": lb["cur_full"], "q_prev_short": lb["prv_s"], "q_cur_short": lb["cur_s"],
        "mix_prev": f"{lb['prv_s']} 비중", "mix_cur": f"{lb['cur_s']} 비중",
        "coverage_note": (f"증권사 {len(tps)}곳 기준" + (f"(보고서 {dates[0]}~{dates[-1]})" if dates else "")
                          + " · 목표가 " + ", ".join(f"{k} {v}" for k, v in flow.items() if v)
                          + " · 전체 커버리지는 미확인" if tps else
                          "실적 발표 뒤 나온 증권사 보고서를 찾지 못했다 (커버리지 없음, 미확인)"),   # 실제 건수로 만든다
        "cons_buy_pct": f"{cons['buy'] / n * 100:.1f}%", "cons_buy": str(cons["buy"]),
        "cons_hold_pct": f"{cons['hold'] / n * 100:.1f}%", "cons_hold": str(cons["hold"]),
        "cons_sell_pct": f"{cons['sell'] / n * 100:.1f}%", "cons_sell": str(cons["sell"]),
        "tp_cur": f"{px['close']:,}원 ({int(d[4:6])}/{int(d[6:])} 종가)",
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
    missing = [v for v in ledger_names if not (parts / f"{v}.json").exists()]
    print(f"✅ {out}  (검증 장부 {len(web)}건" + (f", 아직 없는 출처 검증: {', '.join(missing)})" if missing else ")"))


Q_REPRT = {"1": "11013", "2": "11012", "3": "11014", "4": "11011", "FY": "11011"}


def pick_quarter(q: str, fm: int, latest_end: str | None = None, fiscal_year: int | None = None) -> tuple[int, str]:
    """사용자가 말한 분기 → (DART bsns_year, reprt_code). bsns_year는 그 기간 끝 월의 연도다.

    fiscal_year(회계연도 시작 연도, 라벨의 연도)를 주면 그 회계연도의 분기, 없으면 가장 최근 제출 보고서의
    기간 끝(latest_end, 'YYYY.MM')보다 늦지 않은 가장 최근 분기를 고른다. 결산월이 12월이 아니어도 맞는다.
    """
    reprt = Q_REPRT[q]
    pe = (fm + REPRT_OFFSET[reprt] - 1) % 12 + 1          # 그 분기의 기간 끝 월
    if fiscal_year is not None:
        return (fiscal_year if fm == 12 else fiscal_year + (1 if pe <= fm else 0)), reprt
    ly, lm = (int(x) for x in latest_end.split("."))
    return (ly if pe <= lm else ly - 1), reprt


def period(a) -> dict:
    """기간을 정한다. 기본은 가장 최근에 제출된 정기보고서, --quarter를 주면 그 분기. 결산월·코넥스는 상장사 목록에서."""
    corp = _corp(a.corp_code)
    fm = corp["fiscal_month"] or 12
    konex = corp["market"] == "코넥스"
    a.quarter, a.fiscal_year = getattr(a, "quarter", None), getattr(a, "fiscal_year", None)
    rep = DartClient().latest_periodic_report(a.corp_code, fiscal_month=fm, annual_only=konex)
    if not rep and not (a.quarter and a.fiscal_year):
        sys.exit("최근 460일 안에 제출된 정기보고서가 없다. 사용자에게 알리고 중단한다.")
    out = dict(rep or {})
    note = None
    if a.quarter and konex:
        note = "코넥스는 분기·반기보고서 제출 의무가 없어 연간(사업보고서)으로 만든다. 사용자에게 알린다."
    elif a.quarter:
        year, reprt = pick_quarter(a.quarter, fm, (rep or {}).get("period_end"), a.fiscal_year)
        pe = (fm + REPRT_OFFSET[reprt] - 1) % 12 + 1
        out = {"bsns_year": str(year), "reprt_code": reprt, "period_end": f"{year}.{pe:02d}",
               "label": ("FY" + fiscal_label(year, reprt, fm)[2:]) if a.quarter == "FY" else fiscal_label(year, reprt, fm),
               "latest_submitted": (rep or {}).get("label")}
    if konex and out.get("label", "").startswith("4Q"):
        out["label"] = "FY" + out["label"][2:]     # 코넥스는 연간 리포트다
    args = f"--year {out['bsns_year']} --reprt {out['reprt_code']}"
    if fm != 12:
        args += f" --fiscal-month {fm}"
    if konex or a.quarter == "FY":
        args += " --scope annual"
    res = {**out, "fiscal_month": fm, "konex": konex, "args": args}
    if note:
        res["note"] = note
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="DART 리포트 data.json 조립")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("period")
    pp.add_argument("--corp-code", required=True)
    pp.add_argument("--quarter", choices=list(Q_REPRT), help="사용자가 말한 분기(1~4, 연간은 FY). 생략하면 가장 최근 제출 보고서")
    pp.add_argument("--fiscal-year", type=int, help="사용자가 연도까지 말했을 때: 회계연도 시작 연도(라벨의 연도)")
    for name in ("facts", "build"):
        p = sub.add_parser(name)
        p.add_argument("--corp-code", required=True)
        p.add_argument("--year", required=True)
        p.add_argument("--reprt", required=True, choices=list(REPRT_Q))
        p.add_argument("--fs-div", default="CFS", choices=["CFS", "OFS"])
        p.add_argument("--scope", default="quarter", choices=["quarter", "annual"])
        p.add_argument("--np-basis", default="total", choices=["total", "parent"])
        p.add_argument("--fiscal-month", type=int, default=None, help="생략하면 상장사 목록의 결산월")
        p.add_argument("--parts", required=name == "build",
                       help="조각 폴더. facts에 주면 종가를 여기 고정해 build가 같은 값을 쓴다")
        if name == "build":
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
