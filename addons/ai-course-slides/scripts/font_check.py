#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""字体可用性检测：确认画像/故事板里点名的字体，这台机器上到底有没有。

为什么需要它
------------
教师课件的主题里写着 Calibri，实际渲染用的是「方正正大黑简体」这类商用字体。
画像把真名抓出来了，但**本机没装**时 PowerPoint 会静默回落成宋体——
标签里的中文变成衬线字，看着就不像教师的课件，而脚本一声不响。

这个脚本把「静默」变成「明确」：

    python font_check.py --profile out/profile.json
    python font_check.py --font 方正正大黑简体 --font 微软雅黑

关键区分（很重要，别搞反）
--------------------------
**缺失只影响本机预览和渲染自检，不影响交付文件。**
.pptx 里存的是字体名而不是字形，教师机器上装了那款字体就照常显示。
所以正确做法是：文件里保留教师字体名，本机渲染时知道"我现在看到的不是最终效果"，
并在交付说明里写一句「本机未装 XX 字体，预览以替换字体呈现」。
不要为了本机好看就把字体名改掉——那会把教师的排版规范改没了。
"""
import argparse
import json
import os
import platform
import re
import sys

# 中文字体名里常见的平台差异写法，归一化后再比，避免「微软雅黑 Light」认不出「微软雅黑」
STRIP_RE = re.compile(r"[\s_\-]|(regular|bold|light|medium|semibold|italic|normal)$", re.I)

# 同一款字体的中英文名/新旧名。注册表里常只登记英文名（微软雅黑 → Microsoft YaHei），
# 不打通这层映射，"微软雅黑"会被误判成没装——本机明明就有。
ALIAS_GROUPS = [
    {"微软雅黑", "Microsoft YaHei", "Microsoft YaHei UI"},
    {"宋体", "SimSun"},
    {"新宋体", "NSimSun"},
    {"黑体", "SimHei"},
    {"楷体", "KaiTi", "楷体_GB2312"},
    {"仿宋", "FangSong"},
    {"等线", "DengXian"},
    {"华文细黑", "STHeiti", "Heiti SC"},
    {"华文中宋", "STZhongsong"},
    {"苹方-简", "PingFang SC"},
    {"思源黑体", "Source Han Sans SC", "Noto Sans CJK SC", "Noto Sans SC"},
    {"思源宋体", "Source Han Serif SC", "Noto Serif CJK SC"},
]

# 优先推荐的替代字体：按「黑体观感接近 + 大概率本机已有」排序
SANS_CANDIDATES = [
    "微软雅黑", "Microsoft YaHei", "思源黑体", "Source Han Sans SC", "Noto Sans CJK SC",
    "Noto Sans SC", "苹方-简", "PingFang SC", "阿里巴巴普惠体", "HarmonyOS Sans SC",
    "等线", "DengXian", "黑体", "SimHei", "华文细黑", "STHeiti",
]

# 已知商用字体的替代关系（教师课件里最常见的那几款）
KNOWN_SUBSTITUTE = {
    "方正正大黑简体": ["微软雅黑", "思源黑体", "Noto Sans CJK SC", "黑体"],
    "方正正中黑简体": ["微软雅黑", "思源黑体", "Noto Sans CJK SC", "黑体"],
    "方正兰亭黑简体": ["微软雅黑", "思源黑体", "Noto Sans CJK SC"],
    "方正小标宋简体": ["宋体", "SimSun", "思源宋体"],
    "方正书宋简体": ["宋体", "SimSun"],
    "微软雅黑": ["思源黑体", "Noto Sans CJK SC", "黑体"],
    "思源黑体": ["微软雅黑", "Noto Sans CJK SC"],
    "华文中宋": ["宋体", "SimSun"],
}


def _norm(name):
    s = re.sub(r"[（(].*?[)）]", "", str(name)).strip()
    s = STRIP_RE.sub("", s.lower())
    return s


_cache = None


def installed_fonts():
    """返回本机字体名集合（含归一化形式）。读注册表/字体目录，不做字形解析。"""
    global _cache
    if _cache is not None:
        return _cache
    names = set()
    sysname = platform.system()
    if sysname == "Windows":
        try:
            import winreg
            for root, flag in ((winreg.HKEY_LOCAL_MACHINE, 0), (winreg.HKEY_CURRENT_USER, 0)):
                try:
                    key = winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
                except OSError:
                    continue
                i = 0
                while True:
                    try:
                        disp, val, _ = winreg.EnumValue(key, i)
                    except OSError:
                        break
                    i += 1
                    names.add(re.sub(r"\s*\((TrueType|OpenType|All res|VGA res|PostScript)\)\s*$",
                                     "", disp, flags=re.I))
                    stem = os.path.splitext(os.path.basename(str(val)))[0]
                    if stem:
                        names.add(stem)
        except Exception:
            pass
        windir = os.environ.get("WINDIR", r"C:\Windows")
        for d in (os.path.join(windir, "Fonts"), os.path.expanduser(r"~\AppData\Local\Microsoft\Windows\Fonts")):
            if os.path.isdir(d):
                names.update(os.path.splitext(f)[0] for f in os.listdir(d))
    else:
        for d in ("/System/Library/Fonts", "/Library/Fonts", os.path.expanduser("~/Library/Fonts"),
                  "/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
                  os.path.expanduser("~/.local/share/fonts")):
            if not os.path.isdir(d):
                continue
            for root, _, files in os.walk(d):
                names.update(os.path.splitext(f)[0] for f in files
                             if f.lower().endswith((".ttf", ".ttc", ".otf", ".otc")))
        try:
            import subprocess
            out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout
            for line in out.splitlines():
                names.update(x.strip() for x in line.split(","))
        except Exception:
            pass
    _cache = names
    return names


def has_font(name):
    """名字本身或它的中英文别名在系统里就算已安装。

    注册表里的名字常是 "Microsoft YaHei & Microsoft YaHei UI (TrueType)" 这种复合串，
    所以不能只做精确相等，要允许候选名被系统名包含（≥4 字符才做，避免 "sim" 命中一片）。
    """
    if not _norm(name):
        return True          # 没指定字体不等于缺字体，别把空值报成"未安装"
    targets = alias_set(name)
    for n in installed_fonts():
        nn = _norm(n)
        for t in targets:
            if t == nn or (len(t) >= 4 and t in nn):
                return True
    return False


_ALIAS_INDEX = None


def alias_set(name):
    """返回该字体名所在的别名组（都归一化过）。"""
    global _ALIAS_INDEX
    if _ALIAS_INDEX is None:
        _ALIAS_INDEX = {}
        for grp in ALIAS_GROUPS:
            norms = {_norm(x) for x in grp}
            for n in norms:
                _ALIAS_INDEX[n] = norms
    return _ALIAS_INDEX.get(_norm(name), {_norm(name)})


def suggest(name):
    """给缺失字体挑一个本机已装的替代：先查已知替代关系，再按通用候选排。"""
    cands = KNOWN_SUBSTITUTE.get(name) or []
    seen = set(cands)
    cands = cands + [c for c in SANS_CANDIDATES if c not in seen]
    for c in cands:
        if c != name and has_font(c):
            return c
    return None


def check_names(names):
    """批量检查，返回 [(字体名, 是否已装, 替代建议)]，保持输入顺序、去重。"""
    out, seen = [], set()
    for n in names:
        if not n or n in seen:
            continue
        seen.add(n)
        out.append((n, has_font(n), None if has_font(n) else suggest(n)))
    return out


def report(names, quiet=False):
    rows = check_names(names)
    missing = [r for r in rows if not r[1]]
    if not quiet:
        for n, ok, alt in rows:
            print(f"   {'✓' if ok else '✗'} {n}" + ("" if ok else f"   → 本机可用替代：{alt or '（没找到同风格字体）'}"))
    if missing:
        print(f"[字体] 有 {len(missing)} 款字体本机未安装：")
        for n, _, alt in missing:
            print(f"   - {n}（可用 {alt or '无'} 代替预览）")
        print("     只影响本机预览与渲染自检，**不影响交付文件**：pptx 里存的是字体名，"
              "教师机器装了这款字体就照常显示。")
        print("     交付说明里写一句「本机未安装 XX，预览图为替代字体效果」即可，"
              "不要为了本机好看把字体名改掉。")
    return missing


def main():
    ap = argparse.ArgumentParser(description="检查字体在本机是否可用")
    ap.add_argument("--profile", default=None, help="inspect_template.py 产出的画像 json")
    ap.add_argument("--font", action="append", default=[], help="直接指定字体名，可重复")
    ap.add_argument("-q", "--quiet", action="store_true", help="只报缺失")
    args = ap.parse_args()

    names = list(args.font)
    if args.profile:
        with open(args.profile, encoding="utf-8") as f:
            prof = json.load(f)
        f_ = prof.get("fonts") or {}
        names += [f_.get(k) for k in ("major", "minor", "body", "title")]
        names += [(prof.get("title") or {}).get("font"), (prof.get("page_title") or {}).get("font")]
    names = [n for n in names if n]
    if not names:
        print("没有指定字体。用 --profile 画像 或 --font 字体名。")
        return 0

    if args.quiet:
        missing = [n for n, ok, _ in check_names(names) if not ok]
        for n in missing:
            print(f"[字体] 缺失：{n}")
        return 0
    print(f"[字体] 本机共识别 {len(installed_fonts())} 个字体名，检查 {len(set(names))} 款：")
    report(names)
    return 0


if __name__ == "__main__":
    sys.exit(main())
