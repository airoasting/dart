# PDF 변환

사용자가 PDF나 인쇄본을 요청할 때만 쓴다.

```bash
python3 ~/.claude/skills/dart/assets/html2pdf.py output/카카오_20260704_01.html
python3 ~/.claude/skills/dart/assets/html2pdf.py output/*.html -o output/pdf
```

## 왜 전용 변환기인가

리포트는 화면용이라 섹션이 스크롤할 때 나타나고(IntersectionObserver), KPI 카드는 지연 애니메이션으로 뜨고, 차트는 Chart.js가 CDN에서 내려온 뒤 그려진다. 브라우저의 인쇄 스냅샷은 이 셋을 기다리지 않아서 그냥 인쇄하면 절반이 빈 페이지로 나온다. `html2pdf.py`는 인쇄 직전에 숨은 섹션을 펼치고 차트를 애니메이션 없이 다시 그린 뒤 A4로 굽는다. 데이터 테이블도 펼쳐 숫자를 지면에 남긴다.

## 엔진 (자동 선택, 추가 설치 불필요)

| 순위 | 엔진 | 조건 | 결과 |
|:---:|------|------|------|
| 1 | Playwright | `pip install playwright` 완료 | A4 + 페이지 번호 꼬리말 |
| 2 | 시스템 Chrome/Edge/Brave | 브라우저가 깔려 있음 (대부분) | A4, 페이지 번호 없음 |
| 3 | 수동 | 위 둘 다 없음 | 브라우저에서 `Cmd+P`, 인쇄 설정에서 "배경 그래픽" 켜기 |

3번이 되는 이유는 `template.html`에 인쇄 보정과 `beforeprint` 훅이 들어 있기 때문이다. 엔진을 직접 고르려면 `--engine playwright|chrome`.

`wkhtmltopdf`·`weasyprint`는 쓰지 않는다. 이 리포트의 CSS 변수, `:has()`, Canvas 차트를 처리하지 못한다.

## 문제가 생기면

| 증상 | 원인 | 해결 |
|---|---|---|
| 절반쯤 빈 페이지 | 브라우저 인쇄로 직접 뽑음 | `html2pdf.py`를 쓴다 (`Cmd+P`는 배경 그래픽을 켠다) |
| 차트만 빠짐, `Chart is not defined` | Chart.js CDN 차단·오프라인 | 네트워크 확인. 끊겨도 데이터 테이블은 지면에 남는다 |
| 실행 실패 | Playwright도 Chrome도 없음 | 브라우저에서 `Cmd+P`, 또는 `pip install playwright && python3 -m playwright install chromium` |
| 페이지 번호 없음 | 시스템 Chrome으로 변환됨 | Playwright를 설치하면 꼬리말이 붙는다 |
