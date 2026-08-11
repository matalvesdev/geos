"""SPEC-010 chunking tests."""

from __future__ import annotations

import unittest

from geos.intelligence.chunking import chunk_markdown


class ChunkingTests(unittest.TestCase):
    def test_headings_are_respected(self) -> None:
        text = "# Intro\n\nPrimeiro parágrafo.\n\n## Seção A\n\nTexto A.\n"
        chunks = chunk_markdown(text, uri="doc.md")
        headings = [c.heading for c in chunks]
        self.assertIn("Intro", headings)
        self.assertIn("Seção A", headings)
        self.assertTrue(all(c.content for c in chunks))

    def test_max_chars_fallback_splits_long_block(self) -> None:
        text = "# T\n\n" + "palavra " * 300
        chunks = chunk_markdown(text, uri="doc.md", max_chars=200, overlap=20)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(len(c.content) <= 200 + 25 for c in chunks))

    def test_positions_monotonic(self) -> None:
        text = "# A\n\np1\n\n## B\n\np2\n\np3\n"
        chunks = chunk_markdown(text, uri="doc.md")
        positions = [c.position for c in chunks]
        self.assertEqual(positions, sorted(positions))
        for i, chunk in enumerate(chunks):
            self.assertEqual(chunk.chunk_index, i)

    def test_empty_text(self) -> None:
        chunks = chunk_markdown("   \n\n  ", uri="doc.md")
        self.assertEqual(chunks, [])

    def test_code_blocks_not_split(self) -> None:
        text = "# T\n\n```python\nline1\nline2\nline3\n```\n\nDepois.\n"
        chunks = chunk_markdown(text, uri="doc.md", max_chars=30)
        joined = "\n".join(c.content for c in chunks)
        self.assertIn("line1\nline2\nline3", joined)


if __name__ == "__main__":
    unittest.main()
