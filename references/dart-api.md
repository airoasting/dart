# DART Open API 레퍼런스

베이스 URL: `https://opendart.fss.or.kr/api`  
인증: 모든 요청에 `crtfc_key` 파라미터 추가 (`.env` 또는 `DART_API_KEY` 환경변수)

---

## 주요 엔드포인트

### 1. 공시검색 `GET /list.json`
```
corp_code   기업고유번호 (8자리)
bgn_de      시작일 YYYYMMDD
end_de      종료일 YYYYMMDD
pblntf_ty   공시유형: A=정기공시, B=주요사항, C=발행공시, ...
page_no     페이지 번호 (기본 1)
page_count  페이지당 건수 (기본 10, 최대 100)
```

### 2. 기업개황 `GET /company.json`
```
corp_code   기업고유번호 (8자리, 필수)
```
이름으로는 검색되지 않는다. 이름 → corp_code는 `corp_registry.py`(아래)로 한다.
반환: corp_name, ceo_nm, corp_cls(Y=유가, K=코스닥), jurir_no, bizr_no, adres, hm_url, ir_url, phn_no, fax_no, industry_code, est_dt, acc_mt

### 3. 재무제표 (단일회사 전체 재무제표) `GET /fnlttSinglAcntAll.json`
```
corp_code   기업고유번호 (필수)
bsns_year   사업연도 (YYYY, 필수)
reprt_code  보고서 코드 (필수)
            11013 = 1분기보고서
            11012 = 반기보고서
            11014 = 3분기보고서
            11011 = 사업보고서(연간)
fs_div      재무제표 구분: OFS=개별, CFS=연결 (기본 OFS)
```
반환: list[] → {rcept_no, reprt_nm, bsns_year, corp_code, sj_div(BS/IS/CIS/CF/SCE), sj_nm, account_id, account_nm, account_detail, thstrm_nm, thstrm_amount, frmtrm_nm, frmtrm_amount, ...}

주요 account_nm 예시:
- 매출액, 영업이익, 당기순이익, 기타포괄손익합계, 자산총계, 부채총계, 자본총계, 현금및현금성자산

### 4. 주요재무정보 `GET /fnlttSinglAcnt.json`
3번과 동일 파라미터. 핵심 계정만 반환 (빠르게 조회 시 사용).

### 5. 배당 정보 `GET /alotMatter.json`
```
corp_code   기업고유번호 (필수)
bsns_year   사업연도 (필수)
reprt_code  보고서 코드 (필수)
```

### 6. 주식 현황 `GET /stockTotqySttus.json`
주식의 종류별 발행 현황
```
corp_code, bsns_year, reprt_code
```

### 7. 고유번호 `GET /corpCode.xml`
전체 기업(비상장 포함 약 12만 개)의 corp_code·회사명·영문명·종목코드 zip.
**주의: 상장폐지 뒤에도 stock_code가 남는다.** stock_code가 있다고 상장사가 아니다(약 1,200개가 폐지·이전 종목).
그래서 레지스트리는 KRX KIND 상장법인목록(`kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13`, EUC-KR HTML 표)과 stock_code로 교차해 현재 상장사만 남긴다.
KIND 원본에는 같은 종목이 두 번 실린 행이 있고(2026-10 기준 43행), 신규 종목코드에는 영문이 섞인다(`0035S0`).

### 8. MCP 서버만 쓰는 엔드포인트

리포트 파이프라인은 쓰지 않고 `assets/mcp_server.py`만 부른다. 2026-10-08 카카오로 실측했다.

| 엔드포인트 | MCP 도구 | 인자 | 비고 |
|---|---|---|---|
| `fnlttSinglIndx.json` | `fin_ratios` | 정기 + `idx_cl_code` (M210000 수익성, M220000 안정성, M230000 성장성, M240000 활동성) | 2023년 3분기 보고서부터 있다. 2023 1Q·2022 연간은 013. 값이 없으면 `idx_val` 키 자체가 빠지고, 자릿수가 넘치면 `#########`이 온다 |
| `hyslrSttus.json` | `share_top_holders` | 정기 | 최대주주와 특수관계인. 카카오는 99행 |
| `majorstock.json` | `share_block_reports` | `corp_code`만 | 5% 대량보유 보고 전체 이력. 정렬이 보장되지 않아 서버가 접수일 내림차순으로 정렬한다 |
| `elestock.json` | `share_insider_reports` | `corp_code`만 | 임원·주요주주 소유 보고 전체 이력 (카카오 117행). 정렬은 위와 같다 |
| `tesstkAcqsDspsSttus.json` | `share_treasury` | 정기 | 자기주식 취득 방법별 기초·취득·처분·소각·기말 |
| `irdsSttus.json` | `share_capital_changes` | 정기 | 증자·감자 이력 |
| `exctvSttus.json` | `people_executives` | 정기 | 임원 |
| `empSttus.json` | `people_employees` | 정기 | 직원 수, 평균 근속, 1인 평균 급여 |

