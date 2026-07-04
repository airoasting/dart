---
name: dart
description: 상장사의 DART 공시 재무 데이터를 조회해 인터랙티브 애널리스트 HTML 리포트를 생성한다. 사용자가 "DART 리포트", "실적 리포트 만들어줘", "○○ 실적 분석 HTML", "○○ 대시보드", "/dart ○○" 같은 표현을 쓰면 반드시 발동한다. 기업명·분기를 파악해 DART API로 재무 데이터를 수집하고, 13인 투자자 페르소나 평가를 포함한 HTML 파일을 output/ 폴더에 생성한다.
---

# DART 애널리스트 리포트 스킬

상장사의 DART 재무·공시 데이터를 수집해 인터랙티브 HTML 리포트를 생성한다.
KPI 차트 · 성장 기여도 · 사업별 매출 · 주가 반응 · 애널리스트 시각 · 공시 뉴스 · 13인 투자자 페르소나를 포함한다.

## ⚡ 핵심 원리 — HTML을 직접 쓰지 마라

리포트 HTML은 **1,300줄 중 약 1,200줄이 모든 리포트에서 동일한 보일러플레이트**(CSS·차트 코드·레이아웃)다. 기업마다 바뀌는 건 데이터뿐이다.

그래서 이 스킬은 HTML을 **다시 생성하지 않는다.** 대신:

1. `assets/template.html` — 보일러플레이트가 고정된 템플릿 (건드리지 않는다)
2. **너의 일** — 재무 데이터를 모아 `data.json` 하나를 쓴다 (약 200줄)
3. `assets/build_report.py` — 템플릿 + data.json → 최종 HTML (결정론적, 1초)

HTML 전체를 토큰 단위로 뱉던 과거 방식은 한 리포트에 10분이 걸렸다. 데이터만 쓰면 출력량이 1/10로 줄어 **2분 안쪽**이면 끝난다. 절대 `template.html`을 복붙해 손으로 채우지 마라. 반드시 빌더를 써라.

---

## 파일 구조

```
dart/
├── SKILL.md                          ← 이 파일 (워크플로우)
├── assets/
│   ├── template.html                 ← 고정 보일러플레이트 (수정 금지)
│   ├── build_report.py               ← data.json + template → HTML 빌더
│   ├── data.example.json             ← 데이터 계약(스키마) + 카카오 예시 ★반드시 참고
│   ├── dart_client.py                ← DartClient 클래스
│   └── corp_codes_listed.csv         ← 3,963개 상장사 오프라인 조회
├── investor_persona/
│   ├── _ALL.md                       ← 13인 페르소나 통합본 (이 파일 하나만 읽어라)
│   └── *.md                          ← 개별 원본 (참고용)
├── references/                       ← 사람용 설계 문서 (런타임에 읽을 필요 없음)
│   ├── dart-api.md                   ← DART API 엔드포인트·응답 구조
│   ├── design-system.md              ← CSS 설계 (이미 template.html에 반영됨)
│   └── section-templates.md          ← HTML/JS 설계 (이미 template.html에 반영됨)
└── kakao_20260510.html               ← ground-truth 참고 출력 (열어볼 필요 거의 없음)
```

**경로 규칙**: 스킬 루트를 `SKILL_DIR`로 표기한다. 실제 경로는 `~/.claude/skills/dart/`이다.

---

## 사전 준비 (시작 전 필독)

아래 **두 파일만** 읽으면 된다:

1. **`SKILL_DIR/assets/data.example.json`** — 만들어야 할 데이터의 정확한 형태(스키마)이자 카카오 실제 예시. 이 구조를 그대로 복사해 값만 바꾼다.
2. **`SKILL_DIR/assets/dart_client.py`** — DartClient 클래스 (데이터 수집용)

DART API 세부 응답이 헷갈릴 때만 `references/dart-api.md`를 편다. `design-system.md`·`section-templates.md`는 이미 `template.html`에 녹아 있으니 **런타임에 읽지 마라** (토큰·시간 낭비).

DART API 키: 프로젝트 `.env` (`DART_API_KEY=...`) 또는 환경변수에서 자동 로드. 키가 없으면 `.env` 위치와 설정법을 안내하고 중단한다.

---

## 동작 순서

### Step 1. 입력 파싱

| 항목 | 처리 |
|------|------|
| **기업명** | 한글·영문·종목코드 모두 허용 |
| **분기** | 명시 없으면 최근 분기 자동 판단 (아래) |

최근 분기 자동 판단 (공시 지연 45일 고려):

| 현재 날짜 | 사용 분기 | reprt_code |
|-----------|-----------|------------|
| 1/1 ~ 2/14 | 전년 3Q | 11014 |
| 2/15 ~ 5/14 | 전년 4Q (사업보고서) | 11011 |
| 5/15 ~ 8/14 | 당해 1Q | 11013 |
| 8/15 ~ 11/14 | 당해 2Q (반기) | 11012 |
| 11/15 ~ 12/31 | 당해 3Q | 11014 |

