import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import config
from app.models.schema import (
    ImageMotion,
    MaterialInfo,
    VideoAspect,
    VideoConcatMode,
    VideoFitMode,
)
from app.services import kilang_studio as ks
from app.services import material_upload
from app.utils import file_security, utils


def _png_bytes(color: str = "green") -> bytes:
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


class TestKilangStudio(unittest.TestCase):
    def test_constants_and_presets(self):
        self.assertEqual(ks.DEFAULT_GEMINI_MODEL, "gemini-3.8-flash")
        self.assertEqual(ks.DEFAULT_MALAY_VOICE, "ms-MY-YasminNeural-Female")
        self.assertEqual(ks.DEFAULT_SUBTITLE_FONT, "BeVietnamPro-Bold.ttf")

        preset_ids = {preset.id for preset in ks.CAMPAIGN_PRESETS}
        self.assertEqual(
            preset_ids,
            {"radhi_fruits", "pedalhaus_chukai", "van_sekolah_binjai", "produk_umum"},
        )
        self.assertIn("santai_tiktok", ks.SCRIPT_STYLES)
        self.assertIn("mesra_komuniti", ks.SCRIPT_STYLES)
        self.assertIn("promosi_pantas", ks.SCRIPT_STYLES)
        self.assertEqual(set(ks.DURATION_PROFILES.keys()), {15, 30, 45})

    def test_load_dotenv_if_present_respects_existing_env(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "# comment\n"
                'GEMINI_API_KEY="from-dotenv-file"\n'
                "export GEMINI_MODEL_NAME='gemini-2.5-pro'\n"
                "PEXELS_API_KEY=pexels-from-dotenv\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "already-in-env"},
                clear=True,
            ):
                ks.load_dotenv_if_present(env_path)
                self.assertEqual(os.environ.get("GEMINI_API_KEY"), "already-in-env")
                self.assertEqual(os.environ.get("GEMINI_MODEL_NAME"), "gemini-2.5-pro")
                self.assertEqual(os.environ.get("PEXELS_API_KEY"), "pexels-from-dotenv")

    def test_resolve_gemini_runtime_config_precedence_and_isolation(self):
        orig_provider = config.app.get("llm_provider")
        orig_key = config.app.get("gemini_api_key")
        orig_model = config.app.get("gemini_model_name")

        try:
            with patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "env-key", "GEMINI_MODEL_NAME": "gemini-2.0-flash"},
                clear=False,
            ):
                with patch.dict(
                    config.app,
                    {
                        "llm_provider": "moonshot",
                        "gemini_api_key": "cfg-key",
                        "gemini_model_name": "gemini-2.5-pro",
                    },
                    clear=False,
                ):
                    explicit = ks.resolve_gemini_runtime_config(
                        api_key="ui-key",
                        model_name="gemini-2.5-flash",
                    )
                    self.assertEqual(explicit["llm_provider"], "gemini")
                    self.assertEqual(explicit["gemini_api_key"], "ui-key")
                    self.assertEqual(explicit["gemini_model_name"], "gemini-2.5-flash")

                    from_env = ks.resolve_gemini_runtime_config()
                    self.assertEqual(from_env["gemini_api_key"], "env-key")
                    self.assertEqual(from_env["gemini_model_name"], "gemini-2.0-flash")

                    # Global config must remain untouched
                    self.assertEqual(config.app.get("llm_provider"), "moonshot")
                    self.assertEqual(config.app.get("gemini_api_key"), "cfg-key")

            with patch.dict(os.environ, {}, clear=True):
                with patch.dict(
                    config.app,
                    {"gemini_api_key": "", "gemini_model_name": ""},
                    clear=False,
                ):
                    fallback = ks.resolve_gemini_runtime_config()
                    self.assertEqual(fallback["gemini_api_key"], "")
                    self.assertEqual(fallback["gemini_model_name"], ks.DEFAULT_GEMINI_MODEL)
        finally:
            if orig_provider is not None:
                config.app["llm_provider"] = orig_provider
            if orig_key is not None:
                config.app["gemini_api_key"] = orig_key
            if orig_model is not None:
                config.app["gemini_model_name"] = orig_model

    def test_resolve_stock_api_keys_precedence(self):
        with patch.dict(
            os.environ,
            {"PEXELS_API_KEY": "env-pexels", "PIXABAY_API_KEY": ""},
            clear=True,
        ):
            with patch.dict(
                config.app,
                {"pexels_api_keys": ["cfg-pexels"], "pixabay_api_keys": ["cfg-pixabay"]},
                clear=False,
            ):
                resolved = ks.resolve_stock_api_keys(pexels_key="ui-pexels")
                self.assertEqual(resolved["pexels_api_keys"], ["ui-pexels"])
                self.assertEqual(resolved["pixabay_api_keys"], ["cfg-pixabay"])

    def test_generate_malay_script_requires_product_and_api_key(self):
        empty_brief = ks.CampaignBrief(product_name="   ")
        res_empty = ks.generate_malay_script(empty_brief, api_key="secret")
        self.assertFalse(res_empty.ok)
        self.assertEqual(res_empty.source, "error")
        self.assertIn("produk", res_empty.error.lower())

        radhi = ks.get_preset("radhi_fruits").to_brief()
        with patch.dict(os.environ, {}, clear=True):
            with patch.dict(config.app, {"gemini_api_key": ""}, clear=False):
                with patch("app.services.kilang_studio.llm._generate_response") as mock_gen:
                    res_no_key = ks.generate_malay_script(radhi)
                    self.assertFalse(res_no_key.ok)
                    self.assertEqual(res_no_key.source, "error")
                    self.assertIn("GEMINI_API_KEY", res_no_key.error)
                    mock_gen.assert_not_called()

    def test_generate_malay_script_calls_gemini_and_redacts_errors(self):
        radhi = ks.get_preset("radhi_fruits").to_brief()
        with patch(
            "app.services.kilang_studio.llm._generate_response",
            return_value="**[Hook]** Orang Kemaman, stok durian kampung baru turun pagi ini! (BGM ceria)",
        ) as mock_gen:
            result = ks.generate_malay_script(
                radhi,
                api_key="AIzaSySecretKey123",
                model_name="gemini-3.8-flash",
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.source, "gemini")
            self.assertEqual(result.model_name, "gemini-3.8-flash")
            self.assertEqual(
                result.script,
                "Orang Kemaman, stok durian kampung baru turun pagi ini!",
            )

            kwargs = mock_gen.call_args.kwargs
            self.assertIn(ks.MALAY_MARKETING_SYSTEM_PROMPT, kwargs["prompt"])
            self.assertIn("Bahasa Melayu (Malaysia)", kwargs["prompt"])
            self.assertIn("Radhi Fruits", kwargs["prompt"])
            self.assertEqual(kwargs["app_config"]["llm_provider"], "gemini")
            self.assertEqual(kwargs["app_config"]["gemini_api_key"], "AIzaSySecretKey123")
            self.assertEqual(kwargs["app_config"]["gemini_model_name"], "gemini-3.8-flash")

        with patch(
            "app.services.kilang_studio.llm._generate_response",
            return_value="Error: 400 API_KEY_INVALID for key AIzaSySecretKey123",
        ) as mock_err:
            err_result = ks.generate_malay_script(
                radhi,
                api_key="AIzaSySecretKey123",
            )
            self.assertFalse(err_result.ok)
            self.assertEqual(err_result.source, "error")
            self.assertIn("400 API_KEY_INVALID", err_result.error)
            self.assertNotIn("AIzaSySecretKey123", err_result.error)
            self.assertEqual(mock_err.call_count, 1)

    def test_discover_free_tier_gemini_models_filters_and_ranks(self):
        from types import SimpleNamespace

        fake_models = [
            SimpleNamespace(name="models/gemini-3.1-pro-preview", supported_actions=["generateContent"]),
            SimpleNamespace(name="models/text-embedding-004", supported_actions=["embedContent"]),
            SimpleNamespace(name="models/gemini-2.5-flash-tts", supported_actions=["generateContent"]),
            SimpleNamespace(name="models/gemma-3-27b-it", supported_actions=["generateContent"]),
            SimpleNamespace(name="models/gemini-3.8-flash", supported_actions=["generateContent"]),
            SimpleNamespace(name="models/gemini-3.5-flash-lite", supported_actions=["generateContent"]),
        ]

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.models = SimpleNamespace(list=lambda: fake_models)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("google.genai.Client", _FakeClient):
            ranked = ks.discover_free_tier_gemini_models("AIzaFakeKey")

        self.assertEqual(
            ranked,
            ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemma-3-27b-it"],
        )

    def test_generate_malay_script_retries_and_falls_back_on_503(self):
        radhi = ks.get_preset("radhi_fruits").to_brief()
        seen_models = []

        def fake_generate(prompt, app_config):
            seen_models.append(app_config["gemini_model_name"])
            if len(seen_models) < 3:
                return "Error: 503 UNAVAILABLE. high demand"
            return "Jom singgah Radhi Fruits hari ini, stok durian kampung segar!"

        with patch("app.services.kilang_studio.time.sleep") as mock_sleep:
            with patch(
                "app.services.kilang_studio.discover_free_tier_gemini_models",
                return_value=["gemini-3.5-flash-lite"],
            ):
                with patch(
                    "app.services.kilang_studio.llm._generate_response",
                    side_effect=fake_generate,
                ):
                    result = ks.generate_malay_script(
                        radhi,
                        api_key="AIzaSySecretKey123",
                        model_name="gemini-3.8-flash",
                    )
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "gemini")
        self.assertEqual(result.model_name, "gemini-3.5-flash-lite")
        self.assertEqual(
            seen_models,
            ["gemini-3.8-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"],
        )
        self.assertEqual(mock_sleep.call_count, 2)

    def test_generate_malay_script_skips_same_model_retry_on_free_tier_limit_zero(self):
        radhi = ks.get_preset("radhi_fruits").to_brief()
        seen_models = []

        def fake_generate(prompt, app_config):
            seen_models.append(app_config["gemini_model_name"])
            if app_config["gemini_model_name"] == "gemini-3.1-pro-preview":
                return "Error: 429 RESOURCE_EXHAUSTED limit: 0"
            return "Stok durian Radhi Fruits sedia untuk pickup!"

        with patch("app.services.kilang_studio.time.sleep") as mock_sleep:
            with patch(
                "app.services.kilang_studio.discover_free_tier_gemini_models",
                return_value=["gemini-3.5-flash-lite"],
            ):
                with patch(
                    "app.services.kilang_studio.llm._generate_response",
                    side_effect=fake_generate,
                ):
                    result = ks.generate_malay_script(
                        radhi,
                        api_key="AIzaSySecretKey123",
                        model_name="gemini-3.1-pro-preview",
                    )
        self.assertTrue(result.ok)
        self.assertEqual(result.model_name, "gemini-3.5-flash-lite")
        self.assertEqual(seen_models, ["gemini-3.1-pro-preview", "gemini-3.5-flash-lite"])
        self.assertEqual(mock_sleep.call_count, 1)

    def test_generate_malay_script_surfaces_friendly_503_when_all_models_busy(self):
        radhi = ks.get_preset("radhi_fruits").to_brief()
        with patch("app.services.kilang_studio.time.sleep"):
            with patch(
                "app.services.kilang_studio.discover_free_tier_gemini_models",
                return_value=[],
            ):
                with patch(
                    "app.services.kilang_studio.llm._generate_response",
                    return_value="Error: 503 UNAVAILABLE for AIzaSySecretKey123",
                ):
                    result = ks.generate_malay_script(
                        radhi,
                        api_key="AIzaSySecretKey123",
                        model_name="gemini-3.8-flash",
                    )
        self.assertFalse(result.ok)
        self.assertEqual(result.source, "error")
        self.assertIn("503 UNAVAILABLE", result.error)
        self.assertIn("Pelayan Google Gemini", result.error)
        self.assertNotIn("AIzaSySecretKey123", result.error)

    def test_generate_visual_terms_and_missing_key(self):
        radhi = ks.get_preset("radhi_fruits").to_brief()
        with patch.dict(os.environ, {}, clear=True):
            with patch.dict(config.app, {"gemini_api_key": ""}, clear=False):
                with self.assertRaises(ValueError):
                    ks.generate_visual_terms(radhi, "Skrip durian segar")

        with patch(
            "app.services.kilang_studio.llm.generate_terms",
            return_value=["fresh durian market", "tropical fruit stall"],
        ) as mock_terms:
            terms = ks.generate_visual_terms(
                radhi,
                "Skrip durian segar",
                amount=4,
                api_key="secret-key",
            )
            self.assertEqual(terms, ["fresh durian market", "tropical fruit stall"])
            self.assertEqual(mock_terms.call_args.kwargs["keyword_language"], "en")
            self.assertTrue(mock_terms.call_args.kwargs["match_script_order"])

    def test_offline_template_script_is_explicitly_marked(self):
        radhi = ks.get_preset("radhi_fruits").to_brief()
        res = ks.build_offline_template_script(radhi)
        self.assertTrue(res.ok)
        self.assertEqual(res.source, "offline_template")
        self.assertIn("Radhi Fruits", res.script)
        self.assertTrue(len(res.script.split()) >= 20)

    def test_sample_materials_and_uploaded_materials(self):
        sample_paths = ks.get_sample_material_paths()
        self.assertEqual(len(sample_paths), 3)
        for sample in sample_paths:
            self.assertTrue(Path(sample).is_file())

        staged_samples = ks.stage_sample_materials()
        self.assertEqual(len(staged_samples), 3)
        local_dir = utils.storage_dir("local_videos", create=True)
        for item in staged_samples:
            self.assertIsInstance(item, MaterialInfo)
            self.assertEqual(item.provider, "local")
            resolved = file_security.resolve_path_within_directory(local_dir, item.url)
            self.assertTrue(Path(resolved).is_file())

        upload = _FakeUpload("produk-radhi.png", _png_bytes())
        staged_uploads = ks.stage_uploaded_materials([upload])
        self.assertEqual(len(staged_uploads), 1)
        uploaded_path = Path(
            file_security.resolve_path_within_directory(local_dir, staged_uploads[0].url)
        )
        self.assertTrue(uploaded_path.is_file())
        uploaded_path.unlink(missing_ok=True)

        bad_upload = _FakeUpload("malicious.exe", b"MZ")
        with self.assertRaises(material_upload.MaterialUploadError):
            ks.stage_uploaded_materials([bad_upload])

    def test_build_tiktok_video_params_defaults_and_validation(self):
        staged = ks.stage_sample_materials()
        params = ks.build_tiktok_video_params(
            product_name="Radhi Fruits 4690",
            script="Jom singgah Radhi Fruits hari ini!",
            video_source="local",
            local_materials=staged,
        )
        self.assertEqual(params.video_aspect, VideoAspect.portrait)
        self.assertEqual(params.video_fit_mode, VideoFitMode.cover)
        self.assertEqual(params.image_motion, ImageMotion.zoom)
        self.assertEqual(params.video_concat_mode, VideoConcatMode.sequential)
        self.assertEqual(params.voice_name, ks.DEFAULT_MALAY_VOICE)
        self.assertEqual(params.font_name, ks.DEFAULT_SUBTITLE_FONT)
        self.assertTrue(params.subtitle_enabled)
        self.assertEqual(len(params.video_materials), 3)

        with self.assertRaises(ValueError):
            ks.build_tiktok_video_params(
                product_name="Radhi Fruits 4690",
                script="Skrip ujian",
                video_source="local",
                local_materials=[],
            )

        with self.assertRaises(ValueError):
            ks.build_tiktok_video_params(
                product_name="Radhi Fruits 4690",
                script="Skrip ujian",
                video_source="unsupported_source",
            )

    def test_streamlit_kilang_studio_apptest_smoke(self):
        from streamlit.testing.v1 import AppTest

        app_path = Path(__file__).resolve().parents[2] / "webui" / "KilangStudio.py"
        clean_env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in {
                "GEMINI_API_KEY",
                "GEMINI_MODEL_NAME",
                "PEXELS_API_KEY",
                "PIXABAY_API_KEY",
            }
        }
        with patch.dict(os.environ, clean_env, clear=True):
            with patch.dict(config.app, {"gemini_api_key": ""}, clear=False):
                at = AppTest.from_file(str(app_path), default_timeout=30)
                at.run()
                self.assertEqual(len(at.exception), 0, f"Unexpected UI exceptions: {at.exception}")

                # Switch preset to PedalHaus Chukai and click Load Preset
                at.selectbox(key="selected_preset_picker").set_value("pedalhaus_chukai").run()
                load_btn = next(b for b in at.button if b.label == "Muat Contoh Kempen")
                load_btn.click().run()
                self.assertEqual(len(at.exception), 0)
                self.assertEqual(at.session_state["product_name"], "PedalHaus Chukai")

                # Click offline template button
                tpl_btn = next(
                    b for b in at.button if b.label == "Guna Draf Templat Tempatan (Tanpa AI)"
                )
                tpl_btn.click().run()
                self.assertEqual(len(at.exception), 0)
                self.assertIn("PedalHaus Chukai", at.session_state["video_script"])
                self.assertEqual(
                    at.session_state["script_source_badge"],
                    "Mod Templat Tempatan (Bukan AI)",
                )

                # Click Gemini button without key -> honest error shown, no fake script overwrite
                ai_btn = next(b for b in at.button if b.label == "Jana Skrip BM dengan Gemini")
                ai_btn.click().run()
                self.assertEqual(len(at.exception), 0)
                self.assertGreaterEqual(len(at.error), 1)


if __name__ == "__main__":
    unittest.main()
