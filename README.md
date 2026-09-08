# claud — 판결문(판례) 자동검색 CLI

국가법령정보센터(law.go.kr) Open API를 이용해 판례를 검색/조회하는 파이썬 CLI 도구입니다.

## 1. 사전 준비: OC 발급받기

1. https://open.law.go.kr 접속 후 회원가입
2. "오픈API 신청" 메뉴에서 API 이용 신청 (승인까지 다소 시간이 걸릴 수 있습니다)
3. 승인 후 마이페이지 > "API인증키관리"에서 실제 OC 값을 확인합니다 (가입 이메일과 다를 수 있음)

## 2-0. Windows에서 더블클릭으로 바로 실행하기 (가장 쉬운 방법)

law.go.kr은 한국 정부 사이트라 **해외 클라우드 서버(Colab, Codespaces 등)에서는 접속이 차단**됩니다.
반드시 한국 인터넷을 쓰는 본인 PC에서 실행해야 합니다.

1. Python이 없다면 https://www.python.org/downloads/ 에서 설치 (설치 시 **"Add python.exe to PATH" 체크 필수**)
2. 이 저장소를 ZIP으로 다운로드해서 압축 풀기
   (GitHub 페이지 → 초록색 "Code" 버튼 → "Download ZIP")
3. 압축 푼 폴더 안의 **`run_compare.bat`** 파일을 더블클릭
4. 검은 창이 뜨면 OC 값을 입력하고 Enter
5. 결과가 `compare_results` 폴더에 저장됩니다 (창은 자동으로 닫히지 않고 대기합니다)

## 2-0-b. Mac에서 더블클릭으로 바로 실행하기

1. Python이 없다면 터미널(Spotlight에서 "터미널" 검색)에서 `python3 --version`으로 확인.
   없으면 https://www.python.org/downloads/ 에서 설치하거나 `brew install python3`
2. 이 저장소를 ZIP으로 다운로드해서 압축 풀기
   (GitHub 페이지 → 초록색 "Code" 버튼 → "Download ZIP")
3. 압축 푼 폴더 안의 **`run_compare.command`** 파일을 더블클릭
4. macOS가 "확인되지 않은 개발자" 경고를 띄우면:
   - 파일을 **마우스 오른쪽 클릭(또는 control+클릭) → "열기"** 선택 → 다시 뜨는 창에서 "열기" 클릭
     (한 번만 이렇게 열면 다음부터는 그냥 더블클릭 가능)
5. 터미널 창이 뜨면 OC 값을 입력하고 Enter
6. 결과가 `compare_results` 폴더에 저장됩니다

## 2. 설치 (수동으로 명령어를 입력하고 싶은 경우)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

OC 값은 환경변수로 등록하거나 매 명령마다 `--oc` 옵션으로 넘길 수 있습니다.

```bash
cp .env.example .env   # 편집해서 LAW_GO_KR_OC 값 채우기
export $(grep -v '^#' .env | xargs)
```

### GitHub Codespaces에서 실행하기

터미널 설치 없이 브라우저에서 실행하고 싶다면 Codespaces를 쓸 수 있습니다.

1. GitHub 저장소 페이지에서 이 브랜치(`claude/judgment-auto-search-feasibility-yx9swi`)로 이동
2. 초록색 "Code" 버튼 → "Codespaces" 탭 → "Create codespace on ..." 클릭
3. 몇 분 기다리면 브라우저 안에 VS Code 화면이 뜨고, 하단 터미널에 `pip install -r requirements.txt`가 자동 실행되어 있습니다
4. 터미널에 다음을 입력해 실행:
   ```bash
   export LAW_GO_KR_OC=발급받은OC값
   python -m judgment_search compare
   ```

> **주의:** law.go.kr은 한국 정부(.go.kr) 사이트라 해외 서버에서 접속 시 DNS 조회 자체가
> 차단될 수 있습니다. Codespaces는 보통 해외 리전에서 실행되므로 동일한 문제가 발생할 수
> 있습니다. 이 경우 한국 내 네트워크(가정/회사 인터넷)를 쓰는 PC에서 직접 실행해야 합니다.

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

