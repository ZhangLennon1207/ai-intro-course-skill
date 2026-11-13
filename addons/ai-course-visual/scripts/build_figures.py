#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""配图计划 json -> PNG + SVG（流程图、闭环、层级图、对比矩阵、知识卡）。

    python build_figures.py 配图计划_单元3.json -o out/figs --check
    python build_figures.py 配图计划.json -o out/figs --only fig_neuron,fig_loop

出图之前先查：标题/图注/来源是否齐、元素是否超长、语义色是否超过三种。
图上的每个字都是最终内容，不留「此处放图」。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deid  # noqa: E402  同目录脱敏模块

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

# 三个语义色：主（主体/正确）、对比（另一方案）、警示（易错/风险）
C_MAIN = "#1F4E79"
C_COMPARE = "#2E8B8B"
C_WARN = "#B03A2E"
C_TEXT = "#1A1A1A"
C_LINE = "#5A5A5A"
ROLES = {"main": C_MAIN, "compare": C_COMPARE, "warn": C_WARN}
TYPES = ("flow", "loop", "tree", "compare", "card", "timeline")


def setup_font() -> bool:
    plt.rcParams["svg.fonttype"] = "none"
    for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "PingFang SC"):
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            return True
    return False


def width(s: str) -> float:
    """按全角 1、半角 0.55 估算显示宽度（单位：字）。"""
    w = 0.0
    for ch in str(s):
        w += 1.0 if ord(ch) > 127 else 0.55
    return w


# ---------- 自检 ----------
def check(plan: dict) -> list[tuple[str, str, str]]:
    issues: list[tuple[str, str, str]] = []
    figs = plan.get("figures") or []
    if not figs:
        return [("error", "配图计划", "一张图都没有")]
    seen = set()
    for i, f in enumerate(figs, 1):
        fid = str(f.get("id") or f"fig{i}")
        loc = f"{fid}"
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", fid):
            issues.append(("error", loc, "id必须为安全文件名：字母、数字、下划线或短横线"))
        if fid in seen:
            issues.append(("error", loc, "id 重复，后一张会覆盖前一张"))
        seen.add(fid)
        t = f.get("type")
        if t not in TYPES:
            issues.append(("error", loc, f"类型「{t}」不认识，只能是 {TYPES}"))
            continue
        for k in ("title", "caption", "source"):
            if not str(f.get(k, "")).strip():
                issues.append(("error", loc, f"缺 {k}"))
        if re.search(r"此处放图|待补|TODO|xxx", str(f.get("caption", ""))):
            issues.append(("error", loc, "图注还是占位文字"))
        roles = set()
        if t in ("flow", "loop"):
            els = f.get("elements") or []
            if not 2 <= len(els) <= 6:
                issues.append(("error", loc, f"{t} 需要 2–6 个节点，现在 {len(els)} 个"))
            for e in els:
                if width(e.get("label", "")) > 12:
                    issues.append(("error", loc, f"节点「{e.get('label')}」超过 12 字宽，盒子装不下"))
                if not str(e.get("label", "")).strip():
                    issues.append(("error", loc, "有节点没写标签"))
                roles.add(e.get("role", "main"))
        elif t == "tree":
            root = f.get("root") or {}
            branches = f.get("branches") or []
            if not str(root.get("label", "")).strip():
                issues.append(("error", loc, "树没有根节点"))
            if not 2 <= len(branches) <= 6:
                issues.append(("error", loc, f"分支 {len(branches)} 条，应为 2–6"))
            br = [b for b in branches if width(b.get("label", "")) > 10]
            if br:
                issues.append(("error", loc, f"分支「{br[0].get('label')}」超过 10 字宽"))
            roles.add("main")
        elif t == "compare":
            cols = f.get("cols") or []
            rows = f.get("rows") or []
            if not 2 <= len(cols) <= 4:
                issues.append(("error", loc, f"对比矩阵 {len(cols)} 列，应为 2–4 列（含维度列）"))
            if not 2 <= len(rows) <= 6:
                issues.append(("error", loc, f"对比矩阵 {len(rows)} 行，应为 2–6 行"))
            for r in rows:
                if len(r) != len(cols):
                    issues.append(("error", loc, f"有一行 {len(r)} 格，列头 {len(cols)} 个，对不齐"))
            roles.update({"main", "compare"})
        elif t == "timeline":
            steps = f.get("steps") or []
            if not 2 <= len(steps) <= 7:
                issues.append(("error", loc, f"时间轴 {len(steps)} 段，应为 2–7 段（再多就挤成一条字幕）"))
            for st in steps:
                if not str(st.get("label", "")).strip():
                    issues.append(("error", loc, "有阶段没写标签"))
                elif width(st.get("label", "")) > 12:
                    issues.append(("error", loc, f"阶段「{st.get('label')}」超过 12 字宽"))
                if st.get("note") and width(st["note"]) > 18:
                    issues.append(("error", loc, f"阶段说明「{st['note']}」超过 18 字宽，会压到相邻阶段"))
            roles.add("main")
        else:  # card
            for k in ("term", "def"):
                if not str(f.get(k, "")).strip():
                    issues.append(("error", loc, f"知识卡缺 {k}"))
            if width(f.get("term", "")) > 10:
                issues.append(("error", loc, "卡片正面概念名超过 10 字宽"))
            roles.add("main")
        bad = roles - set(ROLES)
        if bad:
            issues.append(("error", loc, f"role 只能是 {list(ROLES)}，出现了 {bad}"))
        if len(roles) > 3:
            issues.append(("error", loc, "语义色超过 3 种，颜色失去含义"))
        for kind, val in deid.scan(str(f.get("source", "")) + str(f.get("caption", ""))
                                   + str(f.get("title", ""))):
            issues.append(("error", loc, f"发现{kind}（命中值不回显），请检查分发范围"))
        cap = str(f.get("caption", ""))
        if re.search(r"\d", cap) and not re.search(r"示意|实测|教材|课件", cap):
            issues.append(("warn", loc, "图注里有数字但没标「示意」或出处，读者会当成实测值"))
    return issues


