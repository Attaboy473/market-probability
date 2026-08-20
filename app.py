# -*- coding: utf-8 -*-
"""
BI RATE RADAR — Dashboard Streamlit (v3, clean & simple)
Probabilitas keputusan RDG Bank Indonesia dari
konsensus ekonom + pasar obligasi (PHEI) + data makro.

Jalankan:  streamlit run app.py
"""
import os, re, json
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, time as dtime, timedelta

import bi_rdg_calc as calc
import events as evt

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
    final, meta = calc.combine(legs, detail=True)
    bt = calc.backtest(te)
    return te, phei, yf, calendar, legs, final, meta, bt

te, phei, yf, calendar, legs, final, meta, bt = load_all()

@st.cache_data(ttl=1800, show_spinner="Mengambil data event inflasi & The Fed...")
def load_events():
    fed = evt.fetch_fed()
    fed_model = evt.model_fed(fed, yf)
    inf_te = evt.fetch_inflation_te()
    inf_model = evt.model_inflation(inf_te)
    # backtest historis (dibaca dari file JSON hasil run events.py, biar cepat)
    bt_hist = None
    for fn in ["backtest_full_model.json", "backtest_macro_history.json"]:
        p = os.path.join(os.path.dirname(os.path.abspath(evt.__file__)),
                         "data", fn)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                bt_hist = json.load(f)
            break
    return fed, fed_model, inf_te, inf_model, bt_hist

fed, fed_model, inf_te, inf_model, bt_hist = load_events()

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

_BULAN_EN = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}

def fmt_date_id(iso):
    # coba ISO dulu
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return f"{d.day} {BULAN[d.month]} {d.year}"
    except Exception:
        pass
    # coba format Inggris "August 19 2026"
    try:
        parts = iso.split()
        if len(parts) == 3 and parts[0].lower() in _BULAN_EN:
            mo = _BULAN_EN[parts[0].lower()]
            return f"{int(parts[1])} {BULAN[mo]} {parts[2]}"
    except Exception:
        pass
    return iso or "-"

# Terjemahan nama event kalender TE -> Bahasa Indonesia
TERJEMAH_EVENT = {
    "Interest Rate Decision": "Keputusan Suku Bunga",
    "Deposit Facility Rate": "Suku Bunga Fasilitas Simpanan",
    "Lending Facility Rate": "Suku Bunga Fasilitas Pinjaman",
    "Loan Growth YoY": "Pertumbuhan Kredit (YoY)",
    "Current Account": "Neraca Transaksi Berjalan",
    "M2 Money Supply YoY": "Uang Beredar M2 (YoY)",
    "S&P Global Manufacturing PMI": "PMI Manufaktur S&P Global",
    "Balance of Trade": "Neraca Perdagangan",
    "Inflation Rate YoY": "Inflasi (YoY)",
    "Core Inflation Rate YoY": "Inflasi Inti (YoY)",
    "Inflation Rate MoM": "Inflasi (MoM)",
    "Exports YoY": "Ekspor (YoY)",
    "Imports YoY": "Impor (YoY)",
    "Tourist Arrivals YoY": "Kedatangan Wisatawan (YoY)",
    "Foreign Exchange Reserves": "Cadangan Devisa",
    "Consumer Confidence": "Kepercayaan Konsumen",
    "Retail Sales YoY": "Penjualan Ritel (YoY)",
    "GDP Growth Rate YoY": "Pertumbuhan PDB (YoY)",
    "GDP Growth Rate": "Pertumbuhan PDB",
}

_REF_BULAN = {"JAN": "Jan", "FEB": "Feb", "MAR": "Mar", "APR": "Apr",
              "MAY": "Mei", "JUN": "Jun", "JUL": "Jul", "AUG": "Agu",
              "SEP": "Sep", "OCT": "Okt", "NOV": "Nov", "DEC": "Des"}

def terjemah_event(en):
    """'Interest Rate Decision AUG' -> 'Keputusan Suku Bunga (ref: Agu)'"""
    if not en:
        return "?"
    teks = en.strip()
    # pisahkan referensi periode di akhir, misal "AUG", "Q2", "JUL"
    m = re.match(r"^(.*?)[\s]+([A-Z]{3}|Q\d)(\s+\d{4})?$", teks)
    base, ref = (m.group(1), m.group(2) + (m.group(3) or "")) if m else (teks, None)
    base = base.strip()
    terjemah = TERJEMAH_EVENT.get(base, base)
    if terjemah == base:  # tidak ketemu di kamus -> coba terjemahan parsial
        for k, v in TERJEMAH_EVENT.items():
            if k in base:
                terjemah = base.replace(k, v)
                break
    if ref:
        ref = _REF_BULAN.get(ref.upper(), ref)
        return f"{terjemah} (ref: {ref})"
    return terjemah

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

