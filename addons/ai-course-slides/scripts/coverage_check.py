#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""知识点覆盖度机检：把「这单元到底讲全了没有」从人工核对变成可重跑的报告。

为什么要单独一个脚本
--------------------
页数达标 ≠ 内容覆盖。最典型的翻车是「一个知识点一页」写成了「一个页型一页」——
9 种页型各来一遍只有十几页，看着排版齐全，知识点漏掉一半，等到教师翻课件才发现。

故事板里的 `coverage` 数组是人类写的知识点清单，但**默认没有跟 slides 建立任何联系**，
所以它只能当说明书，不能当校验。本脚本做三件事：

  1. 给每个知识点找出承载它的页码（先认显式声明，再退回字符级匹配）
  2. 分三档报：命中 / 疑似（措辞不同，要人确认）/ 漏讲（没有页讲）
  3. 附带抓两类结构问题：一页塞太多知识点、知识点出场页序回跳

用法
----
    python coverage_check.py storyboard.json
    python coverage_check.py storyboard.json --md out/覆盖矩阵.md
    python coverage_check.py storyboard.json --pptx out.pptx     # 顺带核对页数
    python coverage_check.py storyboard.json --strict            # 有漏讲就退出码 1

故事板怎么写才认得准
--------------------
    "coverage": ["机器学习三范式", "训练闭环四零件", "线性回归与梯度下降"]
                       ↓ 两种声明方式，二选一
    {"type": "bullets", "covers": ["机器学习三范式"], ...}    # 按名字（推荐）
    {"type": "bullets", "covers": [1, 2], ...}                # 或按 1 起的序号

**不写 covers 也能跑**，脚本会拿知识点去比每一页的标题和正文。比得上标「用语匹配」，
比不上才报漏讲——所以写 covers 是为了减少人工确认，不是为了过关。

