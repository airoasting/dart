# DART 리포트 CSS 디자인 시스템

HTML `<style>` 태그 안에 아래 CSS를 **그대로** 삽입한다.
순서를 바꾸지 않는다. 토큰 값을 임의로 변경하지 않는다.

---

## 목차

| # | 섹션 | 용도 |
|---|------|------|
| 1 | 디자인 토큰 (Light / Dark) | 색상·반경·그림자 변수 |
| 2 | 리셋 & 전역 | box-sizing, scroll-behavior |
| 3 | 테마 전환 트랜지션 | 모든 카드·표면에 .22s ease |
| 4 | Body & 래퍼 | 폰트, 배경, max-width |
| 5 | 서피스 클래스 | .nr, .ni, .ni-sm |
| 6 | 헤더 | .hdr, .price-now, .price-chg |
| 7 | 스킵 링크 | 접근성 |
| 8 | Sticky Nav | 7개 링크, progress bar |
| 9 | 테마 토글 버튼 | .theme-btn |
| 10 | 섹션 레이블 & 컨테이너 | .sec-label, .sc, .sh |
| 11 | KPI 그리드 | .kpi-card, 애니메이션 |
| 12 | 인사이트 칩 | .chips, .chip |
| 13 | 세그먼트 컨트롤 | 필터·정렬 버튼, 범례, 드릴다운, 테이블 |
| 14 | Stat 카드 | 주가 반응 4칸 |
| 15 | 차트 래퍼 | .cw |
| 16 | 애널리스트 컨센서스 | .cons-wrap, .tp-sum, .at-wrap |
| 17 | Bull / Bear | .bb-grid, .bb-card |
| 18 | 뉴스 카드 | .news-card, .sent-badge |
| 19 | 페르소나 | .persona-card, 툴팁 |
| 20 | 테이블 (전역) | th, td, .pos, .neg |
| 21 | 기타 | .fn, .disc, .invest-disclaimer |
| 22 | 섹션 입장 애니메이션 | .sc-anim |
| 23 | 프린트 | @media print |
| 24 | 반응형 | @media (max-width) |

---

## 1. 디자인 토큰

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

## 2. 리셋 & 전역

```css
html { scroll-behavior: smooth; }
*,*::before,*::after { box-sizing:border-box; margin:0; padding:0; }
```

---

## 3. 테마 전환 트랜지션

```css
body,
.nr,.ni,.ni-sm,.sc,.hdr,.kpi-card,.stat-card,.bb-card,
.news-card,.persona-card,.persona-section-hdr,
.persona-summary,.cw,.dp,.cg,.cb,.lb,.tp-sum,.cons-bw,
.sticky-nav,.chip,.tt-btn,.dt-wrap,.theme-btn,
td,th { transition: background-color .22s ease, border-color .22s ease, color .18s ease, box-shadow .22s ease, transform .15s ease; }
```

---

## 4. Body & 래퍼

```css
body {
  background: var(--bg);
  font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
  color: var(--t1);
  padding-bottom: 80px;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
.wrap { max-width: 1080px; margin: 0 auto; padding: 48px 24px 0; }
```

---

## 5. 서피스 클래스

```css
.nr    { background:var(--bg-s); border:1px solid var(--bdr); border-radius:var(--r); box-shadow:var(--card-shadow); }
.ni    { background:var(--bg);   border:1px solid var(--bdr); border-radius:var(--rs); }
.ni-sm { background:var(--bg);   border:1px solid var(--bdr); border-radius:var(--rs); }
```

---

## 6. 헤더

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

## 7. 스킵 링크

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

## 8. Sticky Nav

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
  -ms-overflow-style: none;
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
```

---

## 9. 테마 토글 버튼

```css
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

## 10. 섹션 레이블 & 컨테이너

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
.sc { padding:28px 28px 24px; margin:20px auto; max-width:1080px; }
.sc.full { border-radius:var(--r); }
.sh { display:flex; justify-content:space-between; align-items:baseline;
      flex-wrap:wrap; gap:8px; margin-bottom:18px; }
.stitle { font-size:.75rem; font-weight:700; color:var(--coral);
          text-transform:uppercase; letter-spacing:.8px; }
