#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTML 리포트를 PDF로 굽는다.

왜 별도 스크립트가 필요한가
    리포트 HTML은 화면용이다. 섹션은 스크롤해야 나타나고(IntersectionObserver),
    KPI 카드는 지연 애니메이션으로 뜨고, 차트는 Chart.js 가 CDN에서 내려온 뒤에
    캔버스에 그려진다. 브라우저의 인쇄 스냅샷은 스크롤도 애니메이션 완료도
    기다려주지 않기 때문에, 그냥 인쇄하면 절반이 빈 페이지로 나온다.
    이 스크립트는 인쇄 직전에 그 연출을 걷어내고 차트를 무애니메이션으로
    다시 그린 다음 PDF를 만든다. 구버전 리포트 HTML도 런타임 주입으로 함께 고친다.

사용
    python3 assets/html2pdf.py output/카카오_20260704_01.html
    python3 assets/html2pdf.py output/*.html -o output/pdf
    python3 assets/html2pdf.py report.html --keep-dark      # 다크 팔레트 유지

엔진
    Playwright 가 설치돼 있으면 그것을 쓰고(페이지 번호 꼬리말까지 붙는다),
    없으면 시스템에 깔린 Chrome/Edge/Brave 를 headless 로 불러 쓴다.
    둘 다 없으면 브라우저에서 Cmd+P 로 뽑아도 된다. 리포트 자체에
    인쇄 보정이 들어 있어 화면과 같은 내용이 나온다.

    더 좋은 결과를 원하면:
        pip install playwright && python3 -m playwright install chromium
"""

from __future__ import annotations

import argparse
import pathlib
import sys

# ── 지면 규격 ────────────────────────────────────────────────
# 뷰포트 폭을 인쇄 본문 폭과 일치시켜, PDF 생성 시점의 재레이아웃을 없앤다.
# 재레이아웃이 일어나면 Chart.js 가 resize 콜백에서 캔버스를 다시 그리는데
# 그 시점이 스냅샷보다 늦으면 차트가 빈칸으로 남는다.
PAGE_W_MM = 210.0
MARGIN = {"top": "12mm", "right": "10mm", "bottom": "14mm", "left": "10mm"}
MARGIN_X_MM = 20.0
CONTENT_PX = round((PAGE_W_MM - MARGIN_X_MM) / 25.4 * 96)  # 718

# ── 인쇄용 CSS (구버전 HTML 보정용. 신버전 template.html 에는 이미 내장) ──
PRINT_CSS = """
@page { size: A4; margin: 12mm 10mm 14mm; }
@media print {
  :root, :root[data-theme="dark"] {
    --bg:#FFFFFF; --bg-s:#FFFFFF; --bg-e:#F3F4F6;
    --bdr:rgba(0,0,0,.16); --bdr-h:rgba(0,0,0,.28);
    --t1:#111111; --t2:#4B5563; --t3:#6B7280;
    --coral:#C0522F; --coral-d:#A24428; --coral-l:rgba(192,82,47,.80);
    --coral-a22:rgba(192,82,47,.22); --coral-a35:rgba(192,82,47,.35);
    --up:#C0522F; --dn:#C02626; --grn:#047857;
    --card-shadow:none; --row-hover:transparent;
    --td-border:rgba(0,0,0,.10); --q-bg:rgba(0,0,0,.06);
    --prog-track:rgba(0,0,0,.10);
    --tooltip-bg:#FFFFFF; --tooltip-c:#111111;
  }
  html, body, .sc, .nr, .ni, .ni-sm, .kpi-card, .stat-card, .bb-card,
  .persona-card, .news-card, .chip, .cw, .lb, .persona-rating,
  .persona-section-hdr, .cons-bw, .cons-bf, th, td {
    -webkit-print-color-adjust:exact; print-color-adjust:exact;
  }
  *, *::before, *::after { animation:none !important; transition:none !important; }
  .sc, .sc.sc-anim, .sc.sc-anim.sc-visible,
  .kpi-card, .stat-card, .bb-card, .persona-card, .news-card {
    opacity:1 !important; transform:none !important; filter:none !important;
  }
  .sticky-nav, .theme-btn, .skip-link, .ctrls, .tt-btn, .dp,
  .persona-q, .dp-close { display:none !important; }
  .dt-wrap { display:block !important; overflow:visible !important; }
  /* 화면에서는 가로 스크롤로 넘기던 표가 지면에서는 잘려 나간다.
     열 너비를 고정해 지면 폭 안에 접어 넣는다. */
  .dt-wrap table { table-layout:fixed; width:100%; font-size:.70rem; }
  .dt-wrap th, .dt-wrap td { padding:7px 6px; word-break:break-word; }
  table { max-width:100%; }
  body { background:#fff !important; color:#111 !important; }
  .wrap, .sc { margin-top:0; }
  .sec-label { break-after:avoid; page-break-after:avoid;
               break-inside:avoid; padding-top:22px; }
  .sc { box-shadow:none !important; padding:20px 20px 18px; margin:12px auto; }
  .kpi-card, .stat-card, .bb-card, .persona-card, .news-card,
  .cw, .cons-wrap { break-inside:avoid; page-break-inside:avoid; }
  /* 페이지보다 긴 그룹에 break-inside:avoid 를 걸면 통째로 밀려 여백만 커진다.
     묶는 단위는 카드로 두고, 그룹 머리말만 뒤 내용과 붙인다. */
  .persona-section-hdr { break-after:avoid; page-break-after:avoid; }
  tr, th, td { break-inside:avoid; }
  thead { display:table-header-group; }
  .nr { box-shadow:none !important; border:1px solid rgba(0,0,0,.16) !important; }
  .invest-disclaimer { border-top:1px solid rgba(0,0,0,.16); padding-bottom:0; }
  canvas { max-width:100% !important; }
  /* 화면용 차트 높이(360~420px)는 A4 한 장을 거의 다 먹는다.
     지면에서는 낮춰서 섹션이 앞 페이지에 같이 들어가게 한다. */
  .cw { height:300px !important; }
  #segWrap { height:380px !important; }
  /* 차트를 화면 높이로 먼저 그린 경우(시스템 Chrome 경로) 캔버스가
     줄어든 상자를 넘쳐 다음 요소를 덮는다. 상자에 맞춰 가둔다. */
  .cw { overflow:hidden; }
  .cw canvas { width:100% !important; height:100% !important; }
  a { text-decoration:none; color:inherit; }
}
"""

# ── 인쇄 준비 스크립트 (신·구버전 모두에서 단독 동작) ──────────
PREP_JS = """() => {
  const report = { sections: 0, charts: 0, table: false, chartjs: !!window.Chart, errors: [] };

  // 1. 스크롤 등장 대기 중인 섹션을 전부 노출
  document.querySelectorAll('.sc').forEach(el => {
    el.classList.remove('sc-anim');
    el.classList.add('sc-visible');
    el.style.opacity = '1';
    el.style.transform = 'none';
    report.sections++;
  });

  // 2. 차트를 애니메이션 없이 현재(지면) 폭으로 다시 그린다
  if (window.Chart) {
    try {
      Chart.defaults.animation = false;
      Chart.defaults.animations = false;
      if (typeof rebuildCharts === 'function') rebuildCharts();
      const reg = Chart.instances || {};
      Object.values(reg).forEach(c => { try { c.resize(); c.update('none'); } catch (e) {} });
      report.charts = Object.keys(reg).length;
    } catch (e) { report.errors.push('charts: ' + e.message); }
  } else {
    report.errors.push('Chart.js 미로드 (CDN 차단 또는 오프라인)');
  }

  // 3. 데이터 테이블을 펼쳐 숫자를 지면에 남긴다
  try {
    const w = document.getElementById('dtW');
    if (w) {
      w.classList.add('on');
      if (typeof renderTbl === 'function') renderTbl();
      report.table = true;
    }
  } catch (e) { report.errors.push('table: ' + e.message); }

  return report;
}"""

# ── 지면 꼬리말 (제목 + 페이지 번호) ──────────────────────────
FOOT_FONT = "-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif"
EMPTY_HEADER = "<span></span>"


def footer_template(title: str) -> str:
    safe = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f'<div style="width:100%;font-size:7.5pt;color:#9CA3AF;font-family:{FOOT_FONT};'
        f'padding:0 10mm;display:flex;justify-content:space-between;align-items:center">'
        f'<span>{safe}</span>'
        f'<span><span class="pageNumber"></span> / <span class="totalPages"></span></span>'
        f'</div>'
    )


FORCE_LIGHT_JS = """() => {
  try { localStorage.setItem('theme', 'light'); } catch (e) {}
  document.documentElement.setAttribute('data-theme', 'light');
}"""


def convert(page, src: pathlib.Path, dst: pathlib.Path, keep_dark: bool = False) -> dict:
    """HTML 한 건을 PDF로 변환하고 진단 정보를 돌려준다."""
    console: list[str] = []
    page.on("console", lambda m: console.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))

    page.goto(src.resolve().as_uri(), wait_until="load", timeout=60_000)
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass  # CDN 지연/차단. 아래에서 Chart.js 유무로 잡는다.

    if not keep_dark:
        page.evaluate(FORCE_LIGHT_JS)

    page.add_style_tag(content=PRINT_CSS)
    page.emulate_media(media="print")  # 지면 레이아웃으로 먼저 전환한 뒤 차트를 그린다

    try:
        page.evaluate("document.fonts && document.fonts.ready")
    except Exception:
        pass

    report = page.evaluate(PREP_JS)
    page.wait_for_timeout(600)  # 캔버스 draw 완료 대기

    title = page.title() or src.stem
    dst.parent.mkdir(parents=True, exist_ok=True)
    page.pdf(
        path=str(dst),
        format="A4",
        print_background=True,
        # 크롬 기본 머리말(인쇄 날짜)·꼬리말(file:// 전체 경로) 대신 직접 지정
        display_header_footer=True,
        header_template=EMPTY_HEADER,
        footer_template=footer_template(title),
        margin=MARGIN,
        scale=1.0,
    )
    report["console_errors"] = console
    return report


# ── 폴백 엔진: 시스템에 깔린 Chrome/Edge/Brave ──────────────
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "/usr/bin/microsoft-edge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def find_chrome() -> str | None:
    import shutil
    for c in CHROME_CANDIDATES:
        if pathlib.Path(c).exists():
            return c
    for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


# 폴백 경로에서는 실행 훅이 없으므로, 임시 사본에 인쇄 준비 스크립트를 심는다.
FALLBACK_INJECT = """
<style>%s</style>
<script>
window.addEventListener('load', function(){
  setTimeout(function(){
    try { (window.prepareForPrint || (%s))(); } catch (e) { console.error(e); }
  }, 400);
});
</script>
</body>"""


def convert_with_chrome(chrome: str, src: pathlib.Path, dst: pathlib.Path) -> dict:
    """Playwright 없이 시스템 Chrome 으로 변환한다. 페이지 번호는 붙지 않는다."""
    import subprocess, tempfile, time

    html = src.read_text(encoding="utf-8", errors="replace")
    inject = FALLBACK_INJECT % (PRINT_CSS, PREP_JS)
    patched = html.replace("</body>", inject, 1) if "</body>" in html else html + inject

    # 상대 경로 참조가 있어도 깨지지 않도록 원본과 같은 폴더에 임시 사본을 둔다.
    tmp = src.with_name(f".{src.stem}.print.tmp.html")
    prof = pathlib.Path(tempfile.mkdtemp(prefix="dart-pdf-"))
    try:
        tmp.write_text(patched, encoding="utf-8")
        dst.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            chrome, "--headless", "--disable-gpu", "--no-sandbox",
            "--no-pdf-header-footer",          # 인쇄 날짜·file:// 경로 제거
            "--virtual-time-budget=10000",     # CDN 로드와 차트 draw 대기
            "--run-all-compositor-stages-before-draw",
            f"--user-data-dir={prof}",
            f"--print-to-pdf={dst.resolve()}",
            tmp.resolve().as_uri(),
        ]
        # 일부 Chrome 버전은 PDF를 다 쓰고도 프로세스가 살아 있다.
        # 종료를 기다리지 않고, 파일 크기가 멎으면 완료로 보고 정리한다.
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline, last, stable = time.monotonic() + 90, -1, 0
        try:
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    break
                size = dst.stat().st_size if dst.exists() else 0
                stable = stable + 1 if size > 0 and size == last else 0
                last = size
                if stable >= 3:          # 0.9초간 크기 변화 없음
                    break
                time.sleep(0.3)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        if not dst.exists() or dst.stat().st_size == 0:
            raise RuntimeError("Chrome이 PDF를 만들지 못했습니다")
        return {"sections": "-", "charts": "-", "table": True, "errors": [], "console_errors": []}
    finally:
        tmp.unlink(missing_ok=True)
        import shutil as _sh
        _sh.rmtree(prof, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="DART 리포트 HTML을 PDF로 변환한다.")
    ap.add_argument("html", nargs="+", help="변환할 HTML 파일")
    ap.add_argument("-o", "--outdir", default=None, help="PDF 저장 폴더 (기본: HTML과 같은 폴더)")
    ap.add_argument("--keep-dark", action="store_true", help="다크 팔레트 그대로 인쇄")
    ap.add_argument("--engine", choices=("auto", "playwright", "chrome"), default="auto",
                    help="변환 엔진 (기본 auto: playwright 우선, 없으면 시스템 Chrome)")
    args = ap.parse_args()

    targets = [pathlib.Path(h) for h in args.html]
    missing = [t for t in targets if not t.is_file()]
    if missing:
        for m in missing:
            print(f"파일 없음: {m}", file=sys.stderr)
        return 1

    def out_path(src: pathlib.Path) -> pathlib.Path:
        d = pathlib.Path(args.outdir) if args.outdir else src.parent
        return d / (src.stem + ".pdf")

    # ── 엔진 선택 ────────────────────────────────────────────
    engine = args.engine
    if engine in ("auto", "playwright"):
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            engine = "playwright"
        except ImportError:
            if args.engine == "playwright":
                print("playwright 가 없습니다.  pip install playwright && "
                      "python3 -m playwright install chromium", file=sys.stderr)
                return 2
            engine = "chrome"

    if engine == "playwright":
        return run_playwright(targets, out_path, args.keep_dark)

    chrome = find_chrome()
    if not chrome:
        print("Chrome·Edge·Chromium 중 하나가 필요합니다.\n"
              "  방법 1) 브라우저에서 HTML을 열고 Cmd+P → PDF로 저장 "
              "(인쇄 설정에서 '배경 그래픽' 켜기)\n"
              "  방법 2) pip install playwright && python3 -m playwright install chromium",
              file=sys.stderr)
        return 2

    why = "지정됨" if args.engine == "chrome" else "playwright 없음"
    print(f"({why}. 시스템 브라우저로 변환합니다: {pathlib.Path(chrome).name})", file=sys.stderr)
    failed = 0
    for src in targets:
        dst = out_path(src)
        try:
            convert_with_chrome(chrome, src, dst)
            print(f"OK  {dst}  ({dst.stat().st_size // 1024}KB)")
        except Exception as e:
            failed += 1
            print(f"실패 {src}: {e}", file=sys.stderr)
    return 1 if failed else 0


def run_playwright(targets, out_path, keep_dark: bool) -> int:
    from playwright.sync_api import sync_playwright

    failed = 0
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:
            # 브라우저 바이너리 미설치. 시스템 Chrome 으로 넘긴다.
            chrome = find_chrome()
            if not chrome:
                print(f"Chromium 실행 실패: {e}\n"
                      f"  python3 -m playwright install chromium", file=sys.stderr)
                return 2
            print(f"(playwright 브라우저 미설치. {pathlib.Path(chrome).name} 로 대체합니다)",
                  file=sys.stderr)
            for src in targets:
                dst = out_path(src)
                try:
                    convert_with_chrome(chrome, src, dst)
                    print(f"OK  {dst}  ({dst.stat().st_size // 1024}KB)")
                except Exception as ee:
                    failed += 1
                    print(f"실패 {src}: {ee}", file=sys.stderr)
            return 1 if failed else 0

        ctx = browser.new_context(
            viewport={"width": CONTENT_PX, "height": 1000},
            device_scale_factor=2,
        )
        for src in targets:
            dst = out_path(src)
            page = ctx.new_page()
            try:
                r = convert(page, src, dst, keep_dark=keep_dark)
                size_kb = dst.stat().st_size // 1024
                print(f"OK  {dst}  ({size_kb}KB, 섹션 {r['sections']}개, 차트 {r['charts']}개"
                      f"{', 테이블 포함' if r['table'] else ''})")
                for e in r["errors"] + r["console_errors"]:
                    print(f"    경고: {e}", file=sys.stderr)
            except Exception as e:
                failed += 1
                print(f"실패 {src}: {e}", file=sys.stderr)
            finally:
                page.close()
        ctx.close()
        browser.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
