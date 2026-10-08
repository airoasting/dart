#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP 서버 회귀 테스트. DART는 흉내 내고 네트워크 없이 돈다.

    python3 -m unittest discover -s tests -v

도구 목록의 모양, JSON-RPC 응답, 회사·기간 해석, 연결→별도 대체, 수시 보고 정렬, 오류 응답을 본다.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
sys.path.insert(0, str(ASSETS))
os.environ.setdefault("DART_CACHE_DIR", tempfile.mkdtemp())

import mcp_server as ms  # noqa: E402

NAVER = "00266961"   # 번들 상장 목록에 있다


class FakeClient:
    """DartClient 흉내. 엔드포인트별 응답을 사전으로 받는다. fs_div가 다르면 키를 (엔드포인트, fs_div)로 둔다."""

    api_key = "SECRETKEY"

    def __init__(self, responses: dict, resolve: dict | None = None) -> None:
        self.responses = responses
        self.resolve = resolve
        self.calls: list[tuple[str, dict]] = []

    def _get(self, endpoint: str, **params):
        self.calls.append((endpoint, params))
        key = (endpoint, params.get("fs_div")) if (endpoint, params.get("fs_div")) in self.responses else endpoint
        return self.responses.get(key, {"status": "013", "message": "조회된 데이타가 없습니다."})

    def resolve_corp(self, query: str):
        return self.resolve

    def latest_periodic_report(self, corp_code: str, fiscal_month: int = 12):
        return {"bsns_year": "2026", "reprt_code": "11012", "period_end": "2026.06", "label": "2Q26",
                "report_nm": "반기보고서 (2026.06)", "rcept_no": "20260814000001", "rcept_dt": "20260814"}


def ok(rows):
    return {"status": "000", "message": "정상", "list": rows}


class ToolCatalogTest(unittest.TestCase):
    def test_sixteen_unique_tools_in_workflow_order(self):
        names = [t["name"] for t in ms.tool_specs()]
        self.assertEqual(len(names), 16)
        self.assertEqual(len(set(names)), 16)
        groups = [n.split("_")[0] for n in names]
        order = ["corp", "filing", "fin", "share", "people"]
        self.assertEqual(sorted(groups, key=order.index), groups, "묶음 순서가 회사→공시→재무→지분→사람이어야 한다")

    def test_specs_are_valid_schemas(self):
        for t in ms.tool_specs():
            s = t["inputSchema"]
            self.assertEqual(s["type"], "object")
            self.assertFalse(s["additionalProperties"])
            for r in s["required"]:
                self.assertIn(r, s["properties"], t["name"])
            self.assertTrue(t["annotations"]["readOnlyHint"])
            self.assertTrue(t["description"])


class ProtocolTest(unittest.TestCase):
    def test_initialize_negotiates_version(self):
        r = ms.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}})
        self.assertEqual(r["result"]["protocolVersion"], "2024-11-05")
        r = ms.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
        self.assertEqual(r["result"]["protocolVersion"], ms.PROTOCOLS[0])
        self.assertIn("tools", r["result"]["capabilities"])

    def test_notification_gets_no_reply_and_unknown_method_errors(self):
        self.assertIsNone(ms.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        r = ms.handle({"jsonrpc": "2.0", "id": 9, "method": "resources/list"})
        self.assertEqual(r["error"]["code"], -32601)

    def test_tools_call_wraps_errors_as_tool_results(self):
        r = ms.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                       "params": {"name": "corp_profile", "arguments": {}}})
        self.assertTrue(r["result"]["isError"])
        self.assertIn("corp", json.loads(r["result"]["content"][0]["text"])["error"])


class ShapeTest(unittest.TestCase):
    def test_hoists_common_values_and_links_source(self):
        rows = [{"rcept_no": "R1", "corp_code": NAVER, "stlm_dt": "2026-06-30", "nm": "가", "v": "1"},
                {"rcept_no": "R1", "corp_code": NAVER, "stlm_dt": "2026-06-30", "nm": "나", "v": "#########"}]
        out = ms.shape(rows)
        self.assertEqual(out["common"], {"stlm_dt": "2026-06-30", "source_url": ms.VIEW_URL + "R1"})
        self.assertEqual(out["rows"], [{"nm": "가", "v": "1"}, {"nm": "나", "v": None}])

    def test_keep_rcept_links_each_row(self):
        out = ms.shape([{"rcept_no": "A"}, {"rcept_no": "B"}], keep_rcept=True)
        self.assertEqual([r["url"] for r in out["rows"]], [ms.VIEW_URL + "A", ms.VIEW_URL + "B"])


