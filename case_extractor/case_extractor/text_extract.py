"""PDF / DOCX 판결문 파일에서 텍스트를 추출한다."""

from __future__ import annotations

from pathlib import Path


class TextExtractError(Exception):
    pass


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix in (".docx",):
        return _extract_docx(path)
    if suffix == ".doc":
        raise TextExtractError(
            f"{path.name}: 옛 .doc 형식은 지원하지 않습니다. "
            "한글/워드에서 '.docx'로 다른 이름으로 저장한 뒤 다시 시도하세요."
        )
    raise TextExtractError(f"{path.name}: 지원하지 않는 파일 형식입니다 (.pdf 또는 .docx만 지원).")


def _extract_pdf(path: Path) -> str:
    import pdfplumber

    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            chunks.append(text)
    full_text = "\n".join(chunks).strip()
    if not full_text:
        raise TextExtractError(
            f"{path.name}: 텍스트를 추출하지 못했습니다. 스캔된 이미지 PDF일 수 있습니다 "
            "(OCR이 필요합니다. macOS에서는 'ocrmypdf'로 먼저 텍스트 레이어를 입힌 뒤 다시 시도하세요)."
        )
    return full_text


def _extract_docx(path: Path) -> str:
    import docx

    document = docx.Document(str(path))
    parts: list[str] = []
    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            parts.append(paragraph.text)
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    full_text = "\n".join(parts).strip()
    if not full_text:
        raise TextExtractError(f"{path.name}: 문서에서 텍스트를 찾을 수 없습니다.")
    return full_text


SUPPORTED_EXTENSIONS = (".pdf", ".docx")


def find_case_files(input_dir: Path) -> list[Path]:
    files = [
        p for p in sorted(input_dir.iterdir())
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return files
