"""Malaysian short-video marketing factory adapter built on MoneyPrinterTurbo."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any, Iterable, Literal

from app.config import config
from app.models.schema import (
    ImageMotion,
    MaterialInfo,
    SubtitleAnimation,
    SubtitleDisplayMode,
    VideoAspect,
    VideoConcatMode,
    VideoFitMode,
    VideoParams,
)
from app.services import llm, material_upload
from app.utils import file_security, utils

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_MODEL_OPTIONS: tuple[str, ...] = (
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3.1-pro-preview",
)
GEMINI_FALLBACK_MODELS: tuple[str, ...] = (
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite",
)
MAX_GEMINI_FALLBACK_MODELS = 3
GEMINI_RETRY_DELAY_SECONDS = 1.5
_OVERLOAD_ERROR_MARKERS = ("503", "unavailable", "high demand", "overloaded")
_QUOTA_OR_MISSING_MARKERS = ("429", "resource_exhausted", "limit: 0", "404", "not_found")
_AUTH_ERROR_MARKERS = ("400", "401", "403", "api_key_invalid", "invalid api key")
_EXCLUDED_FREE_MODEL_TOKENS = (
    "pro",
    "embedding",
    "imagen",
    "veo",
    "tts",
    "audio",
    "live",
    "image",
    "robotics",
    "computer-use",
    "deep-research",
    "vision",
    "learnlm",
    "1.0",
    "1.5",
    "2.0",
)

MALAY_VOICES: dict[str, str] = {
    "ms-MY-YasminNeural-Female": "Yasmin (Wanita BM — Mesra & Jelas, Percuma)",
    "ms-MY-OsmanNeural-Male": "Osman (Lelaki BM — Tegas & Meyakinkan, Percuma)",
}
DEFAULT_MALAY_VOICE = "ms-MY-YasminNeural-Female"
DEFAULT_SUBTITLE_FONT = "BeVietnamPro-Bold.ttf"

SCRIPT_STYLES: dict[str, dict[str, str]] = {
    "santai_tiktok": {
        "label": "Santai TikTok / Reels",
        "guidance": (
            "Gaya percakapan harian rakyat Malaysia yang ringkas, bertenaga, dan mudah melekat; "
            "buka dengan hook pantas 2-3 saat pertama."
        ),
    },
    "mesra_komuniti": {
        "label": "Mesra Komuniti Tempatan",
        "guidance": (
            "Nada jujur, mesra kejiranan dan meyakinkan seperti pemilik kedai tempatan bercakap "
            "terus dengan pelanggan tetap."
        ),
    },
    "promosi_pantas": {
        "label": "Promosi Pantas / Flash Deal",
        "guidance": (
            "Terus kepada tawaran, nilai jimat, stok/slot terhad, dan seruan tindakan segera "
            "tanpa ayat meleret."
        ),
    },
}

DURATION_PROFILES: dict[int, dict[str, Any]] = {
    15: {
        "label": "15 saat (~35-45 patah perkataan)",
        "paragraphs": 1,
        "word_range": "35-45",
        "clip_duration": 3,
    },
    30: {
        "label": "30 saat (~70-90 patah perkataan)",
        "paragraphs": 2,
        "word_range": "70-90",
        "clip_duration": 4,
    },
    45: {
        "label": "45 saat (~105-130 patah perkataan)",
        "paragraphs": 3,
        "word_range": "105-130",
        "clip_duration": 5,
    },
}

MALAY_MARKETING_SYSTEM_PROMPT = """
You are an experienced Malaysian short-form video copywriter creating voiceover scripts for TikTok and Instagram Reels.

