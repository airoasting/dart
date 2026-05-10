---
name: dart
description: 상장사의 DART 공시 재무 데이터를 조회해 인터랙티브 애널리스트 HTML 리포트를 생성한다. 사용자가 "DART 리포트", "실적 리포트 만들어줘", "○○ 실적 분석 HTML", "○○ 대시보드", "/dart ○○" 같은 표현을 쓰면 반드시 발동한다. 기업명·분기를 파악해 DART API로 재무 데이터를 수집하고, 13인 투자자 페르소나 평가를 포함한 HTML 파일을 output/ 폴더에 생성한다.
---

# DART 애널리스트 리포트 스킬

상장사의 DART 재무·공시 데이터를 수집해 인터랙티브 HTML 리포트를 생성한다.  
KPI 차트 · 성장 기여도 · 사업별 매출 · 주가 반응 · 애널리스트 시각 · 공시 뉴스 · 13인 투자자 페르소나를 포함한다.

---

## 사전 준비 (시작 전 필독)

아래 파일을 순서대로 읽는다:

1. **`~/.claude/skills/dart/references/dart-api.md`** — DART API 엔드포인트, 보고서 코드, 응답 구조
2. **`~/.claude/skills/dart/assets/dart_client.py`** — DartClient 클래스 전체

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

csv = Path('~/.claude/skills/dart/assets/corp_codes_listed.csv').expanduser()
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
sys.path.insert(0, str(Path('~/.claude/skills/dart/assets').expanduser()))
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

아래 HTML 디자인 시스템에 따라 완전한 HTML 파일을 생성한다.  
**참조 파일**: `~/.claude/skills/dart/kakao_20260510.html` (1439줄)을 완전히 읽고 CSS·JS·HTML 구조를 그대로 따른다.

---

## HTML 디자인 시스템

`kakao_20260510.html`과 **픽셀 단위로 동일한** 디자인을 구현한다. 아래의 모든 토큰·패턴은 해당 파일에서 추출한 것이다. 이 시스템을 **완전히** 따를 것.

---

### 문서 헤드 (필수 구조)

```html
<!DOCTYPE html>
<html lang="ko" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{종목명} {YYYY.MM.DD} - AI ROASTING</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
```

**절대 규칙**:
- Chart.js는 반드시 **`chart.js@4.4.4`** (4.4.3 아님)
- Pretendard는 반드시 **`<style>` 태그 안** `@import url(...)` 방식 (Google Fonts `<link>` 태그 사용 금지)

---

### CSS 디자인 토큰 (완전 목록)

```css
/* ─── light (default) design tokens ─── */
:root {
  --bg:    #F5F5F7;
  --bg-s:  #FFFFFF;
  --bg-e:  #EBEBED;
  --bdr:   rgba(0,0,0,.09);
  --bdr-h: rgba(0,0,0,.22);
  --t1:    #1A1A1A;
  --t2:    #6B7280;
  --t3:    #9CA3AF;
  --coral:    #D96244;
  --coral-d:  #B84E34;
  --coral-l:  rgba(217,98,68,.80);
  --coral-a22: rgba(217,98,68,.22);
  --coral-a35: rgba(217,98,68,.35);
  --c25:   rgba(60,90,130,.78);
  --c25b:  #3C5A82;
  --cup:   rgba(185,78,52,.85);
  --cupb:  #B84E34;
  --cdn:   rgba(140,35,15,.75);
  --cdnb:  #8B2010;
  --up:    #D96244;
  --dn:    #DC2626;
  --grn:   #059669;
  --r:     14px;
  --rs:    8px;
  --nav-bg:      rgba(245,245,247,.92);
  --card-shadow: 0 1px 3px rgba(0,0,0,.06), 0 4px 16px rgba(0,0,0,.05);
  --row-hover:   rgba(0,0,0,.04);
  --td-border:   rgba(0,0,0,.05);
  --q-bg:        rgba(0,0,0,.06);
  --prog-track:  rgba(0,0,0,.07);
  --tooltip-bg:  #1A1A1A;
  --tooltip-c:   #F2F2F2;
}

/* ─── dark tokens ─── */
[data-theme="dark"] {
  --bg:    #0D0D0D;
  --bg-s:  #161616;
  --bg-e:  #1E1E1E;
  --bdr:   rgba(255,255,255,.09);
  --bdr-h: rgba(255,255,255,.22);
  --t1:    #F2F2F2;
  --t2:    #9A9A9A;
  --t3:    #5E5E5E;
  --coral:    #E07050;
  --coral-d:  #C05A3C;
  --coral-l:  rgba(224,112,80,.80);
  --coral-a22: rgba(224,112,80,.22);
  --coral-a35: rgba(224,112,80,.35);
  --c25:   rgba(90,115,150,.80);
  --c25b:  #5A7396;
  --cup:   rgba(224,112,80,.80);
  --cupb:  #C05A3C;
  --cdn:   rgba(200,50,30,.75);
  --cdnb:  #8B2010;
  --up:    #E07050;
  --dn:    #EF4444;
  --grn:   #22C55E;
  --nav-bg:      rgba(13,13,13,.92);
  --card-shadow: none;
  --row-hover:   rgba(255,255,255,.03);
  --td-border:   rgba(255,255,255,.04);
  --q-bg:        rgba(255,255,255,.08);
  --prog-track:  rgba(255,255,255,.06);
  --tooltip-bg:  #1A1A1A;
  --tooltip-c:   #F2F2F2;
}
```

---

### 전역 리셋 및 스무스 스크롤

```css
html { scroll-behavior: smooth; }
*,*::before,*::after { box-sizing:border-box; margin:0; padding:0; }
```

---

### 스무스 테마 전환 (필수)

body와 카드 요소 **전체**에 transition을 건다:

```css
body,
.nr,.ni,.ni-sm,.sc,.hdr,.kpi-card,.stat-card,.bb-card,
.news-card,.persona-card,.persona-section-hdr,
.persona-summary,.cw,.dp,.cg,.cb,.lb,.tp-sum,.cons-bw,
.sticky-nav,.chip,.tt-btn,.dt-wrap,.theme-btn,
td,th { transition: background-color .22s ease, border-color .22s ease, color .18s ease, box-shadow .22s ease, transform .15s ease; }
```

---

### body 및 래퍼

```css
body {
  background: var(--bg);
  font-family: 'Pretendard', -apple-system, 'Apple SD Gothic Neo', sans-serif;
  color: var(--t1);
  padding-bottom: 80px;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1080px; margin: 0 auto; padding: 48px 24px 0; }
```

---

### 서피스 클래스

```css
.nr    { background:var(--bg-s); border:1px solid var(--bdr); border-radius:var(--r); box-shadow:var(--card-shadow); }
.ni    { background:var(--bg);   border:1px solid var(--bdr); border-radius:var(--rs); }
.ni-sm { background:var(--bg);   border:1px solid var(--bdr); border-radius:var(--rs); }
```

---

### 헤더 (`.hdr`)

HTML 구조:

```html
<div class="wrap">
<div class="hdr">
  <div class="hdr-l">
    <h1><span>{종목명}</span> ({종목코드}) 실적 대시보드</h1>
    <p>{분기} vs {전년동기} &nbsp;|&nbsp; 연결 기준 &nbsp;|&nbsp; 기준일: {YYYY.MM.DD}</p>
  </div>
  <div class="hdr-r">
    <div class="price-now">{주가}<span style="font-size:.93rem;color:var(--t2);font-weight:500">원</span></div>
    <div class="price-chg">{등락률}% ({날짜} 종가)</div>
    <div class="price-meta">52W {저가} ~ {고가} &nbsp;|&nbsp; KRX</div>
  </div>
</div>
</div>
```

CSS:

```css
.hdr { display:flex; justify-content:space-between; align-items:flex-end;
       flex-wrap:wrap; gap:12px; margin-bottom:36px; }
.hdr-l h1 { font-size:1.76rem; font-weight:800; letter-spacing:-.5px; }
.hdr-l h1 span { color:var(--coral); }
.hdr-l p  { margin-top:6px; font-size:.87rem; color:var(--t2); }
.hdr-r    { text-align:right; }
.price-now { font-size:1.62rem; font-weight:700; }
.price-chg { font-size:.90rem; font-weight:600; color:var(--up); margin-top:3px; }
.price-meta{ font-size:.78rem; color:var(--t3); margin-top:3px; }
```

---

### 스킵 링크 (접근성)

`<body>` 태그 바로 다음에 배치:

```html
<a href="#sec-kpi" class="skip-link">콘텐츠로 바로가기</a>
```

CSS:

```css
.skip-link {
  position:fixed; top:-48px; left:24px; z-index:9999;
  padding:9px 18px; background:var(--coral); color:#fff;
  border-radius:0 0 10px 10px; font-size:.85rem; font-weight:700;
  text-decoration:none; transition:top .18s ease;
  box-shadow:0 4px 16px rgba(0,0,0,.20);
}
.skip-link:focus { top:0; }
```

---

### Sticky Nav (7개 링크 — 필수)

HTML 구조:

```html
<nav class="sticky-nav" id="stickyNav">
  <div class="nav-progress-track"><div class="nav-progress-bar" id="navProgress"></div></div>
  <div class="sticky-nav-outer">
    <div class="sticky-nav-inner">
      <a class="nav-link active" href="#sec-kpi">{분기} 실적</a>
      <a class="nav-link" href="#sec-growth">성장 기여도</a>
      <a class="nav-link" href="#sec-segment">사업별 매출</a>
      <a class="nav-link" href="#sec-stock">주가 반응</a>
      <a class="nav-link" href="#sec-market">애널리스트 시각</a>
      <a class="nav-link" href="#sec-news">뉴스</a>
      <a class="nav-link" href="#sec-persona">투자자 시각</a>
    </div>
    <button class="theme-btn" id="themeBtn" onclick="toggleTheme()" aria-label="다크 모드로 전환" title="테마 전환 (T)">
      <span id="themeBtnIcon">🌙</span>
    </button>
  </div>
</nav>
```

CSS:

```css
.sticky-nav {
  position: sticky;
  top: 0;
  z-index: 200;
  background: var(--nav-bg);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border-bottom: 1px solid var(--bdr);
  overflow: hidden;
}
.nav-progress-track {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 2px;
  background: var(--prog-track);
  pointer-events: none;
}
.nav-progress-bar {
  height: 100%;
  background: var(--coral);
  width: 0%;
  transition: width .1s linear;
}
.sticky-nav-outer {
  max-width: 1080px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  padding-right: 16px;
}
.sticky-nav-inner {
  flex: 1;
  overflow-x: auto;
  padding: 0 24px 0 24px;
  display: flex;
  gap: 0;
  align-items: center;
  scrollbar-width: none;
}
.sticky-nav-inner::-webkit-scrollbar { display:none; }
.nav-link {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 14px 18px;
  font-size: .97rem;
  font-weight: 600;
  color: var(--t2);
  text-decoration: none;
  white-space: nowrap;
  transition: color .15s;
  letter-spacing: -.01em;
}
.nav-link::before {
  content: '';
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--bdr-h);
  transition: background .15s, transform .15s;
}
.nav-link:hover { color: var(--t1); }
.nav-link:hover::before { background: var(--t3); }
.nav-link.active { color: var(--coral); }
.nav-link.active::before { background: var(--coral); transform: scale(1.25); }

/* ─── theme toggle button (circle) ─── */
.theme-btn {
  background: var(--bg-e);
  border: 1px solid var(--bdr);
  border-radius: 50%;
  cursor: pointer;
  font-size: 1.05rem;
  width: 34px;
  height: 34px;
  padding: 0;
  flex-shrink: 0;
  color: var(--t2);
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
.theme-btn:hover { border-color: var(--coral); color: var(--coral); }
:focus-visible { outline: 2px solid var(--coral); outline-offset: 2px; border-radius: 4px; }
```

---

### 섹션 레이블 (`.sec-label`)

```css
.sec-label { font-size:.78rem; font-weight:800; color:var(--coral);
             text-transform:uppercase; letter-spacing:1.4px;
             padding:44px 0 0 16px; position:relative;
             scroll-margin-top:58px; }
.sec-label::before {
  content:''; position:absolute; left:0; bottom:0;
  height:1.25em; width:3px; background:var(--coral); border-radius:2px;
  transition: background-color .22s ease;
}
```

---

### 섹션 컨테이너 패턴

콘텐츠는 반드시 `.sc.nr.full` 래퍼 안에 넣는다. 섹션 레이블과 조합:

```html
<div id="sec-kpi" class="sec-label">섹션 이름</div>
<div class="sc nr full">
  <!-- 콘텐츠 -->
</div>
```

CSS:

```css
.sc { padding:28px 28px 24px; margin:20px auto; max-width:1080px; }
.sc.full { border-radius:var(--r); }
.sh { display:flex; justify-content:space-between; align-items:baseline;
      flex-wrap:wrap; gap:8px; margin-bottom:18px; }
.stitle { font-size:.75rem; font-weight:700; color:var(--coral);
          text-transform:uppercase; letter-spacing:.8px; }
.sann   { font-size:.86rem; font-weight:500; color:var(--t2); }
```

---

### 필수 섹션 (Nav 순서 — 7개)

| 순번 | 섹션 ID | 내용 |
|------|---------|------|
| 1 | `sec-kpi` | KPI 카드 3개 (매출·영업이익·순이익, YoY 배지) + 인사이트 칩 |
| 2 | `sec-growth` | 매출 델타 차트 (전기 대비 waterfall) |
| 3 | `sec-segment` | 사업별 매출 비교 바 차트 (전기 대비, 클릭 드릴다운) |
| 4 | `sec-stock` | 주가 반응 (stat-card 4개 + 가격 라인 차트 + 목표가 바 차트) |
| 5 | `sec-market` | 애널리스트 시각 (컨센서스 도넛 + 목표가 표 + Bull/Bear 5개씩) |
| 6 | `sec-news` | 최근 공시 뉴스 카드 (접수일 + 공시명) |
| 7 | `sec-persona` | 투자자 페르소나 13인 |

> **Bull/Bear는 sec-market 안에 있다.** 독립 섹션(`sec-bb`)으로 분리하지 말 것.

---

### KPI 그리드 (sec-kpi)

HTML:

```html
<div id="sec-kpi" class="sec-label">{분기} 실적 요약</div>
<div class="sc nr full">
  <div class="kpi-grid">
    <div class="kpi-card nr">
      <div class="kpi-lbl">전체 매출</div>
      <div class="kpi-val">{값}<span class="kpi-unit">억원</span></div>
      <div class="kpi-yoy up">+{delta}억 &nbsp;(+{pct}% YoY)</div>
      <div class="kpi-div"></div>
      <div class="kpi-sub">전년동기 &nbsp;{전년값}억</div>
    </div>
    <div class="kpi-card nr">
      <div class="kpi-lbl">영업이익</div>
      <div class="kpi-val">{값}<span class="kpi-unit">억원</span></div>
      <div class="kpi-yoy up">+{delta}억 &nbsp;(+{pct}% YoY)</div>
      <div class="kpi-div"></div>
      <div class="kpi-sub">OPM &nbsp;{전년OPM}%<span class="arr"> → </span><span class="b">{당기OPM}%</span></div>
    </div>
    <div class="kpi-card nr">
      <div class="kpi-lbl">당기순이익</div>
      <div class="kpi-val">{값}<span class="kpi-unit">억원</span></div>
      <div class="kpi-yoy up">+{delta}억 &nbsp;(+{pct}% YoY)</div>
      <div class="kpi-div"></div>
      <div class="kpi-sub">NPM &nbsp;{전년NPM}%<span class="arr"> → </span><span class="b">{당기NPM}%</span></div>
    </div>
  </div>
  <div class="chips" id="perfChips"></div>
</div>
```

CSS:

```css
/* ─── KPI ─── */
.kpi-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-bottom:22px; }
@keyframes kpiIn { from{opacity:0;transform:translateY(16px)} to{opacity:1;transform:none} }
.kpi-card { padding:24px 22px 20px; animation:kpiIn .46s cubic-bezier(.4,0,.2,1) both; cursor:default; }
.kpi-card:nth-child(1){animation-delay:.06s}
.kpi-card:nth-child(2){animation-delay:.13s}
.kpi-card:nth-child(3){animation-delay:.20s}
.kpi-card:hover { transform:translateY(-3px); box-shadow:0 8px 24px rgba(0,0,0,.10); border-color:var(--bdr-h); }
[data-theme="dark"] .kpi-card:hover { box-shadow:0 8px 24px rgba(0,0,0,.40); }
.kpi-lbl  { font-size:.72rem; font-weight:600; color:var(--t3); text-transform:uppercase;
            letter-spacing:.8px; margin-bottom:10px; }
.kpi-val  { font-size:2.05rem; font-weight:800; letter-spacing:-1.5px; line-height:1; }
.kpi-unit { font-size:.93rem; font-weight:500; color:var(--t2); margin-left:2px; }
.kpi-yoy  { font-size:1rem; font-weight:700; margin-top:10px; }
.kpi-yoy.up { color:var(--up); } .kpi-yoy.dn { color:var(--dn); }
.kpi-div  { height:1px; background:var(--bdr); margin:14px 0; }
.kpi-sub  { font-size:.84rem; color:var(--t2); display:flex; align-items:center; gap:5px; }
.kpi-sub .arr { color:var(--t3); }
.kpi-sub .b   { color:var(--grn); font-weight:700; }
```

---

### 인사이트 칩 (`.chips`)

KPI 그리드 하단에 배치. 핵심 지표 4~5개를 칩으로 표시:

```css
/* ─── insight chips ─── */
.chips { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:20px; }
.chip  { padding:6px 14px; border-radius:20px; font-size:.83rem; font-weight:600;
         display:flex; align-items:center; gap:6px;
         background:var(--bg-e); border:1px solid var(--bdr); cursor:default;
         transition:border-color .13s, box-shadow .13s; }
.chip:hover { border-color:var(--bdr-h); box-shadow:0 2px 8px rgba(0,0,0,.06); }
.chip .dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
.chip.co { color:var(--coral); } .chip.dn { color:var(--dn); } .chip.gn { color:var(--grn); }
```

JS 빌드:

```javascript
function buildChips(){
  const ch=[
    {cls:'co', dot:'var(--coral)', txt:'핵심 긍정 지표 1'},
    {cls:'gn', dot:'var(--grn)',   txt:'핵심 긍정 지표 2'},
    {cls:'dn', dot:'var(--dn)',    txt:'리스크 지표'},
  ];
  document.getElementById('perfChips').innerHTML=
    ch.map(c=>`<div class="chip ${c.cls}"><span class="dot" style="background:${c.dot}"></span>${c.txt}</div>`).join('');
}
```

---

### 성장 기여도 차트 (sec-growth)

HTML:

```html
<div id="sec-growth" class="sec-label">성장 기여도 분석</div>
<div class="sc nr full">
  <div class="sh">
    <div class="sann">순증 <strong style="color:var(--coral)">+{총순증}억</strong> &nbsp;= 성장 기여 <strong style="color:var(--coral)">+{성장기여}억</strong> + 감소 요인 <strong style="color:var(--dn)">-{감소요인}억</strong> &nbsp;<span style="color:var(--t3);font-size:.80rem">* 추정치 포함</span></div>
  </div>
  <div class="cw" style="height:360px"><canvas id="deltaChart"></canvas></div>
</div>
```

JS (`buildDeltaChart`):

