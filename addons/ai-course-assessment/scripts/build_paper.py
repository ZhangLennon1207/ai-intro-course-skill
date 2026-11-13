#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""题库 json -> 学生卷 / 教师卷 docx + 复核记录。出题的最后一步，也是唯一能机检的一步。

用法：
    python build_paper.py 题库_单元3.json --blueprint out/蓝图表_单元3.json \\
        -o out/试卷_单元3 --check --strict
    # 产物：试卷_单元3_学生卷.docx、试卷_单元3_教师卷.docx、试卷_单元3_复核记录.md

只做排版与复核，不生成题目。题目从哪来是人的事；这里负责让「答案漏了」「选项两个一样」
「简答没给评分细则」在交付前暴露出来。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deid  # noqa: E402  同目录脱敏模块
import kp     # noqa: E402  同目录知识点编码模块

FONT_CN = "宋体"
SIZE_TITLE = 16
SIZE_BODY = 12
SIZE_NOTE = 9
LINE_SPACING = 1.5

TYPE_ORDER = ["single", "multi", "judge", "blank", "short", "comp"]
TYPE_NAME = {
    "single": "单项选择题", "multi": "多项选择题", "judge": "判断题",
    "blank": "填空题", "short": "简答题", "comp": "综合分析题",
}
TYPE_INSTRUCTION = {
    "single": "每题只有一个正确答案，把答案写在题号后的括号内。",
    "multi": "每题有两个或两个以上正确答案，多选、少选、错选均不得分。",
    "judge": "在题号后的括号内作答：正确的打「√」，错误的打「×」。",
    "blank": "将答案写在横线上。",
    "short": "写出要点即可，按评分细则给分。",
    "comp": "要求写出分析过程与结论。",
}
JUDGE_OK = {"对", "错", "√", "×", "T", "F", "正确", "错误", "是", "否"}
LETTERS = "ABCDEFGH"


# ---------- 读取 ----------
def load_json(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"找不到文件：{p}")
    return json.loads(p.read_text(encoding="utf-8"))


def flat_questions(bank: dict) -> list[dict]:
    """支持两种结构：扁平 questions 列表，或 groups 分组。统一拍平。"""
    if isinstance(bank.get("questions"), list):
        return bank["questions"]
    out = []
    for g in bank.get("groups") or []:
        for q in g.get("questions") or []:
            q = dict(q)
            q.setdefault("type", g.get("type"))
            out.append(q)
    return out


# ---------- 复核 ----------
def _norm(s: str) -> str:
    return re.sub(r"[\s，。、；：？！,.;:?!（）()【】\[\]“”\"']", "", str(s or ""))


def q_points(q: dict) -> list[str]:
    """知识点可写 point（单个）或 points（多个），两种都收。"""
    ps = q.get("points") or ([q.get("point")] if q.get("point") else [])
    return [str(p).strip() for p in ps if str(p).strip()]


