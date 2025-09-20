# ia_report.py
from statistics import mean
from db import select_last_hours

def resumo_24h():
    rows = select_last_hours(24)
    if not rows:
        return "Sem dados nas últimas 24h."

    ll, kw, kwh, fq, fp = [], [], [], [], []
    for ts, llavg, kwinst, kwhA, freq, pf in rows:
        ll.append(llavg); kw.append(kwinst); kwh.append(kwhA); fq.append(freq); fp.append(pf)

    def mm(vs):
        vals = [v for v in vs if v is not None]
        if not vals: return (None, None, None)
        return (min(vals), mean(vals), max(vals))

    ll_min, ll_avg, ll_max = mm(ll)
    fq_min, fq_avg, fq_max = mm(fq)
    fp_min, fp_avg, fp_max = mm(fp)

    consumo_24h = None
    kwh_valid = [v for v in kwh if v is not None]
    if len(kwh_valid) >= 2:
        consumo_24h = max(0.0, kwh_valid[-1] - kwh_valid[0])

    flags = []
    if ll_min is not None and ll_min < 340: flags.append(f"Baixa tensão (mín {ll_min:.1f} V)")
    if ll_max is not None and ll_max > 420: flags.append(f"Alta tensão (máx {ll_max:.1f} V)")
    if fq_min is not None and (fq_min < 59.5 or fq_max > 60.5): flags.append("Variação de frequência")
    if fp_avg is not None and fp_avg < 0.9: flags.append(f"FP médio baixo ({fp_avg:.2f})")

    linhas = []
    if consumo_24h is not None: linhas.append(f"Consumo estimado nas últimas 24h: {consumo_24h:.1f} kWh.")
    if ll_avg is not None:       linhas.append(f"Tensão LL média: {ll_avg:.1f} V (mín {ll_min:.1f} / máx {ll_max:.1f}).")
    if fq_avg is not None:       linhas.append(f"Frequência média: {fq_avg:.2f} Hz (mín {fq_min:.2f} / máx {fq_max:.2f}).")
    if fp_avg is not None:       linhas.append(f"Fator de potência médio: {fp_avg:.2f} (mín {fp_min:.2f} / máx {fp_max:.2f}).")
    if flags:                    linhas.append("Anomalias relevantes: " + " • ".join(flags))
    else:                        linhas.append("Sem anomalias relevantes nas últimas 24 horas.")

    return "\n".join(linhas)
