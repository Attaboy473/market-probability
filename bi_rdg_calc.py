# -*- coding: utf-8 -*-
"""
BI RATE RADAR - Kalkulator probabilitas keputusan RDG Bank Indonesia
"Pengganti Polymarket" berbasis: konsensus ekonom, pasar obligasi, data makro.

Sumber data:
  1. Trading Economics  -> BI rate, kalender RDG, konsensus, inflasi, forecast
  2. PHEI (phei.co.id)  -> yield curve SUN, SBN benchmark, indeks INDOBeX/ICBI
  3. yfinance           -> USDIDR, IHSG, US Treasury 10Y (konteks eksternal)

Model 3 kaki (bobot bisa diubah di CONFIG):
  P_final(move) = w_cons*P_consensus + w_mkt*P_market + w_macro*P_macro
  move in {-25, 0, +25} bps (cut / hold / hike)
"""
import json, math, re, os, time
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ============================== CONFIG ==============================
CONFIG = {
    "weights": {"consensus": 0.45, "market": 0.40, "macro": 0.15},
    # konsensus ekonom
    "sigma_consensus_bps": 20,      # sebaran tipikal survei ekonom
    "forecast_tilt_weight": 0.25,   # seberapa besar forecast kuartalan nambah tilt
    # pasar obligasi
    "baseline_spread_front_bps": 75,  # spread normal yield ~1-1,5 bln vs BI rate
    "market_damping": 0.5,            # redam sinyal level (proxy noisy)
    "momentum_weight": 0.5,           # bobot perubahan yield pendek harian
    "sigma_market_bps": 45,
    # makro
    "target_band": (1.5, 3.5),      # target inflasi BI (pct)
    "macro_bps_per_pct_inflation": 25,
    "macro_bps_per_pct_idr_3m": 15,
    "macro_bps_per_pct_ust_3m": 8,
    "sigma_macro_bps": 60,
}

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "id-ID,id;q=0.9,en;q=0.8"}

MOVES = [-25, 0, 25]  # bps: cut, hold, hike

# ============================== HTTP RETRY ==============================
def fetch_with_retry(url, retries=3, backoff=2.0, **kw):
    """requests.get dengan retry + exponential backoff. Raise kalau semua gagal."""
    kw.setdefault("headers", UA)
    kw.setdefault("timeout", 40)
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, **kw)
            if r.status_code == 200:
                return r
            last = Exception(f"HTTP {r.status_code} dari {url}")
        except Exception as e:
            last = e
        if i < retries - 1:
            time.sleep(backoff * (i + 1))
    raise last

def idnum(s):
    """Parse angka format Indonesia: '6,5334' -> 6.5334"""
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

# ============================== DATA: TRADING ECONOMICS ==============================
def fetch_te():
    out = {}
    r = fetch_with_retry("https://id.tradingeconomics.com/indonesia/interest-rate")
    soup = BeautifulSoup(r.text, "lxml")

    # --- kalender keputusan suku bunga ---
    # struktur baris: [date, gmt, ref_name, ref_period, actual, prev, consensus]
    rows = []
    for t in soup.find_all("table"):
        ttext = t.get_text(" ", strip=True)
        if "Keputusan Suku Bunga" in ttext and "Realisasi" in ttext:
            for tr in t.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                if len(cells) >= 7 and "Keputusan Suku Bunga" in cells[2]:
                    rows.append({
                        "date": cells[0],
                        "actual": pct_of(cells[4]),
                        "prev": pct_of(cells[5]),
                        "consensus": pct_of(cells[6]),
                    })
    out["rdg_history"] = rows

    actuals = [x for x in rows if x["actual"] is not None]
    upcoming = [x for x in rows if x["actual"] is None]
    out["bi_rate"] = actuals[-1]["actual"] if actuals else None
    out["next_meeting"] = upcoming[0] if upcoming else None
    out["next_consensus"] = upcoming[0]["consensus"] if upcoming else None

    # --- inflasi ---
    try:
        r3 = fetch_with_retry("https://id.tradingeconomics.com/indonesia/inflation-cpi")
        s3 = BeautifulSoup(r3.text, "lxml")
        mm = s3.find("meta", id="metaDesc")
        if mm:
            content = mm.get("content", "")
            hit = re.search(r"(?:menjadi|tercatat sebesar|sebesar)\s+([\d.,]+) persen", content)
            if hit:
                out["inflation"] = idnum(hit.group(1))
                out["inflation_meta"] = content[:300]
    except Exception as e:
        out["inflation_error"] = str(e)

    # --- forecast kuartalan ---
    try:
        r2 = fetch_with_retry("https://id.tradingeconomics.com/indonesia/forecast")
        soup2 = BeautifulSoup(r2.text, "lxml")
        for t in soup2.find_all("table"):
            ttext = t.get_text("|", strip=True)
            if "Tingkat Bunga" in ttext and ("Q" in ttext or "26" in ttext):
                for tr in t.find_all("tr"):
                    cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                    if cells and cells[0] == "Tingkat Bunga" and len(cells) >= 3:
                        vals = [float(x) for x in cells[1:] if re.match(r"^[\d.,]+$", x)]
                        out["rate_forecast"] = {"values": vals}
                        # cari label kuartal dari header
                        hdr = t.find("tr")
                        if hdr:
                            out["rate_forecast"]["labels"] = [
                                c.get_text(strip=True) for c in hdr.find_all(["th", "td"])]
                        break
    except Exception as e:
        out["forecast_error"] = str(e)

    return out

