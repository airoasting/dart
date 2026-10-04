---
name: dart
description: 상장사의 DART 공시 재무 데이터를 조회해 인터랙티브 애널리스트 HTML 리포트를 생성한다. 사용자가 "DART 리포트", "실적 리포트 만들어줘", "○○ 실적 분석 HTML", "○○ 대시보드", "/dart ○○" 같은 표현을 쓰면 반드시 발동한다. 기업명·분기를 파악해 DART API로 재무 데이터를 수집하고, 13인 투자자 페르소나 평가를 포함한 HTML 파일을 output/ 폴더에 생성한다.
---

# DART 애널리스트 리포트 스킬

상장사의 DART 재무·공시 데이터를 수집해 인터랙티브 HTML 리포트를 생성한다.
KPI 차트 · 성장 기여도 · 사업별 매출 · 애널리스트 시각 · 공시 뉴스 · 13인 투자자 페르소나(6개 섹션)를 포함한다.

## ⚡ 핵심 원리 — HTML을 직접 쓰지 마라

리포트 HTML은 **약 1,190줄 중 1,100줄 이상이 모든 리포트에서 동일한 보일러플레이트**(CSS·차트 코드·레이아웃)다. 기업마다 바뀌는 건 데이터뿐이다.

그래서 이 스킬은 HTML을 **다시 생성하지 않는다.** 대신:

1. `assets/template.html` — 보일러플레이트가 고정된 템플릿 (건드리지 않는다)
2. **너의 일** — 리서치 에이전트를 돌려 조각 파일을 모으고, `assets/assemble_report.py`로 `data.json`을 조립한다 (숫자는 스크립트가 계산한다)
3. `assets/verify_report.py` — **숫자 검증 게이트.** data.json의 모든 숫자를 원천과 다시 대조한다. PASS 전에는 빌드되지 않는다
4. `assets/build_report.py` — 템플릿 + data.json → 최종 HTML (결정론적, 1초)

HTML 전체를 토큰 단위로 뱉던 과거 방식은 한 리포트에 10분이 걸렸다. 지금 구조의 실측은 NAVER 2Q26 **5분 00초**다(이전 구조의 현대자동차는 8분 24초). 전체 시간은 가장 느린 리서치 에이전트(증권사·부문, 약 4분)와 그 출처 검증(약 1분)이 정한다. 나머지 단계(사실 뽑기·조립·게이트·빌드)는 모두 합쳐 10초 남짓이다. 절대 `template.html`을 복붙해 손으로 채우지 마라. 반드시 빌더를 써라.

---

## 전체 흐름 (한눈에)

1. 입력 해석, 종목 확정, DART 재무 수집 — Step 1~4
2. `assemble_report.py facts`로 숫자를 뽑고, 뉴스·증권사·부문·페르소나·강세약세를 **서브에이전트로 병렬** 수집. 각 에이전트가 조각 파일을 직접 쓰고, 출처 검증은 리서치가 끝나는 대로 겹쳐 돈다 — Step 4~4.5
3. `assemble_report.py build`가 조각과 검증 장부를 합쳐 `data.json`을 만든다(meta 숫자는 스크립트가 계산) — Step 5
4. `verify_report.py` 숫자 검증 게이트. FAIL이면 고쳐서 재검증, **최대 3회차** — Step 6
5. PASS 후 `build_report.py` 실행 → `output/`에 HTML, 경로를 사용자에게 전달 — Step 7~8

---

## 파일 구조

```
dart/
├── SKILL.md                          ← 이 파일 (워크플로우)
├── assets/
│   ├── template.html                 ← 고정 보일러플레이트 (수정 금지)
│   ├── verify_report.py              ← 숫자 검증 게이트 (빌드 전 필수, 최대 3회차)
│   ├── assemble_report.py            ← 사실 뽑기(facts) · 조각+검증 장부 → data.json 조립(build)
│   ├── build_report.py               ← data.json + template → HTML 빌더 (게이트 PASS 확인)
│   ├── data.example.json             ← 데이터 계약(스키마) + 카카오 예시 ★반드시 참고
│   ├── dart_client.py                ← DartClient 클래스 (재시도·키 가림)
│   ├── corp_registry.py              ← 종목 찾기: 이름·약칭·코드 → corp_code (Step 2)
│   ├── corp_codes_listed.csv         ← 현재 KRX 상장사 (DART ∩ KIND, 시장·결산월·옛 이름 포함)
│   ├── corp_codes_delisted.csv       ← 폐지·이전 종목 (안내 문구용)
│   ├── corp_codes_meta.json          ← 목록 생성 시각·건수
│   ├── corp_aliases.csv              ← 약칭 → 종목코드 (사람이 관리)
│   ├── price.py                      ← 전일 종가·52주 (KRX, 웹검색 대신 필수)
│   └── html2pdf.py                   ← 리포트 HTML → PDF (인쇄용 보정 포함)
├── tests/                            ← 종목 찾기·조립 회귀 테스트 (오프라인, 93개)
├── investor_persona/
│   ├── _ALL.md                       ← 13인 페르소나 통합본 (이 파일 하나만 읽어라)
│   └── *.md                          ← 개별 원본 (참고용)
└── references/                       ← 사람용 설계 문서 (런타임에 읽을 필요 없음)
    ├── dart-api.md                   ← DART API 엔드포인트·응답 구조
    ├── design-system.md              ← CSS 설계 (이미 template.html에 반영됨)
    └── section-templates.md          ← HTML/JS 설계 (이미 template.html에 반영됨)
```