```javascript
let deltaChartInst=null;

function buildDeltaChart(){
  // 각 사업부별 YoY 증감액을 배열로 정의 (추정치는 est:true)
  const DATA=[
    {name:'세그먼트A', d:+XXX, est:false},
    {name:'세그먼트B', d:+XXX, est:false},
    {name:'세그먼트C', d:-XXX, est:true},
    {name:'기타·조정', d:-XXX, est:true},
    {name:'합계',      d:+XXX, tot:true},
  ];
  const c=tc();
  const vals=DATA.map(d=>d.d);
  const cols=DATA.map(d=>
    d.tot?'rgba(30,42,58,.85)':
    d.d>=0?(d.est?'rgba(201,100,66,.50)':'rgba(201,100,66,.82)'):
           (d.est?'rgba(158,45,20,.48)':'rgba(158,45,20,.76)'));
  const bors=DATA.map(d=>d.tot?'#888':d.d>=0?'#C05A3C':'#CC3333');
  deltaChartInst=new Chart(document.getElementById('deltaChart').getContext('2d'),{
    type:'bar',
    data:{labels:DATA.map(d=>d.name.split('\n')),
          datasets:[{data:vals,backgroundColor:cols,borderColor:bors,borderWidth:1.5,borderRadius:6}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{...ttDef(c),callbacks:{label:ctx=>`${sgn(ctx.raw)}${ctx.raw.toLocaleString('ko-KR')}억${DATA[ctx.dataIndex].est?' (추정)':''}`}}},
      scales:{
        x:{grid:{display:false},ticks:{color:c.tick,font:{size:11.5,family:'Pretendard'}}},
        y:{min: Math.min(...vals)*1.3,
           grid:{color:ctx=>ctx.tick.value===0?c.grid0:c.grid,
                 lineWidth:ctx=>ctx.tick.value===0?1.5:1},
           ticks:{color:c.tick,font:{size:12,family:'Pretendard'},
           callback:v=>(v===0?'0':(v>0?'+':'')+v.toLocaleString('ko-KR'))}}
      }
    },
    plugins:[{id:'dl',afterDatasetsDraw(chart){
      const{ctx}=chart;
      chart.getDatasetMeta(0).data.forEach((bar,i)=>{
        const v=vals[i];
        ctx.save();ctx.font='700 11.5px Pretendard,sans-serif';
        ctx.fillStyle=v>=0?c.lblPos:c.lblNeg;
        ctx.textAlign='center';ctx.textBaseline=v>=0?'bottom':'top';
        ctx.fillText((v>=0?'+':'')+v.toLocaleString('ko-KR'),bar.x,bar.y+(v>=0?-10:10));
        ctx.restore();
      });
    }}]
  });
}
```

---

### 사업별 매출 차트 (sec-segment)

HTML:

```html
<!-- sec-segment -->
<div id="sec-segment" class="sec-label">사업별 매출 상세</div>
<div class="sc nr full">
  <div class="sh">
    <div class="sann">막대 클릭 시 상세 드릴다운</div>
  </div>
  <div class="ctrls">
    <div class="cg" id="fg">
      <button class="cb active" onclick="setF('all',this)">전체</button>
      <!-- 기업별 세그먼트 카테고리에 맞는 버튼 추가 (예: 플랫폼 / 콘텐츠) -->
    </div>
    <div class="cg" id="sg">
      <button class="cb active" onclick="setS('size',this)">규모순</button>
      <button class="cb" onclick="setS('contrib',this)">기여도순</button>
      <button class="cb" onclick="setS('growth',this)">성장률순</button>
      <button class="cb" onclick="setS('name',this)">이름순</button>
    </div>
  </div>
  <div class="leg-row">
    <button class="lb" id="ls0" onclick="togL(0,this)"><span class="dot" style="background:var(--c25)"></span>{전년}분기</button>
    <button class="lb" id="ls1" onclick="togL(1,this)"><span class="dot" style="background:var(--coral)"></span>{당기}분기</button>
  </div>
  <div class="cw" id="segWrap" style="height:420px"><canvas id="segChart"></canvas></div>
  <div class="dp" id="dp">
    <div class="dp-hdr"><div class="dp-title" id="dpT"></div><button class="dp-close" onclick="closeDp()">✕</button></div>
    <div class="dp-grid">
      <div class="dp-item ni-sm"><div class="dp-lbl">전년동기</div><div class="dp-val" id="dp25"></div></div>
      <div class="dp-item ni-sm"><div class="dp-lbl">당기</div><div class="dp-val" id="dp26"></div></div>
      <div class="dp-item ni-sm"><div class="dp-lbl">δ 절대</div><div class="dp-val" id="dpD"></div></div>
      <div class="dp-item ni-sm"><div class="dp-lbl">YoY %</div><div class="dp-val" id="dpP"></div></div>
      <div class="dp-item ni-sm"><div class="dp-lbl">믹스 변화</div><div class="dp-val" id="dpM"></div></div>
    </div>
  </div>
  <button class="tt-btn" id="ttBtn" onclick="togTable()">데이터 테이블 보기</button>
  <div class="dt-wrap" id="dtW">
    <table><thead><tr>
      <th>사업부문</th><th>구분</th>
      <th class="r">전년동기</th><th class="r">당기</th>
      <th class="r">δ(억)</th><th class="r">YoY%</th>
      <th class="r">비중(전)</th><th class="r">비중(당)</th><th class="r">믹스Δ</th>
    </tr></thead><tbody id="tB"></tbody></table>
  </div>
  <div class="fn" id="fn1"></div>
</div>
```

CSS:

```css
/* ─── segment controls ─── */
.ctrls { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:16px; padding:0 2px; }
.cg { display:flex; gap:6px; }
.cb { padding:5px 14px; border-radius:20px; font-size:.82rem; font-weight:600; cursor:pointer;
      background:var(--bg); border:1px solid var(--bdr); color:var(--t2); }
.cb:hover { border-color:var(--bdr-h); color:var(--t1); }
.cb.active { background:var(--coral); border-color:var(--coral); color:#fff; }
.leg-row { display:flex; gap:16px; margin-bottom:14px; }
.lb { display:flex; align-items:center; gap:7px; padding:5px 14px; border-radius:20px;
      font-size:.82rem; font-weight:600; cursor:pointer;
      background:var(--bg); border:1px solid var(--bdr); color:var(--t2); }
.lb:hover { border-color:var(--bdr-h); }
.lb.off { opacity:.4; }
.lb .dot { width:8px; height:8px; border-radius:50%; }
/* ─── drill-down panel ─── */
.dp { margin:20px 0 0; padding:20px; background:var(--bg); border:1px solid var(--bdr);
      border-radius:var(--rs); display:none; }
.dp.on { display:block; }
.dp-hdr { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }
.dp-title { font-size:1rem; font-weight:700; }
.dp-close { background:none; border:none; cursor:pointer; font-size:1rem; color:var(--t3); }
.dp-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:10px; }
.dp-item { padding:12px 14px; }
.dp-lbl { font-size:.72rem; color:var(--t3); font-weight:600; margin-bottom:5px; }
.dp-val { font-size:.96rem; font-weight:700; }
/* ─── table toggle ─── */
.tt-btn { margin:18px 0 0; padding:7px 18px; border-radius:8px; border:1px solid var(--bdr);
          background:var(--bg); font-size:.83rem; font-weight:600; cursor:pointer; color:var(--t2); }
.tt-btn.open { border-color:var(--coral); color:var(--coral); }
.dt-wrap { display:none; overflow-x:auto; margin-top:14px; }
.dt-wrap.on { display:block; }
.dt-wrap table { width:100%; border-collapse:collapse; font-size:.85rem; }
.dt-wrap th, .dt-wrap td { padding:10px 12px; border-bottom:1px solid var(--td-border); }
.dt-wrap th { font-weight:700; color:var(--t2); background:var(--bg-e); text-align:left; }
.dt-wrap td.r { text-align:right; }
.dt-wrap tr:hover { background:var(--row-hover); }
td.pos { color:var(--up); font-weight:600; }
td.neg { color:var(--dn); font-weight:600; }
.fn { font-size:.75rem; color:var(--t3); padding:12px 4px 0; line-height:1.5; }
```

JS — segment 데이터 구조 및 함수:

