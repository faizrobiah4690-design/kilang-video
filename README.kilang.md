# Kilang Pemasaran v2.0 — Studio Kilang Video & Hab Google Flow

Adaptasi penuh [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) untuk pengeluaran video pendek PKS Malaysia (TikTok, Reels & Shorts) secara tempatan dan terus *live* di Render.

## Ciri Utama v2.0

1. **Kilang Video (1 Video Pantas & Mod Kilang Batch 3-Sudut)**:
   - Jana 1 video pantas atau 3 variasi sudut serentak (*Urgensi & Stok Terhad*, *Kualiti, Rasa & Nilai*, *Bukti Sosial & Pelanggan*).
   - Skrip Bahasa Melayu percakapan natural oleh **Google Gemini** (`gemini-3.8-flash` dengan carian automatik model pelan percuma `Flash-Lite` apabila sesak `503`/`429`) + pek **Kapsyen & Hashtag TikTok/Reels**.
   - Suara narasi BM percuma **Edge TTS** (`ms-MY-YasminNeural` & `ms-MY-OsmanNeural`), pilihan warna sarikata, nisbah (`9:16`, `1:1`, `16:9`), dan muzik latar terbina atau muat naik MP3 sendiri.
2. **Pelayar Studio In-House & Pintu Masuk Google Flow** (`app/services/studio_browser.py`):
   - **Mod Komputer Tempatan (Desktop)**: Melancarkan tetingkap Chromium/Edge terasing (`storage/studio_browser_profile/`) untuk log masuk Google Flow, Whisk, Google AI Studio, Pixabay, Canva, atau TikTok Studio — semua muat turun masuk terus ke `storage/flow_inbox/`.
   - **Mod Pelayan Awan (Render Live)**: Pautan studio terus, kotak muat naik seret-dan-lepas ke `storage/flow_inbox/`, **Penjana Prompt Adegan Google Flow (`9:16` Veo / Nano Banana)**, serta integrasi terus **UseAPI Google Flow** (`USEAPI_TOKEN`).
3. **Peti Jenama & Galeri Hasil** (`app/services/kilang_vault.py`):
   - Simpan profil klien berulang (`storage/kilang_brands.json`) dan semak/mainkan/muat turun/padam semua MP4 siap bersama kapsyen (`storage/kilang_history.json`).
4. **Sambungan & Kesihatan**:
   - Ujian langsung Gemini + pengesanan model pelan percuma, FFmpeg, Edge TTS, enjin pelayar in-house, Pixabay/Pexels, dan UseAPI.

> Fail teras asal MoneyPrinterTurbo (`webui/Main.py`, `app/services/llm.py`, `task.py`, `video.py`, `voice.py`) dikekalkan utuh.

---

## 1. Jalankan Secara Tempatan
- **Windows**: Klik dua kali [kilang.bat](file:///d:/CHROME/Project/PPX%20MarTech/kilang-video/kilang.bat) (`http://127.0.0.1:8501`).
- **Linux / macOS**: `chmod +x kilang.sh && ./kilang.sh`
- Tetapkan `GEMINI_API_KEY` (dan pilihan `PIXABAY_API_KEY` / `USEAPI_TOKEN`) dalam `.env` atau terus pada panel kiri WebUI.

## 2. Live Online (Render Blueprint)
- Dikonfigurasi siap dengan `render.yaml` (pelan `free`, `autoDeploy: true`, `Dockerfile.kilang`, `/_stcore/health`).
- Tetapkan `GEMINI_API_KEY` (wajib untuk AI), `PIXABAY_API_KEY` (pilihan video stok), dan `USEAPI_TOKEN` (pilihan Google Flow API terus) di bahagian **Environment** Render.