### Step 2. 기업 코드 조회

`assets/corp_codes_listed.csv` (3,963개 상장사, 네트워크 불필요)에서 먼저 검색:

```python
import pandas as pd
from pathlib import Path
SKILL_DIR = Path('~/.claude/skills/dart').expanduser()
df = pd.read_csv(SKILL_DIR/'assets'/'corp_codes_listed.csv',
                dtype={'corp_code': str, 'stock_code': str}).fillna('')
hits = df[df['corp_name'].str.contains(keyword, na=False)]
```

- 1개 히트 → 사용 / 복수 히트 → 회사명+종목코드 목록 제시 후 선택 대기 / 0개 → DART API `company.json` 재검색, 그래도 없으면 중단.

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

연결(CFS) 없으면 개별(OFS) 재시도 → 차트 제목에 "(개별)" 표기. `status != '000'`이면 메시지 알리고 중단.

**status=013(잠정) 폴백**: 분기 보고서가 미공시면 같은 분기 **잠정실적 공시**(공시명에 "실적(잠정)"/"잠정실적")의 `rcept_no`를 찾아 `document.xml` ZIP을 내려받아 정규식으로 매출·영업이익·순이익을 파싱한다.

```python
import requests, zipfile, io, re
r = requests.get('https://opendart.fss.or.kr/api/document.xml',
                 params={'crtfc_key': API_KEY, 'rcept_no': RCEPT_NO}, timeout=20)
z = zipfile.ZipFile(io.BytesIO(r.content))
text = re.sub(r'<[^>]+>', ' ', z.read(z.namelist()[0]).decode('utf-8', 'ignore'))
text = re.sub(r'\s+', ' ', text).strip()
```

> **병렬로 보내라.** 당해·전년 재무, 개황 등 DART 호출은 서로 독립적이니 한 메시지에서 동시에 호출한다. 순차로 기다리지 마라.

#### Step 3-B. 뉴스 — WebSearch (DART 공시 아님)

`WebSearch`로 실적발표 전후 2주 내 국내 신문사 기사 6~8건 수집. 우선 매체: 한국경제·이데일리·전자신문·파이낸셜뉴스·서울경제·뉴스1·아이뉴스24·뉴시스. **검색에서 확인된 실제 URL만** 쓴다(추측 URL 금지, 네이버 검색 URL 금지). `sent`: 상회/긍정=`pos`, 급감/하락/규제=`neg`, 혼재=`mix`.

> **웹 검색도 한 번에 병렬로.** 뉴스·부문 매출·현재가·애널리스트 목표가 검색을 하나씩 순차로 돌리지 말고, 한 메시지에 여러 `WebSearch`/`WebFetch`를 몰아 동시에 보낸다.

### Step 4. 데이터 파싱

```python
def extract(items, sj_div, keyword):
    for it in items:
        if it.get('sj_div')==sj_div and keyword in it.get('account_nm',''):
            cur=(it.get('thstrm_amount','0') or '0').replace(',','')
            prv=(it.get('frmtrm_amount','0') or '0').replace(',','')
            return {'cur': int(cur), 'prv': int(prv)}
    return {'cur': 0, 'prv': 0}
```

단위: 원 → 억원 (`// 100_000_000`). YoY: `(cur-prv)/abs(prv)*100` (prv==0이면 "N/A").

### Step 4.5. 병렬 리서치·서술 ⚡ 속도 핵심

재무 숫자만 나오면 리포트의 나머지 데이터는 서로 독립적이다. 이 구간을 순차로 하면 5~8분, **서브에이전트(`Task`/`Agent`)로 병렬 처리하면 2~3분**이다. 재무 요약(매출·영업이익·순이익 YoY, OPM/NPM)을 뽑은 뒤 **한 메시지에서 아래 3개 에이전트를 동시에** 띄운다.

| 에이전트 | 넘겨줄 입력 | 반환할 JSON 조각 |
|---|---|---|
| **A. 웹 리서치** | 기업명·종목코드·분기·발표일 | `NEWS`(6~8), `ANALYSTS`(≥3), `CONS`, 현재가·목표가 범위(`meta.tp_*`) |
| **B. 페르소나** | 재무 요약 | `PERSONAS` 13인 (`_ALL.md` 직접 읽고 평가) |
| **C. 강세·약세** | 재무 요약 | `BULLS` 5, `BEARS` 5, `CHIPS` 3~4 |

