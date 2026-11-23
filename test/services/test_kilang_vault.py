from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services import kilang_vault as kv


class TestKilangVault(unittest.TestCase):
    def test_brand_vault_auto_seeds_upserts_and_protects_last_brand(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = Path(tmpdir) / "kilang_brands.json"
            brands = kv.list_brands(store_path=store)
            self.assertGreaterEqual(len(brands), 4)
            self.assertTrue(store.is_file())
            self.assertEqual(brands[0].id, "radhi_fruits")

            radhi = kv.get_brand("radhi_fruits", store_path=store)
            self.assertEqual(radhi.product_name, "Radhi Fruits 4690")

            custom = kv.BrandRecord(
                id="warung_kopi_kemaman",
                label="Warung Kopi Kemaman",
                product_name="Kopi Kampung Warisan",
                offer="Set Sarapan Pagi RM6.90",
                usp="Kopi pekat panggang tradisional",
                audience_cta="Singgah kedai atau WhatsApp tempahan",
                style_key="santai_tiktok",
                duration_seconds=30,
                default_voice="ms-MY-OsmanNeural-Male",
                subtitle_color="#FDE047",
                default_aspect="9:16",
                visual_terms=("hot coffee pour", "malaysian breakfast"),
            )
            kv.upsert_brand(custom, store_path=store)
            loaded = kv.get_brand("warung_kopi_kemaman", store_path=store)
            self.assertEqual(loaded.subtitle_color, "#FDE047")

            # Delete down to 1 brand, then ensure last remaining brand cannot be deleted
            all_ids = [b.id for b in kv.list_brands(store_path=store)]
            for bid in all_ids[:-1]:
                self.assertTrue(kv.delete_brand(bid, store_path=store))

            with self.assertRaises(ValueError):
                kv.delete_brand(all_ids[-1], store_path=store)

    def test_render_history_records_filters_and_deletes_safely(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            store = tmp / "kilang_history.json"
            tasks_root = tmp / "tasks"
            task_dir = tasks_root / "kilang-test-01"
            task_dir.mkdir(parents=True)
            mp4 = task_dir / "final-1.mp4"
            mp4.write_bytes(b"fake-mp4-bytes")

            rec1 = kv.RenderRecord(
                task_id="kilang-test-01",
                created_at="2026-11-23T12:00:00+08:00",
                brand_name="Radhi Fruits 4690",
                angle_label="Urgensi",
                aspect="9:16",
                script="Jom singgah hari ini!",
                caption="Durian segar Kemaman!",
                hashtags=("#radhifruits", "#kemaman"),
                video_path=str(mp4),
                file_size_bytes=mp4.stat().st_size,
                voice_name="ms-MY-YasminNeural-Female",
                video_source="local",
            )
            rec2_missing = kv.RenderRecord(
                task_id="kilang-missing-02",
                created_at="2026-11-23T12:05:00+08:00",
                brand_name="PedalHaus Chukai",
                angle_label="Kualiti",
                aspect="9:16",
                script="Kopi sedap!",
                caption="Singgah kafe!",
                hashtags=("#pedalhaus",),
                video_path=str(tmp / "tasks" / "gone" / "final-1.mp4"),
                file_size_bytes=0,
                voice_name="ms-MY-OsmanNeural-Male",
                video_source="pixabay",
            )
            kv.record_render(rec1, store_path=store)
            kv.record_render(rec2_missing, store_path=store)

            existing = kv.list_renders(existing_only=True, store_path=store)
            self.assertEqual([r.task_id for r in existing], ["kilang-test-01"])

            all_recs = kv.list_renders(existing_only=False, store_path=store)
            self.assertEqual([r.task_id for r in all_recs], ["kilang-missing-02", "kilang-test-01"])

            with patch("app.services.kilang_vault.utils.storage_dir", return_value=str(tasks_root)):
                for bad_id in ("", ".", "..", "../outside", "a/b"):
                    with self.subTest(bad_id=bad_id):
                        with self.assertRaises(ValueError):
                            kv.delete_render(bad_id, store_path=store, remove_files=True)
                self.assertTrue(tasks_root.is_dir())
                self.assertTrue(task_dir.is_dir())

                deleted = kv.delete_render("kilang-test-01", store_path=store, remove_files=True)
                self.assertTrue(deleted)
                self.assertFalse(task_dir.exists())
                self.assertTrue(tasks_root.is_dir())


if __name__ == "__main__":
    unittest.main()
