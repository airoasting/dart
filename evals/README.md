# 평가 (빠른 조회)

dart 스킬의 빠른 조회 경로를 skill-creator 절차로 재는 자산이다. 같은 질문을 새 버전과 비교 버전에 돌리고, 답을 기계적으로 채점해 통과율·시간·토큰을 비교한다. 리포트 경로의 품질은 숫자 검증 게이트(`assets/verify_report.py`)와 `tests/`가 맡는다.

## 파일

| 파일 | 하는 일 |
|---|---|
| `evals.json` | 질문 3개와 채점 기준 18개. 정답값은 2026-10-08 DART 실측 |
| `grade.py` | `answer.md`·`notes.md`를 읽어 기준마다 통과·근거를 `grading.json`에 쓴다 |
| `bench.sh` | 채점 → skill-creator `aggregate_benchmark` → 새 버전을 앞에 둔 `benchmark.json`·`.md` |
| `trigger_queries.json` | 발동해야 할 질문 8개, 발동하면 안 되는 질문 6개와 마지막 점검 결과 |

## 다시 돌리는 법

1. 비교 버전을 스킬 폴더 **밖에** 둔다(안에 두면 SKILL.md가 중첩 스킬로 읽힌다). 예: `git archive <커밋> | tar -x -C <scratch>/old`, `.env`도 복사.
2. 질문마다 두 실행을 한 번에 띄운다. 프롬프트는 "Skill path: <경로>, Task: <질문>, outputs/에 answer.md와 notes.md(실행한 명령·직접 쓴 코드)". 결과는 `output/skill-eval/iteration-N/eval-<id>-<name>/<with_skill|old_skill>/run-1/outputs/`.
3. 실행이 끝날 때마다 알림의 토큰·시간을 `run-1/timing.json`에 적는다(`total_tokens`, `duration_ms`, `total_duration_seconds`).
4. `sh evals/bench.sh output/skill-eval/iteration-N "<skill-creator 경로>"`
5. 뷰어: `python3 <skill-creator>/eval-viewer/generate_review.py <iteration> --skill-name dart --benchmark <iteration>/benchmark.json --static <html>` (2회차부터 `--previous-workspace`).

새 정기보고서가 나오면 "최근 보고서" 기준 정답이 바뀐다. `evals.json`의 기대값과 `grade.py`의 정답 패턴을 함께 고친다.

## 마지막 결과 (2026-10-08)

| | 옛 버전(2.1.0) | 1회차 | 2회차(2.2.0) |
|---|---|---|---|
| 18항목 통과 | 83% | 89% | **100%** |
| 평균 시간 | 87초 | 90초 | **45초** |
| 평균 토큰 | 9.7만 | 10.0만 | **9.4만** |
| API 코드 직접 작성 | 3/3 | 1/3 | **0/3** |

발동 점검은 대리 방식으로 했다(서브에이전트가 스킬 목록만 보고 질문마다 고름). 14/14 일치. `claude -p` 실측(`run_eval`)은 설치된 dart와 같은 설명이 겹쳐 결과가 오염되므로 쓰지 않았다.

## 10점 채점표

skill-creator 기준(발동, 절차, 산출물, 효율, 도구, 재현)에 이 폴더의 9.5·10점 구분을 더했다.

| 축 | 개선 전 | 개선 후 | 근거 |
|---|:---:|:---:|---|
| 발동 | 6 | 9.5 | 조회 표현을 description에 넣고 YAML 오류를 고쳤다. 대리 점검 14/14. 실제 발동률은 재지 못했다 |
| 절차 | 5 | 10 | 2회차 3/3이 SKILL.md만 읽고 도구로 갔다(1회차는 README를 뒤졌다) |
| 산출물 | 9 | 10 | 18/18. 기준일·연결/별도·원문 링크를 모두 밝혔다 |
| 효율 | 7 | 10 | 45초, 옛 버전의 절반 |
| 도구 견고성 | 6 | 10 | requests 없는 파이썬, 큰 응답, 연결 없는 소형사, IS 없는 회사, 합계 행, 날짜 형식을 실측으로 처리. 실제 MCP 클라이언트(Claude Code)가 접속해 16개를 인식 |
| 재현·검증 | 8 | 10 | 테스트 150개(MCP 26개는 requests 없는 3.14에서도 통과), quick_validate·`claude plugin validate --strict` 통과, 이 평가 자산 |
| **종합** | **6.8** | **9.8** | |

10점에 남은 것: 로그인이 살아 있는 `claude -p`로 질문 → 도구 호출 → 답까지 한 번, 그리고 실제 발동률 측정. 둘 다 결함이 아니라 아직 재지 못한 항목이다.