**경로 규칙**: 스킬 루트를 `SKILL_DIR`로 표기한다. 실제 경로는 `~/.claude/skills/dart/`이다.

---

## 사전 준비 (시작 전 필독)

**`SKILL_DIR/assets/data.example.json` 한 파일만** 읽으면 된다. 만들어야 할 데이터의 정확한 형태(스키마)이자 카카오 실제 예시다. 이 구조를 그대로 복사해 값만 바꾼다. 스크립트(`corp_registry.py`·`dart_client.py`·`price.py`)는 이 문서에 적힌 대로 부르기만 하고 소스를 읽지 않는다.

DART API 세부 응답이 헷갈릴 때만 `references/dart-api.md`를 편다. `design-system.md`·`section-templates.md`는 이미 `template.html`에 녹아 있으니 **런타임에 읽지 마라** (토큰·시간 낭비).

DART API 키: 프로젝트 `.env` (`DART_API_KEY=...`) 또는 환경변수에서 자동 로드. 키가 없으면 `.env` 위치와 설정법을 안내하고 중단한다.

---

## 동작 순서

### Step 1. 입력 파싱

| 항목 | 처리 |
|------|------|
| **기업명** | 정식명·약칭(현대차·삼전)·옛 이름·영문명·종목코드(우선주 포함)·corp_code 모두 허용. 해석은 Step 2가 한다 |
| **분기** | 명시 없으면 최근 분기 자동 판단 (아래) |

최근 분기 자동 판단 (공시 지연 45일 고려, **12월 결산 법인 기준**):

| 현재 날짜 | 사용 분기 | reprt_code |
|-----------|-----------|------------|
| 1/1 ~ 2/14 | 전년 3Q | 11014 |
| 2/15 ~ 5/14 | 전년 4Q (사업보고서) | 11011 |
| 5/15 ~ 8/14 | 당해 1Q | 11013 |
| 8/15 ~ 11/14 | 당해 2Q (반기) | 11012 |
| 11/15 ~ 12/31 | 당해 3Q | 11014 |

### Step 2. 기업 코드 조회

이름 부분일치로 직접 찾지 마라. "현대차"는 현대차증권으로, "네이버"는 0건으로 빠진다. 반드시 레지스트리를 쓴다:

```bash
python3 ~/.claude/skills/dart/assets/corp_registry.py "<사용자가 쓴 이름 그대로>" --verify
```

출력 JSON은 두 갈래의 문장을 준다.
- `message`·`notes`: **사용자에게 보여 줄 문장.** 자연스럽게 다듬어 전해도 되지만 뜻은 바꾸지 않는다. `notes`는 하나도 빼지 않는다.
- `agent`: **너에게 주는 지시.** 사용자에게 보여 주지 말고 그대로 따른다.

`status`별 행동 (종료코드 0·2·3):

| status | 뜻 | 행동 |
|---|---|---|
| `ok` | 한 회사로 확정됨 (종목코드·정식명·약칭·옛 이름·영문명) | `corp`로 진행한다. 묻지 않는다. **단 `agent`에 멈추라거나 물으라는 지시가 있으면 그것이 먼저다** (리츠·스팩) |
| `confirm` | 후보가 하나지만 확신할 수 없음 (부분일치, 오타, 앞자리 0이 빠진 코드, 합병으로 사라진 회사) | `message`로 묻고 답을 기다린다 |
| `ambiguous` | 후보가 여럿 | `message`를 전하고 `candidates`의 `display`를 그대로 번호 목록으로 보여 준다(회사명·종목코드·시장, 사용자가 옛 이름으로 물었으면 그 옛 이름까지 들어 있다) |
| `not_found` | 상장사에 없음 (비상장·폐지·오타) | `message`를 전하고, `suggestions`가 있으면 번호 목록으로 붙인다(문구는 `message`에 이미 있다). 사용자가 다시 말할 때까지 멈춘다 |

**사용자가 후보(`candidates`)나 제안(`suggestions`) 중 하나를 고르거나 `confirm`에 "맞다"고 답하면, 고른 회사의 종목코드로 위 명령을 한 번 더 실행한다.** 그래야 그 회사의 `notes`·`agent`(리츠·스팩·코넥스·결산월 안내)가 붙는다. 다시 실행한 결과는 `ok`가 나오므로 아래 확인 항목으로 간다. 이때 `message`("찾았습니다")는 다시 전하지 않고 `notes`만 전한다.

`confirm`에 "아니다"라고 답하면 정식 회사명이나 종목코드를 다시 물어보고, 답을 받으면 처음부터 다시 찾는다.