```javascript
/* ─── SEGMENT DATA ─── */
// 각 사업부문 데이터 배열. cat은 필터 버튼과 연동되는 카테고리 키.
// est:true이면 추정치 표시(*) 및 반투명 색상 적용.
const SEGS=[
  {name:'사업부A', sub:'카테고리1', cat:'cat1', q25:XXXX, q26:XXXX, est:false},
  {name:'사업부B', sub:'카테고리2', cat:'cat2', q25:XXXX, q26:XXXX, est:true},
  // ...
];
const TOT25=전년총매출억;  // 전년 연결 총매출
const TOT26=당기총매출억;  // 당기 연결 총매출

/* ─── HELPERS ─── */
const pv  =(a,b)=>a?(b-a)/a*100:null;
const sgn =n=>n>=0?'+':'';
const fmt =n=>n===0?'재편/미공시':n.toLocaleString('ko-KR')+'억';
const mix =(v,t)=>t?(v/t*100).toFixed(1)+'%':'-';

/* ─── SEGMENT FILTER/SORT STATE ─── */
let fil='all', srt='size', segC=null;

function vis(){
  // fil 값이 'all'이면 전체, 그 외 cat 값으로 필터
  let d=SEGS.filter(s=>fil==='all'||s.cat===fil);
  if(srt==='size')   d.sort((a,b)=>Math.max(b.q25,b.q26)-Math.max(a.q25,a.q26));
  if(srt==='contrib')d.sort((a,b)=>Math.abs(b.q26-b.q25)-Math.abs(a.q26-a.q25));
  if(srt==='growth') d.sort((a,b)=>{const ga=pv(a.q25,a.q26)??-Infinity,gb=pv(b.q25,b.q26)??-Infinity;return gb-ga;});
  if(srt==='name')   d.sort((a,b)=>a.name.localeCompare(b.name,'ko'));
  return d;
}

function setF(f,btn){fil=f;document.querySelectorAll('#fg .cb').forEach(b=>b.classList.remove('active'));btn.classList.add('active');drawSeg();syncTbl();}
function setS(s,btn){srt=s;document.querySelectorAll('#sg .cb').forEach(b=>b.classList.remove('active'));btn.classList.add('active');drawSeg();syncTbl();}
function togL(idx,btn){if(!segC)return;const m=segC.getDatasetMeta(idx);m.hidden=!m.hidden;segC.update();btn.classList.toggle('off');}

function drawSeg(){
  closeDp();
  const data=vis();
  const c=tc();
  const labels=data.map(s=>[s.name,'('+s.sub+')']);
  if(segC)segC.destroy();
  const ctx=document.getElementById('segChart').getContext('2d');
  segC=new Chart(ctx,{
    type:'bar',
    data:{labels,datasets:[
      {label:'{전년}분기',data:data.map(s=>s.q25),
       backgroundColor:c.seg25,borderColor:c.seg25b,borderWidth:1.5,borderRadius:5},
      {label:'{당기}분기',data:data.map(s=>s.q26>0?s.q26:null),
       backgroundColor:data.map(s=>s.q26>s.q25?c.segUp:c.segDn),
       borderColor:data.map(s=>s.q26>s.q25?c.segUpB:c.segDnB),borderWidth:1.5,borderRadius:5},
    ]},
    /* ★ 규칙: Y축은 반드시 데이터 최대값 기준 20% 헤드룸으로 자동 계산.
       clip:false + layout.padding.top:44 로 YoY 레이블이 잘리지 않도록 한다. */
    const _allVals=data.flatMap(s=>[s.q25,s.q26>0?s.q26:0]).filter(Boolean);
    const _segMax=Math.ceil(Math.max(..._allVals)*1.20/1000)*1000;
    options:{
      responsive:true,maintainAspectRatio:false,
      clip:false,
      layout:{padding:{top:44}},
      onClick(e,el){if(!el.length){closeDp();return;}showDp(data[el[0].index]);},
      plugins:{legend:{display:false},tooltip:{...ttDef(c),callbacks:{label(ctx){
        const seg=data[ctx.dataIndex];
        return ctx.raw===null?null:` ${ctx.dataset.label}: ${fmt(ctx.raw)}${seg.est?' (추정)':''}`;
      }}}},
      scales:{
        x:{grid:{display:false},ticks:{color:c.tick,font:{size:12,family:'Pretendard'},maxRotation:0}},
        y:{grid:{color:c.grid},
           ticks:{color:c.tick,font:{size:12,family:'Pretendard'},callback:v=>v.toLocaleString('ko-KR')},
           min:0, max:_segMax}
      }
    },
    plugins:[
      {id:'vl',afterDatasetsDraw(chart){
        const{ctx}=chart;
        chart.data.datasets.forEach((ds,di)=>{
          const m=chart.getDatasetMeta(di);if(m.hidden)return;
          m.data.forEach((bar,i)=>{
            const v=ds.data[i];if(!v)return;
            ctx.save();
            ctx.fillStyle=c.barLbl;ctx.font='500 11px Pretendard,sans-serif';
            ctx.textBaseline='bottom';ctx.textAlign='center';
            ctx.fillText(v.toLocaleString('ko-KR'),bar.x,bar.y-9);
            ctx.restore();
          });
        });
      }},
      {id:'yoy',afterDatasetsDraw(chart){
        const{ctx}=chart;
        const m0=chart.getDatasetMeta(0);
        const m1=chart.getDatasetMeta(1);
        data.forEach((seg,i)=>{
          if(!seg.q25||!seg.q26)return;
          const b0=m0.hidden?null:m0.data[i];
          const b1=m1.hidden?null:m1.data[i];
          if(!b0||!b1)return;
          const minY=Math.min(b0.y,b1.y);
          const midX=(b0.x+b1.x)/2;
          const d=seg.q26-seg.q25;
          if(seg.q26===0)return;
          const p=pv(seg.q25,seg.q26);
          if(p===null)return;
          const text=`${sgn(d)}${d.toLocaleString('ko-KR')} (${sgn(p)}${p.toFixed(1)}%)`;
          ctx.save();
          ctx.fillStyle=d>=0?c.lblPos:c.lblNeg;
          ctx.font='700 11px Pretendard,sans-serif';
          ctx.textAlign='center';ctx.textBaseline='bottom';
          ctx.fillText(text,midX,minY-24);
          ctx.restore();
        });
      }}
    ]
  });
}

function showDp(seg){
  const d=seg.q26-seg.q25,p=pv(seg.q25,seg.q26);
  const mx25=mix(seg.q25,TOT25),mx26=seg.q26>0?mix(seg.q26,TOT26):'-';
  document.getElementById('dpT').textContent=seg.name+(seg.est?' (추정)':'');
  document.getElementById('dp25').textContent=seg.q25.toLocaleString('ko-KR')+'억';
  document.getElementById('dp26').textContent=seg.q26===0?'재편/미공시':seg.q26.toLocaleString('ko-KR')+'억';
  const dEl=document.getElementById('dpD');
  dEl.textContent=seg.q26===0?'N/A':(sgn(d)+d.toLocaleString('ko-KR')+'억');
  dEl.style.color=d>=0?'var(--up)':'var(--dn)';
  const pEl=document.getElementById('dpP');
  pEl.textContent=p===null?'N/A':(sgn(p)+p.toFixed(1)+'%');
  pEl.style.color=p===null?'var(--t2)':p>=0?'var(--up)':'var(--dn)';
  const mxD=seg.q26>0?((seg.q26/TOT26-seg.q25/TOT25)*100).toFixed(1)+'pp':'-';
  document.getElementById('dpM').textContent=`${mx25} → ${mx26} (${mxD})`;
  document.getElementById('dp').classList.add('on');
}
function closeDp(){document.getElementById('dp').classList.remove('on');}

function renderTbl(){
  const data=vis();const tb=document.getElementById('tB');tb.innerHTML='';
  data.forEach(seg=>{
    const d=seg.q26-seg.q25,p=pv(seg.q25,seg.q26);
    const m25=(seg.q25/TOT25*100).toFixed(1),m26=seg.q26>0?(seg.q26/TOT26*100).toFixed(1):'-';
    const mD=seg.q26>0?((seg.q26/TOT26-seg.q25/TOT25)*100).toFixed(1):'N/A';
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${seg.name}${seg.est?' *':''}</td><td>${seg.sub}</td>
      <td class="r">${seg.q25.toLocaleString('ko-KR')}</td>
      <td class="r">${seg.q26===0?'재편':seg.q26.toLocaleString('ko-KR')}</td>
      <td class="r ${seg.q26===0?'':d>=0?'pos':'neg'}">${seg.q26===0?'N/A':sgn(d)+d.toLocaleString('ko-KR')}</td>
      <td class="r ${p===null?'':p>=0?'pos':'neg'}">${p===null?'N/A':sgn(p)+p.toFixed(1)+'%'}</td>
      <td class="r">${m25}%</td>
      <td class="r">${m26==='-'?'-':m26+'%'}</td>
      <td class="r ${mD==='N/A'?'':parseFloat(mD)>=0?'pos':'neg'}">${mD==='N/A'?'N/A':sgn(parseFloat(mD))+mD+'pp'}</td>`;
    tb.appendChild(tr);
  });
}
function syncTbl(){if(document.getElementById('dtW').classList.contains('on'))renderTbl();}
function togTable(){
  const w=document.getElementById('dtW'),b=document.getElementById('ttBtn');
  const o=w.classList.toggle('on');
  b.textContent=o?'데이터 테이블 닫기':'데이터 테이블 보기';
  b.classList.toggle('open',o);if(o)renderTbl();
}
// fn1 내용: 추정 기준 설명 텍스트를 여기에 삽입
document.getElementById('fn1').innerHTML='* 추정치: {추정 기준 설명}';
```

---

### 주가 반응 (sec-stock)

HTML:

```html
<!-- sec-stock -->
<div id="sec-stock" class="sec-label">주가 반응</div>
<div class="sc nr full">
  <div class="stat-grid">
    <div class="stat-card nr">
      <div class="stat-lbl">현재 주가</div>
      <div class="stat-val">{현재가}<span style="font-size:.86rem;color:var(--t2)">원</span></div>
      <div class="stat-sub">{날짜} 종가</div>
    </div>
    <div class="stat-card nr">
      <div class="stat-lbl">실적발표일 등락</div>
      <div class="stat-val" style="color:var(--dn)">{발표일등락}%</div>
      <div class="stat-sub">{발표일} 발표 당일</div>
    </div>
    <div class="stat-card nr">
      <div class="stat-lbl">발표 후 익일</div>
      <div class="stat-val" style="color:var(--up)">{익일등락}%</div>
      <div class="stat-sub">{익일} 종가</div>
    </div>
    <div class="stat-card nr">
      <div class="stat-lbl">52주 범위</div>
      <div class="stat-val" style="font-size:1.08rem">{저가} ~ {고가}</div>
      <div class="stat-sub">현재가: 52W 고점 대비 {갭}%</div>
    </div>
  </div>
  <div class="cw" style="height:300px"><canvas id="priceChart"></canvas></div>
  <div class="disc">※ 일별 종가 데이터는 확인된 기준점 기반 추정치 포함. 투자 목적으로 활용 불가.</div>
</div>
<div class="sc nr full" style="margin-top:0">
  <div class="cw" style="height:200px"><canvas id="tpChart"></canvas></div>
  <div class="fn">컨센서스 평균 목표가 {평균TP}원 &nbsp;|&nbsp; 현재가 {현재가}원 &nbsp;|&nbsp; Implied Upside {상승여력}%</div>
</div>
```

CSS:

```css
/* ─── stat cards (stock section) ─── */
.stat-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:22px; }
.stat-card { padding:20px 18px; }
.stat-lbl  { font-size:.72rem; font-weight:600; color:var(--t3); text-transform:uppercase;
             letter-spacing:.6px; margin-bottom:8px; }
.stat-val  { font-size:1.52rem; font-weight:800; letter-spacing:-1px; }
.stat-sub  { font-size:.80rem; color:var(--t3); margin-top:5px; }
.stat-card:hover { transform:translateY(-2px); border-color:var(--bdr-h); }
@media(max-width:768px){ .stat-grid{grid-template-columns:repeat(2,1fr)} }
/* ─── chart wrapper ─── */
.cw { position:relative; }
```

JS (`buildStockCharts`):

```javascript
/* ─── PRICE DATA ─── */
// 실적발표일 전후 ±30일 일별 종가. earnings:true는 발표 당일.
const PRICE_DATA=[
  {d:'MM/DD', p:XXXXX},
  {d:'MM/DD', p:XXXXX, earnings:true},  // 실적발표일
  {d:'MM/DD', p:XXXXX},
];
const EARN_IDX=실적발표일_인덱스;  // PRICE_DATA 배열에서 earnings:true 위치
const CURR=현재주가;

