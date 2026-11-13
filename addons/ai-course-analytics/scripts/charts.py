#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""学情统计json -> 可用的逐题得分率、D与知识点得分表现图（最多3张）。

    python charts.py out/学情_单元3_统计.json -o out/charts

图只画报告里已经有的数。样本不足（<30）时不画区分度散点，
不给一张看起来很有信息量、其实每条都不可靠的图。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

C_MAIN = "#1F4E79"
C_ACCENT = "#C0504D"
C_GRAY = "#8C8C8C"


def setup_font() -> bool:
    """找一个能显示中文的字体；找不到就返回 False，由调用方决定是否继续。"""
    for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "PingFang SC", "Source Han Sans SC"):
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            return True
    return False


def fig_distribution(stats: dict, out: Path, full: float) -> Path:
    # 用均值与标准差重建近似分布没有意义，改画「每题得分率」的横向条形，信息更实
    items = [i for i in stats["items"] if i["difficulty"] is not None]
    labels = [f"{i['id']}" for i in items]
    vals = [i["difficulty"] for i in items]
    colors = [C_ACCENT if v < 0.3 else (C_GRAY if v > 0.9 else C_MAIN) for v in vals]
    fig, ax = plt.subplots(figsize=(7.2, max(2.6, 0.42 * len(items) + 1.2)))
    ax.barh(labels, vals, color=colors)
    ax.axvline(0.6, color=C_GRAY, lw=1, ls="--")
    ax.text(0.605, len(items) - 0.4, "0.6 参考线", color=C_GRAY, fontsize=8, va="top")
    ax.set_xlim(0, 1)
    ax.set_xlabel("得分率（越高越容易）")
    ax.set_title(f"各题得分率（n={stats['sample']}，满分 {full:g} 分）", color=C_MAIN)
    ax.invert_yaxis()
    for y, v in enumerate(vals):
        ax.text(min(v + 0.01, 0.97), y, f"{v:.2f}", va="center", fontsize=8, color="#333333")
    fig.tight_layout()
    p = out / "图1_各题得分率.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    return p


def fig_discrimination(stats: dict, out: Path) -> Path | None:
    items = [i for i in stats["items"] if i["difficulty"] is not None and i["discrimination"] is not None]
    if not items:
        return None
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    xs = [i["difficulty"] for i in items]
    ys = [i["discrimination"] for i in items]
    ax.scatter(xs, ys, s=46, color=C_MAIN, zorder=3)
    placed: list[tuple[float, float]] = []
    for k, (i, x, y) in enumerate(zip(items, xs, ys)):
        dy = 9.0 if k % 2 == 0 else -14.0    # 上下交替，密集区域才不会叠成一片
        for px, py in placed:
            if abs(x - px) < 0.05 and abs(y - py) < 0.09:
                dy = -14.0 if dy > 0 else 9.0
        ax.annotate(i["id"], (x, y), textcoords="offset points", xytext=(4, dy),
                    fontsize=8, color="#333333")
        placed.append((x, y))
    ax.axhline(0.2, color=C_GRAY, lw=1, ls="--")
    ax.axhline(0, color=C_ACCENT, lw=1, ls="-")
    ax.axvline(0.3, color=C_GRAY, lw=1, ls=":")
    ax.axvline(0.9, color=C_GRAY, lw=1, ls=":")
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(min(-0.3, min(ys) - 0.1), max(0.9, max(ys) + 0.15))
    ax.set_xlabel("得分率（难度）")
    ax.set_ylabel("区分度（高分组 - 低分组）")
    ax.set_title("题目统计：得分率与高低分组差异（仅作线索）", color=C_MAIN, fontsize=10)
    fig.tight_layout()
    p = out / "图2_难度区分度.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    return p


def fig_mastery(stats: dict, out: Path) -> Path | None:
    ks = [k for k in stats["knowledge"] if k["mastery"] is not None]
    if not ks:
        return None
    ks = ks[:12]
    labels = [k["point"][:14] for k in ks][::-1]
    vals = [k["mastery"] for k in ks][::-1]
    colors = [C_ACCENT if v < 0.6 else C_MAIN for v in vals]
    fig, ax = plt.subplots(figsize=(7.2, max(2.4, 0.40 * len(ks) + 1.0)))
    ax.barh(labels, vals, color=colors)
    ax.axvline(0.6, color=C_GRAY, lw=1, ls="--")
    ax.set_xlim(0, 1)
    ax.set_xlabel("掌握度（按分值加权）")
    ax.set_title("知识点得分表现（红＝低于60%参考线）", color=C_MAIN)
    for y, v in enumerate(vals):
        ax.text(min(v + 0.01, 0.95), y, f"{v * 100:.0f}%", va="center", fontsize=8, color="#333333")
    fig.tight_layout()
    p = out / "图3_知识点掌握度.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="学情统计 -> 图")
    ap.add_argument("stats")
    ap.add_argument("-o", "--out", default="charts")
    a = ap.parse_args(argv)

    stats = json.loads(Path(a.stats).read_text(encoding="utf-8"))
    if not any(item.get("difficulty") is not None for item in stats.get("items", [])):
        print("[跳过] 没有可画的逐题得分率；不从总分均值伪造分布或掌握度图。")
        return 0
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if not setup_font():
        print("[提醒] 本机没找到中文字体，图上的中文可能显示为方框；不影响数据。")

    made = [fig_distribution(stats, out, stats.get("full_score", 0))]
    for f in (fig_discrimination(stats, out), fig_mastery(stats, out)):
        if f:
            made.append(f)
        else:
            print("[跳过] 样本不足或无知识点标注，未生成该图")
    for p in made:
        print(f"图: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