"LG그룹"처럼 그룹을 말하면 `ambiguous`로 후보가 나온다. 현대차·한진그룹은 별칭 표의 계열 상장사이고, 그 밖의 그룹은 **이름이 같은 말로 시작하는 상장사**라 계열사가 아닌 회사가 섞일 수 있다(롯데관광개발). `message`가 그렇게 밝히니 덧붙여 "계열사"라고 부르지 않는다. 그룹 리포트는 없으니 한 곳을 고르게 한다.

사용자가 "삼성전자랑 하이닉스"처럼 두 회사 이상을 말하면 `match: "multiple"`인 `ambiguous`가 나온다(후보는 말한 순서). 한 회사를 고르게 하고, 그 리포트를 끝낸 뒤 나머지도 만들지 묻는다.

사용자가 "삼성전자 주가", "현대차 3분기 실적 어때?"처럼 말해도 그대로 넣으면 된다. 덧붙인 말은 레지스트리가 뗀다. 기간 표현("3분기")은 Step 1이 원래 문장에서 이미 읽었으니 그 값을 그대로 쓴다.

`--verify`의 `live_check`부터 본다:
- **`ok`가 `false`** (status가 `not_found`로 바뀌고 `corp`가 비워진다): 아직 사용자에게 아무것도 전하지 말고 `--refresh`를 **한 번** 한 뒤 같은 이름으로 다시 찾는다. 다시 찾은 결과를 위 표대로 처리한다. 두 번째도 false면 그때 `message`를 전하고 멈춘다.
- **`ok`가 `null`** (DART 접속 불가): 그대로 진행한다. Step 6 게이트가 다시 확인한다.

`corp`가 정해진 뒤 확인할 것:
- **`corp.kind`**: `reit`·`fund`이면 `message`가 이미 "만들 수 없다"는 안내다. 전하고 멈춘다(결산 주기·실적 구조가 달라 분기 비교가 성립하지 않는다). `spac`이면 `notes`의 질문을 전하고 원할 때만 진행한다.
- **`corp.market == "코넥스"`**: 분기·반기보고서 제출 의무가 없다. `client.latest_periodic_report(corp_code, fiscal_month, annual_only=True)`로 최신 사업보고서를 찾고 `audit.src.scope="annual"`로 연간 리포트를 만든다(반기보고서를 자진 제출한 코넥스사도 연간으로 통일한다).
- **`corp.fiscal_month != 12`** (리츠·펀드·스팩을 빼면 34개사): Step 1의 달력 표를 쓰지 않는다. `client.latest_periodic_report(corp_code, fiscal_month)`가 가장 최근 정기보고서의 `bsns_year`·`reprt_code`·`period_end`·`label`을 준다.
  - DART의 bsns_year는 보고서 기준월의 연도다. 3월 결산 1Q는 "분기보고서 (2025.06)" → 2025·11013, 4Q는 "사업보고서 (2026.03)" → 2026·11011.
  - **라벨은 회계연도가 시작한 해로 단다**(업계 관행). 위 회계연도(2025.04~2026.03)는 1Q~4Q 모두 `25`다: `meta.q_cur_short`=`label`(예 `1Q25`), `q_prev_short`는 연도만 1 뺀다. `meta.period_full`에 기간(예 `FY25 1Q (2025.04~06)`)을 밝힌다.
  - `audit.src.fiscal_month`를 넣는다. 게이트가 이 값으로 라벨과 4Q 역산(3Q 연도)을 맞춘다.

확정된 `corp`의 세 값을 data.json에 그대로 옮긴다: `meta.name` = `corp_name`, `meta.code` = `stock_code`, `audit.src.corp_code` = `corp_code`. Step 6 게이트가 이 셋이 지금 상장된 한 회사인지 대조한다. 이 게이트는 **식별자 일관성**을 본다. 사용자가 뜻한 회사가 맞는지는 이 단계의 확인 질문이 책임진다.

목록은 번들(`assets/corp_codes_listed.csv`)을 쓰고, 30일이 지났거나 못 찾으면 DART·KRX에서 한 번 갱신해 캐시(`~/.cache/dart-skill/`)에 둔 뒤 다시 찾는다. 갱신은 성공이든 실패든 6시간에 한 번만 한다. 수동 갱신은 `corp_registry.py --refresh`, 상태는 `--status`.

파이썬에서 부를 때: `DartClient().resolve_corp("현대차", verify=True)` (반환과 상태 전환이 CLI와 같다).

### Step 3. DART 데이터 수집

```python
import sys
sys.path.insert(0, str(SKILL_DIR/'assets'))
from dart_client import DartClient
client = DartClient()
```

| 데이터 | 메서드 |
|--------|--------|
| 기업 개황 | `client.company(corp_code)` |
| 재무제표(연결) | `client.get_financial_statements(corp_code, year, reprt_code, 'CFS')` |
| 전년 동기 | 동일, `year-1` |
| 배당 | `client.get_dividend(corp_code, year, reprt_code)` |

재무제표 응답의 `status`는 이 순서로 처리한다.

