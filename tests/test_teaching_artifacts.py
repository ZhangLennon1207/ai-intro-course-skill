"""Real artifact smoke checks in isolated directories; no WorkBuddy or network calls."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
import zipfile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ADDONS = ROOT / "addons"
ARTIFACT_DEPS = all(importlib.util.find_spec(name) for name in ("pptx", "docx", "matplotlib", "PIL", "lxml"))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(ARTIFACT_DEPS, "Artifact checks require the optional teaching development dependencies")
class TeachingArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="teaching-artifacts-")
        self.addCleanup(self.temp.cleanup)
        self.stage = Path(self.temp.name)

    def run_script(self, skill, name, *args):
        return subprocess.run([sys.executable, "-X", "utf8", str(ADDONS / skill / "scripts" / name), *map(str, args)],
                              cwd=self.stage, capture_output=True, text=True, encoding="utf-8", timeout=60)

    def write_json(self, name, obj):
        path = self.stage / name
        path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return path

    def handout_source(self):
        src = json.loads((ADDONS / "ai-course-handout/assets/sample-handout.json").read_text(encoding="utf-8"))
        for section in src["sections"]:
            section["kp_ids"] = ["U7-01"]
        src["sections"][0]["exercises"][0]["answer"] = "TEACHER_ANSWER_SENTINEL"
        return src

    def test_short_pptx_builds_without_fixed_page_count_or_memory_gate(self):
        from pptx import Presentation
        story = self.write_json("story.json", {"meta": {"course": "Fixture", "mode": "B"}, "coverage": ["Matching"],
            "slides": [{"type": "cover", "title": "Matching evidence"},
                       {"type": "bullets", "title": "Matching checks evidence", "covers": ["Matching"],
                        "points": ["Matching compares declared input and output evidence.", "A matching result does not prove source facts."]},
                       {"type": "end", "title": "Inspect the source before using a claim"}]})
        target = self.stage / "deck.pptx"
        result = self.run_script("ai-course-slides", "build_deck.py", story, target, "--check", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        deck = Presentation(target)
        self.assertEqual(len(deck.slides), 3)
        text = "\n".join(shape.text_frame.text for slide in deck.slides for shape in slide.shapes if shape.has_text_frame)
        self.assertIn("Matching checks evidence", text)
        self.assertEqual(deck.core_properties.author, "课程组")

    def test_handout_answer_separation_and_explicit_project_map(self):
        from docx import Document
        source = self.write_json("handout.json", self.handout_source())
        mapping = self.stage / "map.csv"
        mapping.write_text("kp_id,name\nU7-01,Project concept\n", encoding="utf-8")
        teacher, student = self.stage / "teacher.docx", self.stage / "student.docx"
        for target, flags in ((teacher, []), (student, ["--student"])):
            result = self.run_script("ai-course-handout", "build_handout.py", source, "-o", target,
                                     "--md", target.with_suffix(".md"), "--kp", mapping, "--check", "--strict", *flags)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("TEACHER_ANSWER_SENTINEL", "\n".join(p.text for p in Document(teacher).paragraphs))
        self.assertNotIn("TEACHER_ANSWER_SENTINEL", student.with_suffix(".md").read_text(encoding="utf-8"))
        with zipfile.ZipFile(student) as archive:
            self.assertNotIn(b"TEACHER_ANSWER_SENTINEL", b"\n".join(archive.read(n) for n in archive.namelist() if n.endswith('.xml')))
        self.assertEqual(Document(student).core_properties.author, "课程组")

    def test_handout_no_map_does_not_silently_apply_unit_three(self):
        source = self.write_json("handout.json", self.handout_source())
        result = self.run_script("ai-course-handout", "build_handout.py", source, "-o", self.stage / "handout.docx", "--check", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        badmap = self.stage / "map.csv"
        badmap.write_text("kp_id,name\nU8-01,Other concept\n", encoding="utf-8")
        target = self.stage / "bad.docx"
        result = self.run_script("ai-course-handout", "build_handout.py", source, "-o", target, "--kp", badmap, "--check", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertFalse(target.exists())

    def test_visual_creates_real_png_and_editable_svg(self):
        from PIL import Image
        source = self.write_json("figure.json", {"figures": [{"id": "example_flow", "type": "flow", "title": "Evidence flow",
            "caption": "Teaching diagram, not measured data", "source": "Self-authored fixture",
            "elements": [{"label": "Input", "role": "main"}, {"label": "Check", "role": "compare"}]}]})
        result = self.run_script("ai-course-visual", "build_figures.py", source, "-o", self.stage / "figures", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with Image.open(self.stage / "figures/example_flow.png") as image:
            self.assertGreater(image.width, 1000)
            self.assertAlmostEqual(image.info.get("dpi", (0,))[0], 200, delta=1)
        tree = ET.parse(self.stage / "figures/example_flow.svg")
        texts = tree.findall('.//{http://www.w3.org/2000/svg}text')
        self.assertIn("Evidence flow", ["".join(node.itertext()) for node in texts])

    def test_visual_rejects_escaping_output_identifier(self):
        source = self.write_json("badfigure.json", {"figures": [{"id": "../escape", "type": "flow", "title": "Flow",
            "caption": "Teaching diagram", "source": "Self-authored", "elements": [{"label": "A"}, {"label": "B"}]}]})
        result = self.run_script("ai-course-visual", "build_figures.py", source, "-o", self.stage / "figures", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertFalse((self.stage / "escape.png").exists())

    def test_library_node_mode_refuses_hidden_cli_without_writing_output(self):
        for script in ("fetch_textbook.py", "fetch_teacher_outline.py"):
            target = self.stage / (script + ".md")
            result = self.run_script("ai-course-slides", script, "--node", "fixture-node", "-o", target)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertFalse(target.exists())

    def test_dependency_install_refuses_global_interpreter_before_pip(self):
        module = load_module("teaching_envcheck", ADDONS / "ai-course-slides/scripts/envcheck.py")
        with mock.patch.object(module.sys, "prefix", module.sys.base_prefix), mock.patch.object(module.subprocess, "run", side_effect=AssertionError("Must not call pip")):
            with self.assertRaises(SystemExit) as caught:
                module.main(["--install"])
        self.assertEqual(caught.exception.code, 2)

    def test_render_preserves_existing_images_without_opening_office(self):
        module = load_module("teaching_rendercheck", ADDONS / "ai-course-slides/scripts/render_check.py")
        output = self.stage / "render"
        output.mkdir()
        original = output / "teacher.png"
        original.write_bytes(b"existing teacher file")
        fake_client = types.ModuleType("win32com.client")
        fake_client.DispatchEx = mock.Mock(side_effect=AssertionError("Must not open Office"))
        fake = types.ModuleType("win32com")
        fake.client = fake_client
        with mock.patch.dict(sys.modules, {"win32com": fake, "win32com.client": fake_client}):
            with self.assertRaises(ValueError):
                module.export_png(self.stage / "unused.pptx", output)
        self.assertEqual(original.read_bytes(), b"existing teacher file")


if __name__ == "__main__":
    unittest.main()