tab_model, tab_bond, tab_macro, tab_cal, tab_events = st.tabs(
    ["Model", "Pasar Obligasi", "Makro", "Kalender & Backtest", "Event Lain"])

# ---------- MODEL ----------
with tab_model:
    w = calc.CONFIG["weights"]
    wu = meta.get("weights_used", w)
    dropped = meta.get("dropped", [])
    if dropped:
        st.warning("⚠️ Data tidak tersedia untuk: "
                   + ", ".join(LEG_LABELS[k] for k in dropped)
                   + ". Bobot kaki lain di-renormalisasi.")
    st.caption(f"Bobot efektif (renormalisasi): "
               + " | ".join(f"{LEG_LABELS[k]} {wu.get(k, 0):.0%}" for k in legs)
               + (f"   *(bobot nominal: {w['consensus']:.0%} / {w['market']:.0%} / {w['macro']:.0%})*"
                  if dropped else ""))

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
        eff = wu.get(k, 0)
        status = "" if k not in dropped else " — ⚠️ tidak tersedia, bobot 0%"
        with st.expander(f"{LEG_LABELS[k]} (bobot efektif {eff:.0%}){status}"):
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
    st.caption("Catatan: pada hari RDG (19 Agu), BI mengumumkan beberapa indikator "
               "sekaligus — suku bunga acuan, fasilitas simpanan & pinjaman, dan "
               "pertumbuhan kredit — sehingga tanggal yang sama muncul beberapa "
               "baris. Semua waktu dalam WIB (GMT+7).")
    if calendar:
        rows = []
        seen = set()
        for e in calendar:
            c = e["cells"]
            ev_en = c[4] if len(c) > 4 else "?"
            waktu_gmt = c[0] if c else ""
            # GMT -> WIB
            waktu_wib = waktu_gmt
            try:
                t = datetime.strptime(waktu_gmt, "%I:%M %p")
                t = (t + timedelta(hours=7)).time()
                waktu_wib = t.strftime("%H:%M")
            except Exception:
                pass
            aktual = c[6] if len(c) > 6 else ""
            kons = c[8] if len(c) > 8 else ""
            key = (e["date"], ev_en)
            if key in seen or not ev_en or ev_en == "?":
                continue
            seen.add(key)
            rows.append({"date_raw": e["date"], "Waktu (WIB)": waktu_wib,
                         "Event": terjemah_event(ev_en),
                         "Aktual / Sebelumnya": aktual or "-",
                         "Konsensus": kons or "-"})
        df_cal = pd.DataFrame(rows)
        # tanggal ditampilkan hanya pada baris pertama tiap grup hari
        df_cal["Tanggal"] = df_cal["date_raw"].map(fmt_date_id)
        df_cal.loc[df_cal["date_raw"].duplicated(), "Tanggal"] = ""
        df_cal = df_cal[["Tanggal", "Waktu (WIB)", "Event",
                         "Aktual / Sebelumnya", "Konsensus"]]
        st.dataframe(df_cal, width="stretch", hide_index=True, height=360)
    else:
        st.info("Kalender belum berhasil dimuat.")

    # ---------- BACKTEST UTAMA: 122 RDG (2016-2026) ----------
    st.markdown('<div class="section-h">Backtest historis — 122 rapat BI '
                '(Agu 2016 - Agu 2026)</div>', unsafe_allow_html=True)
    bt_full_path = os.path.join(evt.HERE, "data", "backtest_full_model.json")
    bt_full = {}
    if os.path.exists(bt_full_path):
        try:
            with open(bt_full_path, encoding="utf-8") as f:
                bt_full = json.load(f)
        except Exception:
            bt_full = {}
    if bt_full:
        sm = bt_full.get("summary", {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Rapat diuji", sm.get("n_meetings", "-"))
        c2.metric("Akurasi model gabungan", f"{sm.get('model_hit_rate', 0):.0%}")
        c3.metric("Baseline 'selalu hold'", f"{sm.get('naive_hold_hit_rate', 0):.0%}")
        verdict_bt = ("Model belum mengalahkan baseline — kaki konsensus & pasar "
                      "obligasi tidak punya arsip historis gratis sehingga diuji "
                      "sebagai netral." if
                      sm.get("model_hit_rate", 0) <= sm.get("naive_hold_hit_rate", 0)
                      else "Model mengalahkan baseline hold.")
        st.caption(verdict_bt + " Nilai sesungguhnya model ini ada pada prediksi "
                   "RDG live (kaki konsensus & obligasi hanya tersedia untuk rapat "
                   "mendatang).")
        df_h = pd.DataFrame(bt_full.get("meetings", []))
        if len(df_h):
            df_h = df_h.rename(columns={
                "date": "RDG", "move_actual": "Aktual (bps)",
                "pred_move": "Prediksi (bps)", "mu_macro_bps": "Sinyal makro (bps)"})
            df_h["RDG"] = df_h["RDG"].map(fmt_date_id)
            df_h["Hasil"] = ["BENAR" if h else "SALAH"
                             for h in df_h.get("exact_hit", [False]*len(df_h))]
            df_h = df_h[["RDG", "Aktual (bps)", "Prediksi (bps)",
                         "Sinyal makro (bps)", "Hasil"]]
            st.dataframe(df_h, width="stretch", hide_index=True, height=340)

    # ---------- BACKTEST KONSSENSUS (live, dari TE) ----------
    with st.expander("Backtest kaki konsensus (hanya 3 RDG terakhir — "
                     "keterbatasan data TE gratis)"):
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
            st.caption("Hanya RDG dengan konsensus yang tercatat di halaman "
                       "Trading Economics gratis yang bisa diuji.")
        else:
            st.info("Belum ada riwayat RDG dengan konsensus.")

# ---------- EVENT LAIN: INFLASI & THE FED ----------
with tab_events:
    st.caption("Dua event makro lain yang dipantau model: rilis inflasi Indonesia "
               "(bulanan) dan keputusan suku bunga The Fed (FOMC).")

    ev1, ev2 = st.columns(2, gap="large")

    # ===== INFLASI =====
    with ev1:
        st.markdown('<div class="section-h" style="margin-top:0">Inflasi Indonesia (YoY)</div>',
                    unsafe_allow_html=True)
        last_rel = inf_model.get("last_release") or {}
        next_rel = inf_model.get("next_release") or {}
        m1, m2 = st.columns(2)
        m1.metric("Rilis terakhir", f"{last_rel.get('actual', float('nan')):.2f}%",
                  delta=f"ref {last_rel.get('ref', '-')}", delta_color="off")
        m2.metric("Perkiraan titik", f"{inf_model['point_forecast']:.2f}%",
                  delta=f"rilis {fmt_date_id(next_rel.get('date'))}", delta_color="off")

        pf = inf_model["P"]
        st.markdown('<div class="dim">Probabilitas rilis berikutnya terhadap '
                    'target band BI (1,5 - 3,5%)</div>', unsafe_allow_html=True)
        segs_inf = ""
        for k, colr, lab in [("below_band", "#22c55e", "di bawah band"),
                             ("in_band", "#3b82f6", "dalam band"),
                             ("above_band", "#ef4444", "di atas band")]:
            w = pf[k]*100
            segs_inf += (f'<div class="prob-seg" title="{lab}: {w:.1f}%" '
                         f'style="width:{w:.2f}%;background:{colr}"></div>')
        st.markdown(f'<div class="prob-track">{segs_inf}</div>',
                    unsafe_allow_html=True)
        st.markdown(
            f'<div class="track-legend">'
            f'<div class="item"><span class="dot" style="background:#3b82f6"></span>'
            f'dalam band <span class="pct">{pf["in_band"]*100:.1f}%</span></div>'
            f'<div class="item"><span class="dot" style="background:#22c55e"></span>'
            f'di bawah <span class="pct">{pf["below_band"]*100:.1f}%</span></div>'
            f'<div class="item"><span class="dot" style="background:#ef4444"></span>'
            f'di atas <span class="pct">{pf["above_band"]*100:.1f}%</span></div>'
            f'</div>', unsafe_allow_html=True)

        # history inflasi dari dataset
        hist_data = evt.load_hist()
        inf_hist = hist_data.get("inflation_id_history", [])
        if inf_hist:
            df_ih = pd.DataFrame(inf_hist[-18:])
            df_ih["yoy"] = df_ih["yoy"].astype(float)
            fig_ih = go.Figure()
            fig_ih.add_trace(go.Bar(x=df_ih["month"], y=df_ih["yoy"],
                marker_color=["#ef4444" if v > hi else
                              ("#22c55e" if v < lo else "#3b82f6")
                              for v in df_ih["yoy"]],
                hovertemplate="%{x}: %{y:.2f}%<extra></extra>"))
            fig_ih.add_hline(y=hi, line_dash="dot", line_color="#ef4444",
                             annotation_text=f"batas atas {hi}%")
            fig_ih.add_hline(y=lo, line_dash="dot", line_color="#22c55e",
                             annotation_text=f"batas bawah {lo}%")
            fig_ih.update_layout(height=280, yaxis_title="YoY (%)",
                                 xaxis_title="",
                                 margin=dict(l=40, r=20, t=20, b=30),
                                 template="plotly_dark",
                                 paper_bgcolor="rgba(0,0,0,0)",
                                 plot_bgcolor="rgba(0,0,0,0)",
                                 font=dict(color="#c8cdd8", size=11))
            st.plotly_chart(fig_ih, width="stretch")
        with st.expander("Cara hitung"):
            for n in inf_model.get("notes", []):
                st.markdown(f"- {n}")

    # ===== THE FED =====
    with ev2:
        st.markdown('<div class="section-h" style="margin-top:0">Suku Bunga The Fed (FOMC)</div>',
                    unsafe_allow_html=True)
        nf = fed.get("next_fomc") or {}
        m3, m4 = st.columns(2)
        m3.metric("Fed Funds Rate", f"{fed.get('fed_rate', float('nan')):.2f}%",
                  delta=f"terakhir {fmt_date_id(fed.get('fed_last_date'))}",
                  delta_color="off")
        m4.metric("FOMC berikutnya", fmt_date_id(nf.get("date")),
                  delta=None)

        pfed = fed_model["P"]
        st.markdown('<div class="dim">Probabilitas keputusan FOMC berikutnya</div>',
                    unsafe_allow_html=True)
        segs_f = ""
        for mv in [-25, 0, 25]:
            meta = MOVES_META[mv]
            w = pfed[mv]*100
            segs_f += (f'<div class="prob-seg" title="{meta["short"]}: {w:.1f}%" '
                       f'style="width:{w:.2f}%;background:{meta["color"]}"></div>')
        st.markdown(f'<div class="prob-track">{segs_f}</div>',
                    unsafe_allow_html=True)
        st.markdown(
            f'<div class="track-legend">' + "".join(
                f'<div class="item"><span class="dot" style="background:{MOVES_META[m]["color"]}"></span>'
                f'{MOVES_META[m]["short"]} <span class="pct">{pfed[m]*100:.1f}%</span></div>'
                for m in [-25, 0, 25]) + "</div>", unsafe_allow_html=True)

        mode_f = fed_model["mode"]
        fm = MOVES_META[mode_f]
        st.markdown(f"""
        <div class="verdict" style="border-left-color:{fm['color']}; padding:14px 18px;">
          <div>
            <div class="v-main" style="font-size:0.95rem">Prediksi FOMC: {fm['label']}
            -> {fed.get('fed_rate', 0) + mode_f/100:.2f}%</div>
            <div class="v-sub">Bobot: konsensus 60% + makro 40%</div>
          </div>
          <div class="v-prob">
            <div class="p" style="font-size:1.5rem; color:{fm['color']}">{pfed[mode_f]*100:.1f}%</div>
          </div>
        </div>""", unsafe_allow_html=True)

        with st.expander("Cara hitung"):
            for leg_name in ["consensus", "macro"]:
                for n in fed_model["legs"][leg_name][1]:
                    st.markdown(f"- {n}")
        with st.expander("Jadwal FOMC ke depan"):
            for d in evt.load_hist().get("fomc_upcoming", []):
                st.markdown(f"- {fmt_date_id(d['date'])}")

    # ===== BACKTEST HISTORIS =====
    st.markdown('<div class="section-h">Backtest historis: 122 rapat BI (2016-2026)</div>',
                unsafe_allow_html=True)
    if bt_hist:
        s = bt_hist.get("summary", {})
        st.caption(s.get("note", ""))
        b1, b2, b3 = st.columns(3)
        b1.metric("Jumlah rapat diuji", s.get("n_meetings", "-"))
        model_hr = s.get("model_hit_rate")
        naive_hr = s.get("naive_hold_hit_rate")
        b2.metric("Hit rate model gabungan",
                  f"{model_hr*100:.1f}%" if model_hr is not None else "-")
        b3.metric("Baseline 'selalu hold'",
                  f"{naive_hr*100:.1f}%" if naive_hr is not None else "-")
        if model_hr is not None and naive_hr is not None:
            if abs(model_hr - naive_hr) < 0.02:
                st.warning("Hasil backtest jujur: tanpa arsip konsensus & harga "
                           "obligasi historis, model gabungan TIDAK mengalahkan "
                           "tebakan 'selalu hold'. Nilai prediksi sesungguhnya "
                           "harus datang dari kaki konsensus + pasar obligasi yang "
                           "hanya tersedia untuk RDG mendatang.")
            elif model_hr > naive_hr:
                st.success(f"Model mengalahkan baseline hold dengan selisih "
                           f"{(model_hr-naive_hr)*100:.1f} poin persentase.")
            else:
                st.warning(f"Model masih di bawah baseline hold "
                           f"({model_hr*100:.1f}% vs {naive_hr*100:.1f}%).")
    else:
        st.info("File backtest historis belum ada. Jalankan `python events.py` "
                "dulu untuk menghasilkannya.")

# ============================== FOOTER ==============================
st.markdown("---")
st.markdown(f'<div class="dim">Diperbarui {datetime.now():%d %b %Y %H:%M} WIB | '
            f'Sumber: Trading Economics, PHEI (phei.co.id), yfinance | '
            f'Alat analisis, bukan rekomendasi investasi</div>',
            unsafe_allow_html=True)
