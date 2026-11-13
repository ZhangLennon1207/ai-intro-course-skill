#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""知识点清单 -> 双向细目表（命题蓝图）。出题前必须有这张表。

用法：
    python make_blueprint.py --coverage out/storyboard_单元3_C模式_改造后.json \\
        -o out/蓝图表_单元3.json --md out/蓝图表_单元3.md --profile 期末
    python make_blueprint.py --points 知识点.txt --total 40 --profile 随堂

先定表再出题。没有这张表，出题只能凭印象，最后查「这个知识点考没考」查不出来。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kp  # noqa: E402  同目录知识点编码模块

# 题型：单题分值、是否客观题、默认答题时长（分钟）
TYPES = {
    "single": {"name": "单项选择题", "score": 2, "objective": True, "minutes": 1.2},
    "multi": {"name": "多项选择题", "score": 3, "objective": True, "minutes": 1.5},
    "judge": {"name": "判断题", "score": 2, "objective": True, "minutes": 0.6},
    "blank": {"name": "填空题", "score": 2, "objective": True, "minutes": 1.0},
    "short": {"name": "简答题", "score": 8, "objective": False, "minutes": 6.0},
    "comp": {"name": "综合分析题", "score": 15, "objective": False, "minutes": 12.0},
}
LEVELS = ("记忆", "理解", "应用", "分析")

# 三种场景的预设配比：题型占分 / 层次占分
PROFILES = {
    "期末": {
        "types": {"single": 30, "judge": 10, "blank": 15, "short": 25, "comp": 20},
        "levels": {"记忆": 20, "理解": 35, "应用": 30, "分析": 15},
        "open_book": True, "minutes": 120,
    },
    "小测": {
        "types": {"single": 40, "judge": 20, "blank": 20, "short": 20},
        "levels": {"记忆": 30, "理解": 40, "应用": 25, "分析": 5},
        "open_book": False, "minutes": 30,
    },
    "随堂": {
        "types": {"single": 50, "judge": 20, "blank": 30},
        "levels": {"记忆": 35, "理解": 45, "应用": 20, "分析": 0},
        "open_book": False, "minutes": 10,
    },
}


def load_points(path: str) -> list[str]:
    """coverage 可以是故事板 json（取 coverage 字段），也可以是纯文本一行一条。"""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"找不到知识点清单：{p}")
    txt = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        data = json.loads(txt)
        pts = data.get("coverage") if isinstance(data, dict) else None
        if not pts:
            raise SystemExit("这个 json 里没有 coverage 字段；故事板才有，别的文件请用 --points")
        return [str(x).strip() for x in pts if str(x).strip()]
    out = []
    for line in txt.splitlines():
        s = re.sub(r"^\s*(?:[-*+]|\d+[.、)])\s*", "", line).strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def allocate(types_quota: dict, total: int) -> dict:
    """按占分比例算每种题型几道题。只负责题数，余数留给 build() 调最后一道大题的分值。"""
    plan: dict[str, int] = {}
    for t, ratio in types_quota.items():
        unit = TYPES[t]["score"]
        plan[t] = max(1, round(total * ratio / 100 / unit))

    def subtotal(p):
        return sum(TYPES[t]["score"] * n for t, n in p.items())

    # 用单题分值最小的题型逐题微调，逼近总分；余数（小于最小分值）交出去
    small_first = sorted(plan, key=lambda t: (TYPES[t]["score"], t))
    guard = 0
    while subtotal(plan) != total and guard < 500:
        diff = total - subtotal(plan)
        moved = False
        for t in small_first:
            unit = TYPES[t]["score"]
            if diff > 0 and unit <= diff:
                plan[t] += 1
                moved = True
                break
            if diff < 0 and unit <= -diff and plan[t] > 1:
                plan[t] -= 1
                moved = True
                break
        if not moved:
            break      # 剩余差额小于最小单题分值，交给最后一道题吸收
        guard += 1
    return plan


