#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成默认模板 assets/default-template.pptx（16:9，中文黑体，深蓝主色）。

只在需要重建默认模板时运行，日常生成 PPT 不需要跑它。
    python make_default_template.py [输出路径]
"""
import os
import sys

from lxml import etree
import envcheck  # noqa: E402  同目录依赖自检，缺库时给人话
envcheck.ensure()

from pptx import Presentation
from pptx.util import Inches

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "assets", "default-template.pptx")

ACCENT = "1F4E79"      # 主色：深学术蓝
ACCENT2 = "C0504D"     # 次色：警示红（仅用于强调，不做大面积）
TEXT = "1A1A1A"
CN_FONT = "微软雅黑"
EN_FONT = "Segoe UI"


def set_scheme_color(scheme, tag, value):
    node = scheme.find(f"a:{tag}", {"a": A})
    if node is None:
        return
    for child in list(node):
        node.remove(child)
    srgb = etree.SubElement(node, f"{{{A}}}srgbClr")
    srgb.set("val", value)


def main(out=OUT):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    for part in prs.part.package.iter_parts():
        if not str(part.partname).startswith("/ppt/theme/"):
            continue
        root = etree.fromstring(part.blob)
        ns = {"a": A}
        scheme = root.find(".//a:clrScheme", ns)
        if scheme is not None:
            set_scheme_color(scheme, "accent1", ACCENT)
            set_scheme_color(scheme, "accent2", ACCENT2)
            set_scheme_color(scheme, "dk1", "000000")
            set_scheme_color(scheme, "dk2", TEXT)
            set_scheme_color(scheme, "lt1", "FFFFFF")
            set_scheme_color(scheme, "lt2", "F7F7F7")
        fs = root.find(".//a:fontScheme", ns)
        if fs is not None:
            fs.set("name", "课程模板")
            for tag in ("a:majorFont", "a:minorFont"):
                node = fs.find(tag, ns)
                if node is None:
                    continue
                latin = node.find("a:latin", ns)
                ea = node.find("a:ea", ns)
                if latin is not None:
                    latin.set("typeface", EN_FONT)
                if ea is not None:
                    ea.set("typeface", CN_FONT)
        part._blob = etree.tostring(root, xml_declaration=True,
                                    encoding="UTF-8", standalone=True)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    prs.core_properties.author = prs.core_properties.last_modified_by = "课程组"
    prs.core_properties.comments = prs.core_properties.keywords = ""
    prs.save(out)
    print(f"[ok] 默认模板已生成: {out}")
    print(f"     尺寸 13.333×7.5 in（16:9）｜主色 #{ACCENT}｜中文字体 {CN_FONT}｜"
          f"版式 {len(prs.slide_layouts)} 个")
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else OUT)
