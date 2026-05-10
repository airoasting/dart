# dart — DART 애널리스트 리포트 스킬

상장사의 DART 공시 재무 데이터를 조회해 인터랙티브 HTML 리포트를 자동 생성하는 Claude Code 스킬.

---

## 폴더 구조

```
~/.claude/skills/dart/
├── SKILL.md                      # 스킬 메인 정의 (동작 순서·HTML 디자인·규칙)
├── README.md                     # 이 파일
│
├── assets/
│   ├── dart_client.py            # DART Open API 클라이언트
│   └── corp_codes_listed.csv     # 상장사 3,963개 corp_code 목록 (오프라인 검색용)
│
├── investor_persona/             # 13인 투자자 철학 파일 (monarchjuno/vibe-investing 원본)
│   ├── peter_lynch.md
│   ├── cathie_wood.md
│   ├── michael_burry.md
│   ├── stanley_druckenmiller.md
│   ├── rakesh_jhunjhunwala.md
│   ├── warren_buffett.md
│   ├── charlie_munger.md
│   ├── philip_fisher.md
│   ├── bill_ackman.md
│   ├── aswath_damodaran.md
│   ├── mohnish_pabrai.md
│   ├── benjamin_graham.md
│   └── nassim_taleb.md
│
└── references/
    └── dart-api.md               # DART API 엔드포인트·보고서 코드 레퍼런스
```

---

## 사용법

```
/dart 카카오
/dart 삼성전자 1Q2026
실적 리포트 만들어줘 — 네이버
```

출력 파일: `output/{종목명}_{YYYYMMDD}_{NN}.html`  
예: `output/카카오_20260510_01.html`

---

## 사전 요건

### 1. DART API 키

[DART Open API](https://opendart.fss.or.kr) 에서 발급 후 프로젝트 루트 `.env`에 추가:

```
DART_API_KEY=your_key_here
```

### 2. Python 패키지

```bash
pip install requests pandas
```

---

## 생성 리포트 구성

| 섹션 | 내용 |
|------|------|
| KPI 카드 | 매출액·영업이익·영업이익률·순이익 (YoY % 배지) |
| 매출 델타 차트 | 전기 대비 증감 waterfall |
| 재무상태표 요약 | 자산/부채/자본 구성 |
| 공시 뉴스 카드 | 최근 공시 목록 (접수일 + 공시명) |
| Bull / Bear | AI 작성 긍정 3개·부정 3개 근거 |
| 투자자 시각 | 13인 투자자 페르소나 평가 (매수·보유·매도) |

디자인: 라이트/다크 테마 토글 (키보드 `T`), Chart.js v4, Pretendard 폰트.

---

## 투자자 페르소나

`investor_persona/` 파일은 [monarchjuno/vibe-investing](https://github.com/monarchjuno/vibe-investing) 레포의 `skills/investor-personas/` 원본을 사용.  
각 파일: Core Principles → Required Analysis Sequence → Decision Rules → Anti-Hallucination Rules 구조.

| 그룹 | 투자자 |
|------|--------|
| 매수 (기본값) | 피터 린치, 캐시 우드, 마이클 버리, 스탠리 드러켄밀러, 라케시 중주왈라 |
| 보유 (기본값) | 워런 버핏, 찰리 멍거, 필립 피셔, 빌 애크먼, 다모다란, 모니시 파브라이 |
| 매도 (기본값) | 벤저민 그레이엄, 나심 탈렙 |

> rating은 고정이 아님. 각 투자자의 Decision Rules를 실제 기업 데이터에 적용해 동적으로 결정됨.

---

## corp_codes_listed.csv 갱신

상장사 코드는 DART에서 주기적으로 업데이트된다. 최신 목록이 필요하면:

```python
from dart_client import DartClient
client = DartClient()
client._build_corp_codes_csv('assets/corp_codes_listed.csv')
```

---

## 면책

생성된 리포트는 공개 공시 데이터 기반 참고 자료입니다. 투자 권유가 아니며, 최종 투자 판단과 손익 책임은 전적으로 투자자 본인에게 있습니다.
