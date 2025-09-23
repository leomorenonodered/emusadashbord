# app.py — EMUSA BRASIL – CONTROLE E MONITORAMENTO DE ENERGIA
import os, io, csv, math, time, base64
from datetime import datetime, timedelta
from pathlib import Path

import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ====== flags & readers ======
USE_SIM = os.getenv("USE_SIM", "1") == "1"  # casa: 1 (simulador) | empresa: 0 (KRON real)
BASE = Path(__file__).parent

try:
    ANALYSIS_INTERVAL_HOURS = int(os.getenv("IA_REPORT_INTERVAL_HOURS", "6"))
except ValueError:
    ANALYSIS_INTERVAL_HOURS = 6
ANALYSIS_INTERVAL_HOURS = max(1, ANALYSIS_INTERVAL_HOURS)
ANALYSIS_INTERVAL_MS = ANALYSIS_INTERVAL_HOURS * 3600 * 1000


def _next_run_timestamp():
    return (datetime.now() + timedelta(hours=ANALYSIS_INTERVAL_HOURS)).isoformat()

from db import init_schema, insert_leitura, export_csv_last_hours
from ia_report import resumo_periodo
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

REGISTER_META = []
INITIAL_REGISTER_SCAN = []
AI_RELEVANT_KEYS = []
CONNECTION_INFO = {
    "status": "desconectado",
    "port": None,
    "canal": None,
    "identificador": None,
    "connected_at": None,
    "analysis_hours": ANALYSIS_INTERVAL_HOURS,
}

if reader:
    REGISTER_META = getattr(reader, "get_register_metadata", lambda: [])() or []
    CONNECTION_INFO.update(getattr(reader, "connection_info", {}) or {})
    CONNECTION_INFO.setdefault("status", "conectado")
    CONNECTION_INFO["connected_at"] = datetime.now().isoformat()
    CONNECTION_INFO["analysis_hours"] = ANALYSIS_INTERVAL_HOURS
    AI_RELEVANT_KEYS = getattr(reader, "relevant_field_names", lambda: [])() or []
    try:
        INITIAL_REGISTER_SCAN = getattr(reader, "scan_registers", lambda: [])() or []
    except Exception as e:
        print("Falha ao varrer registradores iniciais:", e)
        INITIAL_REGISTER_SCAN = []
else:
    AI_RELEVANT_KEYS = []

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
    html.H2("EMUSA BRASIL – CONTROLE E MONITORAMENTO DE ENERGIA", style={"color": fg}),
    html.Div("By Leo Moreno", style={"color": fg, "opacity": "0.7", "marginBottom": "8px"}),

    html.Div(id="connection-banner", style={
        "backgroundColor": "#111827",
        "border": "1px solid #1f2937",
        "borderRadius": "12px",
        "padding": "10px 14px",
        "color": fg,
        "marginBottom": "12px",
        "fontSize": "13px",
    }),

    html.Div([
        html.Button(
            "Exportar (CSV - Power BI)",
            id="btn-csv",
            style={"padding": "10px 14px", "borderRadius": "10px", "marginRight": "8px"},
        ),
        dcc.Download(id="dl-csv"),
        html.Button(
            "PDF 24h (com IA)",
            id="btn-pdf24",
            style={"padding": "10px 14px", "borderRadius": "10px"},
        ),
        dcc.Download(id="dl-pdf24"),
    ], style={"marginBottom": "12px"}),

    dcc.Tabs(
        id="main-tabs",
        value="tab-realtime",
        children=[
            dcc.Tab(
                label="Tempo real",
                value="tab-realtime",
                children=[
                    html.Div(
                        id="kpis",
                        style={
                            "display": "flex",
                            "gap": "10px",
                            "flexWrap": "wrap",
                            "marginBottom": "10px",
                        },
                    ),
                    html.Div(
                        [
                            dcc.Graph(id="g_ll", style={"height": "300px", "backgroundColor": bg}),
                            dcc.Graph(id="g_kwhA", style={"height": "260px", "backgroundColor": bg}),
                        ]
                    ),
                ],
                style={"backgroundColor": bg, "border": "1px solid #1f2937"},
                selected_style={
                    "backgroundColor": "#111827",
                    "color": fg,
                    "border": "1px solid #1f2937",
                },
            ),
            dcc.Tab(
                label="IA & Diagnóstico",
                value="tab-ia",
                children=[
                    html.Div(
                        [
                            html.Div(id="ia-status", style={"color": fg, "fontWeight": "600"}),
                            html.Div(
                                id="ia-next-run",
                                style={"color": fg, "opacity": "0.75", "fontSize": "12px"},
                            ),
                            html.Pre(
                                id="ia-summary",
                                style={
                                    "backgroundColor": "#111827",
                                    "border": "1px solid #1f2937",
                                    "borderRadius": "10px",
                                    "padding": "12px",
                                    "color": fg,
                                    "whiteSpace": "pre-wrap",
                                    "fontFamily": "Inter, system-ui, monospace",
                                    "fontSize": "13px",
                                    "minHeight": "120px",
                                },
                            ),
                        ],
                        style={
                            "display": "flex",
                            "flexDirection": "column",
                            "gap": "6px",
                            "marginBottom": "16px",
                        },
                    ),
                    dcc.Graph(id="ia-behavior", style={"height": "320px", "backgroundColor": bg}),
                    html.H4("Registros monitorados", style={"color": fg, "marginTop": "18px"}),
                    html.Div(
                        id="register-table",
                        style={
                            "backgroundColor": "#111827",
                            "border": "1px solid #1f2937",
                            "borderRadius": "10px",
                            "padding": "10px",
                            "overflowX": "auto",
                        },
                    ),
                ],
                style={"backgroundColor": bg, "border": "1px solid #1f2937"},
                selected_style={
                    "backgroundColor": "#111827",
                    "color": fg,
                    "border": "1px solid #1f2937",
                },
            ),
        ],
        style={"marginTop": "12px"},
    ),

    # Stores
    dcc.Store(id="mem", data={}),
    dcc.Store(
        id="hist",
        data={
            "ts": [],
            "ll1": [],
            "ll2": [],
            "ll3": [],
            "kwhA": [],
            "kw": [],
            "freq": [],
            "fp": [],
        },
    ),
    dcc.Store(id="register-meta", data=REGISTER_META),
    dcc.Store(id="register-scan", data=INITIAL_REGISTER_SCAN),
    dcc.Store(id="connection-info", data=CONNECTION_INFO),
    dcc.Store(
        id="ia-report",
        data={
            "last_run": None,
            "summary": None,
            "next_run": _next_run_timestamp(),
            "flags": [],
        },
    ),

    dcc.Interval(id="tick", interval=1000, n_intervals=0),
    dcc.Interval(id="ia-interval", interval=ANALYSIS_INTERVAL_MS, n_intervals=0),
], style={"backgroundColor": bg, "padding": "14px", "minHeight": "100vh", "fontFamily": "Inter, system-ui, Arial"})

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
    hist = hist or {"ts": [], "ll1": [], "ll2": [], "ll3": [], "kwhA": [], "kw": [], "freq": [], "fp": []}
    for key in ["ts", "ll1", "ll2", "ll3", "kwhA", "kw", "freq", "fp"]:
        if key not in hist: hist[key] = []

    hist["ts"].append(ts)
    hist["ll1"].append(ll1)
    hist["ll2"].append(ll2)
    hist["ll3"].append(ll3)
    hist["kwhA"].append(gnum(snap,"energia_kwh_a"))
    hist["kw"].append(gnum(snap, "potencia_kw_inst"))
    hist["freq"].append(gnum(snap, "frequencia"))
    hist["fp"].append(gnum(snap, "fp_avg"))

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

