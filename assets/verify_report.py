#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_report.py — HTML 빌드 전 숫자 검증 게이트

data.json의 모든 숫자를 세 층으로 다시 대조한다. 통과(PASS)해야만 build_report.py가 HTML을 만든다.

  A. 산술 정합   meta 텍스트 ↔ js 숫자, YoY·마진·합계·기여도·컨센·업사이드를 다시 계산해 대조
  B. 원천 대조   종목명·종목코드·corp_code가 한 회사인지 확인하고(상장 목록 + DART 기업개황),
                 DART API를 다시 호출해 매출·영업이익·순이익을, KRX 일봉으로 현재가(목표가 기준 종가)를 대조
                 (서술 속 숫자의 대조 풀도 여기서 만든다)
  C. 출처 장부   웹에서 온 숫자(증권사 목표가, 부문 매출, 뉴스, 컨센)는 audit.web에 검증 기록이 있어야 하고,
                 CHIPS·BULLS·BEARS·페르소나 평가 속 숫자는 A·B 풀에 있거나 audit.claims에 출처가 있어야 한다

회차 제한 (무한 반복 방지):
  - data.json 내용이 바뀐 상태로 실행할 때만 1회차가 소모된다. 같은 내용 재실행은 회차를 쓰지 않는다.
  - 기본 3회차. 3회차까지 FAIL이면 BLOCKED. 이후에는 사용자 판단 없이 진행할 수 없다.
  - PASS 뒤에 data.json을 고치면 회차가 새로 시작된다 (PASS는 풀린다).
  - 네트워크 장애로 원천 대조를 못 하면 INCOMPLETE. 회차를 쓰지 않는다.

사용법:
  python3 verify_report.py <data.json>              # 검증 (회차 소모)
  python3 verify_report.py <data.json> --status     # 현재 게이트 상태만 출력
  python3 verify_report.py <data.json> --reset      # 회차 초기화 (사용자 지시가 있을 때만)

종료 코드: 0 PASS · 1 FAIL(회차 남음) · 2 BLOCKED(회차 소진) · 3 INCOMPLETE(원천 접속 실패)

산출물 (data.json 옆):
  <stem>.verify.json   게이트 상태 (build_report.py가 읽는다)
  <stem>.verify.md     사람이 읽는 검증 리포트 (회차별 불일치 목록)
