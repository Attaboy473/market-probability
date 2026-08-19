# -*- coding: utf-8 -*-
"""
EVENTS MODULE — event selain BI Rate:
  1. Inflasi Indonesia (rilis bulanan BPS via Trading Economics)
  2. Keputusan FOMC / The Fed
  3. Backtest diperpanjang: rekonstruksi sinyal makro vs sejarah RDG 2016-2026

Sumber data:
  - Trading Economics (halaman US interest rate + forecast + inflasi ID)
  - data/historical_rates.json (sejarah keputusan BI & Fed, kurasi manual)
  - yfinance (USDIDR & US10Y historis untuk rekonstruksi sinyal makro)
"""
import json, math, os, re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
HIST_PATH = os.path.join(HERE, "data", "historical_rates.json")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

# konfigurasi model (mirip bi_rdg_calc.py tapi terpisah biar gampang di-tune)
EVT_CONFIG = {
    "moves_bps": [-25, 0, 25],
    "sigma_fed_consensus_bps": 20,
    "sigma_fed_macro_bps": 50,
    "weights_fed": {"consensus": 0.6, "macro": 0.4},
    # inflasi
    "target_center": 2.5,           # tengah target band BI
    "target_band": (1.5, 3.5),
    "sigma_inflation_pct": 0.35,    # sebaran tipikal realisasi vs perkiraan
    "momentum_weight": 0.5,         # bobot momentum 3 bulan terakhir
    # makro (sama dengan bi_rdg_calc.py)
    "macro_bps_per_pct_inflation": 25,
    "macro_bps_per_pct_idr_3m": 15,
    "macro_bps_per_pct_ust_3m": 8,
    "sigma_macro_bps": 60,
}

def idnum(s):
    s = s.strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    return float(s)

def pct_of(x):
    if not x: return None
    m = re.search(r"([\d.,]+)\s*%", x)
    return idnum(m.group(1)) if m else None

def normal_pdf(x, mu, sigma):
    return math.exp(-0.5*((x-mu)/sigma)**2) / (sigma*math.sqrt(2*math.pi))

def grid_probs(mu, sigma, moves=None):
    moves = moves or EVT_CONFIG["moves_bps"]
    raw = [normal_pdf(m, mu, sigma) for m in moves]
    s = sum(raw)
    return {m: p/s for m, p in zip(moves, raw)}

def load_hist():
    with open(HIST_PATH, encoding="utf-8") as f:
        return json.load(f)

# ============================== THE FED ==============================
def fetch_fed():
    """FOMC: rate saat ini + rapat berikutnya + konsensus + forecast kuartalan."""
    out = {}
    try:
        r = requests.get("https://tradingeconomics.com/united-states/interest-rate",
                         headers=UA, timeout=40)
        soup = BeautifulSoup(r.text, "lxml")
        for t in soup.find_all("table"):
            txt = t.get_text(" ", strip=True)
            if "Interest Rate Decision" in txt and "Calendar" in txt:
                # cari index kolom dari header
                header_cells = []
                for tr in t.find_all("tr")[:2]:
                    header_cells = [c.get_text(" ", strip=True)
                                    for c in tr.find_all(["td", "th"])]
                    if any("Actual" in c for c in header_cells):
                        break
                def col(name):
                    for i, c in enumerate(header_cells):
                        if name.lower() in c.lower():
                            return i
                    return None
                i_act, i_prev, i_cons = col("Actual"), col("Previous"), col("Consensus")
                rows = []
                for tr in t.find_all("tr"):
                    cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                    if len(cells) >= 5 and "Fed Interest Rate Decision" in " ".join(cells):
                        def get(i):
                            return pct_of(cells[i]) if i is not None and i < len(cells) else None
                        rows.append({
                            "date": cells[0],
                            "actual": get(i_act),
                            "prev": get(i_prev),
                            "consensus": get(i_cons),
                        })
                out["fomc_calendar"] = rows
                actuals = [x for x in rows if x["actual"] is not None]
                today = datetime.now().strftime("%Y-%m-%d")
                upcoming = [x for x in rows
                            if x["actual"] is None and x["date"] >= today]
                if actuals:
                    out["fed_rate"] = actuals[-1]["actual"]
                    out["fed_last_date"] = actuals[-1]["date"]
                if upcoming:
                    out["next_fomc"] = upcoming[0]
                    out["fed_next_consensus"] = upcoming[0]["consensus"]
                break
        # rate saat ini dari tabel ringkasan (baris pertama: Actual/Prev/High/Low)
        if "fed_rate" not in out:
            for t in soup.find_all("table"):
                cells_all = t.get_text(" ", strip=True)
                if "Highest" in cells_all and "Lowest" in cells_all:
                    for tr in t.find_all("tr")[1:2]:
                        cells = [c.get_text(" ", strip=True)
                                 for c in tr.find_all(["td", "th"])]
                        v = pct_of(cells[0]) if cells else None
                        if v:
                            out["fed_rate"] = v
                    break
    except Exception as e:
        out["error"] = str(e)[:200]

    # forecast kuartalan AS
    try:
        r2 = requests.get("https://tradingeconomics.com/united-states/forecast",
                          headers=UA, timeout=40)
        soup2 = BeautifulSoup(r2.text, "lxml")
        for t in soup2.find_all("table"):
            ttxt = t.get_text("|", strip=True)
            if "Interest Rate" in ttxt and ("Q" in ttxt or "26" in ttxt):
                for tr in t.find_all("tr"):
                    cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                    if cells and cells[0].startswith("Interest Rate") and len(cells) >= 3:
                        vals = [float(x) for x in cells[1:] if re.match(r"^[\d.,]+$", x)]
                        out["fed_forecast"] = {"values": vals}
                        hdr = t.find("tr")
                        if hdr:
                            out["fed_forecast"]["labels"] = [
                                c.get_text(strip=True) for c in hdr.find_all(["th", "td"])]
                        break
                break
    except Exception as e:
        out["forecast_error"] = str(e)[:200]

    # --- fallback: dataset statis kalau TE tidak lengkap ---
    try:
        hist = load_hist()
        if out.get("fed_rate") is None and hist.get("fed_decisions"):
            last = hist["fed_decisions"][-1]
            out["fed_rate"] = last["upper"]
            out["fed_last_date"] = last["date"]
        if not out.get("next_fomc") and hist.get("fomc_upcoming"):
            nxt = hist["fomc_upcoming"][0]
            out["next_fomc"] = {"date": nxt["date"], "actual": None,
                                "prev": out.get("fed_rate"), "consensus": None}
    except Exception:
        pass
    return out

