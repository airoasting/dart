#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data.json 조립기 회귀 테스트. DART·주가는 흉내 내고 네트워크 없이 돈다.

    python3 -m unittest discover -s tests -v

조립 결과가 숫자 검증 게이트의 A층(산술 정합)을 그대로 통과하는지, 검증 장부의 patch가 반영되는지,
잘못된 조각이면 멈추는지를 본다.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ASSETS = Path(__file__).resolve().parent.parent / "assets"
sys.path.insert(0, str(ASSETS))
os.environ.setdefault("DART_CACHE_DIR", tempfile.mkdtemp())

import assemble_report as ar  # noqa: E402
import verify_report as vr    # noqa: E402

CORP = "00266961"   # NAVER (번들 상장 목록에 있다)
# 억원 실수 (fetch_dart 반환 형식): 당기, 전년동기
VALS = {"rev": (33888.4, 29150.6), "op": (5203.2, 5216.4), "np_total": (7042.7, 4974.1), "np_parent": (6900.0, 4900.0)}
ITEMS = [{"sj_div": "BS", "account_nm": "자산총계", "thstrm_amount": "44700000000000", "frmtrm_amount": "41100000000000"},
         {"sj_div": "BS", "account_nm": "자본총계", "thstrm_amount": "31000000000000", "frmtrm_amount": "29000000000000"}]
PX = {"date": "20261002", "close": 192200, "change_pct": 0.16, "w52_range": "181,100 ~ 304,000"}


def persona(i):
    return {"name": f"투자자{i}", "type": "t", "rating": "hold", "desc": "d", "eval": "매출 +16.2%"}


def write_parts(d: Path, **override):
    parts = {
        "A1.json": {"NEWS": [{"h": "원래 제목", "src": "한국경제", "date": "2026.08.08", "sent": "mix",
                              "url": "https://example.com/n1", "body": "본문"}]},
        "A2.json": {"ANALYSTS": [
            {"firm": "가증권", "r": "Buy", "tp": 300000, "from": 280000, "date": "2026.08.10", "note": "n", "url": "u1"},
            {"firm": "나증권", "r": "Buy", "tp": 290000, "from": None, "date": "2026.09.01", "note": "n", "url": "u2"}],
            "CONS": {"buy": 2, "hold": 0, "sell": 0}, "coverage_note": "표의 2개 증권사 기준",
            "SEGS": [{"name": "플랫폼", "sub": "s", "cat": "platform", "q25": 20000, "q26": 23000, "est": True},
                     {"name": "콘텐츠", "sub": "s", "cat": "content", "q25": 9151, "q26": 10888, "est": True}],
            "filter_cats": [["platform", "플랫폼"], ["content", "콘텐츠"]]},
        "B.json": [persona(i) for i in range(13)],
        "C.json": {"BULLS": [{"t": "a", "d": "b"}], "BEARS": [{"t": "a", "d": "b"}],
                   "CHIPS": [{"cls": "co", "dot": "var(--coral)", "txt": "매출 +16.2%"}]},
        "V1.json": {"web": [{"sec": "NEWS", "key": "https://example.com/n1", "status": "corrected",
                             "url": "https://example.com/n1", "patch": {"h": "고친 제목"}}], "claims": []},
        "V2.json": {"web": [{"sec": "ANALYSTS", "key": "가증권", "status": "corrected", "url": "u1",
                             "patch": {"tp": 310000}}], "claims": []},
    }
    parts.update(override)
    for name, body in parts.items():
        if body is not None:
            (d / name).write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