匹配为什么用字符权重而不是子串
------------------------------
知识点名是人写的抽象名（"机器学习三范式"），页面写的是自然语句（"三类范式"）。
整串子串匹配会把这种正常情况误报成漏讲（实测 23 个点里有 6 个假警报，工具就没人看了）。
改用字符级加权重合度：在全部页面里出现得越少的字权重越高，于是「范式」这种词承担区分度，
「学习」「训练」这类满篇都是的字自动降权到接近 0。
"""
import argparse
import json
import math
import os
import re
import sys

# 短语切分：这些连接词两边的概念通常各自独立成点
SPLIT_RE = re.compile(r"[与和及、，,/／·]+")
# 满篇都是、无法区分的字，直接不计权重（不是"忽略"，是"不提供区分信息"）
STOP_CHARS = set("的了是在和与及等对为把被让使从到其此该本种个一不有上下")

HIT, MAYBE, MISS = 0.55, 0.34, 0.0     # 三档阈值，凭实际故事板标定过


# ---------------------------------------------------------------- 文本抽取

def slide_text(spec):
    """把一页里所有学生能看到的字拼起来。标题重复一次以提高权重。"""
    buf = []
    title = str(spec.get("title") or "")
    buf.append(title)
    buf.append(title)                      # 标题写了就大概率是这一页的主题
    for key in ("kicker", "section", "subtitle", "takeaway", "caption", "text"):
        buf.append(str(spec.get(key) or ""))
    tb = spec.get("table") or {}
    buf.append(" ".join(str(h) for h in tb.get("header") or []))
    for row in tb.get("rows") or []:
        buf.append(" ".join(str(c) for c in row))
    for key in ("points", "items"):
        buf += [str(p) for p in spec.get(key) or []]
    for side in ("left", "right"):
        col = spec.get(side) or {}
        buf.append(str(col.get("head") or ""))
        buf += [str(p) for p in col.get("items") or []]
    buf += [str(c.get("text") or "") for c in spec.get("cards") or []]
    return "\n".join(buf)


def norm(s):
    return re.sub(r"\s", "", str(s))


# ---------------------------------------------------------------- 匹配打分

def segments(phrase):
    """把「线性回归与梯度下降」拆成 ['线性回归', '梯度下降']。"""
    return [s for s in (norm(x) for x in SPLIT_RE.split(str(phrase))) if len(s) >= 2]


class Matcher:
    """字符级加权重合度：字在页面集合里越罕见，权重越高。

    IDF 而不是整串子串，是因为知识点名和页面用语天然不同名（"三范式" vs "三类范式"）。
    """

    def __init__(self, texts):
        self.texts = texts
        self.n = max(1, len(texts))
        self.df = {}
        for t in texts:
            for c in set(t):
                self.df[c] = self.df.get(c, 0) + 1

    def weight(self, ch):
        if ch in STOP_CHARS or not ch.strip():
            return 0.0
        return math.log(self.n / (self.df.get(ch, 0) + 0.5)) + 0.2

    def score(self, phrase, text):
        chars = {c for c in norm(phrase) if self.weight(c) > 0}
        if not chars:
            return 0.0
        total = sum(self.weight(c) for c in chars)
        if total <= 0:
            return 0.0
        return sum(self.weight(c) for c in chars if c in text) / total

    def best(self, phrases):
        """返回 [(分数, 页码)]，按分数降序。取各别名的最高分。"""
        rows = []
        for idx, text in enumerate(self.texts, 1):
            rows.append((max(self.score(p, text) for p in phrases), idx))
        rows.sort(reverse=True)
        return rows


def parse_coverage(raw):
    """coverage 允许是字符串数组，也允许 {"key":..., "alias":[...], "pages":[...]}。"""
    items = []
    for i, it in enumerate(raw or [], 1):
        if isinstance(it, str):
            items.append({"no": i, "key": it, "alias": [], "pinned": []})
        elif isinstance(it, dict):
            key = it.get("key") or it.get("name") or it.get("k") or ""
            items.append({"no": i, "key": key,
                          "alias": list(it.get("alias") or []),
                          "pinned": list(it.get("pages") or it.get("pinned") or [])})
    return [it for it in items if it["key"]]


def resolve_covers(slides, items, matcher):
    """把 slide.covers 里的名字/序号翻成知识点编号；返回 (映射, 虚标列表)。"""
    by_key = {norm(it["key"]): it["no"] for it in items}
    claims = {it["no"]: [] for it in items}
    bogus = []
    for idx, sp in enumerate(slides, 1):
        for c in sp.get("covers") or []:
            no = None
            if isinstance(c, int) and 1 <= c <= len(items):
                no = c
            else:
                cs = norm(c)
                if cs in by_key:
                    no = by_key[cs]
                elif cs.isdigit() and 1 <= int(cs) <= len(items):
                    no = int(cs)
                else:
                    # 名字写得近似也认：挑离子串最像的那个
                    best = max(items, key=lambda it: matcher.score(it["key"], cs))
                    if matcher.score(best["key"], cs) >= HIT:
                        no = best["no"]
            if no is None:
                bogus.append((idx, c))
            else:
                claims[no].append((idx, "声明"))
    return claims, bogus


# ---------------------------------------------------------------- 主检查

def check(storyboard_path, pptx_path=None, md_path=None, strict=False, quiet=False):
    with open(storyboard_path, encoding="utf-8") as f:
        sb = json.load(f)
    slides = sb.get("slides") or []
    items = parse_coverage(sb.get("coverage"))
    if not items:
        print("[覆盖度] 故事板没有 coverage 数组——无法核对覆盖，等于没做这项检查。")
        print('         请在顶层补 "coverage": ["知识点1", "知识点2", ...]')
        return 1 if strict else 0
    if not slides:
        print("[覆盖度] 故事板没有 slides。")
        return 1 if strict else 0

    texts = [norm(slide_text(sp)) for sp in slides]
    matcher = Matcher(texts)
    claims, bogus = resolve_covers(slides, items, matcher)

    top_hits = {}
    for it in items:
        rows = matcher.best([it["key"]] + it["alias"])
        top_hits[it["no"]] = rows
        if claims[it["no"]]:
            continue                       # 显式声明的优先，不再靠猜
        if not rows or rows[0][0] < HIT:
            continue
        floor = max(HIT, rows[0][0] * 0.75)   # 只收跟最佳页接近的，避免一页页扫过去全是命中
        for sc, p in rows:
            if sc >= floor:
                claims[it["no"]].append((p, "用语匹配"))
        claims[it["no"]] = claims[it["no"]][:6]
    for it in items:
        for p in it["pinned"]:
            if isinstance(p, int) and 1 <= p <= len(slides):
                claims[it["no"]].append((p, "指定"))

    missing = [it for it in items if not claims[it["no"]]]
    maybe = [it for it in missing
             if top_hits[it["no"]] and top_hits[it["no"]][0][0] >= MAYBE]
    hard_missing = [it for it in missing if it not in maybe]

    declared_claims = {no: [p for p, how in rec if how in ("声明", "指定")]
                       for no, rec in claims.items()}

    per_slide = {}
    for it in items:
        for p in declared_claims[it["no"]]:
            per_slide.setdefault(p, set()).add(it["no"])

    # 顺序与堆砌只用「声明」判：这两件事要求知道每页的"主讲知识点"，
    # 而字面匹配只能回答"有没有提到"。主线页和小结页会顺带提到所有概念，
    # 拿它判顺序，每次跑都刷一屏假警报，工具就没人看了。
    primary = {}
    for it in items:
        pages = declared_claims[it["no"]]
        if not pages:
            continue
        scores = {p: matcher.score(it["key"], texts[p - 1]) for p in pages}
        primary[it["no"]] = max(scores, key=lambda p: (scores[p], -p))
    jumps = []
    prev = None
    for it in items:
        cur = primary.get(it["no"])
        if cur is None:
            continue
        if prev is not None and cur < prev[1]:
            jumps.append((prev[0], prev[1], it["key"], cur))
        prev = (it["key"], cur)

    # ---- 输出
    total = len(items)
    covered = total - len(missing)
    declared = sum(1 for it in items if any(h == "声明" for _, h in claims[it["no"]]))
    if not quiet:
        print(f"[覆盖度] {covered}/{total} 个知识点有承载页｜{len(slides)} 页｜"
              f"覆盖率 {covered * 100 // total}%｜其中 {declared} 个靠 slides 的 covers 声明")
        for it in items:
            pages = sorted({p for p, _ in claims[it["no"]]})
            if pages:
                pstr = "、".join(f"p{p}" for p in pages)
                print(f"   {it['no']:>2}. {it['key']}  →  {pstr}")
            else:
                top = top_hits[it["no"]][:1]
                hint = f"（最接近 p{top[0][1]} 得分 {top[0][0]:.2f}）" if top else ""
                print(f"   {it['no']:>2}. {it['key']}  →  ✗ 无页 {hint}")
    if maybe:
        print(f"[疑似] {len(maybe)} 个知识点可能只是换了说法，确认一下再决定补页还是补 covers：")
        for it in maybe:
            sc, p = top_hits[it["no"]][0]
            print(f"   - {it['key']}  ← 最接近 p{p}（{slides[p - 1].get('title', '')}），得分 {sc:.2f}")
        print("     若确认已讲：在那一页加 \"covers\": [\"知识点名\"]；确实没讲：补页。")
    if hard_missing:
        print(f"[漏讲] {len(hard_missing)} 个知识点没有任何一页承载：")
        for it in hard_missing:
            print(f"   - {it['key']}")
    # 全靠字面匹配时，结论只能当提示：D/通识模式的标题本来就是大白话，
    # "训练闭环"写成"一个圈，转很多遍"是正确做法，字面重合度必然低，工具必须说清楚这点。
    if declared * 2 < total and (hard_missing or maybe):
        print(f"     ↑ 只有 {declared}/{total} 个知识点写了 covers，其余靠字面匹配。"
              f"通识版标题常是口语（「一个圈，转很多遍」＝训练闭环），"
              f"匹配不上不等于没讲——补 covers 再跑一次才算数。")
    if bogus:
        print("[虚标] covers 指向了不存在的知识点（名字打错或序号越界）：")
        for idx, c in bogus[:8]:
            print(f"   - 第 {idx} 页 covers 里的「{c}」")
    over = [(p, ns) for p, ns in per_slide.items() if len(ns) >= 5]
    if over:
        print("[堆砌] 一页塞了 5 个以上知识点——学生一页只能记住一件事，拆开：")
        for p, ns in sorted(over):
            names = "、".join(items[x - 1]["key"] for x in sorted(ns))
            print(f"   - 第 {p} 页（{len(ns)} 个）：{names}")
    if jumps:
        print("[顺序] 知识点出场页序回跳，讲到这里时学生已经跟丢：")
        for prev, pp, cur, cp in jumps[:5]:
            print(f"   - 「{prev}」在 p{pp} 之后又出现「{cur}」（p{cp}）")
    elif declared and not quiet:
        print("[顺序] 已声明知识点的主页页序连续，无回跳")

    if pptx_path:
        if not os.path.exists(pptx_path):
            print(f"[覆盖度] 给了 --pptx 但文件不存在：{pptx_path}")
        else:
            from pptx import Presentation
            n = len(Presentation(pptx_path).slides)
            if n != len(slides):
                print(f"[覆盖度] 页数对不上：pptx {n} 页 vs 故事板 {len(slides)} 页"
                      f"（pptx 是旧版？重跑 build_deck.py）")
            else:
                print(f"[覆盖度] pptx 页数与故事板一致（{n} 页）")

    if md_path:
        write_md(md_path, sb, items, claims, maybe, hard_missing, top_hits, bogus)

    return 1 if (strict and missing) else 0


def write_md(path, sb, items, claims, maybe, hard_missing, top_hits, bogus):
    meta = sb.get("meta") or {}
    slides = sb.get("slides") or []
    lines = [f"# 覆盖矩阵：{meta.get('chapter') or os.path.basename(path)}", ""]
    lines.append(f"- 模式：{meta.get('mode') or '未标'}｜页数：{len(slides)}"
                 f"｜知识点：{len(items)}｜待确认：{len(maybe)}｜漏讲：{len(hard_missing)}")
    lines += ["", "| # | 知识点 | 承载页 | 页型 | 命中方式 |", "|---|---|---|---|---|"]
    for it in items:
        rec = claims[it["no"]]
        if not rec:
            sc, p = (top_hits[it["no"]][0] if top_hits[it["no"]] else (0, None))
            tail = f"疑似 p{p}（{sc:.2f}）" if it in maybe else "**漏讲**"
            lines.append(f"| {it['no']} | {it['key']} | — | — | {tail} |")
            continue
        pages = sorted({p for p, _ in rec})
        kinds = sorted({slides[p - 1].get("type", "bullets") for p in pages if p <= len(slides)})
        hows = sorted({h for _, h in rec})
        lines.append(f"| {it['no']} | {it['key']} | {'、'.join('p' + str(p) for p in pages)} "
                     f"| {'/'.join(kinds)} | {'/'.join(hows)} |")
    todo = [it["key"] for it in hard_missing] + [it["key"] for it in maybe]
    if todo:
        lines += ["", "## 待处理", ""]
        lines += [f"- [ ] {it['key']}" for it in hard_missing]
        lines += [f"- [ ] {it['key']}（疑似已讲，请确认）" for it in maybe]
    if bogus:
        lines += ["", "## 声明的知识点不存在", ""]
        lines += [f"- 第 {i} 页：`{c}`" for i, c in bogus]
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[覆盖度] 矩阵已写出：{path}")


def main():
    ap = argparse.ArgumentParser(description="知识点覆盖度机检")
    ap.add_argument("storyboard")
    ap.add_argument("--pptx", default=None, help="顺带核对页数是否与故事板一致")
    ap.add_argument("--md", default=None, help="导出覆盖矩阵 Markdown")
    ap.add_argument("--strict", action="store_true", help="有漏讲时退出码 1，适合卡在交付前")
    ap.add_argument("-q", "--quiet", action="store_true", help="只打问题，不打逐条矩阵")
    args = ap.parse_args()
    sys.exit(check(args.storyboard, args.pptx, args.md, args.strict, args.quiet))


if __name__ == "__main__":
    main()