1. `000`: 정상. Step 4로 간다.
2. 연결(`CFS`)이 `013`(데이터 없음): 개별(`OFS`)로 다시 부른다. 성공하면 차트 제목에 "(개별)"을 붙이고 `audit.src.fs_div="OFS"`.
3. 개별도 `013`: 그 분기 정기보고서가 아직 안 나왔다. **잠정실적 폴백**으로 간다. `client.list_disclosures(corp_code, bgn_de=<분기말>, end_de=<오늘>, page_count=100)`에서 공시명에 "잠정"이 든 것의 `rcept_no`를 찾고, `verify_report.fetch_provisional_text(rcept_no)`로 원문 텍스트를 받아 매출·영업이익·순이익을 읽는다. `audit.src`에 `kind:"provisional"`, `rcept_no`를 넣는다. 잠정실적도 없으면 사용자에게 알리고 직전 분기로 할지 묻는다.
4. 그 밖의 status: 오류 코드와 뜻(`references/dart-api.md` 표)을 알리고 중단한다. `020`·`800`은 `DartClient`가 이미 두 번 더 시도한 결과다.

> **병렬로 보내라.** 당해·전년 재무, 개황 등 DART 호출은 서로 독립적이니 한 메시지에서 동시에 호출한다. 순차로 기다리지 마라.

### Step 4. 사실 뽑기 — `assemble_report.py facts`

```bash
python3 ~/.claude/skills/dart/assets/assemble_report.py facts --corp-code <corp_code> --year <YYYY> --reprt <reprt_code>
# 선택: --fs-div OFS · --scope annual · --np-basis parent · --fiscal-month 3
```

매출·영업이익·순이익(전년 → 당기, 증감액, YoY, OPM/NPM), 재무상태 4개 계정(조), 주가·52주를 **게이트와 같은 표기**의 문장으로 준다. 1초 안쪽이다. 이 출력을 B·C 에이전트에게 그대로 넘긴다. 직접 파싱하거나 다시 계산하지 마라.

이 스크립트는 게이트의 `verify_report.fetch_dart`를 쓴다. 그래서 전년 동기는 이번 보고서의 재작성치(`frmtrm_q_amount`), 사업보고서(11011)는 4Q 단독(연간 − 3Q 누적), 비12월 결산은 `--fiscal-month`로 3Q 사업연도를 맞춘 값이 나온다. 핵심 계정이 없으면 여기서 멈추고 이유를 알려 준다(게이트를 통과할 수 없는 경우다).

### Step 4.5. 병렬 리서치와 출처 검증 ⚡ 속도 핵심

조각 폴더를 하나 정한다(예: `output/<종목명>_parts/`). **한 메시지에서 아래 4개 에이전트를 `run_in_background`로 동시에** 띄운다. 각 에이전트는 결과를 **조각 파일에 직접 쓰고** "done"만 답한다. 메인이 결과를 옮겨 적지 않는다.

| 에이전트 | 모델 | 넘겨줄 입력 | 쓸 파일 |
|---|---|---|---|
| **A1. 뉴스** | Sonnet | 기업명·종목코드·분기 | `A1.json` = `{"NEWS": [5건]}` |
| **A2. 증권사·부문** | Sonnet | 기업명·종목코드·분기·facts의 전년/당기 매출 | `A2.json` = `{"ANALYSTS": [5곳], "CONS", "coverage_note", "SEGS", "filter_cats"}` |
| **B. 페르소나** | **Opus** | facts 출력 | `B.json` = PERSONAS 13인 배열 (`_ALL.md` 직접 읽고 평가) |
| **C. 강세·약세** | Sonnet | facts 출력 | `C.json` = `{"BULLS": 5, "BEARS": 5, "CHIPS": 3~4}` |

**출처 검증은 리서치와 겹쳐 돌린다.** A1이 끝났다는 알림이 오면 곧바로 검증 에이전트 **V1**(Sonnet)을, A2가 끝나면 **V2**를 띄운다. 나머지 에이전트를 기다리지 않는다. 검증 에이전트는 작성한 에이전트와 달라야 한다.

| 검증 | 입력 | 쓸 파일 |
|---|---|---|
| **V1** | `A1.json` | `V1.json` = `{"web": [NEWS 항목별], "claims": []}` |
| **V2** | `A2.json` | `V2.json` = `{"web": [ANALYSTS·SEGS(est:false) 항목별], "claims": []}` |

검증 항목 형식과 규칙:

```json
{"sec": "ANALYSTS", "key": "하나증권", "status": "corrected", "url": "<원문 URL>", "note": "08.24 하향", "patch": {"tp": 50000}}
{"sec": "NEWS", "key": "<기사 URL>", "status": "confirmed", "url": "<기사 URL>"}
{"sec": "SEGS", "key": "톡비즈", "status": "confirmed", "url": "<IR URL>"}
```

- 원문을 직접 열어 본 것만 `confirmed`다. 검색 결과 요약만 봤거나 링크가 열리지 않으면 `unverified`. 확인하지 않은 항목을 `confirmed`로 적는 것은 게이트 전체를 무력화하므로 금지한다.
- 고칠 것이 있으면 `corrected`와 함께 **`patch`에 바뀐 필드와 값**을 넣는다(ANALYSTS는 `firm`, NEWS는 `url`, SEGS는 `name`으로 찾는다). 조립 스크립트가 그대로 반영하므로 메인이 다시 고치지 않는다. 원문에서 확인되지 않은 인용문은 note를 확인된 사실로 바꾸는 patch를 낸다.
- `claims`: C·B의 문장에 재무제표로 계산되지 않는 숫자가 있을 때만 `{"text": "본문 표기 그대로", "url", "status"}`.

