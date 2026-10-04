#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""종목 찾기 회귀 테스트. 네트워크 없이 번들 목록으로 돈다.

    python3 -m unittest discover -s tests -v

번들을 --refresh --bundle로 갱신한 뒤에는 반드시 다시 돌린다. 사명 변경·상장폐지로 기대값이 깨지면
테스트를 고치기 전에 그 변화가 맞는지 먼저 확인한다.
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

import corp_registry as cr  # noqa: E402

# 캐시가 테스트 결과를 바꾸지 않게 빈 폴더를 캐시로 쓴다
_TMP_CACHE = tempfile.mkdtemp()
os.environ["DART_CACHE_DIR"] = _TMP_CACHE
REG = cr.load()


def r(q: str) -> dict:
    return cr.resolve(q, REG)


class ResolveConfirmed(unittest.TestCase):
    """바로 진행해도 되는 경우: status=ok, 기대한 종목코드."""

    CASES = {
        # 이전 버전이 틀리던 것
        "현대차": "005380",          # 부분일치로는 현대차증권(001500) 1건 → 그대로 진행되던 버그
        "네이버": "035420",          # 정식명이 NAVER라 0건이던 것
        "삼성물산": "028260",        # 합병 전 000830(폐지)과 둘이 걸리던 것
        "SK": "034730",              # 옛 SK(003600, 폐지)와 둘이 걸리던 것
        "카카오": "035720",          # 정확히 일치하는데도 카카오뱅크·페이 등 5개를 되묻던 것
        # 종목코드 표기
        "005930": "005930", "A005930": "005930", "005930.KS": "005930", " 005930 ": "005930",
        "0035S0": "0035S0", "0035s0": "0035S0",   # 영문이 섞인 신규 종목코드
        # 우선주 → 보통주
        "005935": "005930", "삼성전자우": "005930", "현대차2우B": "005380",
        # corp_code
        "00258801": "035720",
        # 한글 표기 ↔ 영문 약자
        "엘지에너지솔루션": "373220", "엘지전자": "066570", "에스케이하이닉스": "000660",
        "KT": "030200", "KT&G": "033780", "LS일렉트릭": "010120", "포스코": "005490", "POSCO": "005490",
        # 영문명
        "Samsung Electronics": "005930", "SK hynix": "000660", "LG Energy Solution": "373220",
        "LS ELECTRIC": "010120",
        # 별칭
        "하이닉스": "000660", "삼전": "005930", "롯데지주": "004990",
        # 실사용 약칭 (GOLD 리뷰에서 막혔던 것)
        "하닉": "000660", "현차": "005380", "엘엔솔": "373220", "LGES": "373220",
        "셀트": "068270", "삼디": "006400", "엘화": "051910", "LG생건": "051900", "SK바사": "302440",
        "SK이노": "096770", "HD현대일렉": "267260", "엘디": "034220", "에이치엘비": "028300",
        # 옛 이름 (별칭 표)
        "쌍용차": "003620", "포스코케미칼": "003670", "제일모직": "028260", "다음카카오": "035720",
        "LG상사": "001120", "삼성엔지니어링": "028050", "미래에셋대우": "006800",
        # 3차: GOLD 신규 입력에서 막혔던 것
        "현모": "012330", "카겜": "293490", "삼중": "010140", "현중": "329180", "롯케": "011170",
        "KOGAS": "036460", "KEPCO": "015760", "삼생": "032830", "금호석화": "011780", "NH증권": "005940",
        "DB손보": "005830", "GC녹십자": "006280", "NCSOFT": "036570", "하이닉스반도체": "000660",
        "현대전자": "000660", "LG텔레콤": "032640", "한국담배인삼공사": "033780", "한진중공업": "097230",
        "티웨이항공": "091810", "현대상선": "011200", "빅히트": "352820", "CJ오쇼핑": "035760",
        # 영문 정식명은 묻지 않는다 (2차 RED: 과잉 질문 회귀)
        "Kakao Corp.": "035720", "Hyundai Motor Company": "005380", "Celltrion, Inc.": "068270",
        "Kakao": "035720", "Celltrion": "068270", "KB Financial": "105560",
        # 덧붙인 말·코드
        "삼성전자 주가": "005930", "현대차 실적": "005380", "SK하이닉스 3분기 실적": "000660",
        "삼전 2분기": "005930", "삼성전자 005930": "005930", "현대차 25년 3분기": "005380",
        "LG Corp.": "003550", "SK Inc.": "034730", "KT CORPORATION": "030200",
        "(005930)": "005930", "００５９３０": "005930", "005930삼성전자": "005930",
        # 5차: 증권사 리포트·뉴스 제목식 표기 (GOLD 5차)
        "삼성전자(005930)": "005930", "삼성전자(005930.KS)": "005930", "LG에너지솔루션(373220 KS)": "373220",
        "에코프로비엠(247540 KQ)": "247540", "현대차 (005380)": "005380", "삼성전자 [005930]": "005930",
        "삼성전자 KS": "005930", "삼성重": "010140", "현대車": "005380", "두산重": "034020",
        "케뱅": "279570", "현로": "064350", "YG플러스": "037270", "효성TNC": "298020", "JR글로벌리츠": "",
        "KB34호스팩": "0209J0", "하나스팩36호": "0101C0",
        # 4차: 최근 사명 변경·시총 101~300위 약칭 (GOLD 3차)
        "휠라홀딩스": "081660", "HSD엔진": "082740", "DGB금융지주": "139130", "일진머티리얼즈": "020150",
        "이베스트투자증권": "078020", "STX중공업": "071970", "보령제약": "003850",
        "레고켐바이오": "141080", "동부제철": "016380", "현대건설기계": "267270",
        "DGB": "139130", "두산엔진": "082740",
        "씨윈": "112610", "현백": "069960", "스드": "253450", "한난": "071320", "ABL바이오": "298380", "한콜": "161890",
        # 거래소 접두어
        "KRX:005930": "005930", "KOSDAQ: 247540": "247540", "한전": "015760", "한국전력": "015760",
        "엔씨소프트": "036570", "LIG넥스원": "079550", "대우조선해양": "042660",
        # 옛 회사명 (갱신 때 자동으로 쌓인다)
        "한글과컴퓨터": "030520",
        # 공백·(주) 표기
        "(주)카카오": "035720", "카카오 ": "035720", "주식회사 카카오": "035720",
        # 정확한 이름은 부분일치 별칭에 끌려가지 않는다
        "현대차증권": "001500",
    }

    def test_cases(self):
        jr = next(x["stock_code"] for x in REG.listed if x["corp_name"] == "제이알글로벌리츠")
        for q, code in self.CASES.items():
            code = code or jr
            with self.subTest(q=q):
                res = r(q)
                self.assertEqual(res["status"], "ok", res["message"])
                self.assertEqual(res["corp"]["stock_code"], code)