let priceChartInst=null, tpChartInst=null;

function buildStockCharts(){
  const c=tc();
  const prices=PRICE_DATA.map(d=>d.p);
  const labels=PRICE_DATA.map(d=>d.d);
  const gradCtx=document.getElementById('priceChart').getContext('2d');
  const grad=gradCtx.createLinearGradient(0,0,0,280);
  grad.addColorStop(0,c.gradTop);
  grad.addColorStop(1,c.gradBot);

  priceChartInst=new Chart(gradCtx,{
    type:'line',
    data:{labels,datasets:[{
      data:prices,borderColor:'var(--coral)',borderWidth:2.5,
      backgroundColor:grad,fill:true,tension:.35,
      pointRadius:PRICE_DATA.map((_,i)=>i===EARN_IDX||i===EARN_IDX+1?7:3),
      pointBackgroundColor:PRICE_DATA.map((_,i)=>i===EARN_IDX?'#922010':i===EARN_IDX+1?'#059669':'var(--coral)'),
      pointBorderColor:'#fff',pointBorderWidth:1.5,
    }]},
    options:{
      responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{...ttDef(c),callbacks:{
        title:ctx=>PRICE_DATA[ctx[0].dataIndex].d+(PRICE_DATA[ctx[0].dataIndex].earnings?' (실적발표)':''),
        label:ctx=>` 종가: ${ctx.raw.toLocaleString('ko-KR')}원`
      }}},
      /* ★ 규칙: Y축은 데이터 기준 자동 계산. 1000원 단위로 반올림해 깔끔하게 표시. */
      scales:{
        x:{grid:{display:false},ticks:{color:c.tick,font:{size:11,family:'Pretendard'}}},
        y:{grid:{color:c.grid},
           min:Math.floor(Math.min(...prices)*0.96/1000)*1000,
           max:Math.ceil(Math.max(...prices)*1.04/1000)*1000,
           ticks:{color:c.tick,font:{size:11,family:'Pretendard'},callback:v=>v.toLocaleString('ko-KR')+'원'}}
      }
    },
    plugins:[{
      id:'eLine',afterDraw(chart){
        const meta=chart.getDatasetMeta(0);
        const bar=meta.data[EARN_IDX];if(!bar)return;
        const{ctx,chartArea}=chart;
        ctx.save();
        ctx.fillStyle=c.earnTxt;ctx.font='bold 11px Pretendard,sans-serif';
        ctx.textAlign='center';
        ctx.fillText('실적발표',bar.x,chartArea.top+14);
        ctx.fillText(PRICE_DATA[EARN_IDX].d,bar.x,chartArea.top+27);
        ctx.setLineDash([5,4]);ctx.strokeStyle=c.earnLine;ctx.lineWidth=1.5;
        ctx.beginPath();ctx.moveTo(bar.x,chartArea.top+34);ctx.lineTo(bar.x,chartArea.bottom);ctx.stroke();
        ctx.restore();
      }
    }]
  });

  /* ─── TP chart (목표가 바 차트) ─── */
  // 증권사별 목표가를 규모순으로 배열. 첫 번째는 항상 현재가.
  const tpLabels=[
    ['현재가', CURR.toLocaleString('ko-KR')+'원'],
    // 예: ['NH', '60,000원'], ['메리츠', '75,000원'], ...
  ];
  const tpVals=[CURR, /* 각 증권사 목표가 */];
  const tpCols=[c.tpCurr,
    'rgba(224,112,80,.42)','rgba(224,112,80,.60)',
    'rgba(224,112,80,.76)','rgba(224,112,80,.92)'];
  tpChartInst=new Chart(document.getElementById('tpChart').getContext('2d'),{
    type:'bar',
    data:{labels:tpLabels,datasets:[{data:tpVals,backgroundColor:tpCols,borderRadius:6,borderWidth:0}]},
    options:{
      responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{...ttDef(c),callbacks:{label:ctx=>` ${ctx.raw.toLocaleString('ko-KR')}원`}}},
      scales:{
        x:{grid:{display:false},ticks:{color:c.tick,font:{size:11,family:'Pretendard'}}},
        y:{grid:{color:c.grid},
           min:Math.min(...tpVals)*0.92,max:Math.max(...tpVals)*1.08,
           ticks:{color:c.tick,font:{size:11,family:'Pretendard'},callback:v=>(v/10000).toFixed(0)+'만원'}}
      }
    },
    plugins:[{id:'tl',afterDatasetsDraw(chart){
      const{ctx}=chart;
      chart.getDatasetMeta(0).data.forEach((bar,i)=>{
        const v=tpVals[i];
        const up=((v-CURR)/CURR*100).toFixed(1);
        ctx.save();
        ctx.fillStyle=i===0?c.tpBase:c.tpUp;
        ctx.font='700 11.5px Pretendard,sans-serif';
        ctx.textBaseline='bottom';ctx.textAlign='center';
        ctx.fillText(i===0?'기준':'+'+up+'%',bar.x,bar.y-10);
        ctx.restore();
      });
    }}]
  });
}
```

---

### 애널리스트 시각 (sec-market) — Bull/Bear 포함

> Bull/Bear는 **이 섹션 안**에 있다. 독립 `sec-bb` 섹션으로 분리하지 말 것.

HTML:

```html
<!-- sec-market -->
<div id="sec-market" class="sec-label">애널리스트 시각</div>
<div class="sc nr full">
  <div class="sh">
    <div class="sann">총 {커버리지수}명 커버리지 ({기준일} 기준)</div>
  </div>
  <div class="cons-wrap">
    <div class="cons-pie">
      <canvas id="consChart" style="max-width:150px;max-height:150px"></canvas>
      <div class="cons-lbl">Buy {buy수} &nbsp;|&nbsp; Hold {hold수} &nbsp;|&nbsp; Sell {sell수}</div>
    </div>
    <div>
      <div class="cons-rows" style="margin-bottom:16px">
        <div class="cons-row">
          <span class="nm" style="color:var(--coral)">Buy</span>
          <div class="cons-bw"><div class="cons-b" style="width:{buy%}%;background:var(--coral)"></div></div>
          <span class="cnt" style="color:var(--coral)">{buy수}</span>
        </div>
        <div class="cons-row">
          <span class="nm" style="color:#4B5563">Hold</span>
          <div class="cons-bw"><div class="cons-b" style="width:{hold%}%;background:#9CA3AF"></div></div>
          <span class="cnt" style="color:#4B5563">{hold수}</span>
        </div>
        <div class="cons-row">
          <span class="nm" style="color:var(--dn)">Sell</span>
          <div class="cons-bw"><div class="cons-b" style="width:{sell%}%;background:var(--dn)"></div></div>
          <span class="cnt" style="color:var(--dn)">{sell수}</span>
        </div>
      </div>
      <div class="tp-sum">
        <div class="tp-item"><div class="l">현재가</div><div class="v">{현재가}원</div></div>
        <div class="tp-item"><div class="l">최저 목표가</div><div class="v">{최저TP}원</div></div>
        <div class="tp-item"><div class="l">평균 목표가</div><div class="v" style="color:var(--coral)">{평균TP}원</div></div>
        <div class="tp-item"><div class="l">최고 목표가</div><div class="v">{최고TP}원</div></div>
        <div class="tp-item"><div class="l">Implied Upside</div><div class="v" style="color:var(--grn)">+{상승여력}%</div></div>
      </div>
    </div>
  </div>
</div>
<div class="sc nr full" style="margin-top:0">
  <div class="at-wrap">
    <table>
      <thead><tr>
        <th>증권사</th><th>투자의견</th>
        <th class="r">목표가</th><th class="r">변동</th>
        <th class="r">Upside</th><th>날짜</th><th>코멘트</th>
      </tr></thead>
      <tbody id="atBody"></tbody>
    </table>
  </div>
</div>
<div class="bb-grid" style="margin-bottom:24px">
  <div class="bb-card nr bb-bull">
    <div class="bb-head"><span class="icon">📈</span><span class="ttl" style="color:var(--coral)">Bull Case 5가지</span></div>
    <div id="bullList"></div>
  </div>
  <div class="bb-card nr bb-bear">
    <div class="bb-head"><span class="icon">📉</span><span class="ttl" style="color:var(--dn)">Bear Case 5가지</span></div>
    <div id="bearList"></div>
  </div>
</div>
```

CSS:

```css
/* ─── analyst consensus ─── */
.cons-wrap  { display:flex; gap:32px; align-items:flex-start; margin-bottom:22px; flex-wrap:wrap; }
.cons-pie   { display:flex; flex-direction:column; align-items:center; gap:10px; min-width:150px; }
.cons-lbl   { font-size:.75rem; color:var(--t2); font-weight:600; white-space:nowrap; }
.cons-rows  { min-width:220px; }
.cons-row   { display:flex; align-items:center; gap:10px; margin-bottom:10px; }
.cons-row .nm { font-size:.82rem; font-weight:700; width:30px; }
.cons-bw    { flex:1; height:8px; background:var(--prog-track); border-radius:4px; overflow:hidden; }
.cons-b     { height:100%; background:var(--coral); border-radius:4px; }
.cons-row .cnt { font-size:.82rem; font-weight:700; width:20px; text-align:right; }
.tp-sum     { display:flex; flex-direction:column; gap:8px; }
.tp-item    { display:flex; justify-content:space-between; align-items:center; gap:24px;
              padding:8px 14px; background:var(--bg); border:1px solid var(--bdr); border-radius:var(--rs); }