# ============================== DATA: PHEI ==============================
def fetch_phei():
    S = requests.Session(); S.headers.update(UA)
    out = {}
    r = fetch_with_retry("https://www.phei.co.id/Data/HPW-dan-Imbal-Hasil")
    soup = BeautifulSoup(r.text, "lxml")

    curve_today, curve_yest = {}, {}
    for t in soup.find_all("table"):
        header = t.get_text(" ", strip=True)
        if "Tenor" in header and "Today" in header and "Yesterday" in header \
           and "IGS" not in header[:header.find("Today")+40]:
            for tr in t.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
                if len(cells) >= 3:
                    try:
                        tenor = idnum(cells[0])
                        curve_today[tenor] = idnum(cells[1])
                        curve_yest[tenor] = idnum(cells[2])
                    except ValueError:
                        pass
    out["yield_curve_today"] = curve_today
    out["yield_curve_yesterday"] = curve_yest

    # SBN benchmark (cari baris yang mengandung FR/PBS)
    bench = []
    for tr in soup.find_all("tr"):
        txt = tr.get_text(" ", strip=True)
        m = re.match(r"^(FR|PBS)(\d+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)", txt)
        if m:
            bench.append({
                "series": m.group(1) + m.group(2),
                "ttm": idnum(m.group(3)), "yield_today": idnum(m.group(4)),
                "price_today": idnum(m.group(5)), "yield_yest": idnum(m.group(6)),
                "coupon": idnum(m.group(8)),
            })
    out["sbn_benchmark"] = bench

    # --- indeks ---
    r2 = fetch_with_retry("https://www.phei.co.id/Data/Indeks")
    soup2 = BeautifulSoup(r2.text, "lxml")
    text2 = soup2.get_text(" ", strip=True)
    dm = re.search(r"([A-Z]\w+ , \d+ \w+ \d{4})", text2)
    out["index_date"] = dm.group(1) if dm else None
    idx = {}
    for name, pat in [
        ("ICBI", r"Indonesia Composite Bond Index \(ICBI\)\s+([\d.,]+)\s+([\d.,]+)\s+([-\d.,]+)"),
        ("INDOBeX_EffYield", r"INDOBeX Composite Effective Yield\s+([\d.,]+)\s+([\d.,]+)\s+([-\d.,]+)"),
        ("INDOBeX_Gov_TR", r"INDOBeX Government Total Return\s+([\d.,]+)\s+([\d.,]+)\s+([-\d.,]+)"),
    ]:
        mm = re.search(pat, text2)
        if mm:
            idx[name] = {"prev": idnum(mm.group(1)), "last": idnum(mm.group(2)),
                         "chg": idnum(mm.group(3))}
    out["indexes"] = idx
    return out

