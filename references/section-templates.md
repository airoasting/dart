# DART 리포트 HTML 구조 & JavaScript

각 섹션의 HTML 템플릿과 JavaScript 코드를 정의한다.
`{변수명}` 부분은 실제 데이터로 치환한다.

---

## 목차

| # | 섹션 | 내용 |
|---|------|------|
| 1 | 문서 헤드 | DOCTYPE, meta, Chart.js, Pretendard |
| 2 | 스킵 링크 | 접근성 |
| 3 | 헤더 | 종목명, 주가, 분기 정보 |
| 4 | Sticky Nav | 7개 메뉴 + 테마 토글 |
| 5 | sec-kpi | KPI 카드 3개 + 인사이트 칩 |
| 6 | sec-growth | 매출 델타 차트 (waterfall) |
| 7 | sec-segment | 사업별 매출 비교 바 차트 |
| 8 | sec-stock | 주가 반응 카드 + 차트 |
| 9 | sec-market | 컨센서스 + 애널리스트 표 + Bull/Bear |
| 10 | sec-news | 뉴스 카드 |
| 11 | sec-persona | 13인 투자자 페르소나 |
| 12 | 투자위험 고지사항 | 페이지 하단 필수 |
| 13 | 차트 헬퍼 | tc(), ttDef() |
| 14 | 테마 토글 | toggleTheme(), 키보드 T |
| 15 | rebuildCharts | 테마 전환 시 차트 재생성 |
| 16 | Nav 스크롤 감지 | active 링크 + progress bar |
| 17 | DOMContentLoaded | 초기화 7개 함수 |
| 18 | 섹션 애니메이션 | IntersectionObserver |

---

## 1. 문서 헤드

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
/* design-system.md의 CSS 전체를 여기에 삽입 */
</style>
</head>
```

**절대 규칙**:
- Chart.js는 반드시 **4.4.4** (4.4.3 아님)
- Pretendard는 `<style>` 안 `@import url(...)` 방식 (Google Fonts `<link>` 사용 금지)
- 모든 Chart.js 바 차트는 `clip:false` + `layout:{padding:{top:44}}` 적용
- 모든 Y축은 데이터 기반 자동 계산 (하드코딩 수치 절대 금지)

---

## 2. 스킵 링크

```html
<body>
<a href="#sec-kpi" class="skip-link">콘텐츠로 바로가기</a>
```

---

## 3. 헤더

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

---

## 4. Sticky Nav

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

<div style="max-width:1080px;margin:0 auto;padding:0 20px">
```

---

## 5. sec-kpi — KPI 카드

### HTML

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

### JS — buildChips

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

## 6. sec-growth — 성장 기여도 차트

### HTML

```html
<div id="sec-growth" class="sec-label">성장 기여도 분석</div>
<div class="sc nr full">
  <div class="sh">
    <div class="sann">순증 <strong style="color:var(--coral)">+{총순증}억</strong> &nbsp;= 성장 기여 <strong style="color:var(--coral)">+{성장기여}억</strong> + 감소 요인 <strong style="color:var(--dn)">-{감소요인}억</strong> &nbsp;<span style="color:var(--t3);font-size:.80rem">* 추정치 포함</span></div>
  </div>
  <div class="cw" style="height:360px"><canvas id="deltaChart"></canvas></div>
</div>
```

### JS — buildDeltaChart

```javascript
let deltaChartInst=null;

function buildDeltaChart(){
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
  const _dMax=Math.max(...vals.filter(v=>v>0),0);
  const _dMin=Math.min(...vals.filter(v=>v<0),0);
  deltaChartInst=new Chart(document.getElementById('deltaChart').getContext('2d'),{
    type:'bar',
    data:{labels:DATA.map(d=>d.name.split('\n')),
          datasets:[{data:vals,backgroundColor:cols,borderColor:bors,borderWidth:1.5,borderRadius:6}]},
    options:{responsive:true,maintainAspectRatio:false,
      clip:false,
      layout:{padding:{top:44}},
      plugins:{legend:{display:false},tooltip:{...ttDef(c),callbacks:{label:ctx=>`${sgn(ctx.raw)}${ctx.raw.toLocaleString('ko-KR')}억${DATA[ctx.dataIndex].est?' (추정)':''}`}}},
      scales:{
        x:{grid:{display:false},ticks:{color:c.tick,font:{size:11.5,family:'Pretendard'}}},
        y:{min:_dMin!==0?_dMin*1.3:undefined,
           max:_dMax!==0?Math.ceil(_dMax*1.30/100)*100:undefined,
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

## 7. sec-segment — 사업별 매출

### HTML

```html
<div id="sec-segment" class="sec-label">사업별 매출 상세</div>
<div class="sc nr full">
  <div class="sh">
    <div class="sann">막대 클릭 시 상세 드릴다운</div>
  </div>
  <div class="ctrls">
    <div class="cg" id="fg">
      <button class="cb active" onclick="setF('all',this)">전체</button>
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