class ResolveNeedsUser(unittest.TestCase):
    def test_partial_single_hit_is_confirm_not_ok(self):
        """부분일치는 1건이어도 사용자 확인을 받는다 (현대차→현대차증권 유형의 오인 방지)."""
        res = r("한올바이오파")
        self.assertEqual(res["status"], "confirm")
        self.assertEqual(res["corp"]["stock_code"], "009420")

    def test_name_that_is_also_anothers_nickname_asks(self):
        """'모비스'는 코스닥 모비스의 정식명이자 현대모비스의 약칭이다. 묻지 않고 고르면 안 된다."""
        res = r("모비스")
        self.assertEqual(res["status"], "ambiguous")
        self.assertEqual({c["stock_code"] for c in res["candidates"]}, {"250060", "012330"})

    def test_english_group_name_asks(self):
        for q in ("Hyundai", "Lotte"):
            with self.subTest(q=q):
                self.assertEqual(r(q)["status"], "ambiguous")

    def test_group_word_asks_with_holding_and_affiliates(self):
        for q, code in (("LG그룹", "003550"), ("SK그룹", "034730"), ("삼성그룹", "005930"), ("롯데그룹", "004990")):
            with self.subTest(q=q):
                res = r(q)
                self.assertEqual(res["status"], "ambiguous")
                self.assertIn(code, {c["stock_code"] for c in res["candidates"]})

    def test_zero_stripped_code_confirms(self):
        res = r("5930")     # 엑셀이 앞자리 0을 지운 형태
        self.assertEqual((res["status"], res["corp"]["stock_code"]), ("confirm", "005930"))

    def test_merged_company_confirms_successor(self):
        for q, code in (("셀트리온헬스케어", "068270"), ("GS홈쇼핑", "007070"), ("HD현대미포", "329180"),
                        ("메리츠증권", "138040"), ("CJ E&M", "035760")):
            with self.subTest(q=q):
                res = r(q)
                self.assertEqual((res["status"], res["corp"]["stock_code"]), ("confirm", code))
                self.assertRegex(res["message"], "합병|완전자회사")

    def test_name_code_conflict_asks(self):
        res = r("현대차 005930")
        self.assertEqual(res["status"], "ambiguous")
        self.assertEqual({c["stock_code"] for c in res["candidates"]}, {"005380", "005930"})

    def test_typo_promoted_to_confirm(self):
        for q, code in (("삼송전자", "005930"), ("셀트리언", "068270"), ("두산에너빌러티", "034020")):
            with self.subTest(q=q):
                res = r(q)
                self.assertEqual((res["status"], res["corp"]["stock_code"]), ("confirm", code))

    def test_unlisted_famous_company(self):
        res = r("토스")
        self.assertEqual((res["status"], res["match"]), ("not_found", "unlisted"))
        res = r("카카오엔터테인먼트")
        self.assertEqual(res["match"], "unlisted")
        self.assertEqual([x["stock_code"] for x in res["suggestions"]], ["035720"])
        self.assertIn("관련 상장사의 리포트는 만들 수 있으니", res["message"])

    def test_short_query_no_mid_word_match(self):
        self.assertEqual(r("토스")["status"], "not_found")     # 비스토스·와토스코리아로 묻지 않는다

    def test_candidates_put_well_known_first_and_say_truncated(self):
        for q, first in (("삼성", "005930"), ("현대", "005380")):
            with self.subTest(q=q):
                res = r(q)
                self.assertEqual(res["status"], "ambiguous")
                self.assertEqual(res["candidates"][0]["stock_code"], first)
                self.assertGreater(res["total_candidates"], len(res["candidates"]))
                self.assertIn("구체적으로", res["message"])

    def test_ambiguous_lists_candidates_ranked(self):
        res = r("카카")
        self.assertEqual(res["status"], "ambiguous")
        names = [c["corp_name"] for c in res["candidates"]]
        self.assertIn("카카오", names)
        self.assertEqual(names[0], "카카오")      # 짧고 유가 시장이 먼저

    def test_spac_ranked_last_strict(self):
        res = r("키움")
        kinds = [cr.corp_kind(c) for c in res["candidates"]]
        self.assertEqual(kinds, sorted(kinds, key=lambda k: k != "normal"))

    def test_spac_ranked_last(self):
        res = r("미래에셋")
        if res["status"] == "ambiguous":
            spac = [i for i, c in enumerate(res["candidates"]) if "스팩" in c["corp_name"] or "기업인수목적" in c["corp_name"]]
            normal = [i for i, c in enumerate(res["candidates"]) if i not in spac]
            if spac and normal:
                self.assertLess(max(normal), min(spac))


