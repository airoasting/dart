# dart — 종목 하나로 애널리스트급 실적 리포트

> 상장사 이름만 넣으면, 금융감독원 공시 데이터로 만든 인터랙티브 실적 리포트가 몇 분 만에 나옵니다.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**바로 보기** → [카카오 1Q2026 리포트](https://airoasting.github.io/dart/%EC%B9%B4%EC%B9%B4%EC%98%A4_20260704.html)  ·  [SK하이닉스 (큰 숫자 사례)](https://airoasting.github.io/dart/SK%ED%95%98%EC%9D%B4%EB%8B%89%EC%8A%A4_20260704.html)

---

## 누가 쓰면 좋은가

- 종목의 실적을 **빠르게, 한눈에** 파악하고 싶은 경영자·투자자
- 증권사 리포트를 기다리기 전에 **내 손으로** 먼저 훑어보고 싶은 분
- 코딩을 몰라도 됩니다. 한 줄이면 리포트가 만들어집니다.

## 무엇을 만들어 주나

`/dart 카카오` — 이 한 줄이면 아래 6개 섹션이 담긴 인터랙티브 HTML 리포트가 만들어집니다. 라이트·다크 테마와 차트가 기본 포함됩니다.

| 섹션 | 무엇을 보여주나 |
|------|------|
| **핵심 실적** | 매출 · 영업이익 · 순이익, 전년 동기 대비 |
| **성장 기여도** | 무엇이 실적을 끌어올렸나 (워터폴 차트) |
| **사업별 매출** | 부문별 비교 + 클릭 드릴다운 |
| **애널리스트 시각** | 증권사 목표주가 · 컨센서스 · 강세/약세 근거 |
| **관련 뉴스** | 최신 국내 기사 (긍정·부정·혼재 분류) |
| **투자자 시각** | 13인 전설적 투자자가 이 종목을 본다면 (가상 평가) |

## 믿을 수 있나 — 데이터 출처

- **재무** — 금융감독원 **DART 전자공시**의 공식 재무제표 (전년 동기 비교)
- **주가** — 한국거래소(KRX) **전일 종가** (추측 없이 실제 종가·52주 범위)
- **뉴스·애널리스트** — 실제 기사·증권사 리포트에서 **확인된 것만**
- 추정치가 섞인 값은 화면에 **명확히 표시**하고, 투자자 시각은 AI 시뮬레이션임을 밝힙니다

## 예시로 보기 — 카카오 1Q2026

> 영업이익이 1년 만에 2배로 뛴 수익성 개선 분기입니다. 🔗 [리포트 전체 열어보기](https://airoasting.github.io/dart/%EC%B9%B4%EC%B9%B4%EC%98%A4_20260704.html)

| 지표 | 2025 1Q | 2026 1Q | 전년 대비 |
|------|---------|---------|-----|
| 매출 | 18,637억 | **19,421억** | +4.2% |
| 영업이익 | 1,054억 (이익률 5.7%) | **2,114억 (10.9%)** | +100.6% |
| 당기순이익 | 2,003억 | **2,268억** | +13.2% |

### 대시보드 헤더
![대시보드 헤더](assets/screenshots/01_hero.png)

### 핵심 실적 (KPI)
![KPI 카드](assets/screenshots/02_kpi.png)

### 성장 기여도
![성장 기여도 워터폴 차트](assets/screenshots/03_growth.png)

### 사업별 매출
![사업별 매출 세그먼트 차트](assets/screenshots/04_segment.png)

### 애널리스트 시각
![컨센서스 · 강세/약세](assets/screenshots/06_market.png)

### 관련 뉴스
![국내 기사 카드](assets/screenshots/07_news.png)

### 투자자 시각
![13인 투자자 페르소나](assets/screenshots/08_persona.png)

> 아주 큰 숫자도 잘 다룹니다 — [SK하이닉스 1Q2026 리포트](https://airoasting.github.io/dart/SK%ED%95%98%EC%9D%B4%EB%8B%89%EC%8A%A4_20260704.html)(분기 매출 52조·영업이익률 71.5%)에서도 차트가 데이터에 맞춰 자동으로 조정됩니다.

---

## 쓰는 법 (설치는 한 번만)

1. **스킬 설치** — 터미널에 아래 한 줄:
   ```bash
   git clone https://github.com/airoasting/dart ~/.claude/skills/dart
   ```
2. **DART API 키 발급** — [opendart.fss.or.kr](https://opendart.fss.or.kr)에서 무료로 받아 프로젝트 `.env`에 추가:
   ```env
   DART_API_KEY=발급받은_키
   ```
3. **필요한 패키지** — `pip install requests pandas`

이후 Claude Code에서 이렇게 부르면 됩니다:

```
/dart 카카오
/dart SK하이닉스 1Q2026
실적 리포트 만들어줘 — 네이버
```

리포트는 `output/` 폴더에 `종목명_날짜_번호.html`로 저장됩니다.

---

## 작동 방식 (기술 참고)

HTML을 매번 통째로 만들지 않습니다. 보일러플레이트(디자인·차트·레이아웃)는 `assets/template.html`에 고정돼 있고, 스킬은 **데이터만 만들어** `assets/build_report.py`로 결합합니다. 그래서 빠르고, 디자인이 매번 일정하며, 차트 축은 데이터에 맞춰 자동 조정됩니다. 뉴스·애널리스트·페르소나 같은 무거운 조사는 여러 작업을 병렬로 돌려 시간을 줄입니다.

<details>
<summary>파일 구조 펼치기</summary>

```
~/.claude/skills/dart/
├── SKILL.md                    # 스킬 워크플로우
├── assets/
│   ├── template.html           # 고정 템플릿 (디자인·차트)
│   ├── build_report.py         # 데이터 + 템플릿 → 리포트
│   ├── data.example.json       # 데이터 형식(스키마) + 카카오 예시
│   ├── price.py                # 전일 종가·52주 (KRX)
│   ├── dart_client.py          # DART API 클라이언트
│   └── corp_codes_listed.csv   # 상장사 코드 (오프라인 검색)
├── investor_persona/           # 13인 투자자 철학 파일 (_ALL.md 통합본)
└── references/                 # 설계 문서 (런타임 미사용)
```
</details>

## 투자자 페르소나

`investor_persona/`에 13인의 투자자 철학 파일이 있습니다. 각 파일은 **Overview → Core Principles → Required Analysis Sequence → Decision Rules → Risk and Uncertainty Rules → Anti-Hallucination Rules** 구조로, 그 투자자의 원칙·판단 절차와 지어내지 않기 위한 규칙을 담습니다. 스킬은 이 13개를 합친 통합본 `investor_persona/_ALL.md` 한 파일을 읽어 적용합니다.

매수·보유·매도 판단은 고정이 아닙니다. 각 투자자의 판단 규칙을 실제 기업 데이터에 적용해 매번 새로 결정됩니다.

피터 린치 · 캐시 우드 · 마이클 버리 · 스탠리 드러켄밀러 · 라케시 준준왈라 · 워런 버핏 · 찰리 멍거 · 필립 피셔 · 빌 애크먼 · 애스워스 다모다란 · 모니시 파브라이 · 벤저민 그레이엄 · 나심 탈렙

---

## 라이선스

[MIT](LICENSE) © airoasting

## 면책 고지

이 스킬이 생성하는 리포트는 공개 공시 데이터를 기반으로 한 참고 자료입니다. 투자 권유가 아니며, 최종 투자 판단과 그에 따른 손익 책임은 전적으로 투자자 본인에게 있습니다. 「투자자 시각」 섹션은 각 인물의 공개된 철학을 AI가 시뮬레이션한 가상 평가이며, 실제 의견이 아닙니다.
