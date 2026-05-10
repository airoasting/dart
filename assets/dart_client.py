"""DART Open API 클라이언트.

문서: https://opendart.fss.or.kr/guide/main.do
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://opendart.fss.or.kr/api"


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


class DartClient:
    def __init__(self, api_key: str | None = None, timeout: int = 10) -> None:
        self.api_key = api_key or _load_api_key()
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        params["crtfc_key"] = self.api_key
        resp = self.session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def list_disclosures(
        self,
        corp_code: str | None = None,
        bgn_de: str | None = None,
        end_de: str | None = None,
        page_no: int = 1,
        page_count: int = 10,
    ) -> dict[str, Any]:
        """공시검색 (list.json)."""
        params: dict[str, Any] = {"page_no": page_no, "page_count": page_count}
        if corp_code:
            params["corp_code"] = corp_code
        if bgn_de:
            params["bgn_de"] = bgn_de
        if end_de:
            params["end_de"] = end_de
        return self._get("list.json", **params)

    def company(self, corp_code: str) -> dict[str, Any]:
        """기업개황 (company.json). corp_code는 8자리."""
        return self._get("company.json", corp_code=corp_code)

    def download_corp_codes(self, dest: str | Path = "corpCode.zip") -> Path:
        """전체 기업 corp_code zip 다운로드 (corpCode.xml)."""
        url = f"{BASE_URL}/corpCode.xml"
        resp = self.session.get(url, params={"crtfc_key": self.api_key}, timeout=60)
        resp.raise_for_status()
        path = Path(dest)
        path.write_bytes(resp.content)
        return path

    def load_corp_codes(self, csv_path: str | Path = "corp_codes.csv"):
        """corp_codes.csv를 DataFrame으로 로드. 없으면 zip 받아서 생성."""
        import pandas as pd

        path = Path(csv_path)
        if not path.exists():
            self._build_corp_codes_csv(path)
        return pd.read_csv(path, dtype={"corp_code": str, "stock_code": str}).fillna("")

    def _build_corp_codes_csv(self, csv_path: Path) -> None:
        import zipfile
        import xml.etree.ElementTree as ET
        import pandas as pd

        zip_path = Path("corpCode.zip")
        if not zip_path.exists():
            self.download_corp_codes(zip_path)
        with zipfile.ZipFile(zip_path) as z, z.open("CORPCODE.xml") as f:
            root = ET.parse(f).getroot()
        rows = [
            {
                "corp_code": el.findtext("corp_code"),
                "corp_name": el.findtext("corp_name"),
                "corp_eng_name": el.findtext("corp_eng_name"),
                "stock_code": (el.findtext("stock_code") or "").strip(),
                "modify_date": el.findtext("modify_date"),
            }
            for el in root.findall("list")
        ]
        pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    def find_corp(self, keyword: str, listed_only: bool = False):
        """회사명으로 corp_code 검색. listed_only=True면 상장사만."""
        df = self.load_corp_codes()
        hit = df[df["corp_name"].str.contains(keyword, na=False)]
        if listed_only:
            hit = hit[hit["stock_code"] != ""]
        return hit[["corp_code", "corp_name", "stock_code"]].reset_index(drop=True)

    def find_corp_from_assets(self, keyword: str):
        """assets/corp_codes_listed.csv에서 상장사 검색 (네트워크 불필요)."""
        import pandas as pd

        assets_csv = Path(__file__).parent / "corp_codes_listed.csv"
        df = pd.read_csv(assets_csv, dtype={"corp_code": str, "stock_code": str}).fillna("")
        hit = df[df["corp_name"].str.contains(keyword, na=False)]
        return hit[["corp_code", "corp_name", "stock_code"]].reset_index(drop=True)

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
