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

---

## dart_client.py 사용법

```python
import sys
sys.path.insert(0, str(Path('~/.claude/skills/dart-dashboard/assets').expanduser()))
from dart_client import DartClient

client = DartClient()  # .env 또는 DART_API_KEY 자동 로드

# 회사 코드 검색
df = client.find_corp('카카오', listed_only=True)
corp_code = df.iloc[0]['corp_code']  # '00401731'

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
| 020    | 요청 제한 초과 |
| 100    | 필드 오류 |
| 800    | 시스템 점검 중 |