.sann   { font-size:.86rem; font-weight:500; color:var(--t2); }
```

---

## 11. KPI 그리드

```css
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

## 12. 인사이트 칩

```css
.chips { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:20px; }
.chip  { padding:6px 14px; border-radius:20px; font-size:.83rem; font-weight:600;
         display:flex; align-items:center; gap:6px;
         background:var(--bg-e); border:1px solid var(--bdr); cursor:default;
         transition:border-color .13s, box-shadow .13s; }
.chip:hover { border-color:var(--bdr-h); box-shadow:0 2px 8px rgba(0,0,0,.06); }
.chip .dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
.chip.co { color:var(--coral); } .chip.dn { color:var(--dn); } .chip.gn { color:var(--grn); }
```

---

## 13. 세그먼트 컨트롤

```css
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
/* drill-down panel */
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
/* table toggle */
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

---

## 14. Stat 카드

```css
.stat-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:22px; }
.stat-card { padding:20px 18px; }
.stat-lbl  { font-size:.72rem; font-weight:600; color:var(--t3); text-transform:uppercase;
             letter-spacing:.6px; margin-bottom:8px; }
.stat-val  { font-size:1.52rem; font-weight:800; letter-spacing:-1px; }
.stat-sub  { font-size:.80rem; color:var(--t3); margin-top:5px; }
.stat-card:hover { transform:translateY(-2px); border-color:var(--bdr-h); }
@media(max-width:768px){ .stat-grid{grid-template-columns:repeat(2,1fr)} }
```

---

## 15. 차트 래퍼

```css
.cw { position:relative; }
```

---

## 16. 애널리스트 컨센서스

```css
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
/* analyst table */
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
```

---

## 17. Bull / Bear

```css
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

---

## 18. 뉴스 카드

```css
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

## 19. 페르소나

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

/* persona tooltip */
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

## 20. 테이블 (전역)

```css
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
```

---

## 21. 기타

```css
.fn { margin-top:14px; font-size:.75rem; color:var(--t3); line-height:1.9;
      padding-top:10px; border-top:1px solid var(--bdr); }
.disc { font-size:.75rem; color:var(--t3); margin-top:10px; line-height:1.7;
        padding:10px 0 0; border-top:1px solid var(--bdr); }

.invest-disclaimer {
  max-width:1080px; margin:32px auto 0; padding:20px 24px 60px;
  font-size:.74rem; color:var(--t3); line-height:1.90;
  border-top:1px solid var(--bdr);
}
.invest-disclaimer strong { color:var(--t2); font-weight:600; }
```

---

## 22. 섹션 입장 애니메이션

```css
.sc.sc-anim { opacity:0; transform:translateY(14px); }
.sc.sc-anim.sc-visible { opacity:1; transform:none; transition:opacity .45s cubic-bezier(.4,0,.2,1), transform .45s cubic-bezier(.4,0,.2,1); }
```

---

## 23. 프린트

```css
@media print {
  .sticky-nav,.theme-btn,.skip-link,.ctrls,.tt-btn,.dp { display:none !important; }
  .sc { break-inside:avoid; box-shadow:none !important; }
  body { background:#fff !important; color:#111 !important; }
  .nr { box-shadow:none !important; border:1px solid #ddd !important; }
  .invest-disclaimer { border-top:1px solid #ddd; }
}
```

---

## 24. 반응형

```css
@media(max-width:700px){
  .kpi-grid{grid-template-columns:1fr}
  .kpi-card:hover,.stat-card:hover,.persona-card:hover{transform:none}
  .stat-grid{grid-template-columns:repeat(2,1fr)}
  .bb-grid{grid-template-columns:1fr}
  .cons-wrap{grid-template-columns:1fr}
  .dp-grid{grid-template-columns:repeat(3,1fr)}
  .sc{padding:20px 16px 18px}
  .hdr-l h1{font-size:1.44rem}
  .wrap{padding:32px 16px 0}
  .sticky-nav-inner{padding:0 12px}
  .nav-link{padding:13px 12px;font-size:.88rem}
}
```