def check_questions(bank: dict, blueprint: dict | None = None, table=None) -> list[tuple[str, str, str]]:
    issues: list[tuple[str, str, str]] = []
    qs = flat_questions(bank)
    if not qs:
        return [("error", "题库", "一道题都没有")]

    table = table or {}
    seen_ids = set()
    seen_stem: dict[str, str] = {}
    total = 0
    for i, q in enumerate(qs, 1):
        qid = str(q.get("id") or f"#{i}")
        loc = f"第{i}题（{qid}）"
        if not q.get("id") or qid in seen_ids:
            issues.append(("error", loc, "题号缺失或重复"))
        seen_ids.add(qid)
        qtype = str(q.get("type", ""))
        if qtype not in TYPE_NAME:
            issues.append(("error", loc, f"题型「{qtype}」不认识，只能是 {TYPE_ORDER}"))
            continue
        stem = str(q.get("stem", "")).strip()
        if not stem:
            issues.append(("error", loc, "题干为空"))
        if not q_points(q):
            issues.append(("warn", loc, "没写考查知识点，考后无法做知识点掌握度分析"))
        if table:
            ids = [str(x).strip() for x in (q.get("kp_ids") or []) if str(x).strip()]
            if ids:
                issues.extend(kp.check_refs(ids, table, loc))
            else:
                missing_kp = [p for p in q_points(q) if not kp.resolve(p, table)]
                if missing_kp:
                    issues.append(("warn", loc, f"知识点「{'、'.join(missing_kp)}」不在编码表里，"
                                                f"考后掌握度会单独成行"))
        score = q.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or score <= 0:
            issues.append(("error", loc, "分值缺失或非正数"))
        else:
            total += score

        key = _norm(stem)
        if key:
            if key in seen_stem:
                issues.append(("error", loc, f"与{seen_stem[key]}题干重复"))
            else:
                seen_stem[key] = loc

        ans = q.get("answer")
        if qtype in ("single", "multi"):
            opts = q.get("options") or []
            if not 2 <= len(opts) <= 6:
                issues.append(("error", loc, f"选项 {len(opts)} 个，应为 2–6 个"))
            clean = []
            for o in opts:
                s = re.sub(r"^\s*[A-Ha-h][.．、)）]\s*", "", str(o)).strip()
                clean.append(s)
            if len(set(clean)) != len(clean):
                issues.append(("error", loc, "有两个选项内容相同"))
            for bad in ("以上都", "都不对", "全部正确"):
                if any(bad in c for c in clean):
                    issues.append(("warn", loc, f"选项含「{bad}」，容易产生多解或争议"))
            letters = [c for c in str(ans or "").upper() if c.isalpha()]
            if not letters:
                issues.append(("error", loc, "没有答案字母"))
            else:
                out_of_range = [c for c in letters if c not in LETTERS[:len(opts)]]
                if out_of_range:
                    issues.append(("error", loc, f"答案 {ans} 超出选项范围（共 {len(opts)} 项）"))
                if qtype == "single" and len(letters) != 1:
                    issues.append(("error", loc, "单选题给了多个答案"))
                if qtype == "multi" and len(letters) < 2:
                    issues.append(("error", loc, "多选题答案少于两个"))
        elif qtype == "judge":
            if str(ans).strip() not in JUDGE_OK:
                issues.append(("error", loc, f"判断题答案「{ans}」不合规，用 √ / ×"))
        elif qtype == "blank":
            blanks = len(re.findall(r"_{2,}|＿{2,}", stem))
            ans_list = ans if isinstance(ans, list) else [ans]
            if blanks and len(ans_list) != blanks:
                issues.append(("error", loc, f"题干 {blanks} 个空，答案给了 {len(ans_list)} 个"))
            if not blanks:
                issues.append(("warn", loc, "填空题题干没有横线，学生不知道填在哪"))
        else:  # short / comp
            rubric = q.get("rubric") or []
            if not rubric:
                issues.append(("error", loc, "主观题没有评分细则（rubric），无法按点给分"))
            else:
                try:
                    values = [float(x.get("score", 0)) for x in rubric]
                    if any(not math.isfinite(value) or value < 0 for value in values):
                        raise ValueError("非法分值")
                    rs = sum(values)
                except (TypeError, ValueError):
                    issues.append(("error", loc, "评分细则含非法分值"))
                    rs = -1
                if isinstance(score, (int, float)) and abs(rs - score) > 0.01:
                    issues.append(("error", loc, f"评分细则合计 {rs} 分，与题目分值 {score} 不符"))
                for x in rubric:
                    if not str(x.get("point", "")).strip():
                        issues.append(("error", loc, "评分细则有一项没写给分点"))
        if not str(q.get("answer", "")).strip() and qtype not in ("short", "comp"):
            issues.append(("error", loc, "没有答案"))
        if q.get("analysis") is None and qtype in ("single", "multi", "judge"):
            issues.append(("warn", loc, "没有解析，教师讲评时要现想"))

    # 全卷
    declared = (bank.get("meta") or {}).get("total")
    if declared and abs(total - declared) > 0.01:
        issues.append(("error", "全卷", f"题目分值合计 {total}，与声明满分 {declared} 不符"))
    if blueprint:
        bp_total = blueprint["meta"]["total"]
        if abs(total - bp_total) > 0.01:
            issues.append(("error", "全卷", f"题目合计 {total} 分，细目表要求 {bp_total} 分"))
        issues.extend(_check_against_blueprint(qs, blueprint))
    return issues


