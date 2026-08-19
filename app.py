# -*- coding: utf-8 -*-
"""
BI RATE RADAR — Dashboard Streamlit (v2, desain ulang)
"Polymarket versi analisis": probabilitas keputusan RDG Bank Indonesia
dari konsensus ekonom + pasar obligasi (PHEI) + data makro.

Jalankan:  streamlit run app.py
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, time as dtime

import bi_rdg_calc as calc

st.set_page_config(page_title="BI Rate Radar", page_icon="🎯",
                   layout="wide", initial_sidebar_state="collapsed")

# ============================== STYLING ==============================
CSS = """
<style>
/* --- bersihkan chrome default --- */
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1180px;}

/* --- hero banner --- */
.hero {
  background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 55%, #172554 100%);
  border: 1px solid #312e81; border-radius: 18px;
  padding: 26px 32px; margin-bottom: 20px;
  display: flex; justify-content: space-between; align-items: center; gap: 16px;
}
.hero h1 {font-size: 2.05rem; margin: 0; font-weight: 800; letter-spacing: -0.5px;}
.hero .sub {color: #94a3b8; margin-top: 6px; font-size: 0.92rem;}
.badge-live {
  display: inline-block; background: #052e16; color: #4ade80;
  border: 1px solid #166534; border-radius: 999px; padding: 3px 14px;
  font-size: 0.75rem; font-weight: 700; letter-spacing: 1.5px; margin-bottom: 8px;
}

/* --- kartu KPI --- */
.kpi-card {
  background: #151a23; border: 1px solid #232a36; border-radius: 14px;
  padding: 15px 18px; height: 108px;
}
.kpi-card .label {color: #8b93a7; font-size: 0.72rem; text-transform: uppercase;
  letter-spacing: 1.4px; font-weight: 600;}
.kpi-card .value {font-size: 1.55rem; font-weight: 750; margin-top: 3px;}
.kpi-card .hint {color: #64748b; font-size: 0.74rem; margin-top: 4px;}

/* --- banner keputusan --- */
.verdict {
  border-radius: 16px; padding: 18px 26px; margin: 4px 0 16px;
  border: 1px solid; display: flex; align-items: center; gap: 18px;
}
.verdict .v-emoji {font-size: 2.3rem;}
.verdict .v-title {font-size: 1.25rem; font-weight: 800;}
.verdict .v-sub {color: #94a3b8; font-size: 0.88rem; margin-top: 2px;}
.verdict .v-prob {margin-left: auto; text-align: right;}
.verdict .v-prob .p {font-size: 2.1rem; font-weight: 800; line-height: 1;}
.verdict .v-prob .t {font-size: 0.72rem; color: #94a3b8; text-transform: uppercase;
  letter-spacing: 1.2px;}

/* --- stacked bar gaya Polymarket --- */
.prob-track {display: flex; height: 46px; border-radius: 12px; overflow: hidden;
  border: 1px solid #232a36; margin: 6px 0 4px;}
.prob-seg {display: flex; align-items: center; justify-content: center;
  color: #0b0e14; font-weight: 800; font-size: 0.88rem; min-width: 2px;}
.track-legend {display: flex; gap: 18px; color: #8b93a7; font-size: 0.78rem; margin-bottom: 14px;}

/* --- kartu outcome --- */
.oc {background: #151a23; border: 1px solid #232a36; border-radius: 14px;
  padding: 14px 16px; height: 100%;}
.oc.winner {border-color: #f59e0b; box-shadow: 0 0 0 1px #f59e0b33;}
.oc-top {display: flex; justify-content: space-between; align-items: baseline;}
.oc-top .name {font-weight: 700; font-size: 0.92rem;}
.oc-top .pct {font-size: 1.5rem; font-weight: 800;}
.mini-track {background: #232a36; border-radius: 999px; height: 8px; margin: 9px 0 7px; overflow: hidden;}
.mini-fill {height: 100%; border-radius: 999px;}
.oc-hint {color: #64748b; font-size: 0.72rem; line-height: 1.45;}

/* --- tab --- */
.stTabs [data-baseweb="tab-list"] {gap: 8px;}
.stTabs [data-baseweb="tab"] {padding: 8px 18px; border-radius: 10px 10px 0 0;}

.section-h {font-size: 1.05rem; font-weight: 700; margin: 18px 0 8px; color: #e6e9ef;}
.dim {color: #64748b; font-size: 0.8rem;}
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
    -25: {"label": "CUT −25bp", "emoji": "🟢", "color": "#22c55e",
          "desc": "BI menurunkan suku bunga 25 bps"},
    0:   {"label": "HOLD", "emoji": "🔵", "color": "#3b82f6",
          "desc": "BI menahan suku bunga"},
    25:  {"label": "HIKE +25bp", "emoji": "🔴", "color": "#ef4444",
          "desc": "BI menaikkan suku bunga 25 bps"},
}
LEG_NAMES = {"consensus": "🗣️ Konsensus ekonom", "market": "📈 Pasar obligasi",
             "macro": "🌍 Makro"}

BULAN = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
         7: "Jul", 8: "Agu", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"}

def fmt_date_id(iso):
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return f"{d.day} {BULAN[d.month]} {d.year}"
    except Exception:
        return iso or "—"

def rdg_countdown():
    try:
        d = datetime.strptime(nxt["date"], "%Y-%m-%d").date()
        dt = datetime.combine(d, dtime(14, 30))   # 07:30 GMT = 14:30 WIB
        diff = (dt - datetime.now()).total_seconds()
        if diff > 86400: return f"⏳ {diff/86400:.0f} hari lagi"
        if diff > 3600: return f"⏳ {int(diff//3600)} jam {int(diff%3600//60)} mnt lagi"
        if diff > 0: return f"⏳ {int(diff//60)} menit lagi"
        return "🕑 keputusan sudah / sedang diumumkan"
    except Exception:
        return ""

# ============================== HERO ==============================
hero_html = f"""
<div class="hero">
  <div>
    <span class="badge-live">● LIVE MODEL</span>
    <h1>🎯 BI Rate Radar</h1>
    <div class="sub">Probabilitas keputusan RDG Bank Indonesia —
      konsensus ekonom × pasar obligasi × data makro</div>
  </div>
  <div style="text-align:right">
    <div class="dim">RDG {fmt_date_id(nxt.get('date'))}</div>
    <div style="font-weight:700; margin-top:4px">{rdg_countdown()}</div>
  </div>
</div>
"""
st.markdown(hero_html, unsafe_allow_html=True)

# ============================== KPI ==============================
lo, hi = calc.CONFIG["target_band"]
inf_pos = f"posisi {min(max((inf-lo)/(hi-lo),0),1)*100:.0f}% dalam target band [{lo}–{hi}%]" if inf else ""

c1, c2, c3, c4 = st.columns(4, gap="medium")
with c1:
    st.markdown(f"""<div class="kpi-card"><div class="label">BI Rate saat ini</div>
      <div class="value" style="color:#f59e0b">{rate:.2f}%</div>
      <div class="hint">deposit facility {(rate-1):.2f}% · lending {(rate+0.75):.2f}%</div></div>""",
      unsafe_allow_html=True)
with c2:
    st.markdown(f"""<div class="kpi-card"><div class="label">Inflasi YoY</div>
      <div class="value" style="color:#e6e9ef">{inf:.2f}%</div>
      <div class="hint">{inf_pos}</div></div>""", unsafe_allow_html=True)
with c3:
    st.markdown(f"""<div class="kpi-card"><div class="label">RDG Berikutnya</div>
      <div class="value" style="color:#e6e9ef">{fmt_date_id(nxt.get('date'))}</div>
      <div class="hint">pengumuman ±14:30 WIB</div></div>""", unsafe_allow_html=True)
with c4:
    cons_txt = f"{cons:.2f}%" if cons else "—"
    cons_hint = "ekspektasi ekonom (Trading Economics)"
    st.markdown(f"""<div class="kpi-card"><div class="label">Konsensus</div>
      <div class="value" style="color:#a78bfa">{cons_txt}</div>
      <div class="hint">{cons_hint}</div></div>""", unsafe_allow_html=True)

# ============================== VERDICT ==============================
vm = MOVES_META[mode]
new_rate = (rate or 0) + mode/100
verdict_html = f"""
<div class="verdict" style="border-color:{vm['color']};
     background:linear-gradient(120deg, {vm['color']}22, rgba(11,14,20,0.6));">
  <div class="v-emoji">{vm['emoji']}</div>
  <div>
    <div class="v-title">Prediksi utama: {vm['label']} → {new_rate:.2f}%</div>
    <div class="v-sub">{vm['desc']}</div>
  </div>
  <div class="v-prob">
    <div class="p" style="color:{vm['color']}">{final[mode]*100:.1f}%</div>
    <div class="t">probabilitas model</div>
  </div>
</div>
"""
st.markdown(verdict_html, unsafe_allow_html=True)

# ============================== STACKED BAR + KARTU ==============================
bar_segs = ""
for m in [-25, 0, 25]:
    meta = MOVES_META[m]
    w = final[m]*100
    label = f"{meta['label']} {w:.1f}%" if w >= 16 else (f"{w:.0f}%" if w >= 7 else "")
    bar_segs += (f'<div class="prob-seg" title="{meta["label"]}: {w:.1f}%" '
                 f'style="width:{w:.2f}%;background:{meta["color"]}">{label}</div>')
st.markdown(f'<div class="prob-track">{bar_segs}</div>', unsafe_allow_html=True)
st.markdown('<div class="track-legend">' + " · ".join(
    f'<span>{MOVES_META[m]["emoji"]} {MOVES_META[m]["label"]}</span>' for m in [-25, 0, 25])
    + "</div>", unsafe_allow_html=True)

o1, o2, o3 = st.columns(3, gap="medium")
for col, m in zip([o1, o2, o3], [-25, 0, 25]):
    meta = MOVES_META[m]
    w = final[m]*100
    winner = " winner" if m == mode else ""
    leg_txt = " · ".join(f"{LEG_NAMES[k].split()[0]} {legs[k][0][m]*100:.0f}%"
                         for k in ["consensus", "market", "macro"])
    crown = " 👑" if m == mode else ""
    with col:
        st.markdown(f"""
        <div class="oc{winner}">
          <div class="oc-top">
            <span class="name">{meta['emoji']} {meta['label']}{crown}</span>
            <span class="pct" style="color:{meta['color']}">{w:.1f}%</span>
          </div>
          <div class="mini-track"><div class="mini-fill"
            style="width:{w:.1f}%;background:{meta['color']}"></div></div>
          <div class="oc-hint">{leg_txt}<br>{meta['desc']}</div>
        </div>""", unsafe_allow_html=True)

with st.expander("ℹ️ Cara membaca dashboard ini"):
    st.markdown("""
    Model menggabungkan **3 sumber sinyal** menjadi satu distribusi probabilitas
    atas 3 kemungkinan keputusan RDG (turun / tahan / naik 25 bps):

    1. **Konsensus ekonom (45%)** — ekspektasi para ekonom dari survei Trading Economics.
    2. **Pasar obligasi (40%)** — apa yang "dihargai" pasar: spread yield SUN tenor
       pendek vs BI rate, momentum yield harian, arah indeks INDOBeX.
    3. **Makro (15%)** — tekanan inflasi vs target band BI, momentum rupiah, arah US Treasury.

    Ini **alat analisis**, bukan platform taruhan — pengganti Polymarket yang
    probabilitasnya dihitung dari data, bukan dari uang taruhan.
    """)

# ============================== TABS ==============================
PLOTLY_LAYOUT = dict(template="plotly_dark",
                     paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                     font=dict(color="#e6e9ef", size=12),
                     margin=dict(l=30, r=20, t=50, b=30))

tab_model, tab_bond, tab_macro, tab_cal = st.tabs(
    ["🧠 Model 3 Kaki", "📈 Pasar Obligasi", "🌍 Makro", "📅 Kalender & Backtest"])

# ---------- MODEL ----------
with tab_model:
    w = calc.CONFIG["weights"]
    st.markdown(f"""
    <div class="track-legend" style="margin-top:10px">
      <span class="badge-live" style="background:#1e1b4b;border-color:#4338ca;color:#a5b4fc">🗣️ KONSENSUS {w['consensus']:.0%}</span>
      <span class="badge-live" style="background:#172554;border-color:#1d4ed8;color:#93c5fd">📈 PASAR OBLIGASI {w['market']:.0%}</span>
      <span class="badge-live" style="background:#052e16;border-color:#166534;color:#86efac">🌍 MAKRO {w['macro']:.0%}</span>
    </div>""", unsafe_allow_html=True)

    df_legs = pd.DataFrame(
        [{ "Kaki": LEG_NAMES[k],
           "P(CUT)": f"{legs[k][0][-25]*100:.1f}%",
           "P(HOLD)": f"{legs[k][0][0]*100:.1f}%",
           "P(HIKE)": f"{legs[k][0][25]*100:.1f}%" } for k in legs] +
        [{"Kaki": "⭐ FINAL (gabungan)",
          "P(CUT)": f"{final[-25]*100:.1f}%",
          "P(HOLD)": f"{final[0]*100:.1f}%",
          "P(HIKE)": f"{final[25]*100:.1f}%"}])
    st.dataframe(df_legs, width="stretch", hide_index=True)

    fig_legs = go.Figure()
    xlabels = ["🗣️ Konsensus", "📈 Pasar", "🌍 Makro", "⭐ FINAL"]
    for m in [-25, 0, 25]:
        meta = MOVES_META[m]
        fig_legs.add_trace(go.Bar(
            name=meta["label"],
            x=xlabels,
            y=[legs["consensus"][0][m]*100, legs["market"][0][m]*100,
               legs["macro"][0][m]*100, final[m]*100],
            marker_color=meta["color"],
            hovertemplate=f"{meta['label']}: %{{y:.1f}}%<extra></extra>"))
    fig_legs.update_layout(barmode="group", height=380,
                           yaxis_title="Probabilitas (%)", **PLOTLY_LAYOUT)
    st.plotly_chart(fig_legs, width="stretch")

    st.markdown('<div class="section-h">Detail sinyal tiap kaki</div>',
                unsafe_allow_html=True)
    for k, (_p, notes) in legs.items():
        with st.expander(f"{LEG_NAMES[k]} — {calc.CONFIG['weights'][k]:.0%}"):
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
            name="Hari ini", line=dict(color="#6366f1", width=3),
            hovertemplate="Tenor %{x} thn<br>Yield %{y:.2f}%<extra>Hari ini</extra>"))
        if curve_y:
            fig_y.add_trace(go.Scatter(x=tenors, y=[curve_y.get(t) for t in tenors],
                name="Kemarin", line=dict(color="#64748b", width=1.5, dash="dash"),
                hovertemplate="Tenor %{x} thn<br>Yield %{y:.2f}%<extra>Kemarin</extra>"))
        if rate:
            fig_y.add_hline(y=rate, line_dash="dot", line_color="#f59e0b",
                            annotation_text=f"BI Rate {rate:.2f}%")
        fig_y.update_layout(title="Yield Curve SUN Indonesia (PHEI)", height=430,
                            xaxis_title="Tenor (tahun)", yaxis_title="Yield (%)",
                            legend=dict(orientation="h", y=1.12), **PLOTLY_LAYOUT)
        st.plotly_chart(fig_y, width="stretch")

    bench = phei.get("sbn_benchmark") or []
    if bench:
        st.markdown('<div class="section-h">SBN Benchmark</div>',
                    unsafe_allow_html=True)
        df_b = pd.DataFrame(bench)
        df_b["Δ (bps)"] = ((df_b["yield_today"] - df_b["yield_yest"]) * 100).round(1)
        df_b = df_b.rename(columns={
            "series": "Seri", "ttm": "TTM (thn)", "yield_today": "Yield (%)",
            "price_today": "Harga (%)", "coupon": "Kupon (%)"})
        df_b = df_b[["Seri", "TTM (thn)", "Yield (%)", "Δ (bps)", "Harga (%)", "Kupon (%)"]]
        st.dataframe(df_b, width="stretch", hide_index=True)

    idx = phei.get("indexes") or {}
    if idx:
        st.markdown(f'<div class="section-h">Indeks Obligasi PHEI — '
                    f'{phei.get("index_date", "")}</div>', unsafe_allow_html=True)
        names = {"ICBI": "ICBI Komposit", "INDOBeX_EffYield": "INDOBeX Eff. Yield",
                 "INDOBeX_Gov_TR": "INDOBeX Gov. Total Return"}
        cols = st.columns(len(idx), gap="medium")
        for col, (k, v) in zip(cols, idx.items()):
            chg_color = "#22c55e" if v["chg"] >= 0 else "#ef4444"
            with col:
                st.markdown(f"""<div class="kpi-card"><div class="label">{names.get(k,k)}</div>
                  <div class="value" style="color:#e6e9ef;font-size:1.3rem">{v['last']:,.2f}</div>
                  <div class="hint" style="color:{chg_color}">{v['chg']:+.4f} vs kemarin</div></div>""",
                  unsafe_allow_html=True)

# ---------- MAKRO ----------
with tab_macro:
    meta_yf = {"USDIDR": ("USD/IDR", "", "Rp "), "IHSG": ("IHSG", "", ""),
               "US10Y": ("US Treasury 10Y", "%", "")}
    cols = st.columns(3, gap="medium")
    for col, (k, (label, suffix, prefix)) in zip(cols, meta_yf.items()):
        d = yf.get(k)
        with col:
            if d:
                chg = d.get("chg_1w_pct") or 0
                chg_color = "#22c55e" if chg >= 0 else "#ef4444"
                chg3 = d.get("chg_3m_pct")
                c3_txt = f"3 bln: {chg3:+.2f}%" if chg3 is not None else ""
                st.markdown(f"""<div class="kpi-card"><div class="label">{label}</div>
                  <div class="value" style="color:#e6e9ef;font-size:1.3rem">
                    {prefix}{d['last']:,.4g}{suffix}</div>
                  <div class="hint"><span style="color:{chg_color}">1 mgg: {chg:+.2f}%</span> · {c3_txt}</div></div>""",
                  unsafe_allow_html=True)
            else:
                st.markdown(f"""<div class="kpi-card"><div class="label">{label}</div>
                  <div class="value">—</div></div>""", unsafe_allow_html=True)

    if inf is not None:
        st.markdown('<div class="section-h">Posisi inflasi terhadap target band BI</div>',
                    unsafe_allow_html=True)
        fig_b = go.Figure(go.Indicator(
            mode="number", value=inf, number={"suffix": "%", "font": {"size": 46}},
            gauge={"shape": "bullet", "axis": {"range": [lo, hi], "tickvals":
                   [lo, (lo+hi)/2, hi]},
                   "steps": [
                       {"range": [lo, (lo+hi)/2], "color": "#14532d"},
                       {"range": [(lo+hi)/2, hi], "color": "#7f1d1d"}],
                   "threshold": {"line": {"color": "#f59e0b", "width": 4},
                                 "thickness": 0.9, "value": inf}}))
        fig_b.update_layout(height=140, margin=dict(t=10, b=10, l=20, r=20),
                            paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#e6e9ef"))
        st.plotly_chart(fig_b, width="stretch")
        pos = min(max((inf-lo)/(hi-lo), 0), 1)
        side = "paruh atas (mendekati batas → tekanan hawkish)" if pos > 0.5 \
            else "paruh bawah (ruang dovish lebih besar)"
        st.caption(f"Inflasi {inf:.2f}% berada di **{pos*100:.0f}%** target band "
                   f"[{lo}–{hi}%] → {side}.")

# ---------- KALENDER & BACKTEST ----------
with tab_cal:
    st.markdown('<div class="section-h">📅 Kalender ekonomi Indonesia</div>',
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

    st.markdown('<div class="section-h">🧪 Backtest: prediksi vs hasil aktual</div>',
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
                return "—"
            return "✅" if pred == act else "❌"
        df_bt["Hasil"] = df_bt.apply(hasil_row, axis=1)
        st.dataframe(df_bt, width="stretch", hide_index=True)
        hits = df_bt[df_bt["Hasil"].isin(["✅", "❌"])]
        if len(hits):
            n_hit = int((hits["Hasil"] == "✅").sum())
            st.markdown(f'<div class="dim">Akurasi kaki konsensus: '
                        f'<b>{n_hit}/{len(hits)}</b> ({n_hit/len(hits):.0%})</div>',
                        unsafe_allow_html=True)
    else:
        st.info("Belum ada riwayat RDG dengan konsensus.")

# ============================== FOOTER ==============================
st.markdown("---")
st.markdown(f'<div class="dim">Diperbarui {datetime.now():%d %b %Y %H:%M} WIB · '
            f'Sumber: Trading Economics · PHEI (phei.co.id) · yfinance · '
            f'Alat analisis — bukan rekomendasi investasi</div>',
            unsafe_allow_html=True)