def run_build(d: Path, *extra, vals=VALS):
    out = d / "data.json"
    argv = ["build", "--corp-code", CORP, "--year", "2026", "--reprt", "11012", "--parts", str(d), "-o", str(out), *extra]
    with mock.patch.object(ar, "fetch_dart", return_value=(vals, ITEMS, [], [])), \
            mock.patch.object(ar, "get_prev_close", return_value=PX):
        ar.main(argv)
    return json.loads(out.read_text(encoding="utf-8"))


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_meta_numbers_pass_gate_arithmetic(self):
        write_parts(self.d)
        data = run_build(self.d)
        m = data["meta"]
        self.assertEqual((m["rev_val"], m["rev_sub"]), ("33,888", "2Q25 &nbsp;29,151억"))
        self.assertEqual(m["op_dir"], "down")
        self.assertEqual(m["g_net"], "+4,737억")
        self.assertEqual((m["q_cur_short"], m["nav_label"]), ("2Q26", "26 2Q 실적"))
        R, pool = vr.Report(), vr.Pool()
        vr.check_arithmetic(data, R, pool)               # 게이트 A층을 그대로 돌린다
        self.assertEqual(R.fails, [], R.fails)

    def test_ledger_patches_applied_and_merged(self):
        write_parts(self.d)
        data = run_build(self.d)
        self.assertEqual(data["js"]["NEWS"][0]["h"], "고친 제목")
        self.assertEqual(data["js"]["ANALYSTS"][0]["tp"], 310000)
        self.assertEqual(data["meta"]["tp_avg"], "300,000원")          # 패치 뒤 값으로 평균
        secs = {e["sec"] for e in data["audit"]["web"]}
        self.assertTrue({"NEWS", "ANALYSTS", "CONS", "meta"} <= secs)
        self.assertNotIn("url", data["js"]["ANALYSTS"][0])           # 화면 데이터에는 url을 싣지 않는다

    def test_unknown_previous_target_stays_null(self):
        write_parts(self.d)
        self.assertIsNone(run_build(self.d)["js"]["ANALYSTS"][1]["from"])

    def test_segment_sum_mismatch_stops(self):
        bad = {"ANALYSTS": [{"firm": "가", "r": "Buy", "tp": 1, "from": 1, "date": "d", "note": "n"}],
               "CONS": {"buy": 1, "hold": 0, "sell": 0},
               "SEGS": [{"name": "x", "sub": "", "cat": "platform", "q25": 100, "q26": 100, "est": True}]}
        write_parts(self.d, **{"A2.json": bad})
        with self.assertRaises(SystemExit):
            run_build(self.d)

    def test_persona_count_enforced(self):
        write_parts(self.d, **{"B.json": [persona(i) for i in range(12)]})
        with self.assertRaises(SystemExit):
            run_build(self.d)

    def test_missing_core_account_stops(self):
        write_parts(self.d)
        with self.assertRaises(SystemExit):
            run_build(self.d, vals={k: v for k, v in VALS.items() if k != "op"})

    def test_verification_files_optional(self):
        write_parts(self.d, **{"V1.json": None, "V2.json": None})
        data = run_build(self.d)
        self.assertEqual(data["js"]["NEWS"][0]["h"], "원래 제목")

    def test_fiscal_and_annual_labels(self):
        write_parts(self.d)
        out = self.d / "data.json"
        for argv, short in ((["--reprt", "11011", "--fiscal-month", "3"], "4Q25"), (["--scope", "annual"], "FY26")):
            with self.subTest(argv=argv):
                base = ["build", "--corp-code", CORP, "--year", "2026", "--reprt", "11012",
                        "--parts", str(self.d), "-o", str(out)]
                if "--reprt" in argv:
                    base[base.index("--reprt") + 1] = argv[argv.index("--reprt") + 1]
                    argv = [a for a in argv if a not in ("--reprt", "11011")]
                with mock.patch.object(ar, "fetch_dart", return_value=(VALS, ITEMS, [], [])), \
                        mock.patch.object(ar, "get_prev_close", return_value=PX):
                    ar.main(base + argv)
                self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["meta"]["q_cur_short"], short)


class Facts(unittest.TestCase):
    def test_facts_lines(self):
        with mock.patch.object(ar, "fetch_dart", return_value=(VALS, ITEMS, [], [])), \
                mock.patch.object(ar, "get_prev_close", return_value=PX):
            f = ar.collect(ar.argparse.Namespace(corp_code=CORP, year="2026", reprt="11012", fs_div="CFS",
                                                 scope="quarter", np_basis="total", fiscal_month=12))["facts"]
        self.assertEqual(f["매출"], "매출 29,151억 → 33,888억 (+4,737억, +16.3%)")
        self.assertIn("OPM 17.9% → 15.4%", f["영업이익"])
        self.assertEqual(f["재무상태(조)"]["자산총계"], "41.1조 → 44.7조")
        self.assertIn("192,200원 (10/2 종가, +0.16%)", f["주가"])


