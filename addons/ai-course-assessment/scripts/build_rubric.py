#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""实验报告评分表：显式维度配置 -> docx / md。

用法：
    python build_rubric.py -o out/实验报告评分表.docx --md out/实验报告评分表.md
    python build_rubric.py -o out/评分表_空白.docx --blank      # 打印批改用，只留得分格
    python build_rubric.py -o out/评分表.docx --dims 自定义维度.json
    python build_rubric.py --check                              # 只核分值合计

本包不携带课程正式评分政策。必须传入--dims，或显式--example演示。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deid  # noqa: E402

FONT_CN = "宋体"
SIZE_TITLE = 16
SIZE_BODY = 12
SIZE_NOTE = 9
LINE_SPACING = 1.5

SOURCE = "用户本次提供的维度配置；使用--example时仅为示例建议，非课程正式标准"

DEFAULT_DIMS = [
    {
        "name": "模板格式规范性", "score": 20,
        "full": "完整沿用模板结构，必填栏目齐全；排版、图片表格、文件命名符合模板要求",
        "deduct": ["排版混乱酌情扣 3–8 分", "必填模块空白每处扣 4 分"],
    },
    {
        "name": "实验内容完成度", "score": 35,
        "full": "全部完成规定实验任务，步骤记录完整，实验截图、数据齐全",
        "deduct": ["核心任务未完成每项扣 8–15 分", "步骤简略缺逻辑扣 5–10 分",
                   "截图/数据缺失每处扣 6 分", "大面积复制无关资料扣 10–20 分"],
    },
    {
        "name": "实验原理与理论阐述", "score": 15,
        "full": "准确阐述相关 AI 基础概念、工具/模型原理，表述简洁，有个人理解",
        "deduct": ["概念原理错误每处扣 5 分", "内容空洞、脱离实验扣 3–6 分",
                   "大段照搬原文无思考扣 4–8 分", "完全不写原理本项 0 分"],
    },
    {
        "name": "实验结果与问题分析", "score": 15,
        "full": "能解读实验结果，分析异常现象、报错原因，说明排查与解决思路",
        "deduct": ["仅罗列结果无解读扣 6–8 分", "无问题记录与分析扣 4–6 分", "逻辑矛盾酌情扣 3–5 分"],
    },
    {
        "name": "实验总结与思考创新", "score": 10,
        "full": "总结实验收获与重难点，结合应用场景思考，无空话套话",
        "deduct": ["总结空洞套话多扣 4–6 分", "缺少重难点反思扣 3–5 分",
                   "内容敷衍字数不足扣 2–4 分", "无总结本项 0 分"],
    },
    {
        "name": "行文规范与原创性", "score": 5,
        "full": "语句通顺，错别字少，独立撰写，无抄袭",
        "deduct": ["错别字、语病较多酌情扣 2–3 分", "行文杂乱扣 2 分",
                   "涉嫌抄袭的内容交教师核查，不由本表自动定性或判不合格"],
    },
]

RED_LINES = ["本表仅排版用户指定的评分维度；采用前核对实际课程标准。",
             "不能凭文风或AI感作抄袭、作弊或不合格结论，学术判断需独立证据。"]


def load_dims(path: str | Path | None) -> list[dict]:
    if not path:
        raise ValueError("需要显式--dims维度文件；演示时用--example，不自动套课程权重")
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"找不到维度文件：{p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    dims = data.get("dimensions") if isinstance(data, dict) else data
    if not dims:
        raise SystemExit("维度文件里没有 dimensions 数组")
    return dims


def check(dims: list[dict], total: int = 100) -> list[tuple[str, str, str]]:
    issues: list[tuple[str, str, str]] = []
    s = 0.0
    for i, d in enumerate(dims, 1):
        name = str(d.get("name", "")).strip()
        loc = f"维度{i}《{name or '未命名'}》"
        if not name:
            issues.append(("error", loc, "缺维度名"))
        if not d.get("full"):
            issues.append(("warn", loc, "没写满分要求，评的时候没有依据"))
        if not d.get("deduct"):
            issues.append(("warn", loc, "没写扣分细则，不同老师会打出不同的分"))
        try:
            value = float(d.get("score", 0))
            if not math.isfinite(value) or value <= 0:
                raise ValueError("分值须为有限正数")
            s += value
        except (TypeError, ValueError):
            issues.append(("error", loc, "分值不是数字"))
    if abs(s - total) > 1e-6:
        issues.append(("error", "合计", f"维度分值合计 {s:g} 分，应为 {total} 分"))
    return issues


def format_issues(issues) -> str:
    if not issues:
        return "自检通过：维度齐全、分值合计正确。"
    out = []
    for lv, loc, msg in issues:
        out.append(f"{'[错误]' if lv == 'error' else '[提醒]'} {loc}：{msg}")
    err = sum(1 for i in issues if i[0] == "error")
    out.append(f"\n合计 {len(issues)} 条：错误 {err}，提醒 {len(issues) - err}")
    return "\n".join(out)


def to_md(dims: list[dict], title: str, blank: bool = False) -> str:
    total = sum(float(d.get("score", 0)) for d in dims)
    lines = [f"# {title}", "", f"> 满分 {total:g} 分｜来源：{SOURCE}", ""]
    if blank:
        lines += ["| 评分维度 | 分值 | 得分 | 扣分说明 |", "|---|---|---|---|"]
        for d in dims:
            lines.append(f"| {d.get('name', '')} | {float(d.get('score', 0)):g} |  |  |")
    else:
        # md 版把分值并进维度名：单独一列「分值」在窄屏会被挤成竖排，docx 版仍是独立列
        lines += ["| 评分维度 | 满分要求 | 扣分细则 | 得分 |", "|---|---|---|---|"]
        for d in dims:
            deduct = "；".join(str(x) for x in d.get("deduct") or [])
            lines.append(f"| {d.get('name', '')}（{float(d.get('score', 0)):g} 分） | "
                         f"{d.get('full', '')} | {deduct} |  |")
    lines += ["", f"**总分**：________ / {total:g}", "", "**使用说明**", ""]
    for r in RED_LINES:
        lines.append(f"- {r}")
    lines += ["", "**评语**：", ""]
    return "\n".join(lines)


