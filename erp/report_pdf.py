"""Render the evidence-grounded Markdown report with checked print layout."""
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]


def fonts():
    candidates = [
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
         Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    ]
    for regular, bold in candidates:
        if regular.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont("AuditSans", str(regular)))
            pdfmetrics.registerFont(TTFont("AuditBold", str(bold)))
            pdfmetrics.registerFontFamily("AuditSans", normal="AuditSans", bold="AuditBold")
            return
    raise RuntimeError("Install Arial or DejaVu Sans for a reproducible report render")


def markup(value):
    value = value.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    value = escape(value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"`([^`]+)`", r'<font color="#245978">\1</font>', value)
    return value


def main():
    fonts()
    source = ROOT / "reports/erpnext-detailed-report.md"
    destination = ROOT / "reports/Ajnas_ERPNext_Research_Report.pdf"
    ink, blue, muted = (colors.HexColor(value) for value in ("#172C40", "#126985", "#526778"))
    width = A4[0] - 96
    styles = {
        "title": ParagraphStyle("title", fontName="AuditBold", fontSize=25, leading=31,
                                textColor=ink, spaceAfter=18),
        "heading": ParagraphStyle("heading", fontName="AuditBold", fontSize=15, leading=20,
                                  textColor=blue, spaceBefore=19, spaceAfter=10, keepWithNext=True),
        "body": ParagraphStyle("body", fontName="AuditSans", fontSize=9.5, leading=14,
                               textColor=ink, spaceAfter=8, splitLongWords=True),
        "small": ParagraphStyle("small", fontName="AuditSans", fontSize=8, leading=11,
                                textColor=muted, spaceAfter=8),
        "cell": ParagraphStyle("cell", fontName="AuditSans", fontSize=8, leading=11,
                               textColor=ink, splitLongWords=True),
        "header": ParagraphStyle("header", fontName="AuditBold", fontSize=8, leading=11,
                                 textColor=ink, splitLongWords=True),
    }
    story = [Paragraph("AJNAS N B  /  RESEARCH EVIDENCE", styles["small"]), Spacer(1, 7)]
    lines = source.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                fields = [field.strip() for field in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", field) for field in fields):
                    rows.append(fields)
                index += 1
            columns = len(rows[0])
            fractions = {2: [.38, .62], 3: [.35, .33, .32], 4: [.34, .19, .23, .24],
                         5: [.32, .19, .19, .17, .13]}.get(columns, [1 / columns] * columns)
            cells = [[Paragraph(markup(field), styles["header" if number == 0 else "cell"])
                      for field in row] for number, row in enumerate(rows)]
            table = Table(cells, colWidths=[width * part for part in fractions], repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F2F5")),
                ("LINEBELOW", (0, 0), (-1, 0), .8, blue),
                ("LINEBELOW", (0, 1), (-1, -1), .35, colors.HexColor("#D5E0E6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story += [table, Spacer(1, 9)]
            continue
        if line.startswith("# "):
            story.append(Paragraph(markup(line[2:]), styles["title"]))
            index += 1
            continue
        if line.startswith("## "):
            story.append(Paragraph(markup(line[3:]), styles["heading"]))
            index += 1
            continue
        paragraph = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not lines[index].strip().startswith(("#", "|")):
            paragraph.append(lines[index].strip())
            index += 1
        story.append(Paragraph(markup(" ".join(paragraph)), styles["body"]))

    def page(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D5E0E6"))
        canvas.line(48, 39, A4[0] - 48, 39)
        canvas.setFont("AuditSans", 8)
        canvas.setFillColor(muted)
        canvas.drawString(48, 25, "Ajnas N B | ERPNext research evidence | October 1, 2026")
        canvas.drawRightString(A4[0] - 48, 25, f"{document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=48, rightMargin=48,
        topMargin=43, bottomMargin=53, title="Ajnas: Full ERPNext Research Audit",
        author="Ajnas N B", subject="Measured AI-refactoring checks, synthetic ERP data, costs and limitations")
    document.build(story, onFirstPage=page, onLaterPages=page)
    print(destination)


if __name__ == "__main__":
    main()