class ResolveNotFound(unittest.TestCase):
    def test_dissolved_wording_not_alarming(self):
        """KIND '해산 사유 발생'을 그대로 옮기면 회사가 망한 것처럼 읽힌다 (BLUE 4차)."""
        row = next(x for x in REG.delisted if "해산" in x.get("delist_reason", "") and cr.norm(x["corp_name"]) not in
                   {cr.norm(a["alias"]) for a in REG.aliases})
        res = r(row["stock_code"])
        self.assertIn("흡수합병·파산·청산 등", res["message"])
        self.assertEqual(res["suggestions"], [])            # 이름 비슷한 엉뚱한 회사를 권하지 않는다 (BLUE 5차)
        self.assertNotIn("합병하거나", r("한진해운")["message"])   # 파산한 회사에 합병을 전제하지 않는다 (SILVER 5차)
        self.assertRegex(res["message"], r"\d{4}년 \d{1,2}월 \d{1,2}일")

    def test_candidates_show_alias_former_names(self):
        res = r("티웨이")
        tri = next(c for c in res["candidates"] if c["stock_code"] == "091810")
        self.assertIn("티웨이항공", tri["former_names"])
        self.assertEqual(tri["display"], "트리니티항공(091810, 코스피) (옛 이름: 티웨이항공)")
        hold = next(c for c in res["candidates"] if c["stock_code"] == "004870")
        self.assertNotIn("옛 이름", hold["display"])

    def test_hangul_spelled_acronyms(self):
        for q, code in (("에이치케이이노엔", "195940"), ("엔에이치엔케이씨피", "060250"), ("서부티앤디", "006730")):
            with self.subTest(q=q):
                res = r(q)
                self.assertEqual((res["status"], res["corp"]["stock_code"]), ("ok", code))

    def test_typo_never_crosses_latin_or_first_sound(self):
        self.assertNotEqual((r("JYP엔터테인먼츠")["corp"] or {}).get("stock_code"), "122870")

    def test_english_two_words_not_sent_to_group_company(self):
        """'Hanwha Life'가 한화로 가던 회귀 (RED 5차)."""
        for q, code in (("Hanwha Life", "088350"),):
            with self.subTest(q=q):
                res = r(q)
                self.assertIn(code, {c["stock_code"] for c in res["candidates"]} | ({res["corp"]["stock_code"]} if res["corp"] else set()))
        for q in ("Hyundai Oilbank", "Doosan Infracore"):
            with self.subTest(q=q):
                res = r(q)
                self.assertFalse(res["status"] == "confirm" and res["match"] == "eng_name_prefix", res["message"])

    def test_english_name_longer_than_registered(self):
        res = r("Daewoong Pharmaceutical")
        self.assertEqual((res["status"], res["corp"]["stock_code"]), ("confirm", "069620"))

    def test_group_alias_lists_real_affiliates(self):
        """'현대차그룹'에 기아·현대모비스가 빠지면 안 된다 (RED 4차)."""
        res = r("현대차그룹")
        codes = {c["stock_code"] for c in res["candidates"]}
        self.assertEqual(res["status"], "ambiguous")
        self.assertTrue({"005380", "000270", "012330"} <= codes)
        self.assertTrue({"003490", "020560"} <= {c["stock_code"] for c in r("한진그룹")["candidates"]})

    def test_delisted_code_uses_merger_alias(self):
        """코드로 들어와도 합병 매핑을 탄다 (SILVER 6차: 010620 HD현대미포, 042670 HD현대인프라코어)."""
        for q, code in (("010620", "329180"), ("042670", "267270")):
            with self.subTest(q=q):
                res = r(q)
                self.assertEqual((res["status"], res["corp"]["stock_code"]), ("confirm", code))
                self.assertNotIn("청산", res["message"])

    def test_hanja_and_spac_brand(self):
        self.assertEqual(r("한미藥")["corp"]["stock_code"], "128940")
        self.assertEqual(r("韓電")["corp"]["stock_code"], "015760")
        res = r("KB스팩")
        self.assertEqual(res["status"], "ambiguous")
        self.assertTrue(all(cr.corp_kind(c) == "spac" for c in res["candidates"]))

    def test_conversational_and_multiple(self):
        for q, code in (("삼성전자 실적 어때?", "005930"), ("하이닉스 리포트 뽑아줘", "000660"), ("/dart 삼성전자", "005930"),
                        ("삼성전자 2025.3Q", "005930"), ("HD현대일렉 1H26", "267260"), ("XKRX:005930", "005930"),
                        ("00066O", "000660"), ("삼바 실적 좀 보여줘", "207940")):
            with self.subTest(q=q):
                res = r(q)
                self.assertEqual((res["status"], res["corp"]["stock_code"]), ("ok", code))
        res = r("삼성전자랑 하이닉스")
        self.assertEqual((res["status"], res["match"]), ("ambiguous", "multiple"))
        self.assertEqual([c["stock_code"] for c in res["candidates"]], ["005930", "000660"])

    def test_typo_with_latin_prefixed_name(self):
        res = r("하이닉쓰")          # 정답이 SK로 시작해도 첫 한글 초성으로 비교한다 (BLUE 5차 퇴보)
        self.assertEqual((res["status"], res["corp"]["stock_code"]), ("confirm", "000660"))

    def test_group_message_josa(self):
        self.assertIn("'삼성'으로 시작하는", r("삼성그룹")["message"])

    def test_group_puts_holding_first(self):
        for q, code in (("LG그룹", "003550"), ("SK그룹", "034730"), ("롯데그룹", "004990")):
            with self.subTest(q=q):
                self.assertEqual(r(q)["candidates"][0]["stock_code"], code)

    def test_latin_acronym_not_typo_promoted(self):
        self.assertNotEqual(r("DGBX")["status"], "confirm")     # DB 등으로 오타 질문하지 않는다

    def test_brand_confirms(self):
        res = r("휠라")
        self.assertEqual((res["status"], res["corp"]["stock_code"]), ("confirm", "081660"))

    def test_delisted_explained(self):
        res = r("수성웹툰")
        self.assertEqual(res["status"], "not_found")
        self.assertEqual(res["match"], "delisted")
        self.assertIn("상장폐지됐습니다(사유:", res["message"])
        self.assertIn("상장사만 만들 수 있습니다", res["message"])

    def test_delisted_code_explained(self):
        res = r("000830")      # 옛 삼성물산
        self.assertEqual(res["status"], "not_found")
        self.assertEqual(res["match"], "delisted")

    def test_typo_suggests(self):
        res = r("삼성전ㅈ")          # 확신할 만큼 비슷하지 않으면 제안만 한다
        self.assertEqual(res["status"], "not_found")
        self.assertEqual(res["suggestions"][0]["corp_name"], "삼성전자")

    def test_empty(self):
        for q in ("  ", "(주)", "주식회사"):
            with self.subTest(q=q):
                self.assertEqual(r(q)["status"], "not_found")

    def test_refresh_failure_backs_off(self):
        """오프라인이면 한 번 실패한 뒤 6시간은 네트워크를 다시 기다리지 않는다."""
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"DART_CACHE_DIR": d}), \
                mock.patch.object(cr, "refresh", side_effect=RuntimeError("offline")) as rf:
            first = cr.resolve_or_refresh("없는회사이름xyz", api_key="k")
            second = cr.resolve_or_refresh("없는회사이름xyz", api_key="k")
        self.assertEqual(rf.call_count, 1)
        self.assertTrue(any("받지 못해" in n for n in first["notes"]))
        self.assertTrue(any("최근 목록 갱신이 실패" in n for n in second["agent"]))

    def test_refresh_success_cools_down(self):
        """방금 갱신한 캐시가 있으면 못 찾는 이름이 와도 다시 받지 않는다."""
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"DART_CACHE_DIR": d}):
            meta = dict(REG.meta, generated_at=cr.dt.datetime.now().astimezone().isoformat(timespec="seconds"))
            cr._write_csv(Path(d) / "corp_codes_listed.csv", REG.listed, cr.LISTED_COLS)
            cr._write_csv(Path(d) / "corp_codes_delisted.csv", REG.delisted, cr.DELISTED_COLS)
            (Path(d) / "corp_codes_meta.json").write_text(json.dumps(meta), encoding="utf-8")
            with mock.patch.object(cr, "refresh") as rf:
                cr.resolve_or_refresh("없는회사이름xyz", api_key="k")
            rf.assert_not_called()


