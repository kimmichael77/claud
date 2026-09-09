# 판례 코딩시트 변환기

박사논문 판례분석용 프로그램입니다. **판결문(PDF/DOCX)** 을 넣으면 `코딩시트.xlsx`
(몰카/딥페이크 양형 분석용 43개 항목 템플릿)에 맞춰 자동으로 행을 채워줍니다.

- 날짜 계산, 양형기준 이탈 여부, 상대위치(rel_position) 등 **산술로 결정되는 값**은
  코드가 직접 계산합니다 (LLM이 틀릴 수 있는 부분을 배제).
- case_type, act_type, victim_relationship 등 **판결문 해석이 필요한 값**은
  Claude API가 코딩북 정의를 그대로 참고해서 채웁니다.
- LLM이 채운 모든 행의 `coding_note`에는 `[AI 추출]` 표시가 자동으로 붙습니다.
  **반드시 원문과 대조해서 검수한 뒤 연구에 사용하세요.** 특히 가설 검증용
  변수(`distribution_purpose_established` 등 '가설(파일럿검증)' 상태 항목)는 더 꼼꼼히 확인하세요.

이 프로그램은 순수 Python으로 만들어져 있어 **맥/윈도우 어디서나 동일하게** 동작합니다.
윈도우 사용자는 아래 "윈도우용 더블클릭 실행파일(.exe) 만들기" 섹션을 참고하세요.

## 맥북 설치 (최초 1회)

터미널(Terminal.app)을 열고:

```bash
cd ~/Desktop   # 원하는 위치로 이동 (프로젝트 폴더를 여기 둔다고 가정)
git clone <이 저장소 주소>   # 또는 이미 받은 폴더로 이동
cd claud/case_extractor

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Anthropic API 키가 필요합니다 (https://console.anthropic.com 에서 발급).
터미널에서:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

매번 새 터미널을 열 때마다 다시 설정해야 하는 게 번거로우면, `~/.zshrc`에
위 줄을 추가해두세요.

**API 키가 없거나 만들고 싶지 않다면** 아래 "수동 모드"를 이용하면 API 키 없이
claude.ai 채팅(구독 중인 것)으로 똑같이 진행할 수 있습니다.

## 윈도우용 더블클릭 실행파일(.exe) 만들기

### 방법 A: 윈도우에 Python을 설치할 수 없는 경우 — GitHub에서 자동으로 빌드된 exe 받기

이 저장소는 GitHub Actions로 실제 윈도우 서버에서 exe를 자동으로 빌드하고,
빌드가 끝나면 **Releases**의 `windows-exe-latest`에 자동으로 올리도록 설정되어
있습니다. 여러분의 컴퓨터에는 아무것도 설치할 필요가 없습니다.

1. 저장소 페이지 오른쪽의 **Releases** (또는 `저장소주소/releases/tag/windows-exe-latest`)로 들어갑니다.
2. **Assets** 목록에서 `PanryeCodingConverter.exe`를 클릭하면 바로 다운로드됩니다
   (압축 파일이 아니라 exe 파일 그대로입니다).
3. 다운로드한 `PanryeCodingConverter.exe`를 더블클릭하면 바로 실행됩니다.

`case_extractor/` 코드가 바뀔 때마다 이 릴리스는 자동으로 최신 버전으로 갱신됩니다.
(예전에 쓰던 Actions "Artifacts" 다운로드 버튼은 화면에 잘 보이지 않는 경우가
있어 Releases 방식으로 바꿨습니다.)

### 방법 B: 윈도우 컴퓨터에 Python 설치가 가능한 경우 — 직접 빌드

Python 설치 없이 바로 쓸 수 있는 `.exe` 파일을 직접 만들 수 있습니다
(빌드는 윈도우 컴퓨터에서 딱 한 번만 하면 되고, 이후에는 만들어진 exe 파일만
공유하면 됩니다).

1. 윈도우 컴퓨터에 Python을 설치합니다: https://www.python.org/downloads/windows/
   설치 화면에서 **"Add python.exe to PATH"를 반드시 체크**하세요.
2. 이 저장소를 윈도우 컴퓨터로 내려받습니다 (`git clone` 또는 ZIP 다운로드).
3. `case_extractor` 폴더 안의 **`build_windows_exe.bat`** 파일을 더블클릭합니다.
   (몇 분 정도 걸립니다. 완료되면 `dist\PanryeCodingConverter.exe`가 생성됩니다.)
4. `dist\PanryeCodingConverter.exe` 를 원하는 위치(바탕화면 등)로 옮겨서 더블클릭하면
   바로 프로그램 창이 뜹니다. Python 설치나 터미널 명령이 더 이상 필요 없습니다.
5. 프로그램 창에서 템플릿/판결문 폴더/저장 위치를 선택하고, Anthropic API 키를
   입력한 뒤 "변환 시작"을 누르면 됩니다 (사용법은 아래 GUI 사용법과 동일합니다).

exe 파일 자체에는 API 키가 들어있지 않으니, 실행할 때마다(또는 컴퓨터마다) 화면에서
직접 입력해야 합니다. 여러 사람과 exe만 공유해도 안전합니다.

## 사용법 1: 화면(GUI)으로 실행 — 터미널이 낯설다면 추천

```bash
source .venv/bin/activate
python3 gui.py
```

1. "판결문 입력"에서 **폴더에서 전체 선택** 또는 **파일 개별 선택**(여러 개 동시 선택 가능)으로
   PDF/DOCX 파일을 추가합니다. 두 방식을 섞어서 계속 추가할 수도 있고, "비우기"로 초기화할 수 있습니다.
2. "코딩시트 템플릿"에 원본 코딩시트 xlsx 선택
3. "결과 저장 위치" 확인 (템플릿을 선택하면 자동으로 `_결과.xlsx`로 채워짐)
4. coder_id, API 키 입력 후 "▶ 변환 시작"
5. 처리 중 멈추고 싶으면 "■ 중지"를 누르면 진행 중인 파일까지만 처리하고 멈춥니다
   (이미 처리된 결과는 그대로 저장됩니다).

판결문처럼 보이지 않는 파일(엉뚱한 문서 등)은 자동으로 감지되어 노란색 경고로
표시되고 건너뜁니다: "이 파일은 판결문이 아닌 것 같습니다. 올바른 판결문 파일이
맞는지 다시 확인한 뒤 넣어주세요." 이런 메시지가 뜨면 원본 파일을 다시 확인해보세요.

## 수동 모드 — Anthropic API 키 없이 claude.ai 채팅으로 진행하기

GUI의 **"✂️ 수동 모드 (API 키 없이)"** 탭에서 진행합니다. Anthropic API 키(유료,
종량제) 대신 이미 쓰고 있는 claude.ai 웹 채팅 구독을 그대로 활용하는 방식입니다.
과정이 API 모드보다 손이 더 가지만 추가 비용이 들지 않습니다.

1. **판결문 선택**: 폴더 전체 또는 파일 개별 선택으로 판결문을 고릅니다.
2. **프롬프트 파일 만들기**: 저장할 폴더를 고르고 버튼을 누르면, 판결문마다
   `이름.prompt.txt` 파일이 만들어집니다. 이 안에 코딩북 규칙 + 판결문 전문이 이미
   들어있습니다.
3. **응답 붙여넣어 저장하기**: 만들어진 `.prompt.txt` 파일을 하나씩 열어 **내용
   전체를 복사**해서 claude.ai 채팅창(https://claude.ai)에 붙여넣고 전송합니다.
   받은 답변 전체를 복사한 뒤, GUI의 "응답 붙여넣어 저장하기" 칸에 그대로
   붙여넣고 "저장하고 다음 판결문으로" 버튼을 누르면 **파일명을 직접 맞출 필요 없이**
   자동으로 올바른 이름(`판결문1.json` 등)으로 저장되고, 곧바로 다음 판결문으로
   넘어갑니다. 화면에 몇 개 중 몇 개가 저장됐는지 표시됩니다. 이 과정을 판결문마다
   반복합니다.
4. **응답을 엑셀로 합치기**: 코딩시트 템플릿, 위에서 응답을 저장한 폴더, 결과
   저장 위치를 지정하고 버튼을 누르면 엑셀이 완성됩니다.

(CLI에는 붙여넣기 저장 기능이 없어 파일로 직접 저장해야 합니다. 붙여넣기로 편하게
하려면 GUI를 이용하세요.) CLI로도 동일한 흐름을 할 수 있습니다:

```bash
# 1단계: 프롬프트 생성
python3 -m case_extractor.manual_cli make-prompts \
  --input-dir ~/Desktop/판결문모음 \
  --prompts-dir ~/Desktop/prompts

