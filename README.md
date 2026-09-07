# claud — 판결문(판례) 자동검색 CLI

국가법령정보센터(law.go.kr) Open API를 이용해 판례를 검색/조회하는 파이썬 CLI 도구입니다.

## 1. 사전 준비: OC 발급받기

1. https://open.law.go.kr 접속 후 회원가입
2. "오픈API 신청" 메뉴에서 API 이용 신청 (승인까지 다소 시간이 걸릴 수 있습니다)
3. 승인 후 발급되는 값은 가입 시 사용한 **이메일의 `@` 앞부분**입니다. 예: `abc@gmail.com` → `OC=abc`

## 2. 설치

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

OC 값은 환경변수로 등록하거나 매 명령마다 `--oc` 옵션으로 넘길 수 있습니다.

```bash
cp .env.example .env   # 편집해서 LAW_GO_KR_OC 값 채우기
export $(grep -v '^#' .env | xargs)
```

## 3. 사용법

### 키워드로 검색

```bash
python3 -m judgment_search search "임대차 계약 해지" --display 20 --page 1
```

특정 법원으로 필터링:

```bash
python3 -m judgment_search search "부당해고" --court 대법원
```

결과를 파일로 저장 (`.json` 또는 `.csv`):

```bash
python3 -m judgment_search search "부당해고" --display 100 --out results.json
```

### 판례 전문 조회

검색 결과에 표시되는 `[판례일련번호]`를 이용해 상세(판시사항/판결요지/전문)를 조회합니다.

```bash
python3 -m judgment_search detail 228541
python3 -m judgment_search detail 228541 --out 228541.json
```

## 4. 테스트

```bash
python3 -m unittest discover -s tests -v
```

네트워크 호출 없이 mock으로 동작하므로 OC 값이 없어도 실행됩니다.

## 5. 참고 / 한계

- 국가법령정보센터는 대표적인 주요 판례 위주로 수록되어 있어, 대법원 종합법률정보(glaw.scourt.go.kr)보다 커버리지가 좁을 수 있습니다.
- Open API 상세 파라미터(법원 종류 코드, 선고일자 범위 등)는 law.go.kr에서 배포하는 최신 "오픈API 활용가이드" 문서를 기준으로 필요 시 `judgment_search/client.py`에 추가하면 됩니다.
- API 호출 빈도 제한이 있을 수 있으니, 대량 수집 시 요청 간 지연(sleep)을 두는 것을 권장합니다.
