---
name: dart
description: 상장사의 DART 공시 재무 데이터를 조회해 인터랙티브 애널리스트 HTML 리포트를 생성한다. 사용자가 "DART 리포트", "실적 리포트 만들어줘", "○○ 실적 분석 HTML", "○○ 대시보드", "/dart ○○" 같은 표현을 쓰면 반드시 발동한다. 기업명·분기를 파악해 DART API로 재무 데이터를 수집하고, 13인 투자자 페르소나 평가를 포함한 HTML 파일을 output/ 폴더에 생성한다.
---

# DART 애널리스트 리포트 스킬

상장사의 DART 재무·공시 데이터를 수집해 인터랙티브 HTML 리포트를 생성한다.  
KPI 차트 · 재무요약 · 공시 뉴스 · Bull/Bear · 13인 투자자 페르소나를 포함한다.

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
| 공시 목록 | `client.list_disclosures(corp_code, bgn_de, end_de, page_count=20)` | 뉴스카드용 |
| 배당 | `client.get_dividend(corp_code, year, reprt_code)` | 있을 때만 |

연결(CFS) 응답 없으면 개별(OFS)로 자동 재시도 → 차트 제목에 "(개별)" 표기.  
`status != '000'`이면 메시지 내용을 사용자에게 알리고 중단.

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

---

## HTML 디자인 시스템

카카오 대시보드(`kakao_revenue_chart.html`)와 동일한 CSS 토큰 + 레이아웃.

### 필수 섹션 (Nav 순서)

| 순번 | 섹션 ID | 내용 |
|------|---------|------|
| 1 | `sec-kpi` | KPI 카드 4개 (매출·영업이익·영업이익률·순이익, YoY 배지) |
| 2 | `sec-growth` | 매출 델타 차트 (전기 대비 waterfall) |
| 3 | `sec-finance` | 재무상태표 요약 (자산/부채/자본 구성) |
| 4 | `sec-news` | 최근 공시 카드 (공시명 + 접수일) |
| 5 | `sec-bb` | Bull / Bear 케이스 각 3개 |
| 6 | `sec-persona` | 투자자 페르소나 13인 |

### CSS 토큰

```css
:root {
  --bg:#F5F5F7; --bg-s:#FFFFFF; --bg-e:#EBEBED;
  --bdr:rgba(0,0,0,.09); --bdr-h:rgba(0,0,0,.22);
  --t1:#1A1A1A; --t2:#6B7280; --t3:#9CA3AF;
  --coral:#D96244; --coral-d:#B84E34;
  --coral-a22:rgba(217,98,68,.22); --coral-a35:rgba(217,98,68,.35);
  --up:#D96244; --dn:#DC2626; --grn:#059669;
  --r:14px; --rs:8px;
  --nav-bg:rgba(245,245,247,.92);
  --card-shadow:0 1px 3px rgba(0,0,0,.06),0 4px 16px rgba(0,0,0,.05);
  --row-hover:rgba(0,0,0,.04); --td-border:rgba(0,0,0,.05);
  --q-bg:rgba(0,0,0,.06); --prog-track:rgba(0,0,0,.07);
  --tooltip-bg:#1A1A1A; --tooltip-c:#F2F2F2;
}
[data-theme="dark"] {
  --bg:#0D0D0D; --bg-s:#161616; --bg-e:#1E1E1E;
  --bdr:rgba(255,255,255,.09); --bdr-h:rgba(255,255,255,.22);
  --t1:#F2F2F2; --t2:#9A9A9A; --t3:#5E5E5E;
  --coral:#E07050; --coral-d:#C05A3C;
  --coral-a22:rgba(224,112,80,.22); --coral-a35:rgba(224,112,80,.35);
  --nav-bg:rgba(13,13,13,.92); --card-shadow:none;
  --row-hover:rgba(255,255,255,.03); --td-border:rgba(255,255,255,.04);
  --q-bg:rgba(255,255,255,.08); --prog-track:rgba(255,255,255,.06);
}
```