def leg_fed_consensus(fed):
    """Kaki konsensus buat FOMC: ekspektasi ekonom + tilt forecast kuartalan."""
    notes = []
    rate = fed.get("fed_rate")
    cons = fed.get("fed_next_consensus")
    if cons is None or rate is None:
        notes.append("Konsensus FOMC tidak tersedia di TE untuk rapat terdekat")
        cons = None
    mu = 0.0
    if cons is not None:
        mu = (cons - rate) * 100
        notes.append(f"Konsensus FOMC: {cons:.2f}% vs FF rate {rate:.2f}% "
                     f"-> ekspektasi {mu:+.0f} bps")
    P = grid_probs(mu, EVT_CONFIG["sigma_fed_consensus_bps"]) if cons is not None \
        else {m: 1/3 for m in EVT_CONFIG["moves_bps"]}

    rf = fed.get("fed_forecast", {})
    meeting_date = (fed.get("next_fomc") or {}).get("date")
    qk = quarter_key(meeting_date)
    nxt_q = None
    vals, labels = rf.get("values"), rf.get("labels")
    if vals and labels and qk:
        for i, lab in enumerate(labels):
            if lab.strip().lower() == qk.lower():
                j = i - 1
                if 0 <= j < len(vals):
                    nxt_q = vals[j]
                break
        if nxt_q is None and len(vals) > 1:
            nxt_q = vals[1]
    elif vals and len(vals) > 1:
        nxt_q = vals[1]
    if nxt_q:
        tilt = (nxt_q - rate) * 100
        w = 0.4
        P2 = grid_probs(tilt, EVT_CONFIG["sigma_fed_consensus_bps"] * 1.5)
        P = {m: (1-w)*P[m] + w*P2[m] for m in EVT_CONFIG["moves_bps"]}
        notes.append(f"Forecast kuartal rapat (TE): {nxt_q:.2f}% -> tilt {tilt:+.0f} bps (bobot {w})")
    return P, notes

def quarter_key(date_str):
    if not date_str:
        return None
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"Q{(d.month - 1)//3 + 1}/{str(d.year)[2:]}"
    except Exception:
        return None

def leg_fed_macro(yf):
    """Kaki makro buat The Fed: arah inflasi AS & pasar tenaga kerja susah diambil
    gratis, jadi pakai arah US10Y + DXY proxy. Ringan saja (sigma lebar)."""
    notes = []
    mu = 0.0
    t = yf.get("US10Y")
    if t and t.get("chg_3m_pct") is not None:
        mu += t["chg_3m_pct"] * 12
        notes.append(f"US10Y 3bln {t['chg_3m_pct']:+.2f}% -> mu {mu:+.0f} bps")
    dxy = yf.get("DXY")
    if dxy and dxy.get("chg_3m_pct") is not None:
        mu += dxy["chg_3m_pct"] * 8
        notes.append(f"DXY 3bln {dxy['chg_3m_pct']:+.2f}% -> mu {mu:+.0f} bps")
    P = grid_probs(mu, EVT_CONFIG["sigma_fed_macro_bps"])
    return P, notes

