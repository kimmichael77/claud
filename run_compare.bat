@echo off
cd /d "%~dp0"

echo ============================================
echo  판결문 자동검색 프로그램 (compare)
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않거나 PATH에 등록되지 않았습니다.
    echo https://www.python.org/downloads/ 에서 설치 시
    echo "Add python.exe to PATH" 체크박스를 꼭 체크해주세요.
    pause
    exit /b 1
)

echo 필요한 라이브러리를 설치합니다...
pip install -r requirements.txt -q
echo.

if "%LAW_GO_KR_OC%"=="" (
    set /p LAW_GO_KR_OC=국가법령정보센터 OC 값을 입력하세요:
)

set PDF_OPT=
set /p WANT_PDF=각 판례를 PDF 파일로도 저장할까요? 판례 수만큼 시간이 더 걸립니다 (y/N):
if /i "%WANT_PDF%"=="y" set PDF_OPT=--pdf

echo.
echo 검색을 시작합니다...
echo.
python -m judgment_search compare %PDF_OPT%

echo.
echo 완료되었습니다. compare_results 폴더를 확인하세요.
pause
