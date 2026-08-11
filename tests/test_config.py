"""SPEC-001 config tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from geos.config import ConfigError, Settings
from tests.helpers import TempDir


class ConfigTests(unittest.TestCase):
    def test_defaults(self) -> None:
        settings = Settings.defaults()
        self.assertEqual(settings.storage_provider, "sqlite")
        self.assertEqual(settings.storage_mode, "isolated")
        self.assertTrue(settings.knowledge_rag)

    def test_missing_file_returns_defaults(self) -> None:
        with TempDir() as tmp:
            settings = Settings.from_path(tmp / "nope.yaml", root=str(tmp))
        self.assertEqual(settings.company_name, "Example")

    def test_file_override(self) -> None:
        with TempDir() as tmp:
            (tmp / "geos.yaml").write_text(
                "company:\n  name: Azeetra\nstorage:\n  path: .geos/custom.db\n"
                "approvals:\n  blog_publish: required\n",
                encoding="utf-8",
            )
            settings = Settings.from_path(tmp / "geos.yaml", root=str(tmp))
            self.assertEqual(settings.company_name, "Azeetra")
            self.assertEqual(settings.storage_path, ".geos/custom.db")
            self.assertEqual(settings.approvals["blog_publish"], "required")
            self.assertEqual(str(settings.db_path), str(Path(tmp) / ".geos/custom.db"))

    def test_unknown_top_level_key_rejected(self) -> None:
        with TempDir() as tmp:
            (tmp / "geos.yaml").write_text("bogus: true\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                Settings.from_path(tmp / "geos.yaml", root=str(tmp))

    def test_invalid_yaml_rejected(self) -> None:
        with TempDir() as tmp:
            (tmp / "geos.yaml").write_text("storage: [unclosed", encoding="utf-8")
            with self.assertRaises(ConfigError):
                Settings.from_path(tmp / "geos.yaml", root=str(tmp))

    def test_feature_flags(self) -> None:
        settings = Settings.defaults()
        self.assertFalse(settings.feature("rag"))  # missing -> opt-in false
        settings.features = {"rag": True, "leads": {"enabled": True, "shadow_mode": True}}
        self.assertTrue(settings.feature("rag"))
        self.assertTrue(settings.feature("leads"))
        self.assertFalse(settings.feature("social_publish"))


if __name__ == "__main__":
    unittest.main()