def model_fed(fed, yf):
    """Probabilitas keputusan FOMC berikutnya."""
    w = EVT_CONFIG["weights_fed"]
    p_cons, n1 = leg_fed_consensus(fed)
    p_mac, n2 = leg_fed_macro(yf)
    final = {m: w["consensus"]*p_cons[m] + w["macro"]*p_mac[m]
             for m in EVT_CONFIG["moves_bps"]}
    s = sum(final.values())
    final = {m: v/s for m, v in final.items()}
    return {"P": final, "legs": {"consensus": (p_cons, n1), "macro": (p_mac, n2)},
            "mode": max(final, key=final.get)}

# ============================== INFLASI ID ==============================
def fetch_inflation_te():
    out = {}
    try:
        r = requests.get("https://id.tradingeconomics.com/indonesia/inflation-cpi",
                         headers=UA, timeout=40)
        soup = BeautifulSoup(r.text, "lxml")
        for t in soup.find_all("table"):
            txt = t.get_text(" ", strip=True)
            if "Tingkat Inflasi YoY" in txt and "Realisasi" in txt:
                rows = []
                for tr in t.find_all("tr"):
                    cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                    if len(cells) >= 5 and "Tingkat Inflasi YoY" in " ".join(cells):
                        # kolom bisa 6 (tanpa periode ref) atau 7 (dengan periode ref)
                        # 7 kolom: date|gmt|event|refperiod|actual|prev|consensus
                        if len(cells) >= 7:
                            i_act, i_prev, i_cons = 4, 5, 6
                        else:
                            i_act, i_prev, i_cons = 3, 4, 5
                        rows.append({
                            "date": cells[0],
                            "ref": cells[i_act-1] if i_act >= 1 else "",
                            "actual": pct_of(cells[i_act]),
                            "prev": pct_of(cells[i_prev]),
                            "consensus": pct_of(cells[i_cons]) if len(cells) > i_cons else None,
                        })
                out["inflation_calendar"] = rows
                actuals = [x for x in rows if x["actual"] is not None]
                upcoming = [x for x in rows if x["actual"] is None]
                if actuals:
                    out["last_release"] = actuals[-1]
                if upcoming:
                    out["next_release"] = upcoming[0]
                break
        # history dari kalender (yang punya actual)
        if "inflation_calendar" in out:
            out["recent"] = [x["actual"] for x in out["inflation_calendar"]
                             if x["actual"] is not None][-6:]
    except Exception as e:
        out["error"] = str(e)[:200]
    return out

def model_inflation(inf_te, hist=None):
    """
    Probabilitas untuk rilis inflasi berikutnya:
      - titik perkiraan = blend momentum 3 bln + mean-reversion ke tengah band
      - P(dalam band [1.5-3.5]), P(di atas band), P(di bawah band)
    """
    notes = []
    hist = hist or load_hist()
    series = [x["yoy"] for x in hist.get("inflation_id_history", [])]

    recent = inf_te.get("recent") or series[-6:]
    if len(recent) >= 3:
        momentum = (recent[-1] - recent[-4]) / 3
    else:
        momentum = 0.0
    center = EVT_CONFIG["target_center"]
    last = recent[-1] if recent else center
    point = last + EVT_CONFIG["momentum_weight"] * momentum \
        + 0.2 * (center - last)
    notes.append(f"Rilis terakhir {last:.2f}% | momentum 3 bln {momentum:+.2f} "
                 f"poin/bln | perkiraan titik {point:.2f}%")

    cons = (inf_te.get("next_release") or {}).get("consensus")
    if cons is not None:
        point = 0.5*point + 0.5*cons
        notes.append(f"Konsensus TE: {cons:.2f}% (blend 50/50)")

    sigma = EVT_CONFIG["sigma_inflation_pct"]
    lo, hi = EVT_CONFIG["target_band"]
    # P(X dalam band) via CDF normal (approx erfc-free)
    def cdf(x):
        return 0.5 * (1 + math.erf((x - point) / (sigma * math.sqrt(2))))
    p_in = cdf(hi) - cdf(lo)
    p_hi = 1 - cdf(hi)
    p_lo = cdf(lo)
    notes.append(f"P(dalam band {lo}-{hi}%) = {p_in*100:.1f}%")
    return {"point_forecast": point,
            "P": {"below_band": p_lo, "in_band": p_in, "above_band": p_hi},
            "band": (lo, hi), "notes": notes,
            "next_release": inf_te.get("next_release"),
            "last_release": inf_te.get("last_release")}