# ====== Connection banner ======
@app.callback(Output("connection-banner", "children"), Input("connection-info", "data"))
def render_connection_banner(info):
    info = info or {}
    status = (info.get("status") or "desconhecido").lower()
    interval = info.get("analysis_hours", ANALYSIS_INTERVAL_HOURS)
    if status.startswith("conect") or status.startswith("simul"):
        channel = info.get("canal") or "CH30"
        port = info.get("port") or "—"
        parts = [f"Conectado ao {channel} (porta {port})."]
        identifier = info.get("identificador")
        if identifier:
            parts.append(f"Identificador: {identifier}.")
        connected_at = info.get("connected_at")
        if connected_at:
            try:
                dt = datetime.fromisoformat(connected_at)
                parts.append(f"Sessão iniciada em {dt.strftime('%d/%m/%Y %H:%M')}.")
            except Exception:
                pass
        parts.append(f"Relatórios automáticos a cada {interval}h.")
        return html.Span(" ".join(parts))
    return html.Span("Leitor Modbus não conectado. Verifique cabos e alimentação do CH30.")


# ====== Tabela de registradores monitorados ======
@app.callback(
    Output("register-table", "children"),
    Input("mem", "data"),
    State("register-meta", "data"),
    State("register-scan", "data"),
)
def render_register_table(mem, meta, scan):
    meta = meta or []
    mem = mem or {}
    fallback = {row.get("name"): row.get("value") for row in (scan or []) if isinstance(row, dict)}
    if not meta:
        return html.Div("Nenhum registrador configurado no leitor.", style={"color": fg, "opacity": "0.7"})

    header_style = {
        "textAlign": "left",
        "padding": "6px 8px",
        "fontSize": "12px",
        "borderBottom": "1px solid #1f2937",
        "color": fg,
    }
    cell_style = {
        "padding": "6px 8px",
        "borderBottom": "1px solid #1f2937",
        "fontSize": "12px",
        "color": fg,
    }

    header = html.Tr([
        html.Th("Medida", style=header_style),
        html.Th("Registrador", style=header_style),
        html.Th("Fn", style=header_style),
        html.Th("Valor", style=header_style),
        html.Th("Unidade", style=header_style),
        html.Th("IA", style=header_style),
        html.Th("Descrição", style=header_style),
    ])

    rows = []
    for entry in meta:
        name = entry.get("name") or "--"
        value = mem.get(name)
        if value is None:
            value = fallback.get(name)
        if isinstance(value, (int, float)):
            fmt = f"{value:.3f}" if abs(value) < 100 else f"{value:.2f}"
        elif value is None:
            fmt = "--"
        else:
            fmt = str(value)

        ai_flag = bool(entry.get("ai"))
        badge = html.Span(
            "Sim" if ai_flag else "Não",
            style={
                "color": "#22d3ee" if ai_flag else fg,
                "opacity": "1" if ai_flag else "0.6",
                "fontWeight": "600" if ai_flag else "400",
            },
        )

        row_style = {"backgroundColor": "#1f2937"} if ai_flag else {}

        rows.append(
            html.Tr(
                [
                    html.Td(name, style={**cell_style, "fontWeight": "600" if ai_flag else "500"}),
                    html.Td(entry.get("register", "--"), style=cell_style),
                    html.Td(entry.get("fn", "--"), style=cell_style),
                    html.Td(fmt, style={**cell_style, "fontFamily": "monospace"}),
                    html.Td(entry.get("unit", ""), style=cell_style),
                    html.Td(badge, style=cell_style),
                    html.Td(entry.get("description", ""), style=cell_style),
                ],
                style=row_style,
            )
        )

    return html.Table([header] + rows, style={"width": "100%", "borderCollapse": "collapse"})


