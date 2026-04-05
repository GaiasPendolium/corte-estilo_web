from pathlib import Path
import re

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
MD_PATH = ROOT / "MANUAL_USUARIO_RECEPCION_Y_GERENCIA.md"
LOGO_PATH = ROOT / "frontend" / "public" / "corte_estilo_logo.png"
OUT_PATH = Path(r"c:\Users\slbqu\OneDrive\Documents\MANUAL_USUARIO_RECEPCION_Y_GERENCIA.pdf")


def clean_md_line(line: str) -> str:
    line = line.rstrip("\n")
    line = re.sub(r"!\[([^\]]*)\]\([^\)]*\)", r"\1", line)
    line = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", line)
    line = line.replace("**", "")
    line = line.replace("`", "")
    return line.strip()


def build_pdf(md_text: str) -> FPDF:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    if LOGO_PATH.exists():
        pdf.image(str(LOGO_PATH), x=10, y=8, w=28)
        pdf.ln(20)

    for raw in md_text.splitlines():
        line = clean_md_line(raw)

        if not line:
            pdf.ln(3)
            continue

        if line.startswith("# "):
            pdf.set_font("Helvetica", "B", 18)
            pdf.multi_cell(0, 9, line[2:])
            pdf.ln(1)
            continue

        if line.startswith("## "):
            pdf.set_font("Helvetica", "B", 14)
            pdf.multi_cell(0, 8, line[3:])
            pdf.ln(1)
            continue

        if line.startswith("### "):
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(0, 7, line[4:])
            continue

        if line.startswith("|"):
            pdf.set_font("Helvetica", "", 9)
            row = [c.strip() for c in line.strip("|").split("|")]
            if any(col.strip("-") for col in row):
                pdf.multi_cell(0, 6, " | ".join(row))
            continue

        if re.match(r"^\d+\.\s", line):
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, line)
            continue

        if line.startswith("- "):
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, f"- {line[2:]}")
            continue

        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, line)

    return pdf


def main() -> None:
    md_text = MD_PATH.read_text(encoding="utf-8")
    pdf = build_pdf(md_text)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT_PATH))
    print(f"PDF generado: {OUT_PATH}")


if __name__ == "__main__":
    main()
