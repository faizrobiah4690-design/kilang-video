# Contract — Kilang Pemasaran v2.0 (Lean Studio Level 2 Revamp)

## 1. Goal Contract
- **outcome**: Ship a revamped 5-tab Kilang Pemasaran v2.0 short-video factory with Single & Batch 3-Angle video production, BM social caption/hashtag packs, In-House Studio Browser + Google Flow Inbox (`storage/flow_inbox/`), persistent Brand Vault, persistent Output Gallery, unified dark theme, and live Render deployment on `https://kilang-pemasaran-video.onrender.com`.
- **metric**:
  - 100% pass across `test_kilang_studio.py`, `test_studio_browser.py`, `test_kilang_vault.py` (including 5-tab `AppTest` smoke)
  - 100% pass across upstream regression tests (`test_material_upload.py`, `test_voice.py`, `test_useapi.py`)
  - `ruff check` returns 0 errors across all Kilang Pemasaran modules/tests
  - Real non-mocked MP4 render (`h264`, `1080x1920`, `aac`, duration > 3.0s, size > 100 KB) verified via `ffprobe` + persisted/cleaned cleanly via `kilang_vault`
  - Live Render deployment on `https://kilang-pemasaran-video.onrender.com` and local server on `http://127.0.0.1:8501` verified healthy and visually rendered
- **counter-metric**: Zero edits to core upstream MoneyPrinterTurbo modules (`llm.py`, `task.py`, `video.py`, `voice.py`, `useapi.py`, `bgm.py`, `material_upload.py`, `Main.py`), zero secrets tracked in git, zero faked AI outputs or unsafe path/command execution.
- **review-unit**: Per-module TDD (`RED -> GREEN`) + full non-mocked E2E render + single independent `studio-evaluator` audit (max 1 fix loop) + live Render/local browser check.
- **horizon**: Single Level 2 revamp sprint shipped live immediately.

## 2. Deliverables
1. `app/services/studio_browser.py` + `test/services/test_studio_browser.py`
2. `app/services/kilang_vault.py` + `test/services/test_kilang_vault.py`
3. `app/services/kilang_studio.py` + `test/services/test_kilang_studio.py` (Batch 3-angle scripts, Flow scene prompt generator, BM social caption/hashtag pack, UseAPI Flow bridge, Gemini Free-Tier diagnostics/discovery, extended `build_tiktok_video_params`)
4. `webui/kilang_theme.css`, `webui/kilang_tabs.py`, `webui/KilangStudio.py`
5. `kilang.bat`, `kilang.sh`, `Dockerfile.kilang`, `render.yaml`, `render.kilang.yaml`, `.env.example`, `README.kilang.md`

## 3. Security & Honesty Boundaries
- **Strict URL & Process Safety**: `studio_browser.validate_portal_url` allows only `http://` or `https://` with valid host and zero control characters; `launch_studio_browser` uses `subprocess.Popen(..., shell=False)` and cleanly reports `mode="cloud"` when no local GUI browser exists.
- **Path Confinement**: All `flow_inbox/` reads/imports/deletes and `kilang_vault.delete_render` task deletions are strictly confined via `app.utils.file_security.resolve_path_within_directory`, and media imports always pass through `app.services.material_upload.save_material_upload`.
- **XSS / HTML Escaping**: Dynamic values placed inside HTML markup in `webui/KilangStudio.py` and `webui/kilang_tabs.py` are escaped with `html.escape`.
- **Zero Secrets in Git & Config**: `.env`, `config.toml`, and `storage/` stay gitignored; UI API key inputs use `type="password"` and pass keys per-request or transiently inside `with config.runtime_config_lock():` with `try ... finally` restoration.
- **No Fake AI Output**: Missing/failing Gemini calls return explicit `ok=False` Bahasa Melayu diagnostics; offline template helpers live behind explicit separate buttons.

## 4. Hard Verification Thresholds
1. `pytest test/services/test_kilang_studio.py test/services/test_studio_browser.py test/services/test_kilang_vault.py -v` -> 100% pass.
2. `pytest test/services/test_material_upload.py test/services/test_voice.py test/services/test_useapi.py -q` -> 100% pass.
3. `ruff check app/services/kilang_studio.py app/services/studio_browser.py app/services/kilang_vault.py webui/KilangStudio.py webui/kilang_tabs.py scripts/generate_kilang_samples.py test/services/test_kilang_studio.py test/services/test_studio_browser.py test/services/test_kilang_vault.py` -> 0 errors.
4. Real non-mocked MP4 render (`task.start`) verified by `ffprobe` (`h264`, `1080x1920`, `aac`, > 3.0s, > 100 KB) + `kilang_vault.record_render`/`delete_render` verified.
5. `studio_browser.detect_local_chromium_browser()` detects local browser on Windows host.
6. Git status & `git ls-files .env config.toml storage/` clean; Render live URL `https://kilang-pemasaran-video.onrender.com` and local `http://127.0.0.1:8501` verified live.