# (여기서 각 prompts/*.prompt.txt 를 claude.ai에 붙여넣고,
#  응답을 responses/이름.json 으로 저장)

# 2단계: 엑셀로 합치기
python3 -m case_extractor.manual_cli import \
  --template ~/Desktop/코딩시트.xlsx \
  --input-dir ~/Desktop/판결문모음 \
  --responses-dir ~/Desktop/responses \
  --output ~/Desktop/코딩시트_결과.xlsx \
  --coder-id C1
```

수동 모드로 만든 행의 `coding_note`에는 `[AI 추출-수동]` 표시가 붙습니다. API
모드와 마찬가지로 원문과 대조 검수가 필요합니다.

### "엑셀로 합치기"가 안 될 때 (자주 있는 원인)

"엑셀로 합치기"를 눌렀는데 아무 반응이 없거나 실패한다면, 화면 아래 **"진행 상황"**
로그를 먼저 확인하세요. 각 판결문이 왜 건너뛰어졌는지 거기에 표시됩니다. 자주 있는
원인 3가지:

1. **응답 파일 이름 불일치** — `판결문1.pdf`의 응답은 반드시 responses 폴더 안에
   `판결문1.json` 이라는 이름으로 저장되어야 합니다. 확장자나 이름이 조금이라도
   다르면 그 판결문은 조용히 건너뛰어집니다.
2. **claude.ai 답변에 JSON 외의 내용이 섞임** — claude.ai는 채팅 UI라서 "네, JSON을
   만들어드리겠습니다" 같은 설명이나, 성범죄 판결문이라는 민감한 주제 때문에 완곡한
   문구를 답변 앞뒤에 덧붙이는 경우가 있습니다. 프로그램은 답변 안에서 `{`로 시작해
   `}`로 끝나는 부분을 찾아 JSON으로 해석하려고 시도하지만, 이 과정이 실패하면
   건너뜁니다. 가능하면 답변 전체를 그대로 복사해서 저장하세요 (프로그램이 알아서
   JSON 부분만 찾습니다). 만약 claude.ai가 아예 JSON이 아닌 답변만 준다면, 프롬프트
   맨 앞에 "다른 설명 없이 JSON 객체만 출력하세요"라고 다시 한번 요청해보세요.
3. **결과 엑셀 파일이 이미 열려 있음** — 저장하려는 `.xlsx` 파일을 Excel에서 이미
   열어둔 상태면 저장이 막힙니다. 이 경우 오류 팝업이 뜨도록 개선되어 있으니, 뜬다면
   그 파일을 닫고 다시 시도하세요.

이 문제들은 최신 버전(윈도우 exe는 `windows-exe-latest` 릴리스)에서 오류가 나면
반드시 팝업으로 원인을 알려주도록 고쳐졌습니다. 계속 안 되면 로그 내용을 그대로
알려주세요.

## 사용법 2: 터미널(CLI)로 실행 — 여러 배치를 자동화하고 싶다면 추천

폴더 전체를 넣거나:

```bash
source .venv/bin/activate
python3 -m case_extractor.cli \
  --template ~/Desktop/코딩시트.xlsx \
  --input-dir ~/Desktop/판결문모음 \
  --output ~/Desktop/코딩시트_결과.xlsx \
  --coder-id C1
