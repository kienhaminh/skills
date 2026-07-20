from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skills.bootstrap.scripts.index_codebase import enrich_graph, markdown, record, source_files
from skills.bootstrap.scripts.inspect_codebase import inspect


class BootstrapToolTests(unittest.TestCase):
    def test_inspection_discovers_repository_owned_surfaces_without_requiring_agent_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "CONTRIBUTING.md").write_text("# Contributing\n", encoding="utf-8")
            (root / "pyproject.toml").write_text("[project]\nname='portable'\n", encoding="utf-8")
            (root / "Cargo.toml").write_text("[package]\nname='portable'\nversion='0.1.0'\n", encoding="utf-8")
            package = root / "web" / "package.json"
            package.parent.mkdir()
            package.write_text(
                '{"scripts":{"test":"node --test","lint":"eslint ."}}\n', encoding="utf-8"
            )

            report = inspect(root)

            self.assertEqual(report["instruction_files"], ["CONTRIBUTING.md"])
            self.assertIn("Cargo.toml", report["command_surfaces"])
            self.assertIn("pyproject.toml", report["command_surfaces"])
            self.assertEqual(
                report["declared_package_scripts"]["web/package.json#test"], "node --test"
            )
            self.assertNotIn("agent_entrypoints", report)

    def test_index_query_uses_source_content_as_a_candidate_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "worker.ts"
            source.write_text(
                "export function sendNotice() {\n"
                "  // Retry delivery without sending a duplicate email.\n"
                "}\n",
                encoding="utf-8",
            )
            records = [record(root, path) for path in source_files(root)]
            enrich_graph(records)

            rendered = markdown(records, "duplicate email retry", 12)

            self.assertIn("worker.ts", rendered)
            self.assertIn("Returned: 1", rendered)

    def test_index_includes_node_module_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("worker.mjs", "legacy.cjs", "typed.mts", "compat.cts"):
                (root / name).write_text("export const value = true;\n", encoding="utf-8")

            self.assertEqual(
                sorted(path.name for path in source_files(root)),
                ["compat.cts", "legacy.cjs", "typed.mts", "worker.mjs"],
            )


if __name__ == "__main__":
    unittest.main()
