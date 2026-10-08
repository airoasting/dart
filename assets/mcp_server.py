#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DART 공시 데이터를 MCP 도구로 내놓는 서버. 표준 라이브러리만으로 돈다 (requests가 있으면 그것을 쓴다).

    python3 mcp_server.py                         # stdio MCP 서버로 뜬다 (클라이언트가 띄운다)
    python3 mcp_server.py --list                  # 도구 목록과 입력
    python3 mcp_server.py --help share_top_holders   # 도구 하나의 설명과 입력 상세
    python3 mcp_server.py --call fin_ratios '{"corp": "카카오"}'   # 도구 하나를 바로 불러 본다

설계 원칙
- 모든 도구는 corp에 회사명·약칭·옛 이름·종목코드·DART 고유번호를 다 받는다. 이름 해석은 corp_registry가 한다.
- year·period를 비우면 가장 최근 정기보고서 기간을 쓴다. 고른 기간은 응답 meta에 남긴다.
- 연결 재무제표가 없으면 별도로 한 번 더 찾는다(basis=auto).
- 응답은 DART 원본 필드를 그대로 두되, 행마다 반복되는 값은 common으로 올리고 원문 링크를 붙인다.
"""
from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path
from typing import Any, Callable

warnings.filterwarnings("ignore")   # urllib3 LibreSSL 경고 등. stdio 서버에서는 잡음일 뿐이다
sys.path.insert(0, str(Path(__file__).resolve().parent))

SERVER = {"name": "dart", "version": "2.3.0"}
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
VIEW_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="

PERIOD_CODE = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
CODE_PERIOD = {v: k for k, v in PERIOD_CODE.items()}
BASIS_CODE = {"consolidated": "CFS", "separate": "OFS"}
RATIO_GROUP = {"profitability": "M210000", "stability": "M220000", "growth": "M230000", "activity": "M240000"}
FILING_KIND = {"periodic": "A", "major": "B", "issuance": "C", "ownership": "D", "other": "E", "audit": "F",
               "fund": "G", "abs": "H", "exchange": "I", "ftc": "J"}
MARKET_CODE = {"kospi": "Y", "kosdaq": "K", "konex": "N", "other": "E"}
NOISE = {"corp_cls", "corp_code", "corp_name", "stock_code", "reprt_code", "bsns_year"}


class ToolError(Exception):
    """사용자가 고칠 수 있는 입력 문제. data는 후보 목록처럼 다음 행동에 필요한 것을 담는다."""

    def __init__(self, message: str, data: dict | None = None) -> None:
        super().__init__(message)
        self.data = data or {}


# ── DART 접속 ──────────────────────────────────────────────────────────────

_client = None


def client():
    """키가 없어도 도구 목록은 보여야 하므로 첫 호출 때 만든다."""
    global _client
    if _client is None:
        from dart_client import DartClient
        try:
            _client = DartClient()
        except RuntimeError as e:
            raise ToolError(str(e)) from None
    return _client


def call(endpoint: str, **params: Any) -> list[dict]:
    """DART 호출 → 행 목록. 013(데이터 없음)은 빈 목록, 그 밖의 비정상 status는 ToolError."""
    data = client()._get(endpoint, **{k: v for k, v in params.items() if v not in (None, "")})
    status = data.get("status")
    if status == "013":
        return []
    if status != "000":
        raise ToolError(f"DART {endpoint}: [{status}] {data.get('message', '')}".strip())
    if "list" in data:
        return data["list"]
    return [{k: v for k, v in data.items() if k not in ("status", "message")}]


# ── 입력 해석 ──────────────────────────────────────────────────────────────

def resolve_corp(q: str) -> dict:
    """corp 입력 하나 → {corp_code, corp_name, stock_code, market, fiscal_month}.

    8자리 숫자는 DART 고유번호로 바로 쓴다(비상장사도 된다). 그 밖에는 상장사 목록에서 하나로 좁혀야 진행한다.
    """
    import corp_registry

    q = str(q or "").strip()
    if not q:
        raise ToolError("corp가 비었습니다. 회사명, 종목코드(6자리), DART 고유번호(8자리) 중 하나를 주세요.")
    if re.fullmatch(r"\d{8}", q):
        row = corp_registry.load().by_corp.get(q)
        if row:
            p = corp_registry._public(row)
            return {k: p.get(k) for k in ("corp_code", "corp_name", "stock_code", "market", "fiscal_month")}
        info = call("company.json", corp_code=q)
        if not info:
            raise ToolError(f"DART 고유번호 {q}에 해당하는 회사가 없습니다.")
        acc = str(info[0].get("acc_mt", "")).strip()
        return {"corp_code": q, "corp_name": info[0].get("corp_name"), "stock_code": info[0].get("stock_code") or "",
                "market": "비상장/기타", "fiscal_month": int(acc) if acc.isdigit() else 12}
    res = client().resolve_corp(q)
    if res["status"] == "ok":
        c = res["corp"]
        return {k: c.get(k) for k in ("corp_code", "corp_name", "stock_code", "market", "fiscal_month")}
    raise ToolError(res["message"] + " 종목코드나 정확한 회사명으로 다시 불러 주세요.",
                    {"status": res["status"], "candidates": [_cand(c) for c in res["candidates"]],
                     "suggestions": res["suggestions"]})


def _cand(c: dict) -> dict:
    return {k: c.get(k) for k in ("corp_name", "stock_code", "corp_code", "market_label", "display")}


def resolve_period(corp: dict, year: str | None, period: str | None) -> dict:
    """year·period → bsns_year·reprt_code. 둘 다 비면 최근 정기보고서, year만 있으면 사업보고서(FY)."""
    if year:
        if not re.fullmatch(r"\d{4}", str(year)):
            raise ToolError(f"year는 4자리 연도여야 합니다: {year}")
        p = (period or "FY").upper()
        if p not in PERIOD_CODE:
            raise ToolError(f"period는 {', '.join(PERIOD_CODE)} 중 하나여야 합니다: {period}")
        return {"bsns_year": str(year), "reprt_code": PERIOD_CODE[p], "period": p, "chosen": "지정"}
    if period:
        raise ToolError("period를 주면 year도 함께 주세요. 둘 다 비우면 가장 최근 정기보고서를 씁니다.")
    rep = client().latest_periodic_report(corp["corp_code"], fiscal_month=corp.get("fiscal_month") or 12)
    if not rep:
        raise ToolError(f"{corp['corp_name']}의 최근 정기보고서를 찾지 못했습니다. year와 period를 직접 주세요.")
    return {"bsns_year": rep["bsns_year"], "reprt_code": rep["reprt_code"], "period": CODE_PERIOD[rep["reprt_code"]],
            "chosen": f"최근 정기보고서 {rep['report_nm']}", "rcept_no": rep["rcept_no"]}


# ── 응답 다듬기 ────────────────────────────────────────────────────────────

def _clean(v: Any) -> Any:
    if isinstance(v, str):
        v = v.strip()
        if v and set(v) == {"#"}:     # DART가 자릿수 넘침을 '#########'로 내보낸다
            return None
    return v


def shape(rows: list[dict], drop: set[str] = NOISE, keep_rcept: bool = False) -> dict:
    """행마다 같은 값은 common으로 올리고, 접수번호는 원문 링크로 바꾼다.

    keep_rcept=True는 공시·보고 목록이다. 행 하나가 보고 한 건이라 올리지 않는다
    (두 건의 보고자가 같다고 보고자를 행에서 빼면 읽는 쪽이 헷갈린다).
    """
    rows = [{k: _clean(v) for k, v in r.items() if k not in drop} for r in rows]
    common: dict[str, Any] = {}
    if len(rows) > 1 and not keep_rcept:
        for k in list(rows[0]):
            if all(r.get(k) == rows[0][k] for r in rows):
                common[k] = rows[0][k]
        rows = [{k: v for k, v in r.items() if k not in common} for r in rows]
    elif rows and not keep_rcept and "rcept_no" in rows[0]:
        common["rcept_no"] = rows[0].pop("rcept_no")
    if "rcept_no" in common:
        common["source_url"] = VIEW_URL + common.pop("rcept_no")
    for r in rows:
        if "rcept_no" in r:
            r["url"] = VIEW_URL + r["rcept_no"]
    return {"common": common, "rows": rows} if common else {"rows": rows}


def result(corp: dict, body: dict, **meta: Any) -> dict:
    out = {"corp": {k: corp[k] for k in ("corp_name", "stock_code", "corp_code")}}
    meta = {k: v for k, v in meta.items() if v is not None}
    if meta:
        out["meta"] = meta
    out.update(body)
    if not body.get("rows"):
        out["note"] = "DART에 이 조건의 데이터가 없습니다 (status 013)."
    return out


def periodic(endpoint: str, a: dict, **extra: Any) -> tuple[dict, dict, list[dict]]:
    """정기보고서 기반 엔드포인트 공통 흐름: 회사 → 기간 → 호출."""
    corp = resolve_corp(a["corp"])
    per = resolve_period(corp, a.get("year"), a.get("period"))
    rows = call(endpoint, corp_code=corp["corp_code"], bsns_year=per["bsns_year"], reprt_code=per["reprt_code"],
                **extra)
    return corp, per, rows


def _pmeta(per: dict) -> dict:
    return {"year": per["bsns_year"], "period": per["period"], "period_source": per["chosen"]}


def with_basis(endpoint: str, a: dict) -> tuple[dict, dict, list[dict], str | None]:
    """연결(CFS) → 별도(OFS) 순으로 찾는다. basis를 지정하면 그것만 본다."""
    basis = a.get("basis") or "auto"
    corp = resolve_corp(a["corp"])
    per = resolve_period(corp, a.get("year"), a.get("period"))
    order = ["CFS", "OFS"] if basis == "auto" else [BASIS_CODE[basis]]
    rows: list[dict] = []
    for fs in order:
        rows = call(endpoint, corp_code=corp["corp_code"], bsns_year=per["bsns_year"],
                    reprt_code=per["reprt_code"], fs_div=fs)
        if rows:
            break
    return corp, per, rows, ({"CFS": "연결", "OFS": "별도"}[fs] if rows else None)


# ── 도구 구현 (목록 순서와 같다) ───────────────────────────────────────────

def t_corp_resolve(a: dict) -> dict:
    scope = a.get("scope") or "listed"
    if scope == "all":    # pandas 없이 읽는다 (dart_client.find_corp와 같은 규칙)
        import csv
        import corp_registry

        path = corp_registry.cache_dir() / "corp_codes_all.csv"
        if not path.exists():
            corp_registry.refresh(client().api_key)
        key = corp_registry.norm(a["query"])
        with open(path, encoding="utf-8", newline="") as f:
            hit = [{k: r.get(k, "") for k in ("corp_code", "corp_name", "stock_code")}
                   for r in csv.DictReader(f) if key and key in corp_registry.norm(r.get("corp_name", ""))]
        rows = hit[: int(a.get("limit") or 20)]
        return {"query": a["query"], "scope": "all", "total": len(hit), "rows": rows,
                "note": "비상장·폐지 포함 DART 전체 목록 검색입니다. corp_code(8자리)를 다른 도구의 corp에 넣으면 됩니다."}
    res = client().resolve_corp(a["query"])
    out = {k: res[k] for k in ("query", "status", "message")}
    if res["corp"]:
        out["corp"] = {k: res["corp"].get(k) for k in ("corp_code", "corp_name", "corp_eng_name", "stock_code",
                                                     "market_label", "sector", "fiscal_month", "former_names", "kind")}
    if res["candidates"]:
        out["candidates"] = [_cand(c) for c in res["candidates"]]
    for k in ("suggestions", "notes"):
        if res.get(k):
            out[k] = res[k]
    return out


def t_corp_profile(a: dict) -> dict:
    corp = resolve_corp(a["corp"])
    return result(corp, shape(call("company.json", corp_code=corp["corp_code"]), drop={"corp_code"}))


def t_filing_search(a: dict) -> dict:
    import datetime as dt

    corp = resolve_corp(a["corp"]) if a.get("corp") else None
    end = re.sub(r"\D", "", a.get("to") or "") or dt.date.today().strftime("%Y%m%d")   # 2026-10-08 → 20261008
    bgn = re.sub(r"\D", "", a.get("from") or "") or (dt.datetime.strptime(end, "%Y%m%d").date() - dt.timedelta(days=30)).strftime("%Y%m%d")
    for d in (bgn, end):
        if not re.fullmatch(r"\d{8}", d):
            raise ToolError(f"날짜는 YYYYMMDD 형식이어야 합니다: {d}")
    if not corp and (dt.datetime.strptime(end, "%Y%m%d") - dt.datetime.strptime(bgn, "%Y%m%d")).days > 92:
        raise ToolError("corp 없이 검색할 때 DART는 기간을 3개월 안으로 제한합니다. from·to를 좁히거나 corp를 주세요.")
    data = client()._get("list.json", corp_code=corp["corp_code"] if corp else None, bgn_de=bgn, end_de=end,
                         pblntf_ty=FILING_KIND.get(a.get("kind") or ""), corp_cls=MARKET_CODE.get(a.get("market") or ""),
                         page_no=int(a.get("page") or 1), page_count=min(int(a.get("size") or 20), 100))
    if data.get("status") not in ("000", "013"):
        raise ToolError(f"DART list.json: [{data.get('status')}] {data.get('message', '')}")
    body = shape(data.get("list", []), drop=NOISE if corp else set(), keep_rcept=True)
    meta = {"from": bgn, "to": end, "page": data.get("page_no"), "total": data.get("total_count", 0),
            "total_pages": data.get("total_page")}
    if corp:
        return result(corp, body, **meta)
    return {"meta": meta, **body}


def t_filing_latest_periodic(a: dict) -> dict:
    corp = resolve_corp(a["corp"])
    rep = client().latest_periodic_report(corp["corp_code"], fiscal_month=corp.get("fiscal_month") or 12)
    if not rep:
        return result(corp, {"rows": []})
    report = {"name": rep["report_nm"], "year": rep["bsns_year"], "period": CODE_PERIOD[rep["reprt_code"]],
              "period_end": rep["period_end"], "label": rep["label"], "filed": rep["rcept_dt"],
              "url": VIEW_URL + rep["rcept_no"]}
    return result(corp, {"rows": [report]}, fiscal_month=corp.get("fiscal_month"))


def t_fin_key_accounts(a: dict) -> dict:
    """fnlttSinglAcnt는 연결·별도 행을 한 응답에 함께 준다(fs_div). 호출 한 번으로 고른다."""
    corp, per, rows = periodic("fnlttSinglAcnt.json", a)
    basis = a.get("basis") or "auto"
    order = ["CFS", "OFS"] if basis == "auto" else [BASIS_CODE[basis]]
    fs = next((f for f in order if any(r.get("fs_div") == f for r in rows)), order[0])
    rows = [r for r in rows if r.get("fs_div") == fs]
    return result(corp, shape(rows), basis={"CFS": "연결", "OFS": "별도"}[fs] if rows else None, **_pmeta(per))


def t_fin_statements(a: dict) -> dict:
    corp, per, rows, basis = with_basis("fnlttSinglAcntAll.json", a)
    want = (a.get("statement") or "all").upper()
    note = None
    if want != "ALL":
        have = sorted({r.get("sj_div") for r in rows})
        picked = [r for r in rows if r.get("sj_div") == want]
        if not picked and want == "IS" and "CIS" in have:   # 손익을 포괄손익계산서 한 장으로 공시한 회사
            want, picked = "CIS", [r for r in rows if r.get("sj_div") == "CIS"]
            note = "이 회사는 손익계산서를 포괄손익계산서 한 장으로 공시해서 CIS를 돌려준다."
        elif not picked and rows:
            note = f"{want} 표가 없다. 이 보고서에 있는 표: {', '.join(have)}"
        rows = picked
    return result(corp, statement_table(rows), basis=basis, statement=want.lower(), statement_note=note, **_pmeta(per))


ST_COLS = ("account_nm", "account_detail", "thstrm_amount", "thstrm_add_amount", "frmtrm_amount", "frmtrm_add_amount",
           "bfefrmtrm_amount")


def statement_table(rows: list[dict]) -> dict:
    """전체 재무제표는 표라서 열 이름을 한 번만 쓴다 (삼성전자 연간 기준 96KB → 약 30KB).

    표(sj_div)별로 [계정명, 세부, 당기, 당기 누적, 전기, 전기 누적, 전전기] 행을 담는다. 값이 모두 비거나 '-'인 열은 뺀다.
    account_id·ord·sj_nm은 뺀다: 계정명과 행 순서로 충분하고, 크기만 키운다.
    """
    if not rows:
        return {"rows": []}
    common = {k: rows[0].get(k) for k in ("thstrm_nm", "frmtrm_nm", "bfefrmtrm_nm", "currency")
              if rows[0].get(k) and all(r.get(k) == rows[0].get(k) for r in rows)}
    rc = {r.get("rcept_no") for r in rows}
    if len(rc) == 1 and None not in rc:
        common["source_url"] = VIEW_URL + rc.pop()
    cols = [c for c in ST_COLS if any(str(r.get(c) or "").strip() not in ("", "-") for r in rows)]
    tables: dict[str, list] = {}
    for r in rows:
        tables.setdefault(r.get("sj_div") or "?", []).append([_clean(r.get(c)) for c in cols])
    return {"common": common, "columns": cols, "rows": tables}


def report_url(corp: dict, per: dict) -> str | None:
    """그 기간 정기보고서의 원문 링크. 재무 지표 응답에는 접수번호가 없어서 공시 목록에서 찾는다.

    DART bsns_year는 보고서 기간이 끝나는 해다. 보고서명 '(YYYY.MM)'이 그 해·월인 것 가운데 가장 늦게 접수된 것
    (기재정정 포함)을 고른다. 다른 도구의 source_url도 정정본을 가리키므로 맞춘다.
    """
    if per.get("rcept_no"):
        return VIEW_URL + per["rcept_no"]
    import datetime as dt
    from dart_client import REPRT_OFFSET

    fm = int(corp.get("fiscal_month") or 12)
    mm = (fm + REPRT_OFFSET[per["reprt_code"]] - 1) % 12 + 1
    yyyy = int(per["bsns_year"])
    end = min(dt.date(yyyy + 1, mm, 28), dt.date.today())
    try:
        rows = call("list.json", corp_code=corp["corp_code"], bgn_de=f"{yyyy}{mm:02d}01",
                    end_de=end.strftime("%Y%m%d"), pblntf_ty="A", page_count=100)
    except ToolError:
        return None
    hit = [r for r in rows if f"({yyyy}.{mm:02d})" in r.get("report_nm", "")]
    return VIEW_URL + max(hit, key=lambda r: r.get("rcept_no", ""))["rcept_no"] if hit else None


def t_fin_ratios(a: dict) -> dict:
    corp = resolve_corp(a["corp"])
    per = resolve_period(corp, a.get("year"), a.get("period"))
    groups = list(RATIO_GROUP) if (a.get("group") or "all") == "all" else [a["group"]]
    out: dict[str, list] = {}
    stlm = None
    for g in groups:
        rows = call("fnlttSinglIndx.json", corp_code=corp["corp_code"], bsns_year=per["bsns_year"],
                    reprt_code=per["reprt_code"], idx_cl_code=RATIO_GROUP[g])
        stlm = stlm or next((r.get("stlm_dt") for r in rows), None)
        out[g] = [{"name": r.get("idx_nm"), "code": r.get("idx_code"), "value": _clean(r.get("idx_val"))}
                  for r in rows]
    body: dict[str, Any] = {"rows": out} if any(out.values()) else {"rows": []}
    basis = None
    if body["rows"]:
        url = report_url(corp, per)
        if url:
            body = {"common": {"source_url": url}, **body}
        # DART 지표는 연결재무제표가 있으면 연결, 없으면 별도로 계산돼 있다
        # (2026-10 실측: 카카오·삼성전자 부채비율 = 연결 계정 계산값, 경남스틸 = 별도). 주요계정 한 번으로 가린다
        try:
            acc = call("fnlttSinglAcnt.json", corp_code=corp["corp_code"], bsns_year=per["bsns_year"],
                       reprt_code=per["reprt_code"])
            basis = "연결" if any(r.get("fs_div") == "CFS" for r in acc) else "별도" if acc else None
        except ToolError:
            pass
    return result(corp, body, basis=basis, settlement_date=stlm, **_pmeta(per),
                  caution="DART가 계산해 둔 값이다. 분기·반기 보고서 값은 연초부터 그 기간 끝까지 누적 기준이고 연환산하지 않았다"
                          "(현대차 2026 반기 순이익률 5.752% = 상반기 누적 순이익 ÷ 누적 매출). 2023년 3분기 이전은 제공되지 않는다.")


def _iso_date(v: Any) -> str | None:
    """'2028년 03월 18일' → '2028-03-18'. 정렬할 수 있게 같은 행에 붙인다."""
    m = re.match(r"\s*(\d{4})\D+(\d{1,2})\D+(\d{1,2})", str(v or ""))
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None


def _blank(v: Any) -> bool:
    return str(v or "").strip() in ("", "-", "0")


def _simple(endpoint: str, total_row: bool = False, iso: str | None = None,
            drop_blank: tuple[str, ...] = ()) -> Callable[[dict], dict]:
    def run(a: dict) -> dict:
        corp, per, rows = periodic(endpoint, a)
        if drop_blank:    # 취득 방법별 빈 칸 행(현대차 2026 반기 18행 중 13행)은 읽는 쪽에 잡음일 뿐이다
            rows = [r for r in rows if not all(_blank(r.get(k)) for k in drop_blank)]
        if iso:
            for r in rows:
                r[iso + "_iso"] = _iso_date(r.get(iso))
        if total_row:     # 최대주주 표의 합계 행은 nm이 '계'이고 relate가 없다. 사람 행과 헷갈리지 않게 표시한다
            for r in rows:
                if str(r.get("nm", "")).strip() == "계":
                    r["relate"] = "합계(최대주주+특수관계인)"
        return result(corp, shape(rows), **_pmeta(per))
    return run


def _filings(endpoint: str) -> Callable[[dict], dict]:
    """수시 보고(5%·임원 소유)는 기간 인자가 없다. 최근 접수부터 limit건."""
    def run(a: dict) -> dict:
        corp = resolve_corp(a["corp"])
        rows = sorted(call(endpoint, corp_code=corp["corp_code"]), key=lambda r: (r.get("rcept_dt", ""),
                                                                                 r.get("rcept_no", "")), reverse=True)
        total = len(rows)
        limit = int(a.get("limit") or 20)
        return result(corp, shape(rows[:limit], keep_rcept=True),
                      total=total, shown=min(limit, total), order="최근 접수순")
    return run


# ── 도구 목록 ──────────────────────────────────────────────────────────────

CORP = {"type": "string", "description": "회사명·약칭·옛 이름·영문명·종목코드(6자리)·DART 고유번호(8자리) 중 무엇이든. "
                                         "예: '카카오', '하닉', '005930', '00126380'. 비상장사는 8자리 고유번호로."}
YEAR = {"type": "string", "pattern": r"^\d{4}$",
        "description": "사업연도 YYYY (DART 기준: 보고서 기간이 끝나는 해). 비우면 가장 최근 정기보고서."}
PERIOD = {"type": "string", "enum": list(PERIOD_CODE),
          "description": "Q1=1분기, H1=반기, Q3=3분기, FY=사업보고서(연간). year만 주면 FY."}
BASIS = {"type": "string", "enum": ["auto", "consolidated", "separate"], "default": "auto",
         "description": "auto=연결이 없으면 별도. consolidated=연결만, separate=별도만."}
LIMIT = {"type": "integer", "minimum": 1, "maximum": 100, "default": 20, "description": "최근 접수순으로 몇 건까지."}


def _schema(props: dict, required: tuple[str, ...] = ("corp",)) -> dict:
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


PERIODIC = {"corp": CORP, "year": YEAR, "period": PERIOD}

# (이름, 제목, 설명, 입력 스키마, 구현). 순서는 분석 흐름 그대로: 회사 → 공시 → 재무 → 지분·자본 → 사람.
TOOLS: list[tuple[str, str, str, dict, Callable[[dict], dict]]] = [
    ("corp_resolve", "회사 찾기",
     "회사명·약칭·옛 이름·종목코드를 DART 고유번호(corp_code)로 바꾼다. 상장사는 한국거래소 현재 목록과 맞물려 찾고, "
     "애매하면 추측하지 않고 후보를 돌려준다. scope=all이면 비상장·폐지 포함 DART 전체 목록에서 이름으로 찾는다. "
     "다른 도구는 corp에 이름을 바로 받으므로, 후보 확인이 필요할 때만 먼저 부르면 된다.",
     _schema({"query": {"type": "string", "description": "찾을 이름이나 코드"},
              "scope": {"type": "string", "enum": ["listed", "all"], "default": "listed",
                        "description": "listed=현재 상장사, all=DART 전체(비상장·폐지 포함)"},
              "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20,
                        "description": "scope=all일 때 최대 건수"}}, ("query",)),
     t_corp_resolve),
    ("corp_profile", "기업 개황",
     "회사명, 영문명, 대표자, 법인·사업자 등록번호, 주소, 홈페이지, 업종 코드, 설립일, 결산월.",
     _schema({"corp": CORP}), t_corp_profile),
    ("filing_search", "공시 검색",
     "기간·공시 유형·시장으로 공시 목록을 찾는다. 각 행에 DART 원문 링크(url)가 붙는다. "
     "corp를 비우면 시장 전체에서 찾으며, 이때 DART는 기간을 3개월로 제한한다.",
     _schema({"corp": CORP,
              "from": {"type": "string", "description": "시작일 YYYYMMDD (YYYY-MM-DD도 된다). 기본 to의 30일 전"},
              "to": {"type": "string", "description": "종료일 YYYYMMDD (YYYY-MM-DD도 된다). 기본 오늘"},
              "kind": {"type": "string", "enum": list(FILING_KIND),
                       "description": "periodic=정기, major=주요사항, issuance=발행, ownership=지분, other=기타, "
                                      "audit=외부감사, fund=펀드, abs=자산유동화, exchange=거래소, ftc=공정위"},
              "market": {"type": "string", "enum": list(MARKET_CODE),
                         "description": "kospi=유가증권, kosdaq=코스닥, konex=코넥스, other=기타법인"},
              "page": {"type": "integer", "minimum": 1, "default": 1},
              "size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}}, ()),
     t_filing_search),
    ("filing_latest_periodic", "최근 정기보고서",
     "가장 최근에 나온 사업·반기·분기보고서를 찾아 year·period로 돌려준다. 비12월 결산과 기재정정까지 감안한다. "
     "재무 도구들은 year를 비우면 이 규칙을 자동으로 쓴다.",
     _schema({"corp": CORP}), t_filing_latest_periodic),
    ("fin_key_accounts", "주요 재무 계정",
     "매출액, 영업이익, 당기순이익, 자산·부채·자본 총계 같은 핵심 계정만 당기·전기·전전기로. 빠른 확인용.",
     _schema({**PERIODIC, "basis": BASIS}), t_fin_key_accounts),
    ("fin_statements", "전체 재무제표",
     "재무상태표·손익계산서·포괄손익계산서·현금흐름표·자본변동표의 전체 계정. statement로 한 표만 고를 수 있다. "
     "응답은 표 형식이다: columns가 열 이름이고 rows[표]가 그 순서의 값 목록이다. 손익을 물으면 statement=IS부터.",
     _schema({**PERIODIC, "basis": BASIS,
              "statement": {"type": "string", "enum": ["all", "BS", "IS", "CIS", "CF", "SCE"], "default": "all",
                            "description": "BS=재무상태표, IS=손익, CIS=포괄손익, CF=현금흐름, SCE=자본변동"}}),
     t_fin_statements),
    ("fin_ratios", "재무 지표",
     "DART가 계산한 수익성(ROE·순이익률 등)·안정성(부채비율·유동비율 등)·성장성(매출·이익 증가율)·활동성(회전율) 지표. "
     "group을 비우면 네 묶음을 한 번에 가져온다. 2023년 3분기 보고서부터 제공된다. "
     "연결재무제표가 있는 회사는 연결, 없으면 별도 기준이며 meta.basis에 적는다.",
     _schema({**PERIODIC, "group": {"type": "string", "enum": ["all", *RATIO_GROUP], "default": "all",
                                    "description": "profitability=수익성, stability=안정성, growth=성장성, activity=활동성"}}),
     t_fin_ratios),
    ("fin_dividends", "배당",
     "주당 배당금, 배당 성향, 시가 배당률, 현금배당 총액 등 (보통주·우선주, 당기·전기·전전기).",
     _schema(PERIODIC), _simple("alotMatter.json")),
    ("share_outstanding", "발행 주식 수",
     "발행할 주식 총수, 발행 주식 총수, 자기주식 수, 유통 주식 수 (주식 종류별).",
     _schema(PERIODIC), _simple("stockTotqySttus.json")),
    ("share_top_holders", "최대주주와 특수관계인",
     "최대주주 본인과 특수관계인의 기초·기말 보유 주식 수와 지분율.",
     _schema(PERIODIC), _simple("hyslrSttus.json", total_row=True)),
    ("share_block_reports", "5% 대량보유 보고",
     "지분 5% 이상을 가진 투자자가 낸 대량보유 상황보고. 보고자, 보유 주식·비율과 증감, 보고 사유. 최근 접수순.",
     _schema({"corp": CORP, "limit": LIMIT}), _filings("majorstock.json")),
    ("share_insider_reports", "임원·주요주주 소유 보고",
     "임원과 주요주주의 특정증권 소유 상황 보고. 보고자, 직위, 보유 수량과 증감. 최근 접수순.",
     _schema({"corp": CORP, "limit": LIMIT}), _filings("elestock.json")),
    ("share_treasury", "자기주식 취득·처분",
     "자기주식의 취득 방법별 기초 수량, 취득·처분·소각, 기말 수량. 수량이 모두 비어 있는 방법 행은 뺀다(총계 행은 남는다).",
     _schema(PERIODIC), _simple("tesstkAcqsDspsSttus.json", drop_blank=("bsis_qy", "change_qy_acqs", "change_qy_dsps",
                                                                         "change_qy_incnr", "trmend_qy"))),
    ("share_capital_changes", "증자·감자 이력",
     "주식 발행(감소) 일자, 형태(유상증자·주식매수선택권 행사·소각 등), 주식 종류, 수량, 액면가와 발행 가액.",
     _schema(PERIODIC), _simple("irdsSttus.json")),
    ("people_executives", "임원",
     "임원 이름, 직위, 등기 여부(rgist_exctv_at), 상근 여부, 담당 업무, 주요 경력, 최대주주와의 관계, 재직 기간, "
     "임기 만료일(tenure_end_on, 정렬용 tenure_end_on_iso). 미등기임원은 회사마다 실린 정도가 다르다"
     "(삼성전자 2026 반기는 등기임원 8명만, 경남스틸 2025는 미등기 8명 포함).",
     _schema(PERIODIC), _simple("exctvSttus.json", iso="tenure_end_on")),
    ("people_employees", "직원",
     "사업부문·성별 직원 수(정규·계약), 평균 근속연수, 연간 급여 총액, 1인 평균 급여.",
     _schema(PERIODIC), _simple("empSttus.json")),
]
HANDLERS = {name: fn for name, _t, _d, _s, fn in TOOLS}


def tool_specs() -> list[dict]:
    return [{"name": n, "title": t, "description": d, "inputSchema": s,
             "annotations": {"title": t, "readOnlyHint": True, "openWorldHint": True}} for n, t, d, s, _ in TOOLS]


# ── 실행 ───────────────────────────────────────────────────────────────────

def _redact(text: object) -> str:
    s = str(text)
    key = getattr(_client, "api_key", None)
    if key:
        s = s.replace(key, "***")
    return re.sub(r"crtfc_key=[^&\s]+", "crtfc_key=***", s)


MAX_CHARS = 40_000   # 응답 JSON 글자 수 상한. Claude Code는 MCP 응답이 약 2만 5천 토큰을 넘으면 자른다
NARROW = {"fin_statements": "statement로 표 하나(BS·IS·CIS·CF·SCE)만 고르세요.",
          "filing_search": "size를 줄이거나 from·to·kind로 좁히세요.",
          "share_block_reports": "limit을 줄이세요.", "share_insider_reports": "limit을 줄이세요."}


def _size(body: dict) -> int:
    return len(json.dumps(body, ensure_ascii=False))


def fit(body: dict, name: str) -> dict:
    """응답이 MAX_CHARS를 넘으면 뒤쪽 행부터 덜어 내고 truncated에 남긴다. 조용히 잘리는 것보다 낫다."""
    if _size(body) <= MAX_CHARS:
        return body
    rows = body.get("rows")
    if isinstance(rows, dict):        # 표별로 나뉜 응답: 큰 표부터 줄인다
        total = {k: len(v) for k, v in rows.items()}
        while _size(body) > MAX_CHARS and any(rows.values()):
            k = max(rows, key=lambda x: len(rows[x]))
            rows[k] = rows[k][: max(len(rows[k]) * 3 // 4, len(rows[k]) - 1, 0) if len(rows[k]) > 4 else len(rows[k]) - 1]
        shown = {k: len(v) for k, v in rows.items()}
    elif isinstance(rows, list):
        total = len(rows)
        while _size(body) > MAX_CHARS and rows:
            del rows[max(len(rows) * 3 // 4, 1) if len(rows) > 4 else len(rows) - 1:]
        shown = len(rows)
    else:
        return body
    body["truncated"] = {"total": total, "shown": shown,
                         "hint": "응답이 커서 뒤쪽 행을 덜어 냈습니다. " + NARROW.get(name, "조건을 좁혀 다시 부르세요.")}
    return body


def run_tool(name: str, args: dict | None) -> tuple[dict, bool]:
    """(응답 본문, 오류 여부). 오류도 본문에 담아 돌려준다: 모델이 읽고 고쳐 부를 수 있게."""
    fn = HANDLERS.get(name)
    if fn is None:
        return {"error": f"없는 도구입니다: {name}", "tools": list(HANDLERS)}, True
    args = dict(args or {})
    required = next(s for n, _t, _d, s, _f in TOOLS if n == name)["required"]
    missing = [k for k in required if not args.get(k)]
    if missing:
        return {"error": f"필수 인자가 빠졌습니다: {', '.join(missing)}"}, True
    try:
        return fit(fn(args), name), False
    except ToolError as e:
        return {"error": str(e), **e.data}, True
    except Exception as e:   # 네트워크 등. 키는 가린다
        return {"error": f"{type(e).__name__}: {_redact(e)}"}, True


def handle(msg: dict) -> dict | None:
    """JSON-RPC 메시지 하나 → 응답 (알림이면 None)."""
    mid, method = msg.get("id"), msg.get("method")
    if mid is None:
        return None
    if method == "initialize":
        want = (msg.get("params") or {}).get("protocolVersion")
        res: dict[str, Any] = {
            "protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER,
            "instructions": "한국 DART 공시 데이터 도구. corp에 회사명을 바로 넣으면 된다. year를 비우면 최근 정기보고서 기간을 쓴다. "
                            "숫자 단위는 DART 원본(원, 주, %) 그대로다. 모든 행에 같은 값은 common에 한 번만 담고, "
                            "source_url·url은 DART 원문 링크다.",
        }
    elif method == "ping":
        res = {}
    elif method == "tools/list":
        res = {"tools": tool_specs()}
    elif method == "tools/call":
        p = msg.get("params") or {}
        body, err = run_tool(p.get("name", ""), p.get("arguments"))
        res = {"content": [{"type": "text", "text": json.dumps(body, ensure_ascii=False)}], "isError": err}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": res}


def serve() -> None:
    out = sys.stdout
    sys.stdout = sys.stderr     # 가져온 모듈이 print해도 프로토콜 스트림이 깨지지 않게
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            resp: dict | None = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            resp = handle(msg) if isinstance(msg, dict) else None
        if resp is not None:
            out.write(json.dumps(resp, ensure_ascii=False) + "\n")
            out.flush()


def main(argv: list[str]) -> int:
    if argv[:1] == ["--list"]:
        for i, (n, t, _d, s, _f) in enumerate(TOOLS, 1):
            args = ", ".join(k + ("" if k in s["required"] else "?") for k in s["properties"])
            print(f"{i:2d}. {n:<24} {t:<16} ({args})")
        print("\n?는 생략 가능. 입력 상세: --help <도구>")
        return 0
    if argv[:1] == ["--help"] and len(argv) == 2 and argv[1] in HANDLERS:
        _n, t, d, s, _f = next(x for x in TOOLS if x[0] == argv[1])
        print(f"{argv[1]} · {t}\n{d}\n")
        for k, v in s["properties"].items():
            spec = "|".join(v["enum"]) if "enum" in v else v.get("pattern") or v.get("type", "")
            print(f"  {k}{'' if k in s['required'] else '?'}: {spec}  {v.get('description', '')}".rstrip())
        return 0
    if argv[:1] == ["--call"] and len(argv) >= 2:
        body, err = run_tool(argv[1], json.loads(argv[2]) if len(argv) > 2 else {})
        print(json.dumps(body, ensure_ascii=False, indent=2))
        return 1 if err else 0
    if argv:
        print(__doc__)
        return 2
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
