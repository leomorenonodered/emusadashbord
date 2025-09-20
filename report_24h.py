# report_24h.py
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from db import export_csv_last_hours
from ia_report import resumo_24h

def gerar_pdf_24h(path_pdf):
    c = canvas.Canvas(path_pdf, pagesize=A4)
    w, h = A4

    c.setFont("Helvetica-Bold", 14)
    c.drawString(2*cm, h-2*cm, "EMUSA BRASIL – Relatório 24h")
    c.setFont("Helvetica", 10)
    c.drawRightString(w-2*cm, h-2.7*cm, datetime.now().strftime("%d/%m/%Y %H:%M:%S"))

    # Resumo IA
    y = h - 4*cm
    c.setFont("Helvetica", 10)
    for line in resumo_24h().split("\n"):
        c.drawString(2*cm, y, line)
        y -= 0.6*cm
        if y < 3*cm:
            c.showPage(); y = h - 2*cm

    # Tabela (últimas 50 linhas)
    cols, rows = export_csv_last_hours(24)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(2*cm, y, "Resumo de Leituras (últimas 24h):")
    y -= 0.8*cm
    c.setFont("Helvetica", 9)
    for r in rows[-50:]:
        line = f"{r[0]} | LL_avg={r[7]} | kWhA={r[12]} | kW={r[11]} | FP={r[15]}"
        c.drawString(2*cm, y, line[:110])
        y -= 0.5*cm
        if y < 2*cm:
            c.showPage(); y = h - 2*cm
    c.showPage()
    c.save()
