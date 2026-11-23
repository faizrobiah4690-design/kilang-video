"""Modular 5-tab UI sections for Kilang Pemasaran v2.0."""

from __future__ import annotations

from datetime import datetime, timezone
import html
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
import streamlit as st
import streamlit.components.v1 as components

from app.config import config
from app.models import const
from app.services import bgm as bgm_service
from app.services import kilang_studio as ks
from app.services import kilang_vault as kv
from app.services import material_upload
from app.services import studio_browser as sb
from app.services import task as tm
from app.services import useapi
from app.services import voice
from app.utils import utils


def safe_download_filename(product_name: str, suffix: str = "9x16") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (product_name or "").lower()).strip("-")
    tag = re.sub(r"[^a-z0-9]+", "-", (suffix or "").lower()).strip("-")
    return f"kilang-{slug or 'video'}-{tag or '9x16'}.mp4"


def apply_brand_to_state(brand: kv.BrandRecord) -> None:
    st.session_state["active_brand_id"] = brand.id
    st.session_state["product_name"] = brand.product_name
    st.session_state["offer"] = brand.offer
    st.session_state["usp"] = brand.usp
    st.session_state["audience_cta"] = brand.audience_cta
    st.session_state["style_key"] = (
        brand.style_key if brand.style_key in ks.SCRIPT_STYLES else "santai_tiktok"
    )
    st.session_state["duration_seconds"] = (
        brand.duration_seconds if brand.duration_seconds in ks.DURATION_PROFILES else 30
    )
    st.session_state["voice_name"] = (
        brand.default_voice if brand.default_voice in ks.MALAY_VOICES else ks.DEFAULT_MALAY_VOICE
    )
    st.session_state["subtitle_color"] = (
        brand.subtitle_color if brand.subtitle_color in ks.SUBTITLE_COLOR_PRESETS else "#FFFFFF"
    )
    st.session_state["video_aspect"] = (
        brand.default_aspect if brand.default_aspect in ks.ASPECT_OPTIONS else "9:16"
    )
    st.session_state["stock_terms"] = ", ".join(brand.visual_terms)


def _use_flow_inbox_callback(filenames: list[str]) -> None:
    st.session_state["media_mode"] = "flow_inbox"
    st.session_state["selected_flow_inbox_files"] = list(filenames)
    st.session_state["_kilang_pending_notice"] = (
        "success",
        "Sedia! Pergi ke tab Kilang Video dan klik Jana Video.",
    )


def _load_brand_vault_callback(brand: kv.BrandRecord) -> None:
    apply_brand_to_state(brand)
    st.session_state["selected_brand_picker"] = brand.id
    st.session_state["_kilang_pending_notice"] = (
        "toast",
        f"Profil '{brand.label}' dimuatkan ke Kilang Video.",
    )


def current_brief() -> ks.CampaignBrief:
    return ks.CampaignBrief(
        product_name=st.session_state.get("product_name", ""),
        offer=st.session_state.get("offer", ""),
        usp=st.session_state.get("usp", ""),
        audience_cta=st.session_state.get("audience_cta", ""),
        style_key=st.session_state.get("style_key", "santai_tiktok"),
        duration_seconds=int(st.session_state.get("duration_seconds", 30)),
    )


def _format_size_mb(size_bytes: int) -> str:
    if size_bytes < 1024 * 1024:
        return f"{max(1, size_bytes // 1024)} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _render_badge(text: str, *, warn: bool = False) -> None:
    cls = "kp-pill kp-pill-warn" if warn else "kp-pill kp-pill-ok"
    st.markdown(f'<span class="{cls}">{html.escape(text)}</span>', unsafe_allow_html=True)


