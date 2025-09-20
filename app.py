# app.py — EMUSA BRASIL – CONTROLE E MONITORAMENTO DE ENERGIA
import os, io, csv, math, time, base64
from datetime import datetime
from pathlib import Path

import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go

# ====== flags & readers ======
USE_SIM = os.getenv("USE_SIM", "1") == "1"  # casa: 1 (simulador) | empresa: 0 (KRON real)
BASE = Path(__file__).parent

from db import init_schema, insert_leitura, export_csv_last_hours
from report_24h import gerar_pdf_24h

if USE_SIM:
    from modbus_reader_sim import KronReaderSim as KronReader
else:
    # Seu leitor real original deve se chamar KronReader em modbus_reader.py
    # e ter método .connect() e .read_all()
    from modbus_reader import KronReader  # <- ajuste se necessário

# ====== init ======
init_schema()

try:
    # simulador não precisa BASE; leitor real geralmente recebe BASE
    reader = KronReader() if USE_SIM else KronReader(BASE)
    reader.connect()
except Exception as e:
    print("Erro ao iniciar reader:", e)
    reader = None

# ====== persistência ======
from time import time as _time
def persist_to_db(snapshot: dict):
    payload = {
        "ts": _time(),
        "tensao_l1": snapshot.get("tensao_l1"),
        "tensao_l2": snapshot.get("tensao_l2"),
        "tensao_l3": snapshot.get("tensao_l3"),
        "tensao_ll_l1": snapshot.get("tensao_ll_l1"),
        "tensao_ll_l2": snapshot.get("tensao_ll_l2"),
        "tensao_ll_l3": snapshot.get("tensao_ll_l3"),
        "tensao_ll_avg": snapshot.get("tensao_ll_avg"),
        "corrente_l1": snapshot.get("corrente_l1"),
        "corrente_l2": snapshot.get("corrente_l2") or snapshot.get("corrente_l2_guess"),
        "corrente_l3": snapshot.get("corrente_l3") or snapshot.get("corrente_l3_guess"),
        "potencia_kw_inst": snapshot.get("potencia_kw_inst"),
        "energia_kwh_a": snapshot.get("energia_kwh_a"),
        "energia_kwh_b": snapshot.get("energia_kwh_b"),
        "frequencia": snapshot.get("frequencia"),
        "fp_avg": snapshot.get("fp_avg"),
    }
    try:
        insert_leitura(payload)
    except Exception as e:
        print("DB insert error:", e)

# ====== Dash app ======
app = dash.Dash(__name__)
app.title = "EMUSA BRASIL – Dashboard"

bg = "#0f172a"     # dark azul
fg = "#E5E7EB"     # branco suave
grid = "#172034"   # grid

def kpi_card(title, value, unit="", color="#3b82f6"):
    return html.Div([
        html.Div(title, style={"fontSize":"12px","color":fg,"opacity":"0.8"}),
        html.Div(f"{value} {unit}", style={"fontSize":"22px","fontWeight":"700","color":fg}),
    ], style={
        "backgroundColor":"#111827", "border":"1px solid #1f2937",
        "borderRadius":"14px", "padding":"12px 14px", "minWidth":"160px"
    })

app.layout = html.Div([
    html.H2("EMUSA BRASIL – CONTROLE E MONITORAMENTO DE ENERGIA", style={"color":fg}),
    html.Div("By Leo Moreno", style={"color":fg,"opacity":"0.7","marginBottom":"8px"}),

    html.Div([
        html.Button("Exportar (CSV - Power BI)", id="btn-csv",
                    style={"padding":"10px 14px","borderRadius":"10px","marginRight":"8px"}),
        dcc.Download(id="dl-csv"),
        html.Button("PDF 24h (com IA)", id="btn-pdf24",
                    style={"padding":"10px 14px","borderRadius":"10px"}),
        dcc.Download(id="dl-pdf24"),
    ], style={"marginBottom":"12px"}),

    # KPIs
    html.Div(id="kpis", style={"display":"flex","gap":"10px","flexWrap":"wrap","marginBottom":"10px"}),

    # Gráficos
    html.Div([
        dcc.Graph(id="g_ll", style={"height":"300px","backgroundColor":bg}),
        dcc.Graph(id="g_kwhA", style={"height":"260px","backgroundColor":bg}),
    ]),

    # Stores
    dcc.Store(id="mem", data={}),
    dcc.Store(id="hist", data={
        "ts": [], "ll1": [], "ll2": [], "ll3": [], "kwhA": []
    }),

    dcc.Interval(id="tick", interval=1000, n_intervals=0)
], style={"backgroundColor":bg,"padding":"14px","minHeight":"100vh","fontFamily":"Inter, system-ui, Arial"})