class PeriodAndFallback(unittest.TestCase):
    def test_period_args_from_registry(self):
        rep = {"bsns_year": "2026", "reprt_code": "11013", "period_end": "2026.06", "label": "1Q26",
               "report_nm": "분기보고서 (2026.06)", "rcept_no": "r", "rcept_dt": "d"}
        with mock.patch.object(ar.DartClient, "__init__", return_value=None), \
                mock.patch.object(ar.DartClient, "latest_periodic_report", return_value=rep) as lp:
            out = ar.period(ar.argparse.Namespace(corp_code="00136721"))      # 신영증권, 3월 결산
        self.assertEqual(out["args"], "--year 2026 --reprt 11013 --fiscal-month 3")
        self.assertEqual(lp.call_args.kwargs["fiscal_month"], 3)

    def test_consolidated_missing_falls_back_to_separate(self):
        calls = []

        def fake(src):
            calls.append(src["fs_div"])
            if src["fs_div"] == "CFS":
                raise LookupError("DART status=013 조회된 데이타가 없습니다.")
            return VALS, ITEMS, [], []
        a = ar.argparse.Namespace(corp_code=CORP, year="2026", reprt="11012", fs_div="CFS", scope="quarter",
                                  np_basis="total", fiscal_month=None)
        with mock.patch.object(ar, "fetch_dart", side_effect=fake), \
                mock.patch.object(ar, "get_prev_close", return_value=PX):
            c = ar.collect(a)
        self.assertEqual(calls, ["CFS", "OFS"])
        self.assertEqual(a.fs_div, "OFS")
        self.assertIn("(개별)", c["facts"]["기간"])

    def test_no_report_stops_with_guidance(self):
        a = ar.argparse.Namespace(corp_code=CORP, year="2026", reprt="11012", fs_div="CFS", scope="quarter",
                                  np_basis="total", fiscal_month=None)
        with mock.patch.object(ar, "fetch_dart", side_effect=LookupError("DART status=013")), \
                mock.patch.object(ar, "get_prev_close", return_value=PX):
            with self.assertRaises(SystemExit) as cm:
                ar.collect(a)
        self.assertIn("provisional.md", str(cm.exception))


