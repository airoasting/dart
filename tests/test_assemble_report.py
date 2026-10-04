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


if __name__ == "__main__":
    unittest.main()
