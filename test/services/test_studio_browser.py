import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.models.schema import MaterialInfo
from app.services import material_upload
from app.services import studio_browser as sb
from app.utils import file_security, utils


def _png_bytes(color: str = "orange") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=color).save(buf, format="PNG")
    return buf.getvalue()


class _FakeUpload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._buf = io.BytesIO(data)

    def read(self, size: int = -1) -> bytes:
        return self._buf.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._buf.seek(offset, whence)


class TestStudioBrowser(unittest.TestCase):
    def test_studio_portals_catalog(self):
        portal_ids = {p.id for p in sb.STUDIO_PORTALS}
        self.assertEqual(
            portal_ids,
            {
                "google_flow",
                "google_whisk",
                "google_ai_studio",
                "pixabay",
                "canva",
                "tiktok_studio",
            },
        )
        flow = sb.get_portal("google_flow")
        self.assertEqual(flow.url, "https://labs.google/fx/tools/flow")

    def test_validate_portal_url_strict(self):
        self.assertEqual(
            sb.validate_portal_url("https://labs.google/fx/tools/flow"),
            "https://labs.google/fx/tools/flow",
        )
        self.assertEqual(
            sb.validate_portal_url("http://127.0.0.1:8501/"),
            "http://127.0.0.1:8501/",
        )
        for bad in (
            "",
            "   ",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "ftp://example.com/a",
            "https://labs.google/fx\nrm -rf",
            "https://",
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    sb.validate_portal_url(bad)

    def test_detect_local_chromium_browser_cloud_vs_desktop(self):
        with patch("app.services.studio_browser.sys.platform", "linux"):
            with patch.dict(os.environ, {}, clear=True):
                self.assertIsNone(sb.detect_local_chromium_browser())

        with patch("app.services.studio_browser.sys.platform", "win32"):
            with patch(
                "app.services.studio_browser._browser_candidates",
                return_value=[r"C:\Program Files\Google\Chrome\Application\chrome.exe"],
            ):
                with patch(
                    "app.services.studio_browser.os.path.isfile",
                    side_effect=lambda p: p.endswith("chrome.exe"),
                ):
                    self.assertEqual(
                        sb.detect_local_chromium_browser(),
                        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    )

    def test_configure_chromium_download_dir_merges_preferences(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "profile"
            inbox_dir = Path(tmpdir) / "inbox"
            inbox_dir.mkdir()
            default_dir = profile_dir / "Default"
            default_dir.mkdir(parents=True)
            prefs_path = default_dir / "Preferences"
            prefs_path.write_text(json.dumps({"browser": {"show_home_button": True}}), encoding="utf-8")

            sb._configure_chromium_download_dir(profile_dir, inbox_dir)
            prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
            self.assertTrue(prefs["browser"]["show_home_button"])
            self.assertEqual(prefs["download"]["default_directory"], str(inbox_dir.resolve()))
            self.assertFalse(prefs["download"]["prompt_for_download"])

    def test_launch_studio_browser_desktop_and_cloud_modes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "profile"
            inbox_dir = Path(tmpdir) / "inbox"
            with patch("app.services.studio_browser.browser_profile_dir", return_value=profile_dir):
                with patch("app.services.studio_browser.flow_inbox_dir", return_value=inbox_dir):
                    with patch(
                        "app.services.studio_browser.detect_local_chromium_browser",
                        return_value=r"C:\Edge\msedge.exe",
                    ):
                        with patch("app.services.studio_browser.subprocess.Popen") as mock_popen:
                            res = sb.launch_studio_browser("https://labs.google/fx/tools/flow")
                            self.assertTrue(res.ok)
                            self.assertEqual(res.mode, "desktop")
                            mock_popen.assert_called_once()
                            cmd = mock_popen.call_args.args[0]
                            self.assertEqual(cmd[0], r"C:\Edge\msedge.exe")
                            self.assertTrue(any(arg.startswith("--user-data-dir=") for arg in cmd))
                            self.assertIn("--app=https://labs.google/fx/tools/flow", cmd)
                            self.assertFalse(mock_popen.call_args.kwargs.get("shell", False))

                    with patch(
                        "app.services.studio_browser.detect_local_chromium_browser",
                        return_value=None,
                    ):
                        with patch("app.services.studio_browser.subprocess.Popen") as mock_popen:
                            cloud_res = sb.launch_studio_browser("https://labs.google/fx/tools/flow")
                            self.assertFalse(cloud_res.ok)
                            self.assertEqual(cloud_res.mode, "cloud")
                            mock_popen.assert_not_called()

    def test_flow_inbox_save_list_import_and_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inbox_dir = Path(tmpdir) / "flow_inbox"
            inbox_dir.mkdir()
            with patch("app.services.studio_browser.flow_inbox_dir", return_value=inbox_dir):
                saved = sb.save_upload_to_flow_inbox([_FakeUpload("veo-durian.png", _png_bytes())])
                self.assertEqual(saved, ["veo-durian.png"])

                items = sb.list_flow_inbox_items()
                self.assertEqual(len(items), 1)
                self.assertEqual(items[0].name, "veo-durian.png")
                self.assertEqual(items[0].kind, "image")

                with self.assertRaises(material_upload.MaterialUploadError):
                    sb.save_upload_to_flow_inbox([_FakeUpload("bad.exe", b"MZ")])

                with self.assertRaises(material_upload.MaterialUploadError):
                    sb.save_upload_to_flow_inbox([_FakeUpload("corrupt.png", b"not-a-real-png")])
                self.assertFalse((inbox_dir / "corrupt.png").exists())

                with self.assertRaises(ValueError):
                    sb.import_flow_inbox_to_materials(["../secret.png"])

                materials = sb.import_flow_inbox_to_materials(["veo-durian.png"])
                self.assertEqual(len(materials), 1)
                self.assertIsInstance(materials[0], MaterialInfo)
                self.assertEqual(materials[0].provider, "local")
                local_dir = utils.storage_dir("local_videos", create=True)
                staged_path = Path(
                    file_security.resolve_path_within_directory(local_dir, materials[0].url)
                )
                self.assertTrue(staged_path.is_file())
                staged_path.unlink(missing_ok=True)

                with self.assertRaises(ValueError):
                    sb.delete_flow_inbox_item("../outside.png")

                self.assertTrue(sb.delete_flow_inbox_item("veo-durian.png"))
                self.assertEqual(sb.list_flow_inbox_items(), [])


if __name__ == "__main__":
    unittest.main()
