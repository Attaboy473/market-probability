# -*- coding: utf-8 -*-
"""
BI RATE RADAR — Dashboard Streamlit (v3, clean & simple)
Probabilitas keputusan RDG Bank Indonesia dari
konsensus ekonom + pasar obligasi (PHEI) + data makro.

Jalankan:  streamlit run app.py
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, time as dtime

import bi_rdg_calc as calc

st.set_page_config(page_title="BI Rate Radar", layout="wide",
                   initial_sidebar_state="collapsed")

# ============================== STYLING ==============================
CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1100px;}

/* header */
.header-row {display: flex; justify-content: space-between; align-items: flex-end;
  border-bottom: 1px solid #262d3a; padding-bottom: 16px; margin-bottom: 24px;}
.header-row h1 {font-size: 1.7rem; font-weight: 700; margin: 0; letter-spacing: -0.3px;}
.header-row .sub {color: #8b93a7; font-size: 0.88rem; margin-top: 4px;}
.header-right {text-align: right; color: #8b93a7; font-size: 0.82rem; line-height: 1.6;}
.header-right b {color: #e6e9ef; font-weight: 600;}

/* verdict */
.verdict {background: #151a23; border: 1px solid #262d3a; border-left: 4px solid #6366f1;
  border-radius: 10px; padding: 18px 24px; margin: 0 0 26px;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;}
.verdict .v-main {font-size: 1.05rem; font-weight: 600;}
.verdict .v-sub {color: #8b93a7; font-size: 0.85rem; margin-top: 3px;}
.verdict .v-prob {text-align: right;}
.verdict .v-prob .p {font-size: 1.9rem; font-weight: 700; line-height: 1;}
.verdict .v-prob .t {font-size: 0.72rem; color: #8b93a7; letter-spacing: 0.8px;
  text-transform: uppercase; margin-top: 4px;}

/* probability track */
.prob-track {display: flex; height: 14px; border-radius: 7px; overflow: hidden;
  border: 1px solid #262d3a; margin: 18px 0 10px;}
.prob-seg {height: 100%;}
.track-legend {display: flex; gap: 28px; margin-bottom: 24px;}
.track-legend .item {display: flex; align-items: center; gap: 8px;
  font-size: 0.86rem; color: #c8cdd8;}
.track-legend .dot {width: 10px; height: 10px; border-radius: 3px;}
.track-legend .pct {color: #e6e9ef; font-weight: 700;}

/* outcome cards */
.oc {background: #151a23; border: 1px solid #262d3a; border-radius: 10px;
  padding: 18px 20px 20px;}
.oc.winner {border-color: #4f566b; background: #181d29;}
.oc-top {display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 12px;}
.oc-top .name {font-weight: 600; font-size: 0.95rem; color: #e6e9ef;}
.oc-top .tag {font-size: 0.68rem; color: #fbbf24; border: 1px solid #fbbf2455;
  border-radius: 999px; padding: 2px 10px; margin-left: 8px; letter-spacing: 0.6px;}
.oc-top .pct {font-size: 1.45rem; font-weight: 700;}
.mini-track {background: #262d3a; border-radius: 999px; height: 6px;
  margin-bottom: 14px; overflow: hidden;}
.mini-fill {height: 100%; border-radius: 999px;}
.oc-split {display: flex; justify-content: space-between; color: #8b93a7;
  font-size: 0.76rem; margin-bottom: 10px;}
.oc-desc {color: #6b7280; font-size: 0.78rem; line-height: 1.5;}

.section-h {font-size: 0.98rem; font-weight: 650; margin: 26px 0 12px; color: #e6e9ef;}
.dim {color: #6b7280; font-size: 0.78rem;}
.stTabs [data-baseweb="tab-list"] {gap: 4px;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ============================== DATA ==============================
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

te, phei, yf, calendar, legs, final, bt = load_all()

rate = te.get("bi_rate")
nxt = te.get("next_meeting") or {}
inf = te.get("inflation")
cons = te.get("next_consensus")
mode = max(final, key=final.get)

MOVES_META = {
    -25: {"label": "Turun 25 bps", "short": "CUT -25bp", "color": "#22c55e",
          "desc": "BI menurunkan suku bunga acuan sebesar 25 bps."},
    0:   {"label": "Tahan", "short": "HOLD", "color": "#3b82f6",
          "desc": "BI menahan suku bunga acuan di level saat ini."},
    25:  {"label": "Naik 25 bps", "short": "HIKE +25bp", "color": "#ef4444",
          "desc": "BI menaikkan suku bunga acuan sebesar 25 bps."},
}
LEG_LABELS = {"consensus": "Konsensus ekonom", "market": "Pasar obligasi",
              "macro": "Makro"}

BULAN = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
         7: "Jul", 8: "Agu", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"}

def fmt_date_id(iso):
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return f"{d.day} {BULAN[d.month]} {d.year}"
    except Exception:
        return iso or "-"

def rdg_countdown():
    try:
        d = datetime.strptime(nxt["date"], "%Y-%m-%d").date()
        dt = datetime.combine(d, dtime(14, 30))  # 07:30 GMT = 14:30 WIB
        diff = (dt - datetime.now()).total_seconds()
        if diff > 86400: return f"sekitar {diff/86400:.0f} hari lagi"
        if diff > 3600: return f"sekitar {int(diff//3600)} jam lagi"
        if diff > 0: return f"sekitar {int(diff//60)} menit lagi"
        return "pengumuman sedang / sudah berjalan"
    except Exception:
        return ""

# ============================== HEADER ==============================
st.markdown(f"""
<div class="header-row">
  <div>
    <h1>BI Rate Radar</h1>
    <div class="sub">Probabilitas keputusan RDG Bank Indonesia dari konsensus ekonom,
    pasar obligasi, dan data makro</div>
  </div>
  <div class="header-right">
    RDG berikutnya<br><b>{fmt_date_id(nxt.get('date'))}</b> &middot; {rdg_countdown()}
  </div>
