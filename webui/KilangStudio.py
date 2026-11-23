"""Kilang Pemasaran v2.0 — Studio Kilang Video Pendek & Hab Google Flow."""

from __future__ import annotations

import html
import os
from pathlib import Path
import sys

import streamlit as st

# Ensure repository root takes priority so local `app` package is never shadowed.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if ROOT_DIR in sys.path:
    sys.path.remove(ROOT_DIR)
sys.path.insert(0, ROOT_DIR)

from app.services import kilang_studio as ks  # noqa: E402
from app.services import kilang_vault as kv  # noqa: E402
from app.services import studio_browser as sb  # noqa: E402
from webui import kilang_tabs as tabs  # noqa: E402

st.set_page_config(
    page_title="Kilang Pemasaran v2.0 — Studio Video Pendek",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _inject_theme_css() -> None:
    css_path = Path(__file__).with_name("kilang_theme.css")
    if css_path.is_file():
        st.markdown(
            f"<style>{css_path.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )


def _init_session_state() -> None:
    ks.load_dotenv_if_present()
    if "kilang_initialized" in st.session_state:
        return
    st.session_state["kilang_initialized"] = True
    brands = kv.list_brands()
    tabs.apply_brand_to_state(brands[0])
    st.session_state["selected_brand_picker"] = brands[0].id
    st.session_state["factory_mode"] = "single"
    st.session_state["video_script"] = ""
    st.session_state["script_source_badge"] = ""
    st.session_state["social_caption"] = ""
    st.session_state["social_hashtags"] = ""
    st.session_state["media_mode"] = "samples"
    st.session_state["stock_provider"] = "pixabay"
    st.session_state["useapi_mode"] = "useapi"
    st.session_state["useapi_video_model"] = ks.USEAPI_GOOGLE_FLOW_MODELS["video"][0]
    st.session_state["useapi_image_model"] = ks.USEAPI_GOOGLE_FLOW_MODELS["image"][0]
    st.session_state["voice_rate"] = 1.05
    st.session_state["subtitle_enabled"] = True
    st.session_state["subtitle_display_mode"] = "sentence"
    st.session_state["subtitle_animation"] = "pop_spring"
    st.session_state["subtitle_position"] = "bottom"
    st.session_state["bgm_choice"] = "random"
    st.session_state["bgm_volume"] = 0.15
    st.session_state["last_batch_renders"] = []
    st.session_state["flow_prompts_list"] = []
    st.session_state["selected_flow_inbox_files"] = []
    st.session_state["preview_audio_bytes"] = b""


def _render_sidebar() -> dict[str, str]:
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
        useapi_env_ok = bool(ks.resolve_useapi_config()["useapi_api_token"])

        st.markdown(
            f"- `GEMINI_API_KEY`: **{'Dikesan' if gemini_env_ok else 'Belum ditetapkan'}**\n"
            f"- `PIXABAY_API_KEY`: **{'Dikesan' if pixabay_env_ok else 'Belum ditetapkan'}**\n"
            f"- `PEXELS_API_KEY`: **{'Dikesan' if pexels_env_ok else 'Belum ditetapkan'}**\n"
            f"- `USEAPI_TOKEN`: **{'Dikesan' if useapi_env_ok else 'Belum ditetapkan'}**"
        )

        gemini_api_key = st.text_input(
            "Kunci API Gemini (Pilihan Sesi)",
            type="password",
            key="sidebar_gemini_api_key",
            placeholder="AIza...",
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

        with st.expander("Kunci Video Stok & Google Flow", expanded=False):
            pixabay_key = st.text_input(
                "Pixabay API Key",
                type="password",
                key="sidebar_pixabay_api_key",
            )
            pexels_key = st.text_input(
                "Pexels API Key",
                type="password",
                key="sidebar_pexels_api_key",
            )
            useapi_token = st.text_input(
                "UseAPI Token (Google Flow AI Terus)",
                type="password",
                key="sidebar_useapi_token",
            )

        st.divider()
        st.caption(
            "Antaramuka penuh asal MoneyPrinterTurbo masih kekal di `webui/Main.py`."
        )

    return {
        "gemini": gemini_api_key,
        "gemini_model": gemini_model,
        "pixabay": pixabay_key,
        "pexels": pexels_key,
        "useapi": useapi_token,
    }


def _render_header(keys: dict[str, str]) -> None:
    gemini_ok = bool(ks.resolve_gemini_runtime_config(api_key=keys["gemini"])["gemini_api_key"])
    stock = ks.resolve_stock_api_keys(pexels_key=keys["pexels"], pixabay_key=keys["pixabay"])
    pixabay_ok = bool(stock["pixabay_api_keys"])
    desktop_browser = bool(sb.detect_local_chromium_browser())
    inbox_count = len(sb.list_flow_inbox_items())
    render_count = len(kv.list_renders(existing_only=True))

    gemini_pill = (
        '<span class="kp-pill kp-pill-ok">Gemini: Sedia</span>'
        if gemini_ok
        else '<span class="kp-pill kp-pill-warn">Gemini: Perlu Kunci</span>'
    )
    pix_pill = (
        '<span class="kp-pill kp-pill-ok">Pixabay: Sedia</span>'
        if pixabay_ok
        else '<span class="kp-pill">Pixabay: Pilihan</span>'
    )
    browser_pill = (
        '<span class="kp-pill kp-pill-ok">Pelayar In-House: Desktop</span>'
        if desktop_browser
        else '<span class="kp-pill kp-pill-warn">Pelayar: Mod Awan</span>'
    )
    counts_pill = (
        f'<span class="kp-pill">Peti Flow: {html.escape(str(inbox_count))} • '
        f'Hasil: {html.escape(str(render_count))}</span>'
    )

    st.markdown(
        f"""
        <div class="kp-header">
          <div>
            <h1 class="kp-title">Kilang Pemasaran — Studio Video Pendek</h1>
            <p class="kp-subtitle">
              Kilang penghasilan video TikTok, Reels &amp; Shorts untuk PKS Malaysia — skrip Bahasa Melayu Gemini, suara Edge TTS percuma, Peti Masuk Google Flow, dan galeri siap pos.
            </p>
          </div>
          <div class="kp-ribbon">
            {gemini_pill}
            {pix_pill}
            {browser_pill}
            {counts_pill}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    _inject_theme_css()
    _init_session_state()
    keys = _render_sidebar()
    _render_header(keys)

    notice = st.session_state.pop("_kilang_pending_notice", None)
    if isinstance(notice, tuple) and len(notice) == 2:
        kind, msg = notice
        if kind == "success":
            st.success(msg)
        else:
            st.toast(msg)

    tab_factory, tab_browser, tab_brands, tab_gallery, tab_diag = st.tabs(
        [
            "Kilang Video",
            "Pelayar Studio & Google Flow",
            "Peti Jenama",
            "Galeri Hasil",
            "Sambungan & Kesihatan",
        ]
    )

    with tab_factory:
        tabs.render_factory_tab(keys)
    with tab_browser:
        tabs.render_browser_flow_tab(keys)
    with tab_brands:
        tabs.render_brand_vault_tab()
    with tab_gallery:
        tabs.render_gallery_tab()
    with tab_diag:
        tabs.render_diagnostics_tab(keys)


if __name__ == "__main__":
    main()