class ReviewRegressions(unittest.TestCase):
    """독립 리뷰에서 나온 재현 사례."""

    def test_holdings_query_not_confirmed_as_operating_company(self):
        for q in ("Celltrion Holdings", "Cosmax Holdings", "Hyundai Motor Group", "Kakao Holdings"):
            with self.subTest(q=q):
                self.assertNotEqual(r(q)["status"], "ok")

    def test_typo_codes_not_treated_as_preferred(self):
        for q in ("005931", "000661"):
            with self.subTest(q=q):
                self.assertEqual(r(q)["status"], "not_found")

    def test_k_suffix_preferred_code(self):
        res = r("00499K")       # 롯데지주우
        self.assertEqual((res["status"], res["corp"]["stock_code"]), ("ok", "004990"))

    def test_prefix_words_with_space_before_transliteration(self):
        for q, code in (("(주) 엘지전자", "066570"), ("주식회사 에스케이하이닉스", "000660"), ("㈜ 케이티앤지", "033780")):
            with self.subTest(q=q):
                res = r(q)
                self.assertEqual((res["status"], res["corp"]["stock_code"]), ("ok", code))

    def test_risky_nicknames_ask(self):
        for q in ("닉스", "카이", "토스"):
            with self.subTest(q=q):
                self.assertNotEqual(r(q)["status"], "ok")

    def test_verify_live_outage_is_unknown_not_mismatch(self):
        corp = r("카카오")["corp"]
        for status, want in (("020", None), ("800", None), ("013", False)):
            resp = mock.Mock(json=mock.Mock(return_value={"status": status, "message": "x"}))
            with self.subTest(status=status), mock.patch("requests.get", return_value=resp):
                self.assertIs(cr.verify_live(corp, api_key="k")["ok"], want)

    def test_every_listed_company_resolves_to_itself(self):
        """상장사 전체를 이름·종목코드·corp_code로 넣어 자기 자신이 ok로 나오는지 (리뷰어 전수 점검의 상설화)."""
        contested = {cr.norm(a["alias"]) for a in REG.aliases}   # 다른 회사의 약칭이기도 한 이름은 묻는 게 맞다
        bad = []
        for x in REG.listed:
            for q in (x["corp_name"], x["stock_code"], x["corp_code"]):
                res = r(q)
                if q == x["corp_name"] and cr.norm(q) in contested:
                    ok = res["status"] == "ambiguous" and x["corp_code"] in {c["corp_code"] for c in res["candidates"]}
                else:
                    ok = res["status"] == "ok" and res["corp"]["corp_code"] == x["corp_code"]
                if not ok:
                    bad.append((q, res["status"]))
        self.assertEqual(bad, [])


