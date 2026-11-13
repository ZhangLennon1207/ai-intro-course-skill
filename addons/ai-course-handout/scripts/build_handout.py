#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""讲义源 -> docx / md，带结构自检。

用法：
    python build_handout.py 讲义源.json -o out/讲义.docx --md out/讲义.md --check
    python build_handout.py 讲义源.json -o out/讲义_学生版.docx --student
    python build_handout.py 讲义源.json --check --strict      # 只查不生成

讲义源结构见 assets/sample-handout.json。五段缺一段即报错，不静默补空。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deid  # noqa: E402
import kp     # noqa: E402  同目录知识点编码模块

# ---------- 版式常量（改这里等于改全篇） ----------
FONT_CN = "宋体"
SIZE_TITLE = 16      # 三号
SIZE_SECTION = 14    # 四号
SIZE_BODY = 12       # 小四
SIZE_NOTE = 9        # 小五
LINE_SPACING = 1.5
FIRST_LINE_CHARS = 200  # 首行缩进 2 字符（单位：1/100 字符）
MARGIN_TB = 2.54
MARGIN_LR = 3.17
LEVELS = ("复述", "应用", "辨析")


# ---------- 读取 ----------
def load(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"找不到讲义源：{p}")
    txt = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        return json.loads(txt)
    raise SystemExit("讲义源只支持 .json；从课件/教材转来的先用 from_slides.py 转成 json")


