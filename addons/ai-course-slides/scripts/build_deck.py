#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从故事板 JSON 生成可编辑 PPTX。

用法:
    python build_deck.py storyboard.json out.pptx [--template a.pptx] [--check]

设计要点:
1. 有模板 -> 以模板文件为底，清空示例页但保留母版/版式/主题，再从模板读取字体与配色
2. 无模板 -> 用 assets/default-template.pptx
3. 标题优先写进模板自带的标题占位符（继承模板样式），正文自绘，位置按占位符底部自动下移
"""
import argparse
import json
import math
import os
import re
import sys

from lxml import etree
import envcheck  # noqa: E402  同目录依赖自检，缺库时给人话
envcheck.ensure()

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Inches, Pt
from pptx.oxml.ns import qn

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
DEFAULT_TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "assets", "default-template.pptx")

# ---------- 四种授课口径（深度模式） ----------
# 两个维度：是有教师课件（对齐）还是没有（从教材起）；对象是 AI 相关专业还是非 AI 专业。
# 同一份内容在四个模式下，排版密度必须不同，否则"给艺术类上的课"和"给计算机类上的课"看起来一样。
MODE_STYLE = {
    # A 对齐增强：有课件 + AI 类。沿用教师的知识顺序与公式，只补环节，密集排版。
    "A": {"name": "对齐增强（有课件·AI类）", "body_min": 14, "body_max": 24, "pages": None,
          "max_points": 5, "line": 1.35, "gap": 0.9, "max_chars": 320},
    # B 专业标准：无课件 + AI 类。推导完整，允许公式与紧凑要点。
    "B": {"name": "专业标准（无课件·AI类）", "body_min": 14, "body_max": 25, "pages": None,
          "max_points": 5, "line": 1.35, "gap": 0.9, "max_chars": 320},
    # C 通俗改造：有课件 + 非 AI 类。骨架不动，字号加大、每页要点减少、行距放松。
    "C": {"name": "通俗改造（有课件·非AI类）", "body_min": 16, "body_max": 26, "pages": None,
          "max_points": 4, "line": 1.5, "gap": 1.05, "max_chars": 240},
    # D 通识入门：无课件 + 非 AI 类。最少字、最大字号，靠图与类比承担信息。
    "D": {"name": "通识入门（无课件·非AI类）", "body_min": 18, "body_max": 28, "pages": None,
          "max_points": 4, "line": 1.5, "gap": 0.95, "max_chars": 260},
}

# ---------- 主题读取 ----------

def read_theme(prs):
    """从 ppt/theme/themeN.xml 读字体与配色。"""
    theme = {"major": "微软雅黑", "minor": "微软雅黑",
             "accent": "1F4E79", "text": "1A1A1A", "muted": "595959",
             "bg": "FFFFFF", "accent_light": "EAF0F8"}
    for part in prs.part.package.iter_parts():
        name = str(part.partname)
        if not name.startswith("/ppt/theme/"):
            continue
        try:
            root = etree.fromstring(part.blob)
        except Exception:
            continue
        ns = {"a": A}
        fonts = root.findall(".//a:fontScheme", ns)
        if fonts:
            fs = fonts[0]
            for tag, key in (("a:majorFont", "major"), ("a:minorFont", "minor")):
                node = fs.find(tag, ns)
                if node is None:
                    continue
                ea = node.find("a:ea", ns)
                latin = node.find("a:latin", ns)
                face = ""
                if ea is not None and ea.get("typeface"):
                    face = ea.get("typeface")
                elif latin is not None and latin.get("typeface"):
                    face = latin.get("typeface")
                if face and not face.startswith("+"):
                    theme[key] = face
        cs = root.findall(".//a:clrScheme", ns)
        if cs:
            scheme = cs[0]
            def get(tag):
                n = scheme.find(f"a:{tag}", ns)
                if n is None:
                    return None
                s = n.find("a:srgbClr", ns)
                if s is not None:
                    return s.get("val")
                sy = n.find("a:sysClr", ns)
                if sy is not None:
                    return sy.get("lastClr")
                return None
            if get("accent1"):
                theme["accent"] = get("accent1")
            if get("dk1"):
                theme["text"] = get("dk1")
            if get("lt1"):
                theme["bg"] = get("lt1")
        break
    theme["accent_light"] = tint(theme["accent"], 0.90)
    return theme


def tint(hex_color, amount):
    """向白色混合，amount=0.9 表示 90% 白。"""
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
    except Exception:
        r, g, b = 31, 78, 121
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"{r:02X}{g:02X}{b:02X}"


# ---------- 基础绘制 ----------

def set_font(run, name, size=None, bold=None, color=None, italic=None, spc=None):
    f = run.font
    if size is not None:
        f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    if italic is not None:
        f.italic = italic
    if color is not None:
        f.color.rgb = RGBColor.from_string(color)
    if spc is not None:
        # 字距按 1/100 pt 存，教师模板的章节标签就靠这个撑开字
        run.font._element.set("spc", str(int(spc)))
    f.name = name
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        node = rPr.find(qn(tag))
        if node is None:
            node = etree.SubElement(rPr, qn(tag))
        node.set("typeface", name)


def text_width_units(s):
    """粗略估算宽度：中文 1，ASCII 0.55。"""
    n = 0.0
    for ch in s:
        n += 1.0 if ord(ch) > 127 else 0.55
    return n


SCRIPT_RE = re.compile(r"\^\{([^{}]*)\}|_\{([^{}]*)\}")
# 匹配没包花括号的上下标：o_j / x^2 / Σ_k。已经写成 _{..} 或 ^{..} 的不会命中。
# 基字符不限于 ASCII：Σ_k、σ_w 一样会原样显示下划线。
BARE_SCRIPT_RE = re.compile(r"(\S)[_^](?!\{)([A-Za-z0-9]+)")


def split_scripts(text):
    """把 ^{上标} 与 _{下标} 拆成 (片段, baseline) 序列。

    为什么不用 Unicode 上标字符（⁽¹⁾ ᵀ ᵢ）：这些字符在中文字体里没有字形，
    PowerPoint 会静默降级成普通括号，W⁽¹⁾ 读起来就成了 W(1)（像函数调用）。
    真正的上下标要用 OOXML 的 baseline 属性。
    """
    out, pos = [], 0
    for m in SCRIPT_RE.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], 0))
        if m.group(1) is not None:
            out.append((m.group(1), 30000))
        else:
            out.append((m.group(2), -25000))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], 0))
    return out or [(text, 0)]


def fit_block(points, w_in, h_in, max_pt=22, min_pt=14, line_factor=1.6, gap_ratio=0.9):
    """按容器高度给一段要点选字号：逐档试，取能装下的最大字号。

    line_factor 取 1.6 而不是 1.35：PowerPoint 的行距倍数是乘在字体行高（约 1.2em）上的，
    按 1.35 算会低估，导致最后一行压到页脚或小结句上。
    """
    import math
    pt = max_pt
    while pt > min_pt:
        cpl = max(1.0, (w_in * 72.0) / pt)
        total = 0.0
        for p in points:
            lines = max(1, math.ceil(text_width_units(p) / cpl))
            total += lines * pt * line_factor / 72.0 + pt * gap_ratio / 72.0
        if total <= h_in:
            return pt
        pt -= 1
    return min_pt


def fit_size(text, box_w_in, box_h_in, max_pt, min_pt=12, line_factor=1.35):
    """按容器尺寸反推可用字号。"""
    size = max_pt
    while size > min_pt:
        cpl = max(1.0, (box_w_in * 72.0) / size)          # 每行可容纳的"中文字"
        lines = 0
        for seg in str(text).split("\n"):
            lines += max(1, int(text_width_units(seg) / cpl) + (1 if text_width_units(seg) % cpl else 0))
        need_h = lines * size * line_factor / 72.0
        if need_h <= box_h_in:
            return size
        size -= 1
    return min_pt


def add_text(slide, x, y, w, h, text, size=18, color="1A1A1A", bold=False,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font="微软雅黑",
             line_spacing=1.25, space_after=6, bullets=False, spc=None):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    lines = text.split("\n") if isinstance(text, str) else list(text)
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        p.space_after = Pt(space_after)
        if bullets:
            pPr = p._p.get_or_add_pPr()
            pPr.set("marL", str(int(Inches(0.28))))
            pPr.set("indent", str(int(-Inches(0.28))))
            # 顺序必须 buFont 在 buChar 之前，否则 PowerPoint 会判定文件损坏
            for old in pPr.findall(qn("a:buChar")) + pPr.findall(qn("a:buFont")) \
                    + pPr.findall(qn("a:buNone")):
                pPr.remove(old)
            bu_font = etree.SubElement(pPr, qn("a:buFont"))
            bu_font.set("typeface", "Arial")
            bu = etree.SubElement(pPr, qn("a:buChar"))
            bu.set("char", "•")
        for seg, base in split_scripts(line):
            run = p.add_run()
            run.text = seg
            set_font(run, font, size, bold, color, spc=spc)
            if base:
                # 用 OOXML baseline 做真上下标：Unicode 上标字符（⁽¹⁾、ᵀ、ᵢ）在
                # 微软雅黑等中文字体里缺字形，会被降级成普通括号，读起来像函数调用
                run.font._element.set("baseline", str(base))
    return box


def add_line(slide, x, y, w, color="D9D9D9", width=1.0):
    from pptx.enum.shapes import MSO_SHAPE
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                 Inches(w), Pt(width))
    shp.fill.solid()
    shp.fill.fore_color.rgb = RGBColor.from_string(color)
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def add_rect(slide, x, y, w, h, fill=None, line=None, line_w=1.0, rounded=None):
    from pptx.enum.shapes import MSO_SHAPE
    shape = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    shp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if rounded:
        try:
            shp.adjustments[0] = float(rounded)   # 0.5 = 全圆头，跟教师标签一致
        except Exception:
            pass
    if fill:
        shp.fill.solid()
        shp.fill.fore_color.rgb = RGBColor.from_string(fill)
    else:
        shp.fill.background()
    if line:
        shp.line.color.rgb = RGBColor.from_string(line)
        shp.line.width = Pt(line_w)
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


# ---------- 版式选择 ----------

LAYOUT_HINTS = {
    "cover": [["标题幻灯片", "Title Slide", "封面"]],
    "content": [["仅标题", "Title Only"], ["标题和内容", "Title and Content"],
                ["Title and Content", "Content"]],
    "section": [["节标题", "Section Header"], ["仅标题", "Title Only"]],
}


def pick_layout(prs, kind):
    """按名称优先匹配版式，找不到就退化。"""
    hints = LAYOUT_HINTS.get(kind, LAYOUT_HINTS["content"])
    for names in hints:
        for idx, lay in enumerate(prs.slide_layouts):
            for nm in names:
                if nm.lower() in (lay.name or "").lower():
                    return idx
    if kind == "cover":
        return 0
    if kind == "section":
        return min(1, len(prs.slide_layouts) - 1)
    return min(5, len(prs.slide_layouts) - 1)


def strip_slides(prs):
    lst = prs.slides._sldIdLst
    for sld in list(lst):
        rid = sld.get(qn("r:id"))
        try:
            prs.part.drop_rel(rid)
        except Exception:
            pass
        lst.remove(sld)


def kill_placeholders(slide, keep_title=True):
    """删掉除标题外的占位符，避免与自绘内容重叠。"""
    for shp in list(slide.shapes):
        if not shp.is_placeholder:
            continue
        ph = shp.placeholder_format
        if keep_title and ph.type is not None and str(ph.type).startswith("TITLE"):
            continue
        if keep_title and ph.idx == 0:
            continue
        shp._element.getparent().remove(shp._element)


def fill_title(slide, text, theme, fallback_size=30):
    """优先写进模板标题占位符；没有占位符则自绘。

    对齐默认强制左对齐：Office 自带版式的标题是居中的，而正文与 kicker 都是左对齐，
    不统一会出现"同一份 PPT 有的页居中、有的页靠左"。需要居中时在 meta 里写
    "title_align": "center"。
    """
    align = PP_ALIGN.CENTER if theme.get("title_align") == "center" else PP_ALIGN.LEFT
    for shp in slide.shapes:
        if shp.is_placeholder and (shp.placeholder_format.idx == 0):
            tf = shp.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.BOTTOM
            tf.text = ""
            p = tf.paragraphs[0]
            p.alignment = align
            run = p.add_run()
            run.text = text
            size = fit_size(text, shp.width / 914400.0, (shp.height / 914400.0) or 1.0, 32, 18)
            set_font(run, theme["major"], size, True, theme["text"])
            return shp
    add_text(slide, 0.9, 0.85, 11.5, 1.0, text, fallback_size, theme["text"], True,
             font=theme["major"], align=align)
    return None


def title_bottom(slide, default=1.95):
    for shp in slide.shapes:
        if shp.is_placeholder and shp.placeholder_format.idx == 0:
            return (shp.top + shp.height) / 914400.0 + 0.18
    return default


# ---------- 版式画像（从教师课件反推） ----------

def load_profile(path, base_dir=None):
    """读 inspect_template.py 产出的 profile.json，把相对图片路径补全。"""
    with open(path, encoding="utf-8") as f:
        prof = json.load(f)
    root = base_dir or os.path.dirname(os.path.abspath(path))
    for slot in ("chrome", "cover", "end"):
        node = prof.get(slot) or {}
        for key in ("bg_image", "logo", "bg"):
            v = node.get(key)
            if v and not os.path.isabs(v):
                cand = os.path.join(root, v)
                if os.path.exists(cand):
                    node[key] = cand
    return prof


def profile_layout_index(prs, prof):
    """找到画像里指定的正文版式；名字对不上就按「含全页背景图」找。"""
    name = (prof.get("meta") or {}).get("content_layout")
    for idx, lay in enumerate(prs.slide_layouts):
        if name and lay.name == name:
            return idx
    PW = prs.slide_width / 914400.0
    PH = prs.slide_height / 914400.0
    for idx, lay in enumerate(prs.slide_layouts):
        for sh in lay.shapes:
            try:
                if sh.shape_type == 13 and (sh.width / 914400.0) > PW * 0.95 \
                        and (sh.height / 914400.0) > PH * 0.95:
                    return idx
            except Exception:
                pass
    return pick_layout(prs, "content")


def new_content_slide(prs, theme):
    """新建一页正文页：版式取自画像，占位符全部清掉（教师模板靠版式装饰，不靠占位符）。"""
    prof = theme.get("_profile")
    idx = profile_layout_index(prs, prof) if prof else pick_layout(prs, "content")
    s = prs.slides.add_slide(prs.slide_layouts[idx])
    kill_placeholders(s, keep_title=not prof)
    return s


def draw_head(s, prs, spec, theme):
    """按模板画像画页头，返回正文起始 y。

    教师课件的页头是两层，不能只塞一个标题占位符：
      上层 章节标签（圆角标签、居中、白字）—— 说明「这是第几节」
      下层 页标题（左对齐、加粗、18pt）      —— 说明「这一页讲什么」
    只画一层就会出现「全篇页标题都是章节名」，学生翻页时找不到当前讲到哪里。
    """
    prof = theme.get("_profile")
    w = prs.slide_width / 914400.0
    h = prs.slide_height / 914400.0

    if not prof or not prof.get("title"):
        # 没有画像：退回占位符路径
        if spec.get("kicker"):
            add_text(s, 0.9, 0.5, w - 1.8, 0.3, spec["kicker"], 11, theme["muted"], False,
                     font=theme["minor"])
        fill_title(s, spec["title"], theme)
        return title_bottom(s)

    t = prof["title"]
    px, py, pw, phh = t["geom"]

    # --- 章节标签
    label = spec.get("section") or spec.get("kicker") or ""
    if label:
        add_rect(s, px, py, pw, phh,
                 t.get("fill") or theme["accent"],
                 t.get("line"), t.get("line_w") or 1.0,
                 rounded=0.5 if t.get("kind") == "pill" else None)
        size = t.get("size") or 24
        # 标签宽度固定，字数多了会被挤出圆角，按宽度回缩字号
        per = max(1.0, (pw - 0.5) * 72.0 / max(1.0, size))
        while text_width_units(label) > per * 1.08 and size > 12:
            size -= 1
        add_text(s, px, py, pw, phh, label, size, t.get("color") or "FFFFFF",
                 bool(t.get("bold")), align=PP_ALIGN.CENTER,
                 anchor=MSO_ANCHOR.MIDDLE, font=t.get("font") or theme["major"],
                 line_spacing=t.get("line_spacing") or 1.1, space_after=0,
                 spc=t.get("spc"))

    # --- 页标题
    pt = prof.get("page_title") or {}
    g = pt.get("geom") or [0.55, py + phh + 0.10, w - 1.1, 0.42]
    # 页标题必须比正文大，否则「标题比内容还小」，学生分不清哪句是本页主题
    tsize = max(pt.get("size") or 18, theme.get("page_title_min") or 0)
    tfont = pt.get("font") or theme["major"]
    tcolor = pt.get("color") or theme["text"]
    tw = min(g[2], w - g[0] - 0.5)
    # 引文页、图页这类页型允许不写 title。缺 title 时只画标签，不要抛 KeyError。
    if not spec.get("title"):
        return max(prof.get("body", [0, 1.5])[1], py + phh + 0.16)
    while text_width_units(spec["title"]) > (tw * 72.0 / tsize) * 1.05 and tsize > 13:
        tsize -= 0.5
    add_text(s, g[0], g[1], tw, g[3] or 0.42, spec["title"], tsize, tcolor, True,
             font=tfont, line_spacing=1.1, space_after=0)

    body_y = max(prof.get("body", [0, 1.5])[1], g[1] + (g[3] or 0.42) + 0.14)
    return body_y


def content_box(prs, theme):
    """正文左右边界：有画像就按画像的内容框，没有就用默认页边距。"""
    prof = theme.get("_profile")
    w = prs.slide_width / 914400.0
    if prof and prof.get("body"):
        bx, _, bw, _ = prof["body"]
        return bx, bw
    return 0.9, w - 1.8


def body_bottom(prs, theme):
    prof = theme.get("_profile")
    h = prs.slide_height / 914400.0
    if prof and prof.get("body"):
        b = prof["body"]
        return b[1] + b[3]
    return h - 0.85


def paint_bg(slide, prs, theme, kind):
    """封面/封底铺整页背景图（教师模板的科技底图不在版式里，在页面上）。"""
    prof = theme.get("_profile")
    if not prof:
        return False
    node = prof.get(kind) or {}
    bg = node.get("bg")
    if not bg or not os.path.exists(bg):
        return False
    slide.shapes.add_picture(bg, 0, 0, prs.slide_width, prs.slide_height)
    return True


# ---------- 页脚 ----------

def add_footer(slide, prs, page, total, meta, theme):
    w = prs.slide_width / 914400.0
    h = prs.slide_height / 914400.0
    add_line(slide, 0.9, h - 0.62, w - 1.8, theme.get("footer_line", "D9D9D9"), 0.75)
    left = meta.get("footer", "")
    add_text(slide, 0.9, h - 0.52, w - 2.6, 0.3, left, 10, theme["muted"], False,
             font=theme["minor"])
    add_text(slide, w - 1.9, h - 0.52, 1.0, 0.3, f"{page} / {total}", 10,
             theme["muted"], False, align=PP_ALIGN.RIGHT, font=theme["minor"])


# ---------- 各类页 ----------

def slide_cover(prs, spec, theme, meta):
    prof = theme.get("_profile")
    if prof:
        s = prs.slides.add_slide(prs.slide_layouts[profile_layout_index(prs, prof)])
    else:
        s = prs.slides.add_slide(prs.slide_layouts[pick_layout(prs, "cover")])
    kill_placeholders(s, keep_title=False)
    w = prs.slide_width / 914400.0
    h = prs.slide_height / 914400.0

    if prof and paint_bg(s, prs, theme, "cover"):
        # 教师封面是「整页底图 + 角标 + 三行字」：课程名 / 章节名 / 主讲人
        cv = prof.get("cover") or {}
        if cv.get("logo") and os.path.exists(cv["logo"]):
            g = cv.get("logo_geom") or [0, 0, 3.1, 0.92]
            s.shapes.add_picture(cv["logo"], Inches(g[0]), Inches(g[1]),
                                 Inches(g[2]), Inches(g[3]))
        layers = [l for l in ((prof.get("cover") or {}).get("layers") or [])
                  if l.get("size") and l["size"] >= 16]
        rows = [("kicker", spec.get("kicker", meta.get("course", ""))),
                ("title", spec["title"]),
                ("meta", spec.get("meta", meta.get("meta", "")))]
        for i, (role, text) in enumerate(rows):
            if not text:
                continue
            ref = layers[i] if i < len(layers) else None
            y = ref["y"] if ref else (1.3 + i * 1.2)
            size = ref["size"] if ref else (40 - i * 4)
            x = ref["x"] if ref else 1.1
            add_text(s, x, y, w - x - 1.0, size / 72.0 * 1.7, text, size, "FFFFFF", True,
                     font=(ref or {}).get("font") or theme["major"],
                     align=PP_ALIGN.CENTER, line_spacing=1.15, space_after=0)
        return s

    add_rect(s, 0, 0, w, 0.16, theme["accent"])
    add_text(s, 0.9, 2.05, w - 1.8, 0.4,
             spec.get("kicker", meta.get("course", "")), 14, theme["accent"], True,
             font=theme["minor"])
    size = fit_size(spec["title"], w - 1.8, 2.0, 44, 26, 1.2)
    add_text(s, 0.9, 2.5, w - 1.8, 2.1, spec["title"], size, theme["text"], True,
             font=theme["major"], line_spacing=1.15, space_after=0)
    if spec.get("subtitle"):
        add_text(s, 0.9, 4.7, w - 1.8, 0.9, spec["subtitle"], 20, theme["muted"], False,
                 font=theme["minor"])
    add_line(s, 0.9, h - 1.55, 3.2, theme["accent"], 2.5)
    bottom = spec.get("meta") or meta.get("meta", "")
    if bottom:
        add_text(s, 0.9, h - 1.35, w - 1.8, 0.4, bottom, 13, theme["muted"], False,
                 font=theme["minor"])
    return s


def slide_section(prs, spec, theme, meta):
    prof = theme.get("_profile")
    if prof:
        s = prs.slides.add_slide(prs.slide_layouts[profile_layout_index(prs, prof)])
    else:
        s = prs.slides.add_slide(prs.slide_layouts[pick_layout(prs, "section")])
    kill_placeholders(s, keep_title=False)
    w = prs.slide_width / 914400.0
    if paint_bg(s, prs, theme, "cover"):
        # 有整页底图时不铺浅色块，直接把章节名压在底图上
        no = str(spec.get("no", "")).zfill(2) if spec.get("no") else ""
        y = 1.9
        if no:
            add_text(s, 1.1, y, 3.0, 1.1, no, 72, "FFFFFF", True, font=theme["major"])
            y += 1.25
        add_text(s, 1.1, y, w - 2.2, 0.9, spec["title"], 34, "FFFFFF", True,
                 align=PP_ALIGN.CENTER, font=theme["major"])
        if spec.get("subtitle"):
            add_text(s, 1.1, y + 1.0, w - 2.2, 0.6, spec["subtitle"], 17, "D8E6F2", False,
                     align=PP_ALIGN.CENTER, font=theme["minor"])
        return s
    add_rect(s, 0, 0, w, prs.slide_height / 914400.0, theme["accent_light"])
    no = str(spec.get("no", "")).zfill(2) if spec.get("no") else ""
    if no:
        add_text(s, 0.9, 2.15, 3.0, 1.2, no, 72, theme["accent"], True, font=theme["major"])
    add_text(s, 0.9, 3.55, w - 1.8, 1.0, spec["title"], 34, theme["text"], True,
             font=theme["major"])
    if spec.get("subtitle"):
        add_text(s, 0.9, 4.6, w - 1.8, 0.7, spec["subtitle"], 17, theme["muted"], False,
                 font=theme["minor"])
    return s


def slide_bullets(prs, spec, theme, meta):
    s = new_content_slide(prs, theme)
    w = prs.slide_width / 914400.0
    top = draw_head(s, prs, spec, theme)
    cx, cw = content_box(prs, theme)
    add_line(s, 0.9, top - 0.12, 1.1, theme["accent"], 3)
    st = dict(meta.get("_style", MODE_STYLE["B"]))
    # 有画像时正文上限不超过教师实际字号太多：教师正文 14pt，我们放到 24pt 就跟原件不像了
    if theme.get("body_max_cap"):
        st["body_max"] = min(st["body_max"], theme["body_max_cap"])
    points = spec.get("points", [])
    take_h = 0.62 if spec.get("takeaway") else 0.0
    avail_h = body_bottom(prs, theme) - top - take_h
    text_w = cw - 0.52
    size = fit_block(points, text_w, avail_h, st["body_max"], st["body_min"],
                     line_factor=1.2 * st["line"], gap_ratio=st["gap"])
    body = "\n".join(points)
    # 内容装不满时，把余量摊进段间距：否则整页下半是空的，看着内容稀
    gap_pt = max(6, int(size * st["gap"]))
    anchor = MSO_ANCHOR.TOP
    if points:
        import math as _m
        cpl = max(1.0, (text_w * 72.0) / size)
        need = sum(max(1, _m.ceil(text_width_units(p) / cpl)) * size * 1.2 * st["line"] / 72.0
                   for p in points)
        n_gap = max(1, len(points) - 1)
        extra_pt = (avail_h - need) * 72.0 - gap_pt * n_gap
        if extra_pt > 0:
            # 段距最多放开到 1.5 倍；再放就把要点拉散了，宁可整块居中
            gap_pt = min(int(size * st["gap"] * 1.15), int(gap_pt + extra_pt / n_gap * 0.55))
        used = need + gap_pt * n_gap / 72.0
        if avail_h - used > avail_h * 0.16:
            anchor = MSO_ANCHOR.MIDDLE
    add_text(s, cx, top, cw, avail_h, body, size, theme["text"], False,
             font=theme["minor"], bullets=True, line_spacing=st["line"],
             space_after=gap_pt, anchor=anchor)
    if spec.get("takeaway"):
        # 结论句压在正文区底部，不能写到框外：教师的内容框到 5.2 英寸就结束了
        add_text(s, cx, body_bottom(prs, theme) - 0.42, cw, 0.4,
                 spec["takeaway"], 13, theme["accent"], True, font=theme["minor"])
    return s


def slide_twocol(prs, spec, theme, meta):
    s = new_content_slide(prs, theme)
    w = prs.slide_width / 914400.0
    top = draw_head(s, prs, spec, theme)
    cx, cw = content_box(prs, theme)
    col_w = (cw - 0.5) / 2
    for i, col in enumerate([spec.get("left", {}), spec.get("right", {})]):
        x = cx + i * (col_w + 0.5)
        head = col.get("head", "")
        add_rect(s, x, top, col_w, 0.55, theme["accent_light"] if i == 0 else "F2F2F2")
        add_text(s, x + 0.2, top + 0.12, col_w - 0.4, 0.35, head, 15, theme["text"], True,
                 font=theme["major"])
        items = col.get("items", [])
        body_h = body_bottom(prs, theme) - top - 0.7
        size = fit_block(items, col_w - 0.4, body_h, 19, 12)
        add_text(s, x + 0.2, top + 0.78, col_w - 0.4, body_h,
                 "\n".join(items), size, theme["text"], False, font=theme["minor"],
                 bullets=True, line_spacing=1.35,
                 space_after=max(8, min(int(size * 1.9), int(8 + body_h * 6))))
    return s


def slide_table(prs, spec, theme, meta):
    s = new_content_slide(prs, theme)
    w = prs.slide_width / 914400.0
    top = draw_head(s, prs, spec, theme)
    cx, cw = content_box(prs, theme)
    tb = spec["table"]
    header, rows = tb["header"], tb["rows"]
    ncol, nrow = len(header), len(rows) + 1
    tbl_w = cw
    _avail = body_bottom(prs, theme) - top
    row_h = max(0.42, min(1.05, _avail / max(nrow, 1)))
    _body_pt = 14 if row_h >= 0.9 else (13 if row_h >= 0.7 else 12)
    frame = s.shapes.add_table(nrow, ncol, Inches(cx), Inches(top),
                               Inches(tbl_w), Inches(row_h * nrow))
    table = frame.table
    widths = tb.get("widths")
    if widths:
        total = sum(widths)
        for i, ww in enumerate(widths):
            table.columns[i].width = Emu(int(Inches(tbl_w) * (ww / total)))
    for j, htext in enumerate(header):
        cell = table.cell(0, j)
        cell.text = ""
        p = cell.text_frame.paragraphs[0]
        r = p.add_run()
        r.text = str(htext)
        set_font(r, theme["major"], 13, True, "FFFFFF")
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor.from_string(theme["accent"])
        cell.margin_left = Inches(0.08)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            cell = table.cell(i, j)
            cell.text = ""
            p = cell.text_frame.paragraphs[0]
            r = p.add_run()
            r.text = str(val)
            set_font(r, theme["minor"], _body_pt, False, theme["text"])
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string(
                "FFFFFF" if i % 2 else tint(theme["accent"], 0.96))
            cell.margin_left = Inches(0.08)
            cell.margin_top = Inches(0.03)
            cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    return s


def slide_figure(prs, spec, theme, meta):
    s = new_content_slide(prs, theme)
    w = prs.slide_width / 914400.0
    h = prs.slide_height / 914400.0
    top = draw_head(s, prs, spec, theme)
    cx, cw = content_box(prs, theme)
    img = spec.get("image")
    caption_h = 0.55 if spec.get("caption") else 0.35
    area_h = body_bottom(prs, theme) - top - caption_h
    if img and os.path.exists(img):
        from PIL import Image
        iw, ih = Image.open(img).size
        box_w, box_h = cw, area_h
        scale = min(box_w / iw, box_h / ih)
        dw, dh = iw * scale, ih * scale
        s.shapes.add_picture(img, Inches(cx + (box_w - dw) / 2), Inches(top + (box_h - dh) / 2),
                             Inches(dw), Inches(dh))
    else:
        add_rect(s, cx, top, cw, area_h, "F7F7F7", "D0D0D0", 1.0)
        add_text(s, cx + 0.5, top + area_h / 2 - 0.4, cw - 1.0, 0.8,
                 spec.get("placeholder", "（此处放图：按 storyboard 的 figure 注记补图）"),
                 14, theme["muted"], False, align=PP_ALIGN.CENTER, font=theme["minor"])
    if spec.get("caption"):
        add_text(s, cx, top + area_h + 0.08, cw, 0.4, spec["caption"], 12,
                 theme["muted"], False, font=theme["minor"])
    return s


def slide_summary(prs, spec, theme, meta):
    s = new_content_slide(prs, theme)
    w = prs.slide_width / 914400.0
    h = prs.slide_height / 914400.0
    top = draw_head(s, prs, spec, theme)
    cx, cw = content_box(prs, theme)
    cards = spec.get("cards", [])
    n = max(1, len(cards))
    gap = 0.3
    # 4 张卡横排会把每卡压到 2 英寸，中文竖着折成一列。
    # 超过 3 张就改两行：卡片变宽，字才读得下去。
    nrow = 1 if n <= 3 else 2
    ncol = (n + nrow - 1) // nrow
    card_w = (cw - gap * (ncol - 1)) / ncol
    # 结论句要占一行，先把它从可用高度里扣掉，否则卡片会把结论挤到框外
    take_h = 0.62 if spec.get("takeaway") else 0.0
    avail = body_bottom(prs, theme) - top - take_h

    def _need(card):
        """按卡片文字的行数估高度。不估就会拉满可用区，两行字的卡片下半全是白。"""
        cpl = max(1.0, (card_w - 0.8) * 72.0 / 16.0)
        lines = sum(max(1, math.ceil(text_width_units(seg) / cpl))
                    for seg in str(card.get("text") or "").split("\n"))
        return 0.55 + 0.42 + lines * 16 * 1.3 * 1.3 / 72.0

    need = max([_need(c) for c in cards] or [1.9])
    if nrow == 1:
        # 单行同样按内容给：三张两行字的卡片撑到上限 3.4 in，底部会空掉半页
        ch = min(avail, max(1.9, min(3.4, need)))
        # 卡片在可用区里居中：贴顶会留下「卡片悬着、结论在底部」的大段空隙
        top0 = top + max(0.0, (avail - ch) * 0.42)
    else:
        # 底部留 0.12 in 余量：留满会让第二排卡片底边紧贴内容框，看着像压出去了
        ch = min((avail - gap - 0.12) / 2, max(1.6, need))
        top0 = top + max(0.0, (avail - (ch * nrow + gap)) * 0.3)
    card_bg = tint(theme["accent"], 0.84)
    for i, card in enumerate(cards):
        r, c = divmod(i, ncol)
        x = cx + c * (card_w + gap)
        top_i = top0 + r * (ch + gap)
        add_rect(s, x, top_i, card_w, ch, card_bg)
        add_rect(s, x, top_i, 0.07, ch, theme["accent"])
        head_h = 0.55
        add_text(s, x + 0.3, top_i + 0.18, card_w - 0.55, 0.5, str(card.get("n", i + 1)),
                 26, theme["accent"], True, font=theme["major"])
        card_h = ch - head_h - 0.3
        csize = fit_block([card.get("text", "")], card_w - 0.8, card_h, 16, 11,
                          line_factor=1.55, gap_ratio=0)
        add_text(s, x + 0.3, top_i + head_h + 0.1, card_w - 0.6, card_h, card.get("text", ""),
                 csize, theme["text"], False, font=theme["minor"], line_spacing=1.3)
    if spec.get("takeaway"):
        # 收束页也该有结论句：卡片本身只给名词，判断句要单独一行
        add_text(s, cx, body_bottom(prs, theme) - 0.42, cw, 0.4,
                 spec["takeaway"], 13, theme["accent"], True, font=theme["minor"])
    return s


def slide_quote(prs, spec, theme, meta):
    w = prs.slide_width / 914400.0
    h = prs.slide_height / 914400.0
    prof = theme.get("_profile")
    if prof:
        # 有教师画像时，引文页必须活在内容框里。原来无条件铺封面底图，
        # 结果整页变成深蓝花纹封面：正文压在齿轮和光环上看不清，出处撞在最后一行上，
        # 页头的章节标签也丢了——一页引文在整份课件里最不该长得跟封面一样。
        s = new_content_slide(prs, theme)
        top = draw_head(s, prs, spec, theme)
        cx, cw = content_box(prs, theme)
        bottom = body_bottom(prs, theme)
        add_text(s, cx, top - 0.12, 0.9, 0.9, "“", 56, theme["accent"], True, font="Georgia")
        box_h = bottom - top - 0.95
        size = fit_size(spec["text"], cw - 1.0, box_h, 30, 16, 1.45)
        add_text(s, cx + 0.8, top + 0.1, cw - 0.8, box_h, spec["text"], size,
                 theme["text"], False, font=theme["major"], line_spacing=1.45)
        if spec.get("source"):
            add_text(s, cx + 0.8, bottom - 0.42, cw - 0.8, 0.4, "—— " + spec["source"],
                     13, theme["muted"], False, font=theme["minor"])
        return s

    s = new_content_slide(prs, theme)
    cx, cw = content_box(prs, theme)
    on_bg = paint_bg(s, prs, theme, "cover")
    fg = "FFFFFF" if on_bg else theme["text"]
    add_text(s, cx, 1.35, 1.0, 1.0, "“", 72, theme["accent"], True, font="Georgia")
    size = fit_size(spec["text"], cw - 0.6, 2.6, 34, 18, 1.35)
    add_text(s, cx + 0.6, 1.95, cw - 0.6, 2.6, spec["text"], size, fg, False,
             font=theme["major"], line_spacing=1.35)
    if spec.get("source"):
        add_text(s, cx + 0.6, h - 1.55, cw - 0.6, 0.4, "—— " + spec["source"], 13,
                 "D8E6F2" if on_bg else theme["muted"], False, font=theme["minor"])
    return s


def slide_end(prs, spec, theme, meta):
    prof = theme.get("_profile")
    if prof:
        s = prs.slides.add_slide(prs.slide_layouts[profile_layout_index(prs, prof)])
    else:
        s = prs.slides.add_slide(prs.slide_layouts[pick_layout(prs, "cover")])
    kill_placeholders(s, keep_title=False)
    w = prs.slide_width / 914400.0
    h = prs.slide_height / 914400.0
    if not paint_bg(s, prs, theme, "end"):
        add_rect(s, 0, 0, w, h, theme["accent"])
    # 教师封底是 54pt 居中「谢 谢 观 看」，这里跟齐
    end_pt = 40
    if prof:
        for lay in (prof.get("end") or {}).get("layers") or []:
            if lay.get("size") and lay["size"] >= 30:
                end_pt = lay["size"]
                break
    add_text(s, 0.9, h / 2 - 0.85, w - 1.8, 1.0, spec.get("title", "谢 谢 观 看"),
             end_pt, "FFFFFF", True, align=PP_ALIGN.CENTER, font=theme["major"])
    if spec.get("subtitle"):
        add_text(s, 0.9, h / 2 + 0.25, w - 1.8, 0.6, spec["subtitle"], 16, "E8EEF6", False,
                 align=PP_ALIGN.CENTER, font=theme["minor"])
    return s


def slide_spine(prs, spec, theme, meta):
    """记忆主干页：一条能背下来的链，配一句口诀。

    课件里"要记住的东西"通常散在十几页要点里，学生课后想不起来哪几条是一组。
    这一页只做一件事：把 3–5 个环节串成一条线，下面压一句口诀。
    检测报告只看结构（节点数、有没有口诀），串得对不对是备课的事。
    """
    from pptx.enum.shapes import MSO_SHAPE
    s = new_content_slide(prs, theme)
    top = draw_head(s, prs, spec, theme)
    cx, cw = content_box(prs, theme)
    add_line(s, 0.9, top - 0.12, 1.1, theme["accent"], 3)
    nodes = spec.get("nodes") or []
    n = max(1, len(nodes))
    gap = 0.30 if n >= 4 else 0.42
    box_w = max(1.15, (cw - gap * (n - 1)) / n)
    # 盒子加高到 1.55、口诀条 0.78：原先 1.34+0.66 的块在正文区居中之后，
    # 上下各空一大条，整页像没铺满。加高不挤字，只是把留白还给块本身。
    box_h = 1.55
    bottom = body_bottom(prs, theme)
    mnem = str(spec.get("mnemonic") or "").strip()
    bar_h = 0.78 if mnem else 0.0
    # 整块（盒子 + 口诀条）垂直居中：只按盒子居中会让口诀条压到下半页，
    # 盒子上面却空一大条
    block_h = box_h + (0.42 + bar_h if mnem else 0)
    y = top + max(0.05, (bottom - top - block_h) / 2)
    for i, nd in enumerate(nodes):
        x = cx + i * (box_w + gap)
        label = str(nd.get("label") or "")
        sub = str(nd.get("sub") or "")
        add_rect(s, x, y, box_w, box_h,
                 theme["accent_light"] if i % 2 == 0 else "F4F6F8", rounded=0.10)
        add_text(s, x + 0.16, y + 0.10, box_w - 0.32, 0.26, str(i + 1),
                 12, theme["accent"], True, font=theme["major"])
        add_text(s, x + 0.14, y + 0.38, box_w - 0.28, 0.46, label, 16,
                 theme["text"], True, align=PP_ALIGN.CENTER, font=theme["major"],
                 line_spacing=1.05)
        if sub:
            add_text(s, x + 0.14, y + 0.98, box_w - 0.28, 0.42, sub, 11,
                     theme["muted"], False, align=PP_ALIGN.CENTER, font=theme["minor"],
                     line_spacing=1.1)
        if i:                       # 箭头画在两个盒子之间，不压盒角
            ar = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x - gap + 0.055),
                                    Inches(y + box_h / 2 - 0.075),
                                    Inches(gap - 0.11), Inches(0.15))
            ar.fill.solid()
            ar.fill.fore_color.rgb = RGBColor.from_string(theme["accent"])
            ar.line.fill.background()
            ar.shadow.inherit = False
    if mnem:
        by = y + box_h + 0.42
        add_rect(s, cx, by, cw, bar_h, theme["accent_light"], rounded=0.24)
        add_text(s, cx + 0.2, by + 0.20, cw - 0.4, bar_h - 0.24,
                 f"口诀｜{mnem}", 15, theme["accent"], True,
                 align=PP_ALIGN.CENTER, font=theme["major"])
    return s


def slide_recall(prs, spec, theme, meta):
    """回问页：讲到一半停下来问，先让人自己想，再给答案。

    这是「间隔复现」唯一能落进 PPT 的形式。没有这一页，一节课就是连续投喂，
    学生全程没有一处需要自己回想——下了课自然记不住。
    """
    s = new_content_slide(prs, theme)
    # 页头只留章节标签：这句话本身就是全页主角，画进卡片里，
    # 再在页头用同一句当标题就成了上下各一遍
    head_spec = dict(spec)
    head_spec["title"] = ""
    top = draw_head(s, prs, head_spec, theme)
    cx, cw = content_box(prs, theme)
    # 不画标题下那道短横线：这页没有标题，横线会悬在空处
    bottom = body_bottom(prs, theme)
    answer = str(spec.get("answer") or "").strip()
    hint = str(spec.get("hint") or "").strip()
    # 卡片不拉满正文区。之前 card_h = bottom - top - 1.0 会让卡片吃掉整页，
    # 提示被挤到底边、答案紧贴卡片下沿，看起来像"文字掉出卡片"。
    # 现在按内容给固定高度，整块（卡片 + 答案）在正文区垂直居中，
    # 卡片上下都有呼吸，答案独立成一段。
    avail = bottom - top
    card_h = min(3.30, max(2.40, avail * 0.62))
    ans_h = 0.86 if answer else 0.0
    block_h = card_h + (0.34 + ans_h if answer else 0.0)
    y = top + max(0.06, (avail - block_h) / 2)
    add_rect(s, cx, y, cw, card_h, theme["accent_light"], rounded=0.06)
    # 提问在卡片里占中上位置，把底部 0.7 留给提示，避免两者贴在一起
    add_text(s, cx + 0.45, y + 0.12, cw - 0.9, card_h - 0.78,
             str(spec.get("title") or ""), 25, theme["text"], True,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
             font=theme["major"], line_spacing=1.3)
    if hint:
        add_text(s, cx + 0.45, y + card_h - 0.62, cw - 0.9, 0.3, hint, 12,
                 theme["muted"], False, align=PP_ALIGN.CENTER, font=theme["minor"])
    if answer:
        add_line(s, cx, y + card_h + 0.26, cw, "D9D9D9", 1.0)
        add_text(s, cx, y + card_h + 0.38, 0.9, 0.3, "答案", 12, theme["accent"], True,
                 font=theme["major"])
        add_text(s, cx + 0.72, y + card_h + 0.36, cw - 0.72, 0.62, answer, 15,
                 theme["muted"], False, font=theme["minor"], line_spacing=1.2)
    return s


BUILDERS = {
    "cover": slide_cover,
    "section": slide_section,
    "bullets": slide_bullets,
    "twocol": slide_twocol,
    "table": slide_table,
    "figure": slide_figure,
    "summary": slide_summary,
    "quote": slide_quote,
    "spine": slide_spine,
    "recall": slide_recall,
    "end": slide_end,
}


# ---------- 主流程 ----------

def _resolve_images(sb, sb_path):
    """把 image 字段解析成绝对路径，相对故事板文件所在目录。

    原先直接用 os.path.exists(img) 判，等于按「当前工作目录」解析：
    在 out/ 里跑能找到 figs/xxx.png，回到项目根跑就全变成灰框占位，
    而 check 报的是「没跑 make_figures.py」——把环境问题说成了缺图。
    顺序：原样 → 相对故事板目录 → 同目录同名 → 同目录 figs/ 下同名。
    """
    base = os.path.dirname(os.path.abspath(sb_path))
    for sp in sb.get("slides", []):
        img = str(sp.get("image") or "").strip()
        if not img:
            continue
        name = os.path.basename(img)
        for cand in (img, os.path.join(base, img), os.path.join(base, name),
                     os.path.join(base, "figs", name)):
            if os.path.exists(cand):
                sp["image"] = os.path.abspath(cand)
                break


def build(storyboard_path, out_path, template_path=None, do_check=False, mode=None,
          profile_path=None, strict=False):
    do_check = do_check or strict
    output_key = os.path.normcase(os.path.realpath(out_path))
    if output_key in {os.path.normcase(os.path.realpath(path))
                      for path in (storyboard_path, template_path or DEFAULT_TEMPLATE)}:
        raise ValueError("输出不能覆盖故事板或模板原件")
    with open(storyboard_path, encoding="utf-8") as f:
        sb = json.load(f)
    _resolve_images(sb, storyboard_path)
    meta = sb.get("meta", {})
    # 故事板自己声明的模式，用来跟命令行传进来的比对：两者不一致时产出会「标一种、实际另一种」
    declared = str(meta.get("mode") or "").strip().upper()[:1] or None
    mode_key = str(mode or meta.get("mode") or "B").strip().upper()[:1]
    if mode_key not in MODE_STYLE:
        sys.exit(f"[错误] 未知模式 {mode_key}：只支持 A（有课件·AI类）/ B（无课件·AI类）/"
                 f" C（有课件·非AI类）/ D（无课件·非AI类）")
    meta["_style"] = MODE_STYLE[mode_key]
    meta["_mode"] = mode_key
    slides = sb["slides"]

    tpl = template_path or DEFAULT_TEMPLATE
    if not os.path.exists(tpl):
        sys.exit(f"[错误] 模板不存在: {tpl}（请先运行 make_default_template.py）")

    prs = Presentation(tpl)
    theme = read_theme(prs)

    prof = None
    if profile_path:
        if not os.path.exists(profile_path):
            sys.exit(f"[错误] 找不到画像文件: {profile_path}（先跑 inspect_template.py）")
        prof = load_profile(profile_path)
        theme["_profile"] = prof
        # 配色/字体以画像为准：主题里的 accent1 常常跟教师实际用的填充色不一致
        pal = prof.get("palette") or {}
        if pal.get("accent"):
            theme["accent"] = pal["accent"]
        if pal.get("text"):
            theme["text"] = pal["text"]
        if pal.get("muted"):
            theme["muted"] = pal["muted"]
        if pal.get("bg"):
            theme["bg"] = pal["bg"]
        theme["accent_light"] = tint(theme["accent"], 0.90)
        # 字体按「教师实际渲染用的」取：主题里常写着 Calibri，中文实际回落成别的字体
        pf = prof.get("fonts") or {}
        if (prof.get("title") or {}).get("font"):
            theme["major"] = prof["title"]["font"]
        elif pf.get("major"):
            theme["major"] = pf["major"]
        if pf.get("body"):
            theme["minor"] = pf["body"]
        elif pf.get("minor"):
            theme["minor"] = pf["minor"]
        # 教师正文用的是第三套字体（标题体 vs 正文字体常不同），画像里没存就保持主题值
        dep = prof.get("density") or {}
        if dep.get("body_pt_median"):
            theme["body_pt"] = dep["body_pt_median"]
            # 正文上限 = 教师字号 ×1.35（投影比原件大一档好读），夹在模式区间内
            theme["body_max_cap"] = int(round(dep["body_pt_median"] * 1.35))
            # 页标题至少比正文大一档，避免层级反转
            theme["page_title_min"] = theme["body_max_cap"] + 5
        # 本机缺字体时只是预览回落，交付不受影响——一句话提示即可，不打断生成
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import font_check
            miss = [n for n, ok, _ in font_check.check_names(
                [theme["major"], theme["minor"]]) if not ok]
            if miss:
                print(f"[字体] 本机未安装 {'、'.join(miss)}：预览与渲染自检会用替代字体，"
                      f"文件里保留原字体名，教师机器上照常显示")
        except Exception:
            pass

    if meta.get("font"):
        theme["major"] = theme["minor"] = meta["font"]
    if meta.get("title_align"):
        theme["title_align"] = meta["title_align"]
    strip_slides(prs)

    body = [s for s in slides if s.get("type") not in ("cover", "end")]
    total = len(slides)
    idx = 0
    for spec in slides:
        idx += 1
        typ = spec.get("type", "bullets")
        fn = BUILDERS.get(typ)
        if fn is None:
            raise SystemExit(f"[错误] 未知页型: {typ}")
        slide = fn(prs, spec, theme, meta)
        if spec.get("note"):
            slide.notes_slide.notes_text_frame.text = spec["note"]
        # 教师模板的页脚挂在版式里（空占位符不出图），再自绘一条会重影
        has_own_footer = bool(prof and (prof.get("chrome") or {}).get("footer"))
        if typ not in ("cover", "end") and not has_own_footer:
            add_footer(slide, prs, idx, total, meta, theme)

    # 交付文件常常正被 PowerPoint 或预览面板打开着，直接存会抛 PermissionError。
    # 与其甩一屏 traceback，不如说清是哪个文件、怎么解决。
    try:
        prs.core_properties.author = prs.core_properties.last_modified_by = "课程组"
        prs.core_properties.comments = prs.core_properties.keywords = ""
        prs.save(out_path)
    except PermissionError:
        sys.exit(f"[错误] 写不进 {out_path}：文件正被其他程序占用（PowerPoint / 预览面板）。\n"
                 f"       关掉它再跑，或先输出到另一个文件名。")
    print(f"[ok] 已生成 {out_path}｜{total} 页｜模式={meta['_mode']} "
          f"{meta['_style']['name']}｜模板={os.path.basename(tpl)}"
          f"{'｜画像=' + os.path.basename(profile_path) if profile_path else ''}｜"
          f"字体={theme['major']}｜主色=#{theme['accent']}")
    if do_check:
        issues = check(out_path, slides, meta["_style"], profile=prof,
                       mode=meta["_mode"], declared_mode=declared, extra={"sb": sb})
        # 页数达标 ≠ 内容覆盖。结构性检查过了但知识点漏了一半，是返工成本最高的一种，
        # 所以在同一条 --check 里顺带跑覆盖度，不给"忘了单独跑一次"留口子。
        leak = 0
        if sb.get("coverage"):
            print("")
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                import coverage_check
                rep = coverage_check.check(storyboard_path, out_path, quiet=True, strict=True)
                leak = 1 if rep else 0
            except Exception as exc:            # 覆盖度出问题不该让成品生成失败
                print(f"[覆盖度] 检查未能完成：{exc}")
                leak = 1
        else:
            print("\n[覆盖度] 故事板没有 coverage 数组，跳过覆盖检查——"
                  "这一步跳过就不知道有没有讲漏，建议补上知识点清单再跑。")
        # --strict 给脚本/CI 用：有问题就非 0 退出，别靠人眼盯屏幕
        if strict and (issues or leak):
            sys.exit(f"[自检] --strict：{len(issues)} 条结构问题、{leak} 个知识点漏讲，"
                     f"退出码 1")
    return out_path


# ---------------- 页型硬规则 ----------------
# SKILL.md 的页型表写着「行数 ≤6、列数 ≤5、quote 必须有出处」。这些约束如果只写在
# 文档里、不进 check()，故事板写得再合规也只是「声明合规」：实测中 7 行 6 列的表格、
# 6 张卡的 summary、没出处的引用，全都静默通过——那等于自检是摆设。
#
# 长度一律按**显示宽度**算（中文 1.0、ASCII 0.55），不按字符数：一条 softmax 公式
# 有 40 多个字符，渲染出来是一行短式；用字符数判会把公式页全部打回，逼人删公式。
LIMITS = {
    "table_rows": 6,
    "table_cols": 5,
    "table_cell": 16,       # 宽度单位 ≈ 16 个汉字
    "cards": 4,
    "point_width": 40,      # ≈ 40 个汉字，或 70 个西文字符
    "twocol_item_width": 30,
    "card_width": 34,       # 三列卡片每列约 3 英寸，34 正好两行
}

# C/D 是降深版：概念名可以出现（"激活函数的作用"是合法的通识页标题），
# 但推导符号和公式表达式不行——那说明只是把专业版换了字体，没换解释路径。
# 第三列是类别：formula 类的「额度」按模式不同（C 最多 2 页，D 零页），
# term 类照报，但「链式法则」只在 D 里算越界——它是教师课件里的正式知识点，
# C 档要求沿用教师术语，禁掉就等于逼着删知识点。
DEPTH_COMMON = [
    (re.compile(r"[∂∇∫]|\\frac|\\partial"), "数学推导符号", "formula"),
    (re.compile(r"Σ[_^]|[\wθ]_\{[^{}]+\}"), "公式下标/求和式", "formula"),
    (re.compile(r"偏导数|雅可比矩阵|矩阵求导|收敛性证明|推导过程"), "推导术语", "term"),
]
DEPTH_D_ONLY = [
    (re.compile(r"链式法则"), "推导术语", "term"),
]
# 只认「真的画出来了式子」，用来数 C 档的公式额度
FORMULA_RE = re.compile(r"Σ[_^]|[\wθ]_\{[^{}]+\}|[∂∇∫]|\\frac")


def _depth_rules(mode_key):
    return DEPTH_COMMON + (DEPTH_D_ONLY if mode_key == "D" else [])


def _walk_text(obj, skip=("image", "note", "placeholder")):
    """把故事板某页里所有该显示给人看的字符串摊平，用于术语与字数检查。"""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in skip:
                continue
            yield from _walk_text(v, skip)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_text(v, skip)


def page_type_issues(sp, i, style):
    """逐页查页型硬规则。只报能改的问题，不报风格偏好。"""
    out = []
    t = sp.get("type", "bullets")
    pts = sp.get("points") or []
    # 只有 bullets / summary 会画结论句。别的页型写了 takeaway 就是白写：
    # 生成时被静默丢掉，人还以为「我写了结论」，投影时却找不到。
    if sp.get("takeaway") and t not in ("bullets", "summary"):
        out.append(f"第 {i} 页是 {t} 页却写了 takeaway：该页型不画结论句，"
                   f"这句会被丢掉，改成 bullets 页或删掉")
    if t == "bullets":
        if not pts:
            out.append(f"第 {i} 页是要点页但 points 为空")
        for p in pts:
            if text_width_units(str(p)) > LIMITS["point_width"]:
                out.append(f"第 {i} 页有要点约 {text_width_units(str(p)):.0f} 字宽，"
                           f"超过 {LIMITS['point_width']}：拆成两条，"
                           f"或把第二句挪进 note 当讲稿")
                break
    elif t == "table":
        tb = sp.get("table") or {}
        header, rows = tb.get("header") or [], tb.get("rows") or []
        if not header or not rows:
            out.append(f"第 {i} 页 table 缺 header 或 rows，会渲染成空表")
        if len(header) > LIMITS["table_cols"]:
            out.append(f"第 {i} 页表格 {len(header)} 列，超过 {LIMITS['table_cols']} 列："
                       f"每列不足 1.6 英寸，中文会挤成一字一行")
        if len(rows) > LIMITS["table_rows"]:
            out.append(f"第 {i} 页表格 {len(rows)} 行，超过 {LIMITS['table_rows']} 行："
                       f"拆成两张，或只留要对照的那几行")
        for r, row in enumerate(rows, 1):
            if header and len(row) != len(header):
                out.append(f"第 {i} 页表格第 {r} 行 {len(row)} 格，与表头 {len(header)} 列不符")
                break
            over = next(((c, v) for c, v in enumerate(row, 1)
                         if text_width_units(str(v)) > LIMITS["table_cell"]), None)
            if over:
                out.append(f"第 {i} 页表格第 {r} 行第 {over[0]} 格约 "
                           f"{text_width_units(str(over[1])):.0f} 字宽，"
                           f"超过 {LIMITS['table_cell']}：表格只放短标签，整句挪到正文")
                break
    elif t == "summary":
        cards = sp.get("cards") or []
        if not cards:
            out.append(f"第 {i} 页 summary 没有 cards")
        elif len(cards) > LIMITS["cards"]:
            out.append(f"第 {i} 页 {len(cards)} 张卡片，超过 {LIMITS['cards']} 张："
                       f"小结只收束 3–4 条，多了学生一条都记不住")
        for c in cards:
            txt = str(c.get("text") or "")
            if text_width_units(txt) > LIMITS["card_width"] and "\n" not in txt:
                out.append(f"第 {i} 页有卡片约 {text_width_units(txt):.0f} 字宽且没用 \\n 断行："
                           f"窄卡片自然折行会把「、」「，」甩到行首")
                break
    elif t == "spine":
        nodes = sp.get("nodes") or []
        if len(nodes) < 3:
            out.append(f"第 {i} 页记忆主干只有 {len(nodes)} 个节点：少于 3 个串不成链，"
                       f"退回要点页即可")
        elif len(nodes) > 5:
            out.append(f"第 {i} 页记忆主干 {len(nodes)} 个节点，超过 5 个："
                       f"一条线最多五步，再长就得分两条")
        for nd in nodes:
            lb = str(nd.get("label") or "")
            if text_width_units(lb) > 9:
                out.append(f"第 {i} 页节点「{lb}」约 {text_width_units(lb):.0f} 字宽，"
                           f"框里会折成两行——节点只放名字，解释写 sub")
                break
        if not str(sp.get("mnemonic") or "").strip():
            out.append(f"第 {i} 页 spine 没写 mnemonic：这条线很好，但没给一句能背下来的话，"
                       f"它就是一张流程图")
    elif t == "recall":
        if not str(sp.get("answer") or "").strip():
            out.append(f"第 {i} 页回问没有 answer：问了不揭晓，学生记住的是自己的错答案")
        if text_width_units(str(sp.get("title") or "")) > 30:
            out.append(f"第 {i} 页回问 {text_width_units(str(sp.get('title'))):.0f} 字宽："
                       f"投影上超过两行就不像一句话了")
    elif t == "quote":
        if not str(sp.get("text") or "").strip():
            out.append(f"第 {i} 页引用页没有 text")
        if not str(sp.get("source") or "").strip():
            out.append(f"第 {i} 页引用没有 source：原话必须能追到出处，"
                       f"否则学生记下的是一句没来由的话")
    elif t == "twocol":
        L, R = sp.get("left") or {}, sp.get("right") or {}
        for name, col in (("左", L), ("右", R)):
            if not str(col.get("head") or "").strip():
                out.append(f"第 {i} 页{name}列没有列头：两列得是同一维度才叫对照")
            items = col.get("items") or []
            if not items:
                out.append(f"第 {i} 页{name}列没有条目")
            for x in items:
                if text_width_units(str(x)) > LIMITS["twocol_item_width"]:
                    out.append(f"第 {i} 页{name}列有条目约 "
                               f"{text_width_units(str(x)):.0f} 字宽，超过 "
                               f"{LIMITS['twocol_item_width']}：半栏宽放不下，会折成三行")
                    break
        dl, dr = len(L.get("items") or []), len(R.get("items") or [])
        if abs(dl - dr) >= 3:
            out.append(f"第 {i} 页两列条目数差 {abs(dl - dr)} 条（{dl} vs {dr}），"
                       f"对照关系看不出来——补平，或改成要点页")
    elif t == "figure":
        if not str(sp.get("caption") or "").strip():
            out.append(f"第 {i} 页图页没有 caption：图注要写清读图顺序和「示意/实测」，"
                       f"不然学生盯着图不知道该看哪儿")
    return out


def depth_issues(sp, i, mode_key, allow_formula=False):
    """C/D 模式混入推导符号，说明只是换了字体没换讲法。

    公式类受额度限制（见 FORMULA_RE 与 check 里的 allowed_formula），
    术语类不看额度——它跟页数无关，出现就是没降深。
    """
    if mode_key not in ("C", "D"):
        return []
    hit = []
    for txt in _walk_text(sp):
        for rx, label, kind in _depth_rules(mode_key):
            if kind == "formula" and allow_formula:
                continue
            m = rx.search(txt)
            if m:
                hit.append((label, m.group(0)))
                break
        if hit:
            break
    if not hit:
        return []
    label, frag = hit[0]
    return [f"第 {i} 页出现{label}「{frag}」：{mode_key} 是降深版，"
            f"概念名可以留、推导要去掉（换类比或直接给结论）"]


def check(path, specs, style=None, profile=None, mode=None, declared_mode=None, extra=None):
    """结构性自检：页数、空页、文字量、页型硬规则、裸下标、以及「是否真的贴上了教师版式」。

    extra 带故事板里非页面的部分（memory / coverage / terms）：
    记忆骨架和术语白名单不在任何一页里，但少了它们，页面看着完全正常。
    """
    extra = extra or {}
    style = style or MODE_STYLE["B"]
    mode = str(mode or "B").strip().upper()[:1]
    prs = Presentation(path)
    issues = []
    h_in = prs.slide_height / 914400.0
    if len(prs.slides) != len(specs):
        issues.append(f"页数不符：{len(prs.slides)} vs 计划 {len(specs)}")
    for i, s in enumerate(prs.slides, 1):
        chars = 0
        has_pic = False
        for shp in s.shapes:
            if shp.has_text_frame:
                # 页脚区的文字不计入承载量：模板页脚长度与内容多少无关
                if shp.top is not None and shp.top / 914400.0 > h_in - 0.7:
                    continue
                txt = shp.text_frame.text.strip()
                chars += len(txt)
                # 裸下标：故事板里写 o_j 而不是 o_{j}，上下标语法没生效，屏幕上就是字面下划线，
                # 学生会读成代码变量名。这类错误渲染检查时最容易漏，机器查最省事。
                m = BARE_SCRIPT_RE.search(txt)
                if m:
                    issues.append(f"第 {i} 页出现裸上下标「{m.group(0)}」："
                                  f"要写成 {m.group(1)}_{{{m.group(2)}}} 才会变成真下标")
            if shp.shape_type == 13:
                has_pic = True
        # 封面/分段/引用/收尾页本来就字少，拿"字数下限"去要求它们只会制造噪音
        typ_i = str(specs[i - 1].get("type", "")) if i - 1 < len(specs) else ""
        if chars < 10 and not has_pic and typ_i not in ("cover", "section", "quote", "end"):
            issues.append(f"第 {i} 页几乎无内容（{chars} 字）")
        if chars > style["max_chars"]:
            issues.append(f"第 {i} 页文字 {chars} 字，超出本模式承载"
                          f"（{style['name']} 建议 ≤{style['max_chars']}）")
    pg = style.get("pages")
    # 区间衡量的是「讲授页」，只把 spine / recall 排除在外：这两类每页 30–60 秒
    # （指一条线、问一句揭晓一句），不占内容铺陈的时间。
    # 不排除 cover/end/section：它们照样占课时，算进总量才反映真实节奏。
    # 若按总页数判，同一份内容加了记忆骨架反而被判「页数超标」——
    # 而那条提示的原意是「内容没铺满」，正好相反。
    if pg:
        teach = [s for s in specs if str(s.get("type")) not in ("spine", "recall")]
        if not (pg[0] <= len(teach) <= pg[1]):
            issues.append(f"讲授页 {len(teach)} 页（总 {len(specs)} 页，另含 "
                          f"{len(specs) - len(teach)} 页主干/回问）不在本模式建议区间 "
                          f"{pg[0]}–{pg[1]}（{style['name']}）：内容没铺满，或课时与页数不匹配，"
                          f"先核知识点清单")
    # C 档允许最多 2 页带式子（depth-modes.md：只留 1–2 个式子，讲含义不推导），
    # D 档一个都不留。额度按页算，不看出现次数：一页里写了三行式子，仍算一页。
    formula_pages = [i for i, sp in enumerate(specs, 1)
                     if FORMULA_RE.search("".join(_walk_text(sp)))]
    allowed_formula = set(formula_pages[:2]) if mode == "C" else set()
    for i, sp in enumerate(specs, 1):
        if sp.get("type") == "figure":
            img = sp.get("image")
            if not img or not os.path.exists(img):
                issues.append(f"第 {i} 页是图页但没有可用图片（{img or '未填 image'}），"
                              f"会渲染成灰框占位：先跑 scripts/make_figures.py 或换成本地图片")
        pts = sp.get("points") or []
        if len(pts) > style["max_points"]:
            issues.append(f"第 {i} 页要点 {len(pts)} 条，超出本模式上限 "
                          f"{style['max_points']} 条（{style['name']} 应拆页而非缩字号）")
        title = str(sp.get("title") or "")
        # 回问页的标题就是那句提问，本来就长；它另有 30 字宽的单独上限
        if text_width_units(title) > 26 and sp.get("type") != "recall":
            issues.append(f"第 {i} 页标题约{text_width_units(title):.0f}字宽，建议拆分或调整布局：{title[:16]}…")
        issues.extend(page_type_issues(sp, i, style))
        if ((extra.get("sb") or {}).get("meta") or {}).get("enforce_depth_preset"):
            issues.extend(depth_issues(sp, i, mode, allow_formula=i in allowed_formula))

    # ---- 全片结构：封面/收尾/分段页的数量关系
    types = [str(s.get("type", "bullets")) for s in specs]
    if types and types[0] != "cover":
        issues.append("第一页不是 cover：课件开头得有标题页，投影时才知道这一讲是什么")
    if types and types[-1] != "end":
        issues.append("最后一页不是 end：缺收尾页，学生会以为还没讲完")
    if types.count("section") == 1:
        issues.append("全片只有 1 张 section 分段页：多这一页只多一次翻页，"
                      "内容直接接在上一页更顺（段数 ≥4 才值得用分段页）")
    if types and types[0] == "cover":
        ct = str(specs[0].get("title") or "")
        # A/C 照着教师课件做，教师封面本来就写「第X章 课程名」，改掉反而不像原件。
        # 这条只该管 B/D 自己攒的封面：那类封面只写章节号，等于没交代这一讲讲什么。
        if mode not in ("A", "C") and re.search(r"第[一二三四五六七八九十\d]+[章单元讲课节次]", ct):
            issues.append(f"封面标题写的是章节号「{ct[:12]}」：标题该写这一讲的核心判断，"
                          f"章节号放 kicker 或 subtitle")

    # ---- 模式冲突：故事板声明一个、命令行给另一个，产出的深度会跟标签对不上。
    # 这种错不报错、看着完全正常，是最该拦的一类。
    if declared_mode and declared_mode != mode:
        issues.append(f"故事板写的是 mode={declared_mode}，本次按 --mode {mode} 生成："
                      f"要点数/字号/页数区间用的是 {mode} 的规则。"
                      f"「标着通识版、实际专业版深度」是最难被发现的一种错，确认是不是本意")
    # ---- 记忆骨架：这一讲「要背下来的那条线」有没有落进文件
    # 页面全绿但学生记不住，是课件最常见也最难被发现的失败：它不报错，
    # 只是上完课没人说得出来讲了什么。所以 memory 段和工作量一样要查。
    _sb = extra.get("sb") or {}
    mem = extra.get("memory") or _sb.get("memory") or {}
    cov = extra.get("coverage") or _sb.get("coverage") or []
    if not mem and (_sb.get("meta") or {}).get("require_memory"):
        issues.append("故事板没有 memory 段（本讲的记忆主干、口诀、锚点）："
                      "页面上就不会出现 spine 页，学生课后没有可背的抓手")
    elif mem:
        spine_names = [str(x) for x in (mem.get("spine") or [])]
        if len(spine_names) < 2:
            issues.append("memory.spine 少于 2 环：这一讲讲完之后，学生该能一口气说出的"
                          "那条线还没定下来")
        if not str(mem.get("mnemonic") or "").strip():
            issues.append("memory.mnemonic 为空：知识点要靠一句顺口的话挂住，"
                          "没有口诀就只剩十几页要点")
        anchors = mem.get("anchors") or []
        need = min(3, max(1, len(cov) // 3)) if cov else 2
        if len(anchors) < need:
            issues.append(f"memory.anchors 只有 {len(anchors)} 条，本讲至少要 {need} 条："
                          f"锚点是「这个抽象概念对应生活里哪件事」，没有它就只能死记")
        has_spine = any(str(s.get("type")) == "spine" for s in specs)
        if spine_names and not has_spine:
            issues.append("写了 memory.spine 却没有 spine 页：记忆主干留在 json 里，"
                          "投影上学生看不到")

    # ---- 间隔复现：讲 20 分钟不停下来问一次，前面讲的会被后面的冲掉
    if len(specs) >= 14 and (_sb.get("meta") or {}).get("require_recall"):
        rp = [i for i, s in enumerate(specs, 1) if str(s.get("type")) == "recall"]
        if not rp:
            issues.append("全片没有 recall 回问页：一节课从头投喂到尾，"
                          "学生没有一处需要自己回想——每 6–8 页该停一次")
        else:
            marks = [1] + rp + [len(specs)]
            gap = max(b - a for a, b in zip(marks, marks[1:]))
            if gap > 8:
                issues.append(f"最长 {gap} 页没有回问（上限 8 页）："
                              f"这一段学生只是在看，没有在想")

    # ---- 去 AI 味：文案层面的模板腔，逐页可定位
    # 规则表在 voice_check.py。放在这里是因为「文档里写、脚本不查」的约束等于没有：
    # 上一版页型规则也吃过这个亏。
    voice_notes = []
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import voice_check
        terms = extra.get("terms") or voice_check._terms_of(_sb)
        rep = voice_check.analyze(specs, terms)
        voice_notes = [h for h in rep["hits"] if h["level"] == "block"]
        print("")
        print(voice_check.report(rep, "本讲"))
        voice_head = [f"第 {h['page'] or '全片'} 页 AI 味：{h['name']}"
                      f"「{h['frag']}」——{h['advice']}" for h in voice_notes[:6]]
    except Exception as exc:
        print(f"[去AI味] 检查未能完成：{exc}")
        voice_head = []

    # 版式专项在 AI 味之后、汇总之前跑完，最后一次性汇总，避免同一屏出现两个结论
    if (_sb.get("meta") or {}).get("enforce_voice"):
        issues = voice_head + issues

    # --- 画像专项：贴合教师版式才算 A/C 模式做完
    if profile:
        lay_name = (profile.get("meta") or {}).get("content_layout")
        body = profile.get("body") or [0, 1.4, 10, 4.0]
        body_bottom_y = body[1] + body[3]
        pill = profile.get("title") or {}
        overflow = []
        for i, sl in enumerate(prs.slides, 1):
            if sl.slide_layout.name != lay_name:
                continue
            for shp in sl.shapes:
                if shp.top is None or shp.height is None:
                    continue
                bottom = (shp.top + shp.height) / 914400.0
                if shp.has_text_frame and shp.text_frame.text.strip() and bottom > body_bottom_y + 0.25:
                    overflow.append(f"第 {i} 页有文字越过正文区下沿（{bottom:.2f} > {body_bottom_y:.2f}）")
        if overflow:
            issues.extend(overflow[:6])
        # 章节标签字数：超出圆角宽度会被挤成两行
        if pill.get("geom"):
            pw, psize = pill["geom"][2], pill.get("size") or 24
            cap = int((pw - 0.45) * 72.0 / psize / 1.05)
            for i, sp in enumerate(specs, 1):
                label = sp.get("section") or ""
                if label and len(label) > cap:
                    issues.append(f"第 {i} 页章节标签「{label}」{len(label)} 字，"
                                  f"超出标签宽度上限 {cap} 字，会被拆行")
                    break

    if issues:
        print(f"[自检] 发现问题 {len(issues)} 条：")
        for it in issues[:20]:
            print("   -", it)
        if len(issues) > 20:
            print(f"   …另有 {len(issues) - 20} 条，先修前 20 条再看")
    else:
        print("[自检] 结构检查通过：页数、页型、内容量、深度均无问题")
    return issues


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("out")
    ap.add_argument("--template", default=None)
    ap.add_argument("--mode", default=None,
                    help="A 有课件·AI类 / B 无课件·AI类 / C 有课件·非AI类 / D 无课件·非AI类")
    ap.add_argument("--profile", default=None,
                    help="版式画像 json（inspect_template.py 产出）。给教师模板时配套使用")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="自检发现问题时以退出码 1 结束（给批量跑和 CI 用）")
    args = ap.parse_args()
    if args.profile and not args.template:
        sys.exit("[错误] --profile 需要配合 --template 使用：底色/版式来自模板文件，"
                 "画像只提供几何与配色")
    build(args.storyboard, args.out, args.template, args.check, args.mode, args.profile,
          strict=args.strict)