def _execute_single_render(
    *,
    product_name: str,
    angle_label: str,
    script_text: str,
    caption_text: str,
    hashtags: tuple[str, ...],
    video_source: str,
    local_materials: list | None,
    stock_terms: str | list[str] | None,
    bgm_type: str,
    bgm_file: str,
    keys: dict[str, str],
) -> tuple[bool, kv.RenderRecord | None, str]:
    brief = current_brief()
    profile = ks.DURATION_PROFILES.get(brief.duration_seconds, ks.DURATION_PROFILES[30])
    aspect_value = st.session_state.get("video_aspect", "9:16")

    if video_source == "useapi" and aspect_value == "1:1":
        return False, None, "Google Flow (UseAPI Video) hanya menyokong nisbah 9:16 atau 16:9."

    try:
        params = ks.build_tiktok_video_params(
            product_name=product_name,
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
            text_fore_color=st.session_state.get("subtitle_color", "#FFFFFF"),
            video_aspect=aspect_value,
            bgm_type=bgm_type,
            bgm_file=bgm_file,
            bgm_volume=float(st.session_state.get("bgm_volume", 0.15)),
            clip_duration=profile["clip_duration"],
        )
    except ValueError as exc:
        return False, None, str(exc)

    task_id = f"kilang-{uuid4().hex[:12]}"
    stock_keys = ks.resolve_stock_api_keys(
        pexels_key=keys.get("pexels", ""),
        pixabay_key=keys.get("pixabay", ""),
    )
    useapi_cfg = ks.resolve_useapi_config(
        token=keys.get("useapi", ""),
        video_model=st.session_state.get("useapi_video_model", "veo-3.1-lite"),
        image_model=st.session_state.get("useapi_image_model", "nano-banana-2-lite"),
    )

    watched_keys = (
        "subtitle_provider",
        "pexels_api_keys",
        "pixabay_api_keys",
        "useapi_api_token",
        "useapi_video_model",
        "useapi_image_model",
    )
    with config.runtime_config_lock():
        prev_values = {k: config.app.get(k) for k in watched_keys if k in config.app}
        try:
            config.app["subtitle_provider"] = "edge"
            if video_source == "pexels":
                config.app["pexels_api_keys"] = stock_keys["pexels_api_keys"]
            elif video_source == "pixabay":
                config.app["pixabay_api_keys"] = stock_keys["pixabay_api_keys"]
            elif video_source in {"useapi", "useapi_image"}:
                config.app["useapi_api_token"] = useapi_cfg["useapi_api_token"]
                config.app["useapi_video_model"] = useapi_cfg["useapi_video_model"]
                config.app["useapi_image_model"] = useapi_cfg["useapi_image_model"]
            result = tm.start(task_id=task_id, params=params)
        finally:
            for k in watched_keys:
                if k in prev_values:
                    config.app[k] = prev_values[k]
                else:
                    config.app.pop(k, None)

    if not isinstance(result, dict):
        return False, None, "Ralat dalaman: tugas tidak memulangkan keputusan sah."
    if result.get("state") == const.TASK_STATE_FAILED or result.get("error"):
        stage = result.get("failed_stage", "pipeline")
        return False, None, f"Penghasilan video gagal pada peringkat '{stage}': {result.get('error')}"

    videos = result.get("videos") or []
    if not videos or not Path(videos[0]).is_file():
        return False, None, "Video akhir tidak berjaya dijana oleh FFmpeg."

    mp4_path = Path(videos[0])
    record = kv.RenderRecord(
        task_id=task_id,
        created_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        brand_name=product_name.strip() or "Kempen Video",
        angle_label=angle_label,
        aspect=aspect_value,
        script=script_text,
        caption=caption_text,
        hashtags=hashtags,
        video_path=str(mp4_path),
        file_size_bytes=mp4_path.stat().st_size,
        voice_name=st.session_state.get("voice_name", ks.DEFAULT_MALAY_VOICE),
        video_source=video_source,
    )
    kv.record_render(record)
    return True, record, ""


def _resolve_factory_visual_source(keys: dict[str, str]):
    mode = st.session_state.get("media_mode", "samples")
    if mode == "upload":
        uploads = st.session_state.get("_factory_uploaded_files") or []
        if not uploads:
            return None, None, None, "Sila muat naik sekurang-kurangnya satu gambar atau klip produk."
        try:
            materials = ks.stage_uploaded_materials(uploads)
        except (material_upload.MaterialUploadError, material_upload.MaterialServiceError) as exc:
            return None, None, None, f"Fail media tidak sah: {exc}"
        return "local", materials, None, ""

    if mode == "flow_inbox":
        selected_names = st.session_state.get("selected_flow_inbox_files") or []
        if not selected_names:
            return None, None, None, "Pilih sekurang-kurangnya satu fail daripada Peti Masuk Google Flow."
        try:
            materials = sb.import_flow_inbox_to_materials(list(selected_names))
        except (ValueError, material_upload.MaterialUploadError, material_upload.MaterialServiceError) as exc:
            return None, None, None, f"Gagal mengimport fail Peti Masuk Flow: {exc}"
        return "local", materials, None, ""

    if mode == "stock":
        provider = st.session_state.get("stock_provider", "pixabay")
        stock_keys = ks.resolve_stock_api_keys(
            pexels_key=keys.get("pexels", ""),
            pixabay_key=keys.get("pixabay", ""),
        )
        if not stock_keys.get(f"{provider}_api_keys"):
            return None, None, None, (
                f"Kunci API {provider.capitalize()} belum ditetapkan di panel kiri atau persekitaran."
            )
        return provider, None, st.session_state.get("stock_terms", ""), ""

    if mode == "useapi":
        useapi_cfg = ks.resolve_useapi_config(token=keys.get("useapi", ""))
        if not useapi_cfg["useapi_api_token"]:
            return None, None, None, "USEAPI_TOKEN diperlukan untuk mod Google Flow AI Terus (UseAPI)."
        src = st.session_state.get("useapi_mode", "useapi")
        return src, None, st.session_state.get("stock_terms", ""), ""

    return "local", ks.stage_sample_materials(), None, ""


def _resolve_factory_bgm() -> tuple[str, str, str]:
    bgm_choice = st.session_state.get("bgm_choice", "random")
    if bgm_choice in {"random", "none"}:
        return bgm_choice, "", ""
    if bgm_choice == "upload":
        bgm_up = st.session_state.get("_factory_bgm_upload")
        if not bgm_up:
            return "", "", "Sila muat naik fail MP3/WAV untuk muzik latar tersuai."
        try:
            stored = bgm_service.save_bgm_upload(getattr(bgm_up, "name", "bgm.mp3"), bgm_up)
            return "custom", bgm_service.resolve_bgm_file(stored), ""
        except Exception as exc:
            return "", "", f"Fail muzik latar tidak sah: {exc}"
    return "custom", bgm_choice, ""