에이전트에게 줄 공통 규칙:
- 파일에는 사람용 설명 없이 **순수 JSON**만 쓴다(Write 도구).
- A1·A2는 검색을 순차로 돌리지 말고 한 메시지에 여러 `WebSearch`/`WebFetch`를 몰아 보낸다. 할당량(뉴스 5건, 증권사 5곳)을 채우면 검색을 멈춘다.
- A1 뉴스: 실적발표 전후 2주 내 국내 신문사 기사 5건. 우선 매체는 한국경제·이데일리·전자신문·파이낸셜뉴스·서울경제·뉴스1·아이뉴스24·뉴시스. **검색에서 확인된 실제 URL만** 쓴다(추측 URL·네이버 검색 URL 금지). `body`의 숫자는 기사에 있는 것만. `sent`: 상회·긍정=`pos`, 급감·하락·규제=`neg`, 혼재=`mix`.
- A2 증권사·부문: 아래 "데이터 생성 가이드"의 애널리스트·사업별 매출 규칙을 넘긴다. 직전 목표가(`from`)를 원문에서 못 찾으면 `null`로 둔다. `note`에는 원문에서 확인한 사실만 쓰고 확인 안 된 인용문은 넣지 않는다. `SEGS`의 `q25`·`q26` 합계는 facts의 전년·당기 매출과 같아야 한다(차이는 연결조정 행으로).
- B·C: facts에 있는 숫자만 facts에 적힌 표기 그대로 쓴다. 새로 계산한 숫자는 게이트 C층에서 걸린다.

**모델 선택** (`Agent`의 `model` 파라미터): 검색·추출·구조화 서술인 A1·A2·C·V1·V2는 Sonnet, 13인의 판단 규칙을 데이터에 적용하는 B만 Opus. 실측(현대자동차 2Q26)에서 웹 리서치가 전체 시간의 병목이었다.

서브에이전트를 못 쓰는 환경이면 메인이 차례로 하되, 웹 검색만은 한 메시지에 몰아 병렬로 보낸다.

### Step 5. `data.json` 조립 — `assemble_report.py build`

A1·A2·B·C·V1·V2 파일이 모두 생기면:

```bash
python3 ~/.claude/skills/dart/assets/assemble_report.py build --corp-code <corp_code> --year <YYYY> --reprt <reprt_code> \
    --parts <조각 폴더> -o output/<종목명>_data.json
# 비12월 결산은 --fiscal-month와 --period-note "FY25 1Q (2025.04~06)"을 더한다
```

스크립트가 하는 일: meta의 모든 숫자(실적·증감·이익률·성장 기여도·기간 라벨·주가·목표가 범위·컨센 비율)를 DART·KRX에서 계산해 채운다. `DELTA`는 `SEGS`에서 만든다. 검증 장부를 `audit`에 합치고 `patch`를 본문에 반영한다. meta 키·페르소나 13인·SEGS 합계를 확인하고, 어긋나면 이유를 찍고 멈춘다. 메인은 data.json을 손으로 쓰지 않는다. 고칠 것이 생기면 조각 파일을 고치고 다시 조립한다.

데이터 계약(구조)은 `data.example.json`이 정본이다. **`q25`·`q26`·`TOT25`·`TOT26`은 연도가 아니라 "전년 동기·당기"를 뜻하는 고정 키 이름이다.** 2027년 리포트에서도 이름을 바꾸지 않는다.

| 키 | 내용 | 규칙 |
|----|------|------|
| `CHIPS` | KPI 인사이트 칩 3~4개 | `{cls:'co'|'gn'|'dn', dot, txt}` |
| `SEGS` | 사업부문별 매출 | `{name,sub,cat,q25,q26,est}` · Y축은 자동 계산됨 |
| `ANALYSTS` | 증권사 리포트 5곳 | `{firm,r:'Buy'|'Hold'|'Sell',tp,from,date,note}` (+조각에는 `url`). `from`은 직전 목표가이고, 원문에 없으면 `null`로 둔다(화면에 '미확인'). 지어내지 않는다 |
| `BULLS`/`BEARS` | 각 5개 | `{t,d}` |
| `NEWS` | 5건 | `{h,src,date,sent,url,body}` |
| `PERSONAS` | **정확히 13인** | `{name,type,rating:'buy'|'hold'|'sell',desc,eval}` |

`audit.src` 선택 키는 조립 스크립트 옵션과 같다: `np_basis: "parent"`(지배주주순이익 표기), `scope: "annual"`(연간 리포트, 코넥스는 항상), `fiscal_month`(비12월 결산). 잠정실적 폴백(`kind: "provisional"`, `rcept_no`)은 조립 스크립트 대상이 아니라 data.example.json 구조대로 손으로 만든다.

### Step 6. 숫자 검증 게이트 ★ 빌드 전 필수

```bash
python3 ~/.claude/skills/dart/assets/verify_report.py <data.json 경로>
```

세 층을 대조한다. 숫자는 하나라도 틀리면 FAIL이다.