`fnlttSinglIndx.json` 값은 연결재무제표가 있으면 연결, 없으면 별도 계정으로 계산돼 있다(2025 연간 부채비율 실측: 카카오 82.487 = 연결, 삼성전자 29.937 = 연결, 경남스틸 39.662 = 별도). 응답에 접수번호가 없어서 `fin_ratios`는 공시 목록에서 그 기간 보고서(정정본 우선)를 찾아 링크를 붙이고, 주요계정 한 번으로 기준을 가려 `meta.basis`에 적는다. `exctvSttus.json`은 회사마다 미등기임원을 싣는 정도가 다르다(삼성전자 2026 반기는 등기 8명만, 경남스틸 2025는 미등기 8명 포함).

"정기"는 `corp_code, bsns_year, reprt_code`다. `fnlttSinglAcnt.json`은 `fs_div`를 줘도 연결·별도 행을 함께 돌려주므로 서버가 응답의 `fs_div`로 고른다. 소형사 중에는 손익계산서 없이 포괄손익계산서(`CIS`) 한 장만 공시하는 곳이 있다(경남스틸 2025 사업보고서).

---

## dart_client.py 사용법

```python
import sys
sys.path.insert(0, str(Path('~/.claude/skills/dart/assets').expanduser()))
from dart_client import DartClient

client = DartClient()  # .env 또는 DART_API_KEY 자동 로드

# 회사 찾기: 정식명·약칭·옛 이름·영문명·종목코드·우선주 모두 받는다
res = client.resolve_corp('현대차', verify=True)
# res['status']: ok | confirm | ambiguous | not_found   (CLI: corp_registry.py 현대차 --verify)
corp_code = res['corp']['corp_code']  # '00164742' (현대자동차, 005380)

# 비12월 결산 법인: 최근 정기보고서 → 재무 API 파라미터
rep = client.latest_periodic_report(corp_code, fiscal_month=res['corp']['fiscal_month'])
# {'bsns_year': '2026', 'reprt_code': '11013', 'period_end': '2026.06', ...}

# 기업 개황
info = client.company(corp_code)

# 재무제표 (연결 기준, 최근 사업연도)
fin = client.get_financial_statements(corp_code, bsns_year='2025', reprt_code='11011', fs_div='CFS')
```

---

## 보고서 코드 빠른 참조

| 코드  | 보고서명       | 대상 기간 |
|-------|---------------|----------|
| 11013 | 1분기보고서    | 1Q       |
| 11012 | 반기보고서     | 2Q (상반기) |
| 11014 | 3분기보고서    | 3Q       |
| 11011 | 사업보고서     | 연간     |

---

## 응답 status 코드

| status | 의미 |
|--------|------|
| 000    | 정상 |
| 010    | 미등록 API 키 |
| 011    | 사용 불가 API 키 |
| 013    | 조회 결과 없음 |
| 020    | 요청 제한 초과 (일 2만 건). `DartClient`가 두 번 더 시도한다 |
| 100    | 필드 오류 |
| 800    | 시스템 점검 중. `DartClient`가 두 번 더 시도한다 |
| 900    | 정의되지 않은 오류 |
| 901    | 개인정보 보유기간이 지난 키. 키를 다시 발급받는다 |

`company.json`의 `corp_cls`: Y 코스피 · K 코스닥 · N 코넥스 · E 기타(비상장·폐지). 검증 게이트는 Y·K·N만 통과시킨다.

재시도 뒤에도 네트워크 오류면 `DartError`(ConnectionError)를 낸다. 메시지의 `crtfc_key`는 `***`로 가린다.

## 결산월이 12월이 아닌 법인

`bsns_year`는 보고서 기준월 `(YYYY.MM)`의 연도다(3월 결산 신영증권으로 실측).

| 보고서명 | bsns_year | reprt_code |
|---|---|---|
| 사업보고서 (2026.03) | 2026 | 11011 |
| 분기보고서 (2026.06) | 2026 | 11013 |
| 반기보고서 (2025.09) | 2025 | 11012 |
| 분기보고서 (2025.12) | 2025 | 11014 |

`reprt_code`는 보고서 종류로 정한다(사업→11011, 반기→11012). 분기보고서는 결산월로부터 3개월 뒤면 11013, 9개월 뒤면 11014.
6개월 결산(리츠)은 사업보고서를 1년에 두 번 낸다. 4Q 역산에 쓰는 3Q 보고서의 bsns_year는 결산월 − 3이 0 이하이면 전년이다(3월 결산 FY 2026.03 → 3Q는 2025.12, bsns_year 2025).
