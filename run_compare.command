#!/bin/bash
cd "$(dirname "$0")"

echo "============================================"
echo " 판결문 자동검색 프로그램 (compare)"
echo "============================================"
echo

if ! command -v python3 &> /dev/null; then
    echo "[오류] python3이 설치되어 있지 않습니다."
    echo "https://www.python.org/downloads/ 에서 설치하거나"
    echo "터미널에서 'brew install python3' 를 실행해 설치하세요."
    read -p "Enter 키를 누르면 창이 닫힙니다..."
    exit 1
fi

echo "필요한 라이브러리를 설치합니다..."
pip3 install -r requirements.txt -q

if [ -z "$LAW_GO_KR_OC" ]; then
    read -p "국가법령정보센터 OC 값을 입력하세요: " LAW_GO_KR_OC
    export LAW_GO_KR_OC
fi

read -p "각 판례를 PDF 파일로도 저장할까요? 판례 수만큼 시간이 더 걸립니다 (y/N): " WANT_PDF
PDF_OPT=()
if [[ "$WANT_PDF" =~ ^[Yy]$ ]]; then
    PDF_OPT=(--pdf)
fi

echo
echo "검색을 시작합니다..."
echo
python3 -m judgment_search compare "${PDF_OPT[@]}"

echo
echo "완료되었습니다. compare_results 폴더를 확인하세요."
read -p "Enter 키를 누르면 창이 닫힙니다..."
