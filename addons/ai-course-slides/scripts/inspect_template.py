#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从真实课件里反推「版式画像」（profile.json），供 build_deck.py --profile 使用。

为什么需要它
------------
教师的 pptx 往往不是「占位符驱动」的：母版里塞一堆默认版式，实际讲课全用某一个空白版式，
标题是手画的圆角标签，装饰（背景图、角标、内容边框、横线）挂在版式里而不是母版里。
这种文件用 python-pptx 的占位符接口去套，只会得到「配色差不多、位置全靠猜」的结果。

本脚本读的是「教师实际怎么排」，输出结构化参数：

    python inspect_template.py 教师课件.pptx -o out/profile.json --assets out/tpl_assets

得到的东西
----------
  palette    主色/正文色/背景色（从主题 + 实际填充反解）
  chrome     版式里的全页背景图、角标、内容边框、标题下横线（连图片一起导出）
  title      章节标签：圆角标签的几何、填充、描边、字体字号字距
  page_title 页标题：位置、字号、字体（教师用它做本页主题，跟章节标签是两层）
  body       正文安全区（内容边框内缩，避开横线与页脚）
  cover/end  封面封底的全页背景图与文字层级
  density    教师每页字数与正文字号中位数——用来校准「一页该放多少」

拿到 profile 后：
    python build_deck.py storyboard.json out.pptx --template 教师课件.pptx --profile out/profile.json --mode A
"""
import argparse
import json
import os
import re
import statistics
from collections import Counter

from lxml import etree
import envcheck  # noqa: E402  同目录依赖自检，缺库时给人话
envcheck.ensure()

from pptx import Presentation

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"a": A}
E = 914400.0


# ---------------------------------------------------------------- 主题解析

def read_theme(prs):
    """解析主题配色与字体，并把 schemeClr 的名字映射成实际色值。"""
    palette = {"dk1": "000000", "lt1": "FFFFFF", "dk2": "44546A", "lt2": "E7E6E6",
               "accent1": "1F4E79", "accent2": "4472C4", "accent3": "A5A5A5",
               "accent4": "FFC000", "accent5": "5B9BD5", "accent6": "70AD47",
               "hlink": "0563C1", "folHlink": "954F72"}
    fonts = {"major": "微软雅黑", "minor": "微软雅黑"}
    for part in prs.part.package.iter_parts():
        if not str(part.partname).startswith("/ppt/theme/"):
            continue
        try:
            root = etree.fromstring(part.blob)
        except Exception:
            continue
        cs = root.find(".//a:clrScheme", NS)
        if cs is not None:
            for node in cs:
                tag = etree.QName(node).localname
                srgb = node.find("a:srgbClr", NS)
                sysc = node.find("a:sysClr", NS)
                if srgb is not None:
                    palette[tag] = srgb.get("val")
                elif sysc is not None:
                    palette[tag] = sysc.get("lastClr")
        for tag, key in (("majorFont", "major"), ("minorFont", "minor")):
            node = root.find(f".//a:{tag}", NS)
            if node is None:
                continue
            ea = node.find("a:ea", NS)
            latin = node.find("a:latin", NS)
            face = ""
            if ea is not None and ea.get("typeface"):
                face = ea.get("typeface")
            elif latin is not None and latin.get("typeface"):
                face = latin.get("typeface")
            if face and not face.startswith("+"):
                fonts[key] = face
        break
    # 别名：bg1/tx1/bg2/tx2 分别指向 lt1/dk1/lt2/dk2
    palette["bg1"] = palette["lt1"]
    palette["tx1"] = palette["dk1"]
    palette["bg2"] = palette["lt2"]
    palette["tx2"] = palette["dk2"]
    return palette, fonts


def resolve_color(fill_parent, palette):
    """从一个带 solidFill 的节点解出 #RRGGBB。支持 srgbClr 与 schemeClr。"""
    if fill_parent is None:
        return None
    sf = fill_parent.find("a:solidFill", NS)
    if sf is None:
        return None
    srgb = sf.find("a:srgbClr", NS)
    if srgb is not None:
        return srgb.get("val", "").upper()
    sch = sf.find("a:schemeClr", NS)
    if sch is not None:
        return (palette.get(sch.get("val")) or "").upper() or None
    return None


