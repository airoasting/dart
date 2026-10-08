#!/usr/bin/env python3
"""DART 공시 원문을 텍스트로 꺼내 검색어 주변만 보여 준다 (A2b 부문 조사·V2b 검증 에이전트용).

dart.fss.or.kr 뷰어 페이지(dsaf001/main.do?rcpNo=...)는 프레임과 스크립트로 그려져서 WebFetch로는 목차만 보인다.
같은 공시를 OpenDART document.xml로 받으면 본문 표까지 텍스트로 나온다.

    python3 dart_text.py <rcpNo 또는 뷰어 URL> 영업부문 위탁매매
    python3 dart_text.py 20260810000423 "영업부문에 대한 공시" --width 900

공시 표는 보통 천원·백만원 단위다. 억원과 비교할 때 천원은 100,000으로, 백만원은 100으로 나눠 반올림한다.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def rcept_no(s):
    m = re.search(r"(\d{14})", s)
    if not m:
        sys.exit(f"접수번호(14자리)를 찾지 못했다: {s}")
    return m.group(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="접수번호(rcpNo) 또는 DART 뷰어 URL")
    ap.add_argument("terms", nargs="*", help="찾을 말. 없으면 앞부분만 보여 준다")
    ap.add_argument("--width", type=int, default=600, help="검색어 뒤로 보여 줄 글자 수")
    ap.add_argument("--max", type=int, default=3, help="검색어마다 보여 줄 최대 건수")
    a = ap.parse_args()

    from verify_report import fetch_provisional_text
    try:
        text = fetch_provisional_text(rcept_no(a.src))
    except Exception as e:  # 네트워크·키·압축 오류를 한 줄로
        sys.exit(f"원문을 받지 못했다: {type(e).__name__}: {e}")

    if not a.terms:
        print(text[: a.width])
        return
    for t in a.terms:
        hits = [m.start() for m in re.finditer(re.escape(t), text)][: a.max]
        print(f"=== {t}: {len(hits)}건" + ("" if hits else " (없음)"))
        for i in hits:
            print(text[max(0, i - 80): i + a.width])
            print("---")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
