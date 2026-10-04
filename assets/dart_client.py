"""DART Open API 클라이언트.

문서: https://opendart.fss.or.kr/guide/main.do
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://opendart.fss.or.kr/api"
sys.path.insert(0, str(Path(__file__).resolve().parent))   # corp_registry 동봉 모듈


def _load_api_key() -> str:
    key = os.environ.get("DART_API_KEY")
    if key:
        return key
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "DART_API_KEY":
                return v.strip()
    raise RuntimeError("DART_API_KEY가 환경변수 또는 .env 파일에 없습니다.")


RETRY_STATUS = {"020", "800"}   # 요청 제한 초과·시스템 점검: 잠깐 쉬었다 다시 부른다


class DartError(ConnectionError):
    """DART 접속 실패(재시도 후). 메시지에 API 키가 남지 않게 가린다.

    ConnectionError(OSError)라서 verify_report.py는 이것을 INCOMPLETE로 처리한다(회차 미소모).
    """


def _redact(text: object, key: str) -> str:
    s = str(text).replace(key, "***") if key else str(text)
    return re.sub(r"crtfc_key=[^&\s]+", "crtfc_key=***", s)


REPRT_OFFSET = {"11013": 3, "11012": 6, "11014": 9, "11011": 12}   # 회계연도 시작부터 기간 끝까지 개월 수
REPRT_Q = {"11013": "1Q", "11012": "2Q", "11014": "3Q", "11011": "4Q"}


def fiscal_label_year(bsns_year: str | int, reprt_code: str, fiscal_month: int = 12) -> int:
    """리포트 라벨에 쓸 회계연도(시작 연도). 12월 결산이면 bsns_year 그대로다.

    DART bsns_year는 보고서 기간 끝 월의 연도라서, 3월 결산은 한 회계연도(2025.04~2026.03)의 1~3Q가 2025,
    4Q가 2026으로 갈린다. 업계 관행대로 회계연도가 시작한 해로 묶는다: 위 예는 모두 FY25.
    """
    fm = int(fiscal_month or 12)
    pe = (fm + REPRT_OFFSET[str(reprt_code)] - 1) % 12 + 1          # 기간 끝 월
    fy_end = int(bsns_year) + (0 if pe <= fm else 1)
    return fy_end if fm == 12 else fy_end - 1


def fiscal_label(bsns_year: str | int, reprt_code: str, fiscal_month: int = 12) -> str:
    """'1Q26' 형식. 비12월 결산은 회계연도 시작 연도 기준."""
    return f"{REPRT_Q[str(reprt_code)]}{fiscal_label_year(bsns_year, reprt_code, fiscal_month) % 100:02d}"


class DartClient:
    def __init__(self, api_key: str | None = None, timeout: int = 10, retries: int = 2) -> None:
        self.api_key = api_key or _load_api_key()
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()

    def _get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        """JSON 엔드포인트 호출. status 판정은 호출자가 한다 (013 등은 정상 흐름이다).

        네트워크 오류와 status 020·800은 최대 retries번 다시 시도한다(1초, 3초).
        예외 메시지에서 crtfc_key는 가린다.
        """
        params["crtfc_key"] = self.api_key
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            if attempt:
                time.sleep(1 if attempt == 1 else 3)
            try:
                resp = self.session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, ValueError) as e:
                last = e
                continue
            if data.get("status") in RETRY_STATUS and attempt < self.retries:
                continue
            return data
        raise DartError(f"DART {endpoint} 호출 실패: {_redact(last, self.api_key)}")

    def list_disclosures(
        self,
        corp_code: str | None = None,
        bgn_de: str | None = None,
        end_de: str | None = None,
        page_no: int = 1,
        page_count: int = 10,
        pblntf_ty: str | None = None,
    ) -> dict[str, Any]:
        """공시검색 (list.json). pblntf_ty: A=정기공시, B=주요사항, I=거래소공시 등."""
        params: dict[str, Any] = {"page_no": page_no, "page_count": page_count}
        if corp_code:
            params["corp_code"] = corp_code
        if bgn_de:
            params["bgn_de"] = bgn_de
        if end_de:
            params["end_de"] = end_de
        if pblntf_ty:
            params["pblntf_ty"] = pblntf_ty
        return self._get("list.json", **params)

    def company(self, corp_code: str) -> dict[str, Any]:
        """기업개황 (company.json). corp_code는 8자리. 이름으로는 검색되지 않는다."""
        return self._get("company.json", corp_code=corp_code)

    def latest_periodic_report(self, corp_code: str, fiscal_month: int = 12, lookback_days: int = 460,
                               annual_only: bool = False) -> dict[str, Any] | None:
        """가장 최근 기간의 정기보고서(분기·반기·사업)를 찾아 재무 API 파라미터로 바꾼다.

        DART 규칙 (3월 결산 신영증권으로 실측): bsns_year = 보고서명 '(YYYY.MM)'의 YYYY.
        reprt_code는 보고서 종류로 정한다: 사업보고서→11011, 반기보고서→11012,
        분기보고서는 결산월로부터 3개월 뒤면 11013, 9개월 뒤면 11014.
        annual_only=True면 사업보고서만 본다 (코넥스: 반기를 자진 제출한 회사도 연간으로 통일).
        6개월 결산(리츠 등)은 사업보고서를 1년에 두 번 내므로 종류를 우선한다.
        [기재정정]으로 나중에 다시 낸 옛 기간 보고서에 끌려가지 않도록 접수일이 아니라 기간 끝 월로 고른다.
        """
        import datetime as _dt

        end = _dt.date.today()
        bgn = end - _dt.timedelta(days=lookback_days)
        res = self.list_disclosures(corp_code, bgn_de=bgn.strftime("%Y%m%d"), end_de=end.strftime("%Y%m%d"),
                                    pblntf_ty="A", page_count=100)
        best = None
        for it in res.get("list", []):
            m = re.search(r"(사업|반기|분기)보고서\s*\((\d{4})\.(\d{2})\)", it.get("report_nm", ""))
            if not m:
                continue
            kind, yyyy, mm = m.group(1), int(m.group(2)), int(m.group(3))
            if annual_only and kind != "사업":
                continue
            if kind == "사업":
                reprt = "11011"
            elif kind == "반기":
                reprt = "11012"
            else:
                reprt = {3: "11013", 9: "11014"}.get((mm - fiscal_month) % 12)
                if reprt is None:
                    continue    # 결산월과 맞지 않는 분기보고서 (결산월 변경 직후 등): 건너뛴다
            key = (yyyy, mm, it.get("rcept_dt", ""))
            if best is None or key > best[0]:
                best = (key, {"bsns_year": str(yyyy), "reprt_code": reprt, "period_end": f"{yyyy}.{mm:02d}",
                              "label": fiscal_label(yyyy, reprt, fiscal_month),
                              "report_nm": it["report_nm"], "rcept_no": it["rcept_no"], "rcept_dt": it["rcept_dt"]})
        return best[1] if best else None

    # ── 종목 찾기: corp_registry.py에 위임한다 (DART ∩ KRX 상장 목록, 별칭, 옛 이름, 우선주) ──

    def resolve_corp(self, query: str, verify: bool = False, refresh: bool = True) -> dict[str, Any]:
        """회사명·약칭·옛 이름·영문명·종목코드 → 상장사 하나.

        반환 status: ok(바로 진행) · confirm(1건이지만 부분일치라 확인 필요) · ambiguous(여럿) · not_found.
        verify=True면 company.json으로 corp_code와 종목코드가 같은 회사인지 한 번 더 확인한다.
        """
        import corp_registry

        res = (corp_registry.resolve_or_refresh(query, api_key=self.api_key) if refresh
               else corp_registry.resolve(query))
        if verify:
            corp_registry.apply_live_check(res, api_key=self.api_key)   # CLI --verify와 같은 상태 전환
        return res

    def download_corp_codes(self, dest: str | Path | None = None) -> Path:
        """전체 기업 corp_code zip 다운로드 (corpCode.xml). 기본 위치는 캐시 폴더."""
        import corp_registry

        path = Path(dest) if dest else corp_registry.cache_dir() / "corpCode.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            resp = self.session.get(f"{BASE_URL}/corpCode.xml", params={"crtfc_key": self.api_key}, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise DartError(_redact(e, self.api_key)) from None
        path.write_bytes(resp.content)
        return path

    def load_corp_codes(self, listed_only: bool = True):
        """상장사(기본) 또는 전체 기업 목록을 DataFrame으로. 전체 목록은 캐시에 없으면 갱신해 만든다."""
        import pandas as pd
        import corp_registry

        if listed_only:
            return pd.DataFrame(corp_registry.load().listed)
        path = corp_registry.cache_dir() / "corp_codes_all.csv"
        if not path.exists():
            corp_registry.refresh(self.api_key)
        return pd.read_csv(path, dtype=str).fillna("")

    def find_corp(self, keyword: str, listed_only: bool = True):
        """회사명으로 후보 검색 (DataFrame). 확정이 필요하면 resolve_corp를 써라.

        listed_only=True(기본)는 현재 KRX 상장사만, False는 비상장·폐지 포함 DART 전체 목록에서 찾는다.
        """
        import pandas as pd
        import corp_registry

        cols = ["corp_code", "corp_name", "stock_code"]
        if listed_only:
            res = corp_registry.resolve(keyword)
            rows = [res["corp"]] if res["corp"] and res["status"] == "ok" else res["candidates"]
            return pd.DataFrame(rows, columns=cols + ["market"]).reset_index(drop=True)
        df = self.load_corp_codes(listed_only=False)
        key = corp_registry.norm(keyword)
        hit = df[df["corp_name"].map(corp_registry.norm).str.contains(key, regex=False)]
        return hit[cols].reset_index(drop=True)

    def find_corp_from_assets(self, keyword: str):
        """번들 상장사 목록에서 검색 (네트워크 불필요). find_corp(listed_only=True)와 같다."""
        return self.find_corp(keyword, listed_only=True)

    def get_financial_statements(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = "11011",
        fs_div: str = "CFS",
    ) -> dict[str, Any]:
        """재무제표 전체 (fnlttSinglAcntAll.json).

        reprt_code: 11013=1Q, 11012=2Q반기, 11014=3Q, 11011=사업보고서(연간)
        fs_div: CFS=연결, OFS=개별
        """
        return self._get(
            "fnlttSinglAcntAll.json",
            corp_code=corp_code,
            bsns_year=bsns_year,
            reprt_code=reprt_code,
            fs_div=fs_div,
        )

    def get_financial_key(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = "11011",
        fs_div: str = "CFS",
    ) -> dict[str, Any]:
        """주요재무정보 (fnlttSinglAcnt.json) — 핵심 계정만, 빠른 조회용."""
        return self._get(
            "fnlttSinglAcnt.json",
            corp_code=corp_code,
            bsns_year=bsns_year,
            reprt_code=reprt_code,
            fs_div=fs_div,
        )

    def get_dividend(self, corp_code: str, bsns_year: str, reprt_code: str = "11011") -> dict[str, Any]:
        """배당 정보 (alotMatter.json)."""
        return self._get("alotMatter.json", corp_code=corp_code, bsns_year=bsns_year, reprt_code=reprt_code)

    def get_stock_status(self, corp_code: str, bsns_year: str, reprt_code: str = "11011") -> dict[str, Any]:
        """주식 현황 (stockTotqySttus.json)."""
        return self._get("stockTotqySttus.json", corp_code=corp_code, bsns_year=bsns_year, reprt_code=reprt_code)


if __name__ == "__main__":
    client = DartClient()
    print("[1] 최근 공시 5건 (오늘 기준)")
    today = __import__("datetime").date.today().strftime("%Y%m%d")
    res = client.list_disclosures(bgn_de=today, end_de=today, page_count=5)
    print(f"  status={res.get('status')} message={res.get('message')}")
    for item in res.get("list", [])[:5]:
        print(f"  - {item.get('corp_name')} | {item.get('report_nm')} | {item.get('rcept_dt')}")