def shape_fill_hex(shape, palette):
    try:
        return resolve_color(shape._element.spPr, palette)
    except Exception:
        return None


def shape_line_hex(shape, palette):
    try:
        return resolve_color(shape._element.spPr.find("a:ln", NS), palette)
    except Exception:
        return None


def shape_line_width_pt(shape):
    try:
        w = shape._element.spPr.find("a:ln", NS).get("w")
        return round(int(w) / 12700.0, 2) if w else None
    except Exception:
        return None


# ---------------------------------------------------------------- 文本取样

def iter_text_shapes(slide):
    for sh in slide.shapes:
        if not sh.has_text_frame:
            continue
        t = sh.text_frame.text.strip()
        if t:
            yield sh, t


def shape_font(sh):
    """取该形状里「字数最多」的那个 run 的字体属性，避免被孤立符号带偏。"""
    best = None
    for para in sh.text_frame.paragraphs:
        for r in para.runs:
            if not r.text.strip():
                continue
            if best is None or len(r.text) > len(best[1]):
                best = (r, r.text)
    if best is None:
        return {}
    r = best[0]
    f = r.font
    color = None
    try:
        if f.color is not None and f.color.type is not None:
            color = str(f.color.rgb) if f.color.type == 1 else None
    except Exception:
        color = None
    spc = None
    try:
        rPr = r._r.find("a:rPr", NS)
        if rPr is not None and rPr.get("spc"):
            spc = int(rPr.get("spc"))
    except Exception:
        spc = None
    return {"font": f.name, "size": f.size.pt if f.size else None,
            "bold": f.bold, "color": color, "spc": spc}


def para_line_spacing(sh):
    try:
        pPr = sh.text_frame.paragraphs[0]._p.find("a:pPr", NS)
        if pPr is None:
            return None
        ln = pPr.find("a:lnSpc", NS)
        if ln is None:
            return None
        pct = ln.find("a:spcPct", NS)
        if pct is not None:
            return int(pct.get("val")) / 100000.0
    except Exception:
        pass
    return None


def para_align(sh):
    al = sh.text_frame.paragraphs[0].alignment
    if al is None:
        return None
    return str(al).split("(")[0].split(".")[-1].lower()


def text_chars(slide):
    n = 0
    for sh, t in iter_text_shapes(slide):
        n += len(re.sub(r"\s", "", t))
    return n


# ---------------------------------------------------------------- 聚类工具

def cluster(points, tol=0.35):
    """把 (x,y,...) 按距离聚类，返回 [[代表点, 成员列表], ...]，按成员数降序。"""
    clusters = []
    for p in points:
        for c in clusters:
            if abs(c[0][0] - p[0]) <= tol and abs(c[0][1] - p[1]) <= tol:
                c[1].append(p)
                break
        else:
            clusters.append([p, [p]])
    clusters.sort(key=lambda c: -len(c[1]))
    return clusters


def save_pic(shape, assets_dir, stem):
    if not assets_dir:
        return None
    try:
        im = shape.image
    except Exception:
        return None
    os.makedirs(assets_dir, exist_ok=True)
    fn = os.path.join(assets_dir, f"{stem}.{im.ext}")
    try:
        with open(fn, "wb") as f:
            f.write(im.blob)
    except Exception:
        return None
    return fn


# ---------------------------------------------------------------- 主提取