# ---------- 自检 ----------
def check(src: dict, table=None) -> list[tuple[str, str, str]]:
    """返回 [(级别, 位置, 说明)]，级别 error / warn。"""
    issues: list[tuple[str, str, str]] = []
    meta = src.get("meta") or {}
    for k in ("course", "chapter"):
        if not str(meta.get(k, "")).strip():
            issues.append(("error", "meta", f"缺 {k}，讲义封面无法标注"))
    if not str(meta.get("audience", "")).strip():
        issues.append(("warn", "meta", "没写目标读者（专业门类/先修），难度无法复核"))

    sections = src.get("sections") or []
    if not sections:
        issues.append(("error", "sections", "一节都没有"))
        return issues

    seen: set[str] = set()
    for i, sec in enumerate(sections, 1):
        loc = f"第{i}节《{sec.get('title', '无标题')}》"
        if not str(sec.get("title", "")).strip():
            issues.append(("error", loc, "缺节标题"))
        if sec.get("title") in seen:
            issues.append(("warn", loc, "节标题重复，读目录会分不清"))
        seen.add(sec.get("title"))

        # 1 一句话结论
        if not str(sec.get("conclusion", "")).strip():
            issues.append(("error", loc, "缺『一句话结论』：先说这节解决什么问题"))
        # 2 概念解释
        concepts = sec.get("concepts") or []
        if not concepts:
            issues.append(("error", loc, "缺『概念解释』"))
        for c in concepts:
            name = c.get("term", "未命名概念")
            if not str(c.get("def", "")).strip():
                issues.append(("error", loc, f"概念《{name}》没有定义"))
            if not str(c.get("not", "")).strip():
                issues.append(("error", loc, f"概念《{name}》没写『它不是什么』，边界没划"))
        # 3 例子：正例 + 反例/失效
        exs = sec.get("examples") or []
        kinds = [str(e.get("kind", "")) for e in exs]
        if not any("正" in k for k in kinds):
            issues.append(("error", loc, "缺正例"))
        if not any(("反" in k or "失效" in k) for k in kinds):
            issues.append(("error", loc, "缺反例/失效场景：只给正例学生不会判断边界"))
        for e in exs:
            if ("反" in str(e.get("kind", "")) or "失效" in str(e.get("kind", ""))) \
                    and not str(e.get("why", "")).strip():
                issues.append(("error", loc, "反例没写为什么失效"))
            if not str(e.get("text", "")).strip():
                issues.append(("error", loc, "例子正文为空"))
        # 4 易错点
        pits = [p for p in (sec.get("pitfalls") or []) if str(p).strip()]
        if not pits:
            issues.append(("error", loc, "缺『易错点』：不写学生真实会犯的错，等于没写"))
        for p in pits:
            if re.search(r"注意理解|认真掌握|加强练习|重点把握", str(p)):
                issues.append(("warn", loc, f"易错点写成空话：{p}"))
        # 5 练习
        exs2 = sec.get("exercises") or []
        if len(exs2) < 2:
            issues.append(("error", loc, f"练习只有 {len(exs2)} 题，至少 2 题"))
        lv = set()
        for j, q in enumerate(exs2, 1):
            level = str(q.get("level", ""))
            if level not in LEVELS:
                issues.append(("error", loc, f"练习{j} 层次『{level}』不在 {LEVELS} 内"))
            else:
                lv.add(level)
            if not str(q.get("q", "")).strip():
                issues.append(("error", loc, f"练习{j} 题干为空"))
            if not str(q.get("answer", "")).strip():
                issues.append(("error", loc, f"练习{j} 没有答案要点"))
        if exs2 and len(lv) < 2:
            issues.append(("warn", loc, "练习只覆盖 1 个层次，补一题复述/应用/辨析"))

        # 公式符号
        body = json.dumps(sec, ensure_ascii=False)
        if ("$" in body or "＝" in body or "=" in body) and not sec.get("symbols"):
            issues.append(("warn", loc, "出现公式但没有 symbols 符号表（符号/含义/单位）"))
        # 来源
        if not (sec.get("sources") or []):
            issues.append(("warn", loc, "没写来源，无法核到章节号"))

    # 知识点编码：节上挂了 kp_ids 就必须在表里，讲义与试卷才对得上号
    table = table or {}
    all_ids = [i for sec in src.get("sections") or [] for i in (sec.get("kp_ids") or [])]
    if all_ids:
        issues.extend(kp.check_refs(all_ids, table, "知识点编码"))
    elif not table:
        issues.append(("warn", "知识点编码", "未提供项目编码表，保留输入名称与编号，不自动套用包内示例"))

    # 全篇级
    if not (src.get("references") or []):
        issues.append(("warn", "封面", "缺整体来源对照表（章节号 -> 页码/标题）"))
    if not str(meta.get("textbook", "")).strip():
        issues.append(("warn", "meta", "未写教材版本，请按实际使用的资料核对来源"))
    # 脱敏：扫将要交付的全文（教材署名豁免）
    for kind, val in deid.scan(json.dumps(src, ensure_ascii=False)):
        issues.append(("error", "分发检查", f"发现{kind}（命中值不回显），请检查分发范围"))
    return issues


def format_issues(issues) -> str:
    if not issues:
        return "自检通过：五段齐、练习层次达标、来源非空。"
    lines = []
    for lv, loc, msg in issues:
        tag = "[错误]" if lv == "error" else "[提醒]"
        lines.append(f"{tag} {loc}：{msg}")
    err = sum(1 for i in issues if i[0] == "error")
    lines.append(f"\n合计 {len(issues)} 条：错误 {err}，提醒 {len(issues) - err}")
    return "\n".join(lines)