규칙:
- 각 에이전트에게 **"출력은 사람용 설명이 아니라 순수 JSON 조각"**임을 명시한다. 그래야 메인이 그대로 `data.json`에 꽂는다.
- B·C는 웹이 필요 없으니 A와 정말 동시에 돈다. 세 트랙에 의존성이 없다.
- 서브에이전트를 못 쓰는 환경이면 최소한 웹 검색만이라도 Step 3-B처럼 한 번에 병렬로 보낸다.

### Step 5. `data.json` 작성 ★ 핵심 단계

`data.example.json`을 열어 **똑같은 구조로** `data.json`을 만든다. 최상위 두 키:

- **`meta`** — 헤더·KPI 카드·주가 카드·컨센서스 등 화면에 박히는 스칼라 텍스트. `data.example.json`의 모든 `meta` 키를 그대로 채운다.
- **`js`** — 차트·표·페르소나에 쓰이는 배열/객체 데이터.

`js`의 필수 키와 규칙:

| 키 | 내용 | 규칙 |
|----|------|------|
| `NAME` | 종목명(뉴스 검색 링크용) | `meta.name`과 동일 |
| `CONS` | `{buy,hold,sell}` 애널리스트 컨센 수 | 도넛·집계에 사용 |
| `CHIPS` | KPI 인사이트 칩 3~4개 | `{cls:'co'|'gn'|'dn', dot, txt}` |
| `SEGS` | 사업부문별 매출 | `{name,sub,cat,q25,q26,est}` · Y축은 자동 계산됨 |
| `TOT25`/`TOT26` | 전년·당기 총매출(억) | 믹스 계산용 |
| `DELTA` | 성장 기여도 워터폴 | `{name,d,est}` + 마지막 `{name:'합계',d,tot:true}` |
| `CURR` | 현재 주가(숫자) | 애널리스트 표 Upside 계산에 사용 |
| `ANALYSTS` | 증권사 리포트 | `{firm,r:'Buy'|'Hold'|'Sell',tp,from,date,note}` |
| `BULLS`/`BEARS` | 각 5개 | `{t,d}` |
| `NEWS` | 6~8건 | `{h,src,date,sent,url,body}` |
| `PERSONAS` | **정확히 13인** | `{name,type,rating:'buy'|'hold'|'sell',desc,eval}` |

**절대 규칙**: 모든 차트 Y축은 데이터에서 자동 계산된다(템플릿이 처리). data.json에 축 수치를 넣지 마라. `meta`의 숫자 텍스트(예: `rev_yoy`)는 Step 4에서 계산한 값과 일치시켜라.

### Step 6. 빌드

```bash
cd <프로젝트 루트>          # output/ 이 생길 위치
python3 ~/.claude/skills/dart/assets/build_report.py <data.json 경로>
```

빌더가 하는 일:
- `js` 전체를 `const` 선언으로 주입, `meta` 토큰 치환, 세그먼트 필터 버튼 생성
- 검증: 미치환 토큰·데이터 누락·**페르소나 13인**·Chart.js 4.4.4 로드 확인 (실패 시 경고/중단)
- `output/{종목명}_{YYYYMMDD}_{NN}.html` 저장 (같은 날 재실행 시 NN 자동 증가)

`--stdout`으로 파일 대신 표준출력, `-o <dir>`로 출력 폴더 지정 가능.

### Step 7. 확인

빌더가 성공(✅)하면 끝이다. 열어서 육안 확인은 선택. 빌더가 경고를 내면 그 항목만 `data.json`에서 고쳐 다시 빌드한다. **HTML을 직접 수정하지 마라** — 항상 data.json → 빌드.

---

## 데이터 생성 가이드 (섹션별)

### 사업별 매출 (`SEGS`)
1. DART 사업보고서 "사업부문별 영업실적"(연결 분기 매출) 우선 → 없으면 IR 자료 → 역산 시 `est:true`.
2. `cat`은 필터 그룹 키(예: `platform`/`content`/`other`). `meta.filter_cats`에 표시할 필터 버튼 `[["platform","플랫폼"],...]`를 명시(전체 버튼은 자동). 세그먼트 2개 미만이면 `filter_cats: []`.

### 현재가 (`CURR`)
현재 주가 하나만 필요하다(주가 차트 섹션은 제거됨). `meta.price`와 같은 값의 숫자. 애널리스트 표의 Upside `(tp-CURR)/CURR`에 쓰인다.

### 애널리스트 (`ANALYSTS`, `CONS`, `meta.tp_*`)
최소 3개 이상 증권사 확인. `CONS`는 전체 커버리지 집계(리스트에 안 실린 곳 포함 가능), `meta.coverage_note`·`cons_*_pct`와 정합. 목표가 범위는 `meta.tp_low/tp_avg/tp_high/tp_upside`에 넣는다. 불확실하면 note에 "(추정)".

### Bull/Bear (`BULLS`/`BEARS`)
DART 공시+개황+재무 기반, 각 5개. 주술 정합, em dash 없음, 투자 권유 배제.