```

또는 파일을 하나씩 지정할 수도 있습니다 (`--input-dir` 대신 `--input-files`):

```bash
python3 -m case_extractor.cli \
  --template ~/Desktop/코딩시트.xlsx \
  --input-files ~/Desktop/판결문1.pdf ~/Desktop/판결문2.docx \
  --output ~/Desktop/코딩시트_결과.xlsx \
  --coder-id C1
```

옵션:
- `--id-prefix DF-2024-` : case_id 자동 채번 접두어 (기본값 `DF-2024-`)
- `--model claude-...` : 사용할 Claude 모델 지정 (기본값은 환경변수 `ANTHROPIC_MODEL`,
  없으면 `claude-sonnet-5`). API 호출 시 모델을 찾을 수 없다는 오류가 나면
  https://docs.anthropic.com/en/docs/about-claude/models 에서 현재 사용 가능한
  모델 ID를 확인해 이 옵션으로 지정하세요.
- `--dry-run` : 엑셀에 쓰지 않고 추출 결과만 화면에 출력 (테스트용)
- `--skip-judgment-check` : 판결문 여부 사전 검사를 건너뜁니다 (기본적으로는 판결문처럼
  보이지 않는 파일을 자동으로 걸러내고 안내 메시지를 띄웁니다. 권장하지 않지만 필요하면 사용하세요)

CLI는 Ctrl+C로 언제든 중지할 수 있습니다 (이미 처리된 결과는 저장되지 않으니, 중간에
저장하고 싶다면 GUI의 "중지" 버튼을 이용하세요).

## 파일 형식 관련 주의사항

- `.pdf`: 텍스트 레이어가 있는(복사·붙여넣기가 되는) 판결문이어야 합니다.
  스캔 이미지 PDF는 OCR이 필요합니다 (`ocrmypdf` 등으로 먼저 텍스트 레이어를 입히세요).
- `.docx`: 지원. 옛 `.doc`는 한글/워드에서 `.docx`로 다른 이름으로 저장 후 사용하세요.

## 코딩북/항목 수정하기

`case_extractor/coding_book.py` 파일에 43개 변수의 정의·코딩규칙이 그대로 들어 있습니다.
코딩북 내용이 바뀌면 이 파일도 함께 고쳐야 LLM 추출 결과가 최신 정의를 따릅니다.
자동 계산되는 4개 항목(`duration`, `appeal_duration`, `guideline_rel_position`,
`area_rel_position`)과 이탈 관련 2개 항목(`guideline_deviation`, `deviation_direction`)의
계산식은 `case_extractor/compute.py`에 있습니다. 판결문 여부를 판단하는 표지 문구
목록은 `case_extractor/validate.py`의 `JUDGMENT_MARKERS`에 있습니다.

## 정확도에 대한 당부

이 프로그램은 판결문을 "읽고 해석"해서 항목을 채우는 만큼, 특히 다음 항목들은
AI가 틀리기 쉬우니 전수 검수를 권장합니다:
- 양형기준 권고형 범위(`guideline_min/max_months`), 형량영역(`area_min/max_months`) — 판결문의
  "[권고영역 및 권고형의 범위]" 문구를 정확히 옮겨야 함
- 특별양형인자 개수(`aggravating_factors`, `mitigating_factors`)
- 가설 검증용 항목 6개 (`distribution_purpose_established` 등)