def _check_against_blueprint(qs: list[dict], bp: dict) -> list[tuple[str, str, str]]:
    issues = []
    # 每个细目表行都要有题顶着（按题型 + 知识点）
    q_points_all = [(str(q.get("type")), set(q_points(q))) for q in qs]
    for row in bp.get("rows") or []:
        want = set(map(str, row.get("points") or []))
        hit = [1 for t, ps in q_points_all if t == row.get("type") and (want & ps)]
        if not hit:
            issues.append(("error", f"题号{row.get('no')}",
                           f"细目表要求的「{'、'.join(want)}」没有对应题目"))
    # 层次分布
    got: dict[str, float] = {}
    for q in qs:
        got[str(q.get("level", "未标注"))] = got.get(str(q.get("level", "未标注")), 0) + float(q.get("score", 0))
    total = sum(got.values()) or 1
    for lv, target_pct in (bp["meta"].get("level_quota") or {}).items():
        actual = got.get(lv, 0) / total * 100
        if abs(actual - target_pct) > 10:
            issues.append(("warn", "层次", f"{lv}实际 {actual:.0f}%，目标 {target_pct}%，偏差超过 10 个百分点"))
    return issues


def format_issues(issues) -> str:
    if not issues:
        return "结构检查未发现问题；内容准确性、打印版式以及未提供的细目表不在此结论内。"
    lines = []
    for lv, loc, msg in issues:
        lines.append(f"{'[错误]' if lv == 'error' else '[提醒]'} {loc}：{msg}")
    err = sum(1 for x in issues if x[0] == "error")
    lines.append(f"\n合计 {len(issues)} 条：错误 {err}，提醒 {len(issues) - err}")
    return "\n".join(lines)


# ---------- docx ----------
def _font(run, size, bold=False, color=None):
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor
    run.font.name = FONT_CN
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rf)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rf.set(qn(a), FONT_CN)


def _para(doc, text="", indent=False, size=SIZE_BODY, bold=False, align=None,
          space_before=0, space_after=0, left=0.0):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt
    p = doc.add_paragraph()
    p.alignment = align if align is not None else WD_ALIGN_PARAGRAPH.JUSTIFY
    pf = p.paragraph_format
    pf.line_spacing = LINE_SPACING
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    if left:
        pf.left_indent = Cm(left)
    if indent:
        pf.first_line_indent = Pt(size * 2)
    if text:
        _font(p.add_run(text), size, bold)
    return p