| 층 | 대조 대상 | 정답 |
|---|---|---|
| A 산술 | YoY·증감액·OPM/NPM·방향, TOT ↔ 부문 합계, DELTA ↔ 부문 차이, g_net/up/dn, 컨센 %, 업사이드 | 재계산값 |
| B 원천 | 종목명 ↔ 종목코드 ↔ corp_code가 지금 상장된 한 회사인지(폐지 corp_code·비상장 구분 포함), 매출·영업이익·순이익 당기/전년(재작성치), 분기 라벨, 종가·등락률·52주 | 상장사 레지스트리, DART 기업개황·재무 재조회, KRX 일봉 |
| C 출처 | 증권사·부문·뉴스·컨센의 `audit.web` 기록, 목표가 범위, 서술 속 모든 `억·조·%·pp·원·만·배` 숫자 | A·B에서 나온 값 또는 `audit.claims` |

종료 코드와 행동:

| 결과 | 코드 | 행동 |
|---|:---:|---|
| ✅ PASS | 0 | Step 7 빌드로 간다 |
| ❌ FAIL | 1 | 찍힌 항목을 모두 고치고 다시 실행한다 |
| ⛔ BLOCKED | 2 | **멈춘다.** 사용자에게 보고한다 (아래) |
| ⚠️ INCOMPLETE | 3 | 네트워크 장애. 회차를 쓰지 않았다. 한 번 더 실행하고, 또 실패하면 사용자에게 알린다 |

**회차 규칙 (무한 반복 방지)**
- data.json 내용이 바뀐 채 실행할 때만 1회차를 쓴다. **최대 3회차**(첫 검증 + 수정 2번)다. 3회차에도 FAIL이면 BLOCKED로 잠긴다.
- 회차가 귀하니 **한 회차에 찍힌 불일치를 전부** 고친다. 하나 고치고 돌리고를 반복하지 마라.
- 숫자 하나를 고치면 그 숫자를 인용한 문장(CHIPS·BULLS·BEARS·페르소나 `eval`)도 같이 고친다. 게이트는 서술 속 숫자도 대조한다.
- 정답은 원천(DART·KRX·원문)이다. 원천에 맞춰 data.json을 고친다. 확인할 수 없는 숫자는 지어내지 말고 문장에서 빼거나, 부문은 `est:true`, 증권사는 note에 `(추정)`을 붙인다.

**BLOCKED일 때**: 자동 수정을 멈추고 `<data>.verify.md`의 남은 불일치 표를 그대로 보여 준 뒤 사용자에게 묻는다.
1. 사용자가 값을 확인해 준다 → 반영 후 `verify_report.py <data> --reset`으로 재검증
2. 미통과 표시를 붙여 빌드한다 → `build_report.py <data> --allow-unverified` (리포트 상단에 경고 배너)
3. 이번 리포트를 중단한다

`--reset`과 `--allow-unverified`는 **사용자가 그 선택지를 고른 경우에만** 쓴다. 스스로 쓰지 마라.

산출물: `<data>.verify.json`(게이트 상태, 빌더가 읽는다)과 `<data>.verify.md`(회차 기록·불일치·통과 목록). `--status`로 현재 상태만 볼 수 있다.

### Step 7. 빌드

```bash
cd <프로젝트 루트>          # output/ 이 생길 위치
python3 ~/.claude/skills/dart/assets/build_report.py <data.json 경로>
```

빌더가 하는 일:
- **게이트 확인**: `verify.json`이 PASS이고 그 뒤로 data.json이 바뀌지 않았을 때만 빌드한다. 아니면 exit 2로 멈춘다
- 헤더 기준일 옆에 "숫자 검증 통과 (N개 항목 · R회차)"를 찍는다
- `js` 전체를 `const` 선언으로 주입, `meta` 토큰 치환, 세그먼트 필터 버튼 생성
- 검증: 미치환 토큰·데이터 누락·**페르소나 13인**·Chart.js 4.4.4 로드 확인 (실패 시 경고/중단)
- `output/{종목명}_{YYYYMMDD}_{NN}.html` 저장 (같은 날 재실행 시 NN 자동 증가)

`--stdout`으로 파일 대신 표준출력, `-o <dir>`로 출력 폴더 지정 가능.

### Step 8. 확인·전달

빌더가 성공(✅)하면 **생성된 파일 경로를 사용자에게 알린다**(가능하면 열어서 보여준다). 빌더가 경고를 내면 그 항목만 `data.json`에서 고쳐 **Step 6 검증부터 다시** 한다(내용이 바뀌면 PASS가 풀리고 회차를 하나 쓴다). 숫자와 무관한 빌더 경고로 회차를 쓰지 않도록, Step 6 전에 `meta` 키가 `data.example.json`과 빠짐없이 같은지 먼저 맞춘다. **HTML을 직접 수정하지 마라** — 항상 data.json → 빌드.

### Step 9. PDF 변환 (요청 시에만)

사용자가 PDF나 인쇄본을 요청하면 전용 변환기를 쓴다. HTML을 그냥 인쇄하면 안 된다.