def format_issues(issues) -> str:
    if not issues:
        return "配图计划自检通过：图注/来源齐、元素长度合规、语义色 ≤3。"
    lines = [f"{'[错误]' if lv == 'error' else '[提醒]'} {loc}：{msg}" for lv, loc, msg in issues]
    err = sum(1 for x in issues if x[0] == "error")
    lines.append(f"\n合计 {len(issues)} 条：错误 {err}，提醒 {len(issues) - err}")
    return "\n".join(lines)


# ---------- 画图 ----------
def _canvas(w=9.0, h=5.0):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    return fig, ax


def _box(ax, x, y, w, h, text, sub="", color=C_MAIN, fs=11, subfs=8.5, fc="white", lw=1.6):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.6,rounding_size=1.4",
                       linewidth=lw, edgecolor=color, facecolor=fc, zorder=2)
    ax.add_patch(p)
    if sub:
        ax.text(x + w / 2, y + h * 0.63, text, ha="center", va="center",
                fontsize=fs, color=C_TEXT, zorder=3, fontweight="bold")
        ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center",
                fontsize=subfs, color="#4D4D4D", zorder=3)
    else:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=fs, color=C_TEXT, zorder=3, fontweight="bold")


def _arrow(ax, p1, p2, color=C_LINE, curve=0.0, lw=1.8, style="-|>", ls="-"):
    a = FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=13, linewidth=lw,
                        color=color, connectionstyle=f"arc3,rad={curve}",
                        shrinkA=2, shrinkB=2, linestyle=ls, zorder=1)
    ax.add_patch(a)


def _edge_point(c1, c2, bw, bh):
    """从 c1 中心指向 c2 的射线与 c1 矩形边界的交点（让箭头停在框外，不扎进框里）。"""
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    sx = (bw / 2) / abs(dx) if dx else float("inf")
    sy = (bh / 2) / abs(dy) if dy else float("inf")
    s = min(sx, sy)
    return (c1[0] + dx * s, c1[1] + dy * s)


