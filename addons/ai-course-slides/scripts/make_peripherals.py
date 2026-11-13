#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从故事板生成三份周边材料：速记卡、提问单、讲稿提示。

课件只是课堂的中间产物。学生课后复习靠的是速记卡，教师上台靠的是讲稿提示，
课堂互动靠的是提问单——这三样以前要另外手工攒，攒不出来就只剩一份 PPT 发给学生。

三份全从故事板出，不新增内容：速记卡的数字与口诀都取自 memory 段，
提问单只取 recall 页，讲稿提示只取每页已有的字段。写故事板时没写的东西，
这里不会替它编——那一栏留空并标注，让教师补。

用法：
    python scripts/make_peripherals.py 故事板.json -o out/周边
    python scripts/make_peripherals.py 故事板.json -o out/周边 --minutes 90
"""
import argparse
import json
import os
import re
import sys

# 每页大概讲多久（分钟）。按页型给，不按字数：字多的页不一定讲得久，
# 一张图让学生自己看的那几分钟，比三行公式长。
MIN_PER_TYPE = {"cover": 1.0, "section": 0.5, "spine": 3.0, "recall": 2.5,
                "bullets": 2.5, "twocol": 2.5, "table": 3.0, "figure": 3.5,
                "summary": 2.0, "quote": 1.5, "end": 1.0}
TYPE_CN = {"cover": "封面", "section": "分段", "spine": "记忆主干", "recall": "回问",
           "bullets": "要点", "twocol": "对照", "table": "表格", "figure": "图",
           "summary": "小结", "quote": "引文", "end": "收尾"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _first_sentence(text, cap=60):
    t = str(text or "").strip().replace("\n", " ")
    for ch in ("。", "；", "！", "？"):
        i = t.find(ch)
        if 0 < i < cap:
            return t[:i + 1]
    return t[:cap] + ("…" if len(t) > cap else "")


def _sec_key(sp, cur):
    """这一页属于哪一节，返回 (分组键, 节名)。

    三档回退：显式的 section 字段 → kicker 里的编号前缀（「4.2 结构」→ 4.2）
    → 最近一张 section 页的标题。只认 section 页会漏掉整类故事板：
    C/D 版常常不写 section 页，只在 kicker 里标「4.1 / 4.2」，
    那样「每节只留一句」会整段空着。
    """
    sec = str(sp.get("section") or "").strip()
    if sec:
        return sec, sec
    kick = str(sp.get("kicker") or "").strip()
    m = re.match(r"^\s*(\d+(?:\.\d+)*)", kick)
    if m:
        rest = kick[m.end():].strip(" ·-—:：")
        return m.group(1), (cur or rest or m.group(1))
    if cur:
        return cur, cur
    return kick or "_", kick or "全讲"


# ---------------------------------------------------------------- 速记卡
def handout(sb):
    mem = sb.get("memory") or {}
    meta = sb.get("meta") or {}
    slides = sb.get("slides") or []
    title = meta.get("chapter") or "本讲"
    out = [f"# 速记卡｜{title}", "",
           f"> {meta.get('course', '')}　{meta.get('meta', '')}".strip(), ""]
    if not mem:
        out += ["> 故事板没有 memory 段，这张卡只能是空的。"
                "补上 spine / mnemonic / anchors 再跑一次。", ""]

    spine = [str(x) for x in (mem.get("spine") or [])]
    if spine:
        out += ["## 一条线：这一讲讲完，你应该能一口气说出这四步", ""]
        out += [f"{i}. {s}" for i, s in enumerate(spine, 1)]
        out += [""]
    if mem.get("mnemonic"):
        out += [f"**口诀**　{mem['mnemonic']}", ""]

    anchors = mem.get("anchors") or []
    if anchors:
        out += ["## 锚点：抽象概念挂在什么事上", "",
                "| 知识点 | 拿这个记住它 |", "|---|---|"]
        for a in anchors:
            out.append(f"| {a.get('point', '')} | {a.get('anchor', '')} |")
        out += [""]

    # 每节一句话：在该节里找第一个带结论句的页，整节都没有才退回标题。
    # 原先只取该节第一张内容页，那一页的 takeaway 被减密删掉时，
    # 卡片上这句就变成了页标题（「突触可塑性：学习就是改连接强度」），
    # 读起来像目录而不是结论。
    out += ["## 每节只留一句", ""]
    cur, order, bucket = "", [], {}
    for sp in slides:
        if sp.get("type") == "section":
            cur = str(sp.get("title") or "")
            continue
        # spine 不参与：它是全讲的主干，不属于任何一节；拿它当第一节那一句，
        # 那张卡上第一节就等于没写
        if str(sp.get("type")) not in ("bullets", "table", "figure", "twocol"):
            continue
        key, name = _sec_key(sp, cur)
        if key not in bucket:
            order.append((key, name))
            bucket[key] = []
        bucket[key].append(sp)
    for key, name in order:
        sps = bucket[key]
        line = next((str(x.get("takeaway")) for x in sps
                     if str(x.get("takeaway") or "").strip()), "")
        if not line:
            line = next((str(x.get("title")) for x in sps if x.get("title")), "")
        out.append(f"- **{name}**｜{line}")
    if not order:
        out.append("（故事板里既没有 section 页，kicker 里也没有节号，这一栏只能留空）")
    out += [""]

    pit = mem.get("pitfalls") or []
    if pit:
        out += ["## 容易记错的", ""]
        out += [f"- {p}" for p in pit]
        out += [""]

    # 复习节奏建议：不写具体日期，写间隔
    out += ["## 什么时候再看一遍", "",
            "- 当天晚上：只看「一条线」和口诀，能背出来就过",
            "- 第二天：遮住锚点表右列，自己说一遍对应关系",
            "- 一周后：只看口诀，把四步复述出来", ""]
    if not mem.get("mnemonic"):
        out += ["> 这张卡缺口诀，间隔复习会退化成重读讲义。", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- 提问单
def questions(sb):
    slides = sb.get("slides") or []
    title = (sb.get("meta") or {}).get("chapter") or "本讲"
    rec = [(i, s) for i, s in enumerate(slides, 1) if str(s.get("type")) == "recall"]
    out = [f"# 课堂提问单｜{title}", ""]
    if not rec:
        return "\n".join(out + ["故事板里没有 recall 页，这份提问单没有内容。",
                                "", "回问页是唯一能让「间隔复现」落进 PPT 的形式：",
                                "每 6–8 页插一页，问的是上一段的核心判断。", ""])
    out += [f"共 {len(rec)} 处停顿。每题按「问 → 等 → 揭晓 → 追问」用，"
            f"不要自问自答。", ""]
    for n, (i, s) in enumerate(rec, 1):
        out += [f"## {n}. 第 {i} 页（{s.get('kicker') or '停顿'}）", "",
                f"**问**　{s.get('title') or s.get('ask') or ''}", ""]
        if s.get("answer"):
            out += [f"**参考答案**　{s['answer']}", ""]
        if s.get("covers"):
            out += [f"**这题在考**　{'、'.join(str(c) for c in s['covers'])}", ""]
        if s.get("note"):
            out += [f"**教师备忘**　{s['note']}", ""]
        if s.get("followup"):
            out += [f"**追问**　{s['followup']}", ""]
        else:
            out += ["**追问**　＿＿＿＿＿＿＿＿（备课时填：这道题答对了，还能问什么）", ""]
        out += ["等待时间：心里数 5 秒再点名。三秒内举手的通常是背过的，不一定是想过的。", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- 讲稿提示
def script(sb, minutes=90):
    slides = sb.get("slides") or []
    meta = sb.get("meta") or {}
    title = meta.get("chapter") or "本讲"
    raw = [MIN_PER_TYPE.get(str(s.get("type")), 2.5) for s in slides]
    total = sum(raw) or 1
    # 只允许把配速放慢到 1.4 倍。再往上就是「15 页撑 90 分钟」——
    # 那不是配速问题，是内容不够，硬摊成每页 9 分钟只会让课堂空转。
    k = min(minutes / total, 1.4)
    out = [f"# 讲稿提示｜{title}", "",
           f"配速按 {minutes} 分钟排；按页型估时 {total:.0f} 分钟，"
           f"折算系数 ×{k:.2f}。", ""]
    if total > minutes * 1.35:
        out += [f"> 页太多：估时 {total:.0f} 分钟，比 {minutes} 分钟多出 "
                f"{(total / minutes - 1) * 100:.0f}%。这个差不是靠讲快补的，是要砍页的。", ""]
    elif total < minutes * 0.6:
        out += [f"> 页太少：估时只有 {total:.0f} 分钟，{minutes} 分钟的课会空出 "
                f"{minutes - total:.0f} 分钟。空出来的时间安排当堂练习或讨论，"
                f"不要靠拖慢语速填——拖慢的课学生注意力掉得最快。", ""]
    out += ["| 页 | 页型 | 分 | 这页要让学生拿到什么 | 讲的时候注意 |", "|---|---|---|---|---|"]
    acc = 0.0
    for i, (s, m) in enumerate(zip(slides, raw), 1):
        acc += m * k
        typ = TYPE_CN.get(str(s.get("type")), str(s.get("type")))
        head = s.get("takeaway") or s.get("title") or s.get("caption") or ""
        if s.get("type") == "spine":
            head = s.get("mnemonic") or s.get("title") or ""
        elif s.get("type") == "recall":
            head = s.get("answer") or s.get("title") or ""
        note = s.get("note") or ""
        out.append(f"| {i} | {typ} | {m * k:.1f} | {_first_sentence(head, 42)} | "
                   f"{_first_sentence(note, 34)} |")
    out += ["", f"累计约 {acc:.0f} 分钟。", ""]
    out += ["## 上台前照这个顺序过一遍", "",
            "1. 封面那句判断，能不能用一句话说给外行听懂",
            "2. 记忆主干四个节点，顺序不能乱；口诀要念出声",
            "3. 每个回问停 5 秒，等不到答案就降一个问题再问",
            "4. 小结页让学生自己说，不要替他们说", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="从故事板生成周边材料（速记卡/提问单/讲稿提示）")
    ap.add_argument("storyboard")
    ap.add_argument("-o", "--outdir", default="out/周边")
    ap.add_argument("--minutes", type=int, default=90, help="本讲时长，默认90只是示例建议，不是课程学时规定")
    ap.add_argument("--tag", default="", help="文件名后缀，如「单元3_C模式」")
    args = ap.parse_args()

    if not os.path.exists(args.storyboard):
        sys.exit(f"故事板不存在：{args.storyboard}")
    sb = load(args.storyboard)
    if not sb.get("slides"):
        sys.exit("故事板里没有 slides")
    os.makedirs(args.outdir, exist_ok=True)
    tag = args.tag or os.path.splitext(os.path.basename(args.storyboard))[0]
    for name, text in (("速记卡", handout(sb)),
                       ("提问单", questions(sb)),
                       ("讲稿提示", script(sb, args.minutes))):
        p = os.path.join(args.outdir, f"{name}_{tag}.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[ok] {p}（{len(text)} 字）")


if __name__ == "__main__":
    main()
