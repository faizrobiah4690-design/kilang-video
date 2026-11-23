"""Persistent Brand Vault and Render Output Gallery stores for Kilang Pemasaran."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
from typing import Any

from app.services import kilang_studio as ks
from app.utils import file_security, utils

_VAULT_LOCK = threading.RLock()


@dataclass(frozen=True)
class BrandRecord:
    """Reusable client brand configuration saved in storage/kilang_brands.json."""

    id: str
    label: str
    product_name: str
    offer: str = ""
    usp: str = ""
    audience_cta: str = ""
    style_key: str = "santai_tiktok"
    duration_seconds: int = 30
    default_voice: str = ks.DEFAULT_MALAY_VOICE
    subtitle_color: str = "#FFFFFF"
    default_aspect: str = "9:16"
    visual_terms: tuple[str, ...] = field(default_factory=tuple)

    def to_brief(self, *, duration_override: int | None = None) -> ks.CampaignBrief:
        return ks.CampaignBrief(
            product_name=self.product_name,
            offer=self.offer,
            usp=self.usp,
            audience_cta=self.audience_cta,
            style_key=self.style_key,
            duration_seconds=int(duration_override or self.duration_seconds or 30),
        )


@dataclass(frozen=True)
class RenderRecord:
    """Completed factory render metadata saved in storage/kilang_history.json."""

    task_id: str
    created_at: str
    brand_name: str
    angle_label: str
    aspect: str
    script: str
    caption: str
    hashtags: tuple[str, ...]
    video_path: str
    file_size_bytes: int
    voice_name: str
    video_source: str


def _default_brands_path() -> Path:
    return Path(utils.storage_dir(create=True)) / "kilang_brands.json"


def _default_history_path() -> Path:
    return Path(utils.storage_dir(create=True)) / "kilang_history.json"


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def _brand_from_dict(raw: dict[str, Any]) -> BrandRecord:
    terms = raw.get("visual_terms") or ()
    return BrandRecord(
        id=str(raw.get("id", "")).strip(),
        label=str(raw.get("label", "")).strip(),
        product_name=str(raw.get("product_name", "")).strip(),
        offer=str(raw.get("offer", "")),
        usp=str(raw.get("usp", "")),
        audience_cta=str(raw.get("audience_cta", "")),
        style_key=str(raw.get("style_key", "santai_tiktok")),
        duration_seconds=int(raw.get("duration_seconds", 30) or 30),
        default_voice=str(raw.get("default_voice", ks.DEFAULT_MALAY_VOICE)),
        subtitle_color=str(raw.get("subtitle_color", "#FFFFFF")),
        default_aspect=str(raw.get("default_aspect", "9:16")),
        visual_terms=tuple(str(t).strip() for t in terms if str(t).strip()),
    )


def _seed_brands_from_presets() -> list[BrandRecord]:
    return [
        BrandRecord(
            id=preset.id,
            label=preset.label,
            product_name=preset.product_name,
            offer=preset.offer,
            usp=preset.usp,
            audience_cta=preset.audience_cta,
            style_key=preset.style_key,
            duration_seconds=preset.duration_seconds,
            default_voice=ks.DEFAULT_MALAY_VOICE,
            subtitle_color="#FFFFFF",
            default_aspect="9:16",
            visual_terms=preset.visual_terms,
        )
        for preset in ks.CAMPAIGN_PRESETS
    ]


def _load_brands_raw(path: Path) -> list[BrandRecord]:
    if not path.is_file():
        seeded = _seed_brands_from_presets()
        _atomic_write_json(path, [asdict(item) for item in seeded])
        return seeded
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return [_brand_from_dict(row) for row in data if isinstance(row, dict)]
    except (OSError, ValueError):
        pass
    seeded = _seed_brands_from_presets()
    _atomic_write_json(path, [asdict(item) for item in seeded])
    return seeded


def list_brands(store_path: Path | None = None) -> list[BrandRecord]:
    path = store_path or _default_brands_path()
    with _VAULT_LOCK:
        return _load_brands_raw(path)


def get_brand(brand_id: str, store_path: Path | None = None) -> BrandRecord:
    for item in list_brands(store_path=store_path):
        if item.id == brand_id:
            return item
    raise KeyError(f"Jenama tidak ditemui: {brand_id}")


def upsert_brand(record: BrandRecord, store_path: Path | None = None) -> BrandRecord:
    clean_id = record.id.strip().lower().replace(" ", "_")
    if not clean_id or not record.product_name.strip():
        raise ValueError("ID jenama dan nama produk wajib diisi.")
    normalized = BrandRecord(
        id=clean_id,
        label=record.label.strip() or record.product_name.strip(),
        product_name=record.product_name.strip(),
        offer=record.offer.strip(),
        usp=record.usp.strip(),
        audience_cta=record.audience_cta.strip(),
        style_key=record.style_key,
        duration_seconds=int(record.duration_seconds or 30),
        default_voice=record.default_voice or ks.DEFAULT_MALAY_VOICE,
        subtitle_color=record.subtitle_color or "#FFFFFF",
        default_aspect=record.default_aspect or "9:16",
        visual_terms=tuple(t.strip() for t in record.visual_terms if t.strip()),
    )
    path = store_path or _default_brands_path()
    with _VAULT_LOCK:
        brands = _load_brands_raw(path)
        updated = [item for item in brands if item.id != normalized.id]
        if any(item.id == normalized.id for item in brands):
            updated = [
                normalized if item.id == normalized.id else item for item in brands
            ]
        else:
            updated.append(normalized)
        _atomic_write_json(path, [asdict(item) for item in updated])
    return normalized


def delete_brand(brand_id: str, store_path: Path | None = None) -> bool:
    path = store_path or _default_brands_path()
    with _VAULT_LOCK:
        brands = _load_brands_raw(path)
        remaining = [item for item in brands if item.id != brand_id]
        if len(remaining) == len(brands):
            return False
        if not remaining:
            raise ValueError("Sekurang-kurangnya satu profil jenama mesti dikekalkan.")
        _atomic_write_json(path, [asdict(item) for item in remaining])
    return True


def _render_from_dict(raw: dict[str, Any]) -> RenderRecord:
    hashtags = raw.get("hashtags") or ()
    return RenderRecord(
        task_id=str(raw.get("task_id", "")).strip(),
        created_at=str(raw.get("created_at", "")).strip(),
        brand_name=str(raw.get("brand_name", "")).strip(),
        angle_label=str(raw.get("angle_label", "Utama")).strip(),
        aspect=str(raw.get("aspect", "9:16")).strip(),
        script=str(raw.get("script", "")),
        caption=str(raw.get("caption", "")),
        hashtags=tuple(str(tag).strip() for tag in hashtags if str(tag).strip()),
        video_path=str(raw.get("video_path", "")).strip(),
        file_size_bytes=int(raw.get("file_size_bytes", 0) or 0),
        voice_name=str(raw.get("voice_name", ks.DEFAULT_MALAY_VOICE)),
        video_source=str(raw.get("video_source", "local")),
    )


def _load_renders_raw(path: Path) -> list[RenderRecord]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [_render_from_dict(row) for row in data if isinstance(row, dict)]
    except (OSError, ValueError):
        pass
    return []


def list_renders(
    *, existing_only: bool = True, store_path: Path | None = None
) -> list[RenderRecord]:
    path = store_path or _default_history_path()
    with _VAULT_LOCK:
        items = _load_renders_raw(path)
    items.sort(key=lambda item: item.created_at, reverse=True)
    if existing_only:
        items = [item for item in items if item.video_path and Path(item.video_path).is_file()]
    return items


def record_render(record: RenderRecord, store_path: Path | None = None) -> RenderRecord:
    path = store_path or _default_history_path()
    with _VAULT_LOCK:
        items = _load_renders_raw(path)
        items = [item for item in items if item.task_id != record.task_id]
        items.insert(0, record)
        _atomic_write_json(path, [asdict(item) for item in items[:200]])
    return record


def delete_render(
    task_id: str,
    *,
    store_path: Path | None = None,
    remove_files: bool = True,
) -> bool:
    clean_id = (task_id or "").strip()
    if (
        not clean_id
        or clean_id in {".", ".."}
        or "/" in clean_id
        or "\\" in clean_id
        or ".." in clean_id
    ):
        raise ValueError("ID tugas tidak sah.")

    path = store_path or _default_history_path()
    with _VAULT_LOCK:
        items = _load_renders_raw(path)
        remaining = [item for item in items if item.task_id != clean_id]
        removed = len(remaining) != len(items)
        if removed:
            _atomic_write_json(path, [asdict(item) for item in remaining])

    if remove_files:
        tasks_root = utils.storage_dir("tasks", create=True)
        tasks_root_real = Path(os.path.realpath(tasks_root))
        resolved = Path(
            file_security.resolve_path_within_directory(
                tasks_root, clean_id, require_file=False
            )
        )
        if resolved == tasks_root_real or resolved.parent != tasks_root_real:
            raise ValueError("ID tugas tidak sah.")
        if resolved.is_dir():
            shutil.rmtree(resolved, ignore_errors=True)
            return True
    return removed
