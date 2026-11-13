"""Isolated artifact/statistics behavior checks; no network, real grades or Office automation."""
from __future__ import annotations
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, skill, script):
    path = ROOT / "addons" / skill / "scripts" / script
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


try:
    import pandas as pd
    from docx import Document
    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False

if DEPENDENCIES_AVAILABLE:
    paper = load("integrated_paper", "ai-course-assessment", "build_paper.py")
    blueprint = load("integrated_blueprint", "ai-course-assessment", "make_blueprint.py")
    rubric = load("integrated_rubric", "ai-course-assessment", "build_rubric.py")
    grade = load("integrated_grade", "ai-course-analytics", "grade.py")
    merge = load("integrated_merge", "ai-course-analytics", "merge_scores.py")
    demo = load("integrated_demo", "ai-course-analytics", "make_demo.py")


def bank():
    return {"meta": {"title": "测试卷", "total": 6, "pass_fraction": 0.6}, "questions": [
        {"id": "S1", "type": "single", "score": 2, "stem": "选择已知条件", "options": ["甲", "乙"],
         "answer": "A", "analysis": "仅教师可见解析", "points": ["条件判断"], "kp_ids": ["C-01"]},
        {"id": "H1", "type": "short", "score": 4, "stem": "解释理由", "answer": "仅教师可见答案",
         "rubric": [{"point": "仅教师可见评分点", "score": 4}], "points": ["理由解释"], "kp_ids": ["C-02"]}]}


