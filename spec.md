# Spec — Kilang Pemasaran v2.0 (Adaptasi Penuh MoneyPrinterTurbo)

## 1. Tujuan Produk
Menjadikan adaptasi `MoneyPrinterTurbo` dalam `kilang-video/` sebagai **kilang pengeluaran video pemasaran pendek (TikTok / Reels / Shorts)** sebenar untuk PKS Malaysia — bukan sekadar satu borang klip demo — sambil kekal mudah digunakan secara tempatan dan terus *live* di Render (`https://kilang-pemasaran-video.onrender.com`).

## 2. Aliran Kerja Teras (5 Tab Studio Gelap Bersepadu)
1. **Tab 1 — Kilang Video (Tunggal & Batch 3-Sudut)**:
   - Pilih jenama daripada **Peti Jenama** (`kilang_vault.py`).
   - Mod **1 Video Pantas** atau **Mod Kilang Batch 3-Sudut** (*Urgensi*, *Kualiti & Nilai*, *Bukti Sosial*) yang menjana 3 skrip + 3 video MP4 berbeza dalam satu aliran kerja.
   - Penjanaan **Pek Kapsyen & Hashtag TikTok/Reels** automatik dalam Bahasa Melayu.
   - Sumber visual fleksibel: Muat Naik Produk Sendiri, Peti Masuk Google Flow (`storage/flow_inbox/`), Video Stok Pixabay/Pexels, Google Flow AI Terus (UseAPI), atau Sampel Demo Radhi Fruits.
   - Kawalan penuh nisbah (`9:16`, `1:1`, `16:9`), warna sarikata viral, kelajuan suara `ms-MY` Edge TTS, dan muzik latar terbina atau muat naik MP3 sendiri.
2. **Tab 2 — Pelayar Studio & Google Flow**:
   - **Mod Komputer Tempatan (Desktop)**: Melancarkan tetingkap Chromium/Edge terasing (`storage/studio_browser_profile/`) yang mengarah muat turun terus ke `storage/flow_inbox/` supaya pengguna boleh log masuk Google Flow, Whisk, Google AI Studio, Pixabay, Canva, atau TikTok Studio dengan sesi kekal sebenar (tanpa disekat iframe `X-Frame-Options`).
   - **Mod Pelayan Awan (Render Live)**: Menjelaskan status awan secara jujur dengan pautan terus, pengimport seret-dan-lepas ke `flow_inbox/`, kotak pasir *iframe* pilihan untuk laman yang membenarkan embed, **Penjana Prompt Adegan Google Flow (`9:16` Veo / Nano Banana)** berasaskan Gemini, serta sokongan token `USEAPI_TOKEN` untuk automasi terus Google Flow.
3. **Tab 3 — Peti Jenama (`storage/kilang_brands.json`)**:
   - Simpan, sunting, dan padam profil klien PKS berulang (tawaran, USP, CTA, warna sarikata, suara, nisbah lalai, kata kunci visual).
4. **Tab 4 — Galeri Hasil (`storage/kilang_history.json`)**:
   - Semak semua MP4 yang telah dijana, mainkan terus dalam pelayar, muat turun semula, salin kapsyen + hashtag, dan padam tugas lama dengan pembersihan cakera yang selamat.
5. **Tab 5 — Sambungan & Kesihatan**:
   - Diagnostik masa nyata untuk FFmpeg, Edge TTS, enjin pelayar in-house tempatan, ujian sambungan Gemini + senarai model pelan percuma yang ditemui (`models.list()`), dan status Pixabay/Pexels/UseAPI.

## 3. Sempadan Seni Bina
- Semua fail teras MoneyPrinterTurbo (`app/services/llm.py`, `task.py`, `video.py`, `voice.py`, `useapi.py`, `bgm.py`, `material_upload.py`, `webui/Main.py`, `config.example.toml`, `webui/.streamlit/config.toml`) kekal **tidak diubah**.
- Semua ciri Kilang Pemasaran v2.0 berada dalam `app/services/kilang_studio.py`, `app/services/studio_browser.py`, `app/services/kilang_vault.py`, `webui/KilangStudio.py`, `webui/kilang_tabs.py`, `webui/kilang_theme.css`, dan skrip/konfigurasi berkaitan.