</div>
""", unsafe_allow_html=True)

# ============================== KPI ==============================
lo, hi = calc.CONFIG["target_band"]
inf_pos_txt = ""
if inf is not None:
    pos = min(max((inf-lo)/(hi-lo), 0), 1)
    inf_pos_txt = f"{pos*100:.0f}% dalam target band BI"

c1, c2, c3, c4 = st.columns(4)
c1.metric("BI Rate saat ini", f"{rate:.2f}%" if rate else "-",
          delta=None)
c2.metric("Inflasi YoY", f"{inf:.2f}%" if inf else "-",
          delta=inf_pos_txt, delta_color="off")
c3.metric("RDG berikutnya", fmt_date_id(nxt.get("date")), delta=None)
c4.metric("Konsensus ekonom", f"{cons:.2f}%" if cons else "-",
          delta="sumber: Trading Economics", delta_color="off")

st.write("")

# ============================== VERDICT ==============================
vm = MOVES_META[mode]
new_rate = (rate or 0) + mode/100
st.markdown(f"""
<div class="verdict" style="border-left-color:{vm['color']}">
  <div>
    <div class="v-main">Prediksi utama: {vm['label']} &mdash; BI Rate menjadi {new_rate:.2f}%</div>
    <div class="v-sub">{vm['desc']}</div>
  </div>
  <div class="v-prob">
    <div class="p" style="color:{vm['color']}">{final[mode]*100:.1f}%</div>
    <div class="t">Probabilitas model</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ============================== TRACK + KARTU ==============================
segs = ""
for m in [-25, 0, 25]:
    meta = MOVES_META[m]
    segs += (f'<div class="prob-seg" title="{meta["short"]}: {final[m]*100:.1f}%" '
             f'style="width:{final[m]*100:.2f}%;background:{meta["color"]}"></div>')
st.markdown(f'<div class="prob-track">{segs}</div>', unsafe_allow_html=True)

legend_items = "".join(
    f'<div class="item"><span class="dot" style="background:{MOVES_META[m]["color"]}"></span>'
    f'{MOVES_META[m]["short"]} <span class="pct">{final[m]*100:.1f}%</span></div>'
    for m in [-25, 0, 25])
