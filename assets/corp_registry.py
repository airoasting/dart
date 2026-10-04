#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""상장사 레지스트리: 종목명·종목코드 → DART corp_code를 한 번에 정확히 찾는다.

왜 따로 두나
  DART corpCode.xml은 상장폐지 뒤에도 stock_code를 지우지 않는다. 그래서 "stock_code가 있는 회사"를
  상장사로 쓰면 1/3이 폐지 종목이고, 같은 이름이 둘씩 걸린다(삼성물산 000830/028260).
  또 회사명 부분일치만 쓰면 "현대차"가 현대차증권으로, "네이버"는 0건이 된다.

데이터
  DART 전체 기업(corpCode.xml) ∩ KRX KIND 현재 상장 목록을 stock_code로 묶는다.
  - assets/corp_codes_listed.csv     번들 스냅샷 (저장소에 포함, 네트워크 없이 조회)
  - assets/corp_codes_delisted.csv   DART에 종목코드가 남은 폐지 종목 + KIND 폐지일·사유 (안내 문구용)
  - assets/corp_aliases.csv          약칭·옛 이름·합병·비상장 → 종목코드 (사람이 관리, kind 열로 구분)
  - ~/.cache/dart-skill/             --refresh 결과. 번들보다 새로우면 이쪽을 쓴다

찾는 순서 (앞 단계에서 1건이면 바로 확정)
  종목코드(우선주는 보통주로) → corp_code → 정확한 회사명 → 별칭(약칭·옛 이름·합병·비상장) → 옛 회사명
  → 영문명 → 앞부분 일치 → 부분 일치(3글자 이상) → 오타 추정(아주 비슷하면 확인 질문)
  확정되지 않으면 덧붙인 말("주가", "3분기", "그룹")과 종목코드를 떼어 한 번 더 본다.
  앞부분·부분 일치는 1건이어도 'confirm'이다. "현대차"→현대차증권 같은 오인을 막기 위해서다.
  같은 말이 정식명이면서 다른 회사의 약칭이면(모비스) 둘 다 후보로 묻는다. 영문 그룹명(Hyundai)도 묻는다.

결과의 message·notes는 사용자에게 보여 줄 문장, agent는 에이전트용 지시다.

CLI
  python3 corp_registry.py 현대차                # JSON 한 덩어리. 종료코드 0 확정 · 2 선택 필요 · 3 없음
  python3 corp_registry.py 현대차 --verify       # DART company.json으로 corp_code↔종목코드 재확인
  python3 corp_registry.py --refresh             # DART+KRX에서 다시 받아 캐시에 저장
  python3 corp_registry.py --refresh --bundle    # 저장소 번들을 갱신 (유지보수자용)
  python3 corp_registry.py --status              # 현재 쓰는 목록의 출처·날짜·건수

stdlib만 쓴다. --refresh·--verify만 requests가 필요하다.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import html.parser
import io
import json
import os
import re
import sys
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE_LISTED = HERE / "corp_codes_listed.csv"
BUNDLE_DELISTED = HERE / "corp_codes_delisted.csv"
BUNDLE_META = HERE / "corp_codes_meta.json"
ALIASES = HERE / "corp_aliases.csv"

STALE_DAYS = 30
LISTED_COLS = ["corp_code", "corp_name", "corp_eng_name", "stock_code", "market", "sector",
               "listed_date", "fiscal_month", "former_names", "mcap_rank", "modify_date"]
DELISTED_COLS = ["corp_code", "corp_name", "corp_eng_name", "stock_code", "modify_date"]
DELISTED_OUT_COLS = DELISTED_COLS + ["delist_date", "delist_reason"]   # KIND 상장폐지현황 (2000년 이후)
MARKET_RANK = {"유가": 0, "코스닥": 1, "코넥스": 2}

DART_CORPCODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
DART_COMPANY_URL = "https://opendart.fss.or.kr/api/company.json"
KIND_LIST_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do"
KIND_DELIST_URL = "https://kind.krx.co.kr/investwarn/delcompany.do"
NAVER_MCAP_URL = "https://m.stock.naver.com/api/stocks/marketValue/{market}"   # 후보 정렬용 시가총액 순위
MCAP_TOP_PER_MARKET = 300


def cache_dir() -> Path:
    return Path(os.environ.get("DART_CACHE_DIR") or Path.home() / ".cache" / "dart-skill")


# ───────────────────────── 정규화 ─────────────────────────

# 회사명 앞머리 영문 약자의 한글 표기. 질의와 회사명 양쪽에 같이 적용해 "엘지전자" = "LG전자"로 만든다.
# 긴 것부터 바꿔야 "에이치디"가 "디"보다 먼저 잡힌다.
_HANGUL_LATIN = sorted({
    "에스케이": "sk", "엘지": "lg", "케이티앤지": "ktandg", "케이티": "kt", "씨제이": "cj",
    "에이치디": "hd", "지에스": "gs", "엘에스": "ls", "케이비": "kb", "디비": "db",
    "에이치엘": "hl", "오씨아이": "oci", "케이씨씨": "kcc", "엔에이치": "nh", "비엔케이": "bnk",
    "제이비": "jb", "에스디아이": "sdi", "에스디에스": "sds", "에스엠": "sm", "와이지": "yg",
    "제이와이피": "jyp", "포스코": "posco", "에이치엠엠": "hmm", "엔에이치엔": "nhn",
    "에스오일": "s-oil", "에쓰오일": "s-oil", "케이엠더블유": "kmw",
}.items(), key=lambda kv: -len(kv[0]))

_CORP_NOISE = re.compile(r"\(주\)|㈜|주식회사|\(株\)|\(유\)|유한회사")
# 법인 형태 표기만 지운다. holdings·group은 다른 회사(지주사)를 가리킬 수 있어 엄격 비교에서는 남긴다.
_ENG_NOISE = re.compile(r"\b(co|company|corp|corporation|inc|incorporated|ltd|limited|plc|the)\b\.?")
_ENG_LOOSE = re.compile(r"\b(holdings?|group)\b")


def norm(s: str) -> str:
    """회사명 비교용 키. NFKC → 소문자 → (주) 등 제거 → 한글 약자 → 기호·공백 제거."""
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"\s+", "", _CORP_NOISE.sub("", s))   # 공백을 먼저 지워야 "(주) 엘지전자"의 약자 변환이 된다
    s = s.replace("&", "and")
    for ko, la in _HANGUL_LATIN:
        if s.startswith(ko):
            s = la + s[len(ko):]
            break
    return re.sub(r"[\s\.\,\-\_\(\)\[\]'\"·/+]", "", s)


_LETTER_KO = dict(zip("abcdefghijklmnopqrstuvwxyz", [
    "에이", "비", "씨", "디", "이", "에프", "지", "에이치", "아이", "제이", "케이", "엘", "엠", "엔", "오", "피", "큐",
    "알", "에스", "티", "유", "브이", "더블유", "엑스", "와이", "제트"]))


def _spac_key(k: str) -> str | None:
    """스팩 이름 변형을 하나로: 'KB제34호스팩' · 'KB34호스팩' · '케이비제34호기업인수목적' → 'kb34',
    '하나스팩36호' · '하나36호스팩' → '하나36'."""
    if not re.search(r"스팩|기업인수목적", k):
        return None
    num = re.search(r"(\d+)", k)
    if not num:
        return None
    brand = re.sub(r"스팩|기업인수목적|제|호|\d+", "", k)
    return brand + num.group(1)


def reading(s: str) -> str:
    """영문 약자를 한글 글자 이름으로 읽은 키. 'NHN KCP' → '엔에이치엔케이씨피', 'HK이노엔' → '에이치케이이노엔'.
    사람들이 약자를 한글로 풀어 쓰는 경우(에이치케이이노엔)를 정식명과 맞추는 데 쓴다."""
    k = norm(s).replace("and", "앤")
    return "".join(_LETTER_KO.get(ch, ch) for ch in k)


def norm_eng(s: str, loose: bool = False) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower().replace("&", "and")
    s = _ENG_NOISE.sub(" ", s)
    if loose:
        s = _ENG_LOOSE.sub(" ", s)
    return re.sub(r"[^0-9a-z가-힣]", "", s)


_CODE_RE = re.compile(r"^a?([0-9][0-9a-z]{5})(?:\.(?:ks|kq|kn))?$")
_PREF_SUFFIX = re.compile(r"(\d?우[bB]?|우선주?)$")


def parse_stock_code(q: str) -> str | None:
    """'005930', 'A005930', '005930.KS', '0035S0' → 대문자 6자리. 숫자가 하나도 없으면 코드가 아니다."""
    m = _CODE_RE.match(re.sub(r"\s", "", q).lower())
    return m.group(1).upper() if m else None


def common_of(code: str) -> str | None:
    """우선주 코드 → 보통주 코드. KRX 우선주는 보통주 앞 5자리에 끝자리 5·7·9 또는 K(신형 우선주)를 붙인다.

    005935(삼성전자우) → 005930, 00499K(롯데지주우) → 004990. 끝자리 1·2 같은 코드는 오타일 수 있어 바꾸지 않는다.
    """
    if code[:5].isdigit() and code[-1] in "579K":
        return code[:5] + "0"
    return None


