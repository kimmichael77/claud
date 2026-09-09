#!/bin/bash
# 맥에서 더블클릭 실행 앱(.app)을 만드는 스크립트.
# Python 3.10 이상이 설치되어 있어야 합니다 (macOS에 기본 내장된 python3로도 됩니다).
#
# 사용법: 이 폴더(case_extractor)에서 터미널을 열고
#   bash build_macos_app.sh
# 를 실행하세요. 완료되면 dist/PanryeCodingConverter.app 이 생성됩니다.

set -e

if ! command -v python3 >/dev/null 2>&1; then
    echo "[오류] python3를 찾을 수 없습니다. https://www.python.org/downloads/macos/ 에서 설치하세요."
    exit 1
fi

echo "[1/4] 가상환경 생성 중..."
python3 -m venv .venv_build
source .venv_build/bin/activate

echo "[2/4] 필요한 패키지 설치 중..."
python3 -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo "[3/4] 앱 빌드 중 (몇 분 걸릴 수 있습니다)..."
pyinstaller --noconfirm --windowed \
  --name PanryeCodingConverter \
  --collect-all pdfplumber \
  --collect-all pypdfium2 \
  --collect-all anthropic \
  --hidden-import docx \
  gui.py

echo "[4/4] 완료!"
echo "결과물: dist/PanryeCodingConverter.app"
echo "이 앱을 다른 폴더나 다른 맥으로 옮겨서 더블클릭하면 실행됩니다."
echo "(직접 빌드했기 때문에 Apple 서명이 없어, 처음 실행 시 '확인되지 않은 개발자' 경고가"
echo " 뜰 수 있습니다. 이 경우 Finder에서 앱을 우클릭 -> 열기를 선택하세요.)"