# ====== Callback: leitura + histórico ======
@app.callback(
    Output("mem","data"),
    Output("hist","data"),
    Input("tick","n_intervals"),
    State("hist","data"),
    prevent_initial_call=False
)
def read_and_acc(n, hist):
    # leitura
    snap = {}
    try:
        if reader:
            snap = reader.read_all() or {}
    except Exception as e:
        print("Leitura erro:", e)

    # helper
    def gnum(d, key, default=None):
        v = d.get(key)
        return v if isinstance(v,(int,float)) else default

    # estimar ll_avg se faltar
    ll1, ll2, ll3 = gnum(snap,"tensao_ll_l1"), gnum(snap,"tensao_ll_l2"), gnum(snap,"tensao_ll_l3")
    if snap.get("tensao_ll_avg") is None:
        vals = [v for v in [ll1,ll2,ll3] if v is not None]
        snap["tensao_ll_avg"] = sum(vals)/len(vals) if vals else None

    # persistir no DB
    if snap:
        persist_to_db(snap)

    # atualizar histórico curto (para gráficos)
    ts = int(time.time())
    hist = hist or {"ts": [], "ll1": [], "ll2": [], "ll3": [], "kwhA": []}
    for key in ["ts","ll1","ll2","ll3","kwhA"]:
        if key not in hist: hist[key] = []

    hist["ts"].append(ts)
    hist["ll1"].append(ll1)
    hist["ll2"].append(ll2)
    hist["ll3"].append(ll3)
    hist["kwhA"].append(gnum(snap,"energia_kwh_a"))

    # limita 600 pontos ~ 10 min
    for k in hist:
        hist[k] = (hist[k] or [])[-600:]

    return snap, hist