st.markdown(f'<div class="track-legend">{legend_items}</div>', unsafe_allow_html=True)

o1, o2, o3 = st.columns(3)
for col, m in zip([o1, o2, o3], [-25, 0, 25]):
    meta = MOVES_META[m]
    w = final[m]*100
    winner = " winner" if m == mode else ""
    tag = '<span class="tag">PILIHAN MODEL</span>' if m == mode else ""
    split = " &nbsp;&middot;&nbsp; ".join(
        f"{LEG_LABELS[k]} {legs[k][0][m]*100:.0f}%" for k in legs)
    with col:
        st.markdown(f"""
        <div class="oc{winner}">
          <div class="oc-top">
            <span class="name">{meta['short']}{tag}</span>
            <span class="pct" style="color:{meta['color']}">{w:.1f}%</span>
          </div>
          <div class="mini-track"><div class="mini-fill"
            style="width:{w:.1f}%;background:{meta['color']}"></div></div>
          <div class="oc-split">{split}</div>
          <div class="oc-desc">{meta['desc']}</div>
        </div>""", unsafe_allow_html=True)

with st.expander("Cara membaca dashboard ini"):
    st.markdown("""
    Model menggabungkan tiga sumber sinyal menjadi satu distribusi probabilitas atas
    tiga kemungkinan keputusan RDG (turun / tahan / naik 25 bps):

    1. **Konsensus ekonom (45%)** - ekspektasi para ekonom dari survei Trading Economics.
    2. **Pasar obligasi (40%)** - apa yang dihargai pasar: spread yield SUN tenor pendek
       terhadap BI rate, momentum yield harian, arah indeks INDOBeX.
    3. **Makro (15%)** - tekanan inflasi terhadap target band BI, momentum rupiah,
       arah US Treasury.

    Ini alat analisis, bukan platform taruhan - pengganti Polymarket yang
    probabilitasnya dihitung dari data, bukan dari uang taruhan.
    """)

# ============================== TABS ==============================
PLOTLY_LAYOUT = dict(template="plotly_dark",
                     paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                     font=dict(color="#c8cdd8", size=12),
                     margin=dict(l=40, r=20, t=30, b=40))

tab_model, tab_bond, tab_macro, tab_cal = st.tabs(
    ["Model", "Pasar Obligasi", "Makro", "Kalender & Backtest"])

# ---------- MODEL ----------
with tab_model:
    w = calc.CONFIG["weights"]
    st.caption(f"Bobot model: konsensus {w['consensus']:.0%} | "
               f"pasar obligasi {w['market']:.0%} | makro {w['macro']:.0%}")

    df_legs = pd.DataFrame(
        [{"Kaki": LEG_LABELS[k],
          "P(CUT)": f"{legs[k][0][-25]*100:.1f}%",
          "P(HOLD)": f"{legs[k][0][0]*100:.1f}%",
          "P(HIKE)": f"{legs[k][0][25]*100:.1f}%"} for k in legs] +
        [{"Kaki": "Final (gabungan)",
          "P(CUT)": f"{final[-25]*100:.1f}%",
          "P(HOLD)": f"{final[0]*100:.1f}%",
          "P(HIKE)": f"{final[25]*100:.1f}%"}])
    st.dataframe(df_legs, width="stretch", hide_index=True)

    fig_legs = go.Figure()
    for m in [-25, 0, 25]:
        meta = MOVES_META[m]
        fig_legs.add_trace(go.Bar(
            name=meta["short"],
            x=[LEG_LABELS[k] for k in legs] + ["Final"],
            y=[legs["consensus"][0][m]*100, legs["market"][0][m]*100,
               legs["macro"][0][m]*100, final[m]*100],
            marker_color=meta["color"],
            hovertemplate=f"{meta['short']}: %{{y:.1f}}%<extra></extra>"))
    fig_legs.update_layout(barmode="group", height=360,
                           yaxis_title="Probabilitas (%)",
                           legend=dict(orientation="h", yanchor="bottom",
                                       y=1.02, xanchor="right", x=1),
                           **PLOTLY_LAYOUT)
    st.plotly_chart(fig_legs, width="stretch")

    st.markdown('<div class="section-h">Detail sinyal tiap kaki</div>',
                unsafe_allow_html=True)
    for k, (_p, notes) in legs.items():
        with st.expander(f"{LEG_LABELS[k]} (bobot {calc.CONFIG['weights'][k]:.0%})"):
            for n in notes:
                st.markdown(f"- {n}")

