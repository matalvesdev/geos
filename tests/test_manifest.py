"""SPEC-009 manifest + registry tests."""

from __future__ import annotations

import unittest

from geos.discovery.capabilities import scan_capabilities
from geos.discovery.manifest import (
    RepoEntry,
    RepositoryRegistry,
    build_manifest,
    load_manifest,
    write_manifest,
)
from geos.discovery.mode import discover_mode
from tests.helpers import TempDir


class ManifestTests(unittest.TestCase):
    def test_manifest_roundtrip(self) -> None:
        with TempDir() as tmp:
            (tmp / "pom.xml").write_text("<project/>", encoding="utf-8")
            mode = discover_mode(tmp)
            detections = scan_capabilities(tmp)
            manifest = build_manifest(tmp, mode, detections, [])
            path = write_manifest(manifest, tmp / "manifest.json")
            loaded = load_manifest(path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["mode"], mode.mode)  # type: ignore[index]
        self.assertIn("capabilities", loaded)  # type: ignore[index]

    def test_registry_add_list_get(self) -> None:
        with TempDir() as tmp:
            registry = RepositoryRegistry(tmp / "repositories.json")
            entry = RepoEntry(id="zetra-one", name="zetra-one", path=str(tmp / "zetra-one"))
            registry.add(entry)
            registry.add(RepoEntry(id="website", name="website", path=str(tmp / "site"),
                                   repo_type="WEB"))
            reloaded = RepositoryRegistry(tmp / "repositories.json")
            self.assertEqual(len(reloaded.list()), 2)
            self.assertEqual(reloaded.get("zetra-one").repo_type, "PRODUCT")  # type: ignore[union-attr]
            self.assertTrue(reloaded.remove("website"))
            self.assertFalse(reloaded.remove("website"))


if __name__ == "__main__":
    unittest.main()