class Notes(unittest.TestCase):
    def test_non_december_fiscal_year(self):
        row = next(x for x in REG.listed if x["fiscal_month"] not in ("", "12") and cr.corp_kind(x) == "normal")
        res = r(row["stock_code"])
        self.assertTrue(any("결산 법인입니다" in n for n in res["notes"]))
        self.assertTrue(any("assemble_report.py period" in a and "--fiscal-month" in a for a in res["agent"]))

    def test_reit_spac_konex(self):
        reit = next(x for x in REG.listed if x["corp_name"].endswith("리츠"))
        spac = next(x for x in REG.listed if "스팩" in x["corp_name"])
        konex = next(x for x in REG.listed if x["market"] == "코넥스" and cr.corp_kind(x) == "normal")
        res = r(reit["stock_code"])
        self.assertEqual(res["corp"]["kind"], "reit")
        self.assertIn("만들 수 없습니다", res["message"])           # "찾았습니다" 뒤에 뒤집지 않는다 (BLUE 2차)
        self.assertTrue(any("멈춘다" in a for a in res["agent"]))
        for name in ("맥쿼리인프라", "맵스리얼티", "KB발해인프라"):
            self.assertEqual(r(name)["corp"]["kind"], "fund")
        self.assertTrue(any("스팩" in n for n in r(spac["stock_code"])["notes"]))
        self.assertTrue(any("period" in a and "--scope annual" in a for a in r(konex["stock_code"])["agent"]))

    def test_user_text_is_polite_and_command_free(self):
        """사용자에게 가는 문장은 ~니다/~요/? 로 끝나고 명령어·API 용어가 없다 (BLUE 리뷰)."""
        qs = ["현대차", "카카", "삼성전쟈", "카카오엠", "005935", "Celltrion Holdings", "삼성", "5930",
              "셀트리온헬스케어", "쌍용차", "모비스", "없는회사이름xyz", "(주)", "000830", "토스", "신한알파리츠",
              "카카오엔터테인먼트", "현대차 005930", "삼송전자", "메리츠화재", "Hyundai"]
        old = cr.Registry(REG.listed, REG.delisted, REG.aliases, {"generated_at": "2020-01-01T00:00:00+09:00"}, "bundle")
        for q in qs:
            for res in (r(q), cr.resolve(q, old)):
                for text in [res["message"], *res["notes"]]:
                    with self.subTest(q=q, text=text):
                        self.assertRegex(text.rstrip(), r"(니다|요|\?|\))\.?$")
                        self.assertNotRegex(text, r"python3|--refresh|corp_code|reprt|list\.json|이\(가\)|\(으\)")

    def test_preferred_note(self):
        self.assertTrue(any("우선주" in n for n in r("005935")["notes"]))

    def test_stale_warning(self):
        old = cr.Registry(REG.listed, REG.delisted, REG.aliases, {"generated_at": "2020-01-01T00:00:00+09:00"}, "bundle")
        res = cr.resolve("카카오", old)
        self.assertTrue(any("기준이라" in n for n in res["notes"]))
        self.assertTrue(any("--refresh" in a for a in res["agent"]))


class BundleIntegrity(unittest.TestCase):
    def test_meta_matches_files(self):
        self.assertEqual(REG.meta["counts"]["listed"], len(REG.listed))
        self.assertEqual(REG.meta["counts"]["delisted"], len(REG.delisted))

    def test_unique_keys(self):
        self.assertEqual(len({x["stock_code"] for x in REG.listed}), len(REG.listed))
        self.assertEqual(len({x["corp_code"] for x in REG.listed}), len(REG.listed))

    def test_no_listed_in_delisted(self):
        self.assertFalse({x["stock_code"] for x in REG.listed} & {x["stock_code"] for x in REG.delisted})

    def test_every_row_has_market_and_codes(self):
        for x in REG.listed:
            self.assertRegex(x["corp_code"], r"^\d{8}$")
            self.assertRegex(x["stock_code"], r"^[0-9][0-9A-Z]{5}$")
            self.assertIn(x["market"], cr.MARKET_RANK)

    def test_alias_kinds(self):
        self.assertTrue(all(a.get("kind") in ("nickname", "former", "merged", "unlisted", "brand", "group") for a in REG.aliases))

    def test_aliases_valid(self):
        self.assertEqual(cr.check_aliases(REG.listed, REG.aliases), [])

    def test_aliases_unique(self):
        keys = [(cr.norm(a["alias"]), a["stock_code"]) for a in REG.aliases]
        self.assertEqual(len(keys), len(set(keys)), "같은 별칭·같은 회사 행이 두 번 있다")

    def test_contested_aliases_ask(self):
        """같은 말을 두 회사가 나눠 쓰면 묻는다 (SILVER 3차: 한화테크윈·티웨이·엔솔·현대중공업)."""
        for q, codes in (("한화테크윈", {"012450", "489790"}), ("티웨이", {"091810", "004870"}),
                         ("엔솔", {"373220", "140610"}), ("현대중공업", {"329180", "009540"}),
                         ("롯데제과", {"280360", "004990"}), ("만도", {"204320", "060980"})):
            with self.subTest(q=q):
                res = r(q)
                self.assertEqual(res["status"], "ambiguous")
                self.assertEqual({c["stock_code"] for c in res["candidates"]}, codes)


