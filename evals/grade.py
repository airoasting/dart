#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evals.json의 빠른 조회 평가를 기계적으로 채점한다 (skill-creator 형식 grading.json).

    python3 evals/grade.py <iteration 폴더>      # 예: output/skill-eval/iteration-2

각 실행 폴더(<eval>/<config>/run-N/outputs/answer.md, notes.md)를 읽어 assertion마다 passed·evidence를 남긴다.
정답값은 evals.json과 같은 2026-10-08 실측이다. 새 보고서가 나오면 evals.json과 함께 고친다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# API를 직접 부르는 코드를 짰다는 흔적 (도구 대신 DartClient·requests·엔드포인트 URL을 직접 쓴 경우)
ADHOC = re.compile(r"DartClient|dart_client\.py[^\n]*(?:직접|import)|\._get\(|get_financial_statements|requests\.get|"
                   r"직접 (?:작성|쓴 스크립트)[^\n]*\.py|ratios\.py|exctv\.py|kakao_holders")


def find(text: str, pat: str) -> str | None:
    m = re.search(pat, text)
    return text[max(0, m.start() - 30): m.end() + 30].replace("\n", " ") if m else None


def check_all(text: str, pats: list[str]) -> tuple[bool, str]:
    ev = [find(text, p) for p in pats]
    miss = [p for p, e in zip(pats, ev) if not e]
    return (not miss, "모두 찾음: " + " / ".join(e for e in ev if e) if not miss else f"못 찾음: {miss}")


def check_any(text: str, pats: list[str]) -> tuple[bool, str]:
    for p in pats:
        e = find(text, p)
        if e:
            return True, f"찾음: …{e}…"
    return False, f"못 찾음: {pats}"


def no_adhoc(notes: str, outputs: Path) -> tuple[bool, str]:
    py = [p.name for p in outputs.glob("*.py")]
    hit = find(notes, ADHOC.pattern)
    if py or hit:
        return False, f"직접 짠 코드 흔적: {py or ''} {('…' + hit + '…') if hit else ''}".strip()
    used = find(notes, r"mcp_server\.py --call|share_top_holders|people_executives|fin_ratios|fin_key_accounts")
    return True, f"도구로 조회: …{used}…" if used else "직접 짠 API 코드 흔적 없음"


def order_check(text: str, first: str, last: str, names: list[str]) -> tuple[bool, str]:
    pos = {n: text.find(n) for n in names}
    if any(v < 0 for v in pos.values()):
        return False, f"이름 누락: {[n for n, v in pos.items() if v < 0]}"
    seq = sorted(names, key=pos.get)
    return seq[0] == first and seq[-1] == last, f"처음 등장 순서: {seq}"


NAMES = ["전영현", "노태문", "김용관", "신제윤", "김준성", "허은녕", "조혜경", "이혁재"]

RULES = {
    "kakao-holders-change": {
        "period": lambda a, n, o: check_all(a, [r"2026", r"반기|2026[.-]06|6월 30일"]),
        "ratio": lambda a, n, o: check_all(a, [r"24\.10", r"23\.99"]),
        "direction": lambda a, n, o: check_any(a, [r"줄었|감소"]),
        "shares": lambda a, n, o: check_any(a, [r"106,622,933[\s\S]{0,200}106,281,442", r"341,491"]),
        "link": lambda a, n, o: check_any(a, [r"rcpNo=20260819000055"]),
        "no_adhoc_code": lambda a, n, o: no_adhoc(n, o),
    },
    "small-cap-ratios": {
        "debt_ratio": lambda a, n, o: check_any(a, [r"39\.6\d", r"39\.7"]),
        "roe": lambda a, n, o: check_all(a, [r"4\.(?:0[5-9]|1\d?)\d*\s*%", r"평균|기말|재무지표|DART가"]),
        "basis": lambda a, n, o: check_all(a, [r"별도|개별", r"연결"]),
        "period": lambda a, n, o: check_all(a, [r"2025", r"사업보고서|2025[.-]12|FY25"]),
        "link": lambda a, n, o: check_any(a, [r"rcpNo=20260309001568"]),
        "no_adhoc_code": lambda a, n, o: no_adhoc(n, o),
    },
    "samsung-board-terms": {
        "all_members": lambda a, n, o: check_all(a, NAMES),
        "sorted": lambda a, n, o: order_check(a, "조혜경", "김용관", NAMES),
        "role": lambda a, n, o: check_all(a, [r"사내이사", r"독립이사|사외이사"]),
        "period": lambda a, n, o: check_all(a, [r"반기보고서", r"2026[.-]06[.-]30|2026년 6월 30일|2026\.06"]),
        "link": lambda a, n, o: check_any(a, [r"rcpNo=20260814003699"]),
        "no_adhoc_code": lambda a, n, o: no_adhoc(n, o),
    },
}


def main(it_dir: str) -> int:
    root = Path(it_dir)
    evals = {e["name"]: e for e in json.loads((Path(__file__).parent / "evals.json").read_text())["evals"]}
    for ev_dir in sorted(root.glob("eval-*")):
        name = next(n for n in evals if ev_dir.name.endswith(n))
        configs = sorted(p for p in ev_dir.iterdir() if p.is_dir())
        runs = [r for c in configs for r in (sorted(c.glob("run-*")) or [c])]   # <config>/run-N/ 또는 <config>/
        for run in runs:
            out = run / "outputs"
            ans = (out / "answer.md").read_text() if (out / "answer.md").exists() else ""
            notes = (out / "notes.md").read_text() if (out / "notes.md").exists() else ""
            exps = []
            for a in evals[name]["assertions"]:
                ok, evid = RULES[name][a["id"]](ans, notes, out)
                exps.append({"text": a["text"], "passed": bool(ok), "evidence": evid})
            n_ok = sum(e["passed"] for e in exps)
            grading = {"expectations": exps,
                       "summary": {"passed": n_ok, "failed": len(exps) - n_ok, "total": len(exps),
                                   "pass_rate": round(n_ok / len(exps), 2)}}
            (run / "grading.json").write_text(json.dumps(grading, ensure_ascii=False, indent=2))
            label = f"{run.parent.name}/{run.name}" if run.name.startswith("run-") else run.name
            print(f"{ev_dir.name:<34} {label:<18} {n_ok}/{len(exps)}  "
                  + " ".join(("✓" if e["passed"] else "✗") for e in exps))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
