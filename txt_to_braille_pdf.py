from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os


def main():

    input_file = "output.txt"
    output_pdf = "braille_output.pdf"

    if not os.path.exists(input_file):
        raise FileNotFoundError("output.txt not found")

    c = canvas.Canvas(output_pdf, pagesize=A4)
    width, height = A4

    x = 50
    y = height - 50

    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:

            if y < 50:
                c.showPage()
                y = height - 50

            c.drawString(x, y, line.rstrip())
            y -= 14

    c.save()

    print("✅ PDF created:", output_pdf)


if __name__ == "__main__":
    main()
