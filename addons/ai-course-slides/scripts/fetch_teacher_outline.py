"""Extract ordered candidate headings from actual local PPTX, PDF or Markdown."""
from __future__ import annotations
import argparse
from pathlib import Path
import re


def read_pages(path):
    suffix = path.suffix.lower()
    if suffix == ".pptx":
        from pptx import Presentation
        deck = Presentation(path)
        return [(str(index), "\n".join(shape.text_frame.text for shape in slide.shapes if shape.has_text_frame))
                for index, slide in enumerate(deck.slides, 1)]
    if suffix == ".pdf":
        from pypdf import PdfReader
        return [(str(index), page.extract_text() or "") for index, page in enumerate(PdfReader(path).pages, 1)]
    if suffix in (".md", ".txt"):
        return [("正文位置未映射为页码", path.read_text(encoding="utf-8-sig"))]
    raise ValueError("只读取本地PPTX、PDF、Markdown或TXT")


def outline(pages):
    lines = []
    for location, body in pages:
        candidates = [line.strip() for line in body.splitlines() if line.strip()]
        if not candidates:
            lines.append(f"- 位置{location}：未取得文字层，需原件或OCR核对")
            continue
        headings = [re.sub(r"^#{1,6}\s+", "", line) for line in candidates if re.match(r"^#{1,6}\s+", line)]
        title = headings[0] if headings else candidates[0][:100]
        lines.append(f"- 位置{location}：{title}")
        lines.append("  > " + " ".join(candidates)[:180])
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pdf")
    group.add_argument("--pptx")
    group.add_argument("--markdown", help="真实原生资料工具导出的正文，不伪造页码")
    parser.add_argument("--node", action="append", default=[])
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--outdir", default="outputs/teacher-outlines")
    parser.add_argument("-o", "--out")
    args = parser.parse_args(argv)
    if args.node:
        parser.error("节点ID须交由当前WorkBuddy真实资料工具检索；取得正文后用--markdown或实际本地文件，不调用隐藏接口")
    source = args.pdf or args.pptx or args.markdown
    if not source:
        parser.error("需要一个实际本地文件")
    path = Path(source)
    try:
        pages = read_pages(path)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    target = Path(args.out) if args.out else Path(args.outdir) / (path.stem + ".md")
    if target.resolve() == path.resolve():
        parser.error("输出不能覆盖输入原件")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"# 教师原件候选大纲\n\n来源：{path.name}\n\n按文件读取顺序列出；候选标题与层级仍需核对，Markdown检索片段不证明原件页序。\n\n" + "\n".join(outline(pages)) + "\n", encoding="utf-8")
    print(f"已写出{target}，读取{len(pages)}个实际区段；未验证图片页及原件全部语义。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
