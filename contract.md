# Contract — Kilang Pemasaran (Adaptasi MoneyPrinterTurbo, Lean Studio Level 2)

## 1. Scope & Deliverables
Adapt `harry0703/MoneyPrinterTurbo` into an isolated Malaysian short-video factory inside `kilang-video/` without modifying `adforge-my`, `faiz-martech-portfolio`, or `Project MarTech`:

1. **`app/services/kilang_studio.py`**:
   - Campaign presets grounded in workspace SMEs (`radhi_fruits`, `pedalhaus_chukai`, `van_sekolah_binjai`, `produk_umum`).
   - Natural spoken Malaysian Bahasa Melayu Gemini prompt engineering (`MALAY_MARKETING_SYSTEM_PROMPT`, `build_malay_brief_requirements`, `generate_malay_script`, `generate_visual_terms`).
   - Honest explicit offline starter template (`build_offline_template_script`) never disguised as Gemini output.
   - Per-session Gemini & stock key resolution (`load_dotenv_if_present`, `resolve_gemini_runtime_config`, `resolve_stock_api_keys`) without mutating global `config.toml` or logging secrets.
   - TikTok/Reels `9:16` `VideoParams` builder (`build_tiktok_video_params`), sample material staging (`get_sample_material_paths`, `stage_sample_materials`), and upload staging (`stage_uploaded_materials`) delegating strictly to `app/services/material_upload.py`.
2. **`scripts/generate_kilang_samples.py` + `resource/kilang_samples/`**:
   - Generates 3 clean `1080x1920` (`9:16`) sample promo PNG visuals (`radhi_fruits_1.png`..`3.png`) using bundled fonts (`BeVietnamPro-Bold.ttf`, `BeVietnamPro-Medium.ttf`) so full rendering works out of the box.
3. **`webui/KilangStudio.py`**:
   - Simplified 3-step Bahasa Melayu Streamlit WebUI (`Pilih Kempen & Jana Skrip BM` -> `Media Visual Produk 9:16` -> `Suara BM, Sarikata & Jana Video MP4`).
   - Supports Gemini BYOK/env, Edge TTS `ms-MY-YasminNeural-Female` & `ms-MY-OsmanNeural-Male`, `subtitle_provider="edge"`, local photo/clip upload, demo sample visuals, or optional Pexels/Pixabay stock footage.
   - Keeps upstream `webui/Main.py`, `app/services/*`, and `config.example.toml` intact.
4. **Local & Live Deployment Files**:
   - `.env.example`, `kilang.bat`, `kilang.sh`, `Dockerfile.kilang`, `render.kilang.yaml`, `README.kilang.md`.

## 2. Security & Honesty Boundaries
- **Zero Secrets Committed**: `.env` and `config.toml` stay untracked in `.gitignore`; UI secret inputs use `type="password"` and pass keys per-request (`app_config`) rather than writing to disk.
- **No Fake AI Output**: Missing/invalid `GEMINI_API_KEY` or Gemini API failure returns `ok=False` with a clear Bahasa Melayu message. Offline template drafting is triggered only via its own explicitly labeled button.
- **Upload Validation Enforced**: All local user uploads pass through `app.services.material_upload.save_material_upload` (filename sanitization, extension + magic-byte image/FFmpeg video verification, size caps) and stay confined under `storage/local_videos/`.

## 3. Hard Verification Thresholds
1. **Unit Tests**: `pytest test/services/test_kilang_studio.py -v` passes 100% (TDD `RED -> GREEN`).
2. **Upstream Regression**: `pytest test/services/test_material_upload.py test/services/test_voice.py -v` passes 100%.
3. **Lint**: `ruff check app/services/kilang_studio.py webui/KilangStudio.py scripts/generate_kilang_samples.py test/services/test_kilang_studio.py` exits 0.
4. **Real MP4 Render E2E**: Real non-mocked `task.start` render with Radhi Fruits script, Edge TTS (`ms-MY-YasminNeural-Female`), `subtitle_provider="edge"`, `BeVietnamPro-Bold.ttf`, and `radhi_fruits_*.png` produces a valid `.mp4` (> 100 KB) verified by `ffprobe` (`h264`, `1080x1920`, duration > 3.0s, `aac` audio).
5. **Live UI Smoke**: `AppTest.from_file("webui/KilangStudio.py").run(...)` completes with zero exceptions, and live Streamlit HTTP check returns `200 OK` on `/_stcore/health` and `/`.
6. **Git Hygiene**: Zero tracked modifications outside `kilang-video/`; zero committed secrets or `.env`/`config.toml` in `kilang-video/`.
