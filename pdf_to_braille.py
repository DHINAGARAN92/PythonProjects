import pdfplumber
import subprocess
import os
import sys


def pdf_to_text(pdf_path):
    """
    Extract text from PDF
    """
    text = ""

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()

            if page_text:
                text += page_text + "\n"

    return text

def text_to_braille(text, table="en-us-g2.ctb"):
    """
    Convert text to Braille using liblouis CLI
    """

    LOU_PATH = r"liblouis-3.36.0-win32\bin\lou_translate.exe"

    if not os.path.exists(LOU_PATH):
        raise FileNotFoundError(f"lou_translate not found: {LOU_PATH}")

    cmd = [
        LOU_PATH,
        "-f", table
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

    return result.stdout

def main():

    # Input / Output files
    pdf_file = "input.pdf"
    output_file = "output.txt"

    print("=" * 40)
    print(" PDF to Braille Converter ")
    print("=" * 40)

    try:
        print("\nReading PDF...")
        text = pdf_to_text(pdf_file)

        if not text.strip():
            raise Exception("No readable text found in PDF")

        print("Converting to Braille...")
        braille = text_to_braille(text)

        print("Saving output...")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(braille)

        print("\n✅ Done Successfully!")
        print("📄 Output File:", output_file)

    except Exception as e:
        print("\n❌ ERROR:")
        print(e)

    print("\nPress Enter to exit...")
    input()


if __name__ == "__main__":
    main()