# ============================== DATA: YFINANCE ==============================
def fetch_yf():
    out = {}
    try:
        import yfinance as yf
        for name, tk in {"USDIDR": "USDIDR=X", "IHSG": "^JKSE",
                         "US10Y": "^TNX", "DXY": "DX-Y.NYB"}.items():
            try:
                h = yf.Ticker(tk).history(period="3mo")
                if h is not None and len(h) > 5:
                    close = h["Close"].dropna()
                    out[name] = {
                        "last": round(float(close.iloc[-1]), 4),
                        "chg_1w_pct": round((float(close.iloc[-1])/float(close.iloc[-6])-1)*100, 2),
                        "chg_1m_pct": round((float(close.iloc[-1])/float(close.iloc[-23])-1)*100, 2) if len(close) > 23 else None,
                        "chg_3m_pct": round((float(close.iloc[-1])/float(close.iloc[0])-1)*100, 2),
                    }
            except Exception as e:
                out[name + "_error"] = str(e)[:120]
    except Exception as e:
        out["error"] = str(e)
    return out

# ============================== KALENDER EKONOMI (TE, pengganti Investing.com) ==============================
def fetch_te_calendar():
    """Kalender ekonomi Indonesia minggu ini dari Trading Economics
    (pengganti Investing.com yang kena Cloudflare)."""
    events = []
    try:
        r = fetch_with_retry("https://tradingeconomics.com/indonesia/calendar")
        soup = BeautifulSoup(r.text, "lxml")
        for t in soup.find_all("table"):
            rows = t.find_all("tr")
            if not rows or len(rows) < 10:
                continue
            cur_date = None
            for tr in rows:
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                if not cells:
                    continue
                joined = " ".join(cells)
                # baris header tanggal, misal: "Wednesday August 19 2026"
                dm = re.match(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
                              r"(\w+ \d+ \d{4})", joined)
                if dm:
                    cur_date = dm.group(2)
                    continue
                if cur_date and len(cells) >= 4 and cells[0] and not dm:
                    # kolom: Time(TZ) | Time(GMT) | Country? | Event | Actual | Prev | Cons | Forecast
                    events.append({"date": cur_date, "cells": cells})
            if events:
                break
    except Exception:
        pass
    return events

# ============================== MODEL ==============================
def normal_pdf(x, mu, sigma):
    return math.exp(-0.5*((x-mu)/sigma)**2) / (sigma*math.sqrt(2*math.pi))

def grid_probs(mu, sigma):
    raw = [normal_pdf(m, mu, sigma) for m in MOVES]
    s = sum(raw)
    return {m: p/s for m, p in zip(MOVES, raw)}