@unittest.skipUnless(DEPENDENCIES_AVAILABLE, "Artifact tests need project dependency environment: pandas, python-docx")
class TeachingAssessmentAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="teaching-package-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def quiet(self, function, *args, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return function(*args, **kwargs)

    def test_student_paper_separates_answers_and_does_not_invent_school_or_exam_rules(self):
        data = bank()
        source = self.root / "bank.json"
        source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        prefix = self.root / "paper"
        self.assertEqual(self.quiet(paper.main, [str(source), "-o", str(prefix), "--strict"]), 0)
        student = Document(str(prefix) + "_学生卷.docx")
        teacher = Document(str(prefix) + "_教师卷.docx")
        student_text = "\n".join(paragraph.text for paragraph in student.paragraphs)
        teacher_text = "\n".join(paragraph.text for paragraph in teacher.paragraphs)
        self.assertNotIn("仅教师可见", student_text)
        self.assertIn("仅教师可见答案", teacher_text)
        self.assertIn("仅教师可见评分点", teacher_text)
        self.assertNotIn("西安电子", student_text)
        self.assertNotIn("只允许带一本", student_text)
        self.assertIn("考试方式未指定", student_text)
        self.assertEqual(student.core_properties.author, "课程组")
        self.assertEqual(source.read_text(encoding="utf-8"), json.dumps(data, ensure_ascii=False))

    def test_invalid_paper_is_rejected_before_any_docx_is_written(self):
        data = bank()
        data["questions"][1]["id"] = "S1"
        source = self.root / "bank.json"
        source.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.quiet(paper.main, [str(source), "-o", str(self.root / "bad"), "--strict"]), 1)
        self.assertEqual(list(self.root.glob("*.docx")), [])
        data = bank()
        data["questions"][0]["score"] = float("nan")
        self.assertTrue(any(severity == "error" for severity, _, _ in paper.check_questions(data)))

    def test_knowledge_map_is_explicit_and_duplicate_ids_cannot_be_lost(self):
        self.assertEqual(paper.kp.load(), {})
        source = self.root / "kp.csv"
        source.write_text("kp_id,name,section,order\nU7-01,条件判断,单元7,1\nU7-02,理由解释,单元7,2\n", encoding="utf-8")
        table = paper.kp.load(source)
        self.assertEqual(paper.kp.resolve("条件判断", table), "U7-01")
        bp = blueprint.build(["条件判断", "理由解释"], 20, "随堂", table=table)
        self.assertEqual(sum(row["score"] for row in bp["rows"]), 20)
        self.assertTrue(all(all(not value or value.startswith("U7-") for value in row["kp_ids"]) for row in bp["rows"]))
        source.write_text("kp_id,name\nDUP,甲\nDUP,乙\n", encoding="utf-8")
        with self.assertRaises(ValueError): paper.kp.load(source)

    def test_rubric_requires_explicit_config_or_labelled_example(self):
        with self.assertRaises(ValueError): rubric.load_dims(None)
        output = self.root / "rubric.docx"
        self.assertEqual(self.quiet(rubric.main, ["--example", "-o", str(output)]), 0)
        text = "\n".join(paragraph.text for paragraph in Document(output).paragraphs)
        self.assertIn("非课程正式标准", text)
        self.assertNotIn("AI 感明显", text)

    def responses(self):
        return pd.DataFrame([
            {"student_id": "local-1", "attendance": "present", "S1": "A", "H1": "4"},
            {"student_id": "local-2", "attendance": "present", "S1": "", "H1": "0"},
            {"student_id": "local-3", "attendance": "present", "S1": "B", "H1": "待人工评分"},
            {"student_id": "local-4", "attendance": "absent", "S1": "", "H1": ""}])

    def test_absence_zero_and_manual_pending_have_distinct_denominators(self):
        frame = self.responses()
        original = frame.copy(deep=True)
        detail, stats = grade.grade(bank(), frame)
        self.assertEqual(stats["sample"], 3)
        self.assertEqual(stats["absent"], 1)
        self.assertEqual(stats["complete_n"], 2)
        self.assertEqual(stats["total_score"], 3)
        self.assertAlmostEqual(stats["pass_rate"], 0.5)
        self.assertAlmostEqual(stats["items"][0]["difficulty"], 1 / 3)
        self.assertAlmostEqual(stats["items"][1]["difficulty"], 0.5)
        self.assertTrue(pd.isna(detail.loc[2, "total"]))
        self.assertEqual(detail.loc[1, "total"], 0)
        self.assertTrue(all(item["discrimination"] is None for item in stats["items"]))
        pd.testing.assert_frame_equal(frame, original)

    def test_missing_column_and_out_of_range_subjective_score_do_not_become_zero(self):
        frame = self.responses().drop(columns=["H1"])
        detail, stats = grade.grade(bank(), frame)
        self.assertEqual(stats["complete_n"], 0)
        self.assertEqual(stats["data_quality"]["missing_item_columns"], ["H1"])
        self.assertIsNone(stats["items"][1]["difficulty"])
        frame = self.responses()
        frame.loc[0, "H1"] = "9"
        detail, stats = grade.grade(bank(), frame)
        self.assertEqual(detail.loc[0, "H1_tag"], "invalid_score")
        self.assertTrue(pd.isna(detail.loc[0, "H1"]))
        self.assertEqual(stats["data_quality"]["invalid_scores"], 1)

    def test_duplicate_response_ids_stop_before_aggregate_and_totals_do_not_imply_mastery(self):
        frame = self.responses()
        frame.loc[1, "student_id"] = frame.loc[0, "student_id"]
        with self.assertRaises(ValueError): grade.grade(bank(), frame)
        _, stats = grade.totals_only(pd.DataFrame({"student_id": ["a", "b", "c"], "total": ["0", "80", "缺考"]}), 100)
        self.assertEqual(stats["total_score"], 40)
        self.assertEqual(stats["items"], [])
        self.assertEqual(stats["knowledge"], [])
        self.assertIsNone(stats["pass_fraction"])
        self.assertIsNone(stats["pass_rate"])
        report = grade.to_markdown(stats)
        self.assertIn("只有总分", report)
        self.assertNotIn("|a|", report)

    def test_discrimination_uses_complete_samples_and_known_high_low_difference(self):
        data = bank()
        data["questions"][1]["score"] = 100
        rows = [{"student_id": f"test-{index}", "S1": "A" if index >= 15 else "B", "H1": str(index)} for index in range(30)]
        _, stats = grade.grade(data, pd.DataFrame(rows))
        self.assertEqual(stats["group_size"], 9)
        self.assertAlmostEqual(stats["items"][0]["discrimination"], 1)
        rows[-1]["H1"] = "未评"
        _, stats = grade.grade(data, pd.DataFrame(rows))
        self.assertEqual(stats["complete_n"], 29)
        self.assertIsNone(stats["items"][0]["discrimination"])

    def test_cli_totals_and_demo_markers_emit_finite_aggregate_json(self):
        frame = self.responses()
        frame["dataset_kind"] = "DEMO"
        source = self.root / "answers.csv"
        frame.to_csv(source, index=False, encoding="utf-8-sig")
        questions = self.root / "questions.json"
        questions.write_text(json.dumps(bank()), encoding="utf-8")
        prefix = self.root / "analysis"
        self.assertEqual(self.quiet(grade.main, [str(questions), str(source), "-o", str(prefix)]), 0)
        raw = Path(str(prefix) + "_统计.json").read_text(encoding="utf-8")
        self.assertNotIn("NaN", raw)
        self.assertNotIn("local-1", raw)
        self.assertIn("DEMO", Path(str(prefix) + "_报告.md").read_text(encoding="utf-8"))

    def test_option_counts_and_distribution_come_from_observed_values(self):
        _, stats = grade.grade(bank(), self.responses())
        choices = stats["items"][0]["options"]
        self.assertEqual(choices["n"], 2)
        self.assertEqual(choices["counts"], {"A": 1, "B": 1})
        self.assertEqual(choices["top_wrong"], "B")
        self.assertEqual(sum(group["count"] for group in stats["score_distribution"]), 2)
        self.assertEqual(stats["score_distribution"][0]["count"], 1)
        self.assertEqual(stats["score_distribution"][-1]["count"], 1)
        report = grade.to_markdown(stats)
        self.assertIn("选项分布", report)
        self.assertIn("完整总分实际分布", report)

    def score_frame(self, source, score):
        return pd.DataFrame([{"student_id": "001", "exp": "1", "score": score, "source": source}])

    def test_merger_rejects_raw_outlier_before_average_and_preserves_inputs(self):
        peer, ai = self.score_frame("peer", 105), self.score_frame("ai", 85)
        original = peer.copy(deep=True)
        with self.assertRaises(ValueError): merge.merge(peer, ai)
        pd.testing.assert_frame_equal(peer, original)
        peer.loc[0, "score"] = 95
        detail, quality = merge.merge(peer, ai)
        self.assertEqual(detail.loc[0, "score"], 90)
        students = merge.per_student(detail)
        self.assertNotIn("排名", students)
        report = merge.to_md(detail, students, quality)
        self.assertNotIn("001", report)
        self.assertNotIn("前 15 名", report)

    def test_merger_missing_side_is_not_an_official_full_score_and_leading_zeros_survive(self):
        peer = self.score_frame("peer", 80)
        ai = pd.DataFrame(columns=["student_id", "exp", "score", "source"])
        detail, _ = merge.merge(peer, ai, experiments=["1", "2"])
        self.assertTrue(detail["score"].isna().all())
        allowed, quality = merge.merge(peer, ai, allow_single_source=True, experiments=["1", "2"])
        self.assertEqual(allowed.loc[0, "score"], 80)
        self.assertTrue(allowed.loc[1, "no_score"])
        path = self.root / "scores.csv"
        path.write_text("student_id,exp,score\n001,1,80\n", encoding="utf-8")
        self.assertEqual(merge.norm(path, "peer").loc[0, "student_id"], "001")
        duplicate = pd.concat([peer, peer], ignore_index=True)
        with self.assertRaises(ValueError): merge.merge(duplicate, ai)

    def test_demo_generator_uses_visible_fake_identifiers(self):
        source = self.root / "bank.json"
        source.write_text(json.dumps(bank()), encoding="utf-8")
        output = self.root / "demo.csv"
        self.assertEqual(self.quiet(demo.main, [str(source), "-o", str(output), "--students", "3"]), 0)
        frame = pd.read_csv(output, dtype=str, keep_default_na=False)
        self.assertTrue(frame["student_id"].str.startswith("DEMO-").all())
        self.assertTrue(frame["dataset_kind"].eq("DEMO").all())


if __name__ == "__main__":
    unittest.main()
