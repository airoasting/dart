#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_report.py — DART 리포트 빌더

정적 보일러플레이트(template.html)에 데이터(data.json)만 주입해 최종 HTML을 만든다.
LLM은 더 이상 1,400줄 HTML을 재생성하지 않는다. 데이터 JSON만 만들고 이 스크립트를 부른다.

사용법:
    python3 build_report.py <data.json> [-o <output_dir>] [--stdout]

data.json 구조:
    {
      "meta": { "name": "...", "code": "...", ... 스칼라 토큰 ... ,
                "filter_cats": [["platform","플랫폼"], ...] },
      "js":   { "SEGS":[...], "TOT25":..., "DELTA":[...], "ANALYSTS":[...], "PERSONAS":[...], ... }
    }

동작:
  1. js 객체의 모든 키를 `const KEY = <json>;` 로 직렬화해 /*__REPORT_DATA__*/ 위치에 주입
  2. meta.filter_cats → 세그먼트 필터 버튼 HTML 생성 → {{filter_buttons}}
  3. meta 나머지 → {{token}} 치환
  4. 검증: 미치환 {{...}} / __REPORT_DATA__ 잔존 여부, 페르소나 13인 등
  5. output/{종목명}_{YYYYMMDD}_{NN}.html 로 저장
"""
import sys, os, re, json, html, datetime, argparse, pathlib

# js 객체를 선언할 순서 (함수보다 먼저 정의돼야 하는 것들). 목록에 없는 키는 뒤에 알파벳순으로.
JS_ORDER = ["NAME", "CONS", "CHIPS", "SEGS", "TOT25", "TOT26", "DELTA", "CURR",
            "ANALYSTS", "BULLS", "BEARS", "NEWS", "PERSONAS"]


def js_literal(v):
    """파이썬 값 → JS 리터럴 (JSON은 유효한 JS 표현식)."""
    return json.dumps(v, ensure_ascii=False)


def build_data_block(js):
    keys = [k for k in JS_ORDER if k in js] + sorted(k for k in js if k not in JS_ORDER)
    lines = []
    for k in keys:
        lines.append(f"const {k} = {js_literal(js[k])};")
    return "\n".join(lines)


def build_filter_buttons(meta):
    cats = meta.get("filter_cats", [])
    btns = ['<button class="cb active" onclick="setF(\'all\',this)">전체</button>']
    for cat_id, label in cats:
        btns.append(f'<button class="cb" onclick="setF(\'{cat_id}\',this)">{label}</button>')
    # 원본 들여쓰기(6칸)와 동일하게 정렬
    return "\n      " + "\n      ".join(btns) + "\n    "


def render(template, data):
    meta = dict(data.get("meta", {}))
    js = data.get("js", {})

    # 1. 데이터 블록 주입
    assert "/*__REPORT_DATA__*/" in template, "template에 /*__REPORT_DATA__*/ 마커가 없습니다"
    out = template.replace("/*__REPORT_DATA__*/", build_data_block(js))

    # 2. 필터 버튼
    out = out.replace("{{filter_buttons}}", build_filter_buttons(meta))
    meta.pop("filter_cats", None)

    # 3. 스칼라 토큰 치환 (긴 토큰 먼저 → 부분 겹침 방지)
    for token in sorted(meta.keys(), key=len, reverse=True):
        out = out.replace("{{" + token + "}}", str(meta[token]))

    return out


def validate(out, js):
    problems = []
    leftovers = re.findall(r"\{\{[a-zA-Z0-9_]+\}\}", out)
    if leftovers:
        problems.append(f"미치환 토큰: {sorted(set(leftovers))}")
    if "/*__REPORT_DATA__*/" in out:
        problems.append("데이터 블록이 주입되지 않았습니다")
    n_persona = len(js.get("PERSONAS", []))
    if n_persona != 13:
        problems.append(f"페르소나가 13인이 아닙니다: {n_persona}인")
    for req in ["SEGS", "ANALYSTS", "NEWS", "PERSONAS", "DELTA"]:
        if not js.get(req):
            problems.append(f"필수 데이터 누락 또는 비어있음: {req}")
    # chart.js 버전 가드 (스킬 절대 규칙)
    if "chart.js@4.4.4" not in out:
        problems.append("Chart.js 4.4.4 로드 태그가 없습니다")
    return problems


def next_output_path(out_dir, corp_name, today):
    out_dir.mkdir(parents=True, exist_ok=True)
    pat = re.compile(rf"^{re.escape(corp_name)}_{today}_(\d{{2}})\.html$")
    used = [int(m.group(1)) for f in out_dir.iterdir() if (m := pat.match(f.name))]
    nn = f"{max(used) + 1:02d}" if used else "01"
    return out_dir / f"{corp_name}_{today}_{nn}.html"


def main():
    here = pathlib.Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="DART 리포트 빌더 (template + data → HTML)")
    ap.add_argument("data", help="데이터 JSON 경로")
    ap.add_argument("-t", "--template", default=str(here / "template.html"),
                    help="템플릿 경로 (기본: assets/template.html)")
    ap.add_argument("-o", "--out-dir", default="output", help="출력 디렉터리 (기본: ./output)")
    ap.add_argument("--stdout", action="store_true", help="파일 저장 대신 표준출력으로")
    ap.add_argument("--date", default=None, help="파일명 날짜 YYYYMMDD (기본: 오늘)")
    args = ap.parse_args()

    data = json.loads(pathlib.Path(args.data).read_text(encoding="utf-8"))
    template = pathlib.Path(args.template).read_text(encoding="utf-8")

    # 기준일(base_date)은 항상 빌드 실행일(= 스킬 돌린 오늘)로 스탬프. 주가(전일 종가)와 별개다.
    _run = args.date or datetime.date.today().strftime("%Y%m%d")
    data.setdefault("meta", {})["base_date"] = f"{_run[:4]}.{_run[4:6]}.{_run[6:]}"

    out = render(template, data)

    problems = validate(out, data.get("js", {}))
    if problems:
        sys.stderr.write("⚠️  검증 경고:\n" + "\n".join("  - " + p for p in problems) + "\n")
        # 미치환 토큰/데이터 미주입은 치명적 → 중단
        fatal = [p for p in problems if "미치환" in p or "주입되지" in p]
        if fatal:
            sys.exit(1)

    if args.stdout:
        sys.stdout.write(out)
        return

    corp_name = data["meta"]["name"]
    today = args.date or datetime.date.today().strftime("%Y%m%d")
    path = next_output_path(pathlib.Path(args.out_dir), corp_name, today)
    path.write_text(out, encoding="utf-8")
    print(f"✅ 생성 완료: {path}  ({len(out.splitlines())} lines)")


if __name__ == "__main__":
    main()
