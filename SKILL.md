---
name: dart
description: 상장사의 DART 공시 재무 데이터를 조회해 인터랙티브 애널리스트 HTML 리포트를 생성한다. 사용자가 "DART 리포트", "실적 리포트 만들어줘", "○○ 실적 분석 HTML", "○○ 대시보드", "/dart ○○" 같은 표현을 쓰면 반드시 발동한다. 기업명·분기를 파악해 DART API로 재무 데이터를 수집하고, 13인 투자자 페르소나 평가를 포함한 HTML 파일을 output/ 폴더에 생성한다.
---

# DART 애널리스트 리포트 스킬

상장사의 DART 재무·공시 데이터를 수집해 인터랙티브 HTML 리포트를 생성한다.
KPI 차트 · 성장 기여도 · 사업별 매출 · 주가 반응 · 애널리스트 시각 · 공시 뉴스 · 13인 투자자 페르소나를 포함한다.

---

## 파일 구조

```
dart/
├── SKILL.md                          ← 이 파일 (워크플로우 + 데이터 가이드)
├── references/
│   ├── dart-api.md                   ← DART API 엔드포인트·응답 구조
│   ├── design-system.md              ← 전체 CSS (24개 섹션, 토큰 포함)
│   └── section-templates.md          ← HTML 템플릿 + JavaScript (18개 섹션)
├── assets/
│   ├── dart_client.py                ← DartClient 클래스
│   └── corp_codes_listed.csv         ← 3,963개 상장사 오프라인 조회
├── investor_persona/                 ← 13인 투자자 페르소나 (각 1 파일)
├── kakao_20260510.html               ← 참조 HTML (ground-truth 출력 예시)
└── 네이버_20260510.html              ← 참조 HTML (ground-truth 출력 예시)
```

**경로 규칙**: 스킬 루트를 `SKILL_DIR`로 표기한다. 실제 경로는 `~/.claude/skills/dart/`이다.

---

## 사전 준비 (시작 전 필독)

아래 파일을 순서대로 읽는다:

1. **`SKILL_DIR/references/dart-api.md`** — DART API 엔드포인트, 보고서 코드, 응답 구조
2. **`SKILL_DIR/assets/dart_client.py`** — DartClient 클래스 전체

DART API 키: 프로젝트 `.env` (`DART_API_KEY=...`) 또는 환경변수에서 자동 로드.
키가 없으면 `.env` 위치와 설정법을 안내하고 중단한다.

---

## 동작 순서

### Step 1. 입력 파싱

사용자 입력에서 추출:

| 항목 | 처리 |
|------|------|
| **기업명** | 한글·영문·종목코드 모두 허용 |
| **분기** | 명시 없으면 최근 분기 자동 판단 (아래 기준) |

최근 분기 자동 판단 (공시 지연 45일 고려):

| 현재 날짜 | 사용 분기 | reprt_code |
|-----------|-----------|------------|
| 1/1 ~ 2/14 | 전년 3Q | 11014 |
| 2/15 ~ 5/14 | 전년 4Q (사업보고서) | 11011 |
| 5/15 ~ 8/14 | 당해 1Q | 11013 |
| 8/15 ~ 11/14 | 당해 2Q (반기) | 11012 |
| 11/15 ~ 12/31 | 당해 3Q | 11014 |

### Step 2. 기업 코드 조회

`assets/corp_codes_listed.csv` (3,963개 상장사, 네트워크 불필요)에서 먼저 검색한다:

```python
import pandas as pd
from pathlib import Path

SKILL_DIR = Path('~/.claude/skills/dart').expanduser()
csv = SKILL_DIR / 'assets' / 'corp_codes_listed.csv'
df = pd.read_csv(csv, dtype={'corp_code': str, 'stock_code': str}).fillna('')
hits = df[df['corp_name'].str.contains(keyword, na=False)]
```

