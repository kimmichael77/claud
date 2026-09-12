@echo off
REM 윈도우에서 더블클릭 실행파일(.exe)을 만드는 스크립트.
REM Python 3.10 이상이 설치되어 있어야 합니다 (https://www.python.org/downloads/windows/
REM 에서 설치 시 "Add python.exe to PATH" 체크 필수).
REM
REM 사용법: 이 파일을 더블클릭하거나, 이 폴더에서 명령 프롬프트를 열고
REM   build_windows_exe.bat
REM 를 실행하세요. 완료되면 dist\PanryeCodingConverter.exe 가 생성됩니다.

setlocal

where python >nul 2>nul
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않거나 PATH에 등록되지 않았습니다.
    echo https://www.python.org/downloads/windows/ 에서 Python을 설치한 뒤 다시 실행하세요.
    pause
    exit /b 1
)

echo [1/4] 가상환경 생성 중...
python -m venv .venv_build
call .venv_build\Scripts\activate.bat

echo [2/4] 필요한 패키지 설치 중...
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo [3/4] exe 빌드 중 (몇 분 걸릴 수 있습니다)...
pyinstaller --noconfirm --onefile --windowed ^
  --name PanryeCodingConverter ^
  --collect-all pdfplumber ^
  --collect-all pypdfium2 ^
  --collect-all anthropic ^
  --hidden-import docx ^
  gui.py

echo [4/4] 완료!
echo 결과물: dist\PanryeCodingConverter.exe
echo 이 파일 하나만 다른 폴더나 다른 컴퓨터로 옮겨서 더블클릭하면 실행됩니다.
pause