### 13인 투자자 페르소나 (`PERSONAS`)
`SKILL_DIR/investor_persona/_ALL.md` **한 파일만** 읽어 13인의 철학·판단 규칙을 적용한다(개별 파일 13개를 따로 읽지 마라 — 통합본이 있다). 각 인물의 `Anti-Hallucination Rules`를 따르고, 실제 의견이 아닌 AI 시뮬레이션임을 유지한다. `rating`은 `buy`/`hold`/`sell`, `eval`은 2문장 이내.

---

## 오류 처리

| 상황 | 처리 |
|------|------|
| 특정 계정 없음 | 해당 `meta` 값 "데이터 없음", 나머지 정상 |
| API 전체 실패 | 오류 코드+해결법 안내 후 중단 |
| CFS 없음 | OFS 재시도, 제목에 "(개별)" |
| status=013 | 잠정실적 XML 폴백 (Step 3) |
| 빌더 "미치환 토큰" 경고 | `data.json`의 `meta`에 그 키 추가 후 재빌드 |
| 빌더 "페르소나 13인 아님" | `PERSONAS` 배열을 13개로 맞춤 |
| 세그먼트/주가 데이터 부족 | 대표 항목만 채우고 `est:true` / `price_disc`에 명기 |

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 빌더가 exit 1 | 미치환 토큰 또는 데이터 미주입 | 경고에 찍힌 키를 `data.json`에 채운다 |
| 차트가 안 그려짐 | 해당 `js` 배열이 비었거나 필드명 오타 | `data.example.json`과 필드명 대조 |
| 값이 화면과 안 맞음 | `meta` 텍스트와 `js` 숫자 불일치 | Step 4 계산값으로 양쪽 동기화 |
| API 키 실패 | `.env` 위치/형식 | 프로젝트 루트 `DART_API_KEY=...` 한 줄 |
| 템플릿을 고치고 싶다 | 디자인 변경 필요 | `template.html` 수정은 신중히. 이후 `data.example.json`으로 회귀 테스트(빌드→렌더) |

---

## 트리거 표현

- "DART 리포트 / 대시보드", "실적 리포트 / 실적 분석 HTML / 실적 차트"
- "○○ 기업 분석 파일 만들어줘", "○○ 재무 리포트", "/dart ○○"

---

## 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-05-10 | 초기 버전 (카카오·네이버 리포트 생성) |
| 2026-05-16 | CSS/HTML/JS를 `references/`로 분리, 크로스 플랫폼 폰트·스크롤바 수정 |
| 2026-07-04 | **템플릿+빌더 아키텍처 도입.** HTML 재생성 폐지 → `data.json` + `build_report.py`. 생성 시간 약 10분 → 2분 안쪽. 차트 Y축 하드코딩(델타 -1000, 목표가 40000/90000, **주가 라인 44000/51000**) 제거해 데이터 기반 자동 계산으로 교정. buildMarket 배지·컨센 수·뉴스검색 종목명 하드코딩 일반화. 페르소나 13파일 → `_ALL.md` 단일 읽기. |
| 2026-07-04 | NAVER 1Q 리포트로 실사용 검증. 이 과정에서 주가 라인 차트 Y축이 44000/51000으로 고정돼 있던 잔여 버그(카카오는 주가대가 같아 안 드러남)를 발견·수정. 회귀 가드에 `min:44000` 금지 추가. |
| 2026-07-04 | **주가 반응 섹션(sec-stock) 제거.** 30영업일 주가 재구성이 느리고(웹 검색 다수) 부정확해 삭제. 주가 라인·목표가 바 차트, 4개 주가 카드, `PRICE_DATA`/`EARN_IDX`/`TP_BARS` 및 주가 `meta` 토큰 제거. 애널리스트 목표가는 sec-market에 그대로 있고, `CURR`은 Upside 계산용으로 유지. 리포트 7→6개 섹션, 템플릿 1306→1186줄. |
| 2026-07-04 | SK하이닉스 리포트에서 발견: 세그먼트 차트 Y축에 `max`가 없어 자동 스케일이 데이터에 붙어 큰 값(24.6조) 막대의 라벨이 상단에서 잘림. 데이터 기반 20% 여유(`_segMax`) + `clip:false` + 상단 패딩 44px 추가로 교정(kakao는 값이 작아 자동 max가 여유를 줘 안 드러남). |
| 2026-07-04 | **병렬화로 2차 병목 제거.** HTML 생성은 이미 1초로 줄었으나 전체는 웹 리서치·서술 생성이 직렬이라 여전히 느렸다. Step 3/3-B에 DART·웹 호출 병렬 지시, Step 4.5 신설로 웹 리서치·13 페르소나·Bull/Bear를 서브에이전트 3개로 동시 처리(직렬 5~8분 → 병렬 2~3분). |
