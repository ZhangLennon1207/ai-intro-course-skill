#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 pptx 逐页导出 PNG 并拼成一张缩略图，用来"亲眼看一遍"。

用法:
    python render_check.py deck.pptx [输出目录] [列数]
输出:
    <输出目录>/slide-01.png ...   单页
    <输出目录>/contact.png        缩略图总览

依赖: pywin32 + 本机 PowerPoint（Windows）。没有 PowerPoint 时脚本会提示改用人工预览，
不会假装检查过。
"""
import os
import sys
import shutil
import tempfile

def export_png(pptx_path, out_dir):
    import win32com.client
    pptx_path = os.path.abspath(pptx_path)
    out_dir = os.path.abspath(out_dir)
    if os.path.isdir(out_dir) and any(name.lower().endswith(".png") for name in os.listdir(out_dir)):
        raise ValueError("渲染目录已有图片，请使用新的专属目录；不删除或覆盖原文件")
    app = win32com.client.DispatchEx("PowerPoint.Application")
    pres = None
    staging = tempfile.TemporaryDirectory(prefix="course-ppt-render-")
    try:
        pres = app.Presentations.Open(pptx_path, ReadOnly=True, WithWindow=False)
        pres.Export(staging.name, "PNG", 1600, 900)
        n = pres.Slides.Count
    finally:
        try:
            if pres is not None:
                pres.Close()
        finally:
            try:
                app.Quit()
            except Exception:
                pass
    def order(f):
        digits = "".join(ch for ch in f if ch.isdigit())
        return int(digits) if digits else 0
    files = [f for f in os.listdir(staging.name)
             if f.lower().endswith(".png") and f.lower() != "contact.png"]
    files.sort(key=order)
    renamed = []
    os.makedirs(out_dir, exist_ok=True)
    for i, f in enumerate(files, 1):
        dst = os.path.join(out_dir, f"slide-{i:02d}.png")
        src = os.path.join(staging.name, f)
        with open(dst, "xb") as stream, open(src, "rb") as image:
            shutil.copyfileobj(image, stream)
        renamed.append(dst)
    staging.cleanup()
    return renamed, n


def contact_sheet(pngs, out_path, cols=3, pad=12, bg=(245, 245, 247)):
    from PIL import Image
    if not pngs:
        raise SystemExit("[错误] 没有导出任何页面")
    ims = [Image.open(p).convert("RGB") for p in pngs]
    tw = 520
    th = int(tw * ims[0].height / ims[0].width)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * pad, rows * th + (rows + 1) * pad), bg)
    for i, im in enumerate(ims):
        r, c = divmod(i, cols)
        sheet.paste(im.resize((tw, th), Image.LANCZOS),
                    (pad + c * (tw + pad), pad + r * (th + pad)))
    sheet.save(out_path)
    return out_path


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    pptx = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(pptx)), "render")
    cols = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    try:
        pngs, n = export_png(pptx, out_dir)
    except Exception as e:
        print("[跳过] 无法调用 PowerPoint 渲染：", e)
        print("      请人工打开 pptx 逐页检查，不要当作已检查。")
        return 2
    sheet = contact_sheet(pngs, os.path.join(out_dir, "contact.png"), cols)
    print(f"[ok] 共 {n} 页，单页在 {out_dir}")
    print(f"[ok] 缩略图: {sheet}")
    print("     现在必须打开 contact.png 逐页看：图有没有顶边、文字有没有溢出、标题有没有压住内容。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
