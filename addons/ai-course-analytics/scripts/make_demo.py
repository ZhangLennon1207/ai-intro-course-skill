#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成演示作答数据（DEMO），用于在没有真实成绩时跑通学情链路。

    python make_demo.py 题库.json -o assets/demo_answers.csv --students 40 --seed 42

生成的数据**不是真实学情**，只用来验证「判分 → 统计 → 报告 → 图」能不能跑通。
每名学生的潜在能力从正态分布抽样，每题按难度参数决定答对概率，所以统计结果
结构合理：有偏难题、有送分题、有一道区分度接近 0 的题——正好覆盖报告里的判断分支。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path

LETTERS = "ABCDEFGH"

# 演示用的题目参数：难度 b（越大越难）、区分度 a（越大越能拉开差距）
DEMO_PARAMS = {
    "memory": {"b": -0.9, "a": 0.9},     # 记忆题：容易，区分度一般
    "normal": {"b": 0.0, "a": 1.4},
    "hard": {"b": 0.9, "a": 1.5},
    "flat": {"b": -0.6, "a": 0.15},      # 几乎谁都对，区分度极低（报告会点名）
}


def p_correct(theta: float, b: float, a: float) -> float:
    return 1.0 / (1.0 + math.exp(-a * (theta - b)))


def flat(bank: dict) -> list[dict]:
    if isinstance(bank.get("questions"), list):
        return bank["questions"]
    out = []
    for g in bank.get("groups") or []:
        for q in g.get("questions") or []:
            q = dict(q)
            q.setdefault("type", g.get("type"))
            out.append(q)
    return out


def param_for(q: dict, idx: int) -> dict:
    lv = str(q.get("level", ""))
    if lv == "记忆":
        return DEMO_PARAMS["memory"]
    if lv == "分析":
        return DEMO_PARAMS["hard"]
    if idx == 2:
        return DEMO_PARAMS["flat"]
    return DEMO_PARAMS["normal"]


def solve(q: dict, p: float, rng: random.Random) -> str:
    t = q.get("type")
    ans = q.get("answer")
    if t in ("single", "multi"):
        std = "".join(sorted(c for c in str(ans).upper() if c.isalpha()))
        if rng.random() < p:
            return std
        opts = [LETTERS[i] for i in range(len(q.get("options") or []))]
        wrong = [c for c in opts if c not in std]
        if t == "multi":
            return "".join(sorted(rng.sample(opts, 2)))
        return rng.choice(wrong) if wrong else "A"
    if t == "judge":
        if rng.random() < p:
            return str(ans)
        return "×" if str(ans) in ("√", "对", "正确", "是") else "√"
    if t == "blank":
        if rng.random() < p:
            # 答案可能写成「震荡/来回跳动」多个可接受写法，取第一个当学生作答
            first = ans[0] if isinstance(ans, list) else ans
            return str(first).split("/")[0].strip()
        return "不清楚"
    # 主观题：按 p 给分，再加一点噪声，取整到 0.5
    full = float(q.get("score", 0))
    ratio = min(1.0, max(0.0, p + rng.gauss(0, 0.12)))
    return f"{round(full * ratio * 2) / 2:g}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成演示作答数据（DEMO）")
    ap.add_argument("bank")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--students", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args(argv)

    if a.students < 2:
        ap.error("演示至少需要2名虚构学生")
    bank = json.loads(Path(a.bank).read_text(encoding="utf-8"))
    qs = flat(bank)
    rng = random.Random(a.seed)

    rows = []
    for i in range(a.students):
        theta = rng.gauss(0, 1)
        row = {"dataset_kind": "DEMO", "student_id": f"DEMO-{i + 1:03d}", "class": "1" if i < a.students // 2 else "2"}
        for idx, q in enumerate(qs):
            prm = param_for(q, idx)
            p = p_correct(theta, prm["b"], prm["a"])
            row[str(q["id"])] = solve(q, p, rng)
        rows.append(row)

    # 制造两个真实会遇到的数据问题：一人缺考、一人主观题未评
    rows[-1]["student_id"] = rows[-1]["student_id"] + "_缺考"
    for q in qs:
        rows[-1][str(q["id"])] = "缺考"
    if qs and str(qs[-1].get("type")) in ("short", "comp"):
        rows[-2][str(qs[-1]["id"])] = "答案还没批"

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"演示数据: {out}（{len(rows)} 行，DEMO，不是真实学情）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
