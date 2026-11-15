#!/usr/bin/env python3
"""README 스크린샷 7장을 리포트 HTML에서 다시 찍는다.

사용법:
    python3 assets/capture_screenshots.py <리포트.html> [저장 폴더]

저장 폴더를 생략하면 이 스크립트 옆의 screenshots/에 쓴다. 파일 이름과 순서는 README가 쓰는 그대로다.
Playwright와 Chromium이 필요하다(pip install playwright && playwright install chromium).
예시 리포트를 바꿀 때마다 한 번 돌리고, 썸네일(assets/thumbnail.html)의 숫자도 함께 맞춘다.
"""
import sys
from pathlib import Path

SHOTS = [  # (파일 이름, 섹션 라벨 id. None이면 맨 위 헤더)
    ("01_hero.png", None),
    ("02_kpi.png", "sec-kpi"),
    ("03_growth.png", "sec-growth"),
    ("04_segment.png", "sec-segment"),
    ("06_market.png", "sec-market"),
    ("07_news.png", "sec-news"),
    ("08_persona.png", "sec-persona"),
]

BOX_JS = """(id) => {
  if (!id) { const r = document.querySelector('.hdr').parentElement.getBoundingClientRect();
             return {x: 0, y: r.top + scrollY, width: innerWidth, height: r.height}; }
  const lab = document.getElementById(id), card = lab.nextElementSibling;
  const a = lab.getBoundingClientRect(), b = card.getBoundingClientRect();
  return {x: b.left + scrollX, y: a.top + scrollY, width: b.width, height: b.bottom - a.top};
}"""


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    html = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path(__file__).resolve().parent / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1240, "height": 900}, device_scale_factor=2)
        page.goto(html.as_uri())
        page.wait_for_timeout(2500)   # 차트 애니메이션이 끝날 때까지
        page.add_style_tag(content=".sticky-nav{position:static !important}")   # 긴 캡처에 내비게이션이 겹치지 않게
        page.wait_for_timeout(300)
        for name, sec in SHOTS:
            box = page.evaluate(BOX_JS, sec)
            page.screenshot(path=str(out / name), clip=box, full_page=True)
            print(f"{name}  {round(box['width'] * 2)}x{round(box['height'] * 2)}")
        browser.close()


if __name__ == "__main__":
    main()