def draw_flow(ax, f):
    els = f["elements"]
    n = len(els)
    top, bottom = 82, 16
    bh = min(12.0, (top - bottom) / n * 0.62)
    gap = (top - bottom - n * bh) / (n - 1) if n > 1 else 0
    bw, x = 54, 23
    for i, e in enumerate(els):
        y = top - bh - i * (bh + gap)
        _box(ax, x, y, bw, bh, e["label"], e.get("sub", ""), ROLES[e.get("role", "main")])
        if i:
            y_prev = top - bh - (i - 1) * (bh + gap)
            _arrow(ax, (x + bw / 2, y_prev), (x + bw / 2, y + bh))


def draw_loop(ax, f):
    els = f["elements"]
    n = len(els)
    import math
    bw, bh = 28, 12
    cx, cy, r = 50, 50, 26
    centers, boxes = [], []
    for i in range(n):
        ang = math.pi / 2 - 2 * math.pi * i / n
        px = cx + r * math.cos(ang) - bw / 2
        py = cy + r * math.sin(ang) - bh / 2
        centers.append((px + bw / 2, py + bh / 2))
        boxes.append((px, py))
        _box(ax, px, py, bw, bh, els[i]["label"], els[i].get("sub", ""),
             ROLES[els[i].get("role", "main")], fs=10)
    for i in range(n):
        j = (i + 1) % n
        p1 = _edge_point(centers[i], centers[j], bw, bh)
        p2 = _edge_point(centers[j], centers[i], bw, bh)
        _arrow(ax, p1, p2, curve=0.22)
    if f.get("center"):
        ax.text(cx, cy, f["center"], ha="center", va="center",
                fontsize=9.5, color="#4D4D4D", style="italic")


def draw_tree(ax, f):
    root = f["root"]
    branches = f["branches"]
    n = len(branches)
    _box(ax, 34, 71, 32, 11, root["label"], root.get("sub", ""), C_MAIN, fs=10.5)
    bw = min(20, 92 / n - 2)
    step = 92 / n
    for i, b in enumerate(branches):
        x = 4 + i * step + (step - bw) / 2
        _box(ax, x, 42, bw, 13, b["label"], b.get("sub", ""), C_COMPARE, fs=9.5)
        _arrow(ax, (50, 71), (x + bw / 2, 55.2))
        kids = (b.get("children") or [])[:4]
        if kids:
            ky0 = 34
            kstep = min(6.0, 20 / max(1, len(kids)))
            ax.plot([x + bw / 2, x + bw / 2], [42, ky0 - (len(kids) - 1) * kstep + 1.5],
                    color="#B0B0B0", lw=1, zorder=1)
            for j, k in enumerate(kids):
                ax.text(x + bw / 2, ky0 - j * kstep, f"· {k}", ha="center", va="center",
                        fontsize=8.5, color="#333333")


def draw_compare(ax, f):
    cols, rows = f["cols"], f["rows"]
    nc, nr = len(cols), len(rows)
    left, right = 4, 96
    cw = (right - left) / nc
    hh = 9.0
    rh = min(10.0, 52 / nr)
    top = 79
    for j, c in enumerate(cols):
        x = left + j * cw
        ax.add_patch(plt.Rectangle((x, top - hh), cw, hh, facecolor=C_MAIN if j == 0 else "#DCE6F1",
                                   edgecolor="white", lw=1.2))
        ax.text(x + cw / 2, top - hh / 2, c, ha="center", va="center",
                fontsize=9.5, color="white" if j == 0 else C_TEXT, fontweight="bold")
    for i, r in enumerate(rows):
        y = top - hh - (i + 1) * rh
        for j, cell in enumerate(r):
            x = left + j * cw
            ax.add_patch(plt.Rectangle((x, y), cw, rh, facecolor="white" if i % 2 == 0 else "#F4F6F8",
                                       edgecolor="#D9D9D9", lw=0.8))
            ax.text(x + cw / 2, y + rh / 2, str(cell), ha="center", va="center",
                    fontsize=9, color=C_TEXT)


def draw_card(ax, f):
    _box(ax, 12, 24, 76, 52, "", "", C_MAIN, lw=2.0, fc="#FBFCFE")
    ax.text(50, 65, f["term"], ha="center", va="center", fontsize=19,
            color=C_MAIN, fontweight="bold")
    ax.plot([22, 78], [58, 58], color=C_MAIN, lw=1.0, alpha=0.45)
    ax.text(50, 49, f["def"], ha="center", va="center", fontsize=10, color=C_TEXT)
    if f.get("not"):
        nots = re.sub(r"^(它)?不是[：:]?\s*", "", str(f["not"]))
        ax.text(50, 37, f"不是：{nots}", ha="center", va="center", fontsize=9.2, color=C_WARN)
    if f.get("tip"):
        ax.text(50, 29, f"记法：{f['tip']}", ha="center", va="center", fontsize=8.8, color="#4D4D4D")