class ApiKey(unittest.TestCase):
    def test_skill_root_env_is_read(self):
        """README가 안내하는 위치(스킬 루트 .env)를 모든 스크립트가 읽는다 (새 설치에서 키를 못 찾던 버그)."""
        import corp_registry as cr
        import dart_client as dc
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "assets").mkdir()
            (root / ".env").write_text("DART_API_KEY=ROOTKEY\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"DART_API_KEY": ""}), mock.patch.object(cr, "HERE", root / "assets"), \
                    mock.patch("pathlib.Path.cwd", return_value=root / "assets"):
                self.assertEqual(cr.find_api_key(), "ROOTKEY")
                self.assertEqual(dc._load_api_key(), "ROOTKEY")
                self.assertEqual(vr._load_key(), "ROOTKEY")


class PatchOrdering(unittest.TestCase):
    """새 리뷰어가 찾은 조립 버그 회귀 (patch가 계산보다 늦게 반영되던 문제 등)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_segment_patch_flows_into_delta_and_sum_check(self):
        v2 = {"web": [{"sec": "SEGS", "key": "플랫폼", "status": "corrected", "url": "u", "patch": {"q26": 23000, "q25": 20000}},
                      {"sec": "SEGS", "key": "콘텐츠", "status": "corrected", "url": "u", "patch": {"q26": 10888}}], "claims": []}
        write_parts(self.d, **{"V2.json": v2})
        data = run_build(self.d)
        self.assertEqual(data["js"]["DELTA"][-1]["d"], 33888 - 29151)
        R, pool = vr.Report(), vr.Pool()
        vr.check_arithmetic(data, R, pool)
        self.assertEqual(R.fails, [])

    def test_cons_recounted_after_opinion_patch(self):
        v2 = {"web": [{"sec": "ANALYSTS", "key": "나증권", "status": "corrected", "url": "u2", "patch": {"r": "Hold"}}], "claims": []}
        write_parts(self.d, **{"V2.json": v2})
        self.assertEqual(run_build(self.d)["js"]["CONS"], {"buy": 1, "hold": 1, "sell": 0})

    def test_missing_target_price_stops(self):
        a2 = json.loads(json.dumps({"ANALYSTS": [{"firm": "가증권", "r": "Buy", "tp": None, "from": None, "date": "d", "note": "n"}],
                                    "CONS": {"buy": 1, "hold": 0, "sell": 0},
                                    "SEGS": [{"name": "플랫폼", "sub": "", "cat": "platform", "q25": 29151, "q26": 33888, "est": True}]}))
        write_parts(self.d, **{"A2.json": a2, "V2.json": None})
        with self.assertRaises(SystemExit):
            run_build(self.d)

    def test_news_url_patch_moves_ledger_key(self):
        v1 = {"web": [{"sec": "NEWS", "key": "https://example.com/n1", "status": "corrected", "url": "https://example.com/n1",
                       "patch": {"url": "https://example.com/real"}}], "claims": []}
        write_parts(self.d, **{"V1.json": v1})
        data = run_build(self.d)
        self.assertEqual(data["js"]["NEWS"][0]["url"], "https://example.com/real")
        self.assertIn("https://example.com/real", {e["key"] for e in data["audit"]["web"] if e["sec"] == "NEWS"})

    def test_chip_dot_from_class(self):
        c = {"BULLS": [{"t": "a", "d": "b"}], "BEARS": [{"t": "a", "d": "b"}],
             "CHIPS": [{"cls": "dn", "dot": "var(--red)", "txt": "x"}]}       # 템플릿에 없는 색을 줘도
        write_parts(self.d, **{"C.json": c})
        self.assertEqual(run_build(self.d)["js"]["CHIPS"][0]["dot"], "var(--dn)")


class ZeroCoverage(unittest.TestCase):
    """증권사 보고서가 없는 중소형주도 리포트를 만든다 (신영증권 실측에서 발견)."""

    def test_empty_analysts_builds_and_passes_arithmetic(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            a2 = {"ANALYSTS": [], "SEGS": [{"name": "플랫폼", "sub": "", "cat": "platform", "q25": 29151, "q26": 33888, "est": True}],
                  "filter_cats": []}
            write_parts(d, **{"A2.json": a2, "V2.json": None})
            data = run_build(d)
        m = data["meta"]
        self.assertEqual((m["tp_avg"], m["tp_upside"], m["cons_buy"]), ("없음", "해당 없음", "0"))
        self.assertIn("커버리지 없음", m["coverage_note"])
        R, pool = vr.Report(), vr.Pool()
        vr.check_arithmetic(data, R, pool)
        self.assertEqual(R.fails, [], R.fails)


class DartText(unittest.TestCase):
    """V2가 DART 뷰어 URL을 그대로 넘겨도 접수번호를 뽑는다."""

    def test_rcept_no_from_url_and_bare(self):
        import dart_text
        self.assertEqual(dart_text.rcept_no("https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260810000423"), "20260810000423")
        self.assertEqual(dart_text.rcept_no("20260810000423"), "20260810000423")
        with self.assertRaises(SystemExit):
            dart_text.rcept_no("https://example.com")


class TemplateHasNoCompanyText(unittest.TestCase):
    """템플릿에 특정 회사 문구가 박히면 모든 리포트에 새어 나간다 (카카오 각주가 신영증권 리포트에 나왔던 회귀)."""

    def test_no_example_company_words(self):
        t = (ASSETS / "template.html").read_text(encoding="utf-8")
        for w in ("카카오", "픽코마", "톡비즈", "하이닉스", "삼성전자", "1Q26", "2Q26"):
            self.assertNotIn(w, t, w)


if __name__ == "__main__":
    unittest.main()
