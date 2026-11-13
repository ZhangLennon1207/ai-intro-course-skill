#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""对照「教师原件」与「生成课件」，输出页级差异清单。

A/C 模式的要求是"沿用教师骨架、只做增补"。但改了什么、漏了什么，把两份 pptx
并排翻是翻不出来的——原件动辄上百页，生成的只有二三十页。

**不做逐页标题对齐**：教师课件常常整章共用一个页头标签（20 页里只有 5 个不同标题），
按标题配对会把同一页判成十页新增。改成两级核对：
  1. 章节对照——按页头标签把连续页聚成节，两边按授课顺序对应，看每节扩了几页、压了几页
  2. 内容落点——原件每页的正文有多少字能在生成件里找到，找不到的就是疑似漏讲

用法：
    python diff_deck.py 原件.pptx 生成件.pptx
    python diff_deck.py 原件.pptx 生成件.pptx --md out/差异清单.md
"""
import argparse
import statistics
import sys
from collections import Counter

import envcheck  # noqa: E402  同目录依赖自检，缺库时给人话
envcheck.ensure()

from pptx import Presentation


def _clean(s):
    import re
    return re.sub(r"\s+", "", s or "")


def bigrams(s):
    """按字符二元组比对。

    用单字集合算覆盖率会虚高：中文里「的、是、在」到处都有，随便两页的字符交集
    就能过半。改成二元组，只有「深度」「学习」这类真实词对才算命中。
    """
    s = _clean(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def coverage_of(page_grams, pool_grams):
    if not page_grams:
        return 0.0
    return len(page_grams & pool_grams) / len(page_grams)


def page_profile(slide, no):
    """分出页头标签与页标题。教师课件里页头标签是整章复用的，页标题常常没有。"""
    items = []
    for shp in slide.shapes:
        if not shp.has_text_frame:
            continue
        t = shp.text_frame.text.strip()
        if not t:
            continue
        top = (shp.top or 0) / 914400.0
        size = 0.0
        for p in shp.text_frame.paragraphs:
            for r in p.runs:
                if r.font.size:
                    size = max(size, r.font.size.pt)
        items.append((top, size, t))
    items.sort(key=lambda x: (x[0], -x[1]))
    label = items[0][2].split("\n")[0][:24] if items else ""
    title = ""
    for top, _sz, t in items[1:]:
        if top < 2.2:                       # 页面上部第一个非标签框，当页标题
            title = t.split("\n")[0][:30]
            break
    if not title and len(items) > 1:
        title = items[1][2].split("\n")[0][:30]
    return {"no": no, "label": label, "title": title,
            "full": "".join(t for _, _, t in items), "nbox": len(items)}


def deck_info(path):
    prs = Presentation(path)
    sizes, fonts, layouts, pages = [], Counter(), Counter(), []
    for i, s in enumerate(prs.slides, 1):
        layouts[s.slide_layout.name] += 1
        for shp in s.shapes:
            if shp.has_text_frame:
                for p in shp.text_frame.paragraphs:
                    for r in p.runs:
                        if r.font.size:
                            sizes.append(round(r.font.size.pt))
                        if r.font.name:
                            fonts[r.font.name] += 1
        pages.append(page_profile(s, i))
    return {"path": path, "count": len(prs.slides), "pages": pages,
            "sizes": sizes,
            "median_pt": statistics.median(sizes) if sizes else 0,
            "fonts": fonts, "layouts": layouts}


def group_sections(pages, strip_topic=False):
    """连续同标签的页归成一节。

    strip_topic：生成件的页头常写成「3.1 · 三类范式」，主题一路变，按整串分组会
    变成一页一节；只留编号才能把同一节聚起来。
    """
    def key(label):
        return label.split("·")[0].strip() if strip_topic else label

    secs = []
    for p in pages:
        k = key(p["label"])
        if secs and secs[-1]["key"] == k:
            secs[-1]["pages"].append(p)
        else:
            secs.append({"key": k, "label": p["label"], "pages": [p]})
    return secs


def ranges(nums):
    return f"p{nums[0]}" if len(nums) == 1 else f"p{nums[0]}–p{nums[-1]}"


def main():
    ap = argparse.ArgumentParser(description="生成教师原件与生成课件的差异清单")
    ap.add_argument("original", help="教师原件 .pptx")
    ap.add_argument("generated", help="生成件 .pptx")
    ap.add_argument("--md", default=None, help="把清单写到这个 markdown 文件")
    ap.add_argument("--trace-floor", type=float, default=0.5,
                    help="原件一页有这么多比例的字在生成件里找不到，就算疑似漏讲（默认 0.5）")
    ap.add_argument("--strict", action="store_true",
                    help="有「几乎没讲」的原件页就退出码 1，供流程串联")
    args = ap.parse_args()

    old, new = deck_info(args.original), deck_info(args.generated)
    old_secs = group_sections(old["pages"])
    # 生成件的页头是「3.1 · 三类范式」这种带主题的写法，剥掉主题才聚得成节
    new_secs = group_sections(new["pages"], strip_topic=True)

    L = ["# 课件差异清单", ""]
    L.append(f"- 原件：`{args.original}`（{old['count']} 页）")
    L.append(f"- 生成：`{args.generated}`（{new['count']} 页）")
    L.append(f"- 页数比：{new['count']}/{old['count']} = "
             f"{new['count'] * 100 // max(old['count'], 1)}%")
    L += ["", "## 一、版式与字号", "", "| 项目 | 原件 | 生成件 |", "|---|---|---|",
          f"| 页数 | {old['count']} | {new['count']} |",
          f"| 正文字号中位数 | {old['median_pt']} pt | {new['median_pt']} pt |",
          f"| 主要版式 | {'、'.join(f'{n} {c} 页' for n, c in old['layouts'].most_common(3)) or '—'} "
          f"| {'、'.join(f'{n} {c} 页' for n, c in new['layouts'].most_common(3)) or '—'} |",
          f"| 主要字体 | {'、'.join(n for n, _ in old['fonts'].most_common(3)) or '—'} "
          f"| {'、'.join(n for n, _ in new['fonts'].most_common(3)) or '—'} |", ""]

    L += ["## 二、结构并列", "",
          "两边各按自己的章节组织，**不强行一一配对**：教师按教材章走，生成件按节次走，"
          "粒度本来就不同，硬配对只会错位。看各自的分布，再结合第三节判断有没有漏。",
          "", "| 原件章节 | 页 | 页数 | 生成件章节 | 页 | 页数 |",
          "|---|---|---|---|---|---|"]
    for i in range(max(len(old_secs), len(new_secs))):
        a = old_secs[i] if i < len(old_secs) else None
        b = new_secs[i] if i < len(new_secs) else None
        cells = []
        cells += [a["label"] or "（无标签）", ranges([p["no"] for p in a["pages"]]),
                  str(len(a["pages"]))] if a else ["", "", ""]
        cells += [b["key"] or "（无标签）", ranges([p["no"] for p in b["pages"]]),
                  str(len(b["pages"]))] if b else ["", "", ""]
        L.append("| " + " | ".join(cells) + " |")
    L.append("")

    # ---- 内容落点：原件每页的字，有多少进了新课件
    # 用「整份新课件」做对照池，不是逐页挑最像的一页：一份 20 页的原件扩成 34 页，
    # 内容本来就被拆散了，只跟单页比必然偏低。
    pool = set()
    for q in new["pages"]:
        pool |= bigrams(q["full"])
    lost, image_only = [], []
    for p in old["pages"]:
        if p["no"] in (1, old["count"]):
            continue                        # 封面封底不是内容页，报"漏讲"只是噪音
        grams = bigrams(p["full"])
        if len(grams) < 6:                  # 400 来字的页才不到 6 个词对，必是无正文页
            image_only.append(p)
            continue
        best = coverage_of(grams, pool)
        if best < args.trace_floor:
            lost.append((p, best))

    hard = [(p, sc) for p, sc in lost if sc < 0.30]
    soft = [(p, sc) for p, sc in lost if sc >= 0.30]

    L += [f"## 三、疑似漏讲的原件页（{len(lost)} 页）", ""]
    if not lost:
        L.append(f"原件每一页都有至少 {int(args.trace_floor * 100)}% 的词在新课件里找得到。")
    else:
        if hard:
            L += [f"### 几乎没讲（留存 < 30%，共 {len(hard)} 页）", "",
                  "这些页的用词在新课件里基本找不到，优先核这几页：", ""]
            for p, sc in hard:
                L.append(f"- p{p['no']}（{p['label']}）{p['title'] or '无小标题'}"
                         f"｜留存 {sc * 100:.0f}%")
            L.append("")
        if soft:
            L += [f"### 可能换了说法（留存 30–{int(args.trace_floor * 100)}%，共 {len(soft)} 页）", "",
                  "内容或许讲了、只是没用教师的原话。快速扫一眼就能确认：", ""]
            for p, sc in soft:
                L.append(f"- p{p['no']}（{p['label']}）{p['title'] or '无小标题'}"
                         f"｜留存 {sc * 100:.0f}%")
            L.append("")
    L.append("")

    if image_only:
        L += [f"## 四、纯图/无文字页（{len(image_only)} 页，需人工看）", ""]
        L.append("这些页原件里没有正文，机器判断不了是否讲到了，只能人眼对：")
        L.append("")
        L.append("、".join(f"p{p['no']}" for p in image_only[:40]))
        L.append("")

    L += ["> 内容留存率是「原件这页的字有多少出现在新课件某页」，只用于定位，不判断对错。",
          "> 换说法、换例子都会让它偏低；重点看留存明显低的那几页。"]

    text = "\n".join(L)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"[ok] 差异清单已写入 {args.md}")
        print(f"     原件 {old['count']} 页 → 生成 {new['count']} 页｜章节 {len(old_secs)}→{len(new_secs)}"
              f"｜疑似漏讲 {len(lost)} 页（其中几乎没讲 {len(hard)} 页）｜纯图页 {len(image_only)} 页")
    else:
        print(text)
    # 「几乎没讲」是硬结论：这些页的用词在新课件里基本找不到，说明整段内容没进来。
    # 只在人眼里过一遍，等于把 A/C 的对齐交给自觉；给个退出码，好串进流程。
    if args.strict and hard:
        print(f"[漏讲] {len(hard)} 个原件页几乎没有落地，验收不通过："
              + "、".join(f"p{p['no']}" for p, _ in hard))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