# ====== Callback: KPIs + gráficos ======
@app.callback(
    Output("kpis","children"),
    Output("g_ll","figure"),
    Output("g_kwhA","figure"),
    Input("mem","data"),
    Input("hist","data"),
)
def render(mem, hist):
    mem = mem or {}
    hist = hist or {"ts": [], "ll1": [], "ll2": [], "ll3": [], "kwhA": []}

    def last(v):
        for x in reversed(v or []):
            if x is not None: return x
        return None

    ll_avg = mem.get("tensao_ll_avg")
    kw_inst = mem.get("potencia_kw_inst")
    fp = mem.get("fp_avg")
    freq = mem.get("frequencia")
    kwhA = mem.get("energia_kwh_a")

    kpis = [
        kpi_card("Tensão LL média", f"{ll_avg:.1f}" if ll_avg else "--", "V"),
        kpi_card("Potência ativa", f"{kw_inst:.2f}" if kw_inst else "--", "kW"),
        kpi_card("Fator de potência", f"{fp:.3f}" if fp else "--"),
        kpi_card("Frequência", f"{freq:.2f}" if freq else "--", "Hz"),
        kpi_card("Energia kWh A", f"{kwhA:.2f}" if kwhA else "--", "kWh"),
    ]

    # ---------- Gráfico senoide LL ----------
    # usa RMS mais recente de cada fase para amplitude
    ll1_rms = last(hist.get("ll1")) or 380.0
    ll2_rms = last(hist.get("ll2")) or 380.0
    ll3_rms = last(hist.get("ll3")) or 380.0

    A1 = ll1_rms * math.sqrt(2)
    A2 = ll2_rms * math.sqrt(2)
    A3 = ll3_rms * math.sqrt(2)

    phase = time.time() * 2 * math.pi * 0.2
    x_deg = list(range(0, 361, 2))
    x_rad = [math.radians(x) for x in x_deg]
    y1 = [A1 * math.sin(w + phase + 0.0) for w in x_rad]
    y2 = [A2 * math.sin(w + phase - 2*math.pi/3) for w in x_rad]
    y3 = [A3 * math.sin(w + phase + 2*math.pi/3) for w in x_rad]

    fig_ll = go.Figure()
    fig_ll.add_scatter(x=x_deg, y=y1, mode="lines", name="LL L1 (R)", line=dict(width=2, color="#3b82f6"))
    fig_ll.add_scatter(x=x_deg, y=y2, mode="lines", name="LL L2 (S)", line=dict(width=2, color="#10b981"))
    fig_ll.add_scatter(x=x_deg, y=y3, mode="lines", name="LL L3 (T)", line=dict(width=2, color="#f59e0b"))
    Amax = max(A1, A2, A3)
    fig_ll.update_layout(
        margin=dict(l=40, r=10, t=24, b=40),
        paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
        xaxis=dict(showgrid=True, gridcolor="#172034", color="#E5E7EB",
                   title=dict(text="Ângulo (°)", font=dict(color="#E5E7EB"))),
        yaxis=dict(showgrid=True, gridcolor="#172034", color="#E5E7EB",
                   title=dict(text="Volts (inst.)", font=dict(color="#E5E7EB")),
                   range=[-Amax*1.1, Amax*1.1]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(color="#E5E7EB")),
        font=dict(color="#E5E7EB")
    )

    # ---------- Gráfico kWh A (histórico curto em tempo real) ----------
    ts = hist.get("ts") or []
    labels = [datetime.fromtimestamp(t).strftime("%H:%M:%S") for t in ts]
    fig_k = go.Figure()
    fig_k.add_scatter(x=labels, y=hist.get("kwhA"), mode="lines+markers",
                      name="Energia kWh A", line=dict(width=2, color="#8b5cf6"),
                      marker=dict(size=5), connectgaps=True)
    fig_k.update_layout(
        margin=dict(l=40, r=10, t=24, b=40),
        paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
        xaxis=dict(showgrid=True, gridcolor="#172034", color="#E5E7EB"),
        yaxis=dict(showgrid=True, gridcolor="#172034", color="#E5E7EB",
                   title=dict(text="kWh", font=dict(color="#E5E7EB"))),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(color="#E5E7EB")),
        font=dict(color="#E5E7EB")
    )

    return kpis, fig_ll, fig_k

# ====== Callbacks de download ======
@app.callback(Output("dl-csv","data"), Input("btn-csv","n_clicks"), prevent_initial_call=True)
def download_csv(_n):
    cols, rows = export_csv_last_hours(24)
    mem = io.StringIO()
    w = csv.writer(mem); w.writerow(cols)
    for r in rows: w.writerow(r)
    mem.seek(0)
    fname = f"EMUSA_export_24h_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    # CSV é texto: pode retornar direto como string
    return dict(content=mem.getvalue(), filename=fname, type="text/csv")

@app.callback(Output("dl-pdf24","data"), Input("btn-pdf24","n_clicks"), prevent_initial_call=True)
def download_pdf24(_n):
    # Gera o arquivo em disco
    outdir = Path(__file__).parent / "RELATORIOS"; outdir.mkdir(exist_ok=True)
    fname = f"EMUSA_relatorio_24h_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    fpath = outdir / fname
    try:
        gerar_pdf_24h(str(fpath))
    except Exception as e:
        # fallback: cria um PDF mínimo para não quebrar o download
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(str(fpath))
        c.drawString(72, 800, "Relatório 24h - EMUSA")
        c.drawString(72, 780, f"Falha ao montar relatório completo: {e}")
        c.save()

    # Lê bytes e devolve em base64 (Dash exige serializável)
    with open(fpath, "rb") as f:
        blob = f.read()
    b64 = base64.b64encode(blob).decode("ascii")
    return dict(content=b64, filename=fname, type="application/pdf", base64=True)

if __name__ == "__main__":
    # Dash novo: use app.run(...)
    app.run(debug=True, host="127.0.0.1", port=8050)