- 1개 히트 → 바로 사용
- 복수 히트 → 회사명 + 종목코드 목록을 사용자에게 제시, 선택 대기
- 0개 히트 → DART API `company.json`으로 재검색; 그래도 없으면 오류 안내 후 중단

### Step 3. DART 데이터 수집

DartClient를 import해 아래 데이터를 병렬 수집한다:

```python
import sys

SKILL_DIR = Path('~/.claude/skills/dart').expanduser()
sys.path.insert(0, str(SKILL_DIR / 'assets'))
from dart_client import DartClient
client = DartClient()
```

| 데이터 | 메서드 | 비고 |
|--------|--------|------|
| 기업 개황 | `client.company(corp_code)` | 업종·CEO·설립일 |
| 재무제표 (연결) | `client.get_financial_statements(corp_code, year, reprt_code, 'CFS')` | 매출·영업이익·순이익 |
| 전년 동기 | 동일, `year-1` | YoY 비교 |
| 배당 | `client.get_dividend(corp_code, year, reprt_code)` | 있을 때만 |

> **뉴스 섹션은 DART 공시 목록을 사용하지 않는다.** WebSearch 도구로 국내 신문사 기사를 수집한다. 아래 Step 3-B를 참조.

연결(CFS) 응답 없으면 개별(OFS)로 자동 재시도 → 차트 제목에 "(개별)" 표기.
`status != '000'`이면 메시지 내용을 사용자에게 알리고 중단.

#### 잠정실적 공시(status=013) 폴백

분기 보고서(11013/11012/11014)가 `status=013`(미공시)을 반환하면, 같은 분기의 **잠정실적 공시** (`rcept_no` 조회 후 아래 패턴으로 XML 직접 파싱)로 폴백한다.

```python
import requests, zipfile, io, re

r = requests.get(
    'https://opendart.fss.or.kr/api/document.xml',
    params={'crtfc_key': API_KEY, 'rcept_no': RCEPT_NO},
    timeout=20
)
z = zipfile.ZipFile(io.BytesIO(r.content))
xml_name = z.namelist()[0]
text = re.sub(r'<[^>]+>', ' ', z.read(xml_name).decode('utf-8', errors='ignore'))
text = re.sub(r'\s+', ' ', text).strip()
# text에서 정규식으로 매출액·영업이익·순이익 숫자를 파싱한다
```

`잠정실적 공시` 문서의 공시명 패턴: "실적(잠정)" 또는 "잠정실적" 포함.
공시 목록에서 해당 rcept_no를 먼저 찾은 뒤 위 코드로 ZIP을 내려받는다.

#### Step 3-B. 뉴스 수집 — 국내 신문사 기사 (WebSearch)

뉴스 섹션은 **DART 공시가 아닌 국내 신문사 기사**로 채운다. WebSearch 도구를 사용해 실적 전후 2주 내 핵심 기사를 수집한다.

검색 쿼리 예시:
```
"{기업명} 1분기 2026 실적 영업이익"
"{기업명} 2026 AI 커머스 주가"
```

검색 대상 신문사 (우선순위 순):

| 매체 | 도메인 |
|------|--------|
| 한국경제 | hankyung.com |
| 이데일리 | edaily.co.kr |
| 전자신문 | etnews.com |
| 파이낸셜뉴스 | fnnews.com |
| 서울경제 | sedaily.com |
| 뉴스1 | news1.kr |
| 아이뉴스24 | inews24.com |
| 뉴시스 | newsis.com |

수집 후 NEWS 배열로 구성:

```javascript
const NEWS=[
  {h:'기사 제목',        // 원문 헤드라인 그대로
   src:'한국경제',       // 신문사 이름 (도메인 아닌 한글명)
   date:'2026.04.30',    // 기사 날짜 (YYYY.MM.DD)
   sent:'pos',           // pos | neg | mix
   url:'https://...',    // 기사 원본 URL (실제 URL만 사용, 네이버 검색 URL 금지)
   body:'2~3문장 요약'}, // 기사 핵심 내용, 직접 인용 없이 요약
  // ... 6~8건
];
```

