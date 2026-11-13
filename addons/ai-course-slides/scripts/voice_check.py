#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""去 AI 味机检（课件口径）。

来源：blader/humanizer（35 条，A–E 分类）与 op7418/Humanizer-zh（31 条，含中文 F 组）。
两个仓库是「通用文章」的编辑指导，直接套到课件上有两个问题：

1. 判不动的太多。声音校准、作者立场、文件保护这些在 PPT 里没有对应物；
   而课件最刺眼的毛病（每页都收结论、标题批量对仗、三连问开场）原文没有。
2. 会误伤术语。humanizer-zh 明确写了保留边界：「控制器使用闭环反馈」不该改。
   课件里这种词更多——「范式」在讲机器学习三范式时是正式术语。

所以这里只做一件事：把 31 个检查点里**能机判、且落在课件文案上**的部分抽出来，
加一组课件特有的模式（G 组），每条给一句可执行的改法。它给出的是**修改线索**，
不是判决：命中不等于要改，术语、公式、引用原话一律放过。

用法：
    python scripts/voice_check.py 故事板.json                 # 出报告
    python scripts/voice_check.py 故事板.json --md out.md      # 报告存 md
    python scripts/voice_check.py 输出.pptx                    # 直接查成品
    python scripts/voice_check.py 故事板.json --strict         # 明显及以上退出码 1
    python scripts/voice_check.py --rules                      # 看规则表