class Josa(unittest.TestCase):
    def test_josa(self):
        for word, pair, want in (("셀트리온", "이/가", "이"), ("삼성전자", "이/가", "가"), ("LG", "이/가", "가"),
                                 ("HMM", "이/가", "이"), ("NAVER", "을/를", "를"), ("S-Oil", "으로/로", "로"),
                                 ("카카오", "으로/로", "로"), ("한컴", "으로/로", "으로"), ("JYP Ent.", "은/는", "는"),
                                 ("SK", "은/는", "는"), ("KT&G", "을/를", "를"), ("삼성물산", "으로/로", "으로"),
                                 ("Coupang", "은/는", "은"), ("SIMPAC", "이/가", "이"), ("SOOP", "이/가", "이"),
                                 ("APR", "은/는", "은"), ("HLB", "이/가", "가"), ("F&F", "을/를", "를"),
                                 ("RFHIC", "이/가", "가"), ("EDGC", "이/가", "가"), ("iMBC", "이/가", "가"),
                                 ("NAVER", "이/가", "가"), ("KRAFTON", "이/가", "이"), ("Hyundai Oilbank", "은/는", "는")):
            with self.subTest(word=word, pair=pair):
                self.assertEqual(cr.josa(word, pair), want)


class Normalize(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(cr.norm("엘지에너지솔루션"), cr.norm("LG에너지솔루션"))
        self.assertEqual(cr.norm("KT&G"), cr.norm("케이티앤지"))
        self.assertEqual(cr.norm("(주) 카카오"), cr.norm("카카오"))
        self.assertEqual(cr.norm("ＮＡＶＥＲ"), cr.norm("naver"))   # 전각

    def test_stock_code_parse(self):
        self.assertEqual(cr.parse_stock_code("a005930"), "005930")
        self.assertEqual(cr.parse_stock_code("005930.KQ"), "005930")
        self.assertIsNone(cr.parse_stock_code("NAVER"))
        self.assertIsNone(cr.parse_stock_code("카카오"))
        self.assertEqual(cr.common_of("005935"), "005930")
        self.assertIsNone(cr.common_of("005930"))


class RefreshLogic(unittest.TestCase):
    """build()와 갱신 방어 로직. 네트워크는 흉내 낸다."""

    DART = [
        {"corp_code": "00000001", "corp_name": "새이름", "corp_eng_name": "New", "stock_code": "111110", "modify_date": "20260901"},
        {"corp_code": "00000002", "corp_name": "폐지사", "corp_eng_name": "", "stock_code": "222220", "modify_date": "20200101"},
        {"corp_code": "00000003", "corp_name": "비상장", "corp_eng_name": "", "stock_code": "", "modify_date": "20200101"},
    ]
    KRX = [{"stock_code": "111110", "name": "새이름", "market": "코스닥", "sector": "x", "listed_date": "2020-01-01",
            "fiscal_month": "12"}]

    def test_build_splits_and_tracks_renames(self):
        prev = [{"corp_code": "00000001", "corp_name": "옛이름", "former_names": "더옛이름"}]
        listed, delisted, meta = cr.build(self.DART, self.KRX, prev)
        self.assertEqual([x["stock_code"] for x in listed], ["111110"])
        self.assertEqual([x["stock_code"] for x in delisted], ["222220"])
        self.assertEqual(listed[0]["former_names"].split("|"), ["더옛이름", "옛이름"])
        self.assertEqual(meta["counts"]["listed"], 1)

    def test_mcap_rank_kept_when_fetch_fails(self):
        prev = [{"corp_code": "00000001", "corp_name": "새이름", "former_names": "", "mcap_rank": "7"}]
        self.assertEqual(cr.build(self.DART, self.KRX, prev, None)[0][0]["mcap_rank"], "7")
        self.assertEqual(cr.build(self.DART, self.KRX, prev, {"111110": 3})[0][0]["mcap_rank"], "3")

    def test_kind_parser(self):
        html = ("<table><tr><th>회사명</th><th>시장구분</th><th>종목코드</th><th>업종</th><th>상장일</th><th>결산월</th></tr>"
                "<tr><td>가나</td><td>유가</td><td>5930</td><td>a</td><td>2000-01-01</td><td>03월</td></tr>"
                "<tr><td>가나</td><td>유가</td><td>5930</td><td>a</td><td>2000-01-01</td><td>03월</td></tr>"
                "<tr><td>다라</td><td>코스닥</td><td>0035S0</td><td>b</td><td>2026-01-01</td><td>12월</td></tr></table>")
        resp = mock.Mock(content=html.encode("euc-kr"), raise_for_status=lambda: None)
        with mock.patch("requests.get", return_value=resp):
            rows = cr.fetch_krx_listed()
        self.assertEqual([x["stock_code"] for x in rows], ["005930", "0035S0"])   # 0 채움, 중복 제거
        self.assertEqual(rows[0]["fiscal_month"], "3")

    def test_refresh_refuses_shrunken_result(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"DART_CACHE_DIR": d}), \
                mock.patch.object(cr, "fetch_dart_corps", return_value=self.DART), \
                mock.patch.object(cr, "fetch_krx_listed", return_value=self.KRX), \
                mock.patch.object(cr, "fetch_mcap_ranks", return_value={}):
            with self.assertRaises(RuntimeError):
                cr.refresh("dummy-key")
            self.assertFalse((Path(d) / "corp_codes_listed.csv").exists())

    def test_refresh_error_hides_key(self):
        def boom(key, timeout=60):
            raise ValueError(f"bad url https://x?crtfc_key={key}&a=1")
        with mock.patch.object(cr, "fetch_dart_corps", side_effect=boom):
            with self.assertRaises(RuntimeError) as cm:
                cr.refresh("SECRET123")
        self.assertNotIn("SECRET123", str(cm.exception))

    def test_cache_preferred_when_newer(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"DART_CACHE_DIR": d}):
            listed, delisted, meta = cr.build(self.DART, self.KRX, [])
            meta["generated_at"] = "2999-01-01T00:00:00+09:00"
            cr._write_csv(Path(d) / "corp_codes_listed.csv", listed, cr.LISTED_COLS)
            cr._write_csv(Path(d) / "corp_codes_delisted.csv", delisted, cr.DELISTED_COLS)
            (Path(d) / "corp_codes_meta.json").write_text(json.dumps(meta), encoding="utf-8")
            reg = cr.load()
            self.assertEqual(reg.source, "cache")
            self.assertEqual(len(reg.listed), 1)


