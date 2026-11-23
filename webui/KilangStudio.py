"""Simplified Malay short-video factory WebUI for Kilang Pemasaran."""

from __future__ import annotations

import html
import os
from pathlib import Path
import re
import sys
import tempfile
from uuid import uuid4

import streamlit as st

# Ensure repository root takes priority so local `app` package is never shadowed.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if ROOT_DIR in sys.path:
    sys.path.remove(ROOT_DIR)
sys.path.insert(0, ROOT_DIR)

from app.config import config  # noqa: E402
from app.models import const  # noqa: E402
from app.services import kilang_studio as ks  # noqa: E402
from app.services import material_upload  # noqa: E402
from app.services import task as tm  # noqa: E402
from app.services import voice  # noqa: E402
from app.utils import utils  # noqa: E402

st.set_page_config(
    page_title="Kilang Pemasaran — Studio Video Pendek",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      [data-testid="stToolbar"] { visibility: hidden; height: 0; }
      .block-container { padding-top: 1.5rem; padding-bottom: 2.5rem; }
      .kilang-badge {
        display: inline-block;
        padding: 0.2rem 0.65rem;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 600;
        background: rgba(16, 185, 129, 0.14);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.35);
      }
      .kilang-badge-warn {
        background: rgba(245, 158, 11, 0.14);
        color: #f59e0b;
        border: 1px solid rgba(245, 158, 11, 0.35);
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def _safe_download_filename(product_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (product_name or "").lower()).strip("-")
    return f"kilang-{slug or 'video-pendek'}-9x16.mp4"


def _apply_preset_to_state(preset_id: str) -> None:
    preset = ks.get_preset(preset_id)
    st.session_state["preset_id"] = preset.id
    st.session_state["product_name"] = preset.product_name
    st.session_state["offer"] = preset.offer
    st.session_state["usp"] = preset.usp
    st.session_state["audience_cta"] = preset.audience_cta
    st.session_state["style_key"] = preset.style_key
    st.session_state["duration_seconds"] = preset.duration_seconds
    st.session_state["stock_terms"] = ", ".join(preset.visual_terms)


def _init_session_state() -> None:
    ks.load_dotenv_if_present()
    if "kilang_initialized" in st.session_state:
        return
    st.session_state["kilang_initialized"] = True
    _apply_preset_to_state("radhi_fruits")
    st.session_state["video_script"] = ""
    st.session_state["script_source_badge"] = ""
    st.session_state["media_mode"] = "samples"
    st.session_state["stock_provider"] = "pexels"
    st.session_state["voice_name"] = ks.DEFAULT_MALAY_VOICE
    st.session_state["voice_rate"] = 1.05
    st.session_state["subtitle_enabled"] = True
    st.session_state["subtitle_display_mode"] = "sentence"
    st.session_state["subtitle_animation"] = "pop_spring"
    st.session_state["subtitle_position"] = "bottom"
    st.session_state["bgm_type"] = "random"
    st.session_state["bgm_volume"] = 0.15
    st.session_state["last_video_path"] = ""
    st.session_state["last_video_product"] = ""
    st.session_state["preview_audio_bytes"] = b""


def _render_sidebar() -> tuple[str, str, str, str]:
    with st.sidebar:
        st.header("Tetapan API (BYOK / Env)")
        st.caption(
            "Kunci yang dimasukkan di sini hanya disimpan dalam sesi pelayar ini dan "
            "tidak ditulis ke `config.toml` atau repositori git."
        )

        gemini_env_ok = bool(ks.resolve_gemini_runtime_config()["gemini_api_key"])
        stock_env = ks.resolve_stock_api_keys()
        pexels_env_ok = bool(stock_env["pexels_api_keys"])
        pixabay_env_ok = bool(stock_env["pixabay_api_keys"])

        st.markdown(
            f"- `GEMINI_API_KEY`: **{'Dikesan' if gemini_env_ok else 'Belum ditetapkan'}**\n"
            f"- `PEXELS_API_KEY`: **{'Dikesan' if pexels_env_ok else 'Belum ditetapkan'}**\n"
            f"- `PIXABAY_API_KEY`: **{'Dikesan' if pixabay_env_ok else 'Belum ditetapkan'}**"
        )

        gemini_api_key = st.text_input(
            "Kunci API Gemini (Pilihan Sesi)",
            type="password",
            key="sidebar_gemini_api_key",
            placeholder="AIza...",
            help="Diperlukan untuk menjana skrip Bahasa Melayu dan kata kunci visual.",
        )

        model_choices = [*ks.GEMINI_MODEL_OPTIONS, "Tersuai (Custom)"]
        selected_model_option = st.selectbox(
            "Model Gemini",
            options=model_choices,
            index=0,
            key="sidebar_gemini_model_choice",
        )
        if selected_model_option == "Tersuai (Custom)":
            gemini_model = st.text_input(
                "Nama Model Gemini Tersuai",
                value=ks.DEFAULT_GEMINI_MODEL,
                key="sidebar_gemini_model_custom",
            ).strip()
        else:
            gemini_model = selected_model_option

        with st.expander("Kunci Video Stok (Pilihan)", expanded=False):
            pexels_key = st.text_input(
                "Pexels API Key",
                type="password",
                key="sidebar_pexels_api_key",
            )
            pixabay_key = st.text_input(
                "Pixabay API Key",
                type="password",
                key="sidebar_pixabay_api_key",
            )

        st.divider()
        st.caption(
            "Antaramuka penuh MoneyPrinterTurbo masih tersedia di `webui/Main.py` "
            "jika perlukan tetapan lanjutan."
        )

    return gemini_api_key, gemini_model, pexels_key, pixabay_key


def _current_brief() -> ks.CampaignBrief:
    return ks.CampaignBrief(
        product_name=st.session_state.get("product_name", ""),
        offer=st.session_state.get("offer", ""),
        usp=st.session_state.get("usp", ""),
        audience_cta=st.session_state.get("audience_cta", ""),
        style_key=st.session_state.get("style_key", "santai_tiktok"),
        duration_seconds=int(st.session_state.get("duration_seconds", 30)),
    )


def _render_script_step(gemini_api_key: str, gemini_model: str) -> None:
    st.subheader("1. Kempen & Skrip Bahasa Melayu (Gemini)")

    preset_ids = [preset.id for preset in ks.CAMPAIGN_PRESETS]
    preset_labels = {preset.id: preset.label for preset in ks.CAMPAIGN_PRESETS}

    col_preset, col_btn = st.columns([3, 1], vertical_alignment="bottom")
    with col_preset:
        chosen_preset = st.selectbox(
            "Pilih Contoh Kempen",
            options=preset_ids,
            format_func=lambda pid: preset_labels[pid],
            key="selected_preset_picker",
        )
    with col_btn:
        if st.button("Muat Contoh Kempen", use_container_width=True):
            _apply_preset_to_state(chosen_preset)
            st.toast(f"Contoh '{preset_labels[chosen_preset]}' dimuatkan.")

    col_a, col_b = st.columns(2)
    with col_a:
        st.text_input("Nama Produk / Jenama", key="product_name")
        st.text_input("Tawaran / Harga Utama", key="offer")
        st.selectbox(
            "Gaya Penyampaian Skrip",
            options=list(ks.SCRIPT_STYLES.keys()),
            format_func=lambda key: ks.SCRIPT_STYLES[key]["label"],
            key="style_key",
        )
    with col_b:
        st.text_input("Kelebihan Utama (USP)", key="usp")
        st.text_input("Sasaran & Seruan Tindakan (CTA)", key="audience_cta")
        st.selectbox(
            "Sasaran Tempoh Video",
            options=list(ks.DURATION_PROFILES.keys()),
            format_func=lambda sec: ks.DURATION_PROFILES[sec]["label"],
            key="duration_seconds",
        )

    btn_ai, btn_tpl = st.columns(2)
    with btn_ai:
        if st.button("Jana Skrip BM dengan Gemini", type="primary", use_container_width=True):
            with st.spinner("Gemini sedang menulis skrip Bahasa Melayu..."):
                res = ks.generate_malay_script(
                    _current_brief(),
                    api_key=gemini_api_key,
                    model_name=gemini_model,
                )
            if res.ok:
                st.session_state["video_script"] = res.script
                st.session_state["script_source_badge"] = f"Dijana oleh Gemini ({res.model_name})"
                st.success("Skrip Bahasa Melayu berjaya dijana!")
            else:
                st.error(res.error)

    with btn_tpl:
        if st.button("Guna Draf Templat Tempatan (Tanpa AI)", use_container_width=True):
            res = ks.build_offline_template_script(_current_brief())
            st.session_state["video_script"] = res.script
            st.session_state["script_source_badge"] = "Mod Templat Tempatan (Bukan AI)"

    badge = st.session_state.get("script_source_badge", "")
    if badge:
        is_offline = "Bukan AI" in badge
        css_cls = "kilang-badge kilang-badge-warn" if is_offline else "kilang-badge"
        st.markdown(
            f'<span class="{css_cls}">{html.escape(badge)}</span>',
            unsafe_allow_html=True,
        )

    script_text = st.text_area(
        "Skrip Suara Akhir (Boleh Disunting Terus)",
        key="video_script",
        height=150,
        placeholder="Klik 'Jana Skrip BM dengan Gemini' atau tulis skrip suara anda di sini...",
    )
    word_count = len(script_text.split())
    est_seconds = round(word_count / 2.5, 1) if word_count else 0.0
    st.caption(f"Jumlah perkataan: **{word_count}** • Anggaran tempoh suara: **~{est_seconds} saat**")


def _render_media_step(gemini_api_key: str, gemini_model: str):
    st.subheader("2. Media Visual Produk (Format Menegak 9:16)")
    mode_labels = {
        "upload": "Muat Naik Gambar / Klip Produk Sendiri (Disyorkan)",
        "samples": "Gambar Sampel Demo Radhi Fruits (Uji Pantas Tanpa API Stok)",
        "stock": "Video Stok Automatik (Pexels / Pixabay)",
    }
    media_mode = st.radio(
        "Pilih Sumber Visual",
        options=list(mode_labels.keys()),
        format_func=lambda m: mode_labels[m],
        key="media_mode",
        horizontal=True,
    )

    uploaded_files = []
    if media_mode == "upload":
        st.info(
            "Muat naik 2–5 gambar produk (JPG/PNG) atau klip video pendek (MP4/MOV/WEBM). "
            "Gambar akan diberi kesan zum perlahan (Ken Burns) secara automatik."
        )
        uploaded_files = (
            st.file_uploader(
                "Pilih Fail Media Produk",
                type=["jpg", "jpeg", "png", "bmp", "mp4", "mov", "webm"],
                accept_multiple_files=True,
                key="kilang_media_uploader",
            )
            or []
        )
    elif media_mode == "samples":
        st.warning(
            "Mod demo menggunakan 3 kad visual sampel terbina dalam. Untuk iklan sebenar, "
            "pilih 'Muat Naik Gambar / Klip Produk Sendiri'."
        )
        sample_paths = ks.get_sample_material_paths()
        if sample_paths:
            cols = st.columns(len(sample_paths))
            for col, img_path in zip(cols, sample_paths):
                with col:
                    st.image(img_path, caption=Path(img_path).name, width=160)
    else:
        col_prov, col_kw_btn = st.columns([2, 1], vertical_alignment="bottom")
        with col_prov:
            st.selectbox(
                "Penyedia Video Stok",
                options=["pexels", "pixabay"],
                format_func=lambda s: s.capitalize(),
                key="stock_provider",
            )
        with col_kw_btn:
            if st.button("Jana Kata Kunci Visual (Gemini)", use_container_width=True):
                try:
                    terms = ks.generate_visual_terms(
                        _current_brief(),
                        st.session_state.get("video_script", ""),
                        amount=4,
                        api_key=gemini_api_key,
                        model_name=gemini_model,
                    )
                    st.session_state["stock_terms"] = ", ".join(terms)
                    st.success("Kata kunci visual Inggeris berjaya dijana.")
                except ValueError as exc:
                    st.warning(f"{exc} Menggunakan kata kunci sedia ada.")

        st.text_input(
            "Kata Kunci Carian Stok (Bahasa Inggeris, dipisah koma)",
            key="stock_terms",
        )

    return media_mode, uploaded_files


def _execute_video_render(
    *,
    media_mode: str,
    uploaded_files: list,
    pexels_key: str,
    pixabay_key: str,
) -> tuple[bool, str]:
    brief = _current_brief()
    script_text = st.session_state.get("video_script", "").strip()
    if not script_text:
        return False, "Sila jana atau masukkan skrip Bahasa Melayu sebelum menjana video."

    local_materials = None
    video_source = "local"
    stock_terms = None

    if media_mode == "upload":
        if not uploaded_files:
            return False, "Sila muat naik sekurang-kurangnya satu gambar atau klip video produk."
        try:
            local_materials = ks.stage_uploaded_materials(uploaded_files)
        except (material_upload.MaterialUploadError, material_upload.MaterialServiceError) as exc:
            return False, f"Fail media tidak sah: {exc}"
    elif media_mode == "samples":
        local_materials = ks.stage_sample_materials()
    else:
        video_source = st.session_state.get("stock_provider", "pexels")
        stock_keys = ks.resolve_stock_api_keys(pexels_key=pexels_key, pixabay_key=pixabay_key)
        required_cfg_key = f"{video_source}_api_keys"
        if not stock_keys.get(required_cfg_key):
            return False, (
                f"Kunci API {video_source.capitalize()} belum ditetapkan di panel tepi atau persekitaran."
            )
        stock_terms = st.session_state.get("stock_terms", "")

    profile = ks.DURATION_PROFILES.get(brief.duration_seconds, ks.DURATION_PROFILES[30])
    try:
        params = ks.build_tiktok_video_params(
            product_name=brief.product_name,
            script=script_text,
            video_source=video_source,
            local_materials=local_materials,
            video_terms=stock_terms,
            voice_name=st.session_state.get("voice_name", ks.DEFAULT_MALAY_VOICE),
            voice_rate=float(st.session_state.get("voice_rate", 1.05)),
            subtitle_enabled=bool(st.session_state.get("subtitle_enabled", True)),
            subtitle_display_mode=st.session_state.get("subtitle_display_mode", "sentence"),
            subtitle_animation=st.session_state.get("subtitle_animation", "pop_spring"),
            subtitle_position=st.session_state.get("subtitle_position", "bottom"),
            bgm_type=st.session_state.get("bgm_type", "random"),
            bgm_volume=float(st.session_state.get("bgm_volume", 0.15)),
            clip_duration=profile["clip_duration"],
        )
    except ValueError as exc:
        return False, str(exc)

    task_id = f"kilang-{uuid4().hex[:12]}"
    stock_keys = ks.resolve_stock_api_keys(pexels_key=pexels_key, pixabay_key=pixabay_key)

    with config.runtime_config_lock():
        prev_subtitle_provider = config.app.get("subtitle_provider", "edge")
        prev_pexels = config.app.get("pexels_api_keys")
        prev_pixabay = config.app.get("pixabay_api_keys")
        try:
            config.app["subtitle_provider"] = "edge"
            if video_source == "pexels":
                config.app["pexels_api_keys"] = stock_keys["pexels_api_keys"]
            elif video_source == "pixabay":
                config.app["pixabay_api_keys"] = stock_keys["pixabay_api_keys"]
            result = tm.start(task_id=task_id, params=params)
        finally:
            config.app["subtitle_provider"] = prev_subtitle_provider
            if prev_pexels is None:
                config.app.pop("pexels_api_keys", None)
            else:
                config.app["pexels_api_keys"] = prev_pexels
            if prev_pixabay is None:
                config.app.pop("pixabay_api_keys", None)
            else:
                config.app["pixabay_api_keys"] = prev_pixabay

    if not isinstance(result, dict):
        return False, "Ralat dalaman: tugas tidak memulangkan keputusan sah."
    if result.get("state") == const.TASK_STATE_FAILED or result.get("error"):
        stage = result.get("failed_stage", "pipeline")
        return False, f"Penghasilan video gagal pada peringkat '{stage}': {result.get('error')}"

    videos = result.get("videos") or []
    if not videos or not Path(videos[0]).is_file():
        return False, "Video akhir tidak berjaya dijana oleh FFmpeg."
    return True, str(videos[0])


def _render_audio_and_generate_step(
    *,
    media_mode: str,
    uploaded_files: list,
    pexels_key: str,
    pixabay_key: str,
) -> None:
    st.subheader("3. Suara BM, Sarikata & Jana Video TikTok / Reels")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.selectbox(
            "Suara Narasi BM (Edge TTS Percuma)",
            options=list(ks.MALAY_VOICES.keys()),
            format_func=lambda v: ks.MALAY_VOICES[v],
            key="voice_name",
        )
        st.slider("Kelajuan Suara", min_value=0.90, max_value=1.25, step=0.05, key="voice_rate")
    with c2:
        st.checkbox("Papar Sarikata Automatik", key="subtitle_enabled")
        st.selectbox(
            "Mod Paparan Sarikata",
            options=["sentence", "word_by_word"],
            format_func=lambda m: "Ikut Ayat" if m == "sentence" else "Perkataan Demi Perkataan",
            key="subtitle_display_mode",
        )
        st.selectbox(
            "Animasi & Posisi Sarikata",
            options=["pop_spring", "none"],
            format_func=lambda a: "Pop TikTok" if a == "pop_spring" else "Statik Kemas",
            key="subtitle_animation",
        )
        st.selectbox(
            "Kedudukan Sarikata",
            options=["bottom", "center"],
            format_func=lambda p: "Bawah (Selamat TikTok)" if p == "bottom" else "Tengah",
            key="subtitle_position",
        )
    with c3:
        st.selectbox(
            "Muzik Latar (BGM)",
            options=["random", "none"],
            format_func=lambda b: "Muzik Latar Rawak Terbina" if b == "random" else "Tiada Muzik Latar",
            key="bgm_type",
        )
        st.slider("Kelantangan Muzik Latar", min_value=0.0, max_value=0.5, step=0.05, key="bgm_volume")

    act_preview, act_render = st.columns([1, 2])
    with act_preview:
        if st.button("Pratonton Suara BM", use_container_width=True):
            snippet = (st.session_state.get("video_script", "") or "").strip()[:220]
            if not snippet:
                st.warning("Masukkan skrip dahulu untuk pratonton suara.")
            else:
                temp_dir = utils.storage_dir("temp", create=True)
                fd, tmp_mp3 = tempfile.mkstemp(prefix="kilang-preview-", suffix=".mp3", dir=temp_dir)
                os.close(fd)
                try:
                    sub_maker = voice.tts(
                        text=snippet,
                        voice_name=voice.parse_voice_name(st.session_state["voice_name"]),
                        voice_rate=float(st.session_state["voice_rate"]),
                        voice_file=tmp_mp3,
                    )
                    if sub_maker is not None and Path(tmp_mp3).is_file():
                        st.session_state["preview_audio_bytes"] = Path(tmp_mp3).read_bytes()
                    else:
                        st.error("Gagal menjana pratonton suara Edge TTS. Semak sambungan internet.")
                finally:
                    Path(tmp_mp3).unlink(missing_ok=True)

    with act_render:
        if st.button("Jana Video TikTok / Reels (9:16)", type="primary", use_container_width=True):
            with st.status("Sedang menghasilkan video menegak 9:16...", expanded=True) as status:
                status.write("Menyediakan suara Edge TTS BM, sarikata, dan gabungan visual...")
                ok, outcome = _execute_video_render(
                    media_mode=media_mode,
                    uploaded_files=uploaded_files,
                    pexels_key=pexels_key,
                    pixabay_key=pixabay_key,
                )
                if ok:
                    st.session_state["last_video_path"] = outcome
                    st.session_state["last_video_product"] = st.session_state.get("product_name", "")
                    status.update(label="Video TikTok / Reels siap dijana!", state="complete")
                else:
                    status.update(label="Penghasilan video gagal", state="error")
                    st.error(outcome)

    preview_bytes = st.session_state.get("preview_audio_bytes", b"")
    if preview_bytes:
        st.audio(preview_bytes, format="audio/mp3")

    last_video = st.session_state.get("last_video_path", "")
    if last_video and Path(last_video).is_file():
        st.divider()
        st.success("Video Siap Untuk Dimuat Turun & Dimuat Naik ke TikTok / Reels!")
        v_col, d_col = st.columns([1, 2])
        with v_col:
            st.video(last_video)
        with d_col:
            dl_name = _safe_download_filename(st.session_state.get("last_video_product", ""))
            st.download_button(
                label=f"Muat Turun MP4 ({dl_name})",
                data=Path(last_video).read_bytes(),
                file_name=dl_name,
                mime="video/mp4",
                type="primary",
            )
            st.caption(f"Fail tempatan: `{last_video}`")


def main() -> None:
    _init_session_state()
    st.title("🎬 Kilang Pemasaran — Studio Video Pendek")
    st.caption(
        "Adaptasi ringkas MoneyPrinterTurbo untuk kempen produk Malaysia (TikTok & Reels 9:16) "
        "dengan skrip Bahasa Melayu Gemini dan suara Edge TTS percuma."
    )

    gemini_api_key, gemini_model, pexels_key, pixabay_key = _render_sidebar()
    _render_script_step(gemini_api_key, gemini_model)
    st.divider()
    media_mode, uploaded_files = _render_media_step(gemini_api_key, gemini_model)
    st.divider()
    _render_audio_and_generate_step(
        media_mode=media_mode,
        uploaded_files=uploaded_files,
        pexels_key=pexels_key,
        pixabay_key=pixabay_key,
    )


if __name__ == "__main__":
    main()
