#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""依赖自检：缺库时给一句能照做的中文提示，而不是甩一段 ImportError 栈。

用法：
    python scripts/envcheck.py            # 只看缺什么
    python scripts/envcheck.py --install  # 仅当前解释器为项目虚拟环境时显式安装

被 build_deck.py 等脚本 import，在导入 pptx 之前先跑一遍。
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys

# 导入名 -> pip 包名
REQUIRED = {
    "pptx": "python-pptx",
    "lxml": "lxml",
    "PIL": "Pillow",
    "matplotlib": "matplotlib",
    "numpy": "numpy",
    "pypdf": "pypdf",
}

# 这些是可选的：缺了会退化成「不检查」而不是报错
OPTIONAL = {
    "fitz": "PyMuPDF",          # 读教师 PDF 大纲
    "win32com": "pywin32",      # 调本机 Office 渲染核对（仅 Windows）
}


def missing(mods: dict[str, str]) -> list[str]:
    return [pkg for mod, pkg in mods.items() if importlib.util.find_spec(mod) is None]


def ensure(modules: tuple[str, ...] = ("pptx",)) -> None:
    """缺必需库时直接退出，并说清楚装到哪个 python 里。"""
    lack = []
    for mod in modules:
        if importlib.util.find_spec(mod) is None:
            lack.append(REQUIRED.get(mod, mod))
    if not lack:
        return
    raise SystemExit(
        "缺依赖：" + "、".join(lack) + "\n"
        f"当前解释器：{sys.executable}\n"
        "装法（装到上面这个 python 里，不是另开一个）：\n"
        "请在项目专属虚拟环境按本Skill的requirements.txt安装依赖；不会自动修改全局环境。\n"
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="课件技能的依赖自检")
    ap.add_argument("--install", action="store_true", help="缺什么装什么（pip，需要联网）")
    a = ap.parse_args(argv)
    if a.install and sys.prefix == sys.base_prefix:
        ap.error("--install只允许项目虚拟环境解释器；先创建并选择项目环境，不改全局Python")

    lack = missing(REQUIRED)
    opt = missing(OPTIONAL)
    print(f"当前解释器：{sys.executable}")
    print("必需依赖：" + ("齐全" if not lack else "缺 " + "、".join(lack)))
    if opt:
        print("可选依赖缺：" + "、".join(opt) + "（缺了只是功能退化，不影响出片）")
    if not lack:
        return 0
    if not a.install:
        print("\n在项目虚拟环境中使用该解释器加--install安装；不自动修改全局Python。")
        return 1

    for pkg in lack:
        print(f"\n安装 {pkg} ...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", pkg])
        if r.returncode != 0:
            print(f"[失败] {pkg} 没装上，先检查网络或换镜像：")
            print("请检查项目环境网络与包源，不自动切换第三方镜像。")
            return r.returncode
    left = missing(REQUIRED)
    print("\n安装完成，依赖" + ("齐全" if not left else "仍缺 " + "、".join(left)))
    return 0 if not left else 1


if __name__ == "__main__":
    raise SystemExit(main())