```bash
python3 ~/.claude/skills/dart/assets/html2pdf.py output/카카오_20260704_01.html
python3 ~/.claude/skills/dart/assets/html2pdf.py output/*.html -o output/pdf
```

리포트는 화면용이라 섹션이 스크롤할 때 나타나고(IntersectionObserver), KPI 카드는 지연 애니메이션으로 뜨고, 차트는 Chart.js가 CDN에서 내려온 뒤 그려진다. 브라우저의 인쇄 스냅샷은 이 셋 중 어느 것도 기다려주지 않아서, 그냥 인쇄하면 절반이 빈 페이지로 나온다. `html2pdf.py`는 인쇄 직전에 숨은 섹션을 펼치고 차트를 무애니메이션으로 다시 그린 뒤 A4로 굽는다. 데이터 테이블도 함께 펼쳐 숫자를 지면에 남긴다.

**추가 설치는 필요 없다.** 엔진은 세 단계로 자동 선택된다.

| 순위 | 엔진 | 조건 | 결과 |
|:---:|------|------|------|
| 1 | Playwright | `pip install playwright` 완료 | A4 + 페이지 번호 꼬리말 |
| 2 | 시스템 Chrome/Edge/Brave | 브라우저가 깔려 있음 (대부분) | A4, 페이지 번호 없음 |
| 3 | 수동 | 위 둘 다 없음 | 브라우저에서 `Cmd+P`, 인쇄 설정에서 "배경 그래픽" 켜기 |

3번이 가능한 이유는 `template.html`에 인쇄 보정과 `beforeprint` 훅이 들어 있기 때문이다. 즉 **스킬을 설치한 사람은 아무것도 더 깔지 않아도 PDF를 뽑을 수 있다.** 엔진을 직접 고르려면 `--engine playwright|chrome`을 쓴다.

`wkhtmltopdf`나 `weasyprint`는 쓰지 마라. 둘 다 이 리포트가 쓰는 CSS 변수, `:has()`, Canvas 차트를 처리하지 못한다.

---

## 데이터 생성 가이드 (섹션별)

### 사업별 매출 (`SEGS`) — 에이전트 A 담당
1. DART 정기보고서 본문 "사업부문별 영업실적"(연결 분기 매출) 우선 → 없으면 IR 자료 → 역산 시 `est:true`. 부문 합계는 `TOT25`·`TOT26`(총매출)과 맞아야 한다(게이트 A층).
2. `cat`은 필터 그룹 키(예: `platform`/`content`/`other`). `meta.filter_cats`에 표시할 필터 버튼 `[["platform","플랫폼"],...]`를 명시(전체 버튼은 자동). 세그먼트 2개 미만이면 `filter_cats: []`.

### 주가 — 항상 전일 종가 (`CURR`, `meta.price`·`price_chg`·`w52_range`·`tp_cur`)
웹 검색 현재가는 출처마다 값이 달라 부정확하다(카카오는 실측 대비 10% 틀린 적도 있다). **주가는 웹 검색을 쓰지 말고 반드시 `assets/price.py`로 가져온다**(Naver 금융 KRX 일봉):

```bash
python3 ~/.claude/skills/dart/assets/price.py <종목코드>
# → {"date_dot":"2026.07.03","close":35500,"change_pct":0.71,"w52_range":"32,250 ~ 71,600", ...}
```

매핑:
- `js.CURR` = `close` (숫자) · `meta.price` = `close`(콤마) · `meta.tp_cur` = `close`+"원"
- `meta.price_chg` = `"{change_pct:+}% (M/D 종가)"` (M/D는 `date` 기준 = 전일 종가 날짜)
- `meta.base_date`는 넣지 않아도 된다 — **빌더가 실행일(오늘)로 자동 스탬프**한다(전일 종가 날짜와 별개)
- `meta.w52_range` = `w52_range`
- `meta.tp_upside` = `(tp_avg-close)/close` 로 재계산

`CURR`은 애널리스트 표의 Upside `(tp-CURR)/CURR` 계산에 쓰인다. `price.py`가 실패하면(네트워크 장애) 다른 소스로 채우지 말고 잠시 뒤 다시 실행한다. 게이트가 같은 KRX 일봉으로 대조하므로 다른 소스 값은 통과하지 못한다.

### 애널리스트 (`ANALYSTS`, `CONS`, `meta.tp_*`)
**증권사는 5곳**이다. 실적 발표 뒤 가장 최근 보고서를 낸 곳부터 고르되, 의견이 다른 곳(보유·매도)이나 목표가를 크게 올린 곳이 있으면 5곳 안에 넣는다. 5곳을 채우면 검색을 멈춘다(리서치 시간의 대부분이 증권사 찾기다). `CONS`는 전체 커버리지 집계(리스트에 안 실린 곳 포함 가능), `meta.coverage_note`·`cons_*_pct`와 정합. 목표가 범위는 `meta.tp_low/tp_avg/tp_high/tp_upside`에 넣는다. 불확실하면 note에 "(추정)".

### Bull/Bear (`BULLS`/`BEARS`)
DART 공시+개황+재무 기반, 각 5개. 주술 정합, em dash 없음, 투자 권유 배제.