class DartClientBehavior(unittest.TestCase):
    def setUp(self):
        import dart_client
        self.dc = dart_client
        self.client = dart_client.DartClient(api_key="SECRET123", retries=2)

    def _resp(self, payload=None, exc=None):
        m = mock.Mock()
        m.raise_for_status = mock.Mock(side_effect=exc)
        m.json = mock.Mock(return_value=payload)
        return m

    def test_retries_rate_limit_then_succeeds(self):
        seq = [self._resp({"status": "020"}), self._resp({"status": "000", "ok": 1})]
        with mock.patch.object(self.client.session, "get", side_effect=seq), mock.patch("time.sleep"):
            self.assertEqual(self.client.company("00258801")["status"], "000")

    def test_013_is_returned_not_retried(self):
        get = mock.Mock(return_value=self._resp({"status": "013"}))
        with mock.patch.object(self.client.session, "get", get):
            self.assertEqual(self.client.company("00258801")["status"], "013")
        self.assertEqual(get.call_count, 1)

    def test_network_error_hides_key_and_is_connection_error(self):
        import requests
        err = requests.HTTPError("500 for url: https://opendart.fss.or.kr/api/x?crtfc_key=SECRET123&corp_code=1")
        with mock.patch.object(self.client.session, "get", return_value=self._resp(exc=err)), mock.patch("time.sleep"):
            with self.assertRaises(ConnectionError) as cm:      # verify_report가 INCOMPLETE로 처리하는 계열
                self.client.company("00258801")
        self.assertNotIn("SECRET123", str(cm.exception))

    def test_latest_periodic_report_march_fye(self):
        """3월 결산: bsns_year는 '(YYYY.MM)'의 연도, 늦게 낸 옛 기간 [기재정정]에 끌려가지 않는다 (신영증권 실측 형태)."""
        lst = {"status": "000", "list": [
            {"report_nm": "[기재정정]반기보고서 (2025.09)", "rcept_no": "a", "rcept_dt": "20260409"},
            {"report_nm": "분기보고서 (2026.06)", "rcept_no": "b", "rcept_dt": "20260810"},
            {"report_nm": "사업보고서 (2026.03)", "rcept_no": "c", "rcept_dt": "20260611"},
        ]}
        with mock.patch.object(self.client, "list_disclosures", return_value=lst):
            got = self.client.latest_periodic_report("00136721", fiscal_month=3)
        self.assertEqual((got["bsns_year"], got["reprt_code"], got["rcept_no"]), ("2026", "11013", "b"))

    def test_latest_periodic_report_december(self):
        lst = {"status": "000", "list": [
            {"report_nm": "사업보고서 (2025.12)", "rcept_no": "a", "rcept_dt": "20260310"},
            {"report_nm": "분기보고서 (2025.09)", "rcept_no": "x", "rcept_dt": "20251114"},
        ]}
        with mock.patch.object(self.client, "list_disclosures", return_value=lst):
            got = self.client.latest_periodic_report("00258801")
        self.assertEqual((got["bsns_year"], got["reprt_code"]), ("2025", "11011"))
        lst["list"] = [{"report_nm": "분기보고서 (2025.09)", "rcept_no": "x", "rcept_dt": "20251114"}]
        with mock.patch.object(self.client, "list_disclosures", return_value=lst):
            self.assertEqual(self.client.latest_periodic_report("00258801")["reprt_code"], "11014")

    def test_latest_periodic_report_semiannual_fiscal(self):
        """6개월 결산(리츠 등)은 사업보고서를 1년에 두 번 낸다. 결산월로부터 6개월 뒤 사업보고서도 11011이다."""
        lst = {"status": "000", "list": [
            {"report_nm": "사업보고서 (2026.09)", "rcept_no": "s2", "rcept_dt": "20261201"},
            {"report_nm": "사업보고서 (2026.03)", "rcept_no": "s1", "rcept_dt": "20260601"},
        ]}
        with mock.patch.object(self.client, "list_disclosures", return_value=lst):
            got = self.client.latest_periodic_report("x", fiscal_month=3)
        self.assertEqual((got["rcept_no"], got["reprt_code"]), ("s2", "11011"))

    def test_verify_live_rejects_unlisted_class(self):
        corp = r("카카오")["corp"]
        payload = {"status": "000", "stock_code": "035720", "corp_cls": "E"}
        with mock.patch("requests.get", return_value=mock.Mock(json=mock.Mock(return_value=payload))):
            self.assertIs(cr.verify_live(corp, api_key="k")["ok"], False)

    def test_latest_periodic_report_annual_only(self):
        lst = {"status": "000", "list": [
            {"report_nm": "반기보고서 (2026.06)", "rcept_no": "h", "rcept_dt": "20260814"},
            {"report_nm": "사업보고서 (2025.12)", "rcept_no": "a", "rcept_dt": "20260320"},
        ]}
        with mock.patch.object(self.client, "list_disclosures", return_value=lst):
            self.assertEqual(self.client.latest_periodic_report("x", annual_only=True)["rcept_no"], "a")

    def test_resolve_corp_live_mismatch_matches_cli(self):
        """파이썬 호출도 CLI처럼 live_check 불일치면 not_found로 바뀐다 (RED 리뷰)."""
        with mock.patch.object(cr, "verify_live", return_value={"ok": False, "reason": "x"}):
            res = self.client.resolve_corp("현대차", verify=True, refresh=False)
        self.assertEqual(res["status"], "not_found")
        self.assertIsNone(res["corp"])
        self.assertTrue(any("--refresh" in a for a in res["agent"]))

    def test_find_corp_listed_uses_registry(self):
        df = self.client.find_corp("현대차")
        self.assertEqual(df.iloc[0]["stock_code"], "005380")
        self.assertEqual(len(df), 1)