.tp-item .l { font-size:.80rem; color:var(--t2); font-weight:600; }
.tp-item .v { font-size:.88rem; font-weight:700; }
/* ─── analyst table ─── */
.at-wrap    { overflow-x:auto; }
.at-wrap table { width:100%; border-collapse:collapse; font-size:.85rem; }
.at-wrap th { padding:10px 14px; background:var(--bg-e); font-weight:700; color:var(--t2);
              border-bottom:1px solid var(--bdr); text-align:left; white-space:nowrap; }
.at-wrap td { padding:10px 14px; border-bottom:1px solid var(--td-border); vertical-align:middle; }
.at-wrap td.r { text-align:right; }
.at-wrap tr.link-row { cursor:pointer; }
.at-wrap tr.link-row:hover { background:var(--row-hover); }
.badge { padding:2px 10px; border-radius:10px; font-size:.72rem; font-weight:700; }
.badge-buy  { background:var(--coral-a22); color:var(--coral); }
.badge-hold { background:var(--q-bg); color:var(--t2); }
.badge-sell { background:rgba(220,38,38,.12); color:var(--dn); }
.act-up { color:var(--coral); font-weight:700; }
.act-dn { color:var(--dn); font-weight:700; }
.act-ke { color:var(--t3); font-weight:700; }
/* ─── bull / bear ─── */
.bb-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.bb-card { padding:22px 20px; }
.bb-bull { border-left:3px solid var(--coral-a35); }
.bb-bear { border-left:3px solid rgba(220,38,38,.30); }
[data-theme="dark"] .bb-bear { border-left-color:rgba(239,68,68,.24); }
.bb-head { display:flex; align-items:center; gap:8px; margin-bottom:16px; }
.bb-head .icon { font-size:1.20rem; }
.bb-head .ttl  { font-size:.93rem; font-weight:800; }
.bb-item { display:flex; gap:9px; margin-bottom:12px; align-items:flex-start; }
.bb-item .num  { font-size:.72rem; font-weight:800; width:18px; height:18px; border-radius:50%;
                 display:flex; align-items:center; justify-content:center; flex-shrink:0; margin-top:2px; }
.bb-bull .num  { background:rgba(217,98,68,.16); color:var(--coral); }
.bb-bear .num  { background:rgba(220,38,38,.14);  color:var(--dn); }
[data-theme="dark"] .bb-bull .num { background:rgba(224,112,80,.13); }
[data-theme="dark"] .bb-bear .num { background:rgba(239,68,68,.12); }
.bb-item .txt  { font-size:.87rem; line-height:1.60; color:var(--t2); }
.bb-item .txt strong { font-weight:700; color:var(--t1); }
.bb-card:hover { border-color:var(--bdr-h); }
```

JS (`buildMarket`):

```javascript
/* ─── ANALYST DATA ─── */
// from: 이전 목표가, tp: 현재 목표가, r: Buy/Hold/Sell
const ANALYSTS=[
  {firm:'증권사A', r:'Buy', tp:XXXXX, from:XXXXX, date:'YYYY.MM.DD', note:'"코멘트"'},
  // ...
];
const BULLS=[
  {t:'Bull 제목 1', d:'Bull 설명 1'},
  {t:'Bull 제목 2', d:'Bull 설명 2'},
  {t:'Bull 제목 3', d:'Bull 설명 3'},
  {t:'Bull 제목 4', d:'Bull 설명 4'},
  {t:'Bull 제목 5', d:'Bull 설명 5'},
];
const BEARS=[
  {t:'Bear 제목 1', d:'Bear 설명 1'},
  {t:'Bear 제목 2', d:'Bear 설명 2'},
  {t:'Bear 제목 3', d:'Bear 설명 3'},
  {t:'Bear 제목 4', d:'Bear 설명 4'},
  {t:'Bear 제목 5', d:'Bear 설명 5'},
];

let consChartInst=null;

function buildMarket(){
  const c=tc();
  const buy=ANALYSTS.filter(a=>a.r==='Buy').length;
  const hold=ANALYSTS.filter(a=>a.r==='Hold').length;
  const sell=ANALYSTS.filter(a=>a.r==='Sell').length;
  const total=buy+hold+sell;

  consChartInst=new Chart(document.getElementById('consChart').getContext('2d'),{
    type:'doughnut',
    data:{labels:['Buy','Hold','Sell'],
          datasets:[{data:[buy,hold,sell],
            backgroundColor:['rgba(201,100,66,.85)','rgba(156,163,175,.7)','rgba(146,32,16,.85)'],
            borderWidth:0,borderRadius:4}]},
    options:{responsive:true,maintainAspectRatio:true,cutout:'62%',
             plugins:{legend:{display:false},tooltip:{...ttDef(c),callbacks:{label:c=>` ${c.label}: ${c.raw}명`}}}}
  });

  const tbody=document.getElementById('atBody');
  tbody.innerHTML='';
  ANALYSTS.forEach(a=>{
    const delta=a.tp-a.from;
    const action=delta>0?`<span class="act-up">▲ 상향</span>`:delta<0?`<span class="act-dn">▼ 하향</span>`:`<span class="act-ke">유지</span>`;
    const upside=((a.tp-CURR)/CURR*100).toFixed(1);
    const badgeCls=a.r==='Buy'?'badge-buy':a.r==='Hold'?'badge-hold':'badge-sell';
    const tr=document.createElement('tr');
    tr.className='link-row';
    tr.onclick=()=>window.open(`https://search.naver.com/search.naver?where=news&query=${encodeURIComponent('{기업명} '+a.firm+' 목표가 '+a.date)}`, '_blank');
    tr.innerHTML=`
      <td><strong>${a.firm}</strong></td>
      <td><span class="badge ${badgeCls}">${a.r}</span></td>
      <td class="r"><strong>${a.tp.toLocaleString('ko-KR')}원</strong></td>
      <td class="r">${action} ${Math.abs(delta)>0?Math.abs(delta).toLocaleString('ko-KR')+'원':''}</td>
      <td class="r pos">+${upside}%</td>
      <td style="font-size:.82rem;color:var(--t2)">${a.date}</td>
      <td style="font-size:.84rem;color:var(--t2)">${a.note}</td>`;
    tbody.appendChild(tr);
  });

  const bull=document.getElementById('bullList');
  bull.innerHTML='';
  BULLS.forEach((b,i)=>{
    bull.innerHTML+=`<div class="bb-item"><span class="num">${i+1}</span>
      <div class="txt"><strong>${b.t}</strong><br>${b.d}</div></div>`;
  });
  const bear=document.getElementById('bearList');
  bear.innerHTML='';
  BEARS.forEach((b,i)=>{
    bear.innerHTML+=`<div class="bb-item"><span class="num">${i+1}</span>
      <div class="txt"><strong>${b.t}</strong><br>${b.d}</div></div>`;
  });
}
```

---

### 뉴스 카드 (sec-news)

HTML 구조:

```html
<div id="sec-news" class="sec-label">최신 뉴스</div>
<div class="sc nr full" style="padding:20px 24px">
  <div id="newsGrid"></div>
</div>
```

JS:

```javascript
const NEWS=[
  {h:'뉴스 제목', src:'언론사', date:'YYYY.MM.DD', sent:'pos',
   url:'https://...', body:'뉴스 본문 요약'},
  // sent: 'pos' | 'mix' | 'neg'
];

function buildNews(){
  const SENT={
    pos:{lbl:'긍정',cls:'sent-pos',dot:'var(--coral)'},
    mix:{lbl:'혼재',cls:'sent-mix',dot:'#9CA3AF'},
    neg:{lbl:'부정',cls:'sent-neg',dot:'var(--dn)'},
  };
  const container=document.getElementById('newsGrid');
  container.innerHTML='';
  const list=document.createElement('div');
  list.className='news-list';
  NEWS.forEach(n=>{
    const s=SENT[n.sent]||SENT.mix;
    const url=n.url||`https://search.naver.com/search.naver?where=news&query=${encodeURIComponent(n.h+' '+n.src)}`;
    const a=document.createElement('a');
    a.href=url; a.target='_blank'; a.rel='noopener';
    a.style.cssText='text-decoration:none;color:inherit;display:block';
    a.innerHTML=`
      <div class="news-card nr">
        <span class="news-dot" style="background:${s.dot}"></span>
        <div class="news-body-wrap">
          <div class="news-top">
            <div class="news-headline">${n.h}</div>
            <span class="sent-badge ${s.cls}">${s.lbl}</span>
          </div>
          <div class="news-meta">${n.src} &nbsp;|&nbsp; ${n.date}</div>
          <div class="news-snippet">${n.body}</div>
        </div>
      </div>`;
    list.appendChild(a);
  });
  container.appendChild(list);
}
```

CSS:

```css
/* ─── news ─── */
.news-list { display:flex; flex-direction:column; }
.news-card { padding:18px 20px; display:flex; align-items:flex-start; gap:14px;
             border-bottom:1px solid var(--bdr); background:transparent;
             border-radius:0; box-shadow:none !important; border-left:none; border-right:none; border-top:none;
             transition:background .15s; }
.news-card:first-child { border-top:1px solid var(--bdr); }
.news-dot  { width:8px; height:8px; border-radius:50%; flex-shrink:0; margin-top:6px; }
.news-body-wrap { flex:1; min-width:0; }
.news-top  { display:flex; justify-content:space-between; align-items:flex-start;
             gap:10px; margin-bottom:5px; }
.news-headline { font-size:.92rem; font-weight:600; line-height:1.45; flex:1; }
.sent-badge { padding:2px 10px; border-radius:10px; font-size:.72rem; font-weight:700;
              flex-shrink:0; margin-top:2px; white-space:nowrap; }