class ToolRunTest(unittest.TestCase):
    def setUp(self):
        self._saved = ms._client

    def tearDown(self):
        ms._client = self._saved

    def use(self, fake):
        ms._client = fake
        return fake

    def test_period_rules(self):
        corp = {"corp_code": NAVER, "corp_name": "NAVER", "fiscal_month": 12}
        self.use(FakeClient({}))
        self.assertEqual(ms.resolve_period(corp, "2025", None)["reprt_code"], "11011")
        self.assertEqual(ms.resolve_period(corp, "2025", "q3")["reprt_code"], "11014")
        self.assertEqual(ms.resolve_period(corp, None, None)["period"], "H1")
        with self.assertRaises(ms.ToolError):
            ms.resolve_period(corp, None, "Q1")
        with self.assertRaises(ms.ToolError):
            ms.resolve_period(corp, "25", None)

    def test_statements_fall_back_to_separate(self):
        fake = self.use(FakeClient({("fnlttSinglAcntAll.json", "OFS"): ok([
            {"sj_div": "CIS", "account_nm": "매출액", "thstrm_amount": "100"},
            {"sj_div": "BS", "account_nm": "자산총계", "thstrm_amount": "500"}])}))
        body, err = ms.run_tool("fin_statements", {"corp": NAVER, "year": "2025", "statement": "IS"})
        self.assertFalse(err)
        self.assertEqual([c[1]["fs_div"] for c in fake.calls], ["CFS", "OFS"])
        self.assertEqual(body["meta"]["basis"], "별도")
        self.assertEqual(body["meta"]["statement"], "cis")          # IS가 없으면 CIS로 답한다
        self.assertEqual(body["rows"], {"CIS": [["매출액", "100"]]})   # 표 형식: columns 순서의 값
        self.assertEqual(body["columns"], ["account_nm", "thstrm_amount"])

    def test_key_accounts_pick_one_basis_from_one_call(self):
        fake = self.use(FakeClient({"fnlttSinglAcnt.json": ok([
            {"fs_div": "CFS", "account_nm": "매출액", "thstrm_amount": "9"},
            {"fs_div": "OFS", "account_nm": "매출액", "thstrm_amount": "5"}])}))
        body, _ = ms.run_tool("fin_key_accounts", {"corp": NAVER, "year": "2025", "basis": "separate"})
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(body["meta"]["basis"], "별도")
        self.assertEqual(body["rows"][0]["thstrm_amount"], "5")

    def test_block_reports_newest_first_with_limit(self):
        self.use(FakeClient({"majorstock.json": ok([
            {"rcept_no": "1", "rcept_dt": "2024-01-01", "repror": "옛"},
            {"rcept_no": "3", "rcept_dt": "2026-08-03", "repror": "새"},
            {"rcept_no": "2", "rcept_dt": "2025-05-05", "repror": "중"}])}))
        body, _ = ms.run_tool("share_block_reports", {"corp": NAVER, "limit": 2})
        self.assertEqual([r["repror"] for r in body["rows"]], ["새", "중"])
        self.assertEqual(body["meta"], {"total": 3, "shown": 2, "order": "최근 접수순"})

    def test_ratios_collect_all_groups(self):
        self.use(FakeClient({"fnlttSinglIndx.json": ok([
            {"idx_nm": "ROE", "idx_code": "M211550", "idx_val": "1.6", "stlm_dt": "2026-06-30"}])}))
        body, _ = ms.run_tool("fin_ratios", {"corp": NAVER})
        self.assertEqual(sorted(body["rows"]), sorted(ms.RATIO_GROUP))
        self.assertEqual(body["meta"]["settlement_date"], "2026-06-30")

    def test_ratios_link_found_from_filing_list(self):
        self.use(FakeClient({
            "fnlttSinglIndx.json": ok([{"idx_nm": "부채비율", "idx_code": "M221100", "idx_val": "39.662"}]),
            "list.json": ok([{"report_nm": "사업보고서 (2025.12)", "rcept_no": "20260309000001"},
                             {"report_nm": "[기재정정]사업보고서 (2025.12)", "rcept_no": "20260320000002"},
                             {"report_nm": "반기보고서 (2025.06)", "rcept_no": "20250814000003"}])}))
        body, _ = ms.run_tool("fin_ratios", {"corp": NAVER, "year": "2025", "group": "stability"})
        self.assertEqual(body["common"]["source_url"], ms.VIEW_URL + "20260320000002")   # 정정본

    def test_no_data_is_not_an_error(self):
        self.use(FakeClient({}))
        body, err = ms.run_tool("people_employees", {"corp": NAVER, "year": "2025"})
        self.assertFalse(err)
        self.assertEqual(body["rows"], [])
        self.assertIn("013", body["note"])

    def test_ambiguous_name_returns_candidates(self):
        self.use(FakeClient({}, resolve={"status": "ambiguous", "message": "후보가 2곳입니다.", "corp": None,
                                         "suggestions": [], "candidates": [
                                             {"corp_name": "현대자동차", "stock_code": "005380", "corp_code": "00164742"},
                                             {"corp_name": "현대모비스", "stock_code": "012330", "corp_code": "00164788"}]}))
        body, err = ms.run_tool("share_top_holders", {"corp": "현대"})
        self.assertTrue(err)
        self.assertEqual(body["status"], "ambiguous")
        self.assertEqual(len(body["candidates"]), 2)

    def test_dart_error_status_and_key_redaction(self):
        self.use(FakeClient({"company.json": {"status": "020", "message": "요청 제한을 초과하였습니다."}}))
        body, err = ms.run_tool("corp_profile", {"corp": NAVER})
        self.assertTrue(err)
        self.assertIn("020", body["error"])

        class Boom(FakeClient):
            def _get(self, endpoint, **params):
                raise RuntimeError("https://x/api?crtfc_key=SECRETKEY&a=1 failed")
        self.use(Boom({}))
        body, err = ms.run_tool("corp_profile", {"corp": NAVER})
        self.assertTrue(err)
        self.assertNotIn("SECRETKEY", body["error"])

    def test_holder_total_row_is_labelled(self):
        self.use(FakeClient({"hyslrSttus.json": ok([
            {"nm": "김범수", "relate": "본인", "trmend_posesn_stock_qota_rt": "13.27"},
            {"nm": "계", "trmend_posesn_stock_qota_rt": "23.99"}])}))
        body, _ = ms.run_tool("share_top_holders", {"corp": NAVER, "year": "2026", "period": "H1"})
        self.assertTrue(body["rows"][1]["relate"].startswith("합계"))

    def test_treasury_drops_blank_method_rows(self):
        self.use(FakeClient({"tesstkAcqsDspsSttus.json": ok([
            {"acqs_mth3": "장내직접취득", "bsis_qy": "1,648,558", "change_qy_acqs": "743,600", "trmend_qy": "2,341,700"},
            {"acqs_mth3": "공개매수", "bsis_qy": "-", "change_qy_acqs": "-", "change_qy_dsps": "-", "trmend_qy": "-"}])}))
        body, _ = ms.run_tool("share_treasury", {"corp": NAVER, "year": "2026", "period": "H1"})
        self.assertEqual(len(body["rows"]), 1)

    def test_executive_term_gets_iso_date(self):
        self.use(FakeClient({"exctvSttus.json": ok([{"nm": "가", "tenure_end_on": "2028년 03월 18일"},
                                                    {"nm": "나", "tenure_end_on": "-"}])}))
        body, _ = ms.run_tool("people_executives", {"corp": NAVER, "year": "2025"})
        self.assertEqual([r["tenure_end_on_iso"] for r in body["rows"]], ["2028-03-18", None])

    def test_filing_dates_accept_dashes(self):
        fake = self.use(FakeClient({"list.json": ok([])}))
        ms.run_tool("filing_search", {"corp": NAVER, "from": "2026-09-01", "to": "2026.10.08"})
        self.assertEqual((fake.calls[0][1]["bgn_de"], fake.calls[0][1]["end_de"]), ("20260901", "20261008"))