# ---------- markdown ----------
def to_markdown(src: dict, student: bool = False) -> str:
    meta = src.get("meta") or {}
    out: list[str] = []
    out.append(f"# {meta.get('chapter', '')}")
    sub = "｜".join(x for x in [meta.get("course", ""), meta.get("audience", "")] if x)
    if sub:
        out.append(f"> {sub}")
    if meta.get("textbook"):
        out.append(f"> 教材：{meta['textbook']}")
    out.append("")
    for sec in src.get("sections") or []:
        no = sec.get("no", "")
        out.append(f"## {no} {sec.get('title', '')}".replace("  ", " "))
        out.append("")
        if sec.get("conclusion"):
            out.append(str(sec["conclusion"]))
            out.append("")
        for c in sec.get("concepts") or []:
            out.append(f"**{c.get('term', '')}**　{c.get('def', '')}")
            if c.get("not"):
                out.append(f"它不是什么：{c['not']}")
            if c.get("boundary"):
                out.append(f"边界：{c['boundary']}")
            out.append("")
        for e in sec.get("examples") or []:
            kind = e.get("kind", "例")
            text = e.get("text", "")
            out.append(f"- **{kind}**：{text}" + (f"（{e['why']}）" if e.get("why") else ""))
        if sec.get("examples"):
            out.append("")
        if sec.get("pitfalls"):
            out.append("**容易错的**")
            out.append("")
            for p in sec["pitfalls"]:
                out.append(f"- {p}")
            out.append("")
        if sec.get("exercises"):
            out.append("**练一练**")
            out.append("")
            for j, q in enumerate(sec["exercises"], 1):
                out.append(f"{j}. （{q.get('level', '')}）{q.get('q', '')}")
                if not student and q.get("answer"):
                    out.append(f"   - 答案要点：{q['answer']}")
            out.append("")
        if sec.get("symbols"):
            out.append("**符号表**")
            out.append("")
            out.append("| 符号 | 含义 | 单位/取值 |")
            out.append("|---|---|---|")
            for s in sec["symbols"]:
                out.append(f"| {s.get('sym', '')} | {s.get('mean', '')} | {s.get('unit', '')} |")
            out.append("")
        if sec.get("sources"):
            out.append(f"<sub>来源：{'；'.join(sec['sources'])}</sub>")
            out.append("")
    if src.get("references"):
        out.append("## 来源对照")
        out.append("")
        out.append("| 讲义位置 | 依据 |")
        out.append("|---|---|")
        for r in src["references"]:
            out.append(f"| {r.get('where', '')} | {r.get('from', '')} |")
        out.append("")
    return "\n".join(out)


# ---------- docx ----------
def _set_run_font(run, size: float, bold: bool = False, color: str | None = None):
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    run.font.name = FONT_CN
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), FONT_CN)


def _body_para(doc, text: str, indent: bool = True, size: float = SIZE_BODY,
               bold: bool = False, space_after: float = 0, space_before: float = 0,
               keep_next: bool = False):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Pt

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf = p.paragraph_format
    pf.line_spacing = LINE_SPACING
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.keep_with_next = keep_next
    if indent:
        # 东亚版式的「首行缩进 2 字符」，随字号自动换算
        ind = p._p.get_or_add_pPr().makeelement(
            qn("w:ind"), {qn("w:firstLineChars"): str(FIRST_LINE_CHARS), qn("w:firstLine"): "480"})
        p._p.get_or_add_pPr().append(ind)
    run = p.add_run(text)
    _set_run_font(run, size, bold)
    return p


def _heading(doc, text: str, size: float, level: int = 1):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    p = doc.add_paragraph()
    p.style = doc.styles[f"Heading {level}"]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if level == 1 else WD_ALIGN_PARAGRAPH.LEFT
    pf = p.paragraph_format
    pf.line_spacing = LINE_SPACING
    pf.space_before = Pt(12 if level == 1 else 10)
    pf.space_after = Pt(6)
    pf.first_line_indent = None
    run = p.add_run(text)
    _set_run_font(run, size, bold=True, color="000000")
    return p


def _add_page_number(doc):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    footer = doc.sections[0].footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    _set_run_font(run, SIZE_NOTE, color="595959")
    for instr in ("begin", "PAGE", "end"):
        if instr == "PAGE":
            fld = OxmlElement("w:instrText")
            fld.set(qn("xml:space"), "preserve")
            fld.text = " PAGE "
            run._r.append(fld)
        else:
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), instr)
            run._r.append(fc)


def _cell_text(par, text: str, size: float):
    """写单元格。x_j 这种写法要排成真下标，否则读者会把下划线当成字符。"""
    m = re.match(r"^([^\W\d_])(_\{[^}]*\}|_[A-Za-z0-9]+)$", text)
    if not m:
        _set_run_font(par.add_run(text), size)
        return
    _set_run_font(par.add_run(m.group(1)), size)
    sub = m.group(2).lstrip("_").strip("{}")
    r = par.add_run(sub)
    _set_run_font(r, size)
    r.font.subscript = True