# ============================== BACKTEST MAKRO HISTORIS ==============================
def backtest_macro_history(yf_hist=None):
    """
    Rekonstruksi sinyal makro pada tiap RDG historis (2016-2026) dan
    bandingkan prediksi arah vs keputusan aktual.

    Data: historical_rates.json + USDIDR/US10Y harian dari yfinance +
    history inflasi dari dataset. Kaki konsensus TIDAK bisa diuji
    (tidak ada arsip konsensus gratis) -> ini backtest kaki makro saja.
    """
    hist = load_hist()
    decisions = hist["bi_decisions"]
    infl = {x["month"]: x["yoy"] for x in hist.get("inflation_id_history", [])}
    lo, hi = EVT_CONFIG["target_band"]

    if yf_hist is None:
        yf_hist = fetch_yf_history()
    usdidr = yf_hist.get("USDIDR")
    ust = yf_hist.get("US10Y")

    out = []
    for d in decisions:
        date = d["date"]
        move_actual = round((d["rate"] - d["prev"]) * 100)
        month = date[:7]
        mu = 0.0
        detail = {}
        # inflasi bulan terdekat <= tanggal rapat
        inf_val = None
        for m in sorted(infl):
            if m <= month:
                inf_val = infl[m]
        if inf_val is not None:
            pos = min(max((inf_val - lo) / (hi - lo), 0), 1)
            mu += (pos - 0.5) * 2 * EVT_CONFIG["macro_bps_per_pct_inflation"]
            detail["inflation"] = inf_val
        # momentum USDIDR 3 bln & US10Y 3 bln di tanggal rapat
        for series, key, w in [(usdidr, "idr_3m", EVT_CONFIG["macro_bps_per_pct_idr_3m"]),
                               (ust, "ust_3m", EVT_CONFIG["macro_bps_per_pct_ust_3m"])]:
            if series is None or len(series) == 0:
                continue
            mask = series.index <= pd_timestamp(date)
            sub = series[mask]
            if len(sub) > 65:
                chg = (float(sub.iloc[-1]) / float(sub.iloc[-64]) - 1) * 100
                mu += chg * w
                detail[key] = round(chg, 2)
        P = grid_probs(mu, EVT_CONFIG["sigma_macro_bps"])
        pred = max(P, key=P.get)
        exact = (pred == move_actual)
        direction = (pred == 0 and move_actual == 0) or \
                    (pred * move_actual > 0) or \
                    (abs(move_actual) <= 0 and pred == 0)
        out.append({
            "date": date, "rate_after": d["rate"], "move_actual": move_actual,
            "pred_move": pred, "exact_hit": exact, "direction_hit": direction,
            "mu_bps": round(mu, 1), "detail": detail,
            "P": {str(k): round(v, 3) for k, v in P.items()},
        })

    n = len(out)
    n_exact = sum(x["exact_hit"] for x in out)
    n_dir = sum(x["direction_hit"] for x in out)
    n_hold = sum(1 for x in out if x["move_actual"] == 0)
    return {
        "meetings": out,
        "summary": {
            "n_meetings": n,
            "exact_hit_rate": round(n_exact/n, 3) if n else 0,
            "direction_hit_rate": round(n_dir/n, 3) if n else 0,
            "naive_hold_hit_rate": round(n_hold/n, 3) if n else 0,
            "n_actual_hold": n_hold, "n_actual_cut": sum(1 for x in out if x["move_actual"] < 0),
            "n_actual_hike": sum(1 for x in out if x["move_actual"] > 0),
        },
    }

