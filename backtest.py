# -*- coding: utf-8 -*-
"""
BACKTEST MODULE untuk BI Rate Radar.

Cara pakai:
  python backtest.py log      -> simpan prediksi RDG berikutnya ke log (panggil sebelum event)
  python backtest.py snapshot -> catat snapshot probabilitas harian (time series untuk Brier score)
  python backtest.py update   -> ambil hasil aktual dari TE, evaluasi vs log, tulis hasil
  python backtest.py report   -> cetak ringkasan akurasi: hit rate, Brier score, log-loss

Prinsip backtest yang jujur: prediksi HARUS dicatat sebelum hasil keluar.
File log:
  data/predictions_log.json    (append-only: semua prediksi yang pernah dibuat)
  data/prediction_history.json (snapshot harian: evolusi probabilitas tiap event)
  data/backtest_results.json   (hasil evaluasi tiap event yang sudah keluar)
"""
import json, math, os, sys
from datetime import datetime

import bi_rdg_calc as calc

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

def _load(name):
    p = os.path.join(DATA, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return []

def _save(name, obj):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------- run model
def _run_model():
    """Fetch semua sumber + hitung kaki + gabung (dengan metadata renormalisasi)."""
    te = calc.fetch_te()
    phei = calc.fetch_phei()
    yf = calc.fetch_yf()
    legs = {
        "consensus": calc.leg_consensus(te),
        "market": calc.leg_market(phei, te),
        "macro": calc.leg_macro(te, yf),
    }
    final, meta = calc.combine(legs, detail=True)
    return te, legs, final, meta

# ---------------------------------------------------------------- log prediksi
def log_prediction():
    """Hitung model SEKARANG dan catat prediksinya untuk RDG terdekat."""
    te, legs, final, meta = _run_model()

    nxt = te.get("next_meeting") or {}
    entry = {
        "meeting_date": nxt.get("date"),
        "predicted_at": datetime.now().isoformat(timespec="seconds"),
        "bi_rate_before": te.get("bi_rate"),
        "consensus": te.get("next_consensus"),
        "inflation": te.get("inflation"),
        "final_probability": {str(m): round(v, 4) for m, v in final.items()},
        "most_likely_move_bps": max(final, key=final.get),
        "legs": {k: {str(m): round(v, 4) for m, v in p.items()}
                 for k, (p, _n) in legs.items()},
        "weights": calc.CONFIG["weights"],
        "weights_used": meta["weights_used"],
        "dropped_legs": meta["dropped"],
        "status": "pending",  # pending | evaluated
    }

    log = _load("predictions_log.json")
    existing = {e["meeting_date"]: e for e in log}
    if entry["meeting_date"] in existing and existing[entry["meeting_date"]]["status"] == "pending":
        print(f"Sudah ada prediksi pending untuk {entry['meeting_date']}, tidak ditimpa.")
        return existing[entry["meeting_date"]]
    log.append(entry)
    _save("predictions_log.json", log)
    print(f"Prediksi dicatat untuk RDG {entry['meeting_date']}:")
    print(f"  P(cut)={entry['final_probability']['-25']:.1%} "
          f"P(hold)={entry['final_probability']['0']:.1%} "
          f"P(hike)={entry['final_probability']['25']:.1%} "
          f"-> paling mungkin {entry['most_likely_move_bps']:+d} bps")
    return entry

# ---------------------------------------------------------------- snapshot harian
def snapshot():
    """Catat snapshot probabilitas hari ini untuk RDG terdekat ke time series.

    Beda dengan log_prediction: snapshot BOLEH dipanggil berkali-kali (tiap hari)
    untuk event yang sama, supaya kita bisa lihat evolusi probabilitas dan
    mengukur apakah prediksi yang makin dekat ke hari H makin tajam.
    """
    te, legs, final, meta = _run_model()
    nxt = te.get("next_meeting") or {}
    date = nxt.get("date")
    if not date:
        print("RDG berikutnya tidak ditemukan di Trading Economics.")
        return None

    hist = _load("prediction_history.json")
    today = datetime.now().date().isoformat()
    entry = {
        "meeting_date": date,
        "observed_on": today,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "days_to_meeting": _days_between(today, date),
        "bi_rate": te.get("bi_rate"),
        "consensus": te.get("next_consensus"),
        "inflation": te.get("inflation"),
        "final_probability": {str(m): round(v, 4) for m, v in final.items()},
        "most_likely_move_bps": max(final, key=final.get),
        "weights_used": meta["weights_used"],
        "dropped_legs": meta["dropped"],
        "legs": {k: {str(m): round(v, 4) for m, v in p.items()}
                 for k, (p, _n) in legs.items()},
    }
    # hindari duplikat snapshot di hari yang sama untuk event yang sama
    hist = [h for h in hist
            if not (h.get("meeting_date") == date and h.get("observed_on") == today)]
    hist.append(entry)
    _save("prediction_history.json", hist)

    n_today = sum(1 for h in hist if h.get("meeting_date") == date)
    print(f"Snapshot dicatat untuk RDG {date} ({entry['days_to_meeting']} hari lagi).")
    print(f"  P(cut)={entry['final_probability']['-25']:.1%} "
          f"P(hold)={entry['final_probability']['0']:.1%} "
          f"P(hike)={entry['final_probability']['25']:.1%}")
    print(f"  Total snapshot untuk event ini: {n_today}")
    return entry

def _days_between(d1, d2):
    from datetime import date as _date
    try:
        a = _date.fromisoformat(d1)
        b = _date.fromisoformat(d2)
        return (b - a).days
    except Exception:
        return None

# ---------------------------------------------------------------- metrik skoring
def brier(fp, actual_move):
    """Brier score 3-kategori: sum((P_i - 1[i=actual])^2). Range 0 (sempurna) - 2."""
    if actual_move not in calc.MOVES:
        return None
    return round(sum((fp[str(m)] - (1 if m == actual_move else 0)) ** 2
                     for m in calc.MOVES), 4)

def log_loss(fp, actual_move, eps=1e-6):
    """Log loss: -log(P(actual)). Makin kecil makin bagus."""
    if actual_move not in calc.MOVES:
        return None
    p = max(fp.get(str(actual_move), 0), eps)
    return round(-math.log(p), 4)

# ---------------------------------------------------------------- laporan
def report():
    """Cetak ringkasan akurasi dari semua prediksi yang sudah dievaluasi."""
    results = _load("backtest_results.json")
    evaluated = [r for r in results if r.get("status") == "evaluated"]
    if not evaluated:
        print("Belum ada prediksi yang terevaluasi. Jalankan: python backtest.py update")
        return

    live = [r for r in evaluated
            if r.get("source") != "historical_consensus_leg_only"]
    hist = [r for r in evaluated
            if r.get("source") == "historical_consensus_leg_only"]

    print("=" * 55)
    print("LAPORAN AKURASI BI RATE RADAR")
    print("=" * 55)
    for label, group in [("LIVE (model penuh)", live),
                         ("HISTORIS (kaki konsensus saja)", hist)]:
        if not group:
            continue
        n = len(group)
        hits = sum(1 for r in group if r.get("hit"))
        briers = [r["brier_score"] for r in group
                  if r.get("brier_score") is not None]
        lls = [log_loss(r["final_probability"], r["actual_move_bps"])
               for r in group if r.get("final_probability")]
        print(f"\n[{label}] n={n}")
        print(f"  Hit rate : {hits}/{n} ({hits/n:.0%})")
        if briers:
            print(f"  Brier    : {sum(briers)/len(briers):.4f} "
                  f"(baseline tebak-hold ~0.44; uniform 0.667)")
        if lls:
            print(f"  Log-loss : {sum(lls)/len(lls):.4f}")
        print("  Detail:")
        for r in sorted(group, key=lambda x: x["meeting_date"]):
            tag = "HIT " if r.get("hit") else "MISS"
            print(f"    {r['meeting_date']} [{tag}] "
                  f"pred {r['most_likely_move_bps']:+d} / aktual "
                  f"{r['actual_move_bps']:+d} | P(aktual)="
                  f"{r.get('prob_assigned_to_actual')}")

    hist_snaps = _load("prediction_history.json")
    if hist_snaps:
        print(f"\nSnapshot harian tersimpan: {len(hist_snaps)} "
              f"(untuk {len({h['meeting_date'] for h in hist_snaps})} event)")
    print()

# ---------------------------------------------------------------- evaluasi
def _evaluate_entry(entry, actual_rate, prev_rate):
    actual_move = round((actual_rate - prev_rate) * 100)
    pred_mode = entry["most_likely_move_bps"]
    fp = entry["final_probability"]
    hit = pred_mode == actual_move
    p_actual = fp.get(str(actual_move))
    entry.update({
        "status": "evaluated",
        "actual_rate": actual_rate,
        "actual_move_bps": actual_move,
        "hit": hit,
        "prob_assigned_to_actual": p_actual,
        "brier_score": brier(fp, actual_move),
        "log_loss": log_loss(fp, actual_move),
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
    })
    return entry

def update():
    """Ambil hasil aktual dari TE; evaluasi semua prediksi pending yang udah lewat."""
    te = calc.fetch_te()
    rows = {r["date"]: r for r in te.get("rdg_history", [])}

    log = _load("predictions_log.json")
    results = _load("backtest_results.json")
    evaluated_dates = {r["meeting_date"] for r in results}

    n_new = n_pending = 0
    for entry in log:
        d = entry["meeting_date"]
        if d in evaluated_dates or entry.get("status") == "evaluated":
            continue
        row = rows.get(d)
        if not row or row["actual"] is None:
            n_pending += 1
            continue
        prev = row["prev"] if row["prev"] is not None else entry.get("bi_rate_before")
        ev = _evaluate_entry(entry, row["actual"], prev)
        results.append(ev)
        n_new += 1

    # evaluasi juga RDG historis TE yang punya konsensus (hanya kaki konsensus)
    hist_dates = {r["meeting_date"] for r in results}
    hist_extra = []
    for r in te.get("rdg_history", []):
        if r["actual"] is None or r["prev"] is None or r["consensus"] is None:
            continue
        if r["date"] in hist_dates:
            continue
        mu = (r["consensus"] - r["prev"]) * 100
        P = calc.grid_probs(mu, calc.CONFIG["sigma_consensus_bps"])
        actual_move = round((r["actual"] - r["prev"]) * 100)
        pred_mode = max(P, key=P.get)
        fp = {str(m): round(v, 4) for m, v in P.items()}
        hist_extra.append({
            "meeting_date": r["date"],
            "source": "historical_consensus_leg_only",
            "bi_rate_before": r["prev"],
            "consensus": r["consensus"],
            "final_probability": fp,
            "most_likely_move_bps": pred_mode,
            "status": "evaluated",
            "actual_rate": r["actual"],
            "actual_move_bps": actual_move,
            "hit": pred_mode == actual_move,
            "prob_assigned_to_actual": round(P.get(actual_move, 0), 4),
            "brier_score": brier(fp, actual_move),
            "log_loss": log_loss(fp, actual_move),
            "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        })
    results.extend(hist_extra)

    _save("predictions_log.json", log)
    _save("backtest_results.json", results)

    print(f"=== BACKTEST SUMMARY ===")
    print(f"Baru dievaluasi: {n_new} | Menunggu hasil: {n_pending} | "
          f"Historis tambahan: {len(hist_extra)}")
    for r in results:
        tag = "✅ HIT" if r.get("hit") else "❌ MISS"
        print(f"  {r['meeting_date']}: prediksi {r['most_likely_move_bps']:+d} bps, "
              f"aktual {r['actual_move_bps']:+d} bps ({r['actual_rate']}%) {tag} "
              f"[P(aktual)={r.get('prob_assigned_to_actual')}]")
    if n_pending:
        print("⏳ Hasil aktual belum tersedia di Trading Economics. Coba lagi nanti.")
    return results

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "log"
    if cmd == "log":
        log_prediction()
    elif cmd == "snapshot":
        snapshot()
    elif cmd == "update":
        update()
    elif cmd == "report":
        report()
    else:
        print("pakai: python backtest.py [log|snapshot|update|report]")