def inspect(path, assets_dir=None):
    prs = Presentation(path)
    PW = prs.slide_width / E
    PH = prs.slide_height / E
    palette, fonts = read_theme(prs)
    slides = list(prs.slides)
    body_slides = slides[1:-1] if len(slides) > 2 else slides

    out = {"meta": {"source": os.path.basename(path), "page_w": round(PW, 3),
                    "page_h": round(PH, 3), "slides": len(slides),
                    "ratio": round(PW / PH, 4)},
           "palette": {}, "fonts": fonts, "chrome": {},
           "title": None, "page_title": None, "body": None,
           "cover": {}, "end": {}, "density": {}, "warnings": []}

    # ---- 1. 正文页最常用的版式
    usage = Counter()
    for s in body_slides:
        try:
            usage[s.slide_layout.name] += 1
        except Exception:
            pass
    layout = None
    if usage:
        top_name = usage.most_common(1)[0][0]
        for lay in prs.slide_layouts:
            if lay.name == top_name:
                layout = lay
                break
    if layout is None and prs.slide_layouts:
        layout = prs.slide_layouts[0]
    out["meta"]["content_layout"] = layout.name if layout is not None else None
    out["meta"]["content_layout_usage"] = usage.most_common(3)

    # ---- 2. 版式里的装饰：全页背景图 / 角标 / 内容框 / 横线
    chrome = {"bg_image": None, "logo": None, "frame": None, "rule_y": None, "footer": False}
    if layout is not None:
        pics, rects, lines = [], [], []
        for sh in layout.shapes:
            try:
                area = (sh.width / E) * (sh.height / E)
            except Exception:
                continue
            stype = str(sh.shape_type or "")
            if "PICTURE" in stype:
                pics.append((area, sh))
            elif "LINE" in stype:
                lines.append(sh)
            elif "AUTO_SHAPE" in stype or "PLACEHOLDER" in stype:
                rects.append((area, sh))
        pics.sort(key=lambda x: -x[0])
        if pics and pics[0][0] > PW * PH * 0.85:
            chrome["bg_image"] = save_pic(pics[0][1], assets_dir, "layout_bg")
        smalls = [p for p in pics[1:] if p[0] < 2.5] or [p for p in pics if p[0] < 2.5]
        if smalls:
            chrome["logo"] = save_pic(smalls[0][1], assets_dir, "layout_logo")
        rects.sort(key=lambda x: -x[0])
        if rects:
            sh = rects[0][1]
            chrome["frame"] = [round(sh.left / E, 3), round(sh.top / E, 3),
                               round(sh.width / E, 3), round(sh.height / E, 3)]
        if lines:
            lines.sort(key=lambda s: s.top or 0)
            chrome["rule_y"] = round(lines[0].top / E, 3)
        chrome["footer"] = any(
            sh.is_placeholder and sh.placeholder_format.type is not None
            and "SLIDE_NUMBER" in str(sh.placeholder_format.type) for sh in layout.shapes)
    out["chrome"] = chrome

    # ---- 3. 章节标签：顶部短文本，跨多页重复在同一位置
    pill = []
    for s in body_slides:
        for sh, t in iter_text_shapes(s):
            if sh.top is None or sh.left is None:
                continue
            y = sh.top / E
            if y > 0.85 or len(t) > 16:
                continue
            st = shape_font(sh)
            if not st.get("size") or st["size"] < 16:
                continue
            pill.append((round(sh.left / E, 2), round(y, 2), round(sh.width / E, 2),
                         round(sh.height / E, 2), t, sh))
    if pill:
        rep = cluster(pill, tol=0.3)[0]
        sh = rep[0][5]
        st = shape_font(sh)
        prst = "rect"
        try:
            g = sh._element.spPr.find("a:prstGeom", NS)
            if g is not None:
                prst = g.get("prst")
        except Exception:
            pass
        out["title"] = {
            "kind": "pill" if prst.startswith("round") else "bar",
            "geom": [round(sh.left / E, 3), round(sh.top / E, 3),
                     round(sh.width / E, 3), round(sh.height / E, 3)],
            "prst": prst,
            "fill": shape_fill_hex(sh, palette),
            "line": shape_line_hex(sh, palette),
            "line_w": shape_line_width_pt(sh),
            "font": st.get("font") or fonts["major"],
            "size": st.get("size") or 24,
            "color": st.get("color") or "FFFFFF",
            "bold": bool(st.get("bold")),
            "align": para_align(sh) or "center",
            "spc": st.get("spc"),
            "line_spacing": para_line_spacing(sh),
            "labels": [c[4] for c in rep[1]][:8],
            "pages": len(rep[1]),
        }
    if out["title"] is None:
        out["warnings"].append("没找到章节标签（顶部圆角标签）：可能是纯图片标题，回退到自绘")

    # ---- 4. 页标题：位于标签下方、字号 14–28、跨多页
    subs = []
    for s in body_slides:
        for sh, t in iter_text_shapes(s):
            if sh.top is None:
                continue
            y = sh.top / E
            if not (0.85 <= y <= 1.75) or len(t) > 22:
                continue
            st = shape_font(sh)
            sz = st.get("size") or 0
            if not (14 <= sz <= 28):
                continue
            subs.append((round(sh.left / E, 2), round(y, 2), round(sh.width / E, 2),
                         round(sh.height / E, 2), t, sz, st))
    if subs:
        rep = cluster(subs, tol=0.55)[0]
        if len(rep[1]) >= 2:
            st = rep[0][6]
            out["page_title"] = {
                "geom": [round(statistics.median([c[0] for c in rep[1]]), 3),
                         round(statistics.median([c[1] for c in rep[1]]), 3),
                         round(statistics.median([c[2] for c in rep[1]]), 3),
                         round(statistics.median([c[3] for c in rep[1]]), 3)],
                "font": st.get("font") or fonts["major"],
                "size": round(statistics.median([c[5] for c in rep[1]]), 1),
                "color": st.get("color"),
                "samples": [c[4] for c in rep[1]][:6],
                "pages": len(rep[1]),
            }
    if out["page_title"] is None:
        out["warnings"].append("没找到稳定的页标题位置：教师可能一页一个主题句，按正文区顶部自绘")

    # ---- 5. 正文安全区
    frame = chrome.get("frame")
    if frame:
        out["body"] = [round(frame[0] + 0.20, 3), round(frame[1] + 0.50, 3),
                       round(frame[2] - 0.40, 3), round(frame[3] - 0.72, 3)]
    else:
        xs0, ys0, xs1, ys1 = [], [], [], []
        for s in body_slides:
            for sh in s.shapes:
                if sh.left is None or sh.top is None:
                    continue
                if sh.top / E < 1.3:      # 跳过标题层
                    continue
                xs0.append(sh.left / E)
                ys0.append(sh.top / E)
                xs1.append((sh.left + (sh.width or 0)) / E)
                ys1.append((sh.top + (sh.height or 0)) / E)
        if xs0:
            out["body"] = [round(min(xs0), 3), round(min(ys0), 3),
                           round(max(xs1) - min(xs0), 3), round(max(ys1) - min(ys0), 3)]
    if out["body"] is None:
        out["warnings"].append("正文区取不到，按页面边距 0.6 英寸估")

    # ---- 6. 封面 / 封底
    def pick_bg(sl):
        best, area = None, 0
        for sh in sl.shapes:
            try:
                if sh.shape_type == 13:
                    a = (sh.width / E) * (sh.height / E)
                    if a > area:
                        best, area = sh, a
            except Exception:
                pass
        return best if (best is not None and area > PW * PH * 0.85) else None

    def text_layers(sl):
        rows = []
        for sh, t in iter_text_shapes(sl):
            if sh.top is None:
                continue
            st = shape_font(sh)
            rows.append({"text": t[:40], "y": round(sh.top / E, 3), "x": round(sh.left / E, 3),
                         "w": round(sh.width / E, 3), "size": st.get("size"),
                         "font": st.get("font"), "color": st.get("color"),
                         "bold": st.get("bold"), "align": para_align(sh)})
        rows.sort(key=lambda r: r["y"])
        return rows

    if slides:
        sl = slides[0]
        bg = pick_bg(sl)
        cover = {"bg": save_pic(bg, assets_dir, "cover_bg") if bg is not None else None,
                 "logo": None, "layers": text_layers(sl)}
        for sh in sl.shapes:
            try:
                if sh.shape_type == 13 and sh is not bg:
                    w = sh.width / E
                    if 1.5 < w < 5:
                        cover["logo"] = save_pic(sh, assets_dir, "cover_logo")
                        # 校徽位置必须记下来：封面底图里没有校徽，它是单独贴的一张图
                        cover["logo_geom"] = [round(sh.left / E, 3), round(sh.top / E, 3),
                                              round(w, 3), round(sh.height / E, 3)]
                        break
            except Exception:
                pass
        out["cover"] = cover
    if len(slides) > 1:
        sl = slides[-1]
        bg = pick_bg(sl)
        end = {"bg": save_pic(bg, assets_dir, "end_bg") if bg is not None else None,
               "layers": text_layers(sl)}
        if end["bg"] is None:
            end["bg"] = out["cover"].get("bg")
        out["end"] = end

    # ---- 6.5 教师实际用的字体（主题里的 Calibri 常常不是实际渲染的字体）
    body_fonts, title_fonts = Counter(), Counter()
    for sl in body_slides:
        for sh, t in iter_text_shapes(sl):
            for para in sh.text_frame.paragraphs:
                for r in para.runs:
                    nm = r.font.name
                    if not nm or not r.text.strip():
                        continue
                    sz = r.font.size.pt if r.font.size else 0
                    (title_fonts if sz >= 22 else body_fonts)[nm] += len(r.text)
    if body_fonts:
        out["fonts"]["body"] = body_fonts.most_common(1)[0][0]
    if title_fonts:
        out["fonts"]["title"] = title_fonts.most_common(1)[0][0]
        out["fonts"]["major"] = out["fonts"]["title"]
    if body_fonts:
        out["fonts"]["minor"] = out["fonts"]["body"]

    # ---- 7. 密度
    chars = [c for c in (text_chars(s) for s in body_slides) if c > 0]
    sizes_w = Counter()
    for s in body_slides:
        for sh, t in iter_text_shapes(s):
            sz = (shape_font(sh) or {}).get("size")
            if sz and 10 <= sz <= 40:
                sizes_w[round(sz)] += len(t)
    out["density"] = {
        "body_pt_median": sizes_w.most_common(1)[0][0] if sizes_w else 18,
        "chars_median": int(statistics.median(chars)) if chars else None,
        "chars_p90": sorted(chars)[int(len(chars) * 0.9)] if chars else None,
        "pages_sampled": len(body_slides),
    }

    # ---- 8. 调色板
    acc = out["title"]["fill"] if out["title"] else None
    out["palette"] = {
        "accent": acc or palette.get("accent1"),
        "text": palette.get("dk1") or "1A1A1A",
        "muted": "767676",
        "bg": palette.get("lt1") or "FFFFFF",
        "accent2": palette.get("accent2"),
    }

    # ---- 9. 字体本机可用性：教师用的常是商用字体，本机没有就会静默回落成宋体，
    #         而 pptx 里存的是字体名，所以缺失只影响本机预览、不影响交付——必须写清楚
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import font_check
        missing = font_check.check_names(
            [out["fonts"].get("major"), out["fonts"].get("minor"),
             out["fonts"].get("body"), out["fonts"].get("title")])
        miss = [(n, alt) for n, ok, alt in missing if not ok]
        if miss:
            detail = "、".join(f"{n}（可用 {alt or '无'} 预览）" for n, alt in miss)
            out["warnings"].append(f"本机未安装：{detail}。文件里仍保留原字体名，"
                                   f"教师机器装了字体就正常，本机预览与渲染自检会是替代字体")
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description="从真实课件反推版式画像")
    ap.add_argument("pptx")
    ap.add_argument("-o", "--out", default="out/profile.json")
    ap.add_argument("--assets", default=None,
                    help="导出背景图/角标到这个目录（建议给，否则只能靠 --template 自带）")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args()

    prof = inspect(args.pptx, args.assets)
    d = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(d, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(prof, f, ensure_ascii=False, indent=2)

    if not args.quiet:
        t, pt = prof.get("title"), prof.get("page_title")
        print(f"[ok] {args.out}")
        print(f"     页面 {prof['meta']['page_w']}x{prof['meta']['page_h']} in，"
              f"正文版式《{prof['meta']['content_layout']}》 ")
        if t:
            print(f"     章节标签 {t['kind']} geom={t['geom']} 填充 #{t['fill']} "
                  f"{t['size']}pt 出现在 {t['pages']} 页")
            print(f"       标签样例：{' / '.join(t['labels'][:4])}")
        if pt:
            print(f"     页标题 {pt['size']}pt @ {pt['geom']}  样例：{' / '.join(pt['samples'][:3])}")
        print(f"     正文区 {prof['body']}")
        print(f"     密度 正文 {prof['density']['body_pt_median']}pt，"
              f"每页约 {prof['density']['chars_median']} 字")
        for w in prof.get("warnings", []):
            print(f"     [警告] {w}")


if __name__ == "__main__":
    main()