def build_docx(dims: list[dict], out_path: str | Path, title: str, blank: bool = False) -> Path:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    total = sum(float(d.get("score", 0)) for d in dims)
    doc = Document()
    s0 = doc.sections[0]
    s0.top_margin = s0.bottom_margin = Cm(2.54)
    s0.left_margin = s0.right_margin = Cm(2.2)

    normal = doc.styles["Normal"]
    normal.font.name = FONT_CN
    normal.font.size = Pt(SIZE_BODY)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)

    def para(text="", size=SIZE_BODY, bold=False, align=None, indent=False,
             space_before=0, space_after=0, color=None):
        p = doc.add_paragraph()
        if align is not None:
            p.alignment = align
        pf = p.paragraph_format
        pf.line_spacing = LINE_SPACING
        pf.space_before = Pt(space_before)
        pf.space_after = Pt(space_after)
        if indent:
            pf.first_line_indent = Pt(size * 2)
        r = p.add_run(text)
        r.font.name = FONT_CN
        r.font.size = Pt(size)
        r.bold = bold
        r._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT_CN)
        if color:
            from docx.shared import RGBColor
            r.font.color.rgb = RGBColor.from_string(color)
        return p

    para(title, SIZE_TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)
    para(f"满分 {total:g} 分｜{SOURCE}", SIZE_NOTE, align=WD_ALIGN_PARAGRAPH.CENTER,
         space_after=8, color="595959")
    para("实验名称：＿＿＿＿＿＿＿＿＿＿　　学号：＿＿＿＿＿＿＿＿　　姓名：＿＿＿＿＿＿",
         SIZE_BODY - 1, space_after=6)

    headers = ["评分维度", "分值", "满分要求", "扣分细则", "得分"] if not blank \
        else ["评分维度", "分值", "得分", "扣分说明"]
    table = doc.add_table(rows=len(dims) + 1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = ""
        r = cell.paragraphs[0].add_run(h)
        r.font.name = FONT_CN
        r.font.size = Pt(SIZE_BODY - 1)
        r.bold = True
        r._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT_CN)
    for i, d in enumerate(dims, 1):
        if blank:
            vals = [str(d.get("name", "")), f"{float(d.get('score', 0)):g}", "", ""]
        else:
            vals = [str(d.get("name", "")), f"{float(d.get('score', 0)):g}",
                    str(d.get("full", "")), "；".join(str(x) for x in d.get("deduct") or []), ""]
        for j, v in enumerate(vals):
            cell = table.cell(i, j)
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.line_spacing = 1.15
            r = p.add_run(v)
            r.font.name = FONT_CN
            r.font.size = Pt(SIZE_NOTE + 1)
            r._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT_CN)
    widths = (Cm(3.2), Cm(1.2), Cm(5.2), Cm(4.4), Cm(1.2)) if not blank else \
        (Cm(4.0), Cm(1.6), Cm(1.6), Cm(9.0))
    for row in table.rows:
        for w, cell in zip(widths, row.cells):
            cell.width = w

    para(f"总分：＿＿＿＿＿ / {total:g}", SIZE_BODY, bold=True, space_before=10, space_after=6)
    para("使用说明", SIZE_BODY, bold=True, space_before=6, space_after=2)
    for k, r in enumerate(RED_LINES, 1):
        para(f"（{k}）{r}", SIZE_BODY - 1)
    para("评语", SIZE_BODY, bold=True, space_before=8, space_after=2)
    for _ in range(2):
        para("＿" * 45, SIZE_BODY - 1)

    deid.set_docx_props(doc, title=title, category="实验评分表")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="实验报告 6 维度评分表")
    ap.add_argument("-o", "--out", help="输出 docx")
    ap.add_argument("--md", help="同时导出 markdown")
    ap.add_argument("--dims", help="教师提供的维度json")
    ap.add_argument("--example", action="store_true", help="显式采用内置示例，不代表课程标准")
    ap.add_argument("--title", default="实验报告评分表（草稿，采用前核对）")
    ap.add_argument("--blank", action="store_true", help="打印批改用：不印细则，只留得分格")
    ap.add_argument("--total", type=float, default=100)
    ap.add_argument("--check", action="store_true", help="只校验分值，不出文件")
    ap.add_argument("--strict", action="store_true", help="有错误时退出码 1")
    a = ap.parse_args(argv)

    if bool(a.dims) == bool(a.example):
        ap.error("提供--dims或--example之一")
    dims = [dict(d) for d in DEFAULT_DIMS] if a.example else load_dims(a.dims)
    issues = check(dims, a.total)
    print(format_issues(issues))
    if any(issue[0] == "error" for issue in issues):
        return 1

    if a.check or not a.out:
        return 1 if (a.strict and any(i[0] == "error" for i in issues)) else 0

    if a.md:
        Path(a.md).parent.mkdir(parents=True, exist_ok=True)
        Path(a.md).write_text(to_md(dims, a.title, blank=a.blank), encoding="utf-8")
        print(f"markdown: {a.md}")
    out = build_docx(dims, a.out, a.title, blank=a.blank)
    print(f"docx: {out}（{'空白批改版' if a.blank else '标准版'}）")
    return 1 if (a.strict and any(i[0] == "error" for i in issues)) else 0


if __name__ == "__main__":
    sys.exit(main())