def render_factory_tab(keys: dict[str, str]) -> None:
    brands = kv.list_brands()
    brand_map = {b.id: b for b in brands}
    brand_ids = list(brand_map.keys())
    if st.session_state.get("selected_brand_picker") not in brand_map:
        st.session_state["selected_brand_picker"] = brand_ids[0]

    col_brand, col_load, col_mode = st.columns([2.2, 1.1, 1.7], vertical_alignment="bottom")
    with col_brand:
        chosen_brand_id = st.selectbox(
            "Profil Jenama",
            options=brand_ids,
            format_func=lambda bid: brand_map[bid].label,
            key="selected_brand_picker",
        )
    with col_load:
        if st.button("Muat Profil Jenama", use_container_width=True):
            apply_brand_to_state(brand_map[chosen_brand_id])
            st.toast(f"Profil '{brand_map[chosen_brand_id].label}' dimuatkan.")
    with col_mode:
        factory_mode = st.radio(
            "Mod Pengeluaran",
            options=["single", "batch"],
            format_func=lambda m: "1 Video Pantas" if m == "single" else "Kilang Batch (3 Sudut)",
            key="factory_mode",
            horizontal=True,
        )

    c_left, c_right = st.columns(2)
    with c_left:
        st.text_input("Nama Produk / Jenama", key="product_name")
        st.text_input("Tawaran / Harga Utama", key="offer")
        st.selectbox(
            "Gaya Penyampaian",
            options=list(ks.SCRIPT_STYLES.keys()),
            format_func=lambda k: ks.SCRIPT_STYLES[k]["label"],
            key="style_key",
        )
    with c_right:
        st.text_input("Kelebihan Utama (USP)", key="usp")
        st.text_input("Sasaran & Seruan Tindakan (CTA)", key="audience_cta")
        st.selectbox(
            "Sasaran Tempoh Video",
            options=list(ks.DURATION_PROFILES.keys()),
            format_func=lambda s: ks.DURATION_PROFILES[s]["label"],
            key="duration_seconds",
        )

    gemini_key = keys.get("gemini", "")
    gemini_model = keys.get("gemini_model", ks.DEFAULT_GEMINI_MODEL)

    if factory_mode == "single":
        btn_ai, btn_tpl, btn_cap = st.columns(3)
        with btn_ai:
            if st.button("Jana Skrip BM dengan Gemini", type="primary", use_container_width=True):
                with st.spinner("Gemini sedang menulis skrip Bahasa Melayu..."):
                    res = ks.generate_malay_script(
                        current_brief(), api_key=gemini_key, model_name=gemini_model
                    )
                if res.ok:
                    st.session_state["video_script"] = res.script
                    st.session_state["script_source_badge"] = f"Dijana oleh Gemini ({res.model_name})"
                    st.success("Skrip Bahasa Melayu berjaya dijana!")
                else:
                    st.error(res.error)
        with btn_tpl:
            if st.button("Guna Draf Templat Tempatan (Tanpa AI)", use_container_width=True):
                res = ks.build_offline_template_script(current_brief())
                st.session_state["video_script"] = res.script
                st.session_state["script_source_badge"] = "Mod Templat Tempatan (Bukan AI)"
        with btn_cap:
            if st.button("Jana Kapsyen & Hashtag TikTok", use_container_width=True):
                pack = ks.generate_social_pack(
                    current_brief(),
                    st.session_state.get("video_script", ""),
                    api_key=gemini_key,
                    model_name=gemini_model,
                )
                if pack.ok:
                    st.session_state["social_caption"] = f"{pack.title}\n\n{pack.caption}"
                    st.session_state["social_hashtags"] = " ".join(pack.hashtags)
                else:
                    offline_pack = ks.build_offline_social_pack(current_brief())
                    st.session_state["social_caption"] = f"{offline_pack.title}\n\n{offline_pack.caption}"
                    st.session_state["social_hashtags"] = " ".join(offline_pack.hashtags)
                    st.warning(f"{pack.error} Menggunakan pek kapsyen templat tempatan.")

        badge = st.session_state.get("script_source_badge", "")
        if badge:
            _render_badge(badge, warn=("Bukan AI" in badge))

        script_text = st.text_area(
            "Skrip Suara Akhir (Boleh Disunting Terus)",
            key="video_script",
            height=135,
            placeholder="Klik 'Jana Skrip BM dengan Gemini' atau tulis skrip suara anda di sini...",
        )
        words = len(script_text.split())
        st.caption(f"Jumlah perkataan: **{words}** • Anggaran tempoh suara: **~{round(words / 2.5, 1)} saat**")

        with st.expander("Pek Kapsyen & Hashtag TikTok / Reels", expanded=False):
            st.text_area("Kapsyen Siap Pos", key="social_caption", height=85)
            st.text_input("Hashtag Cadangan", key="social_hashtags")
    else:
        b_ai, b_tpl = st.columns(2)
        with b_ai:
            if st.button("Jana 3 Skrip Sudut Sekaligus (Gemini)", type="primary", use_container_width=True):
                with st.spinner("Gemini sedang menjana 3 variasi sudut kempen..."):
                    drafts = ks.generate_batch_malay_scripts(
                        current_brief(), api_key=gemini_key, model_name=gemini_model
                    )
                errors = []
                for draft in drafts:
                    if draft.result.ok:
                        st.session_state[f"batch_script_{draft.angle_key}"] = draft.result.script
                    else:
                        errors.append(f"{draft.angle_label}: {draft.result.error}")
                if errors:
                    st.error(" | ".join(errors[:2]))
                else:
                    st.success("Ketiga-tiga variasi skrip siap untuk disemak dan dirender!")
        with b_tpl:
            if st.button("Isi 3 Draf Templat Tempatan (Tanpa AI)", use_container_width=True):
                for draft in ks.build_batch_offline_templates(current_brief()):
                    st.session_state[f"batch_script_{draft.angle_key}"] = draft.result.script

        cols = st.columns(3)
        for col, (angle_key, angle_meta) in zip(cols, ks.BATCH_ANGLES.items()):
            with col:
                st.checkbox(
                    f"Aktif: {angle_meta['label']}",
                    value=True,
                    key=f"batch_enable_{angle_key}",
                )
                st.text_area(
                    angle_meta["label"],
                    key=f"batch_script_{angle_key}",
                    height=130,
                    placeholder=f"Skrip sudut {angle_meta['label']}...",
                )

    st.divider()
    st.subheader("Media Visual & Sumber Klip")
    media_labels = {
        "upload": "Muat Naik Produk Sendiri",
        "flow_inbox": "Peti Masuk Google Flow",
        "stock": "Video Stok (Pixabay / Pexels)",
        "useapi": "Google Flow AI (UseAPI)",
        "samples": "Sampel Demo Radhi Fruits",
    }
    media_mode = st.radio(
        "Sumber Visual",
        options=list(media_labels.keys()),
        format_func=lambda m: media_labels[m],
        key="media_mode",
        horizontal=True,
    )

    if media_mode == "upload":
        uploads = st.file_uploader(
            "Muat Naik Gambar (JPG/PNG) atau Klip Video (MP4/MOV/WEBM)",
            type=["jpg", "jpeg", "png", "bmp", "mp4", "mov", "webm"],
            accept_multiple_files=True,
            key="kilang_media_uploader",
        )
        st.session_state["_factory_uploaded_files"] = uploads or []
    elif media_mode == "flow_inbox":
        inbox_items = sb.list_flow_inbox_items()
        if not inbox_items:
            st.info(
                "Peti Masuk Google Flow masih kosong. Buka tab **Pelayar Studio & Google Flow** "
                "untuk muat turun klip dari Google Flow / Whisk atau muat naik ke Peti Masuk."
            )
        else:
            options = [item.name for item in inbox_items]
            current_sel = [
                n for n in st.session_state.get("selected_flow_inbox_files", []) if n in options
            ]
            if not current_sel:
                current_sel = options[:4]
            st.session_state["selected_flow_inbox_files"] = current_sel
            st.multiselect(
                "Pilih Fail dari Peti Masuk Google Flow",
                options=options,
                key="selected_flow_inbox_files",
            )
    elif media_mode == "stock":
        c_p, c_btn = st.columns([2, 1], vertical_alignment="bottom")
        with c_p:
            st.selectbox(
                "Penyedia Stok",
                options=["pixabay", "pexels"],
                format_func=lambda s: s.capitalize(),
                key="stock_provider",
            )
        with c_btn:
            if st.button("Jana Kata Kunci Visual (Gemini)", use_container_width=True):
                try:
                    terms = ks.generate_visual_terms(
                        current_brief(),
                        st.session_state.get("video_script", ""),
                        amount=4,
                        api_key=gemini_key,
                        model_name=gemini_model,
                    )
                    st.session_state["stock_terms"] = ", ".join(terms)
                    st.success("Kata kunci Inggeris berjaya dijana.")
                except ValueError as exc:
                    st.warning(f"{exc} Menggunakan kata kunci sedia ada.")
        st.text_input("Kata Kunci Carian (Inggeris, dipisah koma)", key="stock_terms")
    elif media_mode == "useapi":
        u_c1, u_c2, u_c3 = st.columns(3)
        with u_c1:
            st.selectbox(
                "Mod UseAPI Google Flow",
                options=["useapi", "useapi_image"],
                format_func=lambda v: "Video (Veo / Gemini Omni)" if v == "useapi" else "Imej (Nano Banana + Zoom)",
                key="useapi_mode",
            )
        with u_c2:
            st.selectbox(
                "Model Video Flow",
                options=list(ks.USEAPI_GOOGLE_FLOW_MODELS["video"]),
                format_func=lambda m: useapi.MODELS.get(m, {}).get("label", m),
                key="useapi_video_model",
            )
        with u_c3:
            st.selectbox(
                "Model Imej Flow",
                options=list(ks.USEAPI_GOOGLE_FLOW_MODELS["image"]),
                format_func=lambda m: useapi.IMAGE_MODELS.get(m, {}).get("label", m),
                key="useapi_image_model",
            )
        st.text_input("Prompt / Kata Kunci Visual Google Flow (Inggeris)", key="stock_terms")
    else:
        sample_paths = ks.get_sample_material_paths()
        if sample_paths:
            cols = st.columns(len(sample_paths))
            for col, img_path in zip(cols, sample_paths):
                with col:
                    st.image(img_path, caption=Path(img_path).name, width=140)

    st.divider()
    st.subheader("Suara BM, Sarikata, Muzik & Format Output")
    g1, g2, g3 = st.columns(3)
    with g1:
        st.selectbox(
            "Suara Narasi BM (Edge TTS Percuma)",
            options=list(ks.MALAY_VOICES.keys()),
            format_func=lambda v: ks.MALAY_VOICES[v],
            key="voice_name",
        )
        st.slider("Kelajuan Suara", min_value=0.90, max_value=1.25, step=0.05, key="voice_rate")
        st.selectbox(
            "Nisbah Video",
            options=list(ks.ASPECT_OPTIONS.keys()),
            format_func=lambda a: ks.ASPECT_OPTIONS[a],
            key="video_aspect",
        )
    with g2:
        st.checkbox("Papar Sarikata Automatik", key="subtitle_enabled")
        st.selectbox(
            "Gaya Sarikata",
            options=["sentence", "word_by_word"],
            format_func=lambda m: "Ikut Ayat" if m == "sentence" else "Perkataan Demi Perkataan",
            key="subtitle_display_mode",
        )
        st.selectbox(
            "Warna Teks Sarikata",
            options=list(ks.SUBTITLE_COLOR_PRESETS.keys()),
            format_func=lambda c: ks.SUBTITLE_COLOR_PRESETS[c],
            key="subtitle_color",
        )
        st.selectbox(
            "Animasi & Posisi",
            options=["pop_spring", "none"],
            format_func=lambda a: "Pop TikTok" if a == "pop_spring" else "Statik Kemas",
            key="subtitle_animation",
        )
    with g3:
        builtin_bgms = bgm_service.list_builtin_bgm_files()
        bgm_options = ["random", "none", "upload", *builtin_bgms]
        st.selectbox(
            "Pilihan Muzik Latar",
            options=bgm_options,
            format_func=lambda b: (
                "Muzik Latar Rawak Terbina"
                if b == "random"
                else "Tiada Muzik Latar"
                if b == "none"
                else "Muat Naik MP3/WAV Sendiri"
                if b == "upload"
                else f"Trek: {Path(b).name}"
            ),
            key="bgm_choice",
        )
        if st.session_state.get("bgm_choice") == "upload":
            st.session_state["_factory_bgm_upload"] = st.file_uploader(
                "Muat Naik Audio BGM", type=["mp3", "wav"], key="kilang_bgm_uploader"
            )
        st.slider("Kelantangan Muzik Latar", min_value=0.0, max_value=0.5, step=0.05, key="bgm_volume")
        st.selectbox(
            "Kedudukan Sarikata",
            options=["bottom", "center"],
            format_func=lambda p: "Bawah (Selamat TikTok)" if p == "bottom" else "Tengah",
            key="subtitle_position",
        )

    act_prev, act_go = st.columns([1, 2])
    with act_prev:
        if st.button("Pratonton Suara BM", use_container_width=True):
            sample_txt = (
                st.session_state.get("video_script", "")
                or st.session_state.get("batch_script_urgensi", "")
                or ""
            ).strip()[:220]
            if not sample_txt:
                st.warning("Masukkan sekurang-kurangnya satu skrip dahulu untuk pratonton suara.")
            else:
                temp_dir = utils.storage_dir("temp", create=True)
                fd, tmp_mp3 = tempfile.mkstemp(prefix="kilang-prev-", suffix=".mp3", dir=temp_dir)
                os.close(fd)
                try:
                    sub = voice.tts(
                        text=sample_txt,
                        voice_name=voice.parse_voice_name(st.session_state["voice_name"]),
                        voice_rate=float(st.session_state["voice_rate"]),
                        voice_file=tmp_mp3,
                    )
                    if sub is not None and Path(tmp_mp3).is_file():
                        st.session_state["preview_audio_bytes"] = Path(tmp_mp3).read_bytes()
                    else:
                        st.error("Gagal menjana pratonton Edge TTS.")
                finally:
                    Path(tmp_mp3).unlink(missing_ok=True)

    with act_go:
        cta_label = (
            "Jana Video Sekarang"
            if factory_mode == "single"
            else "Jalankan Kilang Batch (Hingga 3 Video)"
        )
        if st.button(cta_label, type="primary", use_container_width=True):
            source, materials, stock_terms, media_err = _resolve_factory_visual_source(keys)
            bgm_type, bgm_file, bgm_err = _resolve_factory_bgm()
            if media_err:
                st.error(media_err)
            elif bgm_err:
                st.error(bgm_err)
            else:
                jobs: list[tuple[str, str]] = []
                if factory_mode == "single":
                    txt = st.session_state.get("video_script", "").strip()
                    if not txt:
                        st.error("Sila jana atau masukkan skrip suara sebelum memulakan render.")
                    else:
                        jobs.append(("Utama", txt))
                else:
                    for angle_key, angle_meta in ks.BATCH_ANGLES.items():
                        if st.session_state.get(f"batch_enable_{angle_key}", True):
                            txt = st.session_state.get(f"batch_script_{angle_key}", "").strip()
                            if txt:
                                jobs.append((angle_meta["label"], txt))
                    if not jobs:
                        st.error("Isi sekurang-kurangnya satu skrip sudut yang aktif untuk Mod Batch.")

                if jobs:
                    brief = current_brief()
                    default_social = ks.build_offline_social_pack(brief)
                    cap_txt = (
                        st.session_state.get("social_caption", "").strip()
                        or f"{default_social.title}\n\n{default_social.caption}"
                    )
                    tags_raw = st.session_state.get("social_hashtags", "").strip()
                    tags = tuple(tags_raw.split()) if tags_raw else default_social.hashtags

                    rendered_records: list[kv.RenderRecord] = []
                    with st.status(f"Menjana {len(jobs)} video pemasaran...", expanded=True) as status:
                        for idx, (angle_label, script_body) in enumerate(jobs, start=1):
                            status.write(f"[{idx}/{len(jobs)}] Merender sudut **{angle_label}**...")
                            ok, rec, err_msg = _execute_single_render(
                                product_name=brief.product_name,
                                angle_label=angle_label,
                                script_text=script_body,
                                caption_text=cap_txt,
                                hashtags=tags,
                                video_source=source,
                                local_materials=materials,
                                stock_terms=stock_terms,
                                bgm_type=bgm_type,
                                bgm_file=bgm_file,
                                keys=keys,
                            )
                            if ok and rec is not None:
                                rendered_records.append(rec)
                            else:
                                status.update(label="Penghasilan video gagal", state="error")
                                st.error(f"Sudut {angle_label}: {err_msg}")
                                break
                        else:
                            st.session_state["last_batch_renders"] = rendered_records
                            status.update(
                                label=f"Selesai! {len(rendered_records)} video siap dimuat turun.",
                                state="complete",
                            )

    preview_bytes = st.session_state.get("preview_audio_bytes", b"")
    if preview_bytes:
        st.audio(preview_bytes, format="audio/mp3")

    latest_renders: list[kv.RenderRecord] = st.session_state.get("last_batch_renders") or []
    valid_renders = [r for r in latest_renders if Path(r.video_path).is_file()]
    if valid_renders:
        st.divider()
        st.success(f"{len(valid_renders)} video sedia untuk dimuat turun & dimuat naik!")
        r_cols = st.columns(min(len(valid_renders), 3))
        for col, rec in zip(r_cols, valid_renders):
            with col:
                st.markdown(f"**{rec.angle_label} ({rec.aspect})**")
                st.video(rec.video_path)
                dl_name = safe_download_filename(rec.brand_name, rec.angle_label)
                st.download_button(
                    label=f"Muat Turun ({_format_size_mb(rec.file_size_bytes)})",
                    data=Path(rec.video_path).read_bytes(),
                    file_name=dl_name,
                    mime="video/mp4",
                    key=f"dl_{rec.task_id}",
                    use_container_width=True,
                )


