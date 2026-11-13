"""Read local PDF or text retrieved with real WorkBuddy tools; never guess a library API."""
from __future__ import annotations
import argparse
from pathlib import Path


def from_pdf(path, pages=None):
    from pypdf import PdfReader
    reader = PdfReader(path)
    start, end = 1, len(reader.pages)
    if pages:
        first, separator, last = pages.partition("-")
        start, end = int(first), int(last) if separator else int(first)
    if not 1 <= start <= end <= len(reader.pages):
        raise ValueError("页范围必须位于PDF实际页数内，按1开始计数")
    chunks = []
    for number in range(start, end + 1):
        text = (reader.pages[number - 1].extract_text() or "").strip()
        chunks.append(f"## p{number}\n\n" + (text or "（未取得文字层，不据此补写正文）"))
    return chunks, end - start + 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf")
    parser.add_argument("--text", help="由真实资料工具取得并保存的本地UTF-8正文")
    parser.add_argument("--pages", help="PDF的1起始页范围，如12-18")
    parser.add_argument("--node", action="append", default=[], help="仅用于解释迁移限制，不调用本机隐藏接口")
    parser.add_argument("--space")
    parser.add_argument("--query")
    parser.add_argument("--limit", type=int)
    parser.add_argument("-o", "--out", default="outputs/教材素材.md")
    args = parser.parse_args(argv)
    if args.node or args.space:
        parser.error("资料库检索请使用当前WorkBuddy真实原生工具，取得正文后保存到本地并用--text读取；本脚本不从节点ID猜接口")
    if bool(args.pdf) == bool(args.text):
        parser.error("选择一个--pdf或--text实际文件；搜索词本身不是已取得正文")
    try:
        if args.pdf:
            chunks, count = from_pdf(args.pdf, args.pages)
            source = Path(args.pdf).name
        else:
            if args.pages:
                parser.error("--pages仅用于PDF")
            chunks = [Path(args.text).read_text(encoding="utf-8-sig")]
            count, source = 1, Path(args.text).name
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    destination = Path(args.out)
    if destination.resolve() == Path(args.pdf or args.text).resolve():
        parser.error("输出不能覆盖输入原件")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(f"# 教材素材\n\n来源文件：{source}\n\n以下为文本抽取，不代表图片、公式或章节覆盖已验证。\n\n" + "\n\n".join(chunks) + "\n", encoding="utf-8")
    print(f"已写出{destination}，{count}个文本区段；引用前核对原件位置。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
