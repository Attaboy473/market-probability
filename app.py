# -*- coding: utf-8 -*-
"""
BI RATE RADAR — Dashboard Streamlit
"Polymarket versi analisis": probabilitas keputusan RDG Bank Indonesia
dari konsensus ekonom + pasar obligasi (PHEI) + data makro.

Jalankan:  streamlit run app.py
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

import bi_rdg_calc as calc

st.set_page_config(page_title="BI Rate Radar", page_icon="🎯", layout="wide")

# ============================== CACHED DATA ==============================
@st.cache_data(ttl=1800, show_spinner="Mengambil data Trading Economics + PHEI + pasar...")
def load_all():
    te = calc.fetch_te()
    phei = calc.fetch_phei()
    yf = calc.fetch_yf()
    calendar = calc.fetch_te_calendar()
    legs = {
        "consensus": calc.leg_consensus(te),
        "market": calc.leg_market(phei, te),
        "macro": calc.leg_macro(te, yf),
    }
    final = calc.combine(legs)
    bt = calc.backtest(te)
    return te, phei, yf, calendar, legs, final, bt

def fmt_pct(x):
    return f"{x*100:.1f}%"

MOVE_LABELS = {-25: "CUT −25bp", 0: "HOLD", 25: "HIKE +25bp"}
MOVE_COLORS = {-25: "#22c55e", 0: "#3b82f6", 25: "#ef4444"}

# ============================== HEADER ==============================
te, phei, yf, calendar, legs, final, bt = load_all()

rate = te.get("bi_rate")
nxt = te.get("next_meeting") or {}
inf = te.get("inflation")

st.markdown("""
<style>
.big-title {font-size: 2rem; font-weight: 800;}
.dim {color: #888; font-size: 0.9rem;}
</style>
""", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
with c1:
    st.markdown('<div class="big-title">🎯 BI Rate Radar</div>', unsafe_allow_html=True)
    st.markdown('<div class="dim">Probabilitas keputusan RDG Bank Indonesia — '
                'konsensus ekonom × pasar obligasi × makro</div>', unsafe_allow_html=True)
with c2:
    st.metric("BI Rate", f"{rate:.2f}%" if rate else "—")
with c3:
    st.metric("Inflasi", f"{inf:.2f}%" if inf else "—")
with c4:
    st.metric("RDG Berikutnya", nxt.get("date", "—"))

if st.button("🔄 Refresh data", key="refresh"):
    st.cache_data.clear()
    st.rerun()

# ============================== PROBABILITAS ==============================
st.markdown("## 📊 Probabilitas Keputusan RDG")

mode = max(final, key=final.get)
p1, p2, p3 = st.columns(3)
for col, m in zip([p1, p2, p3], [-25, 0, 25]):
    p = final[m]
    star = " 🏆" if m == mode else ""
    col.metric(f"{MOVE_LABELS[m]}{star}", fmt_pct(p),
               delta=f"mode" if m == mode else None,
               delta_color="normal" if m == mode else "off")

g1, g2 = st.columns([1, 2])
with g1:
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number",
        value=final[mode]*100,
        number={"suffix": "%"},
        title={"text": f"P({MOVE_LABELS[mode]}) — paling mungkin"},
        gauge={"axis": {"range": [0, 100]},
               "bar": {"color": MOVE_COLORS[mode]},
               "steps": [{"range": [0, 33], "color": "#1e293b"},
                         {"range": [33, 66], "color": "#334155"},
                         {"range": [66, 100], "color": "#475569"}]}))
    fig_g.update_layout(height=300, margin=dict(t=50, b=10, l=20, r=20))
    st.plotly_chart(fig_g, width='stretch')

with g2:
    fig_b = go.Figure(go.Bar(
        x=[MOVE_LABELS[m] for m in [-25, 0, 25]],
        y=[final[m]*100 for m in [-25, 0, 25]],
        marker_color=[MOVE_COLORS[m] for m in [-25, 0, 25]],
        text=[fmt_pct(final[m]) for m in [-25, 0, 25]], textposition="outside"))
    fig_b.update_layout(height=300, yaxis_title="%",
                        margin=dict(t=20, b=20),
                        title="Distribusi probabilitas akhir (gabungan 3 kaki)")
    st.plotly_chart(fig_b, width='stretch')

# ============================== TABS ==============================
tab_model, tab_yield, tab_makro, tab_cal = st.tabs(
    ["🧠 Model 3 Kaki", "📈 Yield Curve & Obligasi", "🌍 Makro & Pasar", "📅 Kalender & Backtest"])

# ---------- TAB: MODEL ----------
with tab_model:
    st.markdown(f"**Bobot:** konsensus {calc.CONFIG['weights']['consensus']:.0%} · "
                f"pasar obligasi {calc.CONFIG['weights']['market']:.0%} · "
                f"makro {calc.CONFIG['weights']['macro']:.0%}")
    df_legs = pd.DataFrame({
        "Kaki": ["Konsensus ekonom", "Pasar obligasi", "Makro"],
        "P(CUT)": [fmt_pct(legs["consensus"][0][-25]),
                   fmt_pct(legs["market"][0][-25]),
                   fmt_pct(legs["macro"][0][-25])],
        "P(HOLD)": [fmt_pct(legs["consensus"][0][0]),
                    fmt_pct(legs["market"][0][0]),
                    fmt_pct(legs["macro"][0][0])],
        "P(HIKE)": [fmt_pct(legs["consensus"][0][25]),
                    fmt_pct(legs["market"][0][25]),
                    fmt_pct(legs["macro"][0][25])],
    })
    st.dataframe(df_legs, width='stretch', hide_index=True)

    fig_legs = go.Figure()
    for m in [-25, 0, 25]:
        fig_legs.add_trace(go.Bar(
            name=MOVE_LABELS[m],
            x=["Konsensus", "Pasar", "Makro", "FINAL"],
            y=[legs["consensus"][0][m]*100, legs["market"][0][m]*100,
               legs["macro"][0][m]*100, final[m]*100],
            marker_color=MOVE_COLORS[m]))
    fig_legs.update_layout(barmode="group", height=380, yaxis_title="%",
                           margin=dict(t=30))
    st.plotly_chart(fig_legs, width='stretch')

    st.markdown("**Catatan tiap kaki:**")
    for name, (_p, notes) in legs.items():
        for n in notes:
            st.markdown(f"- `{name}` {n}")

# ---------- TAB: YIELD ----------
with tab_yield:
    curve = phei.get("yield_curve_today", {})
    curve_y = phei.get("yield_curve_yesterday", {})
    if curve:
        tenors = sorted(curve)
        fig_y = go.Figure()
        fig_y.add_trace(go.Scatter(x=tenors, y=[curve[t] for t in tenors],
                                   name="Hari ini", line=dict(color="#3b82f6", width=3)))
        if curve_y:
            fig_y.add_trace(go.Scatter(x=tenors, y=[curve_y.get(t) for t in tenors],
                                       name="Kemarin", line=dict(color="#64748b",
                                       width=1.5, dash="dash")))
        if rate:
            fig_y.add_hline(y=rate, line_dash="dot", line_color="#f59e0b",
                            annotation_text=f"BI Rate {rate:.2f}%")
        fig_y.update_layout(title="Yield Curve SUN (PHEI)", height=420,
                            xaxis_title="Tenor (tahun)", yaxis_title="Yield (%)",
                            margin=dict(t=50))
        st.plotly_chart(fig_y, width='stretch')

    bench = phei.get("sbn_benchmark") or []
    if bench:
        df_b = pd.DataFrame(bench)
        df_b["chg_bps"] = ((df_b["yield_today"] - df_b["yield_yest"]) * 100).round(1)
        st.markdown("**SBN Benchmark:**")
        st.dataframe(df_b.rename(columns={
            "series": "Seri", "ttm": "TTM (thn)", "yield_today": "Yield hari ini",
            "price_today": "Harga", "coupon": "Kupon", "chg_bps": "Δ bps"}),
            width='stretch', hide_index=True)

    idx = phei.get("indexes") or {}
    if idx:
        st.markdown(f"**Indeks Obligasi PHEI** (per {phei.get('index_date', '?')}):")
        c = st.columns(len(idx))
        names = {"ICBI": "ICBI (komposit)", "INDOBeX_EffYield": "INDOBeX Eff. Yield",
                 "INDOBeX_Gov_TR": "INDOBeX Gov. TR"}
        for col, (k, v) in zip(c, idx.items()):
            col.metric(names.get(k, k), f"{v['last']:.2f}",
                       delta=f"{v['chg']:+.4f}")

# ---------- TAB: MAKRO ----------
with tab_makro:
    st.markdown("**Indikator pasar & makro (yfinance):**")
    cols = st.columns(3)
    meta = {"USDIDR": ("USD/IDR", "Rp"), "IHSG": ("IHSG", ""), "US10Y": ("US 10Y Yield", "%")}
    for col, (k, (label, unit)) in zip(cols, meta.items()):
        d = yf.get(k)
        if d:
            col.metric(label, f"{d['last']:,.4g}{unit}",
                       delta=f"{d['chg_1w_pct']:+.2f}% (1w)")
    st.caption("Perubahan 3 bulan dipakai model makro untuk mengukur momentum.")

    if inf is not None:
        lo, hi = calc.CONFIG["target_band"]
        pos = min(max((inf - lo) / (hi - lo), 0), 1)
        fig_t = go.Figure(go.Indicator(
            mode="gauge+number", value=inf, number={"suffix": "%"},
            title={"text": f"Inflasi vs target band BI [{lo}-{hi}%]"},
            gauge={"axis": {"range": [lo, hi]},
                   "bar": {"color": "#f59e0b"},
                   "steps": [{"range": [lo, (lo+hi)/2], "color": "#14532d"},
                             {"range": [(lo+hi)/2, hi], "color": "#7f1d1d"}]}))
        fig_t.update_layout(height=300, margin=dict(t=60, b=10))
        st.plotly_chart(fig_t, width='stretch')
        st.caption(f"Posisi inflasi: {pos*100:.0f}% dalam target band "
                   f"(0% = batas bawah, 100% = batas atas)")

# ---------- TAB: KALENDER ----------
with tab_cal:
    st.markdown("**Kalender ekonomi Indonesia** (Trading Economics):")
    if calendar:
        rows = []
        for e in calendar:
            cells = e["cells"]
            # cari kolom event (yang mengandung huruf kapital & bukan waktu)
            ev = next((c for c in cells if c and not c.endswith(("AM", "PM"))
                       and "%" not in c and not c.startswith("$") and c != "ID"), "?")
            prev = next((c for c in cells if "%" in c or c.startswith("$")), "")
            rows.append({"Tanggal": e["date"], "Event": ev, "Sebelumnya": prev})
        st.dataframe(pd.DataFrame(rows).drop_duplicates(),
                     width='stretch', hide_index=True)
    else:
        st.info("Kalender belum berhasil dimuat.")

    st.markdown("**Backtest (prediksi vs hasil aktual):**")
    if bt:
        df_bt = pd.DataFrame(bt)
        keep = [c for c in ["date", "move_actual", "consensus_move", "pred_leg_consensus"]
                if c in df_bt.columns]
        df_bt = df_bt[keep].rename(columns={
            "date": "RDG", "move_actual": "Aktual (bps)",
            "consensus_move": "Konsensus (bps)", "pred_leg_consensus": "Prediksi (bps)"})
        def hasil_row(r):
            pred = r.get("Prediksi (bps)")
            act = r.get("Aktual (bps)")
            if pd.isna(pred):
                return "—"
            return "✅" if pred == act else "❌"
        df_bt["hasil"] = df_bt.apply(hasil_row, axis=1)
        st.dataframe(df_bt, width='stretch', hide_index=True)
        hits = df_bt[df_bt["hasil"].isin(["✅", "❌"])]
        if len(hits):
            acc = (hits["hasil"] == "✅").mean()
            st.metric("Akurasi kaki konsensus", f"{acc:.0%}",
                      delta=f"{int((hits['hasil']=='✅').sum())}/{len(hits)} benar")
    else:
        st.info("Belum ada riwayat RDG dengan konsensus.")

st.markdown("---")
st.markdown(f'<div class="dim">Dibuat {datetime.now():%d %b %Y %H:%M} · '
            f'Sumber: Trading Economics, PHEI (phei.co.id), yfinance · '
            f'Alat analisis — bukan rekomendasi investasi</div>',
            unsafe_allow_html=True)
