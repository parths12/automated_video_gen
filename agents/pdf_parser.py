"""PDF text extraction for NCERT chapters."""

from pathlib import Path

import fitz  # PyMuPDF


def parse_pdf_fast(pdf_path: str) -> str:
    """
    Fast text extraction using PyMuPDF.
    Suitable for text-selectable NCERT PDFs.
    """
    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text("text") + "\n\n"
    doc.close()
    return full_text


def load_parsed_text(mmd_path: str) -> str:
    """Reads parsed markdown and removes common OCR artefacts."""
    with open(mmd_path, encoding="utf-8") as f:
        text = f.read()
    lines = text.split("\n")
    lines = [l for l in lines if not l.startswith("[MISSING_PAGE")]
    lines = [l for l in lines if not l.startswith("[IGNORED]")]
    return "\n".join(lines)


def parse_ncert_pdf(pdf_path: str, parsed_dir: str | Path | None = None) -> str:
    """
    Full pipeline: PDF -> clean text.
    Uses PyMuPDF by default; saves copy to parsed_dir for inspection.
    """
    pdf_path = Path(pdf_path)
    print(f"[PDF Parser] Extracting text from {pdf_path}...")

    text = parse_pdf_fast(str(pdf_path))

    if parsed_dir:
        parsed_dir = Path(parsed_dir)
        parsed_dir.mkdir(parents=True, exist_ok=True)
        out_path = parsed_dir / f"{pdf_path.stem}.txt"
        out_path.write_text(text, encoding="utf-8")
        print(f"[PDF Parser] Saved text to {out_path}")

    print(f"[PDF Parser] Extracted {len(text)} characters")
    return text