.sent-pos  { background:rgba(217,98,68,.14); color:var(--coral); }
.sent-neg  { background:rgba(220,38,38,.13);  color:var(--dn); }
.sent-mix  { background:rgba(100,100,100,.10); color:var(--t2); }
[data-theme="dark"] .sent-pos { background:rgba(224,112,80,.12); }
[data-theme="dark"] .sent-neg { background:rgba(239,68,68,.12); }
[data-theme="dark"] .sent-mix { background:rgba(160,160,160,.10); }
.news-meta { font-size:.78rem; color:var(--t3); margin-bottom:5px; }
.news-snippet { font-size:.84rem; color:var(--t2); line-height:1.58; }
a:has(.news-card):hover .news-card { background:var(--row-hover); }
a:has(.news-card):hover .news-headline { color:var(--coral); }
```

---

### 차트 헬퍼 함수 (필수 포함)

```javascript
function tc(){
  const d=document.documentElement.getAttribute('data-theme')==='dark';
  return {
    tick:     d?'#9A9A9A':'#6B7280',
    grid:     d?'rgba(255,255,255,.07)':'rgba(0,0,0,.06)',
    grid0:    d?'rgba(255,255,255,.45)':'rgba(0,0,0,.28)',
    lblPos:   d?'#F0A080':'#B84E34',
    lblNeg:   d?'#F87171':'#DC2626',
    barLbl:   d?'#C8C8C8':'#505050',
    earnTxt:  d?'#F87171':'#DC2626',
    earnLine: d?'rgba(248,113,113,.6)':'rgba(220,38,38,.4)',
    tpBase:   d?'#9A9A9A':'#6B7280',
    tpUp:     d?'#E07050':'#D96244',
    tpCurr:   d?'rgba(255,255,255,.12)':'rgba(0,0,0,.08)',
    gradTop:  d?'rgba(224,112,80,.28)':'rgba(217,98,68,.18)',
    gradBot:  d?'rgba(224,112,80,.01)':'rgba(217,98,68,.00)',
    seg25:    d?'rgba(84,108,134,.78)':'rgba(60,90,130,.72)',
    seg25b:   d?'#3D5168':'#3C5A82',
    segUp:    d?'rgba(201,100,66,.84)':'rgba(185,78,52,.88)',
    segUpB:   d?'#A04E30':'#A04E30',
    segDn:    d?'rgba(158,45,20,.76)':'rgba(140,35,15,.80)',
    segDnB:   d?'#7E1D0A':'#7E1D0A',
    ttBg:     d?'#1E1E1E':'#FFFFFF',
    ttBdr:    d?'rgba(255,255,255,.13)':'rgba(0,0,0,.10)',
    ttTitle:  d?'#F2F2F2':'#1A1A1A',
    ttBody:   d?'#9A9A9A':'#6B7280',
  };
}
function ttDef(c){
  return {
    backgroundColor: c.ttBg,
    borderColor:     c.ttBdr,
    borderWidth:     1,
    titleColor:      c.ttTitle,
    bodyColor:       c.ttBody,
    cornerRadius:    9,
    padding:         10,
    titleFont:{family:'Pretendard',weight:'700',size:12},
    bodyFont: {family:'Pretendard',size:12},
    boxPadding:      4,
  };
}
```

테마 전환 시 `rebuildCharts()` 호출로 Chart.js 인스턴스를 **파괴 후 재생성**한다.  
키보드 `T`로 토글:

```javascript
document.addEventListener('keydown',e=>{
  if((e.key==='t'||e.key==='T')&&!e.ctrlKey&&!e.metaKey&&!e.altKey){
    const tag=document.activeElement.tagName;
    if(tag!=='INPUT'&&tag!=='TEXTAREA'&&tag!=='SELECT'){toggleTheme();}
  }
});
```

---

### 테마 토글 함수 (localStorage 포함)

```javascript
function toggleTheme(){
  const root=document.documentElement;
  const isDark=root.getAttribute('data-theme')==='dark';
  const next=isDark?'light':'dark';
  root.setAttribute('data-theme',next);
  localStorage.setItem('theme',next);
  const icon=document.getElementById('themeBtnIcon');
  const btn=document.getElementById('themeBtn');
  icon.textContent=isDark?'🌙':'☀️';
  btn.setAttribute('aria-label',isDark?'다크 모드로 전환':'라이트 모드로 전환');
  rebuildCharts();
}
```

---

### rebuildCharts (7개 섹션 차트 모두 포함)

```javascript
function rebuildCharts(){
  if(deltaChartInst){deltaChartInst.destroy();deltaChartInst=null;}
  buildDeltaChart();
  drawSeg();
  if(priceChartInst){priceChartInst.destroy();priceChartInst=null;}
  if(tpChartInst){tpChartInst.destroy();tpChartInst=null;}
  buildStockCharts();
  if(consChartInst){consChartInst.destroy();consChartInst=null;}
  buildMarket();
}
```

---

### Nav 스크롤 감지 (7개 섹션 ID)

```javascript
const sections=['sec-kpi','sec-growth','sec-segment','sec-stock','sec-market','sec-news','sec-persona'];
window.addEventListener('scroll',()=>{
  let cur=sections[0];
  sections.forEach(id=>{
    const el=document.getElementById(id);
    if(el&&window.scrollY+140>=el.offsetTop)cur=id;
  });
  document.querySelectorAll('.nav-link').forEach(a=>{
    a.classList.toggle('active',a.getAttribute('href')==='#'+cur);
  });
  const doc=document.documentElement;
  const pct=((doc.scrollTop||document.body.scrollTop)/(doc.scrollHeight-doc.clientHeight)*100).toFixed(1);
  const bar=document.getElementById('navProgress');
  if(bar)bar.style.width=pct+'%';
});
```

---

### DOMContentLoaded 초기화 (7개 함수 호출)

```javascript
window.addEventListener('DOMContentLoaded',()=>{
  const saved=localStorage.getItem('theme');
  if(saved==='dark'){
    document.documentElement.setAttribute('data-theme','dark');
    document.getElementById('themeBtnIcon').textContent='☀️';
    document.getElementById('themeBtn').setAttribute('aria-label','라이트 모드로 전환');
  }

  buildChips();
  buildDeltaChart();
  drawSeg();
  buildStockCharts();
  buildMarket();
  buildNews();
  buildPersonas();
  initScrollAnim();

  document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      const target = document.querySelector(link.getAttribute('href'));
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        link.style.transform = 'scale(.94)';
        setTimeout(() => { link.style.transform = ''; }, 160);
      }
    });
  });
});
```

---

### 섹션 입장 애니메이션 (IntersectionObserver)

```css
/* ─── section entrance animation ─── */
.sc.sc-anim { opacity:0; transform:translateY(14px); }
.sc.sc-anim.sc-visible { opacity:1; transform:none; transition:opacity .45s cubic-bezier(.4,0,.2,1), transform .45s cubic-bezier(.4,0,.2,1); }
```

```javascript
function initScrollAnim(){
  const vh=window.innerHeight;
  document.querySelectorAll('.sc').forEach(el=>{
    if(el.getBoundingClientRect().top>vh-40) el.classList.add('sc-anim');
  });
  const io=new IntersectionObserver(entries=>{
    entries.forEach(e=>{
      if(e.isIntersecting){e.target.classList.add('sc-visible');io.unobserve(e.target);}
    });
  },{threshold:0.06,rootMargin:'0px 0px -40px 0px'});
  document.querySelectorAll('.sc.sc-anim').forEach(el=>io.observe(el));
}
```

---

## 투자자 페르소나 섹션 (sec-persona)

### 13인 파일 (순서·그룹 기본값)

각 파일은 `~/.claude/skills/dart/investor_persona/` 에 있다.  
**eval 작성 전 해당 파일을 읽는다** — Core Principles, Required Analysis Sequence, Decision Rules를 기준으로 평가한다.

| 그룹 (기본값) | 파일 | 투자자 |
|--------------|------|--------|
| 매수 | `peter_lynch.md` | 피터 린치 |
| 매수 | `cathie_wood.md` | 캐시 우드 |
| 매수 | `michael_burry.md` | 마이클 버리 |
| 매수 | `stanley_druckenmiller.md` | 스탠리 드러켄밀러 |
| 매수 | `rakesh_jhunjhunwala.md` | 라케시 중주왈라 |
| 보유 | `warren_buffett.md` | 워런 버핏 |
| 보유 | `charlie_munger.md` | 찰리 멍거 |
| 보유 | `philip_fisher.md` | 필립 피셔 |
| 보유 | `bill_ackman.md` | 빌 애크먼 |
| 보유 | `aswath_damodaran.md` | 애스워스 다모다란 |
| 보유 | `mohnish_pabrai.md` | 모니시 파브라이 |
| 매도 | `benjamin_graham.md` | 벤저민 그레이엄 |
| 매도 | `nassim_taleb.md` | 나심 탈렙 |

> **rating은 고정이 아니다.** 각 파일의 Decision Rules를 실제 기업 데이터에 적용해 판단한다.  
> "Lean bullish" → buy / "Stay neutral" → hold / "Lean bearish" → sell  
> 데이터에 따라 평소 보유 투자자가 매수로, 평소 매수 투자자가 보유로 바뀔 수 있다.

### eval 작성 규칙

1. 각 파일의 **Required Analysis Sequence** 순서로 기업 데이터를 검토한다.
2. **Decision Rules**를 적용해 bullish / neutral / bearish를 결정한다.
3. **1~2문장 한국어**로 작성: 주술 구조 정합, em dash 없음, 구체 수치 인용.
4. 투자 권유 문구 배제. **Anti-Hallucination Rules 준수** — 없는 데이터 생성 금지.

### HTML 구조

```html
<div id="sec-persona" class="sec-label">투자자 시각</div>
<div class="sc nr full">
  <div class="sh">
    <div class="sann">13인의 전설적 투자자가 {기업명}을 본다면</div>
  </div>
  <div class="persona-summary nr" id="personaSummary"></div>
  <div class="persona-grid" id="personaGrid"></div>
  <div class="disc">※ 투자자 시각은 각 인물의 공개된 투자 철학·발언을 기반으로 AI가 시뮬레이션한 가상 평가이며, 실제 의견이 아닙니다.</div>
</div>
```

### JS 렌더링

```javascript
const PERSONAS = [
  // 각 투자자 파일에서 name·type·desc 읽어와 채움, eval은 위 규칙으로 작성
  {name:'피터 린치', type:'성장주 발굴', rating:'buy',
   desc:'피델리티 마젤란 펀드 매니저. 13년간 연평균 +29% 수익률', eval:'...'},
  // ... 13개
];

