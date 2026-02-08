import pdfplumber
import camelot
import subprocess
import os
import html

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.colors import black, lightgrey


# ==============================
# CONFIG
# ==============================

LOU_PATH = r"liblouis-3.36.0-win32\bin\lou_translate.exe"
BRAILLE_TABLE = "en-us-g2.ctb"

INPUT_PDF = "input.pdf"
OUTPUT_PDF = "full_braille_document.pdf"


# ==============================
# BRAILLE CONVERTER
# ==============================

def to_braille(text):
    """
    Convert text → Grade 2 Braille using liblouis
    """

    if not text.strip():
        return ""

    cmd = [
        LOU_PATH,
        "-f", BRAILLE_TABLE
    ]

    result = subprocess.run(
        cmd,
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    if result.returncode != 0:
        raise Exception("liblouis error:\n" + result.stderr)

    return result.stdout.strip()


# ==============================
# TEXT EXTRACTION
# ==============================

def extract_text(pdf_path):

    pages = {}

    with pdfplumber.open(pdf_path) as pdf:

        for i, page in enumerate(pdf.pages):

            text = page.extract_text()

            if text:
                lines = text.split("\n")
                pages[i + 1] = lines

    return pages


# ==============================
# TABLE EXTRACTION
# ==============================

def extract_tables(pdf_path):

    tables = camelot.read_pdf(pdf_path, pages="all")

    page_tables = {}

    for t in tables:

        page_no = int(t.page)

        if page_no not in page_tables:
            page_tables[page_no] = []

        page_tables[page_no].append(t.df)

    return page_tables


# ==============================
# PDF BUILDER
# ==============================

def build_pdf(text_pages, table_pages, output_file):

    doc = SimpleDocTemplate(
        output_file,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    story = []

    all_pages = sorted(set(text_pages) | set(table_pages))

    for page in all_pages:

        # ----------------------
        # NORMAL TEXT
        # ----------------------
        if page in text_pages:

            for line in text_pages[page]:

                braille = to_braille(line)

                safe_text = html.escape(braille)

                story.append(Paragraph(safe_text, styles["Normal"]))
                story.append(Spacer(1, 6))


        # ----------------------
        # TABLES
        # ----------------------
        if page in table_pages:

            for df in table_pages[page]:

                braille_data = []

                for row in df.values:

                    braille_row = []

                    for cell in row:

                        cell_text = str(cell)

                        cell_braille = to_braille(cell_text)

                        safe_cell = html.escape(cell_braille)

                        braille_row.append(safe_cell)

                    braille_data.append(braille_row)


                table = Table(
                    braille_data,
                    repeatRows=1,
                    hAlign="LEFT"
                )

                table.setStyle(TableStyle([

                    ("GRID", (0,0), (-1,-1), 0.4, black),

                    ("BACKGROUND", (0,0), (-1,0), lightgrey),

                    ("FONT", (0,0), (-1,-1), "Helvetica", 8),

                    ("ALIGN", (0,0), (-1,-1), "LEFT"),

                    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),

                    ("TOPPADDING", (0,0), (-1,-1), 5),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
                ]))

                story.append(table)
                story.append(Spacer(1, 20))


        story.append(PageBreak())


    doc.build(story)


# ==============================
# MAIN
# ==============================

def main():

    print("=" * 50)
    print(" PDF → TEXT + TABLES → GRADE 2 BRAILLE PDF ")
    print("=" * 50)

    # Check files
    if not os.path.exists(INPUT_PDF):
        raise FileNotFoundError("input.pdf not found")

    if not os.path.exists(LOU_PATH):
        raise FileNotFoundError("lou_translate.exe not found")

    print("\nExtracting text...")
    text_pages = extract_text(INPUT_PDF)

    print("Extracting tables...")
    table_pages = extract_tables(INPUT_PDF)

    print("Generating Braille PDF...")
    build_pdf(text_pages, table_pages, OUTPUT_PDF)

    print("\n✅ SUCCESS!")
    print("Output file:", OUTPUT_PDF)


if __name__ == "__main__":
    main()
