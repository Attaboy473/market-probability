# -*- coding: utf-8 -*-
"""
BACKTEST MODULE untuk BI Rate Radar.

Cara pakai:
  python backtest.py log      -> simpan prediksi RDG berikutnya ke log (panggil sebelum event)
  python backtest.py update   -> ambil hasil aktual dari TE, evaluasi vs log, tulis hasil

Prinsip backtest yang jujur: prediksi HARUS dicatat sebelum hasil keluar.
File log:
  data/predictions_log.json   (append-only: semua prediksi yang pernah dibuat)
  data/backtest_results.json  (hasil evaluasi tiap event yang sudah keluar)
"""
import json, os, sys
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

# ---------------------------------------------------------------- log prediksi
def log_prediction():
    """Hitung model SEKARANG dan catat prediksinya untuk RDG terdekat."""
    te = calc.fetch_te()
    phei = calc.fetch_phei()
    yf = calc.fetch_yf()

    legs = {
        "consensus": calc.leg_consensus(te),
        "market": calc.leg_market(phei, te),
        "macro": calc.leg_macro(te, yf),
    }
    final = calc.combine(legs)

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

# ---------------------------------------------------------------- evaluasi
def _evaluate_entry(entry, actual_rate, prev_rate):
    actual_move = round((actual_rate - prev_rate) * 100)
    pred_mode = entry["most_likely_move_bps"]
    fp = entry["final_probability"]
    hit = pred_mode == actual_move
    p_actual = fp.get(str(actual_move))
    # Brier score untuk outcome 3-kategori (semakin kecil semakin bagus)
    brier = None
    if actual_move in (-25, 0, 25):
        brier = round(sum((fp[str(m)] - (1 if m == actual_move else 0)) ** 2
                          for m in calc.MOVES), 4)
    entry.update({
        "status": "evaluated",
        "actual_rate": actual_rate,
        "actual_move_bps": actual_move,
        "hit": hit,
        "prob_assigned_to_actual": p_actual,
        "brier_score": brier,
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
        hist_extra.append({
            "meeting_date": r["date"],
            "source": "historical_consensus_leg_only",
            "bi_rate_before": r["prev"],
            "consensus": r["consensus"],
            "final_probability": {str(m): round(v, 4) for m, v in P.items()},
            "most_likely_move_bps": pred_mode,
            "status": "evaluated",
            "actual_rate": r["actual"],
            "actual_move_bps": actual_move,
            "hit": pred_mode == actual_move,
            "prob_assigned_to_actual": round(P.get(actual_move, 0), 4),
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
    elif cmd == "update":
        update()
    else:
        print("pakai: python backtest.py [log|update]")