def assign_levels(rows: list[dict], levels_quota: dict, total: int) -> dict:
    """按「分值」而非「题数」分配层次。

    按题数分会让简答题（8 分）和选择题（2 分）等权，最后分值比例偏离目标十几个点。
    做法：每题挂到当前完成度（已分/目标）最低的层次上。
    """
    target = {lv: total * r / 100 for lv, r in levels_quota.items() if r > 0}
    if not target:
        for r in rows:
            r["level"] = "理解"
        return {"理解": sum(r["score"] for r in rows)}
    got = {lv: 0 for lv in target}
    # 先分大题再分小题：16 分的综合题放最后补 1 分的差额，永远补不平
    for r in sorted(rows, key=lambda r: -r["score"]):
        # 主观题不挂「记忆」：8 分简答只考背定义，等于送分还占分
        candidates = {k: v for k, v in target.items()
                      if not (k == "记忆" and not r["objective"])} or target
        lv = min(candidates, key=lambda k: (got[k] / candidates[k] if candidates[k] else 9e9))
        r["level"] = lv
        got[lv] += r["score"]
    return got


def build(points: list[str], total: int = 100, profile: str = "小测",
          types_quota: dict | None = None, table=None) -> dict:
    if not points or not isinstance(total, int) or total < 1:
        raise ValueError("需要真实知识点清单和正整数总分")
    if profile not in PROFILES:
        raise SystemExit(f"场景只有 {list(PROFILES)}；要自定义配比用 --types 参数")
    cfg = PROFILES[profile]
    tq = types_quota or cfg["types"]
    if abs(sum(tq.values()) - 100) > 0.01:
        raise SystemExit(f"题型占分合计 {sum(tq.values())}，必须等于 100")

    plan = allocate(tq, total)
    rows = []
    # 知识点按原顺序连续切分，不取模轮转——取模会把「深度学习定义」和「训练循环」硬凑成一题
    n_items = sum(plan.values())
    base, extra = divmod(len(points or [1]), n_items)
    groups: list[list[str]] = []
    cursor = 0
    src_points = points or ["（未提供知识点）"]
    for i in range(n_items):
        take = base + (1 if i < extra else 0)
        got_points = src_points[cursor:cursor + take]
        cursor += take
        if not got_points:      # 题比知识点多时，多出来的题挂在同一节的知识点上
            got_points = [src_points[i % len(src_points)]]
        groups.append(got_points)

    idx = 0
    for t, n in plan.items():
        for k in range(n):
            rows.append({
                "no": idx + 1,
                "type": t,
                "level": "",
                "points": groups[idx],
                "score": TYPES[t]["score"],
                "unit": TYPES[t]["name"],
                "objective": TYPES[t]["objective"],
            })
            idx += 1

    assign_levels(rows, cfg["levels"], total)

    # 知识点编号：细目表的题号与知识点要能对到同一套编码上，否则考后学情对不上
    table = table or {}
    unmapped: list[str] = []
    for r in rows:
        ids = []
        for name in r["points"]:
            kid = kp.resolve(name, table)
            if not kid and table:
                unmapped.append(name)
            ids.append(kid or "")
        r["kp_ids"] = ids
    unmapped = sorted(set(unmapped))

    # 尾差吸收到最后一题（大题分值可调，这是真实出卷做法；不硬凑题数）
    tail_note = ""
    actual = sum(r["score"] for r in rows)
    if rows and actual != total:
        rows[-1]["score"] += total - actual
        rows[-1]["adjusted"] = True
        tail_note = f"最后一道题分值由 {TYPES[rows[-1]['type']]['score']} 调为 {rows[-1]['score']}，用于凑齐 {total} 分"
    if any(row["score"] <= 0 for row in rows):
        raise ValueError("该总分过小，无法容纳所选题型；请减少题型或提高总分")

    by_type = {}
    for r in rows:
        by_type.setdefault(r["type"], {"name": r["unit"], "count": 0, "score": 0})
        by_type[r["type"]]["count"] += 1
        by_type[r["type"]]["score"] += r["score"]
    by_level = {}
    for r in rows:
        by_level[r["level"]] = by_level.get(r["level"], 0) + r["score"]
    by_level = {lv: by_level[lv] for lv in LEVELS if lv in by_level}

    est = sum(TYPES[r["type"]]["minutes"] for r in rows)
    warns = []
    if unmapped:
        warns.append("以下知识点不在编码表里：" + "、".join(unmapped)
                     + "（考后这些点的掌握度会单独成行，不会并进编号）")
    if tail_note:
        warns.append(tail_note)
    if abs(est - cfg["minutes"]) > cfg["minutes"] * 0.25:
        warns.append(f"按题量估算作答 {est:.0f} 分钟，与预设 {cfg['minutes']} 分钟差得多，题量或分值要调")
    if len(points) and n_items < len(points):
        warns.append(f"知识点 {len(points)} 条多于题目 {n_items} 道，已合并挂载；覆盖会打折")

    return {
        "meta": {
            "profile": profile,
            "status": "建议分配，非课程正式考核政策",
            "total": total,
            "minutes": cfg["minutes"],
            "estimated_minutes": round(est, 1),
            "open_book": cfg["open_book"],
            "points_count": len(points),
            "items_count": n_items,
            "level_quota": cfg["levels"],
            "type_quota": tq,
        },
        "by_type": by_type,
        "by_level": by_level,
        "rows": rows,
        "warnings": warns,
        "note": "计划层次不是实测难度；考后要用作答数据算难度与区分度，别把计划当结论。",
    }