class StatementTableTest(unittest.TestCase):
    def test_columns_once_and_empty_columns_dropped(self):
        rows = [{"rcept_no": "R", "sj_div": "BS", "sj_nm": "재무상태표", "account_id": "x", "account_nm": "자산총계",
                 "account_detail": "-", "thstrm_nm": "제 57 기", "thstrm_amount": "10", "frmtrm_amount": "9", "ord": "1"},
                {"rcept_no": "R", "sj_div": "IS", "sj_nm": "손익계산서", "account_id": "y", "account_nm": "매출액",
                 "account_detail": "-", "thstrm_nm": "제 57 기", "thstrm_amount": "5", "frmtrm_amount": "4", "ord": "1"}]
        out = ms.statement_table(rows)
        self.assertEqual(out["columns"], ["account_nm", "thstrm_amount", "frmtrm_amount"])
        self.assertEqual(out["rows"], {"BS": [["자산총계", "10", "9"]], "IS": [["매출액", "5", "4"]]})
        self.assertEqual(out["common"], {"thstrm_nm": "제 57 기", "source_url": ms.VIEW_URL + "R"})


class FitTest(unittest.TestCase):
    def test_list_rows_trimmed_with_hint(self):
        body = {"rows": [{"x": "가" * 1000} for _ in range(100)]}
        out = ms.fit(body, "share_insider_reports")
        self.assertLessEqual(ms._size(out), ms.MAX_CHARS)
        self.assertEqual(out["truncated"]["total"], 100)
        self.assertLess(out["truncated"]["shown"], 100)
        self.assertIn("limit", out["truncated"]["hint"])

    def test_table_rows_trim_biggest_table(self):
        body = {"columns": ["a"], "rows": {"SCE": [["가" * 500]] * 200, "IS": [["매출"]] * 5}}
        out = ms.fit(body, "fin_statements")
        self.assertLessEqual(ms._size(out), ms.MAX_CHARS)
        self.assertEqual(len(out["rows"]["IS"]), 5)
        self.assertIn("statement", out["truncated"]["hint"])

    def test_small_body_untouched(self):
        body = {"rows": [{"a": 1}]}
        self.assertNotIn("truncated", ms.fit(body, "corp_profile"))