def render_browser_flow_tab(keys: dict[str, str]) -> None:
    st.subheader("Pelayar Studio In-House & Pintu Masuk Google Flow")
    browser_exe = sb.detect_local_chromium_browser()

    if browser_exe:
        st.markdown(
            f"""
            <div class="kp-card">
              <h4>Pelayar Studio Terasing Aktif (Desktop Tempatan)</h4>
              <p>Enjin pelayar dikesan di <code>{html.escape(browser_exe)}</code>. Setiap log masuk Google Flow, Whisk, atau TikTok disimpan kekal dalam profil studio dan semua muat turun masuk terus ke <code>storage/flow_inbox/</code>.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="kp-card">
              <h4>Mod Pelayan Awan (Render Live)</h4>
              <p>Pelayan awan Linux tanpa paparan desktop tidak boleh membuka tetingkap Chrome berasingan. Buka pautan studio di tab pelayar anda, jana atau muat turun klip/imej, kemudian lepas terus ke <strong>Peti Masuk Flow</strong> di bawah (atau jalankan <code>kilang.bat</code> di komputer anda untuk Pelayar In-House automatik).</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    portal_cols = st.columns(3)
    for idx, portal in enumerate(sb.STUDIO_PORTALS):
        with portal_cols[idx % 3]:
            st.markdown(
                f"""
                <div class="kp-card">
                  <h4>{html.escape(portal.label)}</h4>
                  <p>{html.escape(portal.description)}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if browser_exe:
                if st.button(f"Buka {portal.label.split('(')[0].strip()}", key=f"open_{portal.id}", use_container_width=True):
                    res = sb.launch_studio_browser(portal.url)
                    if res.ok:
                        st.toast(res.message)
                    else:
                        st.warning(res.message)
            else:
                st.link_button(
                    f"Buka {portal.label.split('(')[0].strip()} ↗",
                    url=portal.url,
                    use_container_width=True,
                )

    c_url, c_go, c_embed = st.columns([3, 1.1, 1.1], vertical_alignment="bottom")
    with c_url:
        custom_url = st.text_input(
            "URL Studio Tersuai (cth. laman web produk anda / Canva / Google Sites)",
            value="https://labs.google/fx/tools/flow",
            key="studio_custom_url",
        )
    with c_go:
        if browser_exe:
            if st.button("Lancar URL", use_container_width=True):
                try:
                    res = sb.launch_studio_browser(custom_url)
                    if res.ok:
                        st.success(res.message)
                    else:
                        st.warning(res.message)
                except ValueError as exc:
                    st.error(str(exc))
        else:
            try:
                safe_custom = sb.validate_portal_url(custom_url)
                st.link_button("Buka URL ↗", url=safe_custom, use_container_width=True)
            except ValueError:
                st.button("URL Tidak Sah", disabled=True, use_container_width=True)
    with c_embed:
        show_iframe = st.checkbox("Pratonton Iframe (Jika Disokong)", key="studio_iframe_toggle")

    if show_iframe:
        try:
            safe_iframe_url = sb.validate_portal_url(custom_url)
            st.caption(
                "Nota: Google Flow & TikTok menyekat paparan iframe (`X-Frame-Options`). "
                "Jika kotak di bawah kosong, gunakan butang **Buka** di atas."
            )
            components.iframe(safe_iframe_url, height=500, scrolling=True)
        except ValueError as exc:
            st.error(str(exc))

    st.divider()
    st.subheader("Penjana Prompt Adegan Google Flow (Veo & Nano Banana 9:16)")
    fp_c1, fp_c2, fp_c3 = st.columns([1.2, 1.4, 1.4], vertical_alignment="bottom")
    with fp_c1:
        scene_count = st.slider("Bilangan Adegan", min_value=2, max_value=6, value=4, key="flow_scene_count")
    with fp_c2:
        if st.button("Jana Prompt Google Flow (Gemini)", type="primary", use_container_width=True):
            fp = ks.generate_google_flow_prompts(
                current_brief(),
                st.session_state.get("video_script", ""),
                scene_count=scene_count,
                api_key=keys.get("gemini", ""),
                model_name=keys.get("gemini_model", ks.DEFAULT_GEMINI_MODEL),
            )
            if fp.ok:
                st.session_state["flow_prompts_list"] = list(fp.prompts)
                st.success(f"{len(fp.prompts)} prompt adegan 9:16 dijana oleh {fp.model_name}.")
            else:
                st.error(fp.error)
    with fp_c3:
        if st.button("Guna Templat Prompt Flow", use_container_width=True):
            fp = ks.build_offline_flow_prompts(current_brief(), scene_count=scene_count)
            st.session_state["flow_prompts_list"] = list(fp.prompts)

    for idx, prompt_line in enumerate(st.session_state.get("flow_prompts_list") or [], start=1):
        st.caption(f"Adegan {idx} — salin dan tampal ke Google Flow:")
        st.code(prompt_line, language="text")

    st.divider()
    st.subheader("Peti Masuk Flow (`storage/flow_inbox/`)")
    inbox_uploads = st.file_uploader(
        "Lepaskan Video/Imej Dari Google Flow, Whisk, atau Pixabay Ke Sini",
        type=["jpg", "jpeg", "png", "bmp", "mp4", "mov", "webm"],
        accept_multiple_files=True,
        key="flow_inbox_uploader",
    )
    if inbox_uploads and st.button("Simpan Muat Naik Ke Peti Masuk Flow", use_container_width=True):
        try:
            saved = sb.save_upload_to_flow_inbox(inbox_uploads)
            st.success(f"Disimpan ke Peti Masuk Flow: {', '.join(saved)}")
        except material_upload.MaterialUploadError as exc:
            st.error(f"Fail ditolak: {exc}")

    items = sb.list_flow_inbox_items()
    if items:
        st.button(
            "Guna Semua Fail Dalam Kilang Video",
            type="primary",
            key="use_all_flow_inbox_btn",
            on_click=_use_flow_inbox_callback,
            args=([item.name for item in items],),
        )

        i_cols = st.columns(3)
        for idx, item in enumerate(items):
            with i_cols[idx % 3]:
                st.markdown(f"**{item.name}** ({_format_size_mb(item.size_bytes)})")
                try:
                    if item.kind == "image":
                        with Image.open(item.path) as img:
                            img.verify()
                        st.image(item.path, use_container_width=True)
                    else:
                        st.video(item.path)
                except (UnidentifiedImageError, OSError, ValueError, RuntimeError):
                    st.warning(f"Pratonton `{item.name}` rosak atau tidak sah. Anda boleh padam fail ini.")
                if st.button("Padam", key=f"del_inbox_{item.name}", use_container_width=True):
                    sb.delete_flow_inbox_item(item.name)
                    st.rerun()


def render_brand_vault_tab() -> None:
    st.subheader("Peti Jenama Klien & Bisnes")
    brands = kv.list_brands()

    b_cols = st.columns(2)
    for idx, brand in enumerate(brands):
        with b_cols[idx % 2]:
            st.markdown(
                f"""
                <div class="kp-card">
                  <h4>{html.escape(brand.label)}</h4>
                  <p><strong>Produk:</strong> {html.escape(brand.product_name)} • <strong>Nisbah:</strong> {html.escape(brand.default_aspect)}</p>
                  <p>{html.escape(brand.offer)}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            c_use, c_del = st.columns(2)
            with c_use:
                st.button(
                    "Muat Ke Kilang Video",
                    key=f"vault_load_{brand.id}",
                    use_container_width=True,
                    on_click=_load_brand_vault_callback,
                    args=(brand,),
                )
            with c_del:
                if st.button("Padam Profil", key=f"vault_del_{brand.id}", use_container_width=True):
                    try:
                        kv.delete_brand(brand.id)
                        st.rerun()
                    except ValueError as exc:
                        st.warning(str(exc))

    st.divider()
    st.subheader("Tambah / Kemas Kini Profil Jenama")
    with st.form("kilang_brand_upsert_form"):
        f1, f2 = st.columns(2)
        with f1:
            b_id = st.text_input("ID Unik (huruf kecil/garis bawah)", placeholder="cth: kedai_kek_kuantan")
            b_label = st.text_input("Label Paparan", placeholder="cth: Kedai Kek Kuantan")
            b_prod = st.text_input("Nama Produk / Jenama")
            b_offer = st.text_input("Tawaran / Harga Utama")
        with f2:
            b_usp = st.text_input("Kelebihan Utama (USP)")
            b_cta = st.text_input("Sasaran & CTA WhatsApp / Kedai")
            b_aspect = st.selectbox("Nisbah Lalai", options=list(ks.ASPECT_OPTIONS.keys()))
            b_color = st.selectbox(
                "Warna Sarikata",
                options=list(ks.SUBTITLE_COLOR_PRESETS.keys()),
                format_func=lambda c: ks.SUBTITLE_COLOR_PRESETS[c],
            )
        b_terms = st.text_input("Kata Kunci Visual Stok Lalai (Inggeris, dipisah koma)")
        submitted = st.form_submit_button("Simpan Profil Ke Peti Jenama", type="primary")
        if submitted:
            try:
                saved = kv.upsert_brand(
                    kv.BrandRecord(
                        id=b_id or b_prod,
                        label=b_label or b_prod,
                        product_name=b_prod,
                        offer=b_offer,
                        usp=b_usp,
                        audience_cta=b_cta,
                        default_aspect=b_aspect,
                        subtitle_color=b_color,
                        visual_terms=tuple(t.strip() for t in b_terms.split(",") if t.strip()),
                    )
                )
                st.success(f"Profil '{saved.label}' disimpan ke Peti Jenama!")
            except ValueError as exc:
                st.error(str(exc))


def render_gallery_tab() -> None:
    st.subheader("Galeri Hasil Video Kilang Pemasaran")
    renders = kv.list_renders(existing_only=True)
    if not renders:
        st.info("Belum ada video yang siap dijana. Pergi ke tab **Kilang Video** untuk menghasilkan video pertama anda.")
        return

    for rec in renders:
        with st.container(border=True):
            g_vid, g_info = st.columns([1, 1.7])
            with g_vid:
                st.video(rec.video_path)
            with g_info:
                st.markdown(f"**{rec.brand_name}** — {rec.angle_label} (`{rec.aspect}`)")
                st.caption(
                    f"Dicipta: {rec.created_at} • Sumber: `{rec.video_source}` • "
                    f"Saiz: {_format_size_mb(rec.file_size_bytes)}"
                )
                st.text_area(
                    "Skrip Narasi",
                    value=rec.script,
                    height=85,
                    disabled=True,
                    key=f"gal_script_{rec.task_id}",
                )
                if rec.caption or rec.hashtags:
                    st.code(
                        f"{rec.caption}\n\n{' '.join(rec.hashtags)}".strip(),
                        language="text",
                    )
                b_dl, b_del = st.columns(2)
                with b_dl:
                    st.download_button(
                        label="Muat Turun MP4",
                        data=Path(rec.video_path).read_bytes(),
                        file_name=safe_download_filename(rec.brand_name, rec.angle_label),
                        mime="video/mp4",
                        key=f"gal_dl_{rec.task_id}",
                        use_container_width=True,
                    )
                with b_del:
                    if st.button("Padam Video", key=f"gal_del_{rec.task_id}", use_container_width=True):
                        kv.delete_render(rec.task_id, remove_files=True)
                        st.rerun()


def render_diagnostics_tab(keys: dict[str, str]) -> None:
    st.subheader("Sambungan & Kesihatan Sistem")
    ffmpeg_ok = utils.check_ffmpeg_ready()
    browser_exe = sb.detect_local_chromium_browser()
    stock = ks.resolve_stock_api_keys(
        pexels_key=keys.get("pexels", ""),
        pixabay_key=keys.get("pixabay", ""),
    )
    useapi_cfg = ks.resolve_useapi_config(token=keys.get("useapi", ""))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _render_badge("FFmpeg: Sedia" if ffmpeg_ok else "FFmpeg: Tiada", warn=not ffmpeg_ok)
    with c2:
        _render_badge("Pelayar In-House: Desktop" if browser_exe else "Mod Awan (Render)", warn=not browser_exe)
    with c3:
        _render_badge(
            "Pixabay: Sedia" if stock["pixabay_api_keys"] else "Pixabay: Tiada",
            warn=not stock["pixabay_api_keys"],
        )
    with c4:
        _render_badge(
            "UseAPI Flow: Sedia" if useapi_cfg["useapi_api_token"] else "UseAPI: Tiada",
            warn=not useapi_cfg["useapi_api_token"],
        )

    st.divider()
    if st.button("Uji Sambungan Gemini & Senarai Model Percuma", type="primary"):
        with st.spinner("Menguji kunci API Gemini dan mengesan model pelan percuma..."):
            diag = ks.test_gemini_connection(
                api_key=keys.get("gemini", ""),
                model_name=keys.get("gemini_model", ks.DEFAULT_GEMINI_MODEL),
            )
        st.session_state["last_gemini_diag"] = diag

    diag = st.session_state.get("last_gemini_diag")
    if isinstance(diag, dict):
        if diag.get("ok"):
            st.success(
                f"Sambungan Gemini berjaya! Model aktif: `{diag.get('model_name')}` "
                f"({diag.get('latency_ms')} ms)."
            )
        else:
            st.error(diag.get("error") or "Sambungan Gemini gagal.")
        discovered = diag.get("discovered_models") or []
        if discovered:
            st.write("Model pelan percuma yang ditemui pada kunci API anda:")
            st.code("\n".join(discovered), language="text")