`sent` 판단 기준:
- `pos`: 매출/이익 상회, 긍정 전망, 신사업 성과
- `neg`: 이익 급감, 주가 하락, 규제·소송, 리스크 부각
- `mix`: 호실적이지만 우려 동반, 상반된 평가

**규칙**: 실제로 검색에서 확인된 URL만 사용한다. 확인되지 않은 URL은 생성하지 않는다.

### Step 4. 데이터 파싱

```python
def extract(items, sj_div, keyword):
    for it in items:
        if it.get('sj_div') == sj_div and keyword in it.get('account_nm', ''):
            cur = it.get('thstrm_amount', '0').replace(',', '') or '0'
            prv = it.get('frmtrm_amount', '0').replace(',', '') or '0'
            return {'cur': int(cur), 'prv': int(prv)}
    return {'cur': 0, 'prv': 0}

revenue    = extract(items, 'IS', '매출액')
op_profit  = extract(items, 'IS', '영업이익')
net_profit = extract(items, 'IS', '당기순이익')
assets     = extract(items, 'BS', '자산총계')
liabilities= extract(items, 'BS', '부채총계')
equity     = extract(items, 'BS', '자본총계')
```

단위 변환: 원 → 억원 (`// 100_000_000`)
YoY: `(cur - prv) / abs(prv) * 100` (prv == 0이면 "N/A")

### Step 5. 출력 파일명 결정

```
output/{종목명}_{YYYYMMDD}_{NN}.html
```

NN 결정:

```python
from pathlib import Path
import re, datetime

out_dir = Path('output')
out_dir.mkdir(exist_ok=True)
today = datetime.date.today().strftime('%Y%m%d')
pattern = re.compile(rf'^{re.escape(corp_name)}_{today}_(\d{{2}})\.html$')
existing = [int(m.group(1)) for f in out_dir.iterdir() if (m := pattern.match(f.name))]
nn = f'{max(existing) + 1:02d}' if existing else '01'
out_path = out_dir / f'{corp_name}_{today}_{nn}.html'
```

예: `output/카카오_20260510_01.html`
같은 날 두 번째 실행: `output/카카오_20260510_02.html`

### Step 6. HTML 리포트 생성

아래 세 파일을 읽고 그대로 따른다:

1. **`SKILL_DIR/references/design-system.md`** — CSS 전체 (24개 섹션, light/dark 토큰, 반응형, 프린트, 애니메이션)
2. **`SKILL_DIR/references/section-templates.md`** — HTML 구조 + JavaScript 전체 (18개 섹션, 차트 빌더, 테마 토글, 네비게이션)
3. **`SKILL_DIR/kakao_20260510.html`** — ground-truth 출력 예시 (1,441줄). 최종 결과물의 구조·스타일이 이 파일과 **픽셀 단위로 동일**해야 한다.

#### 절대 규칙

| 규칙 | 설명 |
|------|------|
| `<title>` 형식 | `{종목명} {YYYY.MM.DD} - AI ROASTING` |
| Chart.js 버전 | `chart.js@4.4.4` (4.4.3 아님) |
| Pretendard 로드 | `<style>` 안 `@import url(...)` 방식. Google Fonts `<link>` 태그 금지 |
| 바 차트 공통 | `clip:false` + `layout:{padding:{top:44}}` — 데이터 레이블이 잘리지 않게 |
| Y축 | 데이터 기반 자동 계산. 하드코딩 수치 절대 금지 |
| 폰트 | `'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif` |
| 스크롤바 | `.sticky-nav-inner`에 `scrollbar-width:none; -ms-overflow-style:none;` |

#### 7개 섹션 구성

