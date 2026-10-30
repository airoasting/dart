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

ar.valuation = lambda *a, **k: None   # 시가총액은 DART 주식 수 API를 부른다. 테스트는 네트워크 없이 돈다

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
            "SEGS": [{"name": "플랫폼", "sub": "s", "cat": "platform", "q25": 20000, "q26": 23000, "est": True},
                     {"name": "콘텐츠", "sub": "s", "cat": "content", "q25": 9151, "q26": 10888, "est": True}],
            "filter_cats": [["platform", "플랫폼"], ["content", "콘텐츠"]]},
        "B.json": [persona(i) for i in range(13)],
        "C.json": {"HEADLINE": "매출 +16.3%로 늘었다.", "WATCH": ["다음 분기 광고 매출"],
                   "BULLS": [{"t": "a", "d": "b"}], "BEARS": [{"t": "a", "d": "b"}],
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
        self.assertEqual((m["q_cur_short"], m["nav_label"]), ("2Q26", "2Q26 실적"))
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

    def test_split_analyst_and_segment_parts(self):
        """증권사(A2a)와 부문(A2b)을 따로 조사해도 예전 A2.json과 같은 data.json이 나온다."""
        write_parts(self.d)
        legacy = run_build(self.d)
        a2 = json.loads((self.d / "A2.json").read_text(encoding="utf-8"))
        v2 = json.loads((self.d / "V2.json").read_text(encoding="utf-8"))
        for f in ("A2.json", "V2.json"):
            (self.d / f).unlink()
        write_parts(self.d, **{"A2.json": None, "V2.json": None,
                               "A2a.json": {"ANALYSTS": a2["ANALYSTS"]},
                               "A2b.json": {"SEGS": a2["SEGS"], "filter_cats": a2["filter_cats"]},
                               "V2a.json": v2, "V2b.json": {"web": [], "claims": []}})
        split = run_build(self.d)
        self.assertEqual(split["js"], legacy["js"])
        self.assertEqual(split["meta"], legacy["meta"])
        self.assertEqual(split["js"]["ANALYSTS"][0]["tp"], 310000)     # V2a의 patch가 반영된다

    def test_split_parts_need_both_halves(self):
        write_parts(self.d, **{"A2.json": None, "A2a.json": {"ANALYSTS": []}})
        with self.assertRaises(SystemExit):
            run_build(self.d)

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
        self.assertIn("영업이익률 17.9% → 15.4%", f["영업이익"])
        self.assertEqual(f["재무상태 (2025.12말 → 2026.06말)"]["자산총계"], "41.1조 → 44.7조")
        self.assertIn("192,200원 (10/2 종가, +0.16%)", f["주가"])

    def test_small_company_balance_sheet_in_eok(self):
        # 1조 미만이면 '0.0조'가 아니라 억으로 쓴다 (코넥스 광동헬스바이오 실측)
        self.assertEqual(ar._bs_fmt(52_900_000_000, 62_200_000_000), ["529억", "622억"])
        self.assertEqual(ar._bs_fmt(900_000_000_000, 1_100_000_000_000), ["0.9조", "1.1조"])


class PricePin(unittest.TestCase):
    """오늘 행은 빼고(장중·NXT로 바뀐다), facts가 받은 종가를 build가 그대로 쓴다."""
    ROWS = [("20261027", 29700, 30100, 29350), ("20261028", 29900, 30650, 29800), ("20261029", 29200, 29850, 29050)]

    def test_intraday_today_row_dropped(self):
        import price
        kst = price.KST
        at = lambda h, m: price.datetime.datetime(2026, 10, 29, h, m, tzinfo=kst)
        self.assertEqual(price._settled(self.ROWS, at(10, 30))[-1][0], "20261028")
        self.assertEqual(price._settled(self.ROWS, at(21, 0))[-1][0], "20261028")   # 마감 뒤에도 NXT로 바뀐다
        nxt = price.datetime.datetime(2026, 10, 30, 10, 0, tzinfo=kst)   # 다음 날 장중: 어제 행은 확정
        self.assertEqual(price._settled(self.ROWS, nxt)[-1][0], "20261029")
        with mock.patch.object(price, "_naver_daily", return_value=list(self.ROWS)):
            px = price.get_prev_close("035720", now=at(10, 30))
        self.assertEqual((px["date"], px["close"], px["change_pct"]), ("20261028", 29900, 0.67))

    def test_build_reuses_facts_price(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            write_parts(d)
            argv = ["--corp-code", CORP, "--year", "2026", "--reprt", "11012", "--parts", str(d)]
            later = {**PX, "date": "20261005", "close": 200000}
            with mock.patch.object(ar, "fetch_dart", return_value=(VALS, ITEMS, [], [])), \
                    mock.patch.object(ar, "get_prev_close", return_value=PX), \
                    mock.patch("sys.stdout", new=__import__("io").StringIO()):
                ar.main(["facts", *argv])
            self.assertEqual(json.loads((d / ar.PRICE_PIN).read_text())["close"], PX["close"])
            with mock.patch.object(ar, "fetch_dart", return_value=(VALS, ITEMS, [], [])), \
                    mock.patch.object(ar, "get_prev_close", return_value=later) as g:
                ar.main(["build", *argv, "-o", str(d / "data.json")])
            g.assert_not_called()                       # 날짜가 바뀌어도 facts 값 그대로
            meta = json.loads((d / "data.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["js"]["CURR"], PX["close"])
            self.assertIn("(10/2 종가)", meta["meta"]["tp_cur"])
            with mock.patch.object(ar, "fetch_dart", return_value=(VALS, ITEMS, [], [])), \
                    mock.patch.object(ar, "get_prev_close", return_value=later), \
                    mock.patch("sys.stdout", new=__import__("io").StringIO()):
                ar.main(["facts", *argv])                # 새 facts는 언제나 새로 받는다
            self.assertEqual(json.loads((d / ar.PRICE_PIN).read_text())["close"], 200000)

    def test_stale_or_other_stock_pin_ignored(self):
        with tempfile.TemporaryDirectory() as t:
            pin = Path(t) / ar.PRICE_PIN
            pin.write_text(json.dumps({**PX, "code": "035720", "saved": "2026-01-01"}))
            with mock.patch.object(ar, "get_prev_close", return_value=PX) as g, \
                    mock.patch("sys.stderr", new=__import__("io").StringIO()):
                ar._price("035720", t, fresh=False)
                ar._price("000660", t, fresh=False)
            self.assertEqual(g.call_count, 2)


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
        self.assertEqual(calls[:2], ["CFS", "OFS"])   # 그 뒤는 직전 분기 조회(같은 OFS)
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
        c = {"HEADLINE": "h", "BULLS": [{"t": "a", "d": "b"}], "BEARS": [{"t": "a", "d": "b"}],
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

    def test_no_particle_after_name_token(self):
        # '{{name}}을'은 받침 없는 회사(SK하이닉스, 카카오)에서 틀린다. 조사가 필요 없는 문장으로 쓴다
        import re
        t = (ASSETS / "template.html").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"\}\}[은는이가을를과와]", t), [])


class SmallAndLossMaking(unittest.TestCase):
    """소형주(억 반올림이 마진을 흔든다)와 적자 회사도 조립 결과가 게이트 A층을 통과한다 (최종 리뷰에서 발견)."""

    def check(self, vals, q25, q26):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            a2 = {"ANALYSTS": [], "SEGS": [{"name": "본업", "sub": "", "cat": "other", "q25": q25, "q26": q26, "est": True}],
                  "filter_cats": []}
            write_parts(d, **{"A2.json": a2, "V2.json": None, "C.json": {"HEADLINE": "적자가 이어졌다.", "BULLS": [], "BEARS": [], "CHIPS": []}})
            data = run_build(d, vals=vals)
        R, pool = vr.Report(), vr.Pool()
        vr.check_arithmetic(data, R, pool)
        self.assertEqual(R.fails, [], R.fails)
        return data

    def test_operating_loss_negative_margin(self):
        m = self.check({"rev": (100.4, 98.6), "op": (-3.3, 1.0), "np_total": (-5.2, 0.4), "np_parent": (-5.2, 0.4)},
                       99, 100)["meta"]
        self.assertIn("-3.3%", m["op_sub"])

    def test_small_company_margin_rounding(self):
        # 영업이익 4.6억 → 표기 5억이지만 OPM은 원값 4.58% → 4.6%. 반올림한 억으로 다시 계산하면 5.0%가 되어 틀렸다
        self.check({"rev": (100.4, 100.2), "op": (4.6, 4.4), "np_total": (3.4, 3.6), "np_parent": (3.4, 3.6)}, 100, 100)

    def test_small_segment_gap_goes_to_adjustment_row(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            a2 = {"ANALYSTS": [], "filter_cats": [],
                  "SEGS": [{"name": "플랫폼", "sub": "", "cat": "platform", "q25": 20000, "q26": 23000, "est": False},
                           {"name": "콘텐츠", "sub": "", "cat": "content", "q25": 9150, "q26": 10887, "est": False}]}
            write_parts(d, **{"A2.json": a2, "V2.json": None})
            data = run_build(d)
        adj = [s for s in data["js"]["SEGS"] if s["name"] == "연결조정"]
        self.assertEqual((adj[0]["q25"], adj[0]["q26"], adj[0]["est"]), (1, 1, True))
        R, pool = vr.Report(), vr.Pool()
        vr.check_arithmetic(data, R, pool)
        self.assertEqual(R.fails, [], R.fails)


class PickQuarter(unittest.TestCase):
    """사용자가 말한 분기 → DART 사업연도. 결산월이 12월이 아니면 '뒤 분기면 전년' 규칙이 틀린다."""

    def test_december(self):
        self.assertEqual(ar.pick_quarter("1", 12, "2026.06"), (2026, "11013"))
        self.assertEqual(ar.pick_quarter("3", 12, "2026.06"), (2025, "11014"))
        self.assertEqual(ar.pick_quarter("4", 12, "2026.06"), (2025, "11011"))
        self.assertEqual(ar.pick_quarter("3", 12, fiscal_year=2025), (2025, "11014"))

    def test_march_fiscal_year(self):
        # 신영증권: 최근 보고서 1Q26(2026.06). 3분기는 2025.12 보고서, 4분기는 2026.03 사업보고서
        self.assertEqual(ar.pick_quarter("3", 3, "2026.06"), (2025, "11014"))
        self.assertEqual(ar.pick_quarter("4", 3, "2026.06"), (2026, "11011"))
        self.assertEqual(ar.pick_quarter("2", 3, "2026.06"), (2025, "11012"))
        self.assertEqual(ar.pick_quarter("1", 3, fiscal_year=2025), (2025, "11013"))
        self.assertEqual(ar.pick_quarter("4", 3, fiscal_year=2025), (2026, "11011"))

    def test_june_fiscal_year(self):
        self.assertEqual(ar.pick_quarter("3", 6, fiscal_year=2025), (2026, "11014"))   # 2026.03
        self.assertEqual(ar.pick_quarter("2", 6, fiscal_year=2025), (2025, "11012"))   # 2025.12


class AccountNames(unittest.TestCase):
    """증권사 보고서는 'III. 영업이익'처럼 번호를 붙이고 IFRS 표준 id를 쓴다 (신영증권 3Q25에서 영업이익을 못 찾았다)."""

    def test_numbered_names(self):
        for raw in ("III. 영업이익", "Ⅲ.영업이익", "1. 영업이익", "(1) 영업이익", "가. 영업이익", "영업이익"):
            self.assertEqual(vr.acc_name(raw), "영업이익", raw)
        self.assertEqual(vr.acc_name("매출액"), "매출액")

    def test_ifrs_operating_id(self):
        it = {"sj_div": "CIS", "account_id": "ifrs-full_ProfitLossFromOperatingActivities", "account_nm": "III. 영업이익"}
        self.assertIs(vr._find([it], "op"), it)


class SegmentSubNumbers(unittest.TestCase):
    """부문 설명(sub)은 화면에 나온다. 원천에 없는 숫자가 있으면 게이트가 잡는다 (광동헬스바이오 실측에서 발견)."""

    def ledger_fails(self, sub, claims=()):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            a2 = {"ANALYSTS": [], "filter_cats": [],
                  "SEGS": [{"name": "본업", "sub": sub, "cat": "other", "q25": 29151, "q26": 33888, "est": True}]}
            write_parts(d, **{"A2.json": a2, "V2.json": {"web": [], "claims": list(claims)}})
            data = run_build(d)
        R, pool = vr.Report(), vr.Pool()
        vr.check_arithmetic(data, R, pool)
        vr.check_ledger(data, R, pool, [], {})          # 증권사 0곳이라 목표가 없음
        return [f for f in R.fails if "SEGS.sub" in f.get("item", str(f))]

    def test_unverified_number_in_sub_fails(self):
        self.assertTrue(self.ledger_fails("제품 667억 포함"))

    def test_no_number_or_claimed_number_passes(self):
        self.assertFalse(self.ledger_fails("단일 사업부문"))
        self.assertFalse(self.ledger_fails("제품 667억 포함", [{"text": "667억", "url": "u", "status": "confirmed"}]))


class TurnLabels(unittest.TestCase):
    """적자가 낀 증감은 %가 아니라 흑자 전환·적자 축소로 쓴다 (광동헬스바이오 -10억 → 9억이 '+190.3%'로 나왔다)."""

    def test_labels(self):
        self.assertEqual(vr.turn_label(9, -10), "흑자 전환")
        self.assertEqual(vr.turn_label(-5, 3), "적자 전환")
        self.assertEqual(vr.turn_label(-6, -20), "적자 축소")
        self.assertEqual(vr.turn_label(-30, -20), "적자 확대")
        self.assertIsNone(vr.turn_label(10, 5))

    def test_meta_uses_label_and_passes_gate(self):
        m = SmallAndLossMaking.check(self, {"rev": (670.2, 655.1), "op": (8.6, -9.8), "np_total": (-6.4, -19.7),
                                            "np_parent": (-6.4, -19.7)}, 655, 670)["meta"]
        self.assertIn("흑자 전환", m["op_yoy"])
        self.assertIn("적자 축소", m["np_yoy"])
        self.assertNotIn("%", m["op_yoy"])
        self.assertEqual(m["g_dn"], "0억")


class FiscalPeriodNote(unittest.TestCase):
    """결산월이 12월이 아니면 기간 문구를 스크립트가 만든다 (--period-note를 손으로 넣던 단계를 없앴다)."""

    def test_notes(self):
        f = ar.fiscal_period_note
        self.assertEqual(f("1Q", 2025, 3, False), "FY25 1Q (2025.04~06)")
        self.assertEqual(f("4Q", 2025, 3, False), "FY25 4Q (2026.01~03)")
        self.assertEqual(f("4Q", 2025, 3, True), "FY25 (2025.04~2026.03)")
        self.assertEqual(f("2Q", 2025, 6, False), "FY25 2Q (2025.10~12)")
        self.assertIsNone(f("1Q", 2026, 12, False))


REVIEW_OK = {"scene": "투자위원회 5분 전, PM이 안건에 올릴지 정한다",
             "reviews": [{"role": "GOLD", "score": 8.5, "comment": "c", "fix": "f"},
                         {"role": "RED", "score": 9, "comment": "매출 +16.3%에서 나온 결론", "fix": "f"},
                         {"role": "SILVER", "score": 7.5, "comment": "c", "fix": "f"}]}


class ExpertReview(unittest.TestCase):
    """맨 아래 전문가 평가(RED·SILVER·GOLD, 10점 만점). 참고용이지만 형식과 문장 속 숫자는 게이트가 본다."""

    def build(self, review):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_parts(d, **{"R.json": review})
            return run_build(d)

    def test_review_assembled_in_role_order(self):
        js = self.build(REVIEW_OK)["js"]
        self.assertEqual([r["role"] for r in js["REVIEW"]["reviews"]], ["RED", "SILVER", "GOLD"])

    def test_first_assembly_without_review_then_gate_fails(self):
        data = self.build(None)
        self.assertIsNone(data["js"]["REVIEW"])
        self.assertTrue(vr.review_problems(data["js"]["REVIEW"]))

    def test_bad_review_stops_assembly(self):
        bad = {"scene": "s", "reviews": [{"role": "RED", "score": 8.3, "comment": "c", "fix": "f"}]}
        with self.assertRaises(SystemExit):
            self.build(bad)

    def test_numbers_in_review_are_checked(self):
        data = self.build({**REVIEW_OK, "reviews": REVIEW_OK["reviews"][:2] +
                           [{"role": "SILVER", "score": 7.5, "comment": "점유율 37.5%로 보인다", "fix": "f"}]})
        R, pool = vr.Report(), vr.Pool()
        vr.check_arithmetic(data, R, pool)
        vr.check_ledger(data, R, pool, [], {})
        fails = " ".join(str(f) for f in R.fails)
        self.assertIn("37.5%", fails)
        self.assertNotIn("16.3%", fails)          # facts에 있는 숫자는 통과


# 카카오 2Q26 실측 모양: 중단영업으로 순이익이 급감했고, 작년 보고서의 전년 숫자는 재작성 전 값이다
def _it(sj, aid, nm, cur, prv, prv_q=None):
    return {"sj_div": sj, "account_id": aid, "account_nm": nm, "thstrm_amount": str(cur),
            "frmtrm_amount": str(prv), "frmtrm_q_amount": "" if prv_q is None else str(prv_q)}


E = 100_000_000
BRIDGE_ITEMS = ITEMS + [
    _it("CIS", "ifrs-full_ProfitLossBeforeTax", "법인세비용차감전순이익", 3638 * E, 0, 2399 * E),
    _it("CIS", "ifrs-full_IncomeTaxExpenseContinuingOperations", "법인세비용", 1679 * E, 0, 232 * E),
    _it("CIS", "ifrs-full_ProfitLossFromContinuingOperations", "계속영업당기순이익", 1959 * E, 0, 2167 * E),
    _it("CIS", "ifrs-full_ProfitLossFromDiscontinuedOperations", "중단영업당기순이익", -1779 * E, 0, -449 * E),
    _it("CF", "ifrs-full_CashFlowsFromUsedInInvestingActivities", "투자활동현금흐름", 15575 * E, ""),
    _it("CF", "ifrs-full_ProceedsFromSalesOfFinancialAssetsClassifiedAsInvestingActivities", "금융자산의 처분", 20862 * E, ""),
]
PREV = [_it("CIS", "dart_OperatingIncomeLoss", "영업이익", 4000 * E, 0)]    # 처음 발표한 전년 영업이익 4,000억


class FactsBridge(unittest.TestCase):
    """순이익 급감의 원인이 공시 숫자에 있으면 facts가 넘긴다 (카카오 2Q26: B·C가 '원인 확인 필요'로 남겼다)."""

    def facts(self):
        with mock.patch.object(ar, "fetch_dart", return_value=(VALS, BRIDGE_ITEMS, [], PREV)), \
                mock.patch.object(ar, "get_prev_close", return_value=PX):
            return ar.collect(ar.argparse.Namespace(corp_code=CORP, year="2026", reprt="11012", fs_div="CFS",
                                                    scope="quarter", np_basis="total", fiscal_month=12))

    def test_bridge_cash_restatement_lines(self):
        c = self.facts()
        f = c["facts"]
        self.assertIn("중단영업이익 -449억 → -1,779억", f["순이익 구성"])
        self.assertTrue(any(x.startswith("순이익 증감 +2,069억 가운데 중단영업이익 증감 -1,330억") for x in f["순이익 구성"]))
        self.assertIn("투자활동 1.6조 (가장 큰 항목: 금융자산의 처분 2.1조)", f["현금흐름 (2026.01~2026.06 누적)"])
        self.assertIn("처음 발표한 전년 4,000억", f["전년 수치 재작성"][0])
        self.assertEqual(ar._np_bridge_text(c["bridge"]), "계속영업 1,959억 · 중단영업 -1,779억")

    def test_period_bounds(self):
        self.assertEqual(ar.period_bounds("2026", "11012", 12), ((2026, 1), (2025, 12), (2026, 6)))
        self.assertEqual(ar.period_bounds("2025", "11014", 3), ((2025, 4), (2025, 3), (2025, 12)))   # 3월 결산 3Q
        self.assertEqual(ar.period_bounds("2026", "11011", 3), ((2025, 4), (2025, 3), (2026, 3)))


class GateTightening(unittest.TestCase):
    """게이트가 통과시킨 실측 결함: 범위 앞 숫자(29,100 ~ 69,700원), 다른 계정의 숫자, 추정 부문 숫자."""

    def ledger_fails(self, text, segs=None):
        data = {"meta": {}, "js": {"BULLS": [{"t": "t", "d": text}], "SEGS": segs or [], "TOT25": 0, "TOT26": 0,
                                   "DELTA": []}, "audit": {"web": []}}
        R, pool = vr.Report(), vr.Pool()
        pool.add_won(29050, 69700)
        pool.add_eok(126000, 277000, 1959)
        pool.add_lab("부채", 126000)
        pool.add_lab("자산", 277000)
        pool.add_lab("순이익", 1959)
        pool.add_lab("영업이익", 2770)
        for sg in segs or []:
            if not sg.get("est"):
                pool.add_eok(sg["q26"])
        vr.check_ledger(data, R, pool, [], {})
        return " ".join(str(f) for f in R.fails if "BULLS" in str(f))

    def test_range_lower_bound_is_checked(self):
        self.assertIn("29,100", self.ledger_fails("52주 29,100 ~ 69,700원의 하단"))
        self.assertEqual(self.ledger_fails("52주 29,050 ~ 69,700원의 하단"), "")

    def test_number_must_belong_to_its_label(self):
        self.assertIn("'부채' 계정 값이 아니다", self.ledger_fails("부채총계는 27.7조다"))
        self.assertEqual(self.ledger_fails("자산총계 27.7조, 부채총계 12.6조"), "")
        self.assertEqual(self.ledger_fails("계속영업이익 1,959억"), "")     # 영업이익 라벨로 보지 않는다

    def test_estimated_segment_is_not_evidence(self):
        self.assertIn("3,333억", self.ledger_fails("플랫폼 3,333억", [{"name": "플랫폼", "q25": 1, "q26": 3333, "est": True}]))

    def test_label_of(self):
        self.assertEqual(vr.labels_of("계속영업당기순이익", "ifrs-full_ProfitLossFromContinuingOperations"), {"계속영업"})
        self.assertEqual(vr.labels_of("현금및현금성자산", "ifrs-full_CashAndCashEquivalents"), {"현금", "자산"})
        self.assertEqual(vr.labels_of("영업수익", "ifrs-full_Revenue"), {"매출"})
        self.assertEqual(vr.labels_of("영업이익"), {"영업이익"})                       # id 없는 소형사는 합계 이름으로
        self.assertEqual(vr.labels_of("매출원가", "ifrs-full_CostOfSales"), set())       # 합계 계정만
        self.assertEqual(vr.labels_of("자본금", "ifrs-full_IssuedCapital"), set())


class AnalystFlowAndReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_coverage_note_shows_flow(self):
        write_parts(self.d)
        note = run_build(self.d)["meta"]["coverage_note"]
        self.assertIn("보고서 2026.08.10~2026.09.01", note)
        self.assertIn("상향 1", note)                       # 280,000 → 310,000(patch)
        self.assertIn("직전 목표가 없음 1", note)

    def test_headline_required(self):
        write_parts(self.d, **{"C.json": {"BULLS": [], "BEARS": [], "CHIPS": []}})
        with self.assertRaises(SystemExit):
            run_build(self.d)

    def test_stale_review_flagged(self):
        import os, time
        write_parts(self.d, **{"R.json": REVIEW_OK})
        old = time.time() - 60
        os.utime(self.d / "R.json", (old, old))
        with mock.patch("sys.stderr", new=__import__("io").StringIO()):
            self.assertTrue(run_build(self.d)["js"]["REVIEW"]["stale"])


class GateDirectionAndLabels(unittest.TestCase):
    """RED 2차 실측: 방향이 뒤집힌 문장, 다른 계정의 %, 라벨에서 먼 숫자, 출처 없는 기사 숫자가 통과했다."""

    def fails(self, text):
        data = {"meta": {}, "js": {"BULLS": [{"t": "t", "d": text}], "SEGS": [], "TOT25": 0, "TOT26": 0, "DELTA": [],
                                   "ANALYSTS": [{"firm": "한국투자증권", "r": "Buy", "tp": 1, "note": "3분기 영업이익 2,246억 추정"}]},
                "audit": {"web": [{"sec": "ANALYSTS", "key": "한국투자증권", "status": "confirmed", "url": "u"}]}}
        R, pool = vr.Report(), vr.Pool()
        pool.add_eok(2770, 2039, 731, 20985, 180, 1718, -1538, 82000, 64000, 3600, 1679, 3638)
        pool.add_pct(9.4, 35.9, -89.5, 13.2, 10.6)
        pool.add_pp(2.6)
        pool.add_lab("매출", 20985, 19175, 1810)
        pool.add_lab("영업이익", 2770, 2039, 731)
        pool.add_lab("순이익", 180, 1718, -1538)
        pool.add_lab("현금", 82000, 64000, 3600)
        pool.add_lab("법인세", 1679, 232)
        pool.add_lab("세전이익", 3638, 2399)
        pool.add_plab("매출", 9.4)
        pool.add_plab("영업이익", 35.9, 13.2, 10.6, 2.6)
        pool.add_plab("순이익", -89.5)
        pool.orig.append(49.0)
        vr.check_ledger(data, R, pool, [], {})
        return " ".join(str(f) for f in R.fails if "BULLS" in str(f))

    def test_reversed_direction_fails(self):
        for t in ("영업이익은 -35.9% 줄었다", "순이익은 +1,538억 늘었다", "현금 3,600억 감소"):
            with self.subTest(t=t):
                self.assertIn("부호", self.fails(t))

    def test_level_with_direction_passes(self):
        for t in ("순이익은 180억으로 줄었다", "순이익 -1,538억", "영업이익 +35.9%", "영업이익률 +2.6%p 올랐다"):
            with self.subTest(t=t):
                self.assertEqual(self.fails(t), "")

    def test_percent_must_belong_to_its_label(self):
        for t in ("매출은 +35.9% 늘었다", "영업이익률 9.4%"):
            with self.subTest(t=t):
                self.assertIn("계정 값이 아니다", self.fails(t))

    def test_label_reaches_across_the_sentence(self):
        self.assertIn("'매출' 계정", self.fails("매출은 광고와 커머스 회복에 힘입어 2,770억 늘었다"))
        self.assertEqual(self.fails("순이익은 중단영업 손실이 커져 180억에 그쳤다"), "")   # 마디 안 라벨 하나에 맞으면 된다
        self.assertIn("'법인세' 계정", self.fails("법인세 3,638억"))
        self.assertEqual(self.fails("매출이 늘었다. 영업이익은 2,770억이다"), "")   # 문장이 바뀌면 라벨도 바뀐다

    def test_originally_reported_growth_needs_saying_so(self):
        self.assertIn("처음 발표", self.fails("영업이익 +49.0%"))
        self.assertEqual(self.fails("처음 발표한 전년과 견주면 영업이익 +49.0%다"), "")

    def test_korean_mixed_won(self):
        self.assertEqual([x[1] for x in vr.claim_tokens("삼성증권은 3만5000원을 제시했다")], [35000])
        self.assertEqual([x[1] for x in vr.claim_tokens("목표가 4만4,000원")], [44000])

    def test_broker_number_needs_source(self):
        self.assertIn("출처", self.fails("3분기 2,246억이 기준선이다"))
        self.assertEqual(self.fails("한국투자증권은 3분기 2,246억을 예상한다"), "")


class GateRound3(unittest.TestCase):
    """RED 3차 실측 반례: 'A에서 B로' 방향, 부사 낀 방향어, 문장 밖 출처, 약어 라벨, 기간 혼동, 모르는 단위."""

    def fails(self, text):
        data = {"meta": {}, "js": {"BULLS": [{"t": "t", "d": text}], "SEGS": [], "TOT25": 0, "TOT26": 0, "DELTA": [],
                                   "ANALYSTS": [{"firm": "한국투자증권", "r": "Buy", "tp": 1, "note": "3분기 영업이익 2,246억 추정, 시장 예상 2,522억"}]},
                "audit": {"web": [{"sec": "ANALYSTS", "key": "한국투자증권", "status": "confirmed", "url": "u"}]}}
        R, pool = vr.Report(), vr.Pool()
        pool.add_eok(20985, 19175, 1810, 2770, 2039, 731, 180, 1718, -1538, 1612, 163)
        pool.add_pct(9.4, 35.9, -89.5, 13.2, 10.6)
        pool.qoq.extend([8.1, 31.0])
        pool.add_pp(2.6)
        pool.pairs.extend([(19175, 20985), (2039, 2770), (1718, 180), (10.6, 13.2)])
        pool.add_lab("매출", 20985, 19175, 1810)
        pool.add_lab("영업이익", 2770, 2039, 731)
        pool.add_lab("순이익", 180, 1718, -1538, 1612, 163)
        pool.add_plab("매출", 9.4, 8.1)
        pool.add_plab("영업이익", 35.9, 13.2, 10.6, 2.6, 31.0)
        pool.add_plab("법인세", 9.7, 46.1)
        vr.check_ledger(data, R, pool, [], {})
        return " ".join(str(f) for f in R.fails if "BULLS" in str(f))

    def test_should_fail(self):
        for t in ("매출은 2조985억에서 1조9175억으로 줄었다", "순이익은 1,718억에서 180억으로 늘었다",
                  "영업이익은 2,039억에서 2,770억으로 감소했다", "영업이익률은 13.2%에서 10.6%로 상승했다",
                  "영업이익은 35.9%나 줄었다", "영업이익이 35.9% 급감했다", "영업이익은 (+731억) 감소했다",
                  "2분기 순이익은 2,522억원으로 시장 예상을 웃돌았다", "영업이익은 2,246억 늘었다는 전망이다",
                  "영업익은 1,810억 늘었다", "전년보다 1,810억 늘어난 영업이익", "법인세는 35.9% 늘었다",
                  "영업이익은 전년 동기 대비 31.0% 증가했다", "매출은 직전 분기 대비 9.4% 늘었다",
                  "영업이익은 3,000백만원 늘었다"):
            with self.subTest(t=t):
                self.assertNotEqual(self.fails(t), "")

    def test_should_pass(self):
        for t in ("영업이익은 2,039억에서 2,770억으로 늘었다", "순이익은 1,718억에서 180억으로 줄었다",
                  "영업이익은 직전 분기 대비 31.0% 늘었다", "매출은 전년 대비 +9.4%다",
                  "한국투자증권은 3분기 영업이익 2,246억을 추정했다", "영업이익률은 +2.6%p 개선됐다",
                  "731억 줄어든 것은 아니다"):
            with self.subTest(t=t):
                self.assertEqual(self.fails(t), "")


class CashFlowAndScope(unittest.TestCase):
    """SILVER 3차: 재무활동 가장 큰 항목이 dart_ id 줄을 놓쳤고, 연결 제외로 준 차입금을 상환으로 읽었다."""

    def cf(self, ordn, aid, nm, amt):
        return {"sj_div": "CF", "ord": str(ordn), "account_id": aid, "account_nm": nm, "thstrm_amount": str(amt)}

    def test_sections_by_order_and_borrowing(self):
        items = [self.cf(9, "ifrs-full_CashFlowsFromUsedInFinancingActivities", "재무활동현금흐름", -1459 * E),
                 self.cf(10, "dart_PaymentsOfFinanceLeaseLiabilitiesClassifiedAsFinancingActivities", "리스부채의 원금지급", 1391 * E),
                 self.cf(13, "dart_ProceedsFromShortTermBorrowings", "단기차입금의 차입", 3990 * E),
                 self.cf(15, "dart_RepaymentsOfShortTermBorrowings", "단기차입금의 상환", 3437 * E),
                 self.cf(20, "ifrs-full_CashFlowsFromUsedInInvestingActivities", "투자활동현금흐름", 15575 * E),
                 self.cf(25, "ifrs-full_CashFlowsFromLosingControlOfSubsidiariesOrOtherBusinessesClassifiedAsInvestingActivities",
                         "종속기업 처분 및 연결범위변동으로 인한 순현금흐름", -1546 * E)]
        out = ar.cash_flow(items)
        self.assertIn("재무활동 -1,459억 (가장 큰 항목: 단기차입금의 차입 3,990억)", out)
        self.assertIn("차입금 차입 3,990억, 상환 3,437억", out)
        notes = ar.scope_notes(items, None)
        self.assertTrue(notes and "연결 범위가 바뀌었다" in notes[0] and "상환·개선" in notes[0])

    def test_no_scope_change_no_note(self):
        self.assertIsNone(ar.scope_notes([self.cf(9, "ifrs-full_CashFlowsFromUsedInFinancingActivities", "재무활동", 1)], None))


if __name__ == "__main__":
    unittest.main()