"""
from __future__ import annotations

import argparse, datetime, hashlib, html, json, math, os, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

MAX_ROUNDS = 3
TOL_EOK = 1.0          # 억원: 원→억 변환 시 내림/반올림 차이
EXIT = {"PASS": 0, "FAIL": 1, "BLOCKED": 2, "INCOMPLETE": 3}

REPRT_Q = {"11013": "1Q", "11012": "2Q", "11014": "3Q", "11011": "4Q"}


# ───────────────────────── 파싱 유틸 ─────────────────────────

def plain(s) -> str:
    """meta 값의 HTML 태그·엔티티 제거."""
    s = html.unescape(re.sub(r"<[^>]+>", " ", str(s)))
    return re.sub(r"\s+", " ", s).strip()


def to_num(s: str) -> float:
    return float(s.replace(",", "").replace("+", ""))


def nums(s) -> list[float]:
    return [to_num(m) for m in re.findall(r"[+-]?\d[\d,]*(?:\.\d+)?", plain(s))]


def eok_of(s) -> list[float]:
    """'1조2,303억' / '19,175억' / '+1,810억' → 억 단위 숫자 목록."""
    t = plain(s)
    out = []
    for m in re.finditer(r"([+-]?\d[\d,]*(?:\.\d+)?)\s*조\s*(\d[\d,]*)?\s*억?", t):
        out.append(to_num(m.group(1)) * 10000 + (to_num(m.group(2)) if m.group(2) else 0))
    t = re.sub(r"[+-]?\d[\d,]*(?:\.\d+)?\s*조\s*(\d[\d,]*)?\s*억?", " ", t)
    out += [to_num(m) for m in re.findall(r"([+-]?\d[\d,]*(?:\.\d+)?)\s*억", t)]
    return out


def decimals(token: str) -> int:
    return len(token.split(".")[1]) if "." in token else 0


def yoy(cur, prv):
    return None if not prv else (cur - prv) / abs(prv) * 100


REVIEW_ROLES = ("RED", "SILVER", "GOLD")


def review_problems(rv) -> list[str]:
    """전문가 평가(R.json → js.REVIEW) 형식 검사. 문제 목록을 돌려준다(없으면 빈 목록)."""
    if not isinstance(rv, dict):
        return ["전문가 평가(REVIEW)가 없다"]
    out = []
    if not str(rv.get("scene", "")).strip():
        out.append("scene(GOLD의 독자 장면)이 비었다")
    reviews = rv.get("reviews") or []
    if sorted(r.get("role", "") for r in reviews) != sorted(REVIEW_ROLES):
        out.append("RED·SILVER·GOLD가 하나씩 있어야 한다")
    for r in reviews:
        sc = r.get("score")
        if not isinstance(sc, (int, float)) or not 0 <= sc <= 10 or (sc * 2) != int(sc * 2):
            out.append(f"{r.get('role')} 점수는 0~10, 0.5 단위다: {sc}")
        for f in ("comment", "fix"):
            if not str(r.get(f, "")).strip():
                out.append(f"{r.get('role')}의 {f}가 비었다")
        if r.get("target") not in (None, "B", "C", "none"):
            out.append(f"{r.get('role')}의 target은 B·C·none 중 하나다: {r.get('target')}")
    return out


def turn_label(cur, prv):
    """적자가 낀 증감은 %가 아니라 업계 표기로 쓴다(-10억 → 9억을 '+190%'로 쓰면 오해를 부른다). 둘 다 흑자면 None."""
    if cur is None or prv is None or (prv >= 0 and cur >= 0):
        return None
    if prv < 0 <= cur:
        return "흑자 전환"
    if prv >= 0 > cur:
        return "적자 전환"
    return "적자 축소" if cur > prv else ("적자 확대" if cur < prv else "적자 지속")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ───────────────────────── 결과 수집 ─────────────────────────

class Report:
    def __init__(self):
        self.items = []

    def add(self, layer, ok, item, msg, hint=""):
        self.items.append({"layer": layer, "ok": bool(ok), "item": item, "msg": msg, "hint": hint})
        return ok

    def eq(self, layer, item, actual, expected, tol, hint=""):
        ok = actual is not None and expected is not None and abs(actual - expected) <= tol + 1e-9
        msg = f"표기 {fmt(actual)} / 계산 {fmt(expected)}"
        return self.add(layer, ok, item, msg, hint if not ok else "")

    @property
    def fails(self):
        return [i for i in self.items if not i["ok"]]


def fmt(v):
    if v is None:
        return "없음"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:,.2f}"
    return f"{int(v):,}"


def pct_tol(token_val: float, shown: str) -> float:
    """표기 자릿수 기준 반올림 허용폭. 66% → ±0.5, 66.1% → ±0.05."""
    return 0.5 * 10 ** (-decimals(shown)) + 0.001


# ───────────────────────── A. 산술 정합 ─────────────────────────

def first(lst):
    return lst[0] if lst else None


def check_arithmetic(d, R: Report, pool):
    m, js = d.get("meta", {}), d.get("js", {})
    L = "A 산술"

    # 매출·영업이익·순이익: 당기, 전년(역산), 증감, YoY, 방향
    rev_cur = first(nums(m.get("rev_val", "")))
    rev_prv = first(eok_of(m.get("rev_sub", "")))
    vals = {}
    for k, label in (("rev", "매출"), ("op", "영업이익"), ("np", "순이익")):
        cur = first(nums(m.get(f"{k}_val", "")))
        diff = first(eok_of(m.get(f"{k}_yoy", "")))
        pct_tok = re.findall(r"([+-]?\d[\d,]*(?:\.\d+)?)\s*%", plain(m.get(f"{k}_yoy", "")))
        prv = rev_prv if k == "rev" else (cur - diff if cur is not None and diff is not None else None)
        vals[k] = (cur, prv)
        if cur is None or prv is None:
            R.add(L, False, f"meta.{k}_val/{k}_yoy", "숫자를 읽을 수 없음", "형식: '20,985' / '+1,810억 (+9.4% YoY)'")
            continue
        if k == "rev":
            R.eq(L, "meta.rev_yoy 증감액", diff, cur - prv, TOL_EOK, "rev_val − rev_sub 전년치")
        exp = yoy(cur, prv)
        label = turn_label(cur, prv)
        if label:   # 적자가 끼면 %가 아니라 흑자 전환·적자 축소 같은 표기가 맞다
            R.add(L, label in plain(m.get(f"{k}_yoy", "")) and not pct_tok, f"meta.{k}_yoy 표기",
                  f"표기 '{plain(m.get(f'{k}_yoy', ''))}' / 기대 '{label}'", "조립 스크립트를 다시 돌린다")
        elif pct_tok and exp is not None:
            shown = pct_tok[0]
            rnd = (0.5 / abs(prv) + 0.5 * abs(cur) / prv ** 2) * 100   # 억 반올림 전파 오차 (정밀 대조는 B층)
            # 표기값과 '반올림하지 않은' 계산값을 비교한다. 계산값까지 반올림하면 반올림을 두 번 하게 되어
            # 경계값(-11.150%)에서 A층(억 단위)과 B층(원 단위)이 서로 다른 답을 요구한다
            R.eq(L, f"meta.{k}_yoy YoY%", to_num(shown), exp, pct_tol(0, shown) + rnd)
        elif exp is not None:
            R.add(L, False, f"meta.{k}_yoy", "YoY% 표기 없음")
        dir_ = m.get(f"{k}_dir")
        want = "up" if cur >= prv else "down"
        R.add(L, dir_ == want, f"meta.{k}_dir", f"표기 {dir_} / 계산 {want}")
        pool.add_eok(cur, prv, cur - prv)
        if exp is not None:
            pool.add_pct(exp)

    # OPM·NPM
    for k, key in (("op", "op_sub"), ("np", "np_sub")):
        shown = re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", plain(m.get(key, "")))   # 손실이면 음수 마진
        cur, prv = vals.get(k, (None, None))
        if len(shown) >= 2 and cur is not None and rev_cur and rev_prv:
            e_prv, e_cur = prv / rev_prv * 100, cur / rev_cur * 100
            # YoY와 같다: 반올림하지 않은 계산값과 비교하고 억 반올림 전파 오차를 더한다(정밀 대조는 B층)
            mt = lambda num, den: (0.5 / abs(den) + 0.5 * abs(num) / den ** 2) * 100
            R.eq(L, f"meta.{key} 전년 마진", to_num(shown[0]), e_prv, pct_tol(0, shown[0]) + mt(prv, rev_prv))
            R.eq(L, f"meta.{key} 당기 마진", to_num(shown[1]), e_cur, pct_tol(0, shown[1]) + mt(cur, rev_cur))
            pool.add_pct(e_prv, e_cur)
            pool.add_pp(e_cur - e_prv, to_num(shown[1]) - to_num(shown[0]))   # 원값 차이와 표기 마진끼리의 차이

    # 총매출 ↔ 부문 합계
    tot25, tot26 = js.get("TOT25"), js.get("TOT26")
    R.eq(L, "js.TOT25 = 전년 매출", tot25, rev_prv, TOL_EOK, "TOT25는 rev_sub의 전년 매출과 같아야 한다")
    R.eq(L, "js.TOT26 = 당기 매출", tot26, rev_cur, TOL_EOK, "TOT26은 rev_val과 같아야 한다")
    segs = js.get("SEGS", [])
    if segs:
        tol = max(TOL_EOK, math.ceil(len(segs) * 0.5))
        hint = "부문 합계가 총매출과 다르면 '조정' 행을 넣어 맞추고 est:true로 표시한다"
        R.eq(L, "SEGS q25 합계 = TOT25", sum(s["q25"] for s in segs), tot25, tol, hint)
        R.eq(L, "SEGS q26 합계 = TOT26", sum(s["q26"] for s in segs), tot26, tol, hint)
        cats = {}
        for s in segs:
            if s.get("est"):   # 추정·역산 값은 서술 근거가 되지 못한다
                continue
            pool.add_eok(s["q25"], s["q26"], s["q26"] - s["q25"])
            pool.add_lab("매출", s["q25"], s["q26"], s["q26"] - s["q25"])
            if s["q25"]:
                pool.add_pct(yoy(s["q26"], s["q25"]))
                pool.add_plab("매출", yoy(s["q26"], s["q25"]))
            if tot25 and tot26:
                pool.add_pct(s["q25"] / tot25 * 100, s["q26"] / tot26 * 100)
                pool.add_pp(s["q26"] / tot26 * 100 - s["q25"] / tot25 * 100)
                pool.add_plab("매출", s["q25"] / tot25 * 100, s["q26"] / tot26 * 100, s["q26"] / tot26 * 100 - s["q25"] / tot25 * 100)
            c = cats.setdefault(s.get("cat", ""), [0, 0])
            c[0] += s["q25"]; c[1] += s["q26"]
        for a, b in cats.values():
            pool.add_eok(a, b, b - a)
            pool.add_lab("매출", a, b, b - a)
            if a:
                pool.add_pct(yoy(b, a))

    # 성장 기여도
    delta = js.get("DELTA", [])
    body = [x for x in delta if not x.get("tot")]
    tot = next((x for x in delta if x.get("tot")), None)
    by_name = {s["name"]: s for s in segs}
    for x in body:
        s = by_name.get(x["name"])
        if s:
            R.eq(L, f"DELTA '{x['name']}'", x["d"], s["q26"] - s["q25"], TOL_EOK, "SEGS q26 − q25")
        pool.add_eok(x["d"])
    if tot is None:
        R.add(L, False, "DELTA 합계", "{name:'합계', tot:true} 행이 없음")
    else:
        R.eq(L, "DELTA 항목 합 = 합계", sum(x["d"] for x in body), tot["d"], TOL_EOK)
        if tot25 is not None and tot26 is not None:
            R.eq(L, "DELTA 합계 = TOT26−TOT25", tot["d"], tot26 - tot25, TOL_EOK)
        R.eq(L, "meta.g_net", first(eok_of(m.get("g_net", ""))), tot["d"], TOL_EOK)
    R.eq(L, "meta.g_up (증가 합)", first(eok_of(m.get("g_up", ""))), sum(x["d"] for x in body if x["d"] > 0), TOL_EOK)
    R.eq(L, "meta.g_dn (감소 합)", first(eok_of(m.get("g_dn", ""))), sum(x["d"] for x in body if x["d"] < 0), TOL_EOK)

    # 컨센서스
    cons = js.get("CONS", {})
    n = sum(cons.get(k, 0) for k in ("buy", "hold", "sell"))
    for k in ("buy", "hold", "sell"):
        R.eq(L, f"meta.cons_{k}", first(nums(m.get(f"cons_{k}", ""))), cons.get(k), 0)
        shown = re.findall(r"(\d+(?:\.\d+)?)", plain(m.get(f"cons_{k}_pct", "")))
        if n and shown:
            R.eq(L, f"meta.cons_{k}_pct", to_num(shown[0]), round(cons.get(k, 0) / n * 100, decimals(shown[0])),
                 pct_tol(0, shown[0]))
            pool.add_pct(cons.get(k, 0) / n * 100)
    an = js.get("ANALYSTS", [])
    for r_, k in (("Buy", "buy"), ("Hold", "hold"), ("Sell", "sell")):
        listed = sum(1 for a in an if a.get("r") == r_)
        R.add(L, cons.get(k, 0) >= listed, f"CONS.{k} ≥ 표의 {r_} 수",
              f"CONS {cons.get(k, 0)} / 표 {listed}", "집계가 표보다 작을 수 없다")

    # 주가·목표가
    curr = js.get("CURR")
    R.eq(L, "meta.tp_cur = js.CURR", first(nums(m.get("tp_cur", ""))), curr, 0)
    tp = {k: first(nums(m.get(f"tp_{k}", ""))) for k in ("low", "avg", "high")}
    if None not in tp.values():
        R.add(L, tp["low"] <= tp["avg"] <= tp["high"], "meta.tp_low ≤ avg ≤ high",
              f"{fmt(tp['low'])} / {fmt(tp['avg'])} / {fmt(tp['high'])}")
    if curr and tp["avg"]:
        shown = re.findall(r"[+-]?\d+(?:\.\d+)?", plain(m.get("tp_upside", "")))
        if shown:
            R.eq(L, "meta.tp_upside", to_num(shown[0]), round((tp["avg"] - curr) / curr * 100, decimals(shown[0])),
                 pct_tol(0, shown[0]), "(tp_avg − CURR) / CURR")
        pool.add_pct((tp["avg"] - curr) / curr * 100)
    tps = [a["tp"] for a in an if a.get("tp")]
    for a in an:
        pool.add_won(a.get("tp"), a.get("from"))
        if curr and a.get("tp"):
            pool.add_pct((a["tp"] - curr) / curr * 100)
        if a.get("tp") and a.get("from"):
            pool.add_pct(yoy(a["tp"], a["from"]))
    pool.add_won(curr, *[v for v in tp.values() if v])
    return tps, tp


# ───────────────────────── B. 원천 대조 ─────────────────────────

ACC = {
    "rev": (["ifrs-full_Revenue"], ["매출액", "영업수익", "수익(매출액)", "매출"]),
    "op": (["dart_OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities"], ["영업이익", "영업이익(손실)"]),
    "np_total": (["ifrs-full_ProfitLoss"], ["당기순이익", "당기순이익(손실)", "분기순이익", "반기순이익"]),
    "np_parent": (["ifrs-full_ProfitLossAttributableToOwnersOfParent"], ["지배기업 소유주지분", "지배기업의 소유주"]),
}


def _amt(v):
    try:
        return int(str(v).replace(",", "")) if v not in (None, "", "-") else None
    except ValueError:
        return None


_NUM_PREFIX = re.compile(r"^\s*(?:\(\d+\)|(?:[IVXⅠ-Ⅻ]+|\d+|[가나다라마바사아자차카타파하])\s*[.)])\s*")


def acc_name(nm):
    """'III. 영업이익', '1. 매출액', 'Ⅳ.당기순이익' → 번호를 뗀 계정명 (증권사·보험사 보고서가 번호를 붙인다)."""
    return _NUM_PREFIX.sub("", nm or "").strip()


def _find(items, key):
    ids, names = ACC[key]
    pl = [it for it in items if it.get("sj_div") in ("IS", "CIS")]
    for pred in (lambda it: it.get("account_id") in ids, lambda it: acc_name(it.get("account_nm")) in names):
        hit = [it for it in pl if pred(it)]
        if hit:
            hit.sort(key=lambda it: it.get("sj_div") != "IS")
            return hit[0]
    return None


def _eok(v):
    return None if v is None else v / 1e8


def _load_key():
    from corp_registry import find_api_key   # 키를 찾는 규칙은 한 곳에만 둔다
    return find_api_key()


def prev_quarter_src(src):
    """직전 분기 보고서의 (bsns_year, reprt_code). 연간이면 None. assemble_report와 같은 규칙."""
    if src.get("scope") == "annual":
        return None
    fm = int(src.get("fiscal_month") or 12)
    em = (fm + {"11013": 3, "11012": 6, "11014": 9, "11011": 12}[str(src["reprt_code"])] - 1) % 12 + 1
    ey = int(src["year"])
    py = ey if em > 3 else ey - 1
    return str(py), {"11013": "11011", "11012": "11013", "11014": "11012", "11011": "11014"}[str(src["reprt_code"])]


def q3_year(year, fiscal_month=12) -> str:
    """사업보고서(bsns_year=year)와 같은 회계연도의 3분기보고서 bsns_year.

    DART bsns_year는 보고서 기간 끝 월의 연도다. 3Q 끝 월 = 결산월 − 3. 0 이하면 전년이다.
    12월 결산 2025 → 2025(9월), 3월 결산 2026 → 2025(12월), 6월 결산 2026 → 2026(3월).
    """
    fm = int(fiscal_month or 12)
    return str(int(year) - (1 if fm - 3 <= 0 else 0))


def fetch_dart(src):
    """(cur, prv) 억원 dict와 DART 전 계정 리스트를 반환. 실패 시 예외."""
    from dart_client import DartClient
    c = DartClient(api_key=_load_key(), timeout=20)
    year, rc, fs = str(src["year"]), str(src["reprt_code"]), src.get("fs_div", "CFS")
    r = c.get_financial_statements(src["corp_code"], year, rc, fs)
    if r.get("status") != "000":
        raise LookupError(f"DART status={r.get('status')} {r.get('message')}")
    items = r["list"]

    def pair(it, cur_f="thstrm_amount"):
        prv = _amt(it.get("frmtrm_q_amount"))
        if prv is None:
            prv = _amt(it.get("frmtrm_amount"))
        return _amt(it.get(cur_f)), prv

    vals = {}
    q4 = rc == "11011" and src.get("scope", "quarter") == "quarter"
    q3 = None
    if q4:   # 4Q 단독 = 연간 − 3Q 누적. 3Q의 사업연도는 3Q 기간 끝 월의 연도다 (3월 결산이면 전년 12월)
        r3 = c.get_financial_statements(src["corp_code"], q3_year(year, src.get("fiscal_month", 12)), "11014", fs)
        if r3.get("status") != "000":
            raise LookupError(f"4Q 역산용 3Q 보고서 없음: status={r3.get('status')}")
        q3 = r3["list"]
    for k in ACC:
        it = _find(items, k)
        if not it:
            continue
        cur, prv = _amt(it.get("thstrm_amount")), _amt(it.get("frmtrm_amount"))
        if q4:
            it3 = _find(q3, k)
            if not it3:
                continue
            c3, p3 = _amt(it3.get("thstrm_add_amount")), _amt(it3.get("frmtrm_add_amount"))
            cur = None if None in (cur, c3) else cur - c3
            prv = None if None in (prv, p3) else prv - p3
        elif rc != "11011":
            cur, prv = pair(it)
        vals[k] = (_eok(cur), _eok(prv))
    try:
        div = c.get_dividend(src["corp_code"], year, rc).get("list", [])
    except Exception:
        div = []
    try:   # 작년 같은 보고서: 전년 동기말 재무상태표와 처음 발표한 전년 손익 (재작성 전 숫자. 기사가 이 기준으로 쓴다)
        rp = c.get_financial_statements(src["corp_code"], str(int(year) - 1), rc, fs)
        prev = [it for it in rp.get("list", []) if it.get("sj_div") in ("BS", "IS", "CIS")]
    except Exception:
        prev = []
    return vals, items, div, prev


def fetch_provisional_text(rcept_no):
    import io, zipfile
    from http_compat import requests
    r = requests.get("https://opendart.fss.or.kr/api/document.xml",
                     params={"crtfc_key": _load_key(), "rcept_no": rcept_no}, timeout=20)
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
    except zipfile.BadZipFile:   # 접수번호·키 오류면 DART가 zip 대신 오류 JSON/XML을 준다
        raise LookupError(f"공시 원문을 받지 못했다(접수번호 {rcept_no}): {r.text[:160]}") from None
    text = re.sub(r"<[^>]+>", " ", z.read(z.namelist()[0]).decode("utf-8", "ignore"))
    return re.sub(r"\s+", " ", text)


def check_dart(d, R: Report, pool):
    L = "B 원천(DART)"
    m = d.get("meta", {})
    src = (d.get("audit") or {}).get("src") or {}
    need = [k for k in ("corp_code", "year", "reprt_code") if not src.get(k)]
    if need:
        R.add(L, False, "audit.src", f"원천 대조 정보 없음: {need}",
              '"audit":{"src":{"corp_code":"00258801","year":"2026","reprt_code":"11012","fs_div":"CFS"}}')
        return

    # 분기 라벨 ↔ 보고서 코드. 비12월 결산은 회계연도 시작 연도로 라벨을 단다 (dart_client.fiscal_label_year)
    from dart_client import fiscal_label_year
    q = REPRT_Q.get(str(src["reprt_code"]))
    yy = fiscal_label_year(src["year"], str(src["reprt_code"]), src.get("fiscal_month", 12)) % 100
    want_cur, want_prv = f"{q}{yy:02d}", f"{q}{yy - 1:02d}"
    if src.get("scope") == "annual":
        want_cur, want_prv = f"FY{yy:02d}", f"FY{yy - 1:02d}"
    R.add(L, m.get("q_cur_short") == want_cur and m.get("q_prev_short") == want_prv, "meta.q_*_short ↔ 보고서",
          f"표기 {m.get('q_prev_short')}→{m.get('q_cur_short')} / 보고서 {want_prv}→{want_cur}")

    shown = {
        "rev": (first(nums(m.get("rev_val", ""))), first(eok_of(m.get("rev_sub", "")))),
    }
    for k in ("op", "np"):
        cur, diff = first(nums(m.get(f"{k}_val", ""))), first(eok_of(m.get(f"{k}_yoy", "")))
        shown[k] = (cur, None if None in (cur, diff) else cur - diff)

    if src.get("kind") == "provisional":
        try:
            text = fetch_provisional_text(src["rcept_no"])
        except LookupError as e:
            R.add(L, False, "잠정실적 원문", str(e), "audit.src.rcept_no가 잠정실적 공시의 접수번호(14자리)인지 확인한다")
            return
        found = [to_num(x) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]
        for k, label in (("rev", "매출"), ("op", "영업이익"), ("np", "순이익")):
            v = shown[k][0]
            hit = v is not None and any(abs(n - v) <= 1 or abs(n / 100 - v) <= 1 or abs(n / 1e8 - v) <= 1 for n in found)
            R.add(L, hit, f"잠정실적 {label} 당기", f"표기 {fmt(v)}억이 공시 원문({src['rcept_no']})에서 " +
                  ("확인됨" if hit else "발견되지 않음"))
            pool.add_eok(v)
        return

    try:
        vals, items, div, prev = fetch_dart(src)
    except LookupError as e:
        R.add(L, False, "DART 재조회", str(e), "audit.src의 corp_code·year·reprt_code·fs_div를 확인한다")
        return
    cur = sorted({it.get("currency") for it in items if it.get("currency")} - {"KRW"})
    if cur:
        R.add(L, False, "DART 통화", f"재무제표 통화가 {', '.join(cur)}다. 억원 기준 리포트와 맞지 않는다",
              "외화로 공시하는 회사는 이 리포트로 만들 수 없다")
        return
    np_key = "np_parent" if src.get("np_basis") == "parent" else "np_total"
    for k, dk, label in (("rev", "rev", "매출"), ("op", "op", "영업이익"), ("np", np_key, "순이익")):
        if dk not in vals:
            R.add(L, False, f"DART {label}", "DART 응답에서 계정을 찾지 못함")
            continue
        (sc, sp), (dc, dp) = shown[k], vals[dk]
        ok_c = R.eq(L, f"DART {label} 당기", sc, dc, TOL_EOK)
        ok_p = R.eq(L, f"DART {label} 전년동기", sp, dp, TOL_EOK,
                    "전년 비교는 이번 보고서의 frmtrm(재작성치)을 쓴다. 작년 보고서 숫자를 쓰지 마라")
        yt = re.findall(r"([+-]?\d[\d,]*(?:\.\d+)?)\s*%", plain(m.get(f"{k}_yoy", "")))
        if yt and dc is not None and dp:
            R.eq(L, f"DART {label} YoY%", to_num(yt[0]), yoy(dc, dp), pct_tol(0, yt[0]),
                 "YoY는 원 단위 원값으로 계산한다")
        if k == "np" and not (ok_c and ok_p):
            alt = "np_total" if np_key == "np_parent" else "np_parent"
            if alt in vals and sc is not None and abs(sc - vals[alt][0]) <= TOL_EOK:
                R.items[-1]["hint"] = (f"표기값이 {'지배주주' if alt == 'np_parent' else '연결 총'}순이익과 일치한다. "
                                       f"의도라면 assemble_report.py build에 --np-basis {'parent' if alt == 'np_parent' else 'total'}를 붙여 다시 조립한다")

    # facts가 찍는 원값 기준 YoY·증감·마진·pp. 4Q 단독(연간 − 3Q 누적)은 items에 없는 값이라 따로 넣는다
    rc, rp = vals.get("rev", (None, None))
    for dk, (c, p) in vals.items():
        if c is None or p is None:
            continue
        pool.add_eok(c, p, c - p)
        if p:
            pool.add_pct(yoy(c, p))
        if dk != "rev" and rc and rp:
            pool.add_pct(c / rc * 100, p / rp * 100)
            pool.add_pp(c / rc * 100 - p / rp * 100, float(f"{c / rc * 100:.1f}") - float(f"{p / rp * 100:.1f}"))

    # 서술 대조 풀: 손익 전 계정(분기·누적, 당기·전년)과 그 YoY·매출 대비 비율, 재무상태표
    rev = vals.get("rev", (None, None))
    cols = ("thstrm_amount", "frmtrm_q_amount", "thstrm_add_amount", "frmtrm_add_amount", "frmtrm_amount")
    rev_it = _find(items, "rev")
    for it in items:
        a = {c: _eok(_amt(it.get(c))) for c in cols}
        pool.add_eok(*[v for v in a.values() if v is not None])
        if it.get("sj_div") in ("IS", "CIS"):
            for cur_c, prv_c in (("thstrm_amount", "frmtrm_q_amount"), ("thstrm_add_amount", "frmtrm_add_amount"),
                                 ("thstrm_amount", "frmtrm_amount")):
                if a[cur_c] is not None and a[prv_c]:
                    pool.add_pct(yoy(a[cur_c], a[prv_c]))
                    pool.add_x(a[cur_c] / a[prv_c])
                    pool.add_eok(a[cur_c] - a[prv_c])
            if rev_it:
                for ccol in cols:
                    rv = _eok(_amt(rev_it.get(ccol)))
                    if rv and a[ccol] is not None:
                        pool.add_pct(a[ccol] / rv * 100)
    for it in items:   # 계정 라벨별 값과 (당기 − 비교) 증감, 증가율
        labs = labels_of(it.get("account_nm", "").strip(), it.get("account_id") or "")
        a = {c: _eok(_amt(it.get(c))) for c in cols}
        for lab in labs:
            pool.add_lab(lab, *a.values())
            for cur_c, prv_c in (("thstrm_amount", "frmtrm_q_amount"), ("thstrm_amount", "frmtrm_amount"),
                                 ("thstrm_add_amount", "frmtrm_add_amount")):
                if a[cur_c] is not None and a[prv_c] is not None:
                    pool.add_lab(lab, a[cur_c] - a[prv_c])
                    if a[prv_c] and lab in PCT_LABELS:
                        pool.add_plab(lab, yoy(a[cur_c], a[prv_c]))
    for it in prev:    # 전년 동기말 재무상태, 처음 발표한 전년 손익
        for lab in labels_of(it.get("account_nm", "").strip(), it.get("account_id") or ""):
            pool.add_lab(lab, _eok(_amt(it.get("thstrm_amount"))))
    for it in items:
        a = {c: _eok(_amt(it.get(c))) for c in cols}
        for prv_c in ("frmtrm_q_amount", "frmtrm_amount"):
            if a["thstrm_amount"] is not None and a[prv_c] is not None:
                pool.pairs.append((a[prv_c], a["thstrm_amount"]))
    rv_c, rv_p = vals.get("rev", (None, None))
    for k, lab in (("rev", "매출"), ("op", "영업이익"), ("np_total", "순이익"), ("np_parent", "순이익")):
        c_, p_ = vals.get(k, (None, None))
        if c_ is not None and p_ is not None:
            pool.add_lab(lab, c_, p_, c_ - p_)
            if p_:
                pool.add_plab(lab, yoy(c_, p_))
            pool.pairs.append((p_, c_))
            if k != "rev" and rv_c and rv_p:   # 이익률과 그 변화폭
                pool.pairs.append((p_ / rv_p * 100, c_ / rv_c * 100))
                pool.add_plab(lab, c_ / rv_c * 100, p_ / rv_p * 100, c_ / rv_c * 100 - p_ / rv_p * 100,
                              float(f"{c_ / rv_c * 100:.1f}") - float(f"{p_ / rv_p * 100:.1f}"))
    by_id = {it.get("account_id"): it for it in items if it.get("sj_div") in ("BS", "IS", "CIS")}
    pool.add_eok(*[_eok(_amt(it.get("thstrm_amount"))) for it in prev])   # 전년 동기말 BS, 처음 발표한 전년 손익
    # 직전 분기 대비 (assemble_report.prev_quarter와 같은 규칙)
    pq = prev_quarter_src(src)
    if pq:
        try:
            pv, *_ = fetch_dart({**src, "year": pq[0], "reprt_code": pq[1], "scope": "quarter"})
            for k in ("rev", "op", "np_total", "np_parent"):
                c_, p_ = vals.get(k, (None,))[0], (pv.get(k) or (None,))[0]
                if p_ is not None:
                    pool.add_eok(p_)
                    pool.add_lab({"rev": "매출", "op": "영업이익"}.get(k, "순이익"), p_)
                    if c_ is not None:
                        pool.add_eok(c_ - p_)
                        if p_:
                            pool.qoq.append(yoy(c_, p_))
                            pool.add_plab({"rev": "매출", "op": "영업이익"}.get(k, "순이익"), yoy(c_, p_))
        except Exception:
            pass
    # 차입·상환 합계(재무활동 하위 줄), 중단영업 지배주주 귀속 비율, 실효세율
    cf = sorted((it for it in items if it.get("sj_div") == "CF"), key=lambda it: int(it.get("ord") or 0))
    fin, borrow, repay = False, 0, 0
    for it in cf:
        aid = it.get("account_id") or ""
        if aid.startswith("ifrs-full_CashFlowsFromUsedIn"):
            fin = aid.endswith("FinancingActivities")
            continue
        nm = it.get("account_nm", "")
        if fin and "차입" in nm:
            v_ = _amt(it.get("thstrm_amount")) or 0
            if "상환" in nm:
                repay += v_
            else:
                borrow += v_
    pool.add_eok(_eok(borrow), _eok(repay))
    ids_ = {it.get("account_id"): it for it in items if it.get("sj_div") in ("IS", "CIS")}
    for num_id, den_id, lab in (("ifrs-full_IncomeFromDiscontinuedOperationsAttributableToOwnersOfParent",
                                 "ifrs-full_ProfitLossFromDiscontinuedOperations", "중단영업"),
                                ("ifrs-full_IncomeTaxExpenseContinuingOperations", "ifrs-full_ProfitLossBeforeTax", "법인세")):
        a_it, b_it = ids_.get(num_id), ids_.get(den_id)
        if a_it and b_it:
            for ccol in cols:
                a_, b_ = _amt(a_it.get(ccol)), _amt(b_it.get(ccol))
                if a_ is not None and b_:
                    pool.add_pct(a_ / b_ * 100)
                    if lab:
                        pool.add_plab(lab, a_ / b_ * 100)
    # 시가총액·PBR 재료 (종가는 check_price가 안다)
    eq_it = next((it for it in items if it.get("account_id") == "ifrs-full_EquityAttributableToOwnersOfParent"), None)
    pool.parent_eq = _amt(eq_it.get("thstrm_amount")) if eq_it else None
    try:
        from dart_client import DartClient
        r = DartClient(api_key=_load_key(), timeout=15)._get("stockTotqySttus.json", corp_code=src["corp_code"],
                                                             bsns_year=str(src["year"]), reprt_code=str(src["reprt_code"]))
        row = next(x for x in r.get("list", []) if x.get("se") == "보통주")
        pool.shares = _amt(row.get("istc_totqy"))
    except Exception:
        pool.shares = None
    same_basis = str(src.get("reprt_code")) != "11011" or src.get("scope") == "annual"   # 4Q 단독은 작년 연간과 못 견준다
    for k in ("rev", "op", "np_total", "np_parent") if same_basis else ():   # 처음 발표한 전년 대비 증가율 (기사 제목의 숫자)
        it0, cur = _find(prev, k), vals.get(k, (None, None))[0]
        p0 = _eok(_amt(it0.get("thstrm_amount"))) if it0 else None
        if cur is not None and p0:
            pool.orig.append(yoy(cur, p0))
    for it in items:   # EPS는 원 단위 그대로
        if "EarningsLossPerShare" in (it.get("account_id") or ""):
            pool.add_won(*[_amt(it.get(c)) for c in cols])
    op_it, pbt_it = _find(items, "op"), by_id.get("ifrs-full_ProfitLossBeforeTax")
    if op_it and pbt_it:   # 영업외손익 = 영업이익 − 세전이익
        for ccol in cols:
            a, b = _amt(op_it.get(ccol)), _amt(pbt_it.get(ccol))
            if a is not None and b is not None:
                pool.add_eok(_eok(a - b))
    liab, eq = by_id.get("ifrs-full_Liabilities"), by_id.get("ifrs-full_Equity")
    if liab and eq:   # 부채비율
        for ccol in ("thstrm_amount", "frmtrm_amount"):
            a, b = _amt(liab.get(ccol)), _amt(eq.get(ccol))
            if a is not None and b:
                pool.add_pct(a / b * 100)
    for row in div:   # 배당: 백만원·%·원
        se = row.get("se", "")
        for ccol in ("thstrm", "frmtrm", "lwfr"):
            v = row.get(ccol)
            try:
                v = float(str(v).replace(",", ""))
            except ValueError:
                continue
            if "백만원" in se:
                pool.add_eok(v / 100)
            elif "%" in se:
                pool.add_pct(v)
            elif "원" in se:
                pool.add_won(v)
    tax = by_id.get("ifrs-full_IncomeTaxExpenseContinuingOperations")
    pbt = pbt_it
    if tax and pbt:   # 유효세율
        for ccol in cols:
            t, b = _amt(tax.get(ccol)), _amt(pbt.get(ccol))
            if t is not None and b:
                pool.add_pct(t / b * 100)
    if rev_it:   # 누적 마진 변화폭
        for k in ("op", "np_total"):
            it = _find(items, k)
            if it:
                r = {c: _amt(rev_it.get(c)) for c in cols}
                v = {c: _amt(it.get(c)) for c in cols}
                for cc, pc in (("thstrm_add_amount", "frmtrm_add_amount"), ("thstrm_amount", "frmtrm_q_amount")):
                    if r[cc] and r[pc] and v[cc] is not None and v[pc] is not None:
                        pool.add_pp(v[cc] / r[cc] * 100 - v[pc] / r[pc] * 100)


def check_identity(d, R: Report):
    """리포트가 정말 그 회사인가: meta.name ↔ meta.code ↔ audit.src.corp_code가 한 회사를 가리켜야 한다.

    오프라인은 corp_registry(DART ∩ KRX 상장 목록), 온라인은 DART company.json으로 본다.
    "현대차"를 부분일치로 찾아 현대차증권 숫자를 쓰는 식의 오인을 여기서 막는다.
    """
    L = "B 식별"
    import corp_registry
    m = d.get("meta", {})
    src = (d.get("audit") or {}).get("src") or {}
    corp_code, code, name = str(src.get("corp_code") or ""), str(m.get("code") or ""), plain(m.get("name", ""))
    if not (corp_code and code and name):
        R.add(L, False, "식별 정보", f"meta.name={name!r} meta.code={code!r} audit.src.corp_code={corp_code!r}",
              "셋 다 채운다. corp_registry.py <회사명>의 corp.corp_name·stock_code·corp_code를 그대로 쓴다")
        return
    reg = corp_registry.load()
    row = reg.by_corp.get(corp_code)
    gone = next((x for x in reg.delisted if x["corp_code"] == corp_code), None)
    if gone and not row:   # DART는 폐지 뒤에도 종목코드를 남긴다. 기업개황 대조만으로는 못 잡는다
        R.add(L, False, "corp_code 상장 여부", f"{corp_code}는 {gone['corp_name']}({gone['stock_code']}), "
              "현재 KRX 상장 종목이 아니다", "corp_registry.py로 지금 상장된 회사를 다시 찾는다")
        return
    if row:
        R.add(L, row["stock_code"] == code, "corp_code ↔ 종목코드 (상장 목록)",
              f"{corp_code}는 {row['corp_name']}({row['stock_code']}) / 표기 {code}",
              "audit.src.corp_code와 meta.code 중 하나가 다른 회사다. corp_registry.py로 다시 찾는다")
        res = corp_registry.resolve(name, reg)
        # 정식명이 다른 회사의 약칭이기도 한 경우(모비스)는 ambiguous로 나온다. 후보 안에 있으면 같은 회사다
        same = ((res["status"] == "ok" and res["corp"]["corp_code"] == corp_code)
                or (res["status"] == "ambiguous" and corp_code in {c["corp_code"] for c in res["candidates"]}
                    and corp_registry.norm(name) == corp_registry.norm(row["corp_name"])))
        R.add(L, same, "meta.name ↔ corp_code",
              f"'{name}' → " + (f"{res['corp']['corp_name']}({res['corp']['corp_code']})" if res["corp"] else res["status"])
              + f" / audit {row['corp_name']}({corp_code})",
              f"meta.name을 '{row['corp_name']}'(정식명)으로 쓴다")
    from dart_client import DartClient
    info = DartClient(api_key=_load_key(), timeout=20).company(corp_code)
    if info.get("status") in ("020", "800"):   # 한도 초과·점검: 불일치가 아니라 확인 불가 → INCOMPLETE
        raise ConnectionError(f"DART 기업개황 status={info.get('status')} {info.get('message')}")
    if info.get("status") != "000":
        R.add(L, False, "DART 기업개황", f"status={info.get('status')} {info.get('message')}",
              "audit.src.corp_code가 8자리 DART 고유번호인지 확인한다")
        return
    R.add(L, (info.get("stock_code") or "").strip() == code, "corp_code ↔ 종목코드 (DART 기업개황)",
          f"DART {info.get('corp_name')}({info.get('stock_code')}) / 표기 {code}")
    R.add(L, info.get("corp_cls") in ("Y", "K", "N"), "상장 구분 (DART 기업개황)",
          f"corp_cls={info.get('corp_cls')!r} (Y 코스피 · K 코스닥 · N 코넥스, E는 비상장·폐지)",
          "상장 종목이 아니다. corp_registry.py로 다시 찾는다")
    if not row:   # 목록에 아직 없는 신규 상장사: 이름은 기업개황과 직접 대조한다
        dart_names = {corp_registry.norm(info.get("corp_name", "")), corp_registry.norm(info.get("stock_name", ""))}
        R.add(L, corp_registry.norm(name) in dart_names, "meta.name ↔ DART 기업개황",
              f"'{name}' / DART {info.get('stock_name')} · {info.get('corp_name')}",
              f"meta.name을 '{info.get('stock_name')}'로 쓴다")


def check_price(d, R: Report, pool):
    L = "B 원천(KRX)"
    m, js = d.get("meta", {}), d.get("js", {})
    code = m.get("code")
    mt = re.search(r"\((\d{1,2})/(\d{1,2})\s*종가\)", plain(m.get("tp_cur", "")))
    if not mt:
        R.add(L, False, "meta.tp_cur", "'(M/D 종가)' 표기를 찾지 못함", "형식: '32,475원 (10/8 종가)'")
        return
    from price import _naver_daily, _settled
    rows = _settled(_naver_daily(code, days=760))   # 장중 오늘 행은 종가가 아니다
    if not rows:
        raise ConnectionError("KRX 일봉을 받지 못함")
    mm, dd = int(mt.group(1)), int(mt.group(2))
    idx = max((i for i, r in enumerate(rows) if int(r[0][4:6]) == mm and int(r[0][6:]) == dd), default=None)
    if idx is None:
        R.add(L, False, "meta.tp_cur 날짜", f"{mm}/{dd} 거래일 데이터 없음")
        return
    date, close = rows[idx][0], rows[idx][1]
    R.eq(L, f"종가 {date} = js.CURR", js.get("CURR"), close, 0, "price.py 결과를 그대로 쓴다")
    if idx > 0:
        pool.add_pct((close - rows[idx - 1][1]) / rows[idx - 1][1] * 100)
    start = (datetime.datetime.strptime(date, "%Y%m%d") - datetime.timedelta(days=365)).strftime("%Y%m%d")
    win = [r for r in rows[: idx + 1] if r[0] >= start]
    lo, hi = min(r[3] for r in win), max(r[2] for r in win)
    pool.add_won(close, lo, hi)
    shares = getattr(pool, "shares", None)
    if shares:   # 시가총액 = 보통주 발행주식총수 × 종가, PBR = 시가총액 ÷ 지배주주자본
        cap = shares * close
        pool.add_eok(cap / 1e8)
        pool.add_won(shares)
        if getattr(pool, "parent_eq", None):
            pool.add_x(cap / pool.parent_eq)
    if close:
        for v in (lo, hi):
            pool.add_pct((close - v) / v * 100, (v - close) / close * 100)


# ───────────────────────── C. 출처 장부 ─────────────────────────

class Pool:
    """서술 속 숫자를 대조할 사실 풀. 부호 있는 값을 그대로 둔다(방향이 뒤집힌 서술을 잡는다)."""

    def __init__(self):
        self.eok, self.pct, self.pp, self.won, self.x = [], [], [], [], []
        self.lab = {}    # 계정 라벨 → 억원 값(부호 있음). 라벨 바로 뒤 금액은 그 계정 값이어야 한다
        self.plab = {}   # 계정 라벨 → %·%p 값(증가율·이익률). 매출·영업이익·순이익만
        self.ext = {"eok": [], "pct": [], "pp": [], "won": [], "x": [], "man": []}   # 확인된 기사·증권사 note의 숫자(출처를 밝혀야 쓴다)
        self.orig = []   # 처음 발표한 전년 대비 증가율('처음 발표'·'기사'를 밝혀야 쓴다)
        self.qoq = []    # 직전 분기 대비 증가율('전년'이라 쓴 문장에서는 안 된다)
        self.pairs = []  # (비교, 당기) 쌍. 'A에서 B로'가 거꾸로 쓰였는지 본다

    def _put(self, lst, vals):
        lst.extend(float(v) for v in vals if v is not None)

    def add_lab(self, label, *v): self._put(self.lab.setdefault(label, []), v)
    def add_plab(self, label, *v): self._put(self.plab.setdefault(label, []), v)
    def add_eok(self, *v): self._put(self.eok, v)
    def add_pct(self, *v): self._put(self.pct, v)
    def add_pp(self, *v): self._put(self.pp, v)
    def add_won(self, *v): self._put(self.won, v)
    def add_x(self, *v): self._put(self.x, v)

    @staticmethod
    def _match(vals, val, t, sign):
        if sign:   # 부호(또는 늘었다·줄었다)를 말했으면 부호까지 맞아야 한다
            return any(abs(x - sign * abs(val)) <= t for x in vals)
        return any(abs(abs(x) - abs(val)) <= t for x in vals)

    def tol(self, kind, val, tok, tol=None):
        if kind == "eok":
            return max(TOL_EOK, tol or 0)
        if kind in ("pct", "pp"):
            return pct_tol(abs(val), tok)
        if kind == "won":
            return max(1, abs(val) * 0.0005)
        if kind == "x":   # '2배' → ±0.5, '1.9배' → ±0.05
            return 0.5 * 10 ** (-decimals(tok)) + 1e-9
        return 0

    def has(self, kind, val, tok, tol=None, sign=None, src=None):
        if kind == "man":   # '4.9만'(원) 또는 '1,100만'(건수). 기사 숫자(src)는 '만' 그대로 견준다
            if src is not None:
                return any(abs(abs(x) - abs(val)) <= 0.5 * 10 ** (-decimals(tok)) for x in src)
            return any(abs(abs(x) - abs(val) * 10000) <= 5000 * 10 ** (-decimals(tok)) for x in self.won)
        vals = src if src is not None else {"eok": self.eok, "pct": self.pct + self.qoq, "pp": self.pp + self.pct,
                                            "won": self.won, "x": self.x}.get(kind, [])
        return self._match(vals, val, self.tol(kind, val, tok, tol), sign)

    def has_lab(self, label, kind, val, tok, tol=None, sign=None):
        book = self.lab if kind == "eok" else self.plab if kind in ("pct", "pp") else {}
        vals = book.get(label)
        if not vals:          # 그 계정의 값을 모르면 라벨 검사를 하지 않는다
            return True
        return self._match(vals, val, self.tol(kind, val, tok, tol), sign)


# 서술에서 금액 바로 앞에 오는 계정 라벨. '계속영업이익'·'중단영업이익'은 순이익 쪽이라 영업이익에서 뺀다
LABEL = re.compile(r"(?P<l>매출|계속영업|중단영업|세전이익|법인세|차입금|(?<!계속)(?<!중단)(?<!세전)영업(?:이익|익|손실)|당기순(?:이익|손실)|순(?:이익|익|손실)|자산|부채|자본|현금)")
LABEL_ALIAS = {"영업익": "영업이익", "영업손실": "영업이익", "순익": "순이익", "순손실": "순이익",
               "당기순이익": "순이익", "당기순손실": "순이익"}
PCT_LABELS = ("매출", "영업이익", "순이익", "세전이익", "법인세", "계속영업", "중단영업")   # %·%p도 계정을 맞춰 본다
DIR_LEAD = re.compile(r"^[\s)]*(?:이나|나|만큼|씩|가량|정도|넘게|이상|이|가)?\s*(?:(?:크게|급히|더|또)\s*)?")
DIR_UP = re.compile(r"(늘|증가|개선|확대|상승|올랐|올라|커졌|불었|급증|뛰었|높아)")
DIR_DN = re.compile(r"(줄|감소|하락|축소|악화|내렸|내려|떨어|작아졌|빠졌|급감|쪼그라|뒷걸음|역성장|반토막|낮아|꺾였)")
NEGATE = re.compile(r"않|아니")
NUM = r"\d[\d,]*(?:\.\d+)?(?:\s*조(?:\s*\d[\d,]*\s*억)?)?"
FROM_TO = re.compile(rf"(?P<a>{NUM})\s*(?P<ua>억|%|원)?\s*에서\s*(?P<b>{NUM})\s*(?P<ub>억|%|원)?\s*(?:으로|로)(?P<rest>[^.,]{{0,14}})")


def verb_dir(after: str):
    """숫자 바로 뒤 말이 방향을 말하면 +1/-1. '180억으로 줄었다'는 수준이라 None, 부정문도 None."""
    if re.match(r"^\s*(?:으로|로|에서|까지)", after):
        return None
    if NEGATE.search(after[:12]):
        return None
    a = DIR_LEAD.sub("", after, count=1)
    if DIR_UP.match(a):
        return 1
    if DIR_DN.match(a):
        return -1
    return None


def from_to_conflicts(text: str, pairs=()):
    """'A에서 B로 늘었다·줄었다'가 숫자의 실제 방향(B − A)과 엇갈리거나, 원천의 (비교 → 당기)를 거꾸로 쓴 곳."""
    out = []
    for m in FROM_TO.finditer(plain(text)):
        unit = m.group("ub") or m.group("ua") or ""
        ta, tb = claim_tokens(m.group("a") + (m.group("ua") or unit)), claim_tokens(m.group("b") + unit)
        if not (ta and tb):
            continue
        a, b = ta[0][1], tb[0][1]
        vd = DIR_UP.search(m.group("rest")) and 1 or DIR_DN.search(m.group("rest")) and -1 or None
        if vd and not NEGATE.search(m.group("rest")) and b - a and (b - a > 0) != (vd > 0):
            out.append((m.group(0).strip(), "늘었다·줄었다가 두 숫자의 실제 방향과 반대다"))
            continue
        tol = lambda x: max(TOL_EOK, abs(x) * 0.006)    # 조 단위 반올림까지
        fwd = any(abs(p - a) <= tol(p) and abs(c - b) <= tol(c) for p, c in pairs)
        rev = any(abs(c - a) <= tol(c) and abs(p - b) <= tol(p) for p, c in pairs)
        if rev and not fwd:
            out.append((m.group(0).strip(), "비교 기간과 당기 숫자의 앞뒤가 바뀌었다"))
    return out
SENT_END = re.compile(r"[.!?。]\s|[,;]")         # 라벨은 같은 문장, 같은 쉼표 마디 안에서만 잇는다
JOSA = re.compile(r"(으로|에서|까지|부터|보다|은|는|이|가|을|를|도|의|과|와|로|만|에)$")
# 라벨로 읽는 낱말 전체. '금융자산', '리스부채', '자본금'처럼 하위 계정 낱말은 라벨이 아니다
LABEL_WORDS = {"매출", "매출액", "총매출", "영업이익", "계속영업", "계속영업이익", "중단영업", "중단영업이익", "중단영업손실",
               "세전이익", "법인세", "법인세비용", "미지급법인세", "차입금", "단기차입금", "장기차입금", "순이익", "당기순이익",
               "지배주주순이익", "자산", "자산총계", "총자산", "부채", "부채총계", "총부채", "자본", "자본총계", "지배주주자본",
               "현금", "현금및현금성자산", "현금성자산", "보유현금", "현금흐름", "영업활동현금흐름",
               "매출증가율", "영업이익률", "순이익률", "지배주주순이익률",
               "영업익", "영업손실", "순익", "순손실", "당기순손실"}


def find_labels(seg: str):
    """seg 안의 라벨 (위치순). 라벨 낱말이 하위 계정 이름의 일부면 건너뛴다."""
    out = []
    for mt in LABEL.finditer(seg):
        a, b = mt.start(), mt.end()
        while a > 0 and "가" <= seg[a - 1] <= "힣":
            a -= 1
        while b < len(seg) and "가" <= seg[b] <= "힣":
            b += 1
        word = seg[a:b]
        for _ in range(2):
            word = JOSA.sub("", word) if word not in LABEL_WORDS else word
        if word in LABEL_WORDS:
            out.append(LABEL_ALIAS.get(mt.group("l"), mt.group("l")))
    return out
LABEL_GAP = re.compile(r"^[\s→~∼〜,()·\-]*(?:에서)?\s*$")   # 'A억 → B억', 'A억에서 B억으로'는 앞 라벨을 잇는다
LABEL_AFTER = re.compile(r"^\s*\S*(?:난|든|한|된)\s+")       # '1,810억 늘어난 영업이익'처럼 꾸미는 말 바로 뒤 라벨       # 'A억 → B억'처럼 숫자 사이가 화살표뿐이면 앞 라벨을 잇는다
MAN_WON = re.compile(r"(\d+)만\s*(\d[\d,]{0,4})\s*원")
RANGE = re.compile(r"(\d[\d,]*(?:\.\d+)?)(\s*[~∼〜]\s*)(\d[\d,]*(?:\.\d+)?)\s*(원|억|조|%)")


# 라벨은 합계 계정에만 붙인다(매출원가·매출채권이 '매출', 자본금이 '자본'이 되지 않게)
LABEL_IDS = {
    "매출": {"ifrs-full_Revenue"},
    "영업이익": {"dart_OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities"},
    "세전이익": {"ifrs-full_ProfitLossBeforeTax"},
    "법인세": {"ifrs-full_IncomeTaxExpenseContinuingOperations", "ifrs-full_CurrentTaxLiabilitiesCurrent",
               "ifrs-full_CurrentTaxLiabilities", "ifrs-full_IncomeTaxesPaidRefundClassifiedAsOperatingActivities"},
    "계속영업": {"ifrs-full_ProfitLossFromContinuingOperations", "ifrs-full_IncomeFromContinuingOperationsAttributableToOwnersOfParent",
               "ifrs-full_ProfitLossFromContinuingOperationsAttributableToNoncontrollingInterests"},
    "중단영업": {"ifrs-full_ProfitLossFromDiscontinuedOperations", "ifrs-full_IncomeFromDiscontinuedOperationsAttributableToOwnersOfParent",
               "ifrs-full_ProfitLossFromDiscontinuedOperationsAttributableToNoncontrollingInterests"},
    "순이익": {"ifrs-full_ProfitLoss", "ifrs-full_ProfitLossAttributableToOwnersOfParent",
             "ifrs-full_ProfitLossAttributableToNoncontrollingInterests"},
    "자산": {"ifrs-full_Assets", "ifrs-full_CurrentAssets", "ifrs-full_NoncurrentAssets", "ifrs-full_CashAndCashEquivalents"},
    "부채": {"ifrs-full_Liabilities", "ifrs-full_CurrentLiabilities", "ifrs-full_NoncurrentLiabilities"},
    "자본": {"ifrs-full_Equity", "ifrs-full_EquityAttributableToOwnersOfParent", "ifrs-full_NoncontrollingInterests"},
    "현금": {"ifrs-full_CashAndCashEquivalents", "ifrs-full_CashFlowsFromUsedInOperatingActivities",
           "ifrs-full_CashFlowsFromUsedInInvestingActivities", "ifrs-full_CashFlowsFromUsedInFinancingActivities",
           "ifrs-full_IncreaseDecreaseInCashAndCashEquivalents"},
    "차입금": {"ifrs-full_CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings", "ifrs-full_ShorttermBorrowings",
             "ifrs-full_LongtermBorrowings", "ifrs-full_Borrowings"},
}
# 표준 계정 id를 쓰지 않는 회사(소형사)는 합계 계정 이름으로 본다
LABEL_NAMES = {"매출": ("매출액", "영업수익", "수익(매출액)", "매출"), "영업이익": ("영업이익", "영업이익(손실)"),
               "순이익": ("당기순이익", "당기순이익(손실)", "분기순이익", "반기순이익"), "자산": ("자산총계",),
               "부채": ("부채총계",), "자본": ("자본총계",), "현금": ("현금및현금성자산",)}


def labels_of(account_nm: str, account_id: str = "") -> set[str]:
    """계정이 서술에서 불릴 수 있는 라벨. 합계 계정만. '현금및현금성자산'은 현금이자 자산이다."""
    out = {lab for lab, ids in LABEL_IDS.items() if account_id in ids}
    nm = acc_name(account_nm or "")
    out |= {lab for lab, names in LABEL_NAMES.items() if nm in names}
    return out


TOKEN = re.compile(
    r"(?P<approx>약\s*)?(?P<n>[+-]?\d[\d,]*(?:\.\d+)?)\s*(?P<u>백만\s*원|천\s*원|bp|조\s*\d[\d,]*\s*억|조|억|만|원|%p|pp|%|배)(?!\w*년)")


def claim_tokens(text, with_label=False):
    """서술 속 (종류, 값, 표기, 숫자, 허용오차[, 라벨]). '29,100 ~ 69,700원'은 앞 숫자에도 단위를 붙여 본다."""
    out = []
    t = MAN_WON.sub(lambda m: f"{int(m.group(1)) * 10000 + int(m.group(2).replace(',', '')):,}원", plain(text))   # 3만5000원 → 35,000원
    t = RANGE.sub(lambda m: f"{m.group(1)}{m.group(4)}{m.group(2)}{m.group(3)}{m.group(4)}", t)
    prev_end, prev_lab = 0, None
    for mt in TOKEN.finditer(t):
        n, u = mt.group("n"), re.sub(r"\s+", "", mt.group("u"))
        v = to_num(n)
        tol = None
        if u.startswith("조") and "억" in u:
            kind, v = "eok", v * 10000 + to_num(re.search(r"\d[\d,]*", u[1:]).group())
        elif u == "조":
            kind, v = "eok", v * 10000
            tol = 5000 * 10 ** (-decimals(n))          # 31.9조 → ±500억
            if not decimals(n) and not mt.group("approx"):
                tol = min(tol, abs(v) * 0.05)          # '1조'를 ±50%로 받지 않는다(넓게는 '약 1조')
        elif u in ("백만원", "천원"):
            kind, v = "eok", v / (100 if u == "백만원" else 100000)
        elif u == "bp":
            kind, v = "pp", v / 100
        else:
            kind = {"억": "eok", "%": "pct", "%p": "pp", "pp": "pp", "원": "won", "만": "man", "배": "x"}[u]
        if mt.group("approx") and kind == "eok":
            tol = max(tol or 0, abs(v) * 0.01)        # '약 3,400억' → ±1%
        tok = mt.group(0).strip()
        gap = t[prev_end:mt.start()]
        seg = SENT_END.split(gap)[-1]                 # 라벨은 같은 문장 안에서만 잇는다
        labs = find_labels(seg)
        lab = tuple(dict.fromkeys(labs)) if labs else (prev_lab if LABEL_GAP.match(gap) else None)
        prev_end, prev_lab = mt.end(), lab
        vd = verb_dir(t[mt.end():mt.end() + 16])
        if n.startswith(("+", "-")):
            sign = 1 if n.startswith("+") else -1
            if vd and vd != sign:
                sign = 0                                   # '+731억 감소'처럼 부호와 동사가 엇갈린다
        else:
            sign = vd
        if not lab:   # '1,810억 늘어난 영업이익'처럼 라벨이 꾸미는 말 바로 뒤에 오면
            ahead = t[mt.end():mt.end() + 16]
            m2 = LABEL_AFTER.match(ahead)
            la = find_labels(ahead[m2.end():m2.end() + 8]) if m2 else []
            lab = (la[0],) if la and ahead[m2.end():].lstrip().startswith(tuple(LABEL_WORDS)) else None
        s0 = t.rfind(". ", 0, mt.start())
        s1 = t.find(". ", mt.end())
        sent = t[s0 + 2 if s0 >= 0 else 0: s1 if s1 >= 0 else len(t)]
        out.append((kind, v, tok, n, tol, lab, sign, sent) if with_label else (kind, v, tok, n, tol))
    return out


def norm_claim(s):
    return re.sub(r"[\s+]", "", plain(s))


def check_ledger(d, R: Report, pool, tps, tp):
    L = "C 출처"
    m, js = d.get("meta", {}), d.get("js", {})
    audit = d.get("audit") or {}
    web = audit.get("web") or []
    book = {(w.get("sec"), str(w.get("key"))): w for w in web}
    ok_status = ("confirmed", "corrected")

    def entry(sec, key):
        return book.get((sec, str(key)))

    # 증권사
    for a in js.get("ANALYSTS", []):
        e = entry("ANALYSTS", a["firm"])
        if not e:
            R.add(L, False, f"ANALYSTS '{a['firm']}'", "audit.web 기록 없음",
                  "검증 에이전트가 원문 URL에서 의견·목표가·날짜를 확인해 기록한다")
        elif e.get("status") in ok_status:
            R.add(L, bool(e.get("url")), f"ANALYSTS '{a['firm']}'", "확인 URL " + ("있음" if e.get("url") else "없음"))
        else:
            labeled = any(w in (a.get("note") or "") for w in ("추정", "미확인"))
            R.add(L, labeled, f"ANALYSTS '{a['firm']}'", "미확인 항목",
                  "note에 '(추정)' 또는 '미확인'을 표기하거나 표에서 뺀다")

    # 부문 매출: est:false는 확인 기록 필수
    for s in js.get("SEGS", []):
        if s.get("est"):
            continue
        e = entry("SEGS", s["name"])
        R.add(L, bool(e) and e.get("status") in ok_status, f"SEGS '{s['name']}'",
              "확인됨" if e and e.get("status") in ok_status else "출처 확인 기록 없음",
              "IR·사업보고서로 확인해 기록하거나, 역산치면 est:true로 바꾼다")

    # 뉴스: 미확인 기사는 싣지 않는다
    for n in js.get("NEWS", []):
        e = entry("NEWS", n.get("url"))
        R.add(L, bool(e) and e.get("status") in ok_status, f"NEWS '{n.get('h', '')[:24]}'",
              "확인됨" if e and e.get("status") in ok_status else "URL·수치 확인 기록 없음",
              "URL을 열어 제목·날짜·본문 수치를 대조한다. 열리지 않으면 기사를 교체한다")

    # 컨센서스 집계
    e = entry("CONS", "coverage")
    cons_ok = bool(e) and e.get("status") in ok_status
    labeled = any(w in plain(m.get("coverage_note", "")) for w in ("미확인", "추정", "확인된"))
    R.add(L, cons_ok or labeled, "CONS 집계", "확인됨" if cons_ok else ("범위 표기됨" if labeled else "근거 없음"),
          "meta.coverage_note에 집계 범위(표의 N개 증권사 기준, 미확인)를 밝힌다. 조립 스크립트를 쓰면 자동으로 들어간다")

    # 목표가 범위: 표에서 계산되거나 출처가 있어야 한다
    calc = {"low": min(tps) if tps else None, "high": max(tps) if tps else None,
            "avg": sum(tps) / len(tps) if tps else None}
    for k in ("low", "avg", "high"):
        v = tp.get(k)
        if v is None:
            continue
        derived = calc[k] is not None and abs(v - calc[k]) <= max(1, calc[k] * 0.005)
        e = entry("meta", f"tp_{k}")
        sourced = bool(e) and e.get("status") in ok_status and e.get("url")
        R.add(L, derived or sourced, f"meta.tp_{k}",
              f"표기 {fmt(v)} / 표 기준 {fmt(calc[k])}" + (" · 출처 있음" if sourced else ""),
              "목표가 평균은 조립 스크립트가 표의 증권사로 계산한다. 조각을 고쳤다면 다시 조립한다")
    if tps and tp.get("low") and tp.get("high"):
        R.add(L, tp["low"] <= min(tps) and max(tps) <= tp["high"], "목표가 범위 ⊇ 표",
              f"범위 {fmt(tp['low'])}~{fmt(tp['high'])} / 표 {fmt(min(tps))}~{fmt(max(tps))}")

    # 서술 속 숫자
    claims = {norm_claim(c.get("text", "")): c for c in (audit.get("claims") or [])}
    texts = [("HEADLINE", 0, js.get("HEADLINE", ""))]
    texts += [("WATCH", i, w) for i, w in enumerate(js.get("WATCH", []))]
    texts += [("NOTES", i, w) for i, w in enumerate(js.get("NOTES", []))] + [("NP_BRIDGE", 0, js.get("NP_BRIDGE", ""))]
    texts += [("CHIPS", i, c.get("txt", "")) for i, c in enumerate(js.get("CHIPS", []))]
    for sec in ("BULLS", "BEARS"):
        texts += [(sec, i, f"{x.get('t', '')} {x.get('d', '')}") for i, x in enumerate(js.get(sec, []))]
    texts += [("PERSONAS", p.get("name", i), p.get("eval", "")) for i, p in enumerate(js.get("PERSONAS", []))]
    texts += [("SEGS.sub", sg.get("name", i), sg.get("sub", "")) for i, sg in enumerate(js.get("SEGS", []))]   # 화면에 나온다
    rv = js.get("REVIEW") or {}
    texts += [("REVIEW", "scene", rv.get("scene", ""))]
    texts += [("REVIEW", r.get("role", i), f"{r.get('comment', '')} {r.get('fix', '')} {r.get('limit', '')}")
              for i, r in enumerate(rv.get("reviews") or [])]
    # 확인된 기사·증권사 note의 숫자: 출처(매체·증권사·'보도'·'추정')를 밝힌 문장에서만 쓸 수 있다
    sources = set()
    for n in js.get("NEWS", []):
        e = entry("NEWS", n.get("url"))
        if e and e.get("status") in ok_status:
            sources.add(n.get("src", ""))
            for kind, v, tok, num, tol in claim_tokens(f"{n.get('h', '')} {n.get('body', '')}"):
                if kind in pool.ext:
                    pool.ext[kind].append(v if kind != "eok" or not tol else v)
    for a in js.get("ANALYSTS", []):
        e = entry("ANALYSTS", a["firm"])
        if e and e.get("status") in ok_status:
            sources.add(a["firm"])
            for kind, v, tok, num, tol in claim_tokens(a.get("note") or ""):
                if kind in pool.ext:
                    pool.ext[kind].append(v)
    sources = {x for x in sources if x}
    attrib = re.compile("|".join(re.escape(x) for x in sources) or r"(?!x)x")   # 출처 이름(매체·증권사)만 인정한다

    def why_fail(kind, v, n, tol, lab, sign, text):
        """None이면 통과. 아니면 실패 이유. text는 그 숫자가 든 문장, lab은 같은 마디의 계정 라벨들."""
        if sign == 0:
            return "부호(+/−)와 늘었다·줄었다가 서로 엇갈린다"
        if kind in pool.ext and pool.has(kind, v, n, tol, None, src=pool.ext[kind]) and attrib.search(text):
            return None   # 같은 문장에 출처를 밝힌 확인된 기사·증권사 숫자
        if kind == "pct" and re.search(r"직전\s*분기|전\s*분기", text):
            return None if pool.has(kind, v, n, tol, sign, src=pool.qoq) else "직전 분기 대비 값이 아니다"
        if kind == "pct" and re.search(r"전년", text) and pool.has(kind, v, n, tol, sign, src=pool.qoq) \
                and not pool.has(kind, v, n, tol, sign, src=pool.pct):
            return "직전 분기 대비 값이다. '전년 대비'로 쓰지 않는다"
        if pool.has(kind, v, n, tol, sign):
            if lab and not any(pool.has_lab(x, kind, v, n, tol, sign) for x in lab):
                return f"'{'·'.join(lab)}' 계정 값이 아니다(다른 계정의 숫자)"
            return None
        if sign and pool.has(kind, v, n, tol):
            return "부호(늘었다·줄었다)가 원천과 반대다"
        if kind in ("pct", "pp") and pool.has(kind, v, n, tol, sign, src=pool.orig):
            return None if re.search(r"처음 발표|기사", text) else \
                "처음 발표한 전년 대비 증가율이다. '처음 발표한 전년과 견주면'처럼 밝혀야 쓴다(성장률이 아니다)"
        if kind in pool.ext and pool.has(kind, v, n, tol, None, src=pool.ext[kind]):
            return "기사·증권사 숫자다. 출처(매체·증권사)를 같은 문장에 밝힌다"
        return "재무·주가 데이터에서 나오지 않는 숫자"

    for sec, key, text in texts:
        seen = set()
        for frag, why in from_to_conflicts(text, pool.pairs):
            R.add(L, False, f"{sec}[{key}] '{frag}'", why, "B·C 조각에서 바로잡고 다시 조립한다")
        for kind, v, tok, n, tol, lab, sign, sent in claim_tokens(text, with_label=True):
            if tok in seen:
                continue
            why = why_fail(kind, v, n, tol, lab, sign, sent)
            if why is None:
                continue
            seen.add(tok)
            c = claims.get(norm_claim(re.sub(r"^약\s*", "", tok))) or claims.get(norm_claim(tok))
            if c and c.get("status") in ok_status and c.get("url"):
                continue
            R.add(L, False, f"{sec}[{key}] '{tok}'", why,
                  "B·C 조각(B.json·C.json)에서 그 숫자를 빼거나 facts에 있는 표기로 바꾸고 다시 조립한다. "
                  "기사 숫자를 꼭 써야 하면 원문을 확인해 V1.json의 claims에 {text, url, status:'confirmed'}로 남긴다")


# ───────────────────────── 게이트 ─────────────────────────

def state_paths(data_path: pathlib.Path):
    stem = data_path.name[:-5] if data_path.name.endswith(".json") else data_path.name
    return data_path.with_name(stem + ".verify.json"), data_path.with_name(stem + ".verify.md")


def load_state(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"rounds": [], "status": None, "sha": None, "max_rounds": MAX_ROUNDS}


def write_md(md_path, data, state, R: Report | None):
    m = data.get("meta", {})
    lines = [f"# 숫자 검증 리포트 · {m.get('name')} {m.get('q_cur_short', '')}", "",
             f"- 상태: **{state['status']}**  (회차 {len(state['rounds'])}/{state['max_rounds']})",
             f"- data sha256: `{state['sha'][:12]}`", ""]
    lines += ["## 회차 기록", "", "| 회차 | 시각 | 불일치 | sha |", "|---|---|---|---|"]
    for r in state["rounds"]:
        lines.append(f"| {r['n']} | {r['at']} | {r['fails']} | `{r['sha'][:12]}` |")
    if R:
        f = R.fails
        lines += ["", f"## 불일치 {len(f)}건", ""]
        if f:
            lines += ["| 층 | 항목 | 내용 | 고치는 법 |", "|---|---|---|---|"]
            lines += [f"| {i['layer']} | {i['item']} | {i['msg']} | {i['hint']} |" for i in f]
        else:
            lines.append("없음.")
        ok = [i for i in R.items if i["ok"]]
        lines += ["", f"## 통과 {len(ok)}건", "", "<details><summary>펼치기</summary>", ""]
        lines += [f"- [{i['layer']}] {i['item']}: {i['msg']}" for i in ok]
        lines += ["", "</details>", ""]
    if state["status"] == "BLOCKED":
        lines += ["", "## 다음 행동 (사용자 판단 필요)", "",
                  f"{state['max_rounds']}회차 안에 맞추지 못했다. 자동 수정을 멈추고 아래 중 하나를 사용자에게 묻는다.", "",
                  "1. 남은 항목을 사용자가 직접 확인해 값을 준다 → 반영 후 `--reset`으로 재검증",
                  "2. 미확인 표기를 붙인 채 빌드한다 → `build_report.py --allow-unverified` (리포트 상단에 경고 배너)",
                  "3. 이번 리포트를 중단한다"]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_checks(data):
    R, pool = Report(), Pool()
    tps, tp = check_arithmetic(data, R, pool)
    check_identity(data, R)
    check_dart(data, R, pool)
    check_price(data, R, pool)
    check_ledger(data, R, pool, tps, tp)
    probs = review_problems((data.get("js") or {}).get("REVIEW"))
    R.add("A 산술", not probs, "전문가 평가 형식", "; ".join(probs) or "RED·SILVER·GOLD 3인",
          "R 에이전트(references/agent-prompts.md)로 R.json을 쓰고 다시 조립한다")
    return R


def main():
    ap = argparse.ArgumentParser(description="DART 리포트 숫자 검증 게이트")
    ap.add_argument("data")
    ap.add_argument("--max-rounds", type=int, default=MAX_ROUNDS)
    ap.add_argument("--status", action="store_true", help="게이트 상태만 출력")
    ap.add_argument("--reset", action="store_true", help="회차 초기화 (사용자 지시가 있을 때만)")
    args = ap.parse_args()

    data_path = pathlib.Path(args.data).resolve()
    data = json.loads(data_path.read_text(encoding="utf-8"))
    state_p, md_p = state_paths(data_path)
    state = load_state(state_p)
    state["max_rounds"] = args.max_rounds
    sha = sha256(data_path)

    if args.reset:
        state = {"rounds": [], "status": None, "sha": None, "max_rounds": args.max_rounds}
        state_p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        print("↺ 회차를 초기화했다.")
        return

    if args.status:
        cur = "PASS" if state.get("status") == "PASS" and state.get("sha") == sha else state.get("status") or "미검증"
        if state.get("status") == "PASS" and state.get("sha") != sha:
            cur = "STALE (PASS 이후 data.json이 바뀜)"
        print(f"{cur} · 회차 {len(state['rounds'])}/{state['max_rounds']}")
        return

    if state.get("status") == "BLOCKED":
        print(f"⛔ BLOCKED: {state['max_rounds']}회차를 모두 썼다. 자동 수정을 멈추고 사용자에게 {md_p.name}의 남은 항목을 보고한다.")
        sys.exit(EXIT["BLOCKED"])

    if state.get("status") == "PASS" and state.get("sha") != sha:   # PASS 뒤 수정은 새 사이클
        state["rounds"] = []
    new_round = not state["rounds"] or state["rounds"][-1]["sha"] != sha
    if new_round and len(state["rounds"]) >= state["max_rounds"]:
        state["status"] = "BLOCKED"
        state_p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"⛔ BLOCKED: {state['max_rounds']}회차를 모두 썼다.")
        sys.exit(EXIT["BLOCKED"])

    try:
        R = run_checks(data)
    except (OSError, ValueError) as e:     # 네트워크·API 장애(requests 예외 포함): 회차를 쓰지 않는다
        print(f"⚠️  INCOMPLETE: 원천 대조 실패 ({type(e).__name__}: {e}). 회차는 소모되지 않았다. 잠시 후 다시 실행한다.")
        sys.exit(EXIT["INCOMPLETE"])

    fails = R.fails
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    if new_round:
        state["rounds"].append({"n": len(state["rounds"]) + 1, "at": now, "fails": len(fails), "sha": sha})
    else:
        state["rounds"][-1].update({"at": now, "fails": len(fails)})
    n = len(state["rounds"])
    if not fails:
        status = "PASS"
    elif n >= state["max_rounds"]:
        status = "BLOCKED"
    else:
        status = "FAIL"
    state.update({"status": status, "sha": sha, "checks": len(R.items), "verified_at": now})
    state_p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    write_md(md_p, data, state, R)

    head = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "BLOCKED": "⛔ BLOCKED"}[status]
    tail = "" if new_round else " (같은 내용 재검증, 회차 미소모)"
    print(f"{head} · {len(R.items) - len(fails)}/{len(R.items)} 통과 · 회차 {n}/{state['max_rounds']}{tail}")
    for i in fails:
        print(f"  ✗ [{i['layer']}] {i['item']}: {i['msg']}" + (f"\n      → {i['hint']}" if i["hint"] else ""))
    if status == "FAIL":
        print(f"\n남은 회차 {state['max_rounds'] - n}. 위 항목을 조각 파일(parts)에서 고치고 "
              "assemble_report.py build로 다시 조립한 뒤 이 검증을 다시 실행한다. "
              "(조립 스크립트를 쓰지 않은 잠정실적 리포트만 data.json을 직접 고친다)")
    elif status == "BLOCKED":
        print(f"\n회차 소진. 자동 수정을 멈추고 사용자에게 보고한다: {md_p}")
    print(f"리포트: {md_p}")
    sys.exit(EXIT[status])


if __name__ == "__main__":
    main()
