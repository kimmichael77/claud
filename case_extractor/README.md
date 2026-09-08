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

## 윈도우용 더블클릭 실행파일(.exe) 만들기

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

1. "코딩시트 템플릿" 에 원본 코딩시트 xlsx 선택
2. "판결문 폴더" 에 PDF/DOCX 파일들이 모여 있는 폴더 선택
3. "결과 저장 위치" 확인 (자동으로 `_결과.xlsx`로 채워짐)
4. coder_id, API 키 입력 후 "변환 시작"

## 사용법 2: 터미널(CLI)로 실행 — 여러 배치를 자동화하고 싶다면 추천

```bash
source .venv/bin/activate
python3 -m case_extractor.cli \
  --template ~/Desktop/코딩시트.xlsx \
  --input-dir ~/Desktop/판결문모음 \
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

## 파일 형식 관련 주의사항

- `.pdf`: 텍스트 레이어가 있는(복사·붙여넣기가 되는) 판결문이어야 합니다.
  스캔 이미지 PDF는 OCR이 필요합니다 (`ocrmypdf` 등으로 먼저 텍스트 레이어를 입히세요).
- `.docx`: 지원. 옛 `.doc`는 한글/워드에서 `.docx`로 다른 이름으로 저장 후 사용하세요.

## 코딩북/항목 수정하기

`case_extractor/coding_book.py` 파일에 43개 변수의 정의·코딩규칙이 그대로 들어 있습니다.
코딩북 내용이 바뀌면 이 파일도 함께 고쳐야 LLM 추출 결과가 최신 정의를 따릅니다.
자동 계산되는 4개 항목(`duration`, `appeal_duration`, `guideline_rel_position`,
`area_rel_position`)과 이탈 관련 2개 항목(`guideline_deviation`, `deviation_direction`)의
계산식은 `case_extractor/compute.py`에 있습니다.

## 정확도에 대한 당부

이 프로그램은 판결문을 "읽고 해석"해서 항목을 채우는 만큼, 특히 다음 항목들은
AI가 틀리기 쉬우니 전수 검수를 권장합니다:
- 양형기준 권고형 범위(`guideline_min/max_months`), 형량영역(`area_min/max_months`) — 판결문의
  "[권고영역 및 권고형의 범위]" 문구를 정확히 옮겨야 함
- 특별양형인자 개수(`aggravating_factors`, `mitigating_factors`)
- 가설 검증용 항목 6개 (`distribution_purpose_established` 등)