# ---------- OBLIGASI ----------
with tab_bond:
    curve = phei.get("yield_curve_today", {})
    curve_y = phei.get("yield_curve_yesterday", {})
    if curve:
        tenors = sorted(curve)
        fig_y = go.Figure()
        fig_y.add_trace(go.Scatter(x=tenors, y=[curve[t] for t in tenors],
            name="Hari ini", line=dict(color="#6366f1", width=2.5),
            hovertemplate="Tenor %{x} thn<br>Yield %{y:.2f}%<extra></extra>"))
        if curve_y:
            fig_y.add_trace(go.Scatter(x=tenors, y=[curve_y.get(t) for t in tenors],
                name="Kemarin", line=dict(color="#64748b", width=1.5, dash="dash"),
                hovertemplate="Tenor %{x} thn<br>Yield %{y:.2f}%<extra></extra>"))
        if rate:
            fig_y.add_hline(y=rate, line_dash="dot", line_color="#f59e0b",
                            annotation_text=f"BI Rate {rate:.2f}%",
                            annotation_position="bottom right")
        fig_y.update_layout(height=420, xaxis_title="Tenor (tahun)",
                            yaxis_title="Yield (%)",
                            legend=dict(orientation="h", yanchor="bottom",
                                        y=1.02, xanchor="right", x=1),
                            **PLOTLY_LAYOUT)
        st.caption("Yield Curve SUN Indonesia (PHEI)")
        st.plotly_chart(fig_y, width="stretch")

    bench = phei.get("sbn_benchmark") or []
    if bench:
        st.markdown('<div class="section-h">SBN Benchmark</div>',
                    unsafe_allow_html=True)
        df_b = pd.DataFrame(bench)
        df_b["Perubahan (bps)"] = ((df_b["yield_today"] - df_b["yield_yest"]) * 100).round(1)
        df_b = df_b.rename(columns={
            "series": "Seri", "ttm": "TTM (thn)", "yield_today": "Yield (%)",
            "price_today": "Harga (%)", "coupon": "Kupon (%)"})
        df_b = df_b[["Seri", "TTM (thn)", "Yield (%)", "Perubahan (bps)",
                     "Harga (%)", "Kupon (%)"]]
        st.dataframe(df_b, width="stretch", hide_index=True)

    idx = phei.get("indexes") or {}
    if idx:
        st.markdown(f'<div class="section-h">Indeks Obligasi PHEI '
                    f'({phei.get("index_date", "")})</div>', unsafe_allow_html=True)
        names = {"ICBI": "ICBI Komposit", "INDOBeX_EffYield": "INDOBeX Eff. Yield",
                 "INDOBeX_Gov_TR": "INDOBeX Gov. Total Return"}
        cols = st.columns(len(idx))
        for col, (k, v) in zip(cols, idx.items()):
            col.metric(names.get(k, k), f"{v['last']:,.2f}",
                       delta=f"{v['chg']:+.4f} vs kemarin")