class HttpCompatTest(unittest.TestCase):
    """requests가 없는 파이썬을 흉내 내 대체품이 같은 모양으로 동작하는지 본다."""

    def load_fallback(self):
        import builtins
        import importlib
        real_import = builtins.__import__

        def no_requests(name, *a, **k):
            if name == "requests":
                raise ImportError("no requests")
            return real_import(name, *a, **k)
        sys.modules.pop("http_compat", None)
        with unittest.mock.patch("builtins.__import__", no_requests):
            mod = importlib.import_module("http_compat")
        sys.modules.pop("http_compat", None)      # 다른 테스트는 진짜 requests를 쓰게 되돌린다
        return mod.requests

    def test_fallback_shape_and_none_params(self):
        req = self.load_fallback()
        self.assertTrue(issubclass(req.RequestException, OSError))
        seen = {}

        class FakeResp:
            status = 200
            headers = type("H", (), {"get_content_charset": staticmethod(lambda: "utf-8")})()
            def read(self): return b'{"status": "000"}'
            def geturl(self): return seen["url"]
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_urlopen(r, timeout=None):
            seen["url"] = r.full_url
            return FakeResp()
        with unittest.mock.patch("urllib.request.urlopen", fake_urlopen):
            resp = req.Session().get("https://x/api/list.json", params={"a": "1", "corp_code": None}, timeout=3)
        self.assertEqual(seen["url"], "https://x/api/list.json?a=1")
        self.assertEqual(resp.json(), {"status": "000"})
        resp.raise_for_status()

    def test_fallback_network_error_is_request_exception(self):
        import urllib.error
        req = self.load_fallback()
        with unittest.mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaises(req.RequestException):
                req.get("https://x", timeout=1)


class ApiKeyLocationTest(unittest.TestCase):
    def test_plugin_install_reads_documented_env(self):
        """플러그인 캐시에서 돌 때(.env 없음)도 ~/.claude/skills/dart/.env의 키를 찾는다."""
        import corp_registry
        with tempfile.TemporaryDirectory() as t:
            plugin_assets = Path(t, "cache", "dart", "2.2.0", "assets")
            plugin_assets.mkdir(parents=True)
            env = Path(t, "home", ".claude", "skills", "dart", ".env")
            env.parent.mkdir(parents=True)
            env.write_text("DART_API_KEY='HOMEKEY'\n")
            cwd = Path(t, "elsewhere")
            cwd.mkdir()
            with unittest.mock.patch.object(corp_registry, "HERE", plugin_assets), \
                    unittest.mock.patch.dict(os.environ, {"DART_API_KEY": ""}), \
                    unittest.mock.patch("pathlib.Path.home", return_value=Path(t, "home")), \
                    unittest.mock.patch("pathlib.Path.cwd", return_value=cwd):
                self.assertEqual(corp_registry.find_api_key(), "HOMEKEY")


class CliTest(unittest.TestCase):
    def test_list_and_help(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(ms.main(["--list"]), 0)
            self.assertEqual(ms.main(["--help", "filing_search"]), 0)
        out = buf.getvalue()
        self.assertIn("filing_search", out)
        self.assertIn("corp?", out)
        self.assertIn("YYYYMMDD", out)


if __name__ == "__main__":
    unittest.main()