"""
import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------- 规则表
# level: block = 一出现就该改（课件里没有任何正当用途）
#        warn  = 单独出现可能是正常写法，要结合上下文判断
# page_threshold: 只对「同一页出现 N 次以上」才算命中（破折号、被字句这类）
RULES = [
    # ---- A 铺垫代替陈述 ----
    dict(code="A1", name="不是X，而是Y", level="block",
         rx=r"(?:不仅|不只|不光)[^，。！？]{1,24}[，,]\s*更是"
            r"|(?:不是|并非)[^，。！？]{1,16}[，,]\s*(?:更)?而是",
         advice="两半合成一句陈述：直接说它是什么、能做什么"),
    dict(code="A2", name="起跑式铺垫", level="block",
         rx=r"(?:让我们|咱们)[^。！？]{0,10}(?:来看|看看|走进|深入|一起)"
            r"|(?:下面|接下来)我们(?:来|一起)?(?:看|讲|讨论)",
         advice="删掉预告句直接给内容。嘴上过渡可以，投影上别写"),
    dict(code="A3", name="伪深度格言", level="warn",
         rx=r"本质上是|归根结底|说到底[，,]|真正的[^，。]{2,8}在于",
         advice="换成这一页具体想说的判断，格言不承载信息"),
    dict(code="A4", name="与假想敌辩论", level="warn",
         rx=r"(?:有人|大家|你)可能(?:会)?(?:说|问|想)|不要以为|别误会|这并不意味着",
         advice="删掉假设的反对意见；真有争议就写出是谁、什么证据"),
    dict(code="A5", name="戏剧性单句收尾", level="warn",
         rx=r"^(?:这就是|这才是|而这[，,]?(?:就是|正是)|仅此而已|如此而已)[^。]{0,16}[。！]?$",
         advice="结论句要么带新信息，要么删掉"),
    # ---- B 公式化节奏 ----
    dict(code="B1", name="破折号当万能连接", level="warn", rx=r"——",
         advice="改用句号、冒号或括号；一页最多留一个", page_threshold=3),
    dict(code="B2", name="限定词堆叠", level="warn",
         rx=r"(?:可能|也许|或许)[^，。]{0,6}(?:可能|也许|或许)|在一定程度上(?:可能)?",
         advice="留一个限定词，说清是什么证据支撑这个不确定"),
    dict(code="B3", name="名词化空转（进行＋动词）", level="warn",
         rx=r"进行[一-龥]{2}|加以[一-龥]{2}",
         advice="用动词本身：「进行训练」→「训练」，「进行分析」→「分析」"),
    dict(code="B4", name="无主语加工句", level="warn",
         rx=r"通过[^，。]{2,18}(?:实现|达到|完成|获得)[^，。]{0,10}"
            r"(?:提升|优化|增强|改善)",
         advice="补出「谁做什么得到什么」，别用「通过…实现…」套壳"),
    # ---- C 拔高与借权威 ----
    dict(code="C1", name="AI 高频空转词", level="block",
         # 「闭环」在控制/训练语境里是正经术语（训练闭环、反馈闭环），
         # 只有「形成/打造闭环」「闭环思维」这种才是空转词——humanizer-zh 的保留边界。
         rx=r"赋能|(?:形成|打造|构建|业务|生态)[^，。]{0,2}闭环|闭环(?:思维|生态|管理)"
            r"|抓手|无缝(?:衔接|对接)|深度融合|助力|重塑|"
            r"引领(?:未来|潮流)|保驾护航|行稳致远|全方位|多维度",
         advice="换成具体动作或删掉；这类词删了句子意思不减"),
    dict(code="C2", name="意义拔高", level="block",
         rx=r"(?:标志|象征|意味)着[^，。]{0,10}(?:新|一个)(?:的)?(?:时代|阶段|纪元)"
            r"|具有(?:重要|深远|里程碑)(?:的)?意义|开启了[^，。]{0,8}(?:新)?(?:篇章|时代)",
         advice="删掉意义句，停在最后一个具体事实上"),
    dict(code="C3", name="句尾拔高", level="block",
         rx=r"[，,](?:彰显|体现|展现|折射|印证)了",
         advice="删掉「彰显了…」的尾巴；要留就换成「所以…」的实际用途"),
    dict(code="C4", name="宣传语", level="block",
         rx=r"堪称|令人(?:惊叹|震撼|耳目一新)|不得不(?:说|感叹)"
            r"|颠覆(?:性)?(?:的)?(?:变革|创新)|打开(?:了)?(?:新)?(?:大门|想象空间)",
         advice="把评价换成参数、现象或对比"),
    dict(code="C5", name="借权威", level="warn",
         rx=r"(?:专家|学者|业界)(?:们)?(?:认为|指出|表示)|研究(?:表明|显示|发现)"
            r"|据(?:统计|报道|调查)",
         advice="写出是谁、哪年、什么研究；写不出就删掉归因"),
    # ---- D 排版 ----
    dict(code="D1", name="标题里的表情与装饰符号", level="block",
         rx=r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]|✅|❌|★|◆|■",
         advice="投影里不放 emoji 和装饰符号；层级用字号和位置表达"),
    # 箭头单列一条 warn：讲流程时「数据→特征→模型」是有含义的，不能当装饰一起删
    dict(code="D3", name="箭头代替文字关系", level="warn", rx=r"→|▶",
         advice="箭头只在表达流程时留；说因果、对比就用词，别让读者猜"),
    dict(code="D2", name="中文里的英文直引号", level="warn",
         rx=r"\"[^\"]*[一-龥][^\"]*\"|'[^']*[一-龥][^']*'",
         advice="中文正文用「」或“”，英文和代码才用直引号"),
    # ---- E 聊天与草稿残留 ----
    dict(code="E1", name="客服腔", level="block",
         rx=r"希望(?:这|本)(?:份|节|页|讲)|如有(?:疑问|问题|异议)"
            r"|欢迎(?:交流|讨论|指正)|以上(?:就)?是(?:本次|今天|这一讲)",
         advice="课件不开场寒暄也不道别，删掉"),
    dict(code="E2", name="讲稿腔（谈文档而非知识点）", level="block",
         rx=r"本(?:页|节|章|讲|单元)(?:将|会|主要|重点)?(?:介绍|讲述|讨论|梳理)"
            r"|(?:如|见)(?:下|上)?表(?:所示)?|下图(?:展示|给出)了"
            r"|这里(?:我们)?(?:需要)?(?:注意|强调)",
         advice="直接讲知识点；学生看得见这页是什么，不需要旁白"),
    dict(code="E3", name="篇幅免责与猜测填充", level="warn",
         rx=r"由于(?:篇幅|时间)(?:有限|关系)|限于篇幅|不再赘述|在此不再|篇幅所限",
         advice="要么讲、要么不列，别用「篇幅有限」当省略号"),
    # ---- F 中文补充 ----
    dict(code="F1", name="层叠的「的」", level="warn",
         rx=r"的[^，。的]{2,8}的[^，。的]{2,8}的",
         advice="长定语拆成两句：先说是什么，再说它怎么样"),
    dict(code="F2", name="四字词排比（口号腔）", level="warn",
         # 判据是「顿号连排 且 含评价性形容词」。只判顿号会误伤术语列举：
         # 「假设空间、损失函数、优化方法」三项各不相同，本来就该有三项
         # （humanizer-zh 规则 6：不为避开三段式删项或凑项）。
         rx=r"(?:[一-龥]{4}、){2}[一-龥]{4}",
         require=r"可靠|高效|便捷|稳定|智能|全面|深入|丰富|灵活|完善|强大|优质|先进|卓越|精准",
         advice="四字连排像口号；换成具体差异（数量、顺序、代价）"),
    dict(code="F3", name="「随着…发展」式开场", level="block",
         rx=r"(?:随着|在)[^，。]{0,14}(?:的)?(?:快速|迅猛|不断|飞速)?"
            r"(?:发展|进步|普及|到来)[^，。]{0,6}[，,]",
         advice="删掉时代背景，第一句就进正题"),
    dict(code="F4", name="套话收尾", level="block",
         rx=r"总而言之|综上所述|让我们一起|拭目以待|未来可期|值得期待"
            r"|共同(?:期待|见证)|敬请期待",
         advice="收尾给一个可检验的下一步，别给祝愿"),
    # ---- G 课件特有（humanizer 没有，从实测的 4 份课件里攒出来的） ----
    dict(code="G1", name="三连问开场", level="block",
         rx=r"什么是[^？?]{1,12}[？?][^。]{0,12}为什么[^？?]{1,12}[？?]",
         advice="连环三问是模板腔；留一个真问题，其余改成陈述"),
    dict(code="G2", name="模板化举例", level="warn",
         rx=r"小[明红刚华强]|某(?:同学|同学)|张三|李四|王五",
         advice="换成学科里的真实对象：一段信号、一张片子、一条订单"),
    dict(code="G3", name="空泛趋势判断", level="warn",
         rx=r"(?:进一步|更好地|有效地)(?:提升|促进|推动|保障)"
            r"|(?:越来越|日益)(?:重要|广泛|普遍)",
         advice="给出方向、幅度或条件；只说「进一步提升」等于没说"),
    dict(code="G4", name="形容词代替判断", level="warn",
         rx=r"(?:非常|十分|极其|高度)(?:重要|关键|复杂|强大|优秀)",
         advice="说清重要在哪：影响什么、错了会怎样"),
]

for _r in RULES:                       # 一次编译，逐页复用；规则表里仍写成可读的正则串
    _r["rx"] = re.compile(_r["rx"])
RULE_BY_CODE = {r["code"]: r for r in RULES}

# 分数 = 每 10 页的加权命中，不是准确率。不用「每千字」是因为它奖励短稿：
# 一份 22 页 1700 字的通识课件，命中 8 处除以字数只剩 4.6，看着比实际清爽。
# 阈值从实测的 6 份课件校准：改造前 C 版 4.1 分（明显），改写后 0.9 分（清爽）。
LEVELS = [(1.5, "A", "清爽"), (3.0, "B", "轻微"), (6.0, "C", "明显")]
LEVEL_FALLBACK = ("D", "重")
BLOCK_W, WARN_W, DOC_W = 3, 1, 2

# 扫这些字段（投影上看得见的）。note 是讲稿、source 是出处、covers 是机器字段，都不扫。
TEXT_KEYS = ("title", "kicker", "subtitle", "takeaway", "caption", "text",
             "points", "cards", "left", "right", "table", "nodes", "mnemonic",
             "answer", "hint", "ask")
# quote 页的 text 是别人的原话，改一个字都是篡改引用；只查它的标题。
SKIP_BODY_TYPES = ("quote",)


def _flatten(obj, out, key=""):
    if isinstance(obj, str):
        if key in TEXT_KEYS or key == "":
            out.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("note", "source", "image", "covers", "placeholder"):
                continue
            if k in TEXT_KEYS:
                _flatten(v, out, k)
    elif isinstance(obj, list):
        for v in obj:
            _flatten(v, out, key)


def visible_texts(spec):
    """一页里投影可见的文字。"""
    out = []
    for k in TEXT_KEYS:
        if k in spec:
            _flatten(spec[k], out, k)
    return [t for t in out if str(t).strip()]


def body_texts(spec):
    if str(spec.get("type")) in SKIP_BODY_TYPES:
        return [t for t in visible_texts(spec) if t == spec.get("title")]
    return visible_texts(spec)


def _terms_of(sb):
    """术语白名单：coverage 里的知识点名 + meta.terms。

    humanizer-zh 的保留边界在这里最要紧：「控制器使用闭环反馈」不能改成
    「控制器使用负反馈」之外的任何东西——它是术语。命中片段若落在某个术语
    里面，就不算 AI 味。
    """
    terms = []
    for item in sb.get("coverage") or []:
        if isinstance(item, dict):
            terms.append(str(item.get("key") or ""))
            terms.extend(str(a) for a in (item.get("alias") or []))
        else:
            terms.append(str(item))
    terms.extend(str(t) for t in (sb.get("terms") or (sb.get("meta") or {}).get("terms") or []))
    return [t for t in terms if len(t) >= 2]


def _whitelisted(frag, around, terms):
    if not terms:
        return False
    # 命中片段自己就是一个术语（如「闭环」出现在「闭环控制」的上下文里）
    for t in terms:
        if frag and frag in t:
            return True
        if frag and t in around and len(t) >= 2 and frag in t:
            return True
    return False


def _page_weight(spec):
    return len("".join(visible_texts(spec)))


# ---------------------------------------------------------------- 页级模式
def page_pattern_hits(spec, i):
    """整页层面的公式化痕迹：单句看不出来，整页看才明显。"""
    hits = []
    typ = str(spec.get("type") or "bullets")
    title = str(spec.get("title") or "")
    pts = [str(p) for p in (spec.get("points") or [])]

    if typ == "bullets" and len(pts) >= 3:
        heads = [p[:2] for p in pts if len(p) >= 2]
        if len(heads) >= 3 and len(set(heads)) == 1:
            hits.append(dict(page=i, code="P1", name="三条要点同一个开头", level="warn",
                             frag=f"「{heads[0]}…」×{len(heads)}",
                             advice="换主语或合并句子；三个平行句读起来像填空"))
        ws = sorted(len(p) for p in pts)
        # 年表 / 时间线 / 编号清单里，各条长度接近是格式决定的，不是机器凑节奏：
        # 「1998 LeNet：…」「2012 AlexNet：…」四行都二十来字，因为它们必须同构。
        # 为了让这条规则不响而去把某一行砍短，等于把年表改坏——误报比漏报更坏。
        dated = sum(1 for p in pts
                    if re.match(r"^\s*(?:[12]\d{3}\b|[①②③④⑤]|\d[.、)])", p))
        structured = dated >= max(2, len(pts) - 1)
        if ws and ws[-1] - ws[0] <= 2 and ws[0] >= 12 and not structured:
            hits.append(dict(page=i, code="P2", name="三条一样长", level="warn",
                             frag=f"{ws[0]}–{ws[-1]} 字",
                             advice="长短句混排；等长排比是机器凑出来的节奏"))

    if typ == "bullets" and pts and title:
        head = re.sub(r"[，。？！、\s]", "", title)[:6]
        first = re.sub(r"[，。？！、\s]", "", pts[0])[:6]
        if len(head) >= 5 and head == first:
            hits.append(dict(page=i, code="P3", name="首句复读标题", level="warn",
                             frag=f"「{head}」",
                             advice="第一条要点直接给证据或下一步，别把标题再说一遍"))

    body = "".join(body_texts(spec))
    for code, ch, thr in (("P4", "被", 4), ("P5", "——", 3)):
        if body.count(ch) >= thr and not RULE_BY_CODE.get(code):
            hits.append(dict(page=i, code=code,
                             name="被字句堆叠" if ch == "被" else "破折号成瘾",
                             level="warn", frag=f"{ch}×{body.count(ch)}",
                             advice="改主动句" if ch == "被" else "换成句号或括号"))
    return hits


def doc_pattern_hits(specs):
    """全片层面的：这几条只有横着看整份才成立。"""
    hits = []
    n = len(specs)
    body = [s for s in specs if str(s.get("type")) not in ("cover", "end")]
    nb = max(1, len(body))

    # 分母只算「会画结论句」的页型（bullets/summary）：分段页和 spine 页本来
    # 就不带 takeaway，把它们算进来会把密度稀释掉——一份 20 页里 10 张分段页的
    # 课件，就算每张内容页都收了结论，比例也只有一半。
    tb = [s for s in body if str(s.get("type")) in ("bullets", "summary")]
    tk = sum(1 for s in tb if str(s.get("takeaway") or "").strip())
    if len(tb) >= 6 and tk / len(tb) > 0.7:
        hits.append(dict(page=0, code="T1", name="每页都收结论", level="warn",
                         frag=f"{tk}/{nb} 页有结论句",
                         advice="结论句是重音，满篇都是就没有重音；只在真正要停一下的页写"))

    bb = [s for s in body if str(s.get("type")) == "bullets"]
    three = sum(1 for s in bb if len(s.get("points") or []) == 3)
    # 阈值定在 0.8 而不是 0.6：三条要点是教学里最常见的分法（三个部件、三步、
    # 三种范式），六成页面是三条属于正常。到八成才是「不管内容几条都凑三条」。
    if len(bb) >= 8 and three / len(bb) > 0.8:
        hits.append(dict(page=0, code="T2", name="三段式成瘾", level="warn",
                         frag=f"{three} 页正好三条要点",
                         advice="该两条就两条、该五条就五条；凑数比少一条更明显"))

    titles = [re.sub(r"\s", "", str(s.get("title") or "")) for s in body]
    quad = [t for t in titles if re.fullmatch(r"[一-龥]{4}", t)]
    pair = [t for t in titles if re.fullmatch(r"[^，]{2,9}，[^，]{2,9}", t)]
    if nb >= 8 and len(quad) >= 3:
        hits.append(dict(page=0, code="T3", name="标题批量四字格", level="warn",
                         frag=f"{len(quad)}/{nb} 页是四字标题",
                         advice="四字标题信息量低（「深度学习概述」），换成一个判断句"))
    if nb >= 8 and len(pair) >= 5 and len(pair) / nb > 0.45:
        hits.append(dict(page=0, code="T4", name="标题批量对仗", level="warn",
                         frag=f"{len(pair)}/{nb} 页是「A，B」双段",
                         advice="对仗标题连成片像文案；只在真有两个对比项时用"))

    lens = []
    for s in body:
        for p in (s.get("points") or []):
            lens.append(len(str(p)))
    if len(lens) >= 20:
        mean = sum(lens) / len(lens)
        sd = (sum((x - mean) ** 2 for x in lens) / len(lens)) ** 0.5
        if 11 <= mean <= 22 and sd < 3.5:
            hits.append(dict(page=0, code="T5", name="句长节奏一致", level="warn",
                             frag=f"平均 {mean:.0f} 字，标准差 {sd:.1f}",
                             advice="全篇每句一样长最像机器；插几句 6 字的短句"))
    return hits


# ---------------------------------------------------------------- 主分析
def analyze(specs, terms=None, limit=1):
    terms = terms or []
    hits = []
    for i, sp in enumerate(specs, 1):
        counts = {}
        for txt in body_texts(sp):
            for r in RULES:
                for m in r["rx"].finditer(txt):
                    frag = m.group(0)
                    around = txt
                    if r.get("require") and not re.search(r["require"], frag):
                        continue
                    if _whitelisted(frag, around, terms):
                        continue
                    c = counts.setdefault(r["code"], 0)
                    counts[r["code"]] += 1
                    if c + 1 == limit:
                        hits.append(dict(page=i, code=r["code"], name=r["name"],
                                         level=r["level"], frag=frag[:24],
                                         advice=r["advice"]))
                # 页内计数只在达到阈值时报一次
                if r.get("page_threshold") and counts.get(r["code"], 0) >= r["page_threshold"]:
                    if not any(h["page"] == i and h["code"] == r["code"] for h in hits):
                        hits.append(dict(page=i, code=r["code"], name=r["name"],
                                         level="warn", frag=f"×{counts[r['code']]}",
                                         advice=r["advice"]))
        hits.extend(page_pattern_hits(sp, i))
    hits.extend(doc_pattern_hits(specs))

    chars = max(1, sum(_page_weight(s) for s in specs))
    # 全片级命中（每页都收结论、三段式成瘾）不占某一页，权重加倍：
    # 它们是横着看才成立的模式，改起来是整份改，不是改一句。
    raw = sum((DOC_W if not h["page"] else
               BLOCK_W if h["level"] == "block" else WARN_W) for h in hits)
    score = raw * 10.0 / max(1, len(specs))
    level, label = LEVEL_FALLBACK
    for thr, lv, lb in LEVELS:
        if score < thr:
            level, label = lv, lb
            break
    return dict(score=score, level=level, label=label, hits=hits,
                chars=chars, pages=len(specs),
                blocks=sum(1 for h in hits if h["level"] == "block"))


def analyze_file(path):
    if path.lower().endswith(".pptx"):
        specs = _specs_from_pptx(path)
        return analyze(specs)
    with open(path, encoding="utf-8") as f:
        sb = json.load(f)
    return analyze(sb.get("slides") or [], _terms_of(sb))


def _specs_from_pptx(path):
    """直接查成品：成品常常不是这份故事板出的（改过的、别人给的）。"""
    from pptx import Presentation
    prs = Presentation(path)
    h = prs.slide_height / 914400.0
    specs = []
    for sl in prs.slides:
        texts = []
        for shp in sl.shapes:
            if not shp.has_text_frame:
                continue
            if shp.top is not None and shp.top / 914400.0 > h - 0.7:
                continue      # 页脚
            t = shp.text_frame.text.strip()
            if t:
                texts.append(t)
        specs.append({"type": "bullets", "title": texts[0] if texts else "",
                      "points": texts[1:]})
    return specs


# ---------------------------------------------------------------- 报告
def report(rep, storyboard_name="", top=6):
    lines = [f"[去AI味] {storyboard_name}｜{rep['pages']} 页 {rep['chars']} 字｜"
             f"每 10 页 {rep['score']:.1f} 分 → {rep['level']}（{rep['label']}）｜"
             f"命中 {len(rep['hits'])} 处（其中必改 {rep['blocks']} 处）"]
    pages = [h for h in rep["hits"] if h["page"]]
    docs = [h for h in rep["hits"] if not h["page"]]
    if pages:
        lines.append("  逐页：")
        for h in pages[:40]:
            mark = "●" if h["level"] == "block" else "○"
            lines.append(f"   {mark} p{h['page']:<3} {h['code']} {h['name']}"
                         f"「{h['frag']}」→ {h['advice']}")
        if len(pages) > 40:
            lines.append(f"   …另有 {len(pages) - 40} 处")
    if docs:
        lines.append("  全片：")
        for h in docs:
            lines.append(f"   ○ 全片 {h['code']} {h['name']}（{h['frag']}）→ {h['advice']}")
    if rep["level"] in ("C", "D"):
        lines.append(f"  结论：AI 味{rep['label']}，按上面 ● 逐条改；"
                     f"规则出处见 references/de-ai-voice.md")
    else:
        lines.append("  结论：可以交付，○ 项属于可选打磨")
    return "\n".join(lines)


def to_md(rep, name=""):
    out = [f"# 去 AI 味检查：{name}", "",
           f"- 规模：{rep['pages']} 页 / {rep['chars']} 字",
           f"- 密度：每 10 页 {rep['score']:.1f} 分（命中数 × 权重 ÷ 页数）",
           f"- 等级：**{rep['level']}（{rep['label']}）**",
           f"- 命中：{len(rep['hits'])} 处，其中必改 {rep['blocks']} 处", "",
           "| 页 | 码 | 模式 | 命中 | 改法 | 级别 |", "|---|---|---|---|---|---|"]
    for h in rep["hits"]:
        pg = h["page"] or "全片"
        out.append(f"| {pg} | {h['code']} | {h['name']} | {h['frag']} | "
                   f"{h['advice']} | {'必改' if h['level'] == 'block' else '看上下文'} |")
    out += ["", "> 命中是线索不是判决。术语、公式、引用原话不改；"
                "改不动的地方保留，别为了降分把话说空。"]
    return "\n".join(out)


def check(path, strict=False, quiet=False):
    """给 build_deck --check 调用：返回必改项清单。"""
    rep = analyze_file(path)
    if not quiet:
        print("")
        print(report(rep, os.path.basename(path)))
    bad = [h for h in rep["hits"] if h["level"] == "block"]
    if strict and (bad or rep["level"] in ("C", "D")):
        return rep, bad
    return rep, []


def main():
    ap = argparse.ArgumentParser(description="去 AI 味机检（课件口径）")
    ap.add_argument("source", nargs="?", help="故事板 json 或成品 pptx")
    ap.add_argument("--md", default=None, help="报告另存 md")
    ap.add_argument("--strict", action="store_true",
                    help="必改项非空或等级达到「明显」时退出码 1")
    ap.add_argument("--rules", action="store_true", help="打印规则表后退出")
    args = ap.parse_args()

    if args.rules:
        print(f"{len(RULES)} 条机判规则（出处：blader/humanizer A–E ＋ Humanizer-zh F 组 ＋ 课件 G 组）")
        for r in RULES:
            mark = "必改" if r["level"] == "block" else "看上下文"
            print(f"  {r['code']:<3} {r['name']:<18} {mark:<5} {r['advice']}")
        return

    if not args.source:
        sys.exit("要检查什么？给故事板 json 或成品 pptx")
    if not os.path.exists(args.source):
        sys.exit(f"文件不存在：{args.source}")

    if args.source.lower().endswith(".pptx"):
        rep = analyze(_specs_from_pptx(args.source))
    else:
        with open(args.source, encoding="utf-8") as f:
            sb = json.load(f)
        rep = analyze(sb.get("slides") or [], _terms_of(sb))
    print(report(rep, os.path.basename(args.source)))
    if args.md:
        os.makedirs(os.path.dirname(os.path.abspath(args.md)), exist_ok=True)
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(to_md(rep, os.path.basename(args.source)))
        print(f"[ok] 报告已写入 {args.md}")
    if args.strict and (rep["blocks"] or rep["level"] in ("C", "D")):
        sys.exit(f"[strict] AI 味{rep['label']}：{rep['blocks']} 处必改，退出码 1")


if __name__ == "__main__":
    main()