### JS — 세그먼트 데이터 & 차트

```javascript
const SEGS=[
  {name:'사업부A', sub:'카테고리1', cat:'cat1', q25:XXXX, q26:XXXX, est:false},
  {name:'사업부B', sub:'카테고리2', cat:'cat2', q25:XXXX, q26:XXXX, est:true},
];
const TOT25=전년총매출억;
const TOT26=당기총매출억;

const pv  =(a,b)=>a?(b-a)/a*100:null;
const sgn =n=>n>=0?'+':'';
const fmt =n=>n===0?'재편/미공시':n.toLocaleString('ko-KR')+'억';
const mix =(v,t)=>t?(v/t*100).toFixed(1)+'%':'-';

let fil='all', srt='size', segC=null;

function vis(){
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
  const _allVals=data.flatMap(s=>[s.q25,s.q26>0?s.q26:0]).filter(Boolean);
  const _segMax=Math.ceil(Math.max(..._allVals)*1.20/1000)*1000;
  segC=new Chart(ctx,{
    type:'bar',
    data:{labels,datasets:[
      {label:'{전년}분기',data:data.map(s=>s.q25),
       backgroundColor:c.seg25,borderColor:c.seg25b,borderWidth:1.5,borderRadius:5},
      {label:'{당기}분기',data:data.map(s=>s.q26>0?s.q26:null),
       backgroundColor:data.map(s=>s.q26>s.q25?c.segUp:c.segDn),
       borderColor:data.map(s=>s.q26>s.q25?c.segUpB:c.segDnB),borderWidth:1.5,borderRadius:5},
    ]},
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
document.getElementById('fn1').innerHTML='* 추정치: {추정 기준 설명}';
```

---

## 8. sec-stock — 주가 반응

### HTML

```html
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

### JS — buildStockCharts

```javascript
const PRICE_DATA=[
  {d:'MM/DD', p:XXXXX},
  {d:'MM/DD', p:XXXXX, earnings:true},
  {d:'MM/DD', p:XXXXX},
];
const EARN_IDX=실적발표일_인덱스;
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

  const tpLabels=[
    ['현재가', CURR.toLocaleString('ko-KR')+'원'],
  ];
  const tpVals=[CURR];
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

## 9. sec-market — 애널리스트 시각 + Bull/Bear

> Bull/Bear는 이 섹션 안에 있다. 독립 `sec-bb` 섹션으로 분리하지 말 것.

### HTML

```html
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

### JS — buildMarket

```javascript
const ANALYSTS=[
  {firm:'증권사A', r:'Buy', tp:XXXXX, from:XXXXX, date:'YYYY.MM.DD', note:'"코멘트"'},
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

  document.getElementById('bullList').innerHTML=
    BULLS.map((b,i)=>`<div class="bb-item"><span class="num">${i+1}</span>
      <div class="txt"><strong>${b.t}</strong><br>${b.d}</div></div>`).join('');
  document.getElementById('bearList').innerHTML=
    BEARS.map((b,i)=>`<div class="bb-item"><span class="num">${i+1}</span>
      <div class="txt"><strong>${b.t}</strong><br>${b.d}</div></div>`).join('');
}
```

---

## 10. sec-news — 뉴스 카드

### HTML

```html
<div id="sec-news" class="sec-label">최신 뉴스</div>
<div class="sc nr full" style="padding:20px 24px">
  <div id="newsGrid"></div>
</div>
```

### JS — buildNews

```javascript
const NEWS=[
  {h:'뉴스 제목', src:'언론사', date:'YYYY.MM.DD', sent:'pos',
   url:'https://...', body:'뉴스 본문 요약'},
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

---

## 11. sec-persona — 투자자 페르소나

### HTML

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

### JS — buildPersonas

```javascript
const PERSONAS = [
  {name:'피터 린치', type:'성장주 발굴', rating:'buy',
   desc:'피델리티 마젤란 펀드 매니저. 13년간 연평균 +29% 수익률', eval:'...'},
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

---

## 12. 투자위험 고지사항

```html
</div><!-- max-width wrapper 닫기 -->

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

## 13. 차트 헬퍼

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

---

## 14. 테마 토글

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

document.addEventListener('keydown',e=>{
  if((e.key==='t'||e.key==='T')&&!e.ctrlKey&&!e.metaKey&&!e.altKey){
    const tag=document.activeElement.tagName;
    if(tag!=='INPUT'&&tag!=='TEXTAREA'&&tag!=='SELECT'){toggleTheme();}
  }
});
```

---

## 15. rebuildCharts

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

## 16. Nav 스크롤 감지

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

## 17. DOMContentLoaded

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

## 18. 섹션 애니메이션

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