| ID | 섹션명 | 주요 데이터 |
|----|--------|-------------|
| sec-kpi | 핵심 KPI | 매출·영업이익·순이익 카드 3개 + 인사이트 칩 |
| sec-growth | 성장 기여도 | 매출 델타 워터폴 차트 |
| sec-segment | 사업별 매출 | SEGS 배열 → 바 차트 + 드릴다운 테이블 |
| sec-stock | 주가 반응 | PRICE_DATA 30일 → 라인 차트 + stat 카드 4개 |
| sec-market | 시장 평가 | 컨센서스 게이지 + ANALYSTS 테이블 + Bull/Bear 5:5 |
| sec-news | 관련 뉴스 | NEWS 6~8건 → 카드 |
| sec-persona | 투자자 시각 | 13인 페르소나 → 점수 카드 |

#### 13인 투자자 페르소나

`SKILL_DIR/investor_persona/` 디렉터리의 13개 파일을 각각 읽고 해당 투자자의 철학·분석 시퀀스·판단 규칙을 적용해 점수(1~10)와 한줄평을 생성한다.

**페르소나 목록** (파일명 기준):
warren_buffett, peter_lynch, benjamin_graham, philip_fisher, charlie_munger,
cathie_wood, bill_ackman, michael_burry, nassim_taleb, mohnish_pabrai,
stanley_druckenmiller, rakesh_jhunjhunwala, aswath_damodaran

각 파일에 정의된 `Anti-Hallucination Rules`를 반드시 따른다. 페르소나의 실제 의견이 아닌 AI 시뮬레이션임을 명시한다.

---

## 데이터 생성 가이드 (섹션별)

### 사업별 매출 (SEGS 배열)

1. **우선순위 1**: DART 사업보고서 내 "사업부문별 영업실적" 표 (연결 기준 분기 매출)
2. **우선순위 2**: 기업 IR 자료 (분기 실적 발표 PDF, 공시 첨부)
3. **추정 필요 시**: 전체 매출에서 공개된 항목을 빼고 역산, `est:true` 표시
4. 세그먼트가 3개 미만이면 `cg` 필터 버튼을 생략하고 전체만 표시
5. **Y축 자동 스케일 (고정값 절대 금지)** — 바 위 레이블·YoY 텍스트가 잘리지 않도록:
   ```javascript
   const _allVals = data.flatMap(s=>[s.q25, s.q26>0?s.q26:0]).filter(Boolean);
   const _segMax  = Math.ceil(Math.max(..._allVals) * 1.20 / 1000) * 1000;
   // chart options: clip:false, layout:{padding:{top:44}}
   // scales.y: max:_segMax
   ```

### 주가 데이터 (PRICE_DATA 배열)

1. **반드시 30 영업일** 데이터를 구성한다 (실적발표일 기준 전후 포함, 부족하면 이전 날짜로 채움)
2. 확인된 기준점(발표일, 익일): 뉴스·거래소 종가 공식 확인치 우선
3. 중간 추정치 포함 시 `.disc` 태그에 추정 기준 명기
4. `EARN_IDX`: `PRICE_DATA` 배열에서 `earnings:true` 항목의 0-based 인덱스
5. **Y축 자동 계산 (고정값 절대 금지)**:
   ```javascript
   min: Math.floor(Math.min(...prices) * 0.96 / 1000) * 1000,
   max: Math.ceil(Math.max(...prices)  * 1.04 / 1000) * 1000,
   ```

### 애널리스트 데이터 (ANALYSTS 배열)

1. **우선순위 1**: 실적발표 후 1~2주 내 발표된 증권사 리포트 (네이버 증권·Fnguide 등)
2. **우선순위 2**: Investing.com 컨센서스 페이지 (커버리지 수·평균 TP)
3. 최소 3개 이상 증권사 데이터 확인 후 작성, 불확실한 경우 note에 "(추정)" 명기

### 뉴스 (NEWS 배열)

DART 공시 목록은 사용하지 않는다. **WebSearch로 국내 신문사 기사만 수집**한다.

