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
        self.assertEqual(f["재무상태"]["자산총계"], "41.1조 → 44.7조")
        self.assertIn("192,200원 (10/2 종가, +0.16%)", f["주가"])

    def test_small_company_balance_sheet_in_eok(self):
        # 1조 미만이면 '0.0조'가 아니라 억으로 쓴다 (코넥스 광동헬스바이오 실측)
        self.assertEqual(ar._bs_fmt(52_900_000_000, 62_200_000_000), ["529억", "622억"])
        self.assertEqual(ar._bs_fmt(900_000_000_000, 1_100_000_000_000), ["0.9조", "1.1조"])


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
            write_parts(d, **{"A2.json": a2, "V2.json": None, "C.json": {"BULLS": [], "BEARS": [], "CHIPS": []}})
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


if __name__ == "__main__":
    unittest.main()