### 두 조문(죄명)을 구분해서 검색: compare

성폭력범죄의 처벌 등에 관한 특례법 **제14조(카메라 등을 이용한 촬영)**와
**제14조의2(허위영상물 등의 반포등)**처럼, 죄명은 다르지만 관련 키워드가 겹치는
두 조문을 구분해서 판례를 모을 때 사용합니다. 본문 검색 대신 **사건명(죄명) 검색**을
기본값으로 사용해 정확히 분리합니다.

```bash
# 옵션 없이 실행하면 기본값으로 제14조 vs 제14조의2를 비교합니다
python3 -m judgment_search compare
```

결과는 `compare_results/` 폴더에 그룹별 json 파일로 저장되고, 두 그룹에 동시에 걸린
판례(하나의 판결문에서 두 죄가 함께 기소된 경우)가 있으면 화면에 경고로 표시됩니다.

검색어/이름표를 직접 지정하거나 결과 저장 위치를 바꾸려면:

```bash
python3 -m judgment_search compare \
  --query1 "카메라등이용촬영" --label1 "제14조" \
  --query2 "허위영상물"     --label2 "제14조의2" \
  --max-results 300 --out-dir results/spcsa14
```

> **주의:** 국가법령정보센터의 사건명 표기(예: "카메라등이용촬영·반포등",
> "허위영상물편집·반포등")는 개정 시기나 법원에 따라 다를 수 있습니다.
> 처음 실행 후 건수가 0건이거나 예상보다 적게 나오면 `--query1`/`--query2`를
> 조정하거나 `--scope fulltext`(본문 검색)로 바꿔 재시도해 보세요.

### 판례를 PDF로 개별 다운로드하기

law.go.kr Open API는 PDF를 직접 주지 않고 텍스트(JSON)만 제공합니다. 이 도구는
받은 텍스트(사건명/판시사항/판결요지/전문)를 판례 1건당 PDF 파일 1개로 직접 만들어줍니다.

`compare`에 `--pdf`를 추가하면 두 그룹 각각의 판례를 `<out-dir>/<이름표>_pdf/` 폴더에
개별 PDF로 저장합니다 (검색 결과 건수만큼 상세 조회를 추가로 하므로 시간이 더 걸립니다):

```bash
python3 -m judgment_search compare --pdf
```

`search`나 `detail` 명령에도 사용할 수 있습니다:

```bash
python3 -m judgment_search search "부당해고" --pdf-dir pdfs/
python3 -m judgment_search detail 228541 --pdf 228541.pdf
```

PDF에 한글을 표시하려면 시스템에 한글 폰트가 있어야 하며, 이 도구는 Windows(맑은 고딕),
Mac(AppleGothic) 등 OS 기본 한글 폰트를 자동으로 찾아 사용합니다. 자동으로 못 찾으면
`--font "폰트파일경로.ttf"` 옵션으로 직접 지정하세요.

## 4. 테스트

```bash
python3 -m unittest discover -s tests -v
```

네트워크 호출 없이 mock으로 동작하므로 OC 값이 없어도 실행됩니다.

## 5. 참고 / 한계

- 국가법령정보센터는 대표적인 주요 판례 위주로 수록되어 있어, 대법원 종합법률정보(glaw.scourt.go.kr)보다 커버리지가 좁을 수 있습니다.
- Open API 상세 파라미터(법원 종류 코드, 선고일자 범위 등)는 law.go.kr에서 배포하는 최신 "오픈API 활용가이드" 문서를 기준으로 필요 시 `judgment_search/client.py`에 추가하면 됩니다.
- API 호출 빈도 제한이 있을 수 있으니, 대량 수집 시 요청 간 지연(sleep)을 두는 것을 권장합니다.
