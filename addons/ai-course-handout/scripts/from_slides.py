#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""课件故事板 -> 讲义源骨架（半成品，字段留空待补，不编内容）。

用法：
    python from_slides.py out/storyboard_单元3_C模式_改造后.json -o out/讲义源_单元3.json
    python from_slides.py 故事板.json -o 讲义源.json --md out/讲义骨架.md
    # 一讲配多份课件（单元 3 就是 03.pdf + 06/07/08 三份 pptx）：按文件顺序合并成一册
    python from_slides.py sb_03.json sb_06.json sb_07.json sb_08.json -o out/讲义源_单元3.json --textbook "《人工智能通识教程》"

只做三件事：按编号分节、把课件已有的话搬进来、把缺的字段列成 _todo。
不生成定义、不生成例子、不生成练习——这三样必须有人（或明确的生成步骤）来写，
脚本拼出来的句子看着像讲义，一查全是同义反复。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deid  # noqa: E402  同目录脱敏模块

KICKER_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)[\s、.．]*\s*(.*)$")


def _split_kicker(kicker: str) -> tuple[str, str]:
    m = KICKER_RE.match(kicker or "")
    if m:
        return m.group(1), m.group(2).strip()
    return "", (kicker or "").strip()


def _page_text(s: dict) -> list[str]:
    """把一页里学生看得见的话取出来（不含 note）。"""
    out: list[str] = []
    for p in s.get("points") or []:
        if isinstance(p, str):
            out.append(p)
    for key in ("left", "right"):
        col = s.get(key) or {}
        if isinstance(col, dict):
            out.extend([str(x) for x in col.get("points") or []])
    for row in s.get("rows") or []:
        if isinstance(row, list):
            out.append("｜".join(str(c) for c in row))
    for n in s.get("nodes") or []:
        if isinstance(n, dict) and n.get("label"):
            out.append(str(n["label"]))
    return out


def build(storyboard: dict) -> dict:
    meta_in = storyboard.get("meta") or {}
    memory = storyboard.get("memory") or {}
    slides = storyboard.get("slides") or []

    sections: list[dict] = []
    cur: dict | None = None
    for s in slides:
        stype = s.get("type")
        if stype in ("cover", "end", "spine"):
            continue
        kicker = str(s.get("kicker", "")).strip()
        no, title = _split_kicker(kicker)
        # 换节：编号变了才算新一节（同一节里每页 kicker 常写不同的页标题）
        same = cur is not None and (
            (no and no == cur["no"]) or (not no and kicker == cur["_kicker"]))
        if stype != "recall" and not same:
            cur = {
                "_kicker": kicker,
                "no": no,
                "title": title or str(s.get("title", "")),
                "conclusion": "",
                "concepts": [],
                "examples": [],
                "pitfalls": [],
                "exercises": [],
                "sources": [],
                "_pages": [],
                "_raw": [],
            }
            sections.append(cur)
        if cur is None:
            continue
        cur["_pages"].append(stype)
        cur["_raw"].extend(_page_text(s))
        if s.get("takeaway") and not cur["conclusion"]:
            cur["conclusion"] = str(s["takeaway"])
        for cov in s.get("covers") or []:
            if cov and cov not in [c["term"] for c in cur["concepts"]]:
                cur["concepts"].append({"term": cov, "def": "", "not": "", "boundary": ""})
        if stype == "recall" and s.get("answer"):
            cur["exercises"].append({
                "level": "复述",
                "q": str(s.get("title") or s.get("question") or ""),
                "answer": str(s["answer"]),
            })

    # 全讲易错点按关键词落到节：命中 coverage 词最多的节优先
    rest = list(memory.get("pitfalls") or [])
    for sec in sections:
        terms = [c["term"] for c in sec["concepts"]]
        hit = []
        for pit in list(rest):
            if any(t and t[:4] in pit for t in terms):
                hit.append(pit)
                rest.remove(pit)
        sec["pitfalls"] = hit
    if rest:
        if sections:
            sections[-1]["pitfalls"].extend(rest)
        else:
            sections.append({"no": "", "title": "全讲易错点", "conclusion": "",
                             "concepts": [], "examples": [], "pitfalls": rest,
                             "exercises": [], "sources": [], "_pages": [], "_raw": []})

    needs = []
    for sec in sections:
        if not sec["conclusion"]:
            needs.append(f"{sec['title']}：缺一句话结论")
        if any(not c["def"] for c in sec["concepts"]):
            needs.append(f"{sec['title']}：概念缺定义与「它不是什么」")
        if not sec["examples"]:
            needs.append(f"{sec['title']}：缺正例与反例")
        if len(sec["exercises"]) < 2:
            needs.append(f"{sec['title']}：练习不足 2 题")

    for sec in sections:
        raw = sec.pop("_raw")
        sec.pop("_pages")
        sec.pop("_kicker")
        sec["_material"] = raw

    total_cov = len(storyboard.get("coverage") or [])
    covered = {c["term"] for s in sections for c in s["concepts"]}
    missing = [c for c in (storyboard.get("coverage") or []) if c not in covered]

    return {
        "meta": {
            "course": meta_in.get("course", ""),
            "chapter": meta_in.get("chapter", ""),
            "audience": "",
            "unit": "",
            "draft": True,
            "source": f"{meta_in.get('source', '')}；由故事板 {meta_in.get('mode', '')} 模式抽取",
            "coverage_count": total_cov,
            "coverage_in_sections": len(covered),
        },
        "memory": memory,
        "_todo": needs,
        "_coverage_missing": missing,
        "sections": sections,
        "references": [],
    }