def quarter_key(date_str):
    """'2026-08-19' -> 'Q3/26' (format label forecast TE)."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"Q{(d.month - 1)//3 + 1}/{str(d.year)[2:]}"
    except Exception:
        return None

def pick_forecast(vals, labels, meeting_date):
    """Ambil nilai forecast untuk kuartal rapat. values[i] <-> labels[i+1]."""
    if not vals:
        return None
    qk = quarter_key(meeting_date)
    if qk and labels:
        for i, lab in enumerate(labels):
            if lab.strip().lower() == qk.lower():
                j = i - 1
                if 0 <= j < len(vals):
                    return vals[j]
    return vals[1] if len(vals) > 1 else vals[0]

def leg_consensus(te):
    """Kaki 1: konsensus ekonom dari kolom Kesepakatan TE + tilt forecast kuartalan."""
    notes = []
    cons, rate = te.get("next_consensus"), te.get("bi_rate")
    if cons is None or rate is None:
        notes.append("Konsensus tidak tersedia -> uniform")
        return {m: 1/3 for m in MOVES}, notes
    mu = (cons - rate) * 100
    P = grid_probs(mu, CONFIG["sigma_consensus_bps"])
    notes.append(f"Konsensus ekonom: {cons:.2f}% vs BI rate {rate:.2f}% -> ekspektasi {mu:+.0f} bps")

    rf = te.get("rate_forecast", {})
    meeting_date = (te.get("next_meeting") or {}).get("date")
    nxt_q = pick_forecast(rf.get("values"), rf.get("labels"), meeting_date)
    if nxt_q:
        tilt = (nxt_q - rate) * 100
        w = CONFIG["forecast_tilt_weight"]
        P2 = grid_probs(tilt, CONFIG["sigma_consensus_bps"] * 2)
        P = {m: (1-w)*P[m] + w*P2[m] for m in MOVES}
        notes.append(f"Forecast kuartal rapat (TE): {nxt_q:.2f}% -> tilt {tilt:+.0f} bps (bobot {w})")
    return P, notes

def leg_market(phei, te):
    """Kaki 2: pasar obligasi. Spread yield tenor sangat pendek vs BI rate."""
    notes = []
    rate = te.get("bi_rate")
    curve = phei.get("yield_curve_today", {})
    if not curve or rate is None:
        notes.append("Yield curve tidak tersedia -> uniform")
        return {m: 1/3 for m in MOVES}, notes

    t_short = min(k for k in curve if k > 0.05)
    y_short = curve[t_short]
    spread_bps = (y_short - rate) * 100
    mu = (spread_bps - CONFIG["baseline_spread_front_bps"]) * CONFIG["market_damping"]
    notes.append(f"Yield {t_short:.1f}Y {y_short:.2f}% | spread {spread_bps:.0f} bps vs "
                 f"baseline {CONFIG['baseline_spread_front_bps']} bps -> bias {mu:+.0f} bps (diredam {CONFIG['market_damping']})")

    yc = phei.get("yield_curve_yesterday", {})
    if t_short in yc:
        dy = (y_short - yc[t_short]) * 100
        mu += dy * CONFIG["momentum_weight"]
        notes.append(f"Momentum yield pendek {dy:+.1f} bps (kemarin -> hari ini)")

    ey = phei.get("indexes", {}).get("INDOBeX_EffYield")
    if ey:
        notes.append(f"INDOBeX effective yield {ey['last']:.4f} (chg {ey['chg']:+.4f})")

    P = grid_probs(mu, CONFIG["sigma_market_bps"])
    return P, notes

def leg_macro(te, yf):
    """Kaki 3: sinyal makro (inflasi vs target band, momentum IDR, arah US10Y)."""
    notes = []
    mu = 0.0
    lo, hi = CONFIG["target_band"]
    inf = te.get("inflation")
    if inf is not None:
        pos = min(max((inf - lo) / (hi - lo), 0), 1)
        mu += (pos - 0.5) * 2 * CONFIG["macro_bps_per_pct_inflation"]
        notes.append(f"Inflasi {inf:.2f}% -> posisi {pos*100:.0f}% di target band "
                     f"[{lo}-{hi}] (mu {mu:+.0f} bps)")
    u = yf.get("USDIDR")
    if u and u.get("chg_3m_pct") is not None:
        mu += u["chg_3m_pct"] * CONFIG["macro_bps_per_pct_idr_3m"]
        notes.append(f"USDIDR 3bln {u['chg_3m_pct']:+.2f}% "
                     f"({'rupiah melemah' if u['chg_3m_pct']>0 else 'rupiah menguat'})")
    t = yf.get("US10Y")
    if t and t.get("chg_3m_pct") is not None:
        mu += t["chg_3m_pct"] * CONFIG["macro_bps_per_pct_ust_3m"]
        notes.append(f"US10Y 3bln {t['chg_3m_pct']:+.2f}%")
    P = grid_probs(mu, CONFIG["sigma_macro_bps"])
    return P, notes

def leg_available(P, eps=0.01):
    """Suatu kaki dianggap 'tersedia' kalau distribusinya TIDAK uniform.
    Fallback uniform (33/33/33) artinya tidak ada data -> jangan ditimbang."""
    return any(abs(v - 1/3) > eps for v in P.values())

def combine(legs, weights=None, detail=False):
    """Gabungkan kaki menjadi probabilitas final.

    Kalau suatu kaki tidak tersedia (uniform fallback), kaki itu DIBUANG dan
    bobot kaki yang tersisa di-renormalisasi -- supaya sinyal yang ada tidak
    di-dilute oleh kaki kosong (sebelumnya 45% bobot konsensus yang kosong
    selalu memipihkan hasil mendekati 33/33/33).
    """
    w = dict(weights or CONFIG["weights"])
    avail = {k: legs[k] for k in legs if leg_available(legs[k][0])}
    dropped = [k for k in legs if k not in avail]

    if not avail:  # semua kaki kosong -> tidak tahu apa-apa
        final = {m: 1/3 for m in MOVES}
        meta = {"weights_used": {k: 0.0 for k in legs}, "dropped": dropped,
                "note": "Semua kaki tidak tersedia -> uniform"}
        return (final, meta) if detail else final

    ws = sum(w[k] for k in avail)
    w_used = {k: w[k] / ws for k in avail}
    final = {m: sum(w_used[k] * avail[k][0][m] for k in avail) for m in MOVES}
    s = sum(final.values())
    final = {m: v / s for m, v in final.items()}
    meta = {"weights_used": {k: round(v, 4) for k, v in w_used.items()},
            "dropped": dropped}
    if dropped:
        meta["note"] = ("Kaki tidak tersedia, bobot di-renormalisasi: "
                        + ", ".join(f"{k} {w_used[k]:.0%}" for k in avail))
    return (final, meta) if detail else final

def backtest(te):
    """Validasi sederhana: untuk RDG historis yang punya konsensus,
    apakah consensus-leg kami nunjuk arah yang benar?"""
    out = []
    for r in te.get("rdg_history", []):
        if r["actual"] is None or r["prev"] is None:
            continue
        move_actual = round((r["actual"] - r["prev"]) * 100)
        if r["consensus"] is not None:
            mu = (r["consensus"] - r["prev"]) * 100
            P = grid_probs(mu, CONFIG["sigma_consensus_bps"])
            pred = max(P, key=P.get)
            out.append({"date": r["date"], "move_actual": move_actual,
                        "consensus_move": round(mu), "pred_leg_consensus": pred,
                        "hit": abs(pred - move_actual) <= 25,
                        "P_consensus_leg": {str(k): round(v, 3) for k, v in P.items()}})
        else:
            out.append({"date": r["date"], "move_actual": move_actual,
                        "consensus_move": None, "note": "no consensus listed"})
    return out

# ============================== MAIN ==============================
def main():
    print(">> Fetching Trading Economics...", flush=True)
    te = fetch_te()
    print(">> Fetching PHEI...", flush=True)
    phei = fetch_phei()
    print(">> Fetching yfinance...", flush=True)
    yf = fetch_yf()
    print(">> Fetching calendar...", flush=True)
    calendar = fetch_te_calendar()

    legs = {
        "consensus": leg_consensus(te),
        "market": leg_market(phei, te),
        "macro": leg_macro(te, yf),
    }
    final, meta = combine(legs, detail=True)
    bt = backtest(te)

    if meta.get("dropped"):
        print("!! Kaki tidak tersedia (di-renormalisasi): " + ", ".join(meta["dropped"]))

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "inputs": {
            "bi_rate": te.get("bi_rate"),
            "inflation": te.get("inflation"),
            "inflation_meta": te.get("inflation_meta"),
            "next_meeting": te.get("next_meeting"),
            "rate_forecast": te.get("rate_forecast"),
            "yield_curve_front": {str(k): v for k, v in
                                  sorted(phei.get("yield_curve_today", {}).items())[:5]},
            "sbn_benchmark": phei.get("sbn_benchmark"),
            "indexes": phei.get("indexes"),
            "index_date": phei.get("index_date"),
            "yfinance": yf,
            "calendar_economic": calendar[:40],
        },
        "legs": {
            k: {"P": {str(m): round(v, 4) for m, v in p.items()}, "notes": n}
            for k, (p, n) in legs.items()
        },
        "weights": CONFIG["weights"],
        "weights_used": meta["weights_used"],
        "dropped_legs": meta["dropped"],
        "final_probability": {str(m): round(v, 4) for m, v in final.items()},
        "most_likely_move_bps": max(final, key=final.get),
        "backtest_consensus_leg": bt,
    }

    os.makedirs("data", exist_ok=True)
    with open(os.path.join("data", "rdg_result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