Strict rules:
1. Write 100% natural spoken Bahasa Melayu (Malaysia) — conversational, warm, direct, and easy for voice narration.
2. NEVER use Indonesian phrasing or vocabulary (avoid "kamu", "banget", "yuk", "diskon", "gratis", "bisa", "cocok", "keren", "hemat"). Use natural Malaysian expressions (such as "anda", "korang", "memang", "jom", "diskaun", "percuma", "boleh", "padu", "berbaloi", "segar").
3. Structure the flow naturally from Hook (attention-grabbing opening in the first 2-3 seconds) -> Value/USP (why this product/service stands out) -> Offer & Clear CTA (WhatsApp / pickup / order now), WITHOUT printing section labels or headings.
4. Output ONLY the spoken narration sentences as plain text. Do NOT include markdown, bullet points, hashtags, emojis, timestamps, camera directions, or [bracketed] / (parenthetical) notes.
5. Keep sentences crisp and punchy so Malaysian Edge TTS (ms-MY) sounds natural and upbeat.
6. Only state facts, prices, locations, and offers provided in the brief — never invent false claims.
""".strip()

_STOCK_ENV_MAP = (
    ("pexels_api_keys", "PEXELS_API_KEY"),
    ("pixabay_api_keys", "PIXABAY_API_KEY"),
)
_SUPPORTED_VIDEO_SOURCES = frozenset({"local", "pexels", "pixabay"})


@dataclass(frozen=True)
class CampaignBrief:
    """User-editable campaign inputs for Malay script and video generation."""

    product_name: str
    offer: str = ""
    usp: str = ""
    audience_cta: str = ""
    style_key: str = "santai_tiktok"
    duration_seconds: int = 30


@dataclass(frozen=True)
class CampaignPreset:
    """Pre-seeded local Malaysian business campaign preset."""

    id: str
    label: str
    product_name: str
    offer: str
    usp: str
    audience_cta: str
    style_key: str
    duration_seconds: int
    visual_terms: tuple[str, ...] = field(default_factory=tuple)

    def to_brief(self) -> CampaignBrief:
        return CampaignBrief(
            product_name=self.product_name,
            offer=self.offer,
            usp=self.usp,
            audience_cta=self.audience_cta,
            style_key=self.style_key,
            duration_seconds=self.duration_seconds,
        )


CAMPAIGN_PRESETS: tuple[CampaignPreset, ...] = (
    CampaignPreset(
        id="radhi_fruits",
        label="Radhi Fruits 4690 (Kemaman)",
        product_name="Radhi Fruits 4690",
        offer="Stok durian kampung, Musang King & buah bermusim segar turun harian",
        usp="Buah dipilih segar setiap pagi, isi tebal berlemak, boleh semak kualiti terus sebelum bawa balik",
        audience_cta="Penduduk Kemaman & sekitar — WhatsApp untuk semak stok hari ini atau terus pickup di kedai",
        style_key="santai_tiktok",
        duration_seconds=30,
        visual_terms=(
            "fresh tropical fruit market",
            "durian fruit close up",
            "happy customer buying fresh fruit",
        ),
    ),
    CampaignPreset(
        id="pedalhaus_chukai",
        label="PedalHaus Chukai (Kafe & Minuman)",
        product_name="PedalHaus Chukai",
        offer="Koleksi Premium PedalHaus — kopi bru segar & pencuci mulut istimewa harian",
        usp="Rasa kopi seimbang tak terlalu manis, suasana santai di Chukai, sesuai untuk lepak atau tapau kerja",
        audience_cta="Warga Chukai & Kemaman — singgah dine-in, tapau atau pickup hari ini",
        style_key="santai_tiktok",
        duration_seconds=30,
        visual_terms=(
            "iced coffee pour cafe",
            "artisan coffee shop interior",
            "fresh pastry dessert table",
        ),
    ),
    CampaignPreset(
        id="van_sekolah_binjai",
        label="Servis Van Sekolah Binjai",
        product_name="Servis Van Sekolah Binjai",
        offer="Laluan SK Binjai, SMK Binjai, SK Sri Jaya & PASTI serta peluang pemandu berlesen PSV",
        usp="Pengangkutan pagi dan petang yang menepati masa, pemandu berpengalaman & keutamaan keselamatan pelajar",
        audience_cta="Ibu bapa & calon pemandu sekitar Binjai, Kemaman — WhatsApp terus untuk semak laluan dan slot kosong",
        style_key="mesra_komuniti",
        duration_seconds=30,
        visual_terms=(
            "morning school commute van",
            "friendly driver smiling",
            "students walking safely to school",
        ),
    ),
    CampaignPreset(
        id="produk_umum",
        label="Kempen Produk Umum (PKS Malaysia)",
        product_name="Produk Pilihan Tempatan",
        offer="Tawaran khas minggu ini dengan penghantaran pantas seluruh Malaysia",
        usp="Kualiti terjaga, harga berpatutan, mudah digunakan setiap hari",
        audience_cta="Pembeli dalam talian Malaysia — klik pautan atau WhatsApp sekarang sementara stok masih ada",
        style_key="promosi_pantas",
        duration_seconds=30,
        visual_terms=(
            "small business packaging order",
            "happy customer unboxing product",
            "smartphone online shopping",
        ),
    ),
)

_PRESETS_BY_ID: dict[str, CampaignPreset] = {preset.id: preset for preset in CAMPAIGN_PRESETS}


@dataclass(frozen=True)
class ScriptGenerationResult:
    """Structured result from script generation or explicit offline drafting."""

    ok: bool
    script: str
    source: Literal["gemini", "offline_template", "error"]
    model_name: str = ""
    error: str = ""


def get_preset(preset_id: str) -> CampaignPreset:
    if preset_id in _PRESETS_BY_ID:
        return _PRESETS_BY_ID[preset_id]
    raise KeyError(f"Unknown campaign preset: {preset_id}")


def load_dotenv_if_present(env_path: Path | None = None) -> None:
    """Load key=value pairs from `.env` without overwriting existing process env vars."""
    target = env_path or (Path(utils.root_dir()) / ".env")
    if not target.is_file():
        return

    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value


def resolve_gemini_runtime_config(
    api_key: str = "",
    model_name: str = "",
) -> dict[str, Any]:
    """Resolve an isolated per-request Gemini config dict without mutating config.app."""
    load_dotenv_if_present()
    resolved_key = (
        api_key.strip()
        or os.getenv("GEMINI_API_KEY", "").strip()
        or str(config.app.get("gemini_api_key", "") or "").strip()
    )
    resolved_model = (
        model_name.strip()
        or os.getenv("GEMINI_MODEL_NAME", "").strip()
        or str(config.app.get("gemini_model_name", "") or "").strip()
        or DEFAULT_GEMINI_MODEL
    )
    resolved_base_url = str(config.app.get("gemini_base_url", "") or "").strip()
    return {
        "llm_provider": "gemini",
        "gemini_api_key": resolved_key,
        "gemini_model_name": resolved_model,
        "gemini_base_url": resolved_base_url,
    }


def resolve_stock_api_keys(
    pexels_key: str = "",
    pixabay_key: str = "",
) -> dict[str, list[str]]:
    """Resolve Pexels/Pixabay keys from explicit input, environment, or config.app."""
    load_dotenv_if_present()
    explicit_map = {
        "pexels_api_keys": pexels_key.strip(),
        "pixabay_api_keys": pixabay_key.strip(),
    }
    resolved: dict[str, list[str]] = {}
    for cfg_key, env_name in _STOCK_ENV_MAP:
        explicit_val = explicit_map[cfg_key]
        if explicit_val:
            resolved[cfg_key] = [explicit_val]
            continue
        env_val = os.getenv(env_name, "").strip()
        if env_val:
            resolved[cfg_key] = [env_val]
            continue
        existing = config.app.get(cfg_key) or []
        if isinstance(existing, str):
            existing = [existing] if existing.strip() else []
        resolved[cfg_key] = [str(item).strip() for item in existing if str(item).strip()]
    return resolved


def _duration_profile(duration_seconds: int) -> dict[str, Any]:
    if duration_seconds in DURATION_PROFILES:
        return DURATION_PROFILES[duration_seconds]
    return DURATION_PROFILES[30]


def _redact_secret(message: str, secret: str) -> str:
    clean = str(message or "")
    if secret:
        clean = clean.replace(secret, "***")
    return clean


def build_malay_brief_requirements(brief: CampaignBrief) -> str:
    """Format campaign brief fields into concise Malay creative constraints for Gemini."""
    profile = _duration_profile(brief.duration_seconds)
    style = SCRIPT_STYLES.get(brief.style_key, SCRIPT_STYLES["santai_tiktok"])
    lines = [
        f"- Jenama / Produk: {brief.product_name.strip()}",
        f"- Gaya Skrip: {style['label']} ({style['guidance']})",
        f"- Sasaran Panjang: ~{profile['word_range']} patah perkataan (untuk video ~{brief.duration_seconds} saat)",
    ]
    if brief.offer.strip():
        lines.append(f"- Tawaran / Harga: {brief.offer.strip()}")
    if brief.usp.strip():
        lines.append(f"- Kelebihan Utama (USP): {brief.usp.strip()}")
    if brief.audience_cta.strip():
        lines.append(f"- Sasaran & Seruan Tindakan (CTA): {brief.audience_cta.strip()}")
    return "\n".join(lines)


def _clean_generated_script(text: str) -> str:
    """Strip markdown artifacts and stage directions while keeping spoken narration clean."""
    cleaned = llm._strip_code_fence(str(text or "")).replace("*", "")
    cleaned = re.sub(
        r"(?m)^[ \t]{0,3}#{1,6}[ \t]+(.*?)[ \t]*$",
        lambda match: re.sub(r"[ \t]+#+[ \t]*$", "", match.group(1)),
        cleaned,
    )
    cleaned = re.sub(
        r"\[([^\]\n]+)\]\((?:[^()\n]|\([^()\n]*\))*\)",
        lambda match: match.group(1),
        cleaned,
    )
    cleaned = re.sub(r"\[.*?\]", "", cleaned)
    cleaned = re.sub(r"\(.*?\)", "", cleaned)
    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    return "\n\n".join(paragraphs).strip()


def _is_overload_error(detail: str) -> bool:
    lowered = str(detail or "").lower()
    return any(marker in lowered for marker in _OVERLOAD_ERROR_MARKERS)


def _is_quota_or_missing_model_error(detail: str) -> bool:
    lowered = str(detail or "").lower()
    return any(marker in lowered for marker in _QUOTA_OR_MISSING_MARKERS)


def _is_auth_or_request_error(detail: str) -> bool:
    lowered = str(detail or "").lower()
    return any(marker in lowered for marker in _AUTH_ERROR_MARKERS)


def _free_tier_model_sort_key(model_id: str) -> tuple[int, tuple[int, ...], str]:
    lowered = model_id.lower()
    if "flash-lite" in lowered:
        tier = 0
    elif "flash" in lowered:
        tier = 1
    else:
        tier = 2
    version_nums = tuple(-int(part) for part in re.findall(r"\d+", lowered))
    return (tier, version_nums, lowered)


def discover_free_tier_gemini_models(api_key: str, base_url: str = "") -> list[str]:
    """List and rank active Free-Tier-eligible Flash-Lite / Flash / Gemma-3 text models."""
    if not api_key:
        return []
    try:
        from google import genai
        from google.genai import types

        http_options = types.HttpOptions(base_url=base_url) if base_url else None
        candidates: list[str] = []
        with genai.Client(api_key=api_key, http_options=http_options) as client:
            for model in client.models.list():
                actions = getattr(model, "supported_actions", None) or []
                if actions and "generateContent" not in actions:
                    continue
                name = str(getattr(model, "name", "") or "").removeprefix("models/").strip()
                lowered = name.lower()
                if not (lowered.startswith("gemini-") or lowered.startswith("gemma-3")):
                    continue
                if any(token in lowered for token in _EXCLUDED_FREE_MODEL_TOKENS):
                    continue
                if name not in candidates:
                    candidates.append(name)
        candidates.sort(key=_free_tier_model_sort_key)
        return candidates
    except Exception:
        return []


def _format_gemini_error_bm(model_name: str, detail: str) -> str:
    lowered = str(detail or "").lower()
    if "limit: 0" in lowered:
        return (
            f"Model {model_name} tiada kuota pada pelan percuma Google AI Studio (limit: 0). "
            "Sila pilih model Flash / Flash-Lite di panel kiri seperti gemini-3.8-flash atau "
            "gemini-3.5-flash-lite."
        )
    if _is_overload_error(lowered):
        return (
            f"Pelayan Google Gemini ({model_name}) sedang sesak buat sementara waktu "
            "(503 UNAVAILABLE). Sila cuba klik semula beberapa saat lagi, tukar model di panel "
            "kiri, atau guna 'Guna Draf Templat Tempatan (Tanpa AI)'."
        )
    if any(k in lowered for k in ("429", "resource_exhausted")):
        return (
            f"Had penggunaan sementara Google Gemini ({model_name}) penuh (429). "
            "Tunggu sebentar atau tukar model lain di panel kiri."
        )
    return f"Ralat Gemini ({model_name}): {detail}"


def _run_gemini_once(prompt: str, runtime_cfg: dict[str, Any], resolved_key: str) -> tuple[str, str]:
    """Execute one Gemini call and return `(raw_text, error_detail)` with key redacted."""
    try:
        raw_response = llm._generate_response(prompt=prompt, app_config=runtime_cfg)
    except Exception as exc:
        return "", _redact_secret(str(exc), resolved_key)

    raw_text = str(raw_response or "").strip()
    if not raw_text:
        return "", "respons kosong"
    if raw_text.startswith("Error:"):
        return "", _redact_secret(raw_text.removeprefix("Error:").strip(), resolved_key)
    return raw_text, ""


def _build_free_tier_fallbacks(
    primary_model: str,
    api_key: str,
    base_url: str,
) -> list[str]:
    ordered: list[str] = []
    for candidate in (
        *discover_free_tier_gemini_models(api_key, base_url=base_url),
        *GEMINI_FALLBACK_MODELS,
    ):
        if candidate != primary_model and candidate not in ordered:
            ordered.append(candidate)
        if len(ordered) >= MAX_GEMINI_FALLBACK_MODELS:
            break
    return ordered


def _finalize_gemini_result(model_name: str, raw_text: str) -> ScriptGenerationResult:
    cleaned = _clean_generated_script(raw_text)
    if not cleaned:
        return ScriptGenerationResult(
            ok=False,
            script="",
            source="error",
            model_name=model_name,
            error=f"Gemini ({model_name}) tidak memulangkan teks narasi yang sah.",
        )
    return ScriptGenerationResult(
        ok=True,
        script=cleaned,
        source="gemini",
        model_name=model_name,
    )


def generate_malay_script(
    brief: CampaignBrief,
    *,
    api_key: str = "",
    model_name: str = "",
) -> ScriptGenerationResult:
    """Generate a natural Malaysian Bahasa Melayu marketing script via Google Gemini."""
    product_name = brief.product_name.strip()
    if not product_name:
        return ScriptGenerationResult(
            ok=False,
            script="",
            source="error",
            error="Sila masukkan nama produk atau jenama terlebih dahulu.",
        )

    runtime_cfg = resolve_gemini_runtime_config(api_key=api_key, model_name=model_name)
    resolved_key = runtime_cfg["gemini_api_key"]
    resolved_model = runtime_cfg["gemini_model_name"]
    if not resolved_key:
        return ScriptGenerationResult(
            ok=False,
            script="",
            source="error",
            model_name=resolved_model,
            error=(
                "Kunci API Gemini belum ditetapkan. Masukkan Kunci API Gemini di panel "
                "tepi atau tetapkan pembolehubah persekitaran GEMINI_API_KEY."
            ),
        )

    profile = _duration_profile(brief.duration_seconds)
    requirements = build_malay_brief_requirements(brief)
    prompt = llm.build_script_prompt(
        video_subject=product_name,
        language="Bahasa Melayu (Malaysia)",
        paragraph_number=profile["paragraphs"],
        video_script_prompt=requirements,
        custom_system_prompt=MALAY_MARKETING_SYSTEM_PROMPT,
    )

    raw_text, error_detail = _run_gemini_once(prompt, runtime_cfg, resolved_key)
    if not error_detail:
        return _finalize_gemini_result(resolved_model, raw_text)

    if _is_auth_or_request_error(error_detail):
        return ScriptGenerationResult(
            ok=False,
            script="",
            source="error",
            model_name=resolved_model,
            error=_format_gemini_error_bm(resolved_model, error_detail),
        )

    attempt_queue: list[str] = []
    if _is_overload_error(error_detail):
        attempt_queue.append(resolved_model)
    elif not _is_quota_or_missing_model_error(error_detail):
        return ScriptGenerationResult(
            ok=False,
            script="",
            source="error",
            model_name=resolved_model,
            error=_format_gemini_error_bm(resolved_model, error_detail),
        )

    attempt_queue.extend(
        _build_free_tier_fallbacks(
            resolved_model,
            resolved_key,
            runtime_cfg.get("gemini_base_url", ""),
        )
    )

    last_model = resolved_model
    last_error = error_detail
    for candidate_model in attempt_queue:
        time.sleep(GEMINI_RETRY_DELAY_SECONDS)
        attempt_cfg = {**runtime_cfg, "gemini_model_name": candidate_model}
        cand_text, cand_err = _run_gemini_once(prompt, attempt_cfg, resolved_key)
        last_model = candidate_model
        if not cand_err:
            return _finalize_gemini_result(candidate_model, cand_text)
        last_error = cand_err
        if _is_auth_or_request_error(cand_err):
            break

    return ScriptGenerationResult(
        ok=False,
        script="",
        source="error",
        model_name=last_model,
        error=_format_gemini_error_bm(last_model, last_error),
    )


def generate_visual_terms(
    brief: CampaignBrief,
    script: str,
    *,
    amount: int = 5,
    api_key: str = "",
    model_name: str = "",
) -> list[str]:
    """Generate ordered English stock-footage keywords from a Bahasa Melayu script via Gemini."""
    runtime_cfg = resolve_gemini_runtime_config(api_key=api_key, model_name=model_name)
    resolved_key = runtime_cfg["gemini_api_key"]
    if not resolved_key:
        raise ValueError(
            "Kunci API Gemini diperlukan untuk menjana kata kunci visual stok secara automatik."
        )

    subject = brief.product_name.strip() or "Malaysian local product"
    try:
        terms = llm.generate_terms(
            video_subject=subject,
            video_script=script.strip() or subject,
            amount=amount,
            match_script_order=True,
            app_config=runtime_cfg,
            keyword_language="en",
        )
    except Exception as exc:
        raise ValueError(
            f"Gagal menjana kata kunci visual: {_redact_secret(str(exc), resolved_key)}"
        ) from exc

    cleaned_terms = [str(term).strip() for term in (terms or []) if str(term).strip()]
    if not cleaned_terms:
        raise ValueError("Gemini tidak memulangkan kata kunci visual yang sah.")
    return cleaned_terms


def build_offline_template_script(brief: CampaignBrief) -> ScriptGenerationResult:
    """Create an explicit offline Bahasa Melayu starter script (non-AI fallback)."""
    product = brief.product_name.strip() or "produk tempatan pilihan"
    offer = brief.offer.strip() or "tawaran khas stok terhad hari ini"
    usp = brief.usp.strip() or "kualiti terjamin dan memang berbaloi untuk anda cuba"
    cta = brief.audience_cta.strip() or "WhatsApp kami sekarang sebelum stok habis"

    if brief.duration_seconds <= 15:
        script = f"Tengah cari {product}? {offer}. {usp}. {cta}!"
    elif brief.duration_seconds >= 45:
        script = (
            f"Ramai pelanggan selalu tanya mana nak dapat {product} yang betul-betul puas hati. "
            f"Hari ini ada {offer}.\n\n"
            f"Yang paling best, {usp}. Memang sesuai untuk kegunaan harian atau kongsi bersama keluarga.\n\n"
            f"Stok dan slot harian cepat penuh. {cta} hari ini juga."
        )
    else:
        script = (
            f"Orang ramai tengah cari {product}? Jangan terlepas {offer}. "
            f"{usp}.\n\n"
            f"Tak perlu tunggu lama, {cta} sekarang sebelum stok hari ini habis."
        )

    return ScriptGenerationResult(
        ok=True,
        script=script,
        source="offline_template",
        model_name="offline_template",
    )


def get_sample_material_paths() -> list[str]:
    """Return existing 9:16 sample PNG paths under resource/kilang_samples."""
    sample_dir = Path(utils.root_dir()) / "resource" / "kilang_samples"
    paths = sorted(sample_dir.glob("radhi_fruits_*.png"))
    return [str(path) for path in paths if path.is_file()]


def stage_sample_materials() -> list[MaterialInfo]:
    """Stage demo sample visuals inside storage/local_videos/kilang_samples for local render."""
    sample_paths = [Path(path) for path in get_sample_material_paths()]
    if not sample_paths:
        raise FileNotFoundError(
            "Fail sampel visual tidak ditemui dalam resource/kilang_samples."
        )

    local_videos_dir = Path(material_upload.uploaded_material_dir(create=True))
    target_dir = local_videos_dir / "kilang_samples"
    target_dir.mkdir(parents=True, exist_ok=True)

    staged: list[MaterialInfo] = []
    for src in sample_paths:
        dst = target_dir / src.name
        if not dst.is_file() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
        rel_url = f"kilang_samples/{src.name}"
        file_security.resolve_path_within_directory(str(local_videos_dir), rel_url)
        staged.append(MaterialInfo(provider="local", url=rel_url))
    return staged


def stage_uploaded_materials(uploaded_files: Iterable[Any]) -> list[MaterialInfo]:
    """Validate and stage uploaded product media through upstream material_upload."""
    staged: list[MaterialInfo] = []
    for uploaded in uploaded_files:
        filename = getattr(uploaded, "name", "") or "material.bin"
        stored_name = material_upload.save_material_upload(filename, uploaded)
        staged.append(MaterialInfo(provider="local", url=stored_name))
    return staged


def resolve_subtitle_font(preferred: str = DEFAULT_SUBTITLE_FONT) -> str:
    """Resolve an existing bundled font filename for Malay/Latin subtitles."""
    font_dir = Path(utils.font_dir())
    if preferred and (font_dir / preferred).is_file():
        return preferred
    for fallback in ("BeVietnamPro-Bold.ttf", "BeVietnamPro-Medium.ttf", "STHeitiMedium.ttc"):
        if (font_dir / fallback).is_file():
            return fallback
    candidates = sorted(
        path.name for path in font_dir.iterdir() if path.suffix.lower() in {".ttf", ".ttc", ".otf"}
    )
    return candidates[0] if candidates else preferred


def build_tiktok_video_params(
    *,
    product_name: str,
    script: str,
    video_source: str = "local",
    local_materials: list[MaterialInfo] | None = None,
    video_terms: str | list[str] | None = None,
    voice_name: str = DEFAULT_MALAY_VOICE,
    voice_rate: float = 1.05,
    subtitle_enabled: bool = True,
    subtitle_display_mode: SubtitleDisplayMode = "sentence",
    subtitle_animation: SubtitleAnimation = "pop_spring",
    subtitle_position: str = "bottom",
    bgm_type: str = "random",
    bgm_volume: float = 0.15,
    clip_duration: int = 4,
    font_name: str = DEFAULT_SUBTITLE_FONT,
) -> VideoParams:
    """Build validated 9:16 TikTok/Reels VideoParams ready for task.start."""
    clean_subject = product_name.strip() or "Kempen Video Kilang Pemasaran"
    clean_script = script.strip()
    if not clean_script:
        raise ValueError("Skrip suara tidak boleh kosong sebelum menjana video.")

    source = video_source.strip().lower()
    if source not in _SUPPORTED_VIDEO_SOURCES:
        raise ValueError(f"Sumber video tidak disokong: {video_source}")

    materials_arg: list[MaterialInfo] | None = None
    terms_arg: str | list[str] | None = None
    if source == "local":
        if not local_materials:
            raise ValueError("Sila muat naik media produk atau pilih sampel visual dahulu.")
        materials_arg = list(local_materials)
    else:
        if isinstance(video_terms, str):
            parsed_terms = [t.strip() for t in video_terms.split(",") if t.strip()]
        else:
            parsed_terms = [str(t).strip() for t in (video_terms or []) if str(t).strip()]
        if not parsed_terms:
            raise ValueError("Kata kunci visual stok diperlukan untuk Pexels/Pixabay.")
        terms_arg = parsed_terms

    return VideoParams(
        video_subject=clean_subject,
        video_script=clean_script,
        video_terms=terms_arg,
        video_aspect=VideoAspect.portrait,
        video_fit_mode=VideoFitMode.cover,
        image_motion=ImageMotion.zoom,
        video_concat_mode=VideoConcatMode.sequential,
        video_clip_duration=max(2, int(clip_duration)),
        video_count=1,
        video_source=source,
        video_materials=materials_arg,
        voice_name=voice_name or DEFAULT_MALAY_VOICE,
        voice_rate=float(voice_rate),
        voice_volume=1.0,
        bgm_type=bgm_type,
        bgm_volume=float(bgm_volume),
        subtitle_enabled=bool(subtitle_enabled),
        subtitle_position=subtitle_position,
        subtitle_display_mode=subtitle_display_mode,
        subtitle_animation=subtitle_animation,
        font_name=resolve_subtitle_font(font_name),
        text_fore_color="#FFFFFF",
        stroke_color="#000000",
        stroke_width=2.0,
        font_size=62,
    )