def _merge_section(dst: dict, src: dict) -> None:
    """同名节合并：概念去重、其余拼接，结论取先有的那句。"""
    if not dst.get("conclusion") and src.get("conclusion"):
        dst["conclusion"] = src["conclusion"]
    have = {c["term"] for c in dst.get("concepts") or []}
    for c in src.get("concepts") or []:
        if c["term"] not in have:
            dst["concepts"].append(c)
            have.add(c["term"])
    for key in ("examples", "pitfalls", "exercises"):
        dst.setdefault(key, [])
        dst[key].extend(src.get(key) or [])
    dst.setdefault("sources", [])
    for s in src.get("sources") or []:
        if s not in dst["sources"]:
            dst["sources"].append(s)
    dst.setdefault("_material", [])
    dst["_material"].extend(src.get("_material") or [])


def build_many(storyboards: list[dict], textbook: str = "", renumber: bool = True,
               labels: list[str] | None = None) -> dict:
    """多份故事板 -> 一册讲义源。单份时行为与 build() 完全一致。"""
    if len(storyboards) == 1:
        src = build(storyboards[0])
        if textbook:
            src["meta"]["textbook"] = textbook  # 书目署名不脱敏
        src["sections"] = [dict(s, sources=deid.scrub_sources(s.get("sources"))) for s in src["sections"]]
        return src

    sections: list[dict] = []
    todo: list[str] = []
    missing: list[str] = []
    for k, sb in enumerate(storyboards, 1):
        part = build(sb)
        # 先删姓名后缀再掩码：反过来会把 `-示例教师` 变成 `-***`，清洗不掉
        raw_tag = (labels[k - 1] if labels and k - 1 < len(labels) else "") \
            or str(part["meta"].get("source") or f"第{k}份课件")
        tag = deid.scrub_text(deid.clean_filename(raw_tag))
        for sec in part["sections"]:
            sec = dict(sec)
            sec["sources"] = deid.scrub_sources(sec.get("sources") or [tag])
            if not sec["sources"]:
                sec["sources"] = [tag]
            if sections and sections[-1]["title"] == sec["title"]:
                _merge_section(sections[-1], sec)
            else:
                sections.append(sec)
        # 待补清单带上是哪份课件的问题，否则四份混在一起找不到源头
        todo.extend(f"［{tag}］{t}" for t in part.get("_todo") or [])
        missing.extend(part.get("_coverage_missing") or [])

    if renumber:
        for i, sec in enumerate(sections, 1):
            sec["no"] = str(i)

    first = (storyboards[0].get("meta") or {})
    src = {
        "meta": {
            "course": first.get("course", ""),
            "chapter": first.get("chapter", ""),
            "audience": "",
            "unit": "",
            "draft": True,
            "source": "；".join(deid.scrub_text(str(s.get("meta", {}).get("source", ""))) for s in storyboards),
            "textbook": textbook,  # 书目署名不脱敏
            "coverage_count": sum(len(s.get("coverage") or []) for s in storyboards),
            "coverage_in_sections": len({c["term"] for sec in sections for c in sec["concepts"]}),
            "merged_files": len(storyboards),
        },
        "memory": storyboards[0].get("memory") or {},
        "_todo": todo,
        "_coverage_missing": missing,
        "sections": sections,
        "references": [],
    }
    return src



def to_md(src: dict) -> str:
    lines = [f"# {src['meta'].get('chapter', '')}（讲义骨架）", ""]
    if src.get("_todo"):
        lines.append("> 待补清单：")
        for t in src["_todo"]:
            lines.append(f"> - {t}")
        lines.append("")
    for sec in src["sections"]:
        lines.append(f"## {sec['no']} {sec['title']}".replace("  ", " "))
        lines.append("")
        lines.append(sec["conclusion"] or "_（待写：一句话结论）_")
        lines.append("")
        if sec["concepts"]:
            lines.append("概念：" + "、".join(c["term"] for c in sec["concepts"]))
            lines.append("")
        if sec.get("_material"):
            lines.append("课件原话（只能当素材，不能直接当讲义正文）：")
            for m in sec["_material"]:
                lines.append(f"- {m}")
            lines.append("")
        if sec["pitfalls"]:
            lines.append("易错：" + "；".join(sec["pitfalls"]))
            lines.append("")
        if sec["exercises"]:
            lines.append(f"回问 {len(sec['exercises'])} 题（来自 recall 页）")
            lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="故事板 -> 讲义源骨架")
    ap.add_argument("storyboards", nargs="+", help="一份或多份故事板 json，按给出顺序合并")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--md")
    ap.add_argument("--textbook", default="", help="教材名与版本，写进 meta.textbook（如《人工智能通识教程》）")
    ap.add_argument("--keep-numbers", action="store_true",
                    help="多文件时保留各自原节号（默认按合并顺序重排为 1..N）")
    a = ap.parse_args(argv)

    sbs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in a.storyboards]
    labels = [re.sub(r"^(storyboard|故事板|课件)[_-]?", "", deid.clean_filename(Path(p).stem))
              for p in a.storyboards]
    src = build_many(sbs, textbook=a.textbook, renumber=not a.keep_numbers, labels=labels)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(src, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.md:
        Path(a.md).parent.mkdir(parents=True, exist_ok=True)
        Path(a.md).write_text(to_md(src), encoding="utf-8")
    n = len(a.storyboards)
    head = f"讲义源骨架: {a.out}（{n} 份合并，{len(src['sections'])} 节，待补 {len(src['_todo'])} 项）" \
        if n > 1 else f"讲义源骨架: {a.out}（{len(src['sections'])} 节，待补 {len(src['_todo'])} 项）"
    print(head)
    for t in src["_todo"]:
        print("  -", t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