def build_docx(src: dict, out_path: str | Path, student: bool = False) -> Path:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    meta = src.get("meta") or {}
    doc = Document()

    # 页面与正文样式
    sec0 = doc.sections[0]
    sec0.top_margin = Cm(MARGIN_TB)
    sec0.bottom_margin = Cm(MARGIN_TB)
    sec0.left_margin = Cm(MARGIN_LR)
    sec0.right_margin = Cm(MARGIN_LR)

    normal = doc.styles["Normal"]
    normal.font.name = FONT_CN
    normal.font.size = Pt(SIZE_BODY)
    normal.element.rPr.rFonts.set(
        __import__("docx.oxml.ns", fromlist=["qn"]).qn("w:eastAsia"), FONT_CN)
    normal.paragraph_format.line_spacing = LINE_SPACING
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)

    # 封面标题
    _heading(doc, str(meta.get("chapter", "讲义")), SIZE_TITLE, level=1)
    sub = "｜".join(x for x in [meta.get("course", ""), meta.get("audience", "")] if x)
    if sub:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(12)
        _set_run_font(p.add_run(sub), SIZE_NOTE + 1, color="595959")
    if meta.get("textbook"):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(12)
        _set_run_font(p.add_run(f"教材：{meta['textbook']}"), SIZE_NOTE, color="595959")

    for sec in src.get("sections") or []:
        no = str(sec.get("no", "")).strip()
        title = f"{no}　{sec.get('title', '')}".strip()
        _heading(doc, title, SIZE_SECTION, level=2)

        if sec.get("conclusion"):
            _body_para(doc, str(sec["conclusion"]))

        for c in sec.get("concepts") or []:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            pf = p.paragraph_format
            pf.line_spacing = LINE_SPACING
            pf.first_line_indent = None
            _set_run_font(p.add_run(f"{c.get('term', '')}　"), SIZE_BODY, bold=True)
            _set_run_font(p.add_run(str(c.get("def", ""))), SIZE_BODY)
            if c.get("not"):
                q = doc.add_paragraph()
                q.paragraph_format.line_spacing = LINE_SPACING
                q.paragraph_format.left_indent = Cm(0.74)
                q.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                _set_run_font(q.add_run("它不是什么："), SIZE_BODY, bold=True)
                _set_run_font(q.add_run(str(c["not"])), SIZE_BODY)
            if c.get("boundary"):
                q = doc.add_paragraph()
                q.paragraph_format.line_spacing = LINE_SPACING
                q.paragraph_format.left_indent = Cm(0.74)
                q.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                _set_run_font(q.add_run("边界："), SIZE_BODY, bold=True)
                _set_run_font(q.add_run(str(c["boundary"])), SIZE_BODY)

        for e in sec.get("examples") or []:
            text = f"{e.get('kind', '例')}：{e.get('text', '')}"
            if e.get("why"):
                text += f"（{e['why']}）"
            _body_para(doc, text)

        if sec.get("pitfalls"):
            _body_para(doc, "容易错的", indent=False, bold=True, space_before=8, space_after=3, keep_next=True)
            for k, pit in enumerate(sec["pitfalls"], 1):
                _body_para(doc, f"（{k}）{pit}", indent=False)

        if sec.get("exercises"):
            _body_para(doc, "练一练", indent=False, bold=True, space_before=8, space_after=3, keep_next=True)
            for j, q in enumerate(sec["exercises"], 1):
                _body_para(doc, f"{j}.（{q.get('level', '')}）{q.get('q', '')}", indent=False)
                if not student and q.get("answer"):
                    p = _body_para(doc, f"答案要点：{q['answer']}", indent=False)
                    p.paragraph_format.left_indent = Cm(0.74)

        if sec.get("symbols"):
            _body_para(doc, "符号表", indent=False, bold=True, space_before=8, space_after=3, keep_next=True)
            rows = len(sec["symbols"]) + 1
            table = doc.add_table(rows=rows, cols=3)
            table.style = "Table Grid"
            hdr = ("符号", "含义", "单位/取值")
            for j, h in enumerate(hdr):
                cell = table.cell(0, j)
                cell.text = ""
                _set_run_font(cell.paragraphs[0].add_run(h), SIZE_BODY - 1, bold=True)
            for i, s in enumerate(sec["symbols"], 1):
                for j, key in enumerate(("sym", "mean", "unit")):
                    cell = table.cell(i, j)
                    cell.text = ""
                    _cell_text(cell.paragraphs[0], str(s.get(key, "")), SIZE_BODY - 1)
            for row in table.rows:          # 均分列宽会让「符号」列浪费半页，按内容定宽
                for w, cell in zip((Cm(2.6), Cm(7.2), Cm(7.2)), row.cells):
                    cell.width = w

        if sec.get("sources"):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            _set_run_font(p.add_run("来源：" + "；".join(sec["sources"])), SIZE_NOTE, color="595959")

    if src.get("references"):
        _heading(doc, "来源对照", SIZE_SECTION, level=2)
        table = doc.add_table(rows=len(src["references"]) + 1, cols=2)
        table.style = "Table Grid"
        for j, h in enumerate(("讲义位置", "依据")):
            cell = table.cell(0, j)
            cell.text = ""
            _set_run_font(cell.paragraphs[0].add_run(h), SIZE_BODY - 1, bold=True)
        for i, r in enumerate(src["references"], 1):
            for j, key in enumerate(("where", "from")):
                cell = table.cell(i, j)
                cell.text = ""
                _set_run_font(cell.paragraphs[0].add_run(str(r.get(key, ""))), SIZE_BODY - 1)
        for row in table.rows:
            for w, cell in zip((Cm(8.0), Cm(9.0)), row.cells):
                cell.width = w

    _add_page_number(doc)
    deid.set_docx_props(doc, title=str(meta.get("chapter", "讲义")), category="课程讲义")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="讲义源 -> docx/md，带五段结构自检")
    ap.add_argument("source", help="讲义源 json")
    ap.add_argument("-o", "--out", help="输出 docx 路径")
    ap.add_argument("--md", help="同时导出 markdown")
    ap.add_argument("--student", action="store_true", help="学生版：不输出答案要点")
    ap.add_argument("--check", action="store_true", help="只跑自检")
    ap.add_argument("--strict", action="store_true", help="有错误时退出码 1")
    ap.add_argument("--kp", help="本次项目知识点CSV，未提供时不采用包内示例")
    ap.add_argument("--redact-name", action="append", default=[], help="本次需掩码的姓名，可重复；名单不写进Skill")
    a = ap.parse_args(argv)
    source_key = Path(a.source).resolve()
    destinations = [Path(value).resolve() for value in (a.out, a.md) if value]
    if source_key in destinations or len(destinations) != len(set(destinations)):
        ap.error("输出不能覆盖源JSON，DOCX与Markdown也不能使用同一路径")

    src = load(a.source)
    deid.configure(a.redact_name)
    try:
        table = kp.load(a.kp)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    issues = check(src, table)
    if a.check or not a.out:
        print(format_issues(issues))
        if a.strict and any(i[0] == "error" for i in issues):
            return 1
        if not a.out:
            return 0

    if a.md:
        Path(a.md).parent.mkdir(parents=True, exist_ok=True)
        Path(a.md).write_text(to_markdown(src, student=a.student), encoding="utf-8")
        print(f"markdown: {a.md}")
    if a.out:
        out = build_docx(src, a.out, student=a.student)
        print(f"docx: {out}（{'学生版' if a.student else '教师版'}）")
        if not (a.check):
            print(format_issues(issues))

    if a.strict and any(i[0] == "error" for i in issues):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