def backtest_full_model(yf_hist=None):
    """
    Backtest model gabungan 3 kaki untuk tiap RDG historis.
    Kaki konsensus & pasar obligasi tidak bisa direkonstruksi (tidak ada arsip
    gratis) -> diasumsikan netral (mu=0). Kaki makro direkonstruksi dari
    USDIDR/US10Y/inflasi historis. Baseline pembanding: tebakan 'selalu hold'.
    """
    import bi_rdg_calc as calc
    hist = load_hist()
    decisions = hist["bi_decisions"]
    infl = {x["month"]: x["yoy"] for x in hist.get("inflation_id_history", [])}
    lo, hi = EVT_CONFIG["target_band"]

    if yf_hist is None:
        yf_hist = fetch_yf_history()
    usdidr = yf_hist.get("USDIDR")
    ust = yf_hist.get("US10Y")

    out = []
    for d in decisions:
        date = d["date"]
        move_actual = round((d["rate"] - d["prev"]) * 100)
        month = date[:7]
        mu_mac = 0.0
        inf_val = None
        for m in sorted(infl):
            if m <= month:
                inf_val = infl[m]
        if inf_val is not None:
            pos = min(max((inf_val - lo) / (hi - lo), 0), 1)
            mu_mac += (pos - 0.5) * 2 * calc.CONFIG["macro_bps_per_pct_inflation"]
        for series, w in [(usdidr, calc.CONFIG["macro_bps_per_pct_idr_3m"]),
                          (ust, calc.CONFIG["macro_bps_per_pct_ust_3m"])]:
            if series is None or len(series) == 0:
                continue
            sub = series[series.index <= pd_timestamp(date)]
            if len(sub) > 65:
                chg = (float(sub.iloc[-1]) / float(sub.iloc[-64]) - 1) * 100
                mu_mac += chg * w
        p_cons = calc.grid_probs(0, calc.CONFIG["sigma_consensus_bps"])
        p_mkt = calc.grid_probs(0, calc.CONFIG["sigma_market_bps"])
        p_mac = calc.grid_probs(mu_mac, calc.CONFIG["sigma_macro_bps"])
        legs = {"consensus": (p_cons, []), "market": (p_mkt, []),
                "macro": (p_mac, [])}
        final = calc.combine(legs)
        pred = max(final, key=final.get)
        out.append({
            "date": date, "move_actual": move_actual, "pred_move": pred,
            "mu_macro_bps": round(mu_mac, 1),
            "exact_hit": pred == move_actual,
            "P": {str(k): round(v, 3) for k, v in final.items()},
        })

    n = len(out)
    n_exact = sum(x["exact_hit"] for x in out)
    n_hold = sum(1 for x in out if x["move_actual"] == 0)
    return {
        "meetings": out,
        "summary": {
            "n_meetings": n,
            "model_hit_rate": round(n_exact/n, 3) if n else 0,
            "naive_hold_hit_rate": round(n_hold/n, 3) if n else 0,
            "note": "kaki konsensus & pasar obligasi diasumsikan netral (tidak ada arsip gratis); model diuji pada kontribusi kaki makro + prior hold",
        },
    }

def pd_timestamp(s):
    import pandas as pd
    return pd.Timestamp(s)

def fetch_yf_history():
    """USDIDR + US10Y harian (max) untuk rekonstruksi sinyal historis."""
    out = {}
    try:
        import yfinance as yf
        for name, tk in [("USDIDR", "USDIDR=X"), ("US10Y", "^TNX")]:
            try:
                h = yf.Ticker(tk).history(period="max")
                if h is not None and len(h) > 100:
                    close = h["Close"].dropna()
                    if close.index.tz is not None:
                        close.index = close.index.tz_localize(None)
                    out[name] = close
            except Exception as e:
                out[name + "_error"] = str(e)[:150]
    except Exception as e:
        out["error"] = str(e)[:200]
    return out

# ============================== MAIN (test) ==============================
if __name__ == "__main__":
    print(">> Fetch Fed...", flush=True)
    fed = fetch_fed()
    print(json.dumps({k: v for k, v in fed.items() if k != "fomc_calendar"},
                     ensure_ascii=False, indent=1)[:800])

    print("\n>> Fetch yf (makro utk Fed + history utk backtest)...", flush=True)
    import bi_rdg_calc as calc
    yf_now = calc.fetch_yf()

    print("\n>> Model The Fed:", flush=True)
    m_fed = model_fed(fed, yf_now)
    for move, p in sorted(m_fed["P"].items()):
        print(f"   {move:+d} bps: {p*100:.1f}%")
    print("   mode:", m_fed["mode"])

    print("\n>> Fetch inflasi TE...", flush=True)
    inf_te = fetch_inflation_te()
    m_inf = model_inflation(inf_te)
    print(f"   point forecast: {m_inf['point_forecast']:.2f}%")
    for k, v in m_inf["P"].items():
        print(f"   P({k}) = {v*100:.1f}%")

    print("\n>> Backtest makro historis (ini agak lama)...", flush=True)
    bt = backtest_macro_history()
    s = bt["summary"]
    print(json.dumps(s, indent=1))
    with open(os.path.join(HERE, "data", "backtest_macro_history.json"), "w",
              encoding="utf-8") as f:
        json.dump(bt, f, ensure_ascii=False, indent=1)
    print("-> disimpan ke data/backtest_macro_history.json")