### Sticky Nav

```html
<nav class="sticky-nav" id="stickyNav">
  <div class="nav-progress-track"><div class="nav-progress-bar" id="navProgress"></div></div>
  <div class="sticky-nav-outer">
    <div class="sticky-nav-inner">
      <a class="nav-link active" href="#sec-kpi">실적</a>
      <a class="nav-link" href="#sec-growth">성장</a>
      <a class="nav-link" href="#sec-finance">재무</a>
      <a class="nav-link" href="#sec-news">공시</a>
      <a class="nav-link" href="#sec-bb">Bull·Bear</a>
      <a class="nav-link" href="#sec-persona">투자자 시각</a>
    </div>
    <button class="theme-btn" id="themeBtn" onclick="toggleTheme()" aria-label="다크 모드로 전환" title="테마 전환 (T)">
      <span id="themeBtnIcon">🌙</span>
    </button>
  </div>
</nav>
```

Nav 링크 dot indicator:

```css
.nav-link { display:flex; align-items:center; gap:5px; padding:14px 18px;
            font-size:.97rem; font-weight:600; color:var(--t2);
            text-decoration:none; white-space:nowrap; letter-spacing:-.01em; }
.nav-link::before { content:''; width:5px; height:5px; border-radius:50%;
                    flex-shrink:0; background:var(--bdr-h); }
.nav-link.active { color:var(--coral); }
.nav-link.active::before { background:var(--coral); transform:scale(1.25); }
```

섹션 레이블:

```css
.sec-label { font-size:.78rem; font-weight:800; color:var(--coral);
             text-transform:uppercase; letter-spacing:1.4px;
             padding:44px 0 0 16px; position:relative; scroll-margin-top:58px; }
.sec-label::before { content:''; position:absolute; left:0; bottom:0;
                     height:1.25em; width:3px; background:var(--coral); border-radius:2px; }
```

테마 버튼 (circle):

```css
.theme-btn { background:var(--bg-e); border:1px solid var(--bdr); border-radius:50%;
             cursor:pointer; font-size:1.05rem; width:34px; height:34px; padding:0;
             flex-shrink:0; display:flex; align-items:center; justify-content:center; }
```

### 차트 tc() 헬퍼 (필수 포함)

```javascript
function tc(){
  const d = document.documentElement.getAttribute('data-theme') === 'dark';
  return {
    tick: d?'#9A9A9A':'#6B7280', grid: d?'rgba(255,255,255,.07)':'rgba(0,0,0,.06)',
    grid0: d?'rgba(255,255,255,.45)':'rgba(0,0,0,.28)',
    lblPos: d?'#F0A080':'#B84E34', lblNeg: d?'#F87171':'#DC2626',
    barLbl: d?'#C8C8C8':'#505050',
    ttBg: d?'#1E1E1E':'#FFFFFF', ttBdr: d?'rgba(255,255,255,.13)':'rgba(0,0,0,.10)',
    ttTitle: d?'#F2F2F2':'#1A1A1A', ttBody: d?'#9A9A9A':'#6B7280',
  };
}
function ttDef(c){
  return { backgroundColor:c.ttBg, borderColor:c.ttBdr, borderWidth:1,
           titleColor:c.ttTitle, bodyColor:c.ttBody, cornerRadius:9, padding:10,
           titleFont:{family:'Pretendard',weight:'700',size:12},
           bodyFont:{family:'Pretendard',size:12}, boxPadding:4 };
}
```

테마 전환 시 `rebuildCharts()` 호출로 Chart.js 인스턴스 재생성. 키보드 `T`로 토글.

---

## 투자자 페르소나 섹션

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

### HTML 렌더링

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

페르소나 CSS:

```css
.persona-section       { margin-bottom:24px; }
.persona-section-hdr   { display:flex; align-items:center; gap:9px; font-size:.8rem;
                         font-weight:800; padding:10px 16px; border-radius:var(--rs);
                         border:1px solid var(--bdr); margin-bottom:12px; }
.persona-section-hdr.buy  { color:var(--coral); border-color:var(--coral-a22); }
.persona-section-hdr.hold { color:var(--t2); }
.persona-section-hdr.sell { color:var(--dn); border-color:rgba(239,68,68,.18); }
.persona-cards { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
.persona-card  { padding:18px; cursor:default; }
.persona-top   { display:flex; align-items:center; gap:7px; margin-bottom:8px; }
.persona-rating{ display:inline-block; padding:2px 10px; border-radius:10px;
                 font-size:.72rem; font-weight:700; }
.rating-buy  { background:var(--coral-a22); color:var(--coral); }
.rating-hold { background:var(--q-bg); color:var(--t2); }
.rating-sell { background:rgba(239,68,68,.12); color:var(--dn); }
.persona-type  { font-size:.71rem; color:var(--t3); font-weight:600; }
.persona-name  { display:flex; align-items:center; gap:5px; font-size:.92rem;
                 font-weight:800; margin-bottom:6px; }
.persona-eval  { font-size:.83rem; color:var(--t2); line-height:1.62; }
.persona-q { display:inline-flex; align-items:center; justify-content:center;
             width:16px; height:16px; border-radius:50%; border:1.5px solid var(--bdr-h);
             font-size:.68rem; font-weight:700; color:var(--t3); cursor:help; position:relative; }
.persona-q::after { content:attr(data-tip); position:absolute; bottom:calc(100% + 8px);
                    left:50%; transform:translateX(-50%); background:var(--tooltip-bg);
                    color:var(--tooltip-c); font-size:.75rem; padding:8px 12px;
                    border-radius:8px; max-width:260px; white-space:normal; line-height:1.5;
                    opacity:0; pointer-events:none; transition:opacity .15s; z-index:100; }
.persona-q:hover::after { opacity:1; }
.ps-total { font-size:.88rem; font-weight:800; }
.ps-div   { width:1px; height:16px; background:var(--bdr); }
.ps-item  { display:flex; align-items:center; gap:6px; font-size:.82rem; font-weight:600; }
.ps-dot   { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
.ps-count { font-size:.75rem; font-weight:600; color:var(--t3); margin-left:auto; }
@media(max-width:900px){ .persona-cards{grid-template-columns:repeat(2,1fr)} }
@media(max-width:560px){ .persona-cards{grid-template-columns:1fr} }
```

면책 문구 (섹션 하단 필수):

```html
<div class="disc">※ 투자자 시각은 각 인물의 공개된 투자 철학·발언을 기반으로 AI가 시뮬레이션한 가상 평가이며, 실제 의견이 아닙니다.</div>
```

---

## Bull / Bear 케이스 작성

DART 공시 + 기업 개황 + 재무 데이터를 기반으로 작성. 각 3개 항목.

- **Bull**: 성장 촉매, 경쟁우위, 긍정 전망
- **Bear**: 리스크, 비용 압박, 시장 위협

문체: 주술 구조 정합, em dash 없음, 자연스러운 한국어, 투자 권유 문구 배제.

---

## 오류 처리

| 상황 | 처리 |
|------|------|
| 특정 계정 없음 | 해당 KPI "데이터 없음" 표시, 나머지 정상 렌더링 |
| API 전체 실패 | 오류 코드 + 해결법 안내 후 중단 |
| CFS 없음 | OFS 재시도, 차트 제목에 "(개별)" 표기 |
| output/ 없음 | `mkdir -p output/` 자동 생성 |
| NN 중복 체크 실패 | 타임스탬프 suffix로 폴백 |

---

## 트리거 표현

- "DART 리포트 / 대시보드"
- "실적 리포트 / 실적 분석 HTML / 실적 차트"
- "○○ 기업 분석 파일 만들어줘"
- "○○ 재무 리포트"
- "/dart ○○"