function buildPersonas(){
  const buy  = PERSONAS.filter(p => p.rating === 'buy');
  const hold = PERSONAS.filter(p => p.rating === 'hold');
  const sell = PERSONAS.filter(p => p.rating === 'sell');
  const GROUPS = [
    {key:'buy',  icon:'📈', label:'매수 의견', items:buy},
    {key:'hold', icon:'📊', label:'보유 의견', items:hold},
    {key:'sell', icon:'📉', label:'매도 의견', items:sell},
  ];
  const RCLS = {buy:'rating-buy', hold:'rating-hold', sell:'rating-sell'};
  const RLBL = {buy:'매수', hold:'보유', sell:'매도'};

  document.getElementById('personaSummary').innerHTML = `
    <div class="ps-total">총 ${PERSONAS.length}명</div>
    <div class="ps-div"></div>
    <div class="ps-item"><span class="ps-dot" style="background:var(--coral)"></span>매수 ${buy.length}명</div>
    <div class="ps-item"><span class="ps-dot" style="background:#9CA3AF"></span>보유 ${hold.length}명</div>
    <div class="ps-item"><span class="ps-dot" style="background:var(--dn)"></span>매도 ${sell.length}명</div>
    <div style="margin-left:auto;font-size:.78rem;color:var(--t3);font-weight:600">투자 철학 기반 가상 시뮬레이션</div>`;

  document.getElementById('personaGrid').innerHTML = GROUPS.map(g => `
    <div class="persona-section">
      <div class="persona-section-hdr ${g.key}">
        <span>${g.icon}</span><span>${g.label}</span>
        <span class="ps-count">${g.items.length}명</span>
      </div>
      <div class="persona-cards">
        ${g.items.map(p => `
          <div class="persona-card nr">
            <div class="persona-top">
              <span class="persona-rating ${RCLS[p.rating]}">${RLBL[p.rating]}</span>
              <span class="persona-type">${p.type}</span>
            </div>
            <div class="persona-name">
              ${p.name}
              <span class="persona-q" data-tip="${p.desc}">?</span>
            </div>
            <div class="persona-eval">${p.eval}</div>
          </div>`).join('')}
      </div>
    </div>`).join('');
}
```

### 페르소나 CSS

```css
.persona-summary { display:flex; align-items:center; gap:20px; padding:16px 22px; margin-bottom:20px; flex-wrap:wrap; }
.persona-summary.nr { background:var(--bg); }
.ps-total { font-size:.92rem; font-weight:800; }
.ps-div   { width:1px; height:20px; background:var(--bdr); }
.ps-item  { display:flex; align-items:center; gap:7px; font-size:.87rem; font-weight:600; }
.ps-dot   { width:9px; height:9px; border-radius:50%; flex-shrink:0; }

.persona-section       { margin-bottom:24px; }
.persona-section-hdr   { display:flex; align-items:center; gap:9px;
                          font-size:.85rem; font-weight:700; padding:10px 16px;
                          border-radius:var(--rs); margin-bottom:12px;
                          background:var(--bg); border:1px solid var(--bdr); }
.persona-section-hdr.buy  { color:var(--coral); border-color:var(--coral-a22); }
.persona-section-hdr.hold { color:var(--t2); }
.persona-section-hdr.sell { color:var(--dn); border-color:rgba(239,68,68,.18); }
.ps-count { margin-left:auto; font-size:.78rem; opacity:.55; font-weight:600; }

.persona-cards { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
.persona-card  { padding:18px; cursor:default; overflow:visible; }
.persona-card:hover { transform:translateY(-2px); border-color:var(--bdr-h); }
[data-theme="dark"] .persona-card:hover { box-shadow:0 6px 20px rgba(0,0,0,.35); }
.persona-top   { display:flex; align-items:center; gap:7px; margin-bottom:8px; flex-wrap:wrap; }
.persona-rating{ display:inline-block; padding:2px 10px; border-radius:10px; font-size:.72rem; font-weight:700; flex-shrink:0; }
.rating-buy  { background:rgba(217,98,68,.15); color:var(--coral); }
.rating-hold { background:rgba(100,100,100,.11); color:var(--t2); }
.rating-sell { background:rgba(220,38,38,.13);  color:var(--dn); }
[data-theme="dark"] .rating-buy  { background:rgba(224,112,80,.12); }
[data-theme="dark"] .rating-hold { background:rgba(160,160,160,.10); }
[data-theme="dark"] .rating-sell { background:rgba(239,68,68,.11); }
.persona-type  { font-size:.71rem; color:var(--t3); font-weight:600; }
.persona-name  { display:flex; align-items:center; gap:5px; font-size:.92rem; font-weight:800; margin-bottom:6px; }
.persona-eval  { font-size:.83rem; color:var(--t2); line-height:1.62; }

/* ─── persona tooltip ─── */
.persona-q {
  display:inline-flex; align-items:center; justify-content:center;
  width:16px; height:16px; border-radius:50%; flex-shrink:0;
  background:var(--q-bg); color:var(--t3);
  font-size:.64rem; font-weight:800; cursor:default;
  border:1px solid var(--bdr); position:relative; transition:all .15s;
}
.persona-q:hover { background:var(--coral); color:#fff; border-color:var(--coral); }
.persona-q::after {
  content:attr(data-tip);
  position:absolute; bottom:calc(100% + 8px); left:50%;
  transform:translateX(-50%);
  background:var(--tooltip-bg); color:var(--tooltip-c); border:1px solid var(--bdr-h);
  padding:8px 13px; border-radius:9px;
  font-size:.73rem; font-weight:500; line-height:1.45;
  white-space:nowrap; pointer-events:none;
  opacity:0; transition:opacity .15s; z-index:1000;
  box-shadow:0 8px 28px rgba(0,0,0,.30);
}
.persona-q:hover::after { opacity:1; }

@media(max-width:900px){ .persona-cards{grid-template-columns:repeat(2,1fr)} }
@media(max-width:560px){ .persona-cards{grid-template-columns:1fr} }
```

---

## 기타 필수 CSS

```css
/* ─── footnote / disc ─── */
.fn { margin-top:14px; font-size:.75rem; color:var(--t3); line-height:1.9;
      padding-top:10px; border-top:1px solid var(--bdr); }
.disc { font-size:.75rem; color:var(--t3); margin-top:10px; line-height:1.7;
        padding:10px 0 0; border-top:1px solid var(--bdr); }

/* ─── table (global) ─── */
table  { width:100%; border-collapse:collapse; font-size:.88rem; }
th     { font-weight:600; color:var(--t3); padding:10px 14px; text-align:left;
         border-bottom:1px solid var(--bdr); font-size:.74rem;
         text-transform:uppercase; letter-spacing:.4px; white-space:nowrap; }
th.r   { text-align:right; }
td     { padding:10px 14px; border-bottom:1px solid var(--td-border); vertical-align:middle; }
td.r   { text-align:right; }
tr:last-child td { border-bottom:none; }
tr:hover td { background:var(--row-hover); }
.pos { color:var(--up); font-weight:700; }
.neg { color:var(--dn); font-weight:700; }
.grn { color:var(--grn); font-weight:700; }

/* ─── disclaimer ─── */
.invest-disclaimer {
  max-width:1080px; margin:32px auto 0; padding:20px 24px 60px;
  font-size:.74rem; color:var(--t3); line-height:1.90;
  border-top:1px solid var(--bdr);
}
.invest-disclaimer strong { color:var(--t2); font-weight:600; }

/* ─── print ─── */
@media print {
  .sticky-nav,.theme-btn,.skip-link,.ctrls,.tt-btn,.dp { display:none !important; }
  .sc { break-inside:avoid; box-shadow:none !important; }
  body { background:#fff !important; color:#111 !important; }
  .nr { box-shadow:none !important; border:1px solid #ddd !important; }
  .invest-disclaimer { border-top:1px solid #ddd; }
}

/* ─── responsive ─── */
@media(max-width:700px){
  .kpi-grid{grid-template-columns:1fr}
  .kpi-card:hover,.stat-card:hover,.persona-card:hover{transform:none}
  .stat-grid{grid-template-columns:repeat(2,1fr)}
  .bb-grid{grid-template-columns:1fr}
  .dp-grid{grid-template-columns:repeat(2,1fr)}
  .sc{padding:20px 16px 18px}
  .hdr-l h1{font-size:1.44rem}
  .wrap{padding:32px 16px 0}
  .sticky-nav-inner{padding:0 12px}
  .nav-link{padding:13px 12px;font-size:.88rem}
}
```

---

## 투자위험 고지사항 (페이지 하단 필수)

```html
<div class="invest-disclaimer">
  <strong>투자위험 고지사항 (Investment Risk Disclosure)</strong><br>
  본 자료는 공개된 IR 자료·뉴스·리서치 보고서를 기반으로 정보 제공 목적으로만 작성되었으며, 특정 금융투자상품의 매수·매도를 권유하거나 투자를 권고하지 않습니다.
  본 자료에 포함된 일부 수치는 추정치를 포함하고 있으며, 실제 수치와 다를 수 있습니다.
  금융투자상품 거래 시 원금 손실이 발생할 수 있으며, 투자에 관한 최종 판단과 그에 따른 손익의 책임은 전적으로 투자자 본인에게 있습니다.
  과거의 수익률이나 투자 실적이 미래의 수익을 보장하지 않습니다.
  「투자자 시각」 섹션은 각 인물의 공개된 투자 철학을 기반으로 AI가 시뮬레이션한 가상 평가이며, 해당 인물의 실제 의견이 아닙니다.
</div>
```

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
   // chart options에 반드시 포함:
   clip: false,
   layout: { padding: { top: 44 } },
   // scales.y에 반드시 포함:
   max: _segMax
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

## 트리거 표현

- "DART 리포트 / 대시보드"
- "실적 리포트 / 실적 분석 HTML / 실적 차트"
- "○○ 기업 분석 파일 만들어줘"
- "○○ 재무 리포트"
- "/dart ○○"
