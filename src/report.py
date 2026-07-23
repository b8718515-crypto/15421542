"""리포트 생성 (Excel / PDF)"""
import io
import pandas as pd
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont


def to_excel(df: pd.DataFrame, sheet_name: str = "TOP5") -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return buffer.getvalue()


def to_pdf(df: pd.DataFrame, title: str = "알람 TOP5 리포트") -> bytes:
    """한글 지원 PDF 생성"""
    buffer = io.BytesIO()

    # 한글 폰트 등록 (내장 CID 폰트)
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
        font_name = "HYSMyeongJo-Medium"
    except Exception:
        font_name = "Helvetica"

    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    styles["Title"].fontName = font_name

    elements = [Paragraph(title, styles["Title"]), Spacer(1, 12)]

    data = [df.columns.tolist()] + df.astype(str).values.tolist()
    table = Table(data)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003876")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    elements.append(table)
    doc.build(elements)
    return buffer.getvalue()