class IdentityGate(unittest.TestCase):
    """verify_report.check_identity: 잘못된 회사를 막고, 맞는 회사는 통과시킨다."""

    def setUp(self):
        import verify_report as vr
        self.vr = vr

    def run_gate(self, name, code, corp_code, company):
        R = self.vr.Report()
        d = {"meta": {"name": name, "code": code}, "audit": {"src": {"corp_code": corp_code}}}
        with mock.patch("dart_client.DartClient.company", return_value=company), \
                mock.patch.object(self.vr, "_load_key", return_value="k"):
            self.vr.check_identity(d, R)
        return R

    def test_correct_company_passes(self):
        R = self.run_gate("카카오", "035720", "00258801",
                          {"status": "000", "corp_name": "(주)카카오", "stock_code": "035720", "corp_cls": "Y"})
        self.assertEqual(R.fails, [])

    def test_wrong_corp_code_fails(self):
        R = self.run_gate("카카오", "035720", "00137997",
                          {"status": "000", "corp_name": "현대차증권(주)", "stock_code": "001500", "corp_cls": "Y"})
        self.assertGreaterEqual(len(R.fails), 2)

    def test_delisted_corp_code_fails_even_if_dart_agrees(self):
        """DART는 폐지 뒤에도 종목코드를 남긴다. 옛 삼성물산(000830)이 통과하면 안 된다 (RED 리뷰)."""
        R = self.run_gate("삼성물산", "000830", "00126229",
                          {"status": "000", "corp_name": "삼성물산", "stock_code": "000830", "corp_cls": "E"})
        self.assertTrue(R.fails)

    def test_unlisted_class_fails(self):
        R = self.run_gate("카카오", "035720", "00258801",
                          {"status": "000", "corp_name": "(주)카카오", "stock_code": "035720", "corp_cls": "E"})
        self.assertTrue(any("상장 구분" in f["item"] for f in R.fails))

    def test_rate_limit_is_incomplete_not_fail(self):
        with self.assertRaises(ConnectionError):
            self.run_gate("카카오", "035720", "00258801", {"status": "020", "message": "limit"})

    def test_name_that_is_also_alias_passes(self):
        """모비스(250060)의 정상 리포트가 게이트에서 영구 FAIL하던 것 (RED 2차)."""
        row = REG.by_code["250060"]
        R = self.run_gate("모비스", "250060", row["corp_code"],
                          {"status": "000", "corp_name": "모비스", "stock_code": "250060", "corp_cls": "K"})
        self.assertEqual(R.fails, [])

    def test_fiscal_label_year(self):
        from dart_client import fiscal_label, fiscal_label_year
        # 12월 결산은 bsns_year 그대로
        self.assertEqual(fiscal_label("2026", "11012", 12), "2Q26")
        # 3월 결산 FY25 = 2025.04~2026.03: 1Q(2025.06)·3Q(2025.12)·4Q(2026.03) 모두 25
        self.assertEqual([fiscal_label_year(y, c, 3) for y, c in (("2025", "11013"), ("2025", "11014"), ("2026", "11011"))],
                         [2025, 2025, 2025])
        # 6월 결산 FY25 = 2025.07~2026.06: 3Q(2026.03, bsns 2026)도 25
        self.assertEqual(fiscal_label_year("2026", "11014", 6), 2025)

    def test_q3_year(self):
        self.assertEqual(self.vr.q3_year("2025", 12), "2025")
        self.assertEqual(self.vr.q3_year("2026", 3), "2025")
        self.assertEqual(self.vr.q3_year("2026", 6), "2026")


class CLI(unittest.TestCase):
    def test_exit_codes(self):
        import contextlib
        import io
        for q, code in (("현대차", 0), ("카카", 2), ("없는회사이름xyz", 3)):
            with self.subTest(q=q), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(cr.main([q, "--offline"]), code)
                json.loads(out.getvalue())


if __name__ == "__main__":
    unittest.main()