# ───────────────────────── 레지스트리 로드 ─────────────────────────

@dataclass
class Registry:
    listed: list[dict]
    delisted: list[dict]
    aliases: list[dict]
    meta: dict
    source: str                                   # "cache" | "bundle"
    by_code: dict = field(default_factory=dict)
    by_corp: dict = field(default_factory=dict)
    by_norm: dict = field(default_factory=dict)

    by_reading: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 별칭 표의 옛 이름도 후보 설명에 보이게 붙인다 (티웨이 → "트리니티항공(옛 티웨이항공)"). 파일은 바꾸지 않는다
        olds: dict[str, list[str]] = {}
        for a in self.aliases:
            if a.get("kind") == "former" and a.get("stock_code"):
                olds.setdefault(a["stock_code"], []).append(a["alias"])
        if olds:
            self.listed = [dict(r) for r in self.listed]
            for r in self.listed:
                extra = [x for x in olds.get(r["stock_code"], []) if x not in (r.get("former_names") or "").split("|")]
                if extra:
                    r["former_display"] = "|".join(extra)
        for r in self.listed:
            self.by_code[r["stock_code"]] = r
            self.by_corp[r["corp_code"]] = r
            self.by_norm.setdefault(norm(r["corp_name"]), []).append(r)
            if re.search(r"[a-z]", norm(r["corp_name"])):
                self.by_reading.setdefault(reading(r["corp_name"]), []).append(r)

    @property
    def generated_at(self) -> str:
        return self.meta.get("generated_at", "")

    def age_days(self) -> int | None:
        try:
            return (dt.date.today() - dt.date.fromisoformat(self.generated_at[:10])).days
        except ValueError:
            return None


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def _read_meta(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ts(meta: dict) -> float:
    """generated_at → epoch 초. 시간대가 다른 문자열끼리 사전순 비교하지 않기 위해서다."""
    try:
        t = dt.datetime.fromisoformat(meta.get("generated_at", ""))
        return (t if t.tzinfo else t.astimezone()).timestamp()
    except ValueError:
        return 0.0


def load(prefer_cache: bool = True) -> Registry:
    """캐시와 번들 중 generated_at이 더 최근인 쪽을 쓴다."""
    aliases = _read_csv(ALIASES)
    bundle_meta = _read_meta(BUNDLE_META)
    cd = cache_dir()
    cache_meta = _read_meta(cd / "corp_codes_meta.json")
    use_cache = (prefer_cache and (cd / "corp_codes_listed.csv").exists()
                 and _ts(cache_meta) > _ts(bundle_meta))
    if use_cache:
        return Registry(_read_csv(cd / "corp_codes_listed.csv"), _read_csv(cd / "corp_codes_delisted.csv"),
                        aliases, cache_meta, "cache")
    return Registry(_read_csv(BUNDLE_LISTED), _read_csv(BUNDLE_DELISTED), aliases, bundle_meta, "bundle")


# ───────────────────────── 찾기 ─────────────────────────
#
# 결과의 문장은 두 갈래다.
#   message·notes  사용자에게 보여 줄 문장 (~합니다체, 명령어·API 용어 없음)
#   agent          스킬을 실행하는 에이전트에게 주는 지시 (사용자에게 그대로 보이지 않는다)

MARKET_LABEL = {"유가": "코스피", "코스닥": "코스닥", "코넥스": "코넥스"}
REFRESH_COOLDOWN_H = 6
SHOW_MAX = 10
# 오타 후보가 자모 기준으로 이만큼 비슷하고 2등보다 이만큼 앞서면 "이 회사가 맞나요?"로 묻는다.
# 전 상장사에 한·두 글자 오타를 넣어 고른 값이다 (한 글자 97%, 두 글자 80%가 질문으로 가고 오답 질문은 0.1% 미만).
SUGGEST_PROMOTE = ((0.85, 0.05), (0.75, 0.10))

# ── 조사: 회사명 끝소리에 맞춘다.
#    영문 약자(모음이 없거나 3글자 이하: LG, SK, HMM, APR)는 글자 이름으로 읽고(엘지·에스케이·에이치엠엠),
#    그보다 긴 영문 단어(NAVER, Coupang, SIMPAC, SOOP)는 단어로 읽어 마지막 소리로 정한다.
_JOSA_EXC = {"ent": (False, False)}             # (받침 있음, 받침이 ㄹ) — JYP Ent.(엔터)처럼 줄여 읽는 말


def _batchim(word: str) -> tuple[bool, bool]:
    w = re.sub(r"[\s\.\,\)\]'\"&\-]+$", "", word or "")
    if not w:
        return False, False
    if w.lower() in _JOSA_EXC:
        return _JOSA_EXC[w.lower()]
    ch = w[-1]
    if "가" <= ch <= "힣":
        jong = (ord(ch) - 0xAC00) % 28
        return jong != 0, jong == 8
    if ch.isdigit():                              # 영 일 이 삼 사 오 육 칠 팔 구
        return ch in "013678", ch in "178"
    if ch.isalpha():
        token = re.findall(r"[A-Za-z]+$", w)[0]
        # 약자: 3글자 이하, 모음 없음, 자음 셋 이상 연속(RFHIC, EDGC, iMBC) → 글자 이름 (엘 엠 엔 알만 받침)
        if len(token) <= 3 or not re.search(r"[aeiouAEIOU]", token) or re.search(r"[^aeiouAEIOU]{3,}", token):
            return ch.upper() in "LMNR", ch.upper() in "LR"
        last = token.lower()                                           # 단어: 끝소리
        if last.endswith("ng"):
            return True, False
        return last[-1] in "bclmnpt", last[-1] == "l"      # k·d·q로 끝나면 '크·드'로 읽어 받침이 없다 (Oilbank → 뱅크)
    return False, False


def josa(word: str, pair: str) -> str:
    """josa('셀트리온', '이/가') → '이'. pair: 이/가 · 을/를 · 은/는 · 과/와 · 으로/로."""
    has, rieul = _batchim(word)
    a, b = pair.split("/")
    if pair == "으로/로":
        return "으로" if has and not rieul else "로"
    return a if has else b


def corp_kind(r: dict) -> str:
    """spac · reit · fund · normal. 리포트 대상 여부를 가르는 데 쓴다.

    reit: 이름이 '리츠'로 끝나는 부동산투자회사(이리츠코크렙 포함).
    fund: KRX 결산월은 12월이지만 6개월마다 결산하는 상장 인프라·부동산 펀드(맥쿼리인프라, 맵스리얼티 등).
    """
    name = r.get("corp_name", "")
    if "스팩" in name or "기업인수목적" in name:
        return "spac"
    if re.search(r"리츠(코크렙)?$", name):
        return "reit"
    if r.get("sector") == "신탁업 및 집합투자업" and re.search(r"인프라|리얼티", name):
        return "fund"
    return "normal"


def _public(r: dict) -> dict:
    out = {k: r.get(k, "") for k in LISTED_COLS if k != "modify_date"}
    out["fiscal_month"] = int(r["fiscal_month"]) if str(r.get("fiscal_month", "")).isdigit() else None
    out["former_names"] = [x for x in ((r.get("former_names") or "") + "|" + (r.get("former_display") or "")).split("|") if x]
    out.pop("former_display", None)
    out["market_label"] = MARKET_LABEL.get(r.get("market", ""), r.get("market", ""))
    out["kind"] = corp_kind(r)
    out.pop("mcap_rank", None)
    return out


def _mcap(r: dict) -> int:
    return int(r["mcap_rank"]) if str(r.get("mcap_rank", "")).isdigit() else 10 ** 6


def _rank_key(reg: Registry):
    """후보 정렬: 스팩·리츠·펀드 뒤로, 시가총액 순위(코스피·코스닥 각 상위 300), 별칭 있는 회사, 시장, 짧은 이름."""
    popular = {a["stock_code"] for a in reg.aliases}

    def key(r: dict) -> tuple:
        return (corp_kind(r) != "normal", _mcap(r), r["stock_code"] not in popular,
                MARKET_RANK.get(r.get("market", ""), 9), len(r["corp_name"]), r["corp_name"])
    return key


def _fmt(r: dict) -> str:
    return f"{r['corp_name']}({r['stock_code']}, {MARKET_LABEL.get(r.get('market', ''), '시장 미상')})"


def _with(r: dict, pair: str) -> str:
    """'셀트리온(068270, 코스피)이' — 괄호 뒤 조사는 회사명 끝소리를 따른다."""
    return _fmt(r) + josa(r["corp_name"], pair)


def _q(q: str, pair: str) -> str:
    return f"'{q}'{josa(q, pair)}"


def _result(query, status, match, rows, reg: Registry, message, notes=None, agent=None,
            suggestions=None) -> dict:
    rows = sorted(rows, key=_rank_key(reg))
    notes, agent = list(notes or []), list(agent or [])
    corp = _public(rows[0]) if status in ("ok", "confirm") and rows else None
    if corp:
        fm, kind = corp["fiscal_month"], corp["kind"]
        if kind in ("reit", "fund"):
            what = ("리츠(부동산투자회사)" if kind == "reit" else
                    "상장 인프라 펀드" if "인프라" in rows[0]["corp_name"] else "상장 부동산 펀드")
            message = (f"{_with(rows[0], '은/는')} {what}라서 실적 리포트를 만들 수 없습니다. "
                       "결산 주기와 실적 구조가 일반 기업과 달라 분기 비교가 성립하지 않습니다. "
                       "다른 회사를 알려 주세요.")
            agent.append("리포트를 만들지 않는다. message를 전하고 멈춘다.")
        elif kind == "spac":
            notes.append("기업인수목적회사(스팩)는 합병 전에는 영업 실적이 거의 없어 리포트가 의미 있게 나오지 않습니다. "
                         "그래도 만들까요?")
            agent.append("사용자가 그래도 원한다고 답할 때만 진행한다.")
        if corp["market"] == "코넥스" and kind == "normal":
            notes.append("코넥스 상장사는 분기·반기 보고서 제출 의무가 없어 연간 실적으로 만듭니다.")
            agent.append("기간은 assemble_report.py period가 정한다(사업보고서와 --scope annual이 args에 들어 있다). "
                         "그 args를 그대로 쓴다.")
        if fm and fm != 12 and kind == "normal":
            notes.append(f"{fm}월 결산 법인입니다. 분기는 이 회사의 회계연도 기준으로 표시합니다.")
            agent.append(f"기간은 assemble_report.py period가 정한다(--fiscal-month {fm}이 args에 들어 있다). "
                         "build에 --period-note로 실제 기간(예: FY25 1Q (2025.04~06))을 밝힌다.")
    age = reg.age_days()
    if age is not None and age > STALE_DAYS:
        notes.append(f"상장사 목록이 {reg.generated_at[:10]} 기준이라 그 뒤 상장하거나 이름을 바꾼 회사는 빠졌을 수 있습니다.")
        agent.append("python3 ~/.claude/skills/dart/assets/corp_registry.py --refresh 로 목록을 갱신한다.")
    shown = rows[:SHOW_MAX] if status in ("confirm", "ambiguous") else []
    qk = norm(str(query or ""))

    def display(r: dict) -> str:
        """후보 목록에 그대로 쓸 문자열. 사용자가 쓴 말이 이 회사의 옛 이름이면 그것을 밝힌다."""
        p = _public(r)
        olds = [x for x in p["former_names"] if norm(x) == qk or (qk and qk in norm(x))]
        return _fmt(r) + (f" (옛 이름: {olds[0]})" if olds else "")
    cands = []
    for r in shown:
        c = _public(r)
        c["display"] = display(r)
        cands.append(c)
    return {
        "query": query,
        "status": status,              # ok | confirm | ambiguous | not_found
        "match": match,
        "corp": corp,
        "candidates": cands,
        "total_candidates": len(rows) if status in ("confirm", "ambiguous") else 0,
        "suggestions": suggestions or [],
        "message": message,
        "notes": notes,
        "agent": agent,
        "registry": {"source": reg.source, "generated_at": reg.generated_at, "listed": len(reg.listed)},
    }


def _ok(q, match, r, reg, notes=None) -> dict:
    return _result(q, "ok", match, [r], reg, f"{_with(r, '을/를')} 찾았습니다.", notes)


def _confirm(q, match, r, reg, lead: str, notes=None) -> dict:
    return _result(q, "confirm", match, [r], reg, f"{lead} {_with(r, '이/가')} 맞나요?".strip(), notes)


def _ambiguous(q, match, rows, reg, lead: str = "", notes=None, hint: str = "") -> dict:
    n = len(rows)
    msg = f"{lead} 후보가 {n}곳입니다. 어느 회사인가요?".strip()
    if n > SHOW_MAX:
        msg += f" 자주 찾는 순으로 {SHOW_MAX}곳만 보여 드립니다. 원하는 회사가 없으면 이름을 조금 더 구체적으로 알려 주세요."
    elif hint:
        msg += " " + hint
    return _result(q, "ambiguous", match, rows, reg, msg, notes)


_CODE_PREFIX = re.compile(r"^(xkrx|krx|kospi|kosdaq|konex|ks|kq)\s*[:：]\s*", re.I)
# 대화체로 붙는 말: "삼성전자 실적 어때?", "하이닉스 리포트 뽑아줘", "/dart 삼성전자"
_CHAT_WORD = re.compile(r"^(어때|어떄|어떤지|어떻게|좀|한번|좀더|부탁해|부탁|알려줘|보여줘|뽑아줘|만들어줘|분석해줘|정리해줘|해줘|줘|봐줘|"
                        r"궁금해|궁금|요약|요약해줘|최근|이번|지난|올해|작년|분기|\S*해줘|\S*줘|\S*줄래|\S*할래)$")
_PARTICLE = re.compile(r"(이랑|랑|하고|와|과|및|이나|나|은|는|이|가|을|를|의|도|에|에서|부터)$")
_PERIOD_TOKEN = re.compile(r"^(\d{4}[\.\-]?[1-4]q|[1-4]q\d{2,4}|[12]h\d{2,4}|\d{4}\.\d{1,2}|\d{2}\.\d{1,2})$", re.I)
# 회사명 뒤에 붙여 치는 말: "삼성전자 주가", "현대차 실적", "SK하이닉스 3분기", "LG그룹"
_TAIL_WORDS = re.compile(
    r"(\s+(주가|실적|리포트|보고서|분석|대시보드|전망|공시|주식|종목|재무|\d{1,2}분기|[1-4]q\d{0,4}|\d{2}(\d{2})?년?|fy\d{2,4}|\d{4}[\.\-]?[1-4]q|[12]h\d{2,4}|\d{4}\.\d{1,2}))+$",
    re.I)
_GROUP_WORD = re.compile(r"\s*(그룹|계열사?)$")


_LEADING_CODE = re.compile(r"^([0-9][0-9A-Z]{5})(?=[^0-9A-Z\s])", re.I)
# 증권사 리포트식 표기: "삼성전자(005930)", "삼성전자(005930.KS)", "LG에너지솔루션(373220 KS)", "삼성전자 [005930]"
_CODE_ANNOT = re.compile(r"[\(\[]\s*([0-9][0-9A-Z]{5})\s*(?:[\.\s]?\s*(?:KS|KQ|KN|KRX))?\s*[\)\]]", re.I)
_MARKET_TAIL = re.compile(r"\s+(KS|KQ|KN|KOSPI|KOSDAQ|코스피|코스닥)$", re.I)
# 뉴스 제목식 한자 약칭: 현대重 · 삼성重 · 현대車 · 두산重
_HANJA_TAIL = {"重": "중공업", "車": "자동차", "電": "전자", "建": "건설", "證": "증권", "化": "화학",
               "生": "생명", "火": "화재", "銀": "은행", "藥": "약품"}      # 製는 製鐵·製紙 등이 섞여 넣지 않는다
_HANJA_WORD = {"韓電": "한전", "韓銀": "한국은행", "韓航": "대한항공"}


def resolve(query: str, reg: Registry | None = None) -> dict:
    """질의 하나를 상장사 하나로 좁힌다. 네트워크를 쓰지 않는다 (갱신은 resolve_or_refresh).

    질의 전체로 먼저 찾고, 확정되지 않으면 덧붙인 말(주가·실적·분기·그룹)과 종목코드를 떼어 다시 본다.
    """
    reg = reg or load()
    q = unicodedata.normalize("NFKC", query or "").strip()       # 전각 숫자·영문
    q = re.sub(r"^/?dart\s+", "", q, flags=re.I)
    q = re.sub(r"[\?\!\.。~…]+$", "", q).strip()
    # 종목코드처럼 생긴 토큰의 영문 O → 숫자 0 ("00066O")
    q = re.sub(r"\b(?=[0-9O]{6}\b)(?=[^O]*\d)[0-9O]{6}\b", lambda m: m.group(0).replace("O", "0"), q)
    q = _CODE_PREFIX.sub("", q).strip("\"' ")
    m = re.fullmatch(r"[\(\[]\s*([0-9][0-9A-Za-z]{5})\s*[\)\]]", q)          # "(005930)"
    q = m.group(1) if m else q
    q = _LEADING_CODE.sub(r"\1 ", q)                              # "005930삼성전자" → "005930 삼성전자"
    q = _CODE_ANNOT.sub(lambda m: " " + m.group(1).upper() + " ", q).strip()   # "삼성전자(005930.KS)" → "삼성전자 005930"
    q = re.sub(r"\s+", " ", _MARKET_TAIL.sub("", q)).strip()
    for w, ko in _HANJA_WORD.items():
        q = q.replace(w, ko)
    q = "".join(_HANJA_TAIL.get(ch, ch) for ch in q)
    res = _resolve_core(q, reg)
    if res["status"] == "ok":
        return res
    toks = q.split()
    code_toks = [t for t in toks if parse_stock_code(t)]
    if code_toks and len(toks) > 1:                    # "삼성전자 005930": 이름과 코드가 같은 회사인지 본다
        rc = _resolve_core(code_toks[0], reg)
        name = _TAIL_WORDS.sub("", " ".join(t for t in toks if t not in code_toks)).strip()
        rn = _resolve_core(name, reg) if name else None
        if rc["status"] == "ok" and (not rn or rn["status"] != "ok" or rn["corp"]["corp_code"] == rc["corp"]["corp_code"]):
            return rc
        if rc["status"] == "ok" and rn and rn["status"] == "ok":
            rows = [reg.by_corp[rc["corp"]["corp_code"]], reg.by_corp[rn["corp"]["corp_code"]]]
            return _ambiguous(q, "name_code_conflict", rows, reg, "이름과 종목코드가 서로 다른 회사를 가리킵니다.")
    # "LG그룹", "삼성 계열사": 그룹을 하나의 회사로 고르지 않는다. 그 이름으로 시작하는 상장사를 시가총액 순으로 묻는다
    gm = _GROUP_WORD.search(q)
    if gm and res["status"] != "ok" and res["match"] != "alias":   # 그룹 계열사 별칭(현대차그룹)이 있으면 그것이 먼저
        base = _TAIL_WORDS.sub("", q[:gm.start()]).strip()
        bk = norm(base)
        if bk:
            rows = [r for r in reg.listed if norm(r["corp_name"]).startswith(bk)]
            rows += [reg.by_code[a["stock_code"]] for a in reg.aliases
                     if norm(a["alias"]) == bk and a["stock_code"] in reg.by_code and a.get("kind") != "unlisted"]
            rows = list({r["corp_code"]: r for r in rows}.values())
            if rows:
                res_g = _ambiguous(query, "group", rows, reg,
                                   f"그룹 전체가 아니라 상장사 한 곳의 리포트를 만듭니다. "
                                   f"이름이 '{base}'{josa(base, '으로/로')} 시작하는 상장사를 모았습니다.",
                                   hint="찾는 계열사가 없으면 회사 이름을 알려 주세요.")
                holding_keys = {bk, bk + "지주", bk + "홀딩스", bk + "금융지주"}           # 지주사(LG, SK, 롯데지주)를 맨 앞에
                hold = [i for i, c in enumerate(res_g["candidates"]) if norm(c["corp_name"]) in holding_keys]
                if not hold and any(norm(r["corp_name"]) in holding_keys for r in rows):
                    h = next(r for r in rows if norm(r["corp_name"]) in holding_keys)
                    res_g["candidates"] = [_public(h)] + res_g["candidates"][:SHOW_MAX - 1]
                elif hold:
                    c = res_g["candidates"].pop(hold[0])
                    res_g["candidates"].insert(0, c)
                return res_g
    trimmed = _TAIL_WORDS.sub("", q).strip()
    if trimmed and trimmed != q:
        r2 = _resolve_core(trimmed, reg)
        if r2["status"] != "not_found":
            r2["query"] = query
            r2["agent"].append(f"질의에서 덧붙인 말을 떼고 '{trimmed}'로 찾았다. 기간 표현은 SKILL.md Step 2에서 원래 문장으로 정한다.")
            return r2
    # 대화체·여러 회사: 토큰마다 꾸밈말·조사·기간 표현을 떼고, 남은 토큰을 회사로 읽는다
    toks = [t for t in re.split(r"[\s,/·]+|\s(?:vs|VS|대)\s", q) if t]
    if res["status"] == "not_found" and (len(toks) > 1 or (toks and _PARTICLE.search(toks[0]))):
        names = []
        for t in toks:
            t2 = _TAIL_WORDS.sub("", " " + t).strip()
            if not t2 or _CHAT_WORD.match(t2) or _PERIOD_TOKEN.match(t2) or _TAIL_WORDS.fullmatch(" " + t2):
                continue
            hit = _resolve_core(t2, reg)
            if hit["status"] != "ok" and _PARTICLE.search(t2):          # "삼성전자랑" → "삼성전자"
                stem = _PARTICLE.sub("", t2)
                if stem:
                    h2 = _resolve_core(stem, reg)
                    hit = h2 if h2["status"] == "ok" else hit
            names.append((t2, hit))
        found = [h for _, h in names if h["status"] == "ok"]
        uniq = list({h["corp"]["corp_code"]: h for h in found}.values())
        if len(uniq) >= 2:
            rows = [reg.by_corp[h["corp"]["corp_code"]] for h in uniq]
            out = _result(query, "ambiguous", "multiple", rows, reg,
                          f"회사가 {len(rows)}곳 들어 있습니다. 리포트는 한 번에 한 회사씩 만듭니다. 어느 회사부터 할까요?")
            out["candidates"] = [dict(_public(r), display=_fmt(r)) for r in rows]   # 말한 순서대로
            return out
        if len(uniq) == 1 and len(names) == len(found):          # 남은 말이 모두 같은 회사를 가리킨다
            r1 = uniq[0]
            r1["query"] = query
            r1["agent"].append("대화체 질의에서 회사 이름만 골라 찾았다. 기간 표현은 SKILL.md Step 2에서 원래 문장으로 정한다.")
            return r1
    return res


def _resolve_core(q: str, reg: Registry) -> dict:
    if not q:
        return _result(q, "not_found", None, [], reg, "회사 이름이나 종목코드를 알려 주세요.")
    pref_note = "우선주는 보통주 기준으로 만듭니다. 실적은 회사 단위로 공시되고, 주가도 보통주 종가를 씁니다."

    # 1) 종목코드 (우선주는 보통주로, 엑셀이 지운 앞자리 0은 확인을 받는다)
    code = parse_stock_code(q)
    if code:
        if code in reg.by_code:
            return _ok(q, "stock_code", reg.by_code[code], reg)
        common = common_of(code)
        if common and common in reg.by_code:
            r = reg.by_code[common]
            return _result(q, "ok", "preferred_to_common", [r], reg,
                           f"{_with(r, '을/를')} 찾았습니다. 입력하신 코드({code})는 이 회사의 우선주입니다.",
                           [pref_note])
        dl = [r for r in reg.delisted if r["stock_code"] == code]
        if dl:
            return _delisted(q, dl[0], reg, norm(dl[0]["corp_name"]))
        return _result(q, "not_found", None, [], reg,
                       f"종목코드 {code}에 해당하는 상장사가 없습니다. 코드를 다시 확인해 주세요.")
    if re.fullmatch(r"\d{4,5}", q):
        z = q.zfill(6)
        if z in reg.by_code:
            return _confirm(q, "stock_code_zero_padded", reg.by_code[z], reg,
                            f"앞자리 0이 빠진 종목코드로 보고 찾았습니다({z}).")

    # 2) corp_code
    if re.fullmatch(r"\d{8}", q):
        if q in reg.by_corp:
            return _ok(q, "corp_code", reg.by_corp[q], reg)
        dl = [r for r in reg.delisted if r["corp_code"] == q]
        if dl:
            return _delisted(q, dl[0], reg, norm(dl[0]["corp_name"]))
        return _result(q, "not_found", None, [], reg, "이 고유번호에 해당하는 상장사가 없습니다.")

    key = norm(q)
    if not key:   # "(주)", "주식회사"처럼 꾸밈말만 있는 질의
        return _result(q, "not_found", None, [], reg, "회사 이름이나 종목코드를 알려 주세요.")
    # 우선주 이름 "삼성전자우", "현대차2우B" → 본체 이름으로 한 번 더 본다
    base_key = None
    if _PREF_SUFFIX.search(q) and key not in reg.by_norm:
        base_key = norm(_PREF_SUFFIX.sub("", q))

    def aliases_of(k: str) -> list[dict]:
        return [a for a in reg.aliases if norm(a["alias"]) == k]

    def by_former(k: str) -> list[dict]:
        return [r for r in reg.listed if k in {norm(x) for x in r.get("former_names", "").split("|") if x}]

    for k in filter(None, (key, base_key)):
        notes = [pref_note] if k == base_key else []
        exact = reg.by_norm.get(k, [])
        al = aliases_of(k)
        listed_al = [(a, reg.by_code[a["stock_code"]]) for a in al if a["stock_code"] in reg.by_code]
        # 3) 정확한 회사명. 같은 말이 다른 회사의 약칭이기도 하면(모비스 ↔ 현대모비스) 둘 다 보여 준다
        if exact:
            extra = [r for _, r in listed_al if r["corp_code"] not in {x["corp_code"] for x in exact}]
            if len(exact) == 1 and not extra:
                if notes:   # 우선주 이름으로 들어온 경우
                    return _result(q, "ok", "preferred_to_common", exact, reg,
                                   f"{_with(exact[0], '을/를')} 찾았습니다. 입력하신 이름은 이 회사의 우선주입니다.", notes)
                return _ok(q, "exact_name", exact[0], reg)
            if extra:
                return _ambiguous(q, "exact_name_or_alias", exact + extra, reg,
                                  "그 이름의 상장사와, 흔히 그렇게 줄여 부르는 회사가 함께 있습니다.", notes)
            return _result(q, "ambiguous", "exact_name", exact, reg,
                           f"같은 이름의 상장사가 {len(exact)}곳입니다. 종목코드로 골라 주세요.", notes)
        # 4) 별칭 (약칭 · 옛 이름 · 합병 · 비상장)
        if al:
            a = al[0]
            kind = a.get("kind") or "nickname"
            if kind == "brand" and len(al) == 1 and al[0]["stock_code"] in reg.by_code:
                r = reg.by_code[al[0]["stock_code"]]
                return _confirm(q, "brand", r, reg, f"{_q(q, '을/를')} 브랜드 이름으로 보고 찾았습니다({al[0].get('note')}).", notes)
            if kind == "unlisted":
                parent = reg.by_code.get(a.get("stock_code", ""))
                msg = f"{_q(q, '은/는')} 국내 증시에 상장된 회사가 아니라서 공시 실적 리포트를 만들 수 없습니다({a.get('note')})."
                if parent:
                    msg += " 관련 상장사의 리포트는 만들 수 있으니, 아래 회사로 볼지 알려 주세요."
                sug = [{"corp_name": parent["corp_name"], "stock_code": parent["stock_code"],
                        "market_label": MARKET_LABEL.get(parent.get("market", ""), "")}] if parent else []
                return _result(q, "not_found", "unlisted", [], reg, msg, suggestions=sug)
            uniq = list({r["corp_code"]: (a2, r) for a2, r in listed_al}.values())
            if len(uniq) > 1:
                kinds = {a2.get("kind") for a2, _ in uniq}
                lead = ("그룹 전체가 아니라 상장사 한 곳의 리포트를 만듭니다. 그룹의 주요 상장 계열사입니다." if kinds == {"group"}
                        else "예전에 그 이름을 쓴 회사가 여럿입니다." if kinds == {"former"}
                        else "그 이름으로 부를 수 있는 회사가 여럿입니다.")
                return _ambiguous(q, "alias", [r for _, r in uniq], reg, lead, notes)
            if uniq:
                a, r = uniq[0]
                if kind == "merged":
                    return _result(q, "confirm", "alias_merged", [r], reg,
                                   f"{_q(q, '은/는')} 지금 상장돼 있지 않습니다({a.get('note', '합병')}). "
                                   f"{_with(r, '을/를')} 기준으로 볼까요?", notes)
                if kind == "former":
                    return _result(q, "ok", "former_name", [r], reg,
                                   f"예전 이름으로 찾았습니다. 지금 이름은 {_fmt(r)}입니다.", notes)
                return _ok(q, "alias", r, reg, notes)
        # 5) 옛 회사명 (목록 갱신 때 자동으로 쌓인 사명 변경)
        hits = by_former(k)
        if len(hits) == 1:
            return _result(q, "ok", "former_name", hits, reg,
                           f"예전 이름으로 찾았습니다. 지금 이름은 {_fmt(hits[0])}입니다.", notes)
        if hits:
            return _ambiguous(q, "former_name", hits, reg, "예전에 그 이름을 쓴 회사가 여럿입니다.")

    # 5-1) 약자를 한글로 풀어 쓴 이름 ("에이치케이이노엔" = HK이노엔, "엔에이치엔케이씨피" = NHN KCP)
    rk = reading(q)
    hits = [] if re.search(r"[a-z]", rk) else (reg.by_reading.get(rk, []) or
                                               (reg.by_norm.get(rk, []) if rk != key else []))   # JR글로벌리츠 = 제이알글로벌리츠
    if not hits and _spac_key(key):
        hits = [r for r in reg.listed if _spac_key(norm(r["corp_name"])) == _spac_key(key)]
    elif not hits and re.search(r"스팩|기업인수목적", key) and not re.search(r"\d", key):   # "KB스팩": 회차 없이 증권사만
        brand = re.sub(r"스팩|기업인수목적|제|호", "", key)
        spacs = [r for r in reg.listed if corp_kind(r) == "spac" and (_spac_key(norm(r["corp_name"])) or "").startswith(brand)]
        if spacs:
            return _ambiguous(q, "spac_brand", spacs, reg, "회차 번호가 없어 그 증권사의 스팩을 모두 모았습니다.")
    if len(hits) == 1:
        return _ok(q, "reading", hits[0], reg)
    if hits:
        return _ambiguous(q, "reading", hits, reg)

    # 6) 영문명. 법인 형태(Co., Ltd. 등)만 빼고 같으면 확정한다. 단, 그 이름으로 시작하는 다른 상장사 중
    #    더 큰 회사가 있으면 그룹명일 수 있어(Hyundai → 현대코퍼레이션? 현대자동차?) 함께 보여 준다.
    ek = norm_eng(q)
    if ek and re.search(r"[a-z]", ek):
        hits = [r for r in reg.listed if norm_eng(r["corp_eng_name"]) == ek]
        if len(hits) == 1:
            h = hits[0]
            group = [r for r in reg.listed if r is not h and norm_eng(r["corp_eng_name"]).startswith(ek)]
            has_form = bool(_ENG_NOISE.search(unicodedata.normalize("NFKC", q).lower()))   # "LG Corp.", "SK Inc."
            if not group or has_form or (_mcap(h) <= min(_mcap(r) for r in group) and _mcap(h) < 10 ** 6):
                return _ok(q, "eng_name", h, reg)
            return _ambiguous(q, "eng_name_group", hits + group, reg, "그 이름으로 시작하는 상장사가 여럿입니다.")
        if hits:
            return _ambiguous(q, "eng_name", hits, reg, "영문명이 같은 상장사가 여럿입니다.")
        # Holdings·Group을 빼야 같을 때: 회사 쪽에만 Group이 붙은 경우(KB Financial → KB Financial Group)는 같은 회사,
        # 질의 쪽에만 Holdings·Group이 붙거나 회사 쪽에 Holdings가 붙으면 지주사·계열사가 달라 확인한다
        lk = norm_eng(q, loose=True)
        hits = [r for r in reg.listed if lk and norm_eng(r["corp_eng_name"], loose=True) == lk]
        if len(hits) == 1:
            h = hits[0]
            only_group = (not _ENG_LOOSE.search(unicodedata.normalize("NFKC", q).lower())
                          and not re.search(r"\bholdings?\b", h["corp_eng_name"].lower()))
            if only_group:
                return _ok(q, "eng_name", h, reg)
            return _confirm(q, "eng_name_loose", h, reg, "영문명이 정확히 같은 상장사는 없습니다.")
        if hits:
            return _ambiguous(q, "eng_name_loose", hits, reg, "영문명이 비슷한 상장사가 여럿입니다.")

    # 7) 앞부분 일치 → 8) 부분 일치 (1건이어도 확인을 받는다). 두 글자 이하는 앞부분만 본다(토스 → 비스토스 방지)
    stages = [("prefix", lambda n: n.startswith(key))]
    if len(key) >= 3:
        stages.append(("substring", lambda n: key in n))
    for match, pred in stages:
        hits = [r for r in reg.listed if pred(norm(r["corp_name"]))]
        if not hits and ek and len(ek) >= 3 and re.search(r"[a-z]", ek):
            hits = [r for r in reg.listed if (norm_eng(r["corp_eng_name"]).startswith(ek) if match == "prefix"
                                              else ek in norm_eng(r["corp_eng_name"]))]
        if len(hits) == 1:
            return _confirm(q, match, hits[0], reg, "정확히 같은 이름의 상장사는 없습니다.")
        if hits:
            return _ambiguous(q, match, hits, reg)

    # 8-1) 회사 영문명이 질의의 앞부분인 경우: "Daewoong Pharmaceutical" ↔ "DAEWOONG PHARMA".
    #      앞부분·부분 일치가 모두 실패한 뒤에만 보고, 등록 영문명이 질의의 60% 이상을 덮어야 한다
    #      ("Hanwha Life"가 HANWHA로 가는 것 방지 — 그 경우는 7) 앞부분 일치에서 한화생명이 먼저 잡힌다)
    if ek and len(ek) >= 8 and re.search(r"[a-z]", ek):
        hits = [r for r in reg.listed if len(norm_eng(r["corp_eng_name"])) >= max(6, 0.6 * len(ek))
                and ek.startswith(norm_eng(r["corp_eng_name"]))]
        longest = max((len(norm_eng(r["corp_eng_name"])) for r in hits), default=0)
        hits = [r for r in hits if len(norm_eng(r["corp_eng_name"])) == longest]   # 가장 길게 맞는 것 (대웅 < 대웅제약)
        if len(hits) == 1:
            return _confirm(q, "eng_name_prefix", hits[0], reg, "영문명이 정확히 같은 상장사는 없습니다.")

    # 9) 없음: 폐지 종목인지, 오타인지
    dl = [r for r in reg.delisted if norm(r["corp_name"]) == key]
    if dl:
        return _delisted(q, dl[0], reg, key)
    scored = _suggest_scored(key, reg)
    # 영문 약자(DGB, LGES 등 5글자 이하 로마자)는 한 글자만 달라도 다른 회사다(DGB ↔ DB). 오타로 묻지 않는다
    if scored and len(key) >= 3 and not re.fullmatch(r"[a-z0-9&\-]{1,5}", key):
        (best, s1), s2 = scored[0], (scored[1][1] if len(scored) > 1 else 0.0)
        # 질의의 영문 부분은 오타로 보지 않는다 (JYP엔터테인먼트 → 와이지엔터테인먼트 방지),
        # 첫 글자 초성이 다르면 다른 회사다 (공통 꼬리말 '엔터테인먼트'·'바이오'가 점수를 끌어올리는 것 방지)
        latin_ok = all(t in norm(best["corp_name"]) for t in re.findall(r"[a-z]{2,}", key))
        def first_ko(s: str) -> str:   # 앞의 영문(SK, LG)을 건너뛴 첫 한글의 초성
            m = re.search(r"[가-힣]", s)
            return _jamo(m.group(0))[:1] if m else s[:1]
        first_ok = first_ko(key) == first_ko(norm(best["corp_name"]))
        if latin_ok and first_ok and any(s1 >= th and s1 - s2 >= gap for th, gap in SUGGEST_PROMOTE):
            return _confirm(q, "typo", best, reg, "일치하는 상장사가 없어 비슷한 이름으로 찾았습니다.")
    sug = [_sug(r) for r, _ in scored]
    msg = "일치하는 상장사를 찾지 못했습니다."
    msg += (" 혹시 아래 회사 중에 있나요?" if sug else
            " 비상장사이거나 이름이 다를 수 있습니다. 정식 회사명이나 종목코드로 다시 알려 주세요.")
    return _result(q, "not_found", None, [], reg, msg, suggestions=sug)


def _delisted(q: str, row: dict, reg: Registry, key: str) -> dict:
    # 종목코드·corp_code로 들어와도 별칭 표의 합병 매핑(HD현대미포 → HD현대중공업)을 먼저 본다
    nk = norm(row["corp_name"])
    for a in reg.aliases:
        if a.get("kind") == "merged" and norm(a["alias"]) == nk and a["stock_code"] in reg.by_code:
            r = reg.by_code[a["stock_code"]]
            return _result(q, "confirm", "alias_merged", [r], reg,
                           f"{row['corp_name']}({row['stock_code']}) 종목은 지금 상장돼 있지 않습니다({a.get('note', '합병')}). "
                           f"{_with(r, '을/를')} 기준으로 볼까요?")
    merged = any(w in row.get("delist_reason", "") for w in ("합병", "해산", "완전자회사"))
    # 합병·해산으로 없어진 회사에 이름이 비슷하다는 이유로 다른 회사를 권하면 엉뚱한 곳으로 이끈다(제일화재 → 삼성화재)
    sug = [] if merged else [_sug(r) for r, _ in _suggest_scored(key, reg)]
    head = f"{row['corp_name']}({row['stock_code']}) 종목은 "
    if row.get("delist_date"):
        why = row.get("delist_reason", "")
        y, m, d = (row["delist_date"].split("-") + ["", ""])[:3]
        when = f"{int(y)}년 {int(m)}월 {int(d)}일" if y.isdigit() and m.isdigit() and d.isdigit() else row["delist_date"]
        fundlike = re.search(r"투자회사|리츠|펀드|인프라투융자|기업인수목적|스팩", row["corp_name"])   # '인프라코어'는 일반 기업
        if "해산" in why:     # KIND 표기 '해산 사유 발생': 흡수합병이 약 3/4, 나머지는 파산·청산·펀드 만기
            why = ("존속기간 만료에 따른 청산" if fundlike else
                   "회사 해산, 흡수합병·파산·청산 등으로 법인이 없어진 경우")
        msg = head + f"{when}에 상장폐지됐습니다" + (f"(사유: {why})." if why else ".")
        if merged:
            raw = row.get("delist_reason", "")
            if "합병" in raw or "완전자회사" in raw:   # KIND 원문에 합병·완전자회사가 있을 때만 이어받은 회사를 묻는다
                msg += " 합병하거나 지분을 가져간 상장사 이름을 알려 주시면 그 회사로 리포트를 만들 수 있습니다."
            else:
                msg += " 이 리포트는 상장사만 만들 수 있으니 다른 회사를 알려 주세요."
            return _result(q, "not_found", "delisted", [], reg, msg)
    else:
        msg = head + "지금 거래소에 상장돼 있지 않습니다. 상장폐지됐거나 다른 회사에 합병된 경우입니다."
    msg += " 이 리포트는 상장사만 만들 수 있습니다."
    msg += " 이름이 비슷한 상장사를 함께 보여 드리니, 이 중에 찾는 회사가 있나요?" if sug else " 다른 회사를 알려 주세요."
    return _result(q, "not_found", "delisted", [], reg, msg, suggestions=sug)


def _sug(r: dict) -> dict:
    return {"corp_name": r["corp_name"], "stock_code": r["stock_code"],
            "market_label": MARKET_LABEL.get(r.get("market", ""), "")}


_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def _jamo(s: str) -> str:
    """'삼성' → 'ㅅㅏㅁㅅㅓㅇ'. 음절 단위로 비교하면 한 글자 오타가 모두 같은 점수가 나와(삼송전자 ↔ 삼성전자·삼지전자)
    자모 단위로 비교한다."""
    out = []
    for ch in s:
        if "가" <= ch <= "힣":
            i = ord(ch) - 0xAC00
            out += [_CHO[i // 588], _JUNG[(i % 588) // 28], _JONG[i % 28].strip()]
        else:
            out.append(ch)
    return "".join(out)


def _suggest_scored(key: str, reg: Registry, n: int = 5) -> list[tuple[dict, float]]:
    """오타 후보와 자모 유사도. 두 글자 이하는 비슷한 이름이 너무 많아 제안하지 않는다."""
    if len(key) <= 2:
        return []
    pool: dict[str, list[dict]] = {}
    for k, rows in reg.by_norm.items():
        pool.setdefault(_jamo(k), []).extend(rows)
    for a in reg.aliases:
        if a["stock_code"] in reg.by_code and a.get("kind") != "unlisted":
            pool.setdefault(_jamo(norm(a["alias"])), []).append(reg.by_code[a["stock_code"]])
    kj = _jamo(key)
    out, seen = [], set()
    for jk in difflib.get_close_matches(kj, list(pool), n=n * 3, cutoff=0.7):
        score = difflib.SequenceMatcher(None, kj, jk).ratio()
        for r in pool[jk]:
            if r["corp_code"] not in seen:
                seen.add(r["corp_code"])
                out.append((r, score))
    return sorted(out, key=lambda x: -x[1])[:n]


def resolve_or_refresh(query: str, api_key: str | None = None, timeout: int = 30) -> dict:
    """resolve하고, 못 찾았거나 목록이 오래됐으면 한 번 갱신해 다시 찾는다.

    갱신은 성공이든 실패든 한 번 하면 6시간 쉰다. 비상장사·오타 질의마다 전체 목록을 다시 받지 않기 위해서다.
    """
    reg = load()
    res = resolve(query, reg)
    age = reg.age_days()
    if (res["status"] != "not_found" or res["match"] == "unlisted") and (age is None or age <= STALE_DAYS):
        return res                              # 비상장 별칭은 목록을 다시 받아도 결과가 같다
    if reg.source == "cache" and (dt.datetime.now().timestamp() - _ts(reg.meta)) < REFRESH_COOLDOWN_H * 3600:
        return res                              # 방금 갱신한 목록이다. 다시 받아도 같다
    key = api_key or _load_api_key()
    if not key:
        res["notes"].append("DART API 키가 설정돼 있지 않아 최신 상장사 목록을 받지 못했습니다. "
                            "키는 opendart.fss.or.kr에서 무료로 받을 수 있습니다.")
        res["agent"].append("~/.claude/skills/dart/.env 에 DART_API_KEY=발급받은_키 한 줄을 넣도록 안내한다.")
        return res
    marker = cache_dir() / "refresh_failed_at"
    try:   # 오프라인에서 질의마다 타임아웃을 기다리지 않도록, 실패 뒤 6시간은 다시 시도하지 않는다
        last_fail = dt.datetime.fromisoformat(marker.read_text().strip())
        if dt.datetime.now() - last_fail < dt.timedelta(hours=REFRESH_COOLDOWN_H):
            res["agent"].append(f"최근 목록 갱신이 실패했다({last_fail:%m-%d %H:%M}). 네트워크가 돌아오면 "
                                "python3 ~/.claude/skills/dart/assets/corp_registry.py --refresh 를 실행한다.")
            return res
    except (OSError, ValueError):
        pass
    try:
        refresh(key, timeout=timeout)
    except Exception as e:  # 네트워크·KRX 장애: 기존 목록으로 답한다
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(dt.datetime.now().isoformat(timespec="seconds"))
        except OSError:
            pass
        res["notes"].append(f"최신 상장사 목록을 받지 못해 {reg.generated_at[:10]} 기준 목록으로 찾았습니다.")
        res["agent"].append(f"목록 갱신 실패: {_redact(e, key)}")
        return res
    marker.unlink(missing_ok=True)
    res2 = resolve(query, load())
    res2["agent"].insert(0, "상장사 목록을 방금 DART·KRX에서 갱신했다.")
    return res2


def apply_live_check(res: dict, api_key: str | None = None) -> dict:
    """확정·확인 결과에 DART 기업개황 대조를 붙인다. 불일치면 진행하지 못하게 not_found로 바꾼다 (CLI·파이썬 공통)."""
    if not res.get("corp"):
        return res
    res["live_check"] = lc = verify_live(res["corp"], api_key=api_key)
    if lc["ok"] is False:
        res["status"], res["corp"], res["candidates"] = "not_found", None, []
        res["message"] = "회사 정보를 공시 시스템과 대조하다 어긋나는 점이 있어 진행을 멈췄습니다."
        res["agent"].append("python3 ~/.claude/skills/dart/assets/corp_registry.py --refresh 를 한 번 실행하고 다시 찾는다. "
                            f"그래도 어긋나면 사용자에게 알리고 중단한다. 사유: {lc['reason']}")
    elif lc["ok"] is None:
        res["agent"].append(f"DART 대조를 못 했다({lc['reason']}). 오프라인 결과로 진행해도 된다. Step 6 게이트가 다시 본다.")
    return res


# ───────────────────────── DART 실시간 확인 ─────────────────────────

def find_api_key() -> str | None:
    """DART API 키를 찾는 단 하나의 규칙. 모든 스크립트가 이 함수를 쓴다.

    순서: 환경변수 DART_API_KEY → 스킬 루트 .env (README가 안내하는 위치, ~/.claude/skills/dart/.env)
    → assets/.env → 현재 작업 폴더 .env.
    """
    if os.environ.get("DART_API_KEY", "").strip():
        return os.environ["DART_API_KEY"].strip()
    for p in (HERE.parent / ".env", HERE / ".env", Path.cwd() / ".env"):
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                k, _, v = line.strip().partition("=")
                if k.strip() == "DART_API_KEY" and v.strip():
                    return v.strip().strip("'\"")
        except OSError:
            continue
    return None


_load_api_key = find_api_key   # 예전 이름 (내부 호출 호환)


def _redact(e: object, key: str | None) -> str:
    s = str(e)
    if key:
        s = s.replace(key, "***")
    return re.sub(r"crtfc_key=[^&\s]+", "crtfc_key=***", s)


def verify_live(corp: dict, api_key: str | None = None, timeout: int = 15) -> dict:
    """DART company.json으로 corp_code가 정말 이 종목코드의 회사인지 확인한다."""
    import requests

    key = api_key or _load_api_key()
    if not key:
        return {"ok": None, "reason": "DART_API_KEY 없음"}
    try:
        r = requests.get(DART_COMPANY_URL, params={"crtfc_key": key, "corp_code": corp["corp_code"]},
                         timeout=timeout).json()
    except Exception as e:
        return {"ok": None, "reason": _redact(e, key)}
    if r.get("status") == "013":      # 그런 corp_code가 없다: 레지스트리가 틀렸다
        return {"ok": False, "reason": f"DART에 corp_code {corp['corp_code']}가 없다"}
    if r.get("status") != "000":      # 한도 초과·점검·키 오류는 확인 불가이지 불일치가 아니다
        return {"ok": None, "reason": f"DART status={r.get('status')} {r.get('message')}"}
    same = (r.get("stock_code") or "").strip() == corp["stock_code"]
    listed = r.get("corp_cls") in ("Y", "K", "N")     # E는 비상장·폐지
    ok = same and listed
    return {
        "ok": ok,
        "reason": "corp_code·종목코드 일치, 상장 중" if ok else
                  (f"DART 종목코드 {r.get('stock_code')!r} ≠ 레지스트리 {corp['stock_code']!r}" if not same
                   else f"DART 상장 구분 corp_cls={r.get('corp_cls')!r} (상장 종목 아님)"),
        "corp_name": r.get("corp_name"), "stock_name": r.get("stock_name"),
        "corp_cls": r.get("corp_cls"), "acc_mt": r.get("acc_mt"), "ceo_nm": r.get("ceo_nm"),
    }


# ───────────────────────── 갱신 ─────────────────────────

class _KindTable(html.parser.HTMLParser):
    """KIND '상장법인목록' 다운로드는 .xls 이름의 EUC-KR HTML 표다. pandas 없이 읽는다."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def fetch_krx_listed(timeout: int = 30) -> list[dict]:
    import requests

    r = requests.get(KIND_LIST_URL, params={"method": "download", "searchType": "13"},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
    r.raise_for_status()
    p = _KindTable()
    p.feed(r.content.decode("euc-kr", errors="replace"))
    if not p.rows or "종목코드" not in p.rows[0]:
        raise ValueError("KIND 상장법인목록 형식이 바뀌었다 (헤더에 종목코드 없음)")
    head = p.rows[0]
    out, seen = [], set()
    for row in p.rows[1:]:
        d = dict(zip(head, row))
        code = d.get("종목코드", "").strip().upper()
        if code.isdigit():
            code = code.zfill(6)
        if not re.fullmatch(r"[0-9][0-9A-Z]{5}", code) or code in seen:   # KIND 원본에 같은 종목이 두 번 실린 행이 있다
            continue
        seen.add(code)
        fm = re.sub(r"\D", "", d.get("결산월", ""))
        out.append({"stock_code": code, "name": d.get("회사명", ""), "market": d.get("시장구분", ""),
                    "sector": d.get("업종", ""), "listed_date": d.get("상장일", ""),
                    "fiscal_month": str(int(fm)) if fm else ""})
    return out


def fetch_mcap_ranks(timeout: int = 15) -> dict[str, int]:
    """코스피·코스닥 시가총액 상위 종목의 통합 순위 {종목코드: 순위}. 후보 정렬에만 쓴다 (실패해도 갱신은 계속)."""
    import requests

    vals: dict[str, float] = {}
    for market in ("KOSPI", "KOSDAQ"):
        for page in range(1, MCAP_TOP_PER_MARKET // 100 + 1):
            r = requests.get(NAVER_MCAP_URL.format(market=market), params={"page": page, "pageSize": 100},
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
            r.raise_for_status()
            for x in r.json().get("stocks", []):
                try:
                    vals[str(x["itemCode"]).upper()] = float(str(x["marketValue"]).replace(",", ""))
                except (KeyError, ValueError):
                    continue
    return {c: i + 1 for i, (c, _) in enumerate(sorted(vals.items(), key=lambda kv: -kv[1]))}


def fetch_krx_delist_reasons(timeout: int = 30) -> dict[str, tuple[str, str]]:
    """KIND 상장폐지현황: {종목코드: (폐지일, 폐지사유)}. 폐지 종목 안내 문구용 (실패해도 갱신은 계속)."""
    import requests

    out: dict[str, tuple[str, str]] = {}
    for page in range(1, 10):
        r = requests.post(KIND_DELIST_URL, data={
            "method": "searchDelCompanySub", "forward": "delcompany_down", "fromDate": "2000-01-01",
            "toDate": dt.date.today().isoformat(), "currentPageSize": "3000", "pageIndex": str(page),
            "orderMode": "2", "orderStat": "D"}, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        r.raise_for_status()
        p = _KindTable()
        p.feed(r.content.decode("euc-kr", errors="replace"))
        rows = [x for x in p.rows if len(x) >= 5 and re.fullmatch(r"[0-9][0-9A-Z]{5}", x[2])]
        for x in rows:                              # 번호 · 회사명 · 종목코드 · 폐지일자 · 폐지사유 · 비고
            out.setdefault(x[2], (x[3], x[4]))      # 최신 순이라 처음 본 것이 가장 최근 폐지
        if len(rows) < 3000:
            break
    return out


def fetch_dart_corps(api_key: str, timeout: int = 60) -> list[dict]:
    import requests
    import xml.etree.ElementTree as ET

    r = requests.get(DART_CORPCODE_URL, params={"crtfc_key": api_key}, timeout=timeout)
    r.raise_for_status()
    if not r.content.startswith(b"PK"):   # 키 오류 등은 zip 대신 JSON/XML 오류 본문이 온다
        raise ValueError(f"DART corpCode.xml 응답이 zip이 아니다: {r.content[:200]!r}")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z, z.open("CORPCODE.xml") as f:
        root = ET.parse(f).getroot()
    return [{k: (el.findtext(k) or "").strip() for k in DELISTED_COLS} for el in root.iter("list")]


def build(dart: list[dict], krx: list[dict], previous: list[dict],
          mcap: dict[str, int] | None = None, delist: dict[str, tuple[str, str]] | None = None,
          previous_delisted: list[dict] | None = None) -> tuple[list[dict], list[dict], dict]:
    """DART ∩ KRX를 stock_code로 묶는다. 이전 목록과 비교해 사명 변경을 former_names에 쌓는다.

    mcap(시가총액 순위)을 못 받았으면 이전 목록의 순위를 그대로 쓴다.
    """
    krx_by = {k["stock_code"]: k for k in krx}
    prev_by = {r["corp_code"]: r for r in previous}
    listed, delisted, seen = [], [], set()
    for d in dart:
        sc = d["stock_code"].upper()
        if not sc:
            continue
        k = krx_by.get(sc)
        if not k:
            row = {c: d[c] for c in DELISTED_COLS}
            when, why = (delist or {}).get(sc) or next(
                ((x.get("delist_date", ""), x.get("delist_reason", "")) for x in previous_delisted or []
                 if x.get("stock_code") == sc), ("", ""))
            row.update(delist_date=when, delist_reason=why)
            delisted.append(row)
            continue
        if sc in seen:      # 같은 종목코드가 두 corp_code에 걸리면 KRX 회사명과 맞는 쪽, 그다음 최근 수정본
            prev = next(x for x in listed if x["stock_code"] == sc)
            new_key = (norm(d["corp_name"]) == norm(k["name"]), d["modify_date"])
            old_key = (norm(prev["corp_name"]) == norm(k["name"]), prev["modify_date"])
            if new_key <= old_key:
                continue
            listed.remove(prev)
        seen.add(sc)
        p = prev_by.get(d["corp_code"], {})
        former = [x for x in (p.get("former_names") or "").split("|") if x]
        if p.get("corp_name") and p["corp_name"] != d["corp_name"] and p["corp_name"] not in former:
            former.append(p["corp_name"])
        if k["name"] and norm(k["name"]) != norm(d["corp_name"]) and k["name"] not in former:
            former.append(k["name"])        # KRX 표기 이름도 찾을 수 있게 둔다
        former = [x for x in former if x != d["corp_name"]]
        listed.append({
            "corp_code": d["corp_code"], "corp_name": d["corp_name"], "corp_eng_name": d["corp_eng_name"],
            "stock_code": sc, "market": k["market"], "sector": k["sector"], "listed_date": k["listed_date"],
            "fiscal_month": k["fiscal_month"], "former_names": "|".join(former),
            "mcap_rank": str(mcap[sc]) if mcap and sc in mcap else ("" if mcap else p.get("mcap_rank", "")),
            "modify_date": d["modify_date"],
        })
    listed.sort(key=lambda r: r["stock_code"])
    delisted.sort(key=lambda r: r["stock_code"])
    matched = {r["stock_code"] for r in listed}
    meta = {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "sources": {"dart": DART_CORPCODE_URL, "krx": KIND_LIST_URL + "?method=download&searchType=13",
                    "mcap_rank": NAVER_MCAP_URL.format(market="KOSPI|KOSDAQ")},
        "counts": {"dart_all": len(dart), "krx_listed": len(krx), "listed": len(listed),
                   "delisted": len(delisted),
                   "by_market": {m: sum(r["market"] == m for r in listed) for m in MARKET_RANK}},
        "krx_without_dart": sorted(k["stock_code"] + " " + k["name"] for k in krx if k["stock_code"] not in matched),
    }
    return listed, delisted, meta


def _write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.chmod(tmp, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def check_aliases(listed: list[dict], aliases: list[dict]) -> list[str]:
    """별칭 표의 종목코드가 아직 상장돼 있고, 적어 둔 회사명이 지금 이름(또는 옛 이름)과 같은지."""
    by = {r["stock_code"]: r for r in listed}
    names_norm = {norm(r["corp_name"]) for r in listed}   # 다른 회사 정식명과 같은 별칭은 둘 다 후보로 보인다
    problems, seen = [], set()
    for a in aliases:
        k = norm(a["alias"])
        # 같은 별칭이 서로 다른 회사를 가리키는 행은 일부러 둔 것이다(한화테크윈·티웨이·엔솔): 둘 다 후보로 묻는다
        if (k, a.get("stock_code", "")) in seen:
            problems.append(f"별칭 '{a['alias']}' → {a.get('stock_code')}: 같은 행이 이미 있음 (중복)")
            continue
        seen.add((k, a.get("stock_code", "")))
        r = by.get(a["stock_code"])
        if r and k in names_norm and norm(r["corp_name"]) == k:   # 정식명과 같은 별칭은 하는 일이 없다
            problems.append(f"별칭 '{a['alias']}': 대상 회사의 정식명과 같음 (삭제 대상)")
            continue
        if a.get("kind", "nickname") not in ("nickname", "former", "merged", "unlisted", "brand", "group"):
            problems.append(f"별칭 '{a['alias']}': kind는 nickname·former·merged·unlisted·brand·group 중 하나")
        if a.get("kind") in ("unlisted", "merged", "brand") and re.search(r"[()]", a.get("note", "")):
            problems.append(f"별칭 '{a['alias']}': note가 안내 문장의 괄호 안에 들어가니 괄호를 쓰지 않는다")
        if a.get("kind") == "unlisted":      # 비상장사: 종목코드는 비워 두거나 관련 상장사(모회사)를 적는다
            if k in names_norm:
                problems.append(f"별칭 '{a['alias']}': unlisted인데 같은 이름의 상장사가 있음")
            if a.get("stock_code") and not r:
                problems.append(f"별칭 '{a['alias']}' → {a['stock_code']}: 관련 상장사가 상장 목록에 없음")
            continue
        if not r:
            problems.append(f"별칭 '{a['alias']}' → {a['stock_code']}: 상장 목록에 없음")
            continue
        names = {r["corp_name"], *[x for x in r.get("former_names", "").split("|") if x]}
        if a.get("corp_name") and a["corp_name"] not in names:
            problems.append(f"별칭 '{a['alias']}' → {a['stock_code']}: 적힌 이름 '{a['corp_name']}' ≠ 현재 '{r['corp_name']}'")
    return problems


def refresh(api_key: str | None = None, bundle: bool = False, timeout: int = 60) -> dict:
    """DART·KRX에서 다시 받아 캐시(기본) 또는 번들에 쓴다. 이상하면 쓰지 않고 예외를 낸다."""
    key = api_key or _load_api_key()
    if not key:
        raise RuntimeError("DART_API_KEY가 환경변수나 .env에 없다.")
    try:
        dart = fetch_dart_corps(key, timeout=timeout)
        krx = fetch_krx_listed(timeout=timeout)
    except Exception as e:
        raise RuntimeError(_redact(e, key)) from None
    try:
        mcap = fetch_mcap_ranks()
    except Exception:   # 정렬 보조 데이터일 뿐이다. 이전 순위를 유지한다
        mcap = None
    try:
        delist = fetch_krx_delist_reasons()
    except Exception:   # 안내 문구용. 이전 사유를 유지한다
        delist = None
    current = load()
    listed, delisted, meta = build(dart, krx, current.listed, mcap, delist, current.delisted)
    meta["delist_reasons"] = sum(bool(r["delist_reason"]) for r in delisted)
    meta["mcap_ranked"] = sum(bool(r["mcap_rank"]) for r in listed)

    # 반쪽 응답 방어: 건수가 갑자기 줄거나 KRX 대비 매칭률이 낮으면 기존 목록을 지킨다
    prev_n = (current.meta.get("counts") or {}).get("listed")   # 메타 없는 옛 번들은 폐지 종목이 섞여 있어 쓰지 않는다
    floor = max(2000, int(prev_n * 0.9)) if prev_n else 2000
    if len(listed) < floor:
        raise RuntimeError(f"갱신 결과가 비정상적으로 적다: {len(listed)}건 (하한 {floor}). 기존 목록 유지.")
    if len(listed) < 0.97 * len(krx):
        raise RuntimeError(f"KRX {len(krx)}건 중 {len(listed)}건만 DART와 맞물렸다. 기존 목록 유지.")

    meta["alias_problems"] = check_aliases(listed, _read_csv(ALIASES))
    out = HERE if bundle else cache_dir()
    _write_csv(out / "corp_codes_listed.csv", listed, LISTED_COLS)
    _write_csv(out / "corp_codes_delisted.csv", delisted, DELISTED_OUT_COLS)
    (out / "corp_codes_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not bundle:   # 전체 기업 목록(비상장 포함)은 캐시에만 둔다 (dart_client.find_corp용)
        _write_csv(out / "corp_codes_all.csv", dart, DELISTED_COLS)
    meta["written_to"] = str(out)
    return meta


# ───────────────────────── CLI ─────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="상장사 이름·종목코드 → DART corp_code")
    ap.add_argument("query", nargs="?", help="회사명, 약칭, 옛 이름, 영문명, 종목코드, corp_code")
    ap.add_argument("--verify", action="store_true", help="확정되면 DART company.json으로 한 번 더 확인")
    ap.add_argument("--offline", action="store_true", help="못 찾아도 목록을 갱신하지 않는다")
    ap.add_argument("--refresh", action="store_true", help="DART+KRX에서 목록을 다시 받는다")
    ap.add_argument("--bundle", action="store_true", help="--refresh 결과를 저장소 번들(assets/)에 쓴다")
    ap.add_argument("--status", action="store_true", help="현재 목록의 출처·날짜·건수")
    a = ap.parse_args(argv)

    def emit(obj) -> None:
        print(json.dumps(obj, ensure_ascii=False, indent=2))

    if a.refresh:
        try:
            meta = refresh(bundle=a.bundle)
        except Exception as e:
            emit({"ok": False, "error": str(e)})
            return 1
        emit({"ok": True, **{k: meta[k] for k in ("generated_at", "counts", "alias_problems", "written_to")},
              "krx_without_dart": meta["krx_without_dart"][:20]})
        return 0 if not meta["alias_problems"] else 4
    if a.status or not a.query:
        reg = load()
        emit({"source": reg.source, "generated_at": reg.generated_at, "age_days": reg.age_days(),
              "listed": len(reg.listed), "delisted": len(reg.delisted), "aliases": len(reg.aliases),
              "stale": (reg.age_days() or 0) > STALE_DAYS})
        return 0
    res = resolve(a.query) if a.offline else resolve_or_refresh(a.query)
    if a.verify:
        apply_live_check(res)
    emit(res)
    return {"ok": 0, "confirm": 2, "ambiguous": 2, "not_found": 3}[res["status"]]


if __name__ == "__main__":
    sys.exit(main())
