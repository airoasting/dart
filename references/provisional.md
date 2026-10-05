# 잠정실적 리포트 (정기보고서가 아직 없을 때)

`assemble_report.py facts`가 "재무제표를 받지 못했다"며 멈췄고, 사용자가 **아직 정기보고서가 나오지 않은 최신 분기**를 원할 때만 이 경로를 쓴다. 그렇지 않으면 `assemble_report.py period`가 고른 직전 분기로 만드는 편이 낫다. 정기보고서 숫자가 더 많고(재무상태·부문), 조립 스크립트가 숫자를 대신 계산해 주기 때문이다.

사용자에게 먼저 묻는다: "이 분기 정기보고서는 아직 제출 전입니다. 잠정실적 공시로 만들까요, 직전 분기 정기보고서로 만들까요?"

## 순서

1. 잠정실적 공시 찾기:
   ```python
   import sys, pathlib
   sys.path.insert(0, str(pathlib.Path("~/.claude/skills/dart/assets").expanduser()))
   from dart_client import DartClient
   r = DartClient().list_disclosures(corp_code, bgn_de="<분기말 YYYYMMDD>", end_de="<오늘>", page_count=100)
   # report_nm에 "잠정"이 든 항목의 rcept_no
   ```
   없으면 사용자에게 알리고 직전 분기로 할지 묻는다.
2. 원문 읽기: `verify_report.fetch_provisional_text(rcept_no)`가 원문 텍스트를 준다. 매출·영업이익·순이익의 당기·전년동기 값을 읽는다.
3. B·C 에이전트에게 넘길 사실을 facts 출력과 같은 형식으로 직접 쓴다(예: `"매출 17,479억 → 19,421억 (+1,942억, +11.1%)"`). 재무상태와 주가 줄은 빼거나, 주가는 `python3 ~/.claude/skills/dart/assets/price.py <종목코드>`로 채운다(웹 검색 주가는 쓰지 않는다. 게이트가 KRX 일봉으로 대조한다).
4. 리서치 에이전트(A1·A2·B·C)와 검증(V1·V2)은 SKILL.md Step 4와 같다.
5. data.json은 조립 스크립트 대상이 아니다. `~/.claude/skills/dart/assets/data.example.json`을 복사해 값만 바꾼다. meta 키는 하나도 빼지 않는다(빌더가 미치환 토큰으로 멈춘다). 조각 파일(A1·A2·B·C·V1·V2)의 내용은 `js`와 `audit.web`·`audit.claims`에 옮긴다. 조립 스크립트가 대신 만들던 값은 직접 채운다: `js.CONS`는 ANALYSTS의 의견을 센 값, `meta.coverage_note`는 "표의 N개 증권사 기준 (전체 커버리지 집계는 미확인)", `js.DELTA`는 SEGS의 부문별 차이와 합계, CHIPS의 `dot`은 cls에 맞춰 `var(--coral)`·`var(--grn)`·`var(--dn)`. `audit.src`에는 아래 다섯 키가 모두 있어야 게이트가 돈다:
   ```json
   "src": {"corp_code": "<8자리>", "year": "<사업연도>", "reprt_code": "<분기 코드>", "kind": "provisional", "rcept_no": "<잠정실적 공시 번호>"}
   ```
   결산월이 12월이 아니면 `"fiscal_month": <결산월>`을, 연간 실적이면 `"scope": "annual"`을 함께 넣는다(게이트가 분기 라벨을 이 값으로 맞춘다). 게이트는 원문에서 매출·영업이익·순이익 숫자를 찾는다.
6. 이후 게이트·빌드는 SKILL.md와 같다. 이 경로에서만 고칠 때 data.json을 직접 고친다.

헤더 기준 문구(`meta.basis`)에 "잠정실적 기준"을 밝힌다. 조립 스크립트가 하던 표기 규칙도 직접 지킨다: 적자가 낀 증감은 %가 아니라 "흑자 전환"·"적자 전환"·"적자 축소"·"적자 확대"(게이트가 확인한다), 재무상태는 1조 미만이면 억 단위.

## 이 경로에서만 생기는 문제

| 증상 | 원인 | 해결 |
|---|---|---|
| 게이트 B층 전년동기 불일치 | 작년 보고서 숫자를 씀 | 잠정실적 공시 원문의 전년 동기 값을 쓴다 |
| 빌더 "미치환 토큰"(exit 1) | meta 키 누락 | `data.example.json`의 meta 키를 빠짐없이 옮긴다 |
| 빌더 경고 "페르소나 13인 아님" | PERSONAS 개수 | B.json의 13인을 모두 옮긴다 |
| 차트가 안 그려짐 | `js` 배열이 비었거나 필드명 오타 | `data.example.json`과 필드명 대조 |
