# BI RATE RADAR 🎯

Kalkulator probabilitas keputusan RDG Bank Indonesia — "Polymarket versi analisis":
bukan dari taruhan, tapi dari 3 kaki data profesional.

## Hasil (RDG 19 Agustus 2026)
```
Prediksi : HOLD 5.75% : 41.6%  ← paling mungkin
Aktual   : HOLD 5.75%          ← TERBUKTI BENAR (HIT)
```

## RDG berikutnya (23 September 2026)
```
HOLD 5.75% : 35.0%  ← paling mungkin (konsensus belum keluar)
HIKE +25bp : 32.9%
CUT  -25bp : 32.1%
```

## Cara pakai
```bash
pip install -r requirements.txt

# Kalkulator CLI
python bi_rdg_calc.py          # hasil lengkap -> data/rdg_result.json

# Dashboard web (Streamlit + Plotly)
streamlit run app.py           # buka http://localhost:8501
```

### Dashboard (Fase 2)
- 📊 Gauge + bar chart probabilitas CUT / HOLD / HIKE
- 🧠 Breakdown 3 kaki model dengan catatan per sinyal
- 📈 Yield curve SUN hari ini vs kemarin + SBN benchmark + indeks INDOBeX/ICBI
- 🌍 Indikator makro (USDIDR, IHSG, US10Y) + posisi inflasi di target band
- 📅 Kalender ekonomi & tabel backtest dengan akurasi

## Arsitektur

### Sumber data (semua GRATIS, tanpa API key)
| Sumber | Cara akses | Isinya |
|---|---|---|
| Trading Economics | HTTP + BeautifulSoup | BI rate, kalender RDG, konsensus, inflasi, forecast kuartalan, kalender ekonomi |
| PHEI (phei.co.id) | HTTP + BeautifulSoup | Yield curve SUN 0.1–39 thn, SBN benchmark (FR/PBS), indeks INDOBeX & ICBI |
| yfinance | `pip install yfinance` | USDIDR, IHSG, US Treasury 10Y (konteks eksternal) |

Catatan:
- Investing.com kena Cloudflare (403) → kalender diganti Trading Economics (data sama)
- API resmi Trading Economics berbayar; versi gratisnya scraping halaman web (boleh utk pemakaian pribadi, hormati ToS)

### Model probabilitas
```
P_final(move) = 45% × P_konsensus + 40% × P_pasar + 15% × P_makro
move ∈ {-25 bps (cut), 0 (hold), +25 bps (hike)}
```

1. **Kaki konsensus (45%)**: kolom "Kesepakatan" TE vs BI rate sekarang,
   dimodelkan sebagai distribusi normal (σ=20 bps) di grid {-25,0,+25},
   plus tilt dari forecast kuartal depan (bobot 25%).
2. **Kaki pasar obligasi (40%)**: spread yield tenor ~1 bln (PHEI) vs BI rate,
   dikurangi baseline spread normal (75 bps), diredam 50% (karena proxy noisy),
   + momentum yield harian (σ=45 bps).
3. **Kaki makro (15%)**: posisi inflasi di target band BI (1.5–3.5%),
   momentum rupiah 3 bulan (USDIDR), arah US10Y (σ=60 bps).

Semua bobot & parameter di dict `CONFIG` atas file — gampang di-tuning.

### Validasi (backtest)
`python backtest.py log`    → catat prediksi RDG terdekat SEBELUM hasil keluar
`python backtest.py update` → ambil hasil aktual dari TE, evaluasi prediksi vs kenyataan

Prinsip: prediksi harus dicatat sebelum hasil keluar (anti hindsight bias).
Log: `data/predictions_log.json`, hasil: `data/backtest_results.json`.

Backtest live (prediksi penuh 3 kaki, dicatat sebelum hasil keluar):
- 2026-08-19: prediksi HOLD (41.6%), aktual HOLD ✅ **HIT**

RDG historis TE yang punya konsensus (hanya kaki konsensus):
- 2026-06-18: prediksi +25, aktual +25 ✅
- 2026-07-22: prediksi +25, aktual HOLD ❌ (BI surprise, konsensus keliru)
- 2026-08-19: prediksi HOLD, aktual HOLD ✅

Skor sementara: **3 HIT / 1 MISS** (75%) — sampel kecil, tapi live tracking dimulai.

## Roadmap (fase berikutnya)
- [x] Dashboard Streamlit (visual gauge probabilitas + grafik yield curve)
- [x] Event lain: inflasi Indonesia & The Fed (tab "Event Lain")
- [x] Backtest historis 122 RDG (2016-2026) - hasil jujur: 68% = baseline hold,
      karena arsip konsensus & harga obligasi historis tidak tersedia gratis
- [ ] Arsip konsensus historis (TE berbayar) untuk backtest yang benar-benar bermakna
- [ ] Scheduler cron + alert kalau probabilitas geser >10%

## Keterbatasan
- Indonesia tidak punya futures suku bunga BI → probabilitas pasar adalah PROKSI, bukan harga eksak
- Konsensus TE hanya tersedia untuk event terdekat (historisnya terbatas)
- Ini alat analisis, BUKAN platform taruhan (Polymarket diblokir Bappebti/Kominfo di Indonesia)
