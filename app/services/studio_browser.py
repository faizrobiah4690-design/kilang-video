"""In-house isolated Chromium studio launcher and Google Flow inbox bridge."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Iterable, Literal
from urllib.parse import urlsplit

from app.models.schema import MaterialInfo
from app.services import material_upload
from app.utils import file_security, utils


@dataclass(frozen=True)
class StudioPortal:
    """Bookmarkable web studio portal usable with the In-House Studio Browser."""

    id: str
    label: str
    url: str
    description: str
    supports_iframe: bool = False


STUDIO_PORTALS: tuple[StudioPortal, ...] = (
    StudioPortal(
        id="google_flow",
        label="Google Flow (Veo & Nano Banana)",
        url="https://labs.google/fx/tools/flow",
        description="Log masuk Google Flow untuk jana klip Veo atau visual produk berkualiti tinggi.",
    ),
    StudioPortal(
        id="google_whisk",
        label="Google Whisk",
        url="https://labs.google/fx/tools/whisk",
        description="Gabung imej produk, latar belakang, dan gaya visual baharu di Google Labs.",
    ),
    StudioPortal(
        id="google_ai_studio",
        label="Google AI Studio (API Key)",
        url="https://aistudio.google.com/app/apikey",
        description="Urus atau jana kunci API Google Gemini serta semak had penggunaan pelan percuma.",
    ),
    StudioPortal(
        id="pixabay",
        label="Pixabay Videos & Photos",
        url="https://pixabay.com/videos/",
        description="Cari atau muat turun video stok percuma terus ke Peti Masuk Flow.",
    ),
    StudioPortal(
        id="canva",
        label="Canva Studio",
        url="https://www.canva.com/",
        description="Rekaan poster/video produk pantas sebelum dieksport ke Kilang Video.",
    ),
    StudioPortal(
        id="tiktok_studio",
        label="TikTok Upload Studio",
        url="https://www.tiktok.com/creator-center/upload",
        description="Muat naik terus video MP4 dan kapsyen yang telah siap ke TikTok.",
    ),
)

_PORTALS_BY_ID: dict[str, StudioPortal] = {portal.id: portal for portal in STUDIO_PORTALS}


@dataclass(frozen=True)
class BrowserLaunchResult:
    """Outcome of launching or inspecting the in-house studio browser."""

    ok: bool
    mode: Literal["desktop", "cloud", "error"]
    message: str
    url: str = ""
    browser_path: str = ""


@dataclass(frozen=True)
class FlowInboxItem:
    """Media file staged inside storage/flow_inbox ready for Kilang Video import."""

    name: str
    path: str
    kind: Literal["video", "image"]
    size_bytes: int
    modified_ts: float


def get_portal(portal_id: str) -> StudioPortal:
    if portal_id in _PORTALS_BY_ID:
        return _PORTALS_BY_ID[portal_id]
    raise KeyError(f"Unknown studio portal: {portal_id}")


def browser_profile_dir(create: bool = True) -> Path:
    return Path(utils.storage_dir("studio_browser_profile", create=create))


def flow_inbox_dir(create: bool = True) -> Path:
    return Path(utils.storage_dir("flow_inbox", create=create))


def validate_portal_url(url: str) -> str:
    """Allow only clean http(s) URLs with a valid host and zero control characters."""
    raw = str(url or "").strip()
    if not raw or any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        raise ValueError("URL tidak sah.")
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Hanya URL http:// atau https:// yang sah dibenarkan.")
    return raw


def _browser_candidates() -> list[str]:
    if sys.platform == "win32":
        roots = [
            os.getenv("ProgramFiles", r"C:\Program Files"),
            os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.getenv("LocalAppData", ""),
        ]
        relatives = (
            r"Google\Chrome\Application\chrome.exe",
            r"Microsoft\Edge\Application\msedge.exe",
            r"BraveSoftware\Brave-Browser\Application\brave.exe",
        )
        return [str(Path(root) / rel) for root in roots if root for rel in relatives]
    if sys.platform == "darwin":
        return [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ]
    return [
        p
        for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge", "brave-browser")
        if (p := shutil.which(name))
    ]


def detect_local_chromium_browser() -> str | None:
    """Return path to a GUI Chromium/Edge executable, or None in headless cloud containers."""
    if sys.platform.startswith("linux") and not (
        os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")
    ):
        return None
    for candidate in _browser_candidates():
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _configure_chromium_download_dir(profile_dir: Path, inbox_dir: Path) -> None:
    """Configure isolated profile Preferences so downloads land directly in flow_inbox."""
    default_dir = profile_dir / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)
    prefs_path = default_dir / "Preferences"
    prefs: dict[str, Any] = {}
    if prefs_path.is_file():
        try:
            loaded = json.loads(prefs_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                prefs = loaded
        except (OSError, ValueError):
            prefs = {}

    download_cfg = prefs.get("download")
    if not isinstance(download_cfg, dict):
        download_cfg = {}
    download_cfg["default_directory"] = str(inbox_dir.resolve())
    download_cfg["prompt_for_download"] = False
    prefs["download"] = download_cfg

    savefile_cfg = prefs.get("savefile")
    if not isinstance(savefile_cfg, dict):
        savefile_cfg = {}
    savefile_cfg["default_directory"] = str(inbox_dir.resolve())
    prefs["savefile"] = savefile_cfg

    prefs_path.write_text(json.dumps(prefs, indent=2), encoding="utf-8")


def launch_studio_browser(url: str) -> BrowserLaunchResult:
    """Launch isolated Chromium/Edge app window with persistent login profile."""
    safe_url = validate_portal_url(url)
    browser_exe = detect_local_chromium_browser()
    if not browser_exe:
        return BrowserLaunchResult(
            ok=False,
            mode="cloud",
            url=safe_url,
            message=(
                "Pelayar In-House tempatan tidak tersedia di pelayan awan (tanpa paparan GUI). "
                "Buka pautan di tab pelayar anda sendiri, muat turun klip/imej, kemudian muat naik "
                "ke Peti Masuk Flow di bawah."
            ),
        )

    profile = browser_profile_dir(create=True)
    inbox = flow_inbox_dir(create=True)
    _configure_chromium_download_dir(profile, inbox)

    cmd = [
        browser_exe,
        f"--user-data-dir={profile.resolve()}",
        f"--app={safe_url}",
        "--window-size=1280,860",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    try:
        subprocess.Popen(cmd, shell=False)
    except OSError as exc:
        return BrowserLaunchResult(
            ok=False,
            mode="error",
            url=safe_url,
            browser_path=browser_exe,
            message=f"Gagal melancarkan Pelayar Studio: {exc}",
        )

    return BrowserLaunchResult(
        ok=True,
        mode="desktop",
        url=safe_url,
        browser_path=browser_exe,
        message=(
            "Tetingkap Pelayar Studio dibuka! Sesi log masuk Google anda disimpan dalam profil "
            "terasing dan muat turun akan terus masuk ke Peti Masuk Flow."
        ),
    )


def list_flow_inbox_items() -> list[FlowInboxItem]:
    """List valid images and videos currently inside storage/flow_inbox (newest first)."""
    inbox = flow_inbox_dir(create=True)
    items: list[FlowInboxItem] = []
    for entry in inbox.iterdir():
        if not entry.is_file():
            continue
        suffix = entry.suffix.lower()
        if suffix in material_upload.SUPPORTED_VIDEO_EXTENSIONS:
            kind: Literal["video", "image"] = "video"
        elif suffix in material_upload.SUPPORTED_IMAGE_EXTENSIONS:
            kind = "image"
        else:
            continue
        stat = entry.stat()
        items.append(
            FlowInboxItem(
                name=entry.name,
                path=str(entry),
                kind=kind,
                size_bytes=stat.st_size,
                modified_ts=stat.st_mtime,
            )
        )
    items.sort(key=lambda item: item.modified_ts, reverse=True)
    return items


def save_upload_to_flow_inbox(uploaded_files: Iterable[Any]) -> list[str]:
    """Validate and save uploaded media from the web UI into storage/flow_inbox safely."""
    import tempfile

    inbox = flow_inbox_dir(create=True)
    saved_names: list[str] = []
    for uploaded in uploaded_files:
        raw_name = getattr(uploaded, "name", "") or ""
        safe_name = material_upload.sanitize_material_filename(raw_name)
        kind = material_upload._material_kind(safe_name)
        ext = Path(safe_name).suffix.lower()
        max_bytes = (
            material_upload.MAX_VIDEO_MATERIAL_UPLOAD_BYTES
            if kind == "video"
            else material_upload.MAX_IMAGE_MATERIAL_UPLOAD_BYTES
        )
        target_path = Path(
            file_security.resolve_path_within_directory(
                str(inbox), safe_name, require_file=False
            )
        )
        try:
            uploaded.seek(0)
        except (AttributeError, OSError):
            pass

        temp_path = ""
        total_bytes = 0
        try:
            fd, temp_path = tempfile.mkstemp(prefix=".flow-inbox-", suffix=ext, dir=str(inbox))
            with os.fdopen(fd, "wb") as out:
                while True:
                    chunk = uploaded.read(1024 * 1024)
                    if not chunk:
                        break
                    if not isinstance(chunk, (bytes, bytearray, memoryview)):
                        raise material_upload.MaterialUploadError("Muat naik mestilah fail binari.")
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise material_upload.MaterialUploadError(
                            f"Saiz fail melebihi had {max_bytes // (1024 * 1024)} MB."
                        )
                    out.write(chunk)
                out.flush()
            if total_bytes == 0:
                raise material_upload.MaterialUploadError("Fail yang dimuat naik kosong.")

            if kind == "image":
                material_upload._validate_image(temp_path, ext)
            else:
                material_upload._validate_video(temp_path)

            os.replace(temp_path, target_path)
            temp_path = ""
            saved_names.append(safe_name)
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
    return saved_names


def import_flow_inbox_to_materials(filenames: list[str]) -> list[MaterialInfo]:
    """Validate and stage selected flow_inbox files through upstream material_upload."""
    inbox = str(flow_inbox_dir(create=True))
    staged: list[MaterialInfo] = []
    for name in filenames:
        if not name or "/" in name or "\\" in name:
            raise ValueError("Nama fail Peti Masuk Flow tidak sah.")
        resolved = file_security.resolve_path_within_directory(inbox, name, require_file=True)
        with open(resolved, "rb") as stream:
            stored_name = material_upload.save_material_upload(Path(resolved).name, stream)
        staged.append(MaterialInfo(provider="local", url=stored_name))
    return staged


def delete_flow_inbox_item(filename: str) -> bool:
    """Safely delete one file inside storage/flow_inbox."""
    if not filename or "/" in filename or "\\" in filename:
        raise ValueError("Nama fail Peti Masuk Flow tidak sah.")
    inbox = str(flow_inbox_dir(create=True))
    resolved = Path(
        file_security.resolve_path_within_directory(inbox, filename, require_file=False)
    )
    if resolved.is_file():
        resolved.unlink()
        return True
    return False
