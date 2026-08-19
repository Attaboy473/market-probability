# BI RATE RADAR 🎯

Kalkulator probabilitas keputusan RDG Bank Indonesia — "Polymarket versi analisis":
bukan dari taruhan, tapi dari 3 kaki data profesional.

## Hasil (RDG 19 Agustus 2026)
```
HOLD 5.75% : 41.6%  ← paling mungkin
HIKE +25bp : 31.8%
CUT  -25bp : 26.6%
```

## Cara pakai
```bash
python bi_rdg_calc.py
# hasil lengkap -> data/rdg_result.json
```

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

RDG historis TE yang punya konsensus (hanya kaki konsensus):
- 2026-06-18: prediksi +25, aktual +25 ✅
- 2026-07-22: prediksi +25, aktual HOLD ❌ (BI surprise, konsensus keliru)

Prediksi live pertama: RDG 2026-08-19 → hold 41.6% / hike 31.8% / cut 26.6%
(status: menunggu hasil aktual, dievaluasi otomatis via cron)

## Roadmap (fase berikutnya)
- [ ] Dashboard Streamlit (visual gauge probabilitas + grafik yield curve)
- [ ] Backtest lebih panjang (butuh history konsensus → bisa via TE berbayar atau arsip berita)
- [ ] Event lain: inflasi, The Fed, GDP
- [ ] Scheduler cron + alert Telegram kalau probabilitas geser >10%

## Keterbatasan
- Indonesia tidak punya futures suku bunga BI → probabilitas pasar adalah PROKSI, bukan harga eksak
- Konsensus TE hanya tersedia untuk event terdekat (historisnya terbatas)
- Ini alat analisis, BUKAN platform taruhan (Polymarket diblokir Bappebti/Kominfo di Indonesia)