def to_md(bp: dict) -> str:
    m = bp["meta"]
    lines = [f"# 双向细目表（{m['profile']}）", ""]
    lines.append(f"满分 {m['total']} 分｜预设时长 {m['minutes']} 分钟｜估算作答 {m['estimated_minutes']} 分钟｜"
                 f"{'开卷' if m['open_book'] else '闭卷'}｜知识点 {m['points_count']} 条｜题目 {m['items_count']} 道")
    lines.append("")
    lines.append("## 题型分布")
    lines.append("")
    lines.append("| 题型 | 题数 | 分值 | 占比 |")
    lines.append("|---|---|---|---|")
    for t, v in bp["by_type"].items():
        lines.append(f"| {v['name']} | {v['count']} | {v['score']} | {v['score'] / m['total'] * 100:.0f}% |")
    lines.append("")
    lines.append("## 层次分布（计划）")
    lines.append("")
    lines.append("| 层次 | 分值 | 占比 | 目标 | 偏差 |")
    lines.append("|---|---|---|---|---|")
    for lv, sc in bp["by_level"].items():
        tgt = m["level_quota"].get(lv, 0)
        lines.append(f"| {lv} | {sc} | {sc / m['total'] * 100:.0f}% | {tgt}% | {sc / m['total'] * 100 - tgt:+.0f}pp |")
    lines.append("")
    lines.append("## 逐题分配")
    lines.append("")
    lines.append("| 题号 | 题型 | 层次 | 考查知识点（编号） | 分值 |")
    lines.append("|---|---|---|---|---|")
    table = kp.load()
    for r in bp["rows"]:
        names = []
        for i, name in enumerate(r["points"]):
            kid = (r.get("kp_ids") or [""] * len(r["points"]))[i]
            names.append(kp.label(kid, table, name) if kid else name)
        lines.append(f"| {r['no']} | {r['unit']} | {r['level']} | {'、'.join(names)} | {r['score']} |")
    lines.append("")
    if bp["warnings"]:
        lines.append("## 待确认")
        for w in bp["warnings"]:
            lines.append(f"- {w}")
        lines.append("")
    lines.append(f"> {bp['note']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成双向细目表")
    ap.add_argument("--coverage", help="故事板 json（取 coverage）")
    ap.add_argument("--points", help="知识点纯文本，一行一条")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--md")
    ap.add_argument("--total", type=int, default=100)
    ap.add_argument("--profile", default="小测", choices=list(PROFILES))
    ap.add_argument("--kp", help="显式项目知识点映射CSV")
    a = ap.parse_args(argv)

    if not (a.coverage or a.points):
        raise SystemExit("给 --coverage 或 --points 之一")
    pts = load_points(a.coverage or a.points)
    bp = build(pts, total=a.total, profile=a.profile, table=kp.load(a.kp))

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(bp, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.md:
        Path(a.md).write_text(to_md(bp), encoding="utf-8")
    print(f"细目表: {a.out}（{bp['meta']['items_count']} 题 / {a.total} 分）")
    for w in bp["warnings"]:
        print("  [待确认]", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