# ---------- MAKRO ----------
with tab_macro:
    st.caption("Indikator eksternal (yfinance). Perubahan 3 bulan dipakai model "
               "untuk mengukur momentum.")
    meta_yf = {"USDIDR": ("USD/IDR", "", "Rp "), "IHSG": ("IHSG", "", ""),
               "US10Y": ("US Treasury 10Y", "%", "")}
    cols = st.columns(3)
    for col, (k, (label, suffix, prefix)) in zip(cols, meta_yf.items()):
        d = yf.get(k)
        with col:
            if d:
                chg3 = d.get("chg_3m_pct")
                delta = f"1 mgg {d.get('chg_1w_pct', 0):+.2f}%"
                if chg3 is not None:
                    delta += f" | 3 bln {chg3:+.2f}%"
                col.metric(label, f"{prefix}{d['last']:,.4g}{suffix}", delta=delta)
            else:
                col.metric(label, "-")

    if inf is not None:
        st.markdown('<div class="section-h">Posisi inflasi terhadap target band BI</div>',
                    unsafe_allow_html=True)
        fig_b = go.Figure(go.Indicator(
            mode="number", value=inf, number={"suffix": "%", "font": {"size": 40}},
            gauge={"shape": "bullet",
                   "axis": {"range": [lo, hi], "tickvals": [lo, (lo+hi)/2, hi]},
                   "steps": [{"range": [lo, (lo+hi)/2], "color": "#14532d"},
                             {"range": [(lo+hi)/2, hi], "color": "#7f1d1d"}],
                   "threshold": {"line": {"color": "#f59e0b", "width": 4},
                                 "thickness": 0.9, "value": inf}}))
        fig_b.update_layout(height=130, margin=dict(t=10, b=10, l=20, r=20),
                            paper_bgcolor="rgba(0,0,0,0)",
                            font=dict(color="#e6e9ef"))
        st.plotly_chart(fig_b, width="stretch")
        pos = min(max((inf-lo)/(hi-lo), 0), 1)
        side = ("paruh atas, mendekati batas target (tekanan hawkish)" if pos > 0.5
                else "paruh bawah (ruang dovish lebih besar)")
        st.caption(f"Inflasi {inf:.2f}% berada di posisi {pos*100:.0f}% target band "
                   f"{lo} - {hi}%: {side}.")

# ---------- KALENDER & BACKTEST ----------
with tab_cal:
    st.markdown('<div class="section-h">Kalender ekonomi Indonesia</div>',
                unsafe_allow_html=True)
    if calendar:
        rows = []
        for e in calendar:
            cells = e["cells"]
            ev = next((c for c in cells if c and not c.endswith(("AM", "PM"))
                       and "%" not in c and not c.startswith("$") and c != "ID"), "?")
            prev = next((c for c in cells if "%" in c or c.startswith("$")), "")
            rows.append({"Tanggal": fmt_date_id(e["date"]), "Event": ev,
                         "Sebelumnya": prev})
        df_cal = pd.DataFrame(rows).drop_duplicates(subset=["Event"])
        st.dataframe(df_cal, width="stretch", hide_index=True, height=320)
    else:
        st.info("Kalender belum berhasil dimuat.")

    st.markdown('<div class="section-h">Backtest: prediksi vs hasil aktual</div>',
                unsafe_allow_html=True)
    if bt:
        df_bt = pd.DataFrame(bt)
        keep = [c for c in ["date", "move_actual", "consensus_move",
                            "pred_leg_consensus"] if c in df_bt.columns]
        df_bt = df_bt[keep].rename(columns={
            "date": "RDG", "move_actual": "Aktual (bps)",
            "consensus_move": "Konsensus (bps)",
            "pred_leg_consensus": "Prediksi model (bps)"})
        df_bt["RDG"] = df_bt["RDG"].map(fmt_date_id)

        def hasil_row(r):
            pred, act = r.get("Prediksi model (bps)"), r.get("Aktual (bps)")
            if pd.isna(pred):
                return "-"
            return "BENAR" if pred == act else "SALAH"
        df_bt["Hasil"] = df_bt.apply(hasil_row, axis=1)
        st.dataframe(df_bt, width="stretch", hide_index=True)
        hits = df_bt[df_bt["Hasil"].isin(["BENAR", "SALAH"])]
        if len(hits):
            n_hit = int((hits["Hasil"] == "BENAR").sum())
            st.caption(f"Akurasi kaki konsensus: {n_hit}/{len(hits)} "
                       f"({n_hit/len(hits):.0%})")
    else:
        st.info("Belum ada riwayat RDG dengan konsensus.")

# ============================== FOOTER ==============================
st.markdown("---")
st.markdown(f'<div class="dim">Diperbarui {datetime.now():%d %b %Y %H:%M} WIB | '
            f'Sumber: Trading Economics, PHEI (phei.co.id), yfinance | '
            f'Alat analisis, bukan rekomendasi investasi</div>',
            unsafe_allow_html=True)