def build_docx(bank: dict, out_path: str | Path, teacher: bool = False,
               blueprint: dict | None = None) -> Path:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm

    meta = bank.get("meta") or {}
    qs = flat_questions(bank)
    groups: dict[str, list[dict]] = {}
    for q in qs:
        groups.setdefault(str(q.get("type")), []).append(q)
    order = [t for t in TYPE_ORDER if t in groups]

    doc = Document()
    s = doc.sections[0]
    s.top_margin = s.bottom_margin = Cm(2.54)
    s.left_margin = s.right_margin = Cm(2.6)

    # 卷头
    head = _para(doc, str(meta.get("school", "")), size=SIZE_BODY - 1,
                 align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    title = _para(doc, str(meta.get("title") or f"《{meta.get('course', '')}》{meta.get('exam', '考试')}试卷"),
                  size=SIZE_TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)
    exam_mode = "开卷" if meta.get("open_book") is True else "闭卷" if meta.get("open_book") is False else "考试方式未指定"
    info = (f"{meta.get('term', '学期未指定')}　"
            f"{exam_mode}　"
            f"满分 {meta.get('total', sum(float(q.get('score', 0)) for q in qs)):g} 分　"
            f"考试时间 {meta.get('minutes', '未指定')} 分钟")
    _para(doc, info, size=SIZE_BODY - 1, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)
    _para(doc, "姓名＿＿＿＿＿＿＿　学号＿＿＿＿＿＿＿＿＿＿　班级＿＿＿＿＿＿＿　成绩＿＿＿＿＿",
          size=SIZE_BODY - 1, space_after=8)
    if not teacher:
        rule = str(meta.get("instructions") or "材料与设备使用范围以任课教师说明为准。")
        _para(doc, f"考生须知：答案写在答题区内，字迹清楚；{rule}", size=SIZE_NOTE, space_after=8)
    else:
        _para(doc, "【教师版】含答案、解析与评分细则，不得下发给学生。",
              size=SIZE_NOTE, space_after=8)

    cn_no = "一二三四五六七八九十"
    for gi, t in enumerate(order):
        items = groups[t]
        sub = sum(float(q.get("score", 0)) for q in items)
        _para(doc, f"{cn_no[gi]}、{TYPE_NAME[t]}（共 {len(items)} 小题，共 {sub:g} 分）",
              size=SIZE_BODY, bold=True, space_before=8, space_after=2)
        _para(doc, TYPE_INSTRUCTION.get(t, ""), size=SIZE_BODY - 1, space_after=4)
        for qi, q in enumerate(items, 1):
            stem = str(q.get("stem", "")).strip()
            score = float(q.get("score", 0))
            suffix = "（　　）" if t in ("single", "multi", "judge") else ""
            # 分值、答题括号都放题号后：跟着题干走会在换行处被拆成孤零零的「（2 分）」
            _para(doc, f"{qi}．（{score:g} 分）{suffix}{stem}", space_before=4)
            if t in ("single", "multi"):
                for li, opt in enumerate(q.get("options") or []):
                    text = re.sub(r"^\s*[A-Ha-h][.．、)）]\s*", "", str(opt))
                    _para(doc, f"{LETTERS[li]}．{text}", left=0.74)
            if not teacher and t in ("short", "comp"):
                lines = max(4, int(score * 0.9) + 3)      # 按分值给书写空间，不按固定行数
                for _ in range(lines):
                    _para(doc, "＿" * 38, left=0.0)
            if teacher:
                ans = q.get("answer")
                ans_text = "；".join(map(str, ans)) if isinstance(ans, list) else str(ans)
                _para(doc, f"【答案】{ans_text}", size=SIZE_BODY - 1, bold=True, space_before=2)
                if q.get("analysis"):
                    _para(doc, f"【解析】{q['analysis']}", size=SIZE_BODY - 1)
                if q.get("rubric"):
                    _para(doc, "【评分细则】", size=SIZE_BODY - 1, bold=True)
                    for r in q["rubric"]:
                        _para(doc, f"· {r.get('point', '')}（{float(r.get('score', 0)):g} 分）",
                              size=SIZE_BODY - 1, left=0.74)
    deid.set_docx_props(doc, title=str(meta.get("title") or meta.get("exam", "试卷")),
                        category="课程试卷（教师版）" if teacher else "课程试卷（学生版）")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


def to_review(bank: dict, issues, blueprint: dict | None, table=None) -> str:
    meta = bank.get("meta") or {}
    qs = flat_questions(bank)
    total = sum(float(q.get("score", 0)) for q in qs)
    lines = [f"# 复核记录｜{meta.get('title') or meta.get('exam', '试卷')}", ""]
    exam_mode = "开卷" if meta.get("open_book") is True else "闭卷" if meta.get("open_book") is False else "考试方式未指定"
    lines.append(f"题量 {len(qs)} 道｜总分 {total:g} 分｜"
                 f"{exam_mode}｜{meta.get('minutes', '未指定')} 分钟")
    lines.append("")
    by_type = {}
    for q in qs:
        k = str(q.get("type"))
        by_type.setdefault(k, [0, 0.0])
        by_type[k][0] += 1
        by_type[k][1] += float(q.get("score", 0))
    lines.append("| 题型 | 题数 | 分值 |")
    lines.append("|---|---|---|")
    for t in TYPE_ORDER:
        if t in by_type:
            lines.append(f"| {TYPE_NAME[t]} | {by_type[t][0]} | {by_type[t][1]:g} |")
    lines.append("")
    if blueprint:
        lines.append("## 与细目表对账")
        lines.append("")
        lines.append(f"细目表 {len(blueprint.get('rows') or [])} 题 / {blueprint['meta']['total']} 分，"
                     f"实际 {len(qs)} 题 / {total:g} 分。")
        lines.append("")
    lines.append("## 试卷信息")
    lines.append("")
    lines.append(f"- 题库来源：{deid.scrub_text(str(meta.get('source') or '未填写'))}")
    lines.append(f"- 教材版本：{meta.get('textbook') or '未填写（开卷考试需与考生所带教材对得上章节）'}")
    lines.append("- 已执行结构与常见联系方式模式检查；这不能证明内容正确或全文已去标识。")
    table = table or {}
    if table:
        used = [i for q in flat_questions(bank) for i in (q.get("kp_ids") or []) if str(i).strip()]
        covered = set(used)
        uncovered = [k for k in table if k not in covered]
        line = f"- 知识点编码：表内 {len(table)} 条，本卷覆盖 {len(covered)} 条"
        if uncovered:
            line += f"，未考到 {'、'.join(uncovered)}（仅按本次显式映射核对）"
        lines.append(line)
    lines.append("")
    lines.append("## 复核结论")
    lines.append("")
    lines.extend(format_issues(issues).splitlines())
    lines.append("")
    lines.append("> 计划层次不等于实测难度。考后用作答数据算难度（得分率）与区分度，"
                 "凭这份记录不能说题目难易合适。")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="题库 -> 学生卷/教师卷 + 复核记录")
    ap.add_argument("bank", help="题库 json")
    ap.add_argument("-o", "--out-prefix", required=True, help="输出前缀，如 out/试卷_单元3")
    ap.add_argument("--blueprint", help="细目表 json，给了就对账")
    ap.add_argument("--kp", help="项目知识点映射CSV；省略时保留题库名称与编号，不套示例")
    ap.add_argument("--check", action="store_true", help="只复核，不出文件")
    ap.add_argument("--strict", action="store_true", help="有错误时退出码 1")
    a = ap.parse_args(argv)

    bank = load_json(a.bank)
    bp = load_json(a.blueprint) if a.blueprint else None
    table = kp.load(a.kp)
    issues = check_questions(bank, bp, table)
    for kind, val in deid.scan(json.dumps(bank, ensure_ascii=False)):
        issues.append(("error", "隐私检查", f"发现{kind}模式，命中内容不写入报告；请核对原始文件"))
    print(format_issues(issues))

    if any(issue[0] == "error" for issue in issues):
        return 1

    if not a.check:
        prefix = Path(a.out_prefix)
        st = build_docx(bank, str(prefix) + "_学生卷.docx", teacher=False, blueprint=bp)
        tt = build_docx(bank, str(prefix) + "_教师卷.docx", teacher=True, blueprint=bp)
        rv = prefix.parent / (prefix.name + "_复核记录.md")
        rv.parent.mkdir(parents=True, exist_ok=True)
        rv.write_text(to_review(bank, issues, bp, table), encoding="utf-8")
        print(f"学生卷: {st}\n教师卷: {tt}\n复核记录: {rv}")

    if a.strict and any(i[0] == "error" for i in issues):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