1. WebSearch 쿼리: `"{기업명} {분기} 실적"`, `"{기업명} 주가 실적발표"` 등 2~3회 검색
2. 우선 매체: 한국경제, 이데일리, 전자신문, 파이낸셜뉴스, 서울경제, 뉴스1, 아이뉴스24, 뉴시스
3. 실적발표일 전후 2주 내 기사 6~8건 선별
4. `sent` 판단: 매출/이익 상회 → `pos`, 이익 급감·주가 하락·규제 → `neg`, 혼재 → `mix`
5. **검색에서 확인된 실제 URL만** 사용. 추측·생성 URL 절대 금지
6. `url` 필드에 DART(`dart.fss.or.kr`), 네이버 검색 URL 사용 금지

### Bull/Bear 케이스 (BULLS/BEARS 배열)

- DART 공시 + 기업 개황 + 재무 데이터를 기반으로 작성
- **Bull**: 성장 촉매, 경쟁우위, 긍정 전망 (각 5개)
- **Bear**: 리스크, 비용 압박, 시장 위협 (각 5개)
- 문체: 주술 구조 정합, em dash 없음, 자연스러운 한국어, 투자 권유 문구 배제

---

## 오류 처리

| 상황 | 처리 |
|------|------|
| 특정 계정 없음 | 해당 KPI "데이터 없음" 표시, 나머지 정상 렌더링 |
| API 전체 실패 | 오류 코드 + 해결법 안내 후 중단 |
| CFS 없음 | OFS 재시도, 차트 제목에 "(개별)" 표기 |
| status=013 | 잠정실적 공시 XML 폴백 (Step 3 참조) |
| output/ 없음 | `mkdir -p output/` 자동 생성 |
| NN 중복 체크 실패 | 타임스탬프 suffix로 폴백 |
| 세그먼트 데이터 없음 | SEGS 배열에 대표 항목만 채우고 est:true 처리 |
| 주가 데이터 없음 | PRICE_DATA를 발표일 기준점만 포함해 단순화 |
| 애널리스트 데이터 없음 | ANALYSTS 최소 1개 이상 확인 후 컨센 평균으로 채움 |

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 차트 바 위 레이블/YoY가 잘림 | `clip:false` 또는 `layout.padding.top` 누락 | 모든 바 차트에 `clip:false, layout:{padding:{top:44}}` 적용 |
| 다크 모드 전환 시 깜빡임 | transition CSS 누락 | `design-system.md` §3 테마 전환 트랜지션 확인 |
| Windows에서 메뉴 위치 어긋남 | 스크롤바 공간 차지 | `.sticky-nav-inner`에 `scrollbar-width:none; -ms-overflow-style:none` |
| Windows에서 폰트 깨짐 | macOS 전용 폰트만 지정 | font-family에 `'Segoe UI', 'Malgun Gothic'` 포함 확인 |
| 세그먼트 차트 에러 | `const` 선언이 Chart 생성자 안에 위치 | `section-templates.md` §7의 `drawSeg()` 참조 — `const` 선언을 `new Chart()` 앞에 배치 |
| API 키 인식 실패 | `.env` 파일 위치 또는 형식 오류 | 프로젝트 루트에 `DART_API_KEY=...` 한 줄 작성 확인 |
| 13인 페르소나 누락 | investor_persona 파일 미읽기 | `SKILL_DIR/investor_persona/` 내 13개 파일 모두 읽기 |
| 뉴스 URL이 깨진 링크 | URL을 추측/생성함 | WebSearch 결과에서 확인된 URL만 사용, 생성 금지 |

---

## 트리거 표현

- "DART 리포트 / 대시보드"
- "실적 리포트 / 실적 분석 HTML / 실적 차트"
- "○○ 기업 분석 파일 만들어줘"
- "○○ 재무 리포트"
- "/dart ○○"

---

## 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-05-10 | 초기 버전 (카카오·네이버 리포트 생성) |
| 2026-05-16 | CSS/HTML/JS를 `references/`로 분리, 크로스 플랫폼 폰트·스크롤바 수정, drawSeg() JS 버그 수정 |