def draw_timeline(ax, f):
    """横向时间轴：阶段等距排开，标签上下交错，避免相邻文字相撞。"""
    steps = f.get("steps") or []
    n = len(steps)
    x0, x1, y = 12.0, 88.0, 50.0
    ax.annotate("", xy=(x1 + 4, y), xytext=(x0 - 4, y),
                arrowprops=dict(arrowstyle="-|>", color=C_LINE, lw=2.0, shrinkA=0, shrinkB=0))
    xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)] if n > 1 else [(x0 + x1) / 2]
    for i, (x, st) in enumerate(zip(xs, steps)):
        up = i % 2 == 0
        ax.plot([x], [y], marker="o", ms=11, mfc="white", mec=C_MAIN, mew=2.2, zorder=5)
        ax.plot([x, x], [y + 3 if up else y - 3, y + 6 if up else y - 6], color=C_MAIN, lw=1.0)
        ax.text(x, y + (7.5 if up else -7.5), st.get("label", ""), ha="center",
                va="bottom" if up else "top", fontsize=10.5, color=C_TEXT,
                fontweight="bold", wrap=True)
        if st.get("note"):
            ax.text(x, y + (17 if up else -17), st["note"], ha="center",
                    va="bottom" if up else "top", fontsize=8.6, color="#595959", wrap=True)


DRAW = {"flow": draw_flow, "loop": draw_loop, "tree": draw_tree,
        "compare": draw_compare, "card": draw_card, "timeline": draw_timeline}


def render(f: dict, out_dir: Path) -> tuple[Path, Path]:
    h = 4.2 if f["type"] == "compare" else (3.8 if f["type"] == "timeline" else 4.6)
    fig, ax = _canvas(9.0, h)
    ax.text(50, 96, f["title"], ha="center", va="center", fontsize=14,
            color=C_TEXT, fontweight="bold")
    DRAW[f["type"]](ax, f)
    # 来源里常带课件文件名，姓名后缀在这里去掉（图上的字没人会再去改）
    foot = f"{f['caption']}　｜　来源：{deid.clean_filename(str(f['source']))}"
    ax.text(50, 3, foot, ha="center", va="center", fontsize=8, color="#666666", wrap=True)
    fig.tight_layout()
    png = out_dir / f"{f['id']}.png"
    svg = out_dir / f"{f['id']}.svg"
    fig.savefig(png, dpi=200)
    fig.savefig(svg, format="svg")
    plt.close(fig)
    return png, svg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="配图计划 -> PNG/SVG")
    ap.add_argument("plan")
    ap.add_argument("-o", "--out", default="figs")
    ap.add_argument("--check", action="store_true", help="只自检，不出图")
    ap.add_argument("--only", help="只画这几张，逗号分隔 id")
    ap.add_argument("--strict", action="store_true", help="有错误退出码 1")
    a = ap.parse_args(argv)

    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    issues = check(plan)
    print(format_issues(issues))

    if a.check:
        return 1 if (a.strict and any(i[0] == "error" for i in issues)) else 0

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if not setup_font():
        print("[提醒] 没找到中文字体，图上中文可能显示为方框")
    only = set(x.strip() for x in a.only.split(",")) if a.only else None
    made = []
    for f in plan["figures"]:
        if only and f["id"] not in only:
            continue
        if any(lv == "error" and loc == f["id"] for lv, loc, _ in issues):
            print(f"[跳过] {f['id']}：计划有错误，先改计划再出图")
            continue
        png, svg = render(f, out)
        made.append((png, svg))
        print(f"图: {png.name} / {svg.name}")
    print(f"共 {len(made)} 张，输出目录 {out}")
    return 1 if (a.strict and any(i[0] == "error" for i in issues)) else 0


if __name__ == "__main__":
    sys.exit(main())