# ====== Gráfico de comportamento para IA ======
@app.callback(Output("ia-behavior", "figure"), Input("hist", "data"))
def render_ia_behavior(hist):
    hist = hist or {}
    ts = hist.get("ts") or []
    labels = [datetime.fromtimestamp(t).strftime("%H:%M:%S") for t in ts]
    kw = hist.get("kw") or []
    freq = hist.get("freq") or []
    fp_vals = hist.get("fp") or []
    fp_percent = [v * 100 if isinstance(v, (int, float)) else None for v in fp_vals]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(x=labels, y=kw, mode="lines", name="Potência (kW)", line=dict(color="#fb923c", width=2)),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=labels, y=freq, mode="lines", name="Frequência (Hz)", line=dict(color="#38bdf8", width=2)),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=fp_percent,
            mode="lines",
            name="FP (%)",
            line=dict(color="#a855f7", width=2, dash="dash"),
        ),
        secondary_y=True,
    )

    fig.update_layout(
        margin=dict(l=40, r=60, t=24, b=40),
        paper_bgcolor=bg,
        plot_bgcolor=bg,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color=fg)),
        font=dict(color=fg),
    )
    fig.update_xaxes(showgrid=True, gridcolor=grid, color=fg)
    fig.update_yaxes(title_text="Potência (kW)", showgrid=True, gridcolor=grid, color=fg, secondary_y=False)
    fig.update_yaxes(
        title_text="Frequência (Hz) / FP (%)",
        showgrid=True,
        gridcolor=grid,
        color=fg,
        secondary_y=True,
    )
    return fig


# ====== Execução periódica da IA ======
@app.callback(
    Output("ia-report", "data"),
    Input("ia-interval", "n_intervals"),
    State("ia-report", "data"),
    prevent_initial_call=True,
)
def run_periodic_analysis(n, current):
    current = current or {}
    result = resumo_periodo(ANALYSIS_INTERVAL_HOURS)
    now = datetime.now()
    print(f"[IA] Iniciando análise automática ({ANALYSIS_INTERVAL_HOURS}h) às {now:%d/%m/%Y %H:%M:%S}.")
    summary = result.get("texto")
    if summary:
        print("[IA] Resumo gerado:\n" + summary)
    next_run = (now + timedelta(hours=ANALYSIS_INTERVAL_HOURS)).isoformat()
    return {
        "last_run": now.isoformat(),
        "summary": summary,
        "next_run": next_run,
        "flags": result.get("flags", []),
    }


# ====== Painel da IA ======
@app.callback(
    Output("ia-status", "children"),
    Output("ia-summary", "children"),
    Output("ia-next-run", "children"),
    Input("ia-report", "data"),
    State("connection-info", "data"),
)
def update_ia_status(report, info):
    info = info or {}
    interval = info.get("analysis_hours", ANALYSIS_INTERVAL_HOURS)
    report = report or {}
    next_run_text = ""
    if report.get("next_run"):
        try:
            nxt = datetime.fromisoformat(report["next_run"])
            next_run_text = f"Próxima análise automática prevista para {nxt.strftime('%d/%m/%Y %H:%M')}."
        except Exception:
            next_run_text = "Próxima análise automática agendada."

    if not report.get("last_run"):
        status = f"A IA aguardará {interval} horas acumuladas antes de compartilhar o primeiro relatório automático."
        summary = "Sem análises geradas ainda."
        return status, summary, next_run_text

    try:
        last_dt = datetime.fromisoformat(report["last_run"])
        status = f"Última análise automática executada em {last_dt.strftime('%d/%m/%Y %H:%M')} (janela de {interval}h)."
    except Exception:
        status = f"Última análise automática concluída (janela de {interval}h)."

    flags = report.get("flags") or []
    if flags:
        status += " Alertas: " + " | ".join(flags)

    summary = report.get("summary") or "Sem resumo disponível."
    return status, summary, next_run_text

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