### 13인 투자자 페르소나 (`PERSONAS`)
`SKILL_DIR/investor_persona/_ALL.md` **한 파일만** 읽어 13인의 철학·판단 규칙을 적용한다(개별 파일 13개를 따로 읽지 마라 — 통합본이 있다). 각 인물의 `Anti-Hallucination Rules`를 따르고, 실제 의견이 아닌 AI 시뮬레이션임을 유지한다. `rating`은 `buy`/`hold`/`sell`, `eval`은 2문장 이내.

---

## 오류 처리

| 상황 | 처리 |
|------|------|
| 매출·영업이익·순이익 중 하나가 DART에 없음 | 게이트 B층을 통과할 수 없다. `assemble_report.py facts`가 멈추며 알려 준다. 사용자에게 알리고 중단한다 |
| 그 밖의 계정 없음 | 해당 `meta` 값 "데이터 없음", 나머지 정상 |
| API 전체 실패 | 오류 코드+해결법 안내 후 중단 |
| CFS 없음 | OFS 재시도, 제목에 "(개별)" |
| status=013 | Step 3의 처리 순서 (OFS → 잠정실적 → 사용자 확인) |
| status=020·800 | `DartClient`가 1초·3초 쉬고 두 번 더 시도한다. 그래도 020이면 일일 한도(2만 건) 초과다. 내일 다시 하거나 다른 키를 쓴다 |
| 종목 `confirm`·`ambiguous` | 묻고 기다린다 (Step 2). 추측해서 고르지 않는다 |
| 종목 `not_found` | `message`·`suggestions`를 전하고 사용자가 다시 말할 때까지 멈춘다 (Step 2) |
| 빌더 "숫자 검증 게이트 미통과" | Step 6 `verify_report.py`를 먼저 돌린다. PASS 뒤 data.json을 고쳤다면 다시 검증 |
| 게이트 BLOCKED | 3회차 소진. 자동 수정 중단, 사용자에게 `verify.md` 보고 후 선택을 받는다 |
| 빌더 "미치환 토큰" 경고 | `data.json`의 `meta`에 그 키 추가 후 재빌드 |
| 빌더 "페르소나 13인 아님" | `PERSONAS` 배열을 13개로 맞춤 |
| 세그먼트 데이터 부족 | 대표 항목만 채우고 `est:true` |

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 빌더가 exit 1 | 미치환 토큰 또는 데이터 미주입 | 경고에 찍힌 키를 `data.json`에 채운다 |
| 차트가 안 그려짐 | 해당 `js` 배열이 비었거나 필드명 오타 | `data.example.json`과 필드명 대조 |
| 값이 화면과 안 맞음 | `meta` 텍스트와 `js` 숫자 불일치 | 게이트 A층이 잡는다. `verify.md`의 항목대로 동기화 |
| 게이트 "B 식별" 불일치 | 다른 회사의 corp_code나 종목코드를 씀 | Step 2를 다시 돌려 `corp`의 세 값을 그대로 옮긴다. 숫자를 그 회사 것으로 다시 모은다 |
| 종목을 못 찾음 (신규 상장·사명 변경) | 목록이 오래됨 | `corp_registry.py --refresh` 뒤 다시 찾는다 |
| 게이트 B층 전년동기 불일치 | 작년 보고서 숫자를 씀 | 이번 보고서의 `frmtrm_q_amount`(재작성치)를 쓴다 |
| 게이트 C층 "데이터에서 나오지 않는 숫자" | 서술에 출처 없는 숫자 | 계산 오류면 고치고, 기사 숫자면 `audit.claims`에 출처, 확인 불가면 숫자를 뺀다 |
| API 키 실패 | `.env` 위치/형식 | 프로젝트 루트 `DART_API_KEY=...` 한 줄 |
| 템플릿을 고치고 싶다 | 디자인 변경 필요 | `template.html` 수정은 신중히. 이후 `data.example.json`으로 회귀 테스트(빌드→렌더) |
| PDF가 절반쯤 빈 페이지 | 브라우저 인쇄로 직접 뽑음 | Step 9의 `html2pdf.py`를 쓴다 (`Cmd+P`는 배경 그래픽 켜기 필요) |
| PDF에 차트만 빠짐 | Chart.js CDN 차단·오프라인 | 네트워크 확인. 끊긴 상태에서도 데이터 테이블은 지면에 남는다 |
| `Chart is not defined` | 위와 같음 | 리포트는 나머지 섹션을 그대로 그린다. 차트 자리에 안내 문구가 뜬다 |
| `html2pdf.py` 실행 실패 | Playwright도 Chrome도 없음 | 브라우저에서 `Cmd+P` (배경 그래픽 켜기). 또는 `pip install playwright && python3 -m playwright install chromium` |
| PDF에 페이지 번호가 없다 | 시스템 Chrome 폴백으로 변환됨 | Playwright를 설치하면 꼬리말이 붙는다 |

---

## 변경 내역

트리거 표현은 위 frontmatter `description`에 있다. 아키텍처 전환·버그 수정 등 전체 변경 내역과 그 배경은 [`OPTIMIZATION.md`](OPTIMIZATION.md)에 문제→해결→효과로 정리돼 있다.
