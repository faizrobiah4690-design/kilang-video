# Kilang Pemasaran — Studio Video Pendek (Adaptasi MoneyPrinterTurbo)

Studio ringkas berasaskan [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) yang diadaptasi khas untuk kempen pemasaran PKS Malaysia (TikTok & Reels `9:16`):

- **Skrip Bahasa Melayu Natural (Google Gemini)**: Penjanaan skrip gaya percakapan harian rakyat Malaysia (elak bahasa skema/Indonesia) dengan contoh sedia ada seperti **Radhi Fruits 4690**, **PedalHaus Chukai**, **Servis Van Sekolah Binjai**, dan **Kempen Produk Umum**.
- **Suara Narasi BM Percuma (Edge TTS)**: Menyokong `ms-MY-YasminNeural` (Wanita) dan `ms-MY-OsmanNeural` (Lelaki) bersama penjanaan sarikata Edge automatik tanpa perlu memuat turun model Whisper besar.
- **Visual Produk Sendiri, Sampel Demo, atau Video Stok**: Muat naik gambar/klip produk terus, uji serta-merta dengan 3 kad sampel `9:16` di `resource/kilang_samples/`, atau guna carian video stok Pexels/Pixabay.

> Nota: Antaramuka asal MoneyPrinterTurbo (`webui/Main.py`) dan perkhidmatan terasnya kekal utuh tanpa diubah.

---

## 1. Menjalankan Secara Tempatan (Local)

### Prasyarat
- **Python 3.11+** & [`uv`](https://docs.astral.sh/uv/)
- **FFmpeg** tersedia pada `PATH`

### Langkah Pantas
1. Salin `.env.example` kepada `.env` dan isi `GEMINI_API_KEY` (atau masukkan terus di panel tepi UI sebagai kunci sesi):
   ```bash
   cp .env.example .env
   ```
2. Pasang kebergantungan (jika belum):
   ```bash
   uv sync --frozen
   ```
3. Lancarkan studio ringkas:
   - **Windows**: Klik dua kali `kilang.bat` atau jalankan `.\kilang.bat`
   - **Linux / macOS**:
     ```bash
     chmod +x kilang.sh && ./kilang.sh
     ```
   - **Atau melalui `uv`**:
     ```bash
     uv run streamlit run webui/KilangStudio.py
     ```
4. Buka pelayar di `http://127.0.0.1:8501`.

---

## 2. Terus Deploy Live (Cloud)

### Pilihan A — Render (Blueprint `render.kilang.yaml`)
1. Tolak folder `kilang-video` ke repositori GitHub anda (pastikan `.env` dan `config.toml` tidak di-commit).
2. Dalam [Render Dashboard](https://dashboard.render.com/), pilih **New + -> Blueprint** dan pilih repositori tersebut (atau rujuk `render.kilang.yaml`).
3. Masukkan nilai `GEMINI_API_KEY` (dan `PEXELS_API_KEY` jika guna mod stok) di Environment Variables.
4. Render akan membina imej dari `Dockerfile.kilang` dan memantau `/_stcore/health`.

### Pilihan B — Docker / Railway / Fly.io / Hugging Face Spaces
Bina dan jalankan terus daripada `Dockerfile.kilang` (menyokong pembolehubah `PORT`, contohnya `PORT=7860` untuk Hugging Face Spaces Docker SDK):

```bash
docker build -f Dockerfile.kilang -t kilang-pemasaran .
docker run -p 8501:8501 -e GEMINI_API_KEY="AIza..." kilang-pemasaran
```
