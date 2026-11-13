"""Local assessment statistics; missing observations are never fabricated as scores."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import re
import sys
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kp

ABSENT = {"", "缺考", "缺席", "absent", "nan", "none"}
TRUE = {"√", "对", "正确", "是", "t", "true"}
FALSE = {"×", "错", "错误", "否", "f", "false"}
MIN_DISCRIMINATION_SAMPLE = 30


def flat(bank):
    if isinstance(bank.get("questions"), list):
        return bank["questions"]
    return [dict(q, type=q.get("type", group.get("type")))
            for group in bank.get("groups", []) for q in group.get("questions", [])]


def q_points(question):
    values = question.get("points") or ([question["point"]] if question.get("point") else [])
    return [str(value).strip() for value in ([values] if isinstance(values, str) else values) if str(value).strip()]


def links(question, table):
    points = q_points(question)
    ids = question.get("kp_ids") or []
    if isinstance(ids, str):
        ids = [ids]
    if ids and len(ids) != len(points) and points:
        raise ValueError("题目kp_ids与points数量不一致")
    if not points:
        points = [table.get(kid, {}).get("name", str(kid)) for kid in ids]
    linked = [(str(ids[index]) if ids else kp.resolve(point, table) or "", point)
              for index, point in enumerate(points)]
    if table and any(kid and kid not in table for kid, _ in linked):
        raise ValueError("题目中的知识点编号不在本次显式映射中")
    return linked


def clean(value):
    return re.sub(r"[\s，。、；：？！,.;:?!（）()【】\[\]“”\"']", "", str(value)).casefold()


def letters(value):
    if isinstance(value, list):
        value = "".join(map(str, value))
    return "".join(sorted(set(re.sub(r"[\s,，、;；]", "", str(value)).upper())))


def judge_one(question, value):
    text = "" if value is None else str(value).strip()
    score, kind = float(question["score"]), question["type"]
    if kind in ("short", "comp"):
        if text.casefold() in ABSENT:
            return None, "pending"
        try:
            number = float(text)
        except ValueError:
            return None, "pending"
        if not math.isfinite(number) or number < 0 or number > score:
            return None, "invalid_score"
        return number, "correct" if number == score else "wrong" if number == 0 else "part"
    if text.casefold() in ABSENT:
        return 0.0, "blank"
    if kind in ("single", "multi"):
        answer, response = letters(question["answer"]), letters(text)
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"[:len(question.get("options", []))])
        if not response or not set(response) <= allowed or (kind == "single" and len(response) != 1):
            return 0.0, "invalid_answer"
        correct = response == answer
    elif kind == "judge":
        response, answer = text.casefold(), str(question["answer"]).strip().casefold()
        if response not in TRUE | FALSE:
            return 0.0, "invalid_answer"
        correct = (response in TRUE) == (answer in TRUE)
    elif kind == "blank":
        answers = question.get("answer")
        answers = answers if isinstance(answers, list) else [answers]
        responses = text.split("|") if len(answers) > 1 else [text]
        correct = len(responses) == len(answers) and all(
            clean(response) in {clean(option) for option in str(answer).split("/")}
            for response, answer in zip(responses, answers))
    else:
        raise ValueError("未知题型")
    return (score, "correct") if correct else (0.0, "wrong")


def validate_ids(frame):
    if "student_id" not in frame:
        raise ValueError("数据需要student_id列（原始ID仅保留在教师本地明细，不等于匿名化）")
    ids = frame["student_id"].astype(str).str.strip()
    if ids.eq("").any() or ids.str.casefold().isin(["nan", "none"]).any() or ids.duplicated().any():
        raise ValueError("student_id缺失或重复；先核对重考与重复导出，未自动删除或合并")


def summary(values, full, pass_fraction=None):
    if pass_fraction is not None and (not math.isfinite(pass_fraction) or not 0 <= pass_fraction <= 1):
        raise ValueError("显式pass_fraction需在0至1之间")
    valid = pd.to_numeric(values, errors="coerce").dropna()
    distribution = []
    for index in range(10):
        low, high = full * index / 10, full * (index + 1) / 10
        mask = (valid >= low) & ((valid <= high) if index == 9 else (valid < high))
        distribution.append({"from": low, "to": high, "count": int(mask.sum())})
    return {"complete_n": len(valid), "total_score": round(float(valid.mean()), 3) if len(valid) else None,
            "median": round(float(valid.median()), 3) if len(valid) else None,
            "std": round(float(valid.std(ddof=1)), 3) if len(valid) > 1 else None,
            "min": float(valid.min()) if len(valid) else None, "max": float(valid.max()) if len(valid) else None,
            "pass_rate": float((valid >= full * pass_fraction).mean()) if len(valid) and pass_fraction is not None else None,
            "pass_fraction": pass_fraction, "score_distribution": distribution}


def grade(bank, frame, table=None, min_sample=MIN_DISCRIMINATION_SAMPLE):
    validate_ids(frame)
    if min_sample < 10:
        raise ValueError("区分度最小样本不能小于10；默认30是保守实现约定，不是可靠性保证")
    table, questions = table or {}, flat(bank)
    ids = [str(question.get("id", "")) for question in questions]
    if not ids or any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("题库没有题目，或题号缺失/重复")
    for question in questions:
        score = float(question.get("score", 0))
        if not math.isfinite(score) or score <= 0:
            raise ValueError("题目满分必须为有限正数")
        kind = question.get("type")
        if kind not in {"single", "multi", "judge", "blank", "short", "comp"}:
            raise ValueError("题型不支持")
        if kind in {"single", "multi", "judge", "blank"} and question.get("answer") in (None, "", []):
            raise ValueError("客观题缺少标准答案")
        if kind in {"single", "multi"}:
            expected = letters(question["answer"])
            valid_letters = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"[:len(question.get("options", []))])
            if not expected or not set(expected) <= valid_letters or (kind == "single" and len(expected) != 1):
                raise ValueError("标准答案与选项不一致")
        if kind == "judge" and str(question["answer"]).strip().casefold() not in TRUE | FALSE:
            raise ValueError("判断题标准答案不合法")
        links(question, table)
    detail = frame[["student_id"]].copy()
    if "class" in frame:
        detail["class"] = frame["class"]
    missing = [value for value in ids if value not in frame]
    present = [value for value in ids if value in frame]
    if not present:
        raise ValueError("没有逐题列，不能从总分反推掌握度；只有总分请用--totals")
    # Explicit attendance wins. Otherwise an entirely empty response row is only
    # an absence inference, reported as such; zero is never an absence marker.
    inferred = frame[present].apply(lambda row: all(str(value).strip().casefold() in ABSENT for value in row), axis=1)
    explicit = frame.get("attendance")
    absent = explicit.astype(str).str.strip().str.casefold().isin({"缺考", "缺席", "absent"}) if explicit is not None else inferred
    detail["attended"] = ~absent
    for question in questions:
        qid = str(question["id"])
        results = [(None, "absent") if absent.loc[index] else
                   (None, "missing_column") if qid not in frame else judge_one(question, frame.loc[index, qid])
                   for index in frame.index]
        detail[qid] = [value for value, _ in results]
        detail[qid + "_tag"] = [tag for _, tag in results]
    detail["partial_total"] = detail[ids].sum(axis=1, min_count=1)
    detail["total"] = detail[ids].sum(axis=1, min_count=len(ids))
    detail["pending"] = detail["attended"] & detail["total"].isna()
    full = sum(float(question["score"]) for question in questions)
    configured_fraction = (bank.get("meta") or {}).get("pass_fraction")
    pass_fraction = float(configured_fraction) if configured_fraction is not None else None
    complete = detail[detail["attended"] & ~detail["pending"]]
    order = complete["total"].sort_values(ascending=False, kind="stable")
    k = math.ceil(len(order) * 0.27)
    enough = len(order) >= min_sample and order.nunique() > 1
    high, low = (order.index[:k], order.index[-k:]) if enough else ([], [])
    items, knowledge = [], {}
    for question in questions:
        qid, qfull = str(question["id"]), float(question["score"])
        scores = detail.loc[detail["attended"], qid].dropna()
        ratio = float(scores.mean() / qfull) if len(scores) else None
        d = float((detail.loc[high, qid].mean() - detail.loc[low, qid].mean()) / qfull) if enough else None
        options = None
        if question["type"] in ("single", "multi") and qid in frame:
            counts = {chr(65 + index): 0 for index in range(len(question.get("options", [])))}
            valid_n = invalid = 0
            for index in detail.index[detail["attended"]]:
                tag = detail.loc[index, qid + "_tag"]
                if tag == "invalid_answer": invalid += 1
                if tag not in {"correct", "wrong"}: continue
                valid_n += 1
                for letter in letters(frame.loc[index, qid]): counts[letter] += 1
            options = {"n": valid_n, "counts": counts, "invalid": invalid,
                       "pct": {letter: value / valid_n if valid_n else None for letter, value in counts.items()}}
            expected = letters(question["answer"])
            wrong = {letter: count for letter, count in counts.items() if letter not in expected}
            strongest = max(wrong, key=wrong.get) if wrong and max(wrong.values()) else None
            options.update(answer=expected, top_wrong=strongest,
                           top_wrong_pct=wrong[strongest] / valid_n if strongest and valid_n else None)
            if enough:
                high_counts = {letter: 0 for letter in counts}
                high_n = 0
                for index in high:
                    if detail.loc[index, qid + "_tag"] not in {"correct", "wrong"}: continue
                    high_n += 1
                    for letter in letters(frame.loc[index, qid]): high_counts[letter] += 1
                options.update(high_n=high_n, high_counts=high_counts)
        tags = detail[qid + "_tag"]
        item = {"id": qid, "type": question["type"], "level": question.get("level", ""), "score": qfull,
                "points": q_points(question), "kp_ids": [kid for kid, _ in links(question, table)],
                "valid_n": len(scores), "blank_n": int(tags.eq("blank").sum()),
                "pending_n": int(tags.isin(["pending", "missing_column"]).sum()),
                "invalid_score_n": int(tags.eq("invalid_score").sum()),
                "difficulty": ratio, "discrimination": d, "options": options}
        items.append(item)
        if ratio is not None:
            for kid, point in links(question, table):
                record = knowledge.setdefault(kid or point, {"kp_id": kid, "point": point, "label": kp.label(kid, table, point), "got": 0, "score": 0, "items": []})
                record["got"] += ratio * qfull
                record["score"] += qfull
                record["items"].append(qid)
    mastered = [dict(record, mastery=record["got"] / record["score"]) for record in knowledge.values()]
    stats = {"mode": "item_responses", "sample": int(detail["attended"].sum()), "absent": int(absent.sum()),
             "full_score": full, **summary(complete["total"], full, pass_fraction),
             "items": items, "knowledge": mastered, "min_discrimination_sample": min_sample,
             "group_size": k if enough else 0, "ties_in_total": bool(order.duplicated().any()),
             "data_quality": {"students": len(frame), "missing_item_columns": missing,
                              "incomplete_totals": int(detail["pending"].sum()),
                              "absence_inferred_from_empty_rows": explicit is None,
                              "invalid_scores": sum(item["invalid_score_n"] for item in items)}}
    return detail, stats


def totals_only(frame, full_score, pass_fraction=None):
    validate_ids(frame)
    if not math.isfinite(full_score) or full_score <= 0 or "total" not in frame:
        raise ValueError("总分模式需要total列与有限正数--full-score")
    detail = frame[["student_id", "total"]].copy()
    detail["total"] = pd.to_numeric(detail["total"], errors="coerce")
    invalid = detail["total"].notna() & (~detail["total"].between(0, full_score) | ~detail["total"].map(math.isfinite))
    if invalid.any(): raise ValueError("总分越界，未截断或计算")
    text = frame["total"].astype(str).str.strip().str.casefold()
    if (detail["total"].isna() & ~text.isin(ABSENT)).any(): raise ValueError("总分含无法识别的值")
    detail["attended"] = detail["total"].notna()
    stats = {"mode": "totals_only", "sample": int(detail["attended"].sum()), "absent": int((~detail["attended"]).sum()),
             "full_score": full_score, **summary(detail["total"], full_score, pass_fraction), "items": [], "knowledge": [],
             "data_quality": {"students": len(frame)}}
    return detail, stats


def to_markdown(stats, title="学情分析", demo=False):
    def show(value): return "—" if value is None else f"{value:.3g}"
    lines = ["# " + title, "", "> DEMO：演示数据，不是真实学情。" if demo else "> 仅供本次教学分析；明细留在教师受控目录。", "",
             f"出席样本{stats['sample']}人，缺考/空记录{stats['absent']}人；有完整总分{stats['complete_n']}人。",
             f"完整总分均值{show(stats['total_score'])} / {stats['full_score']:g}，中位数{show(stats['median'])}，标准差{show(stats['std'])}。",
             ("本次显式通过参考线为满分的" + show(stats["pass_fraction"] * 100) + "%，比率为" + show(stats["pass_rate"]) + "；它是本次配置，不代表课程正式政策。") if stats["pass_fraction"] is not None else "未提供通过参考线，未计算及格率。", ""]
    if stats["mode"] == "totals_only":
        lines += ["只有总分，不推断逐题难度、区分度、选项分布或知识点掌握度。"]
    else:
        lines += ["## 逐题证据", "", "|题号|有效评分人数|得分率|区分度|未评/缺列|越界分|", "|---|---|---|---|---|---|"]
        for item in stats["items"]:
            lines.append(f"|{item['id']}|{item['valid_n']}|{show(item['difficulty'])}|{show(item['discrimination'])}|{item['pending_n']}|{item['invalid_score_n']}|")
        lines += ["", "## 选项分布", "", "|题号|合法选项作答人数|选项人数|最常见错误项|非法选项作答|", "|---|---|---|---|---|"]
        for item in stats["items"]:
            options = item.get("options")
            if options:
                counts = "、".join(f"{letter}:{count}" for letter, count in options["counts"].items())
                lines.append(f"|{item['id']}|{options['n']}|{counts}|{options['top_wrong'] or '—'}|{options['invalid']}|")
        lines += ["", "选项分母为合法选项作答人数，不含空白与非法填涂；多选每人可贡献多个字母，选项人数之和不等于人数。完整高分组的选项人数仅在D可计算时写入统计JSON，不把缺失组别当0。"]
        lines += ["", "## 知识点得分表现", "", "|知识点|得分率（非能力标签）|题号|", "|---|---|---|"]
        for record in stats["knowledge"]:
            lines.append(f"|{record['label']}|{show(record['mastery'])}|{'、'.join(record['items'])}|")
        lines += ["", "## 解释与下一步", ""]
        for record in stats["knowledge"]:
            if record["mastery"] < 0.6:
                lines.append(f"- 观察：{record['label']}在题{'、'.join(record['items'])}的加权得分率为{record['mastery']:.1%}。解释待核；先检查题意与答案，再选一题变式检查，不据此给学生贴标签。")
        lines += ["", "## 数据口径", "", f"- 区分度只在完整总分样本至少{stats['min_discrimination_sample']}且总分有差异时，按高低各27%（向上取整）计算。阈值是实现中的保守约定，不保证统计可靠性。",
                  "- 分组边界可能有同分，按输入稳定排序；有同分时D更需谨慎，不能作为学生排序依据。",
                  "- 出席者客观题空白计0，主观题未评、缺列或给分越界不当作0；未完成总分不进均分与及格率。",
                  "- 缺考不等于0分。未提供attendance时，全空行仅按缺考推定，需要教师核对。",
                  "- 多知识点题的得分贡献会计入每个挂载点，不能声称准确定位了各知识点能力。",
                  "- 数据质量记录：" + json.dumps(stats["data_quality"], ensure_ascii=False)]
    lines += ["", "## 完整总分实际分布", "", "区间左闭右开，最后一档含满分；只使用已取得完整总分，不由均值拟合。", "", "|分数区间|人数|", "|---|---|"]
    for group in stats["score_distribution"]:
        lines.append(f"|{group['from']:g}–{group['to']:g}|{group['count']}|")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bank", nargs="?")
    parser.add_argument("answers", nargs="?")
    parser.add_argument("--totals", help="只有总分时指定CSV，需student_id,total列")
    parser.add_argument("--full-score", type=float)
    parser.add_argument("--pass-fraction", type=float, help="显式通过参考比例0至1；省略且题库也未配置时不计算及格率")
    parser.add_argument("--kp")
    parser.add_argument("--min-discrimination-sample", type=int, default=MIN_DISCRIMINATION_SAMPLE)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("-o", "--out-prefix", required=True)
    args = parser.parse_args(argv)
    if args.totals:
        if args.bank or args.answers or not args.full_score: parser.error("总分模式只用--totals与--full-score")
        frame = pd.read_csv(args.totals, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        detail, stats = totals_only(frame, args.full_score, args.pass_fraction)
        title = "总分分布分析"
    else:
        if not args.bank or not args.answers: parser.error("逐题模式需要题库与作答CSV")
        bank = json.loads(Path(args.bank).read_text(encoding="utf-8-sig"))
        if args.pass_fraction is not None:
            bank.setdefault("meta", {})["pass_fraction"] = args.pass_fraction
        frame = pd.read_csv(args.answers, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        detail, stats = grade(bank, frame, kp.load(args.kp), args.min_discrimination_sample)
        title = (bank.get("meta") or {}).get("title", "学情分析")
    demo = args.demo or ("dataset_kind" in frame and frame["dataset_kind"].eq("DEMO").all())
    prefix = Path(args.out_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    detail.to_csv(str(prefix) + "_明细.csv", index=False, encoding="utf-8-sig")
    Path(str(prefix) + "_统计.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    Path(str(prefix) + "_报告.md").write_text(to_markdown(stats, title, demo), encoding="utf-8")
    print("已生成本地明细、汇总统计与报告；未发布，未修改原始文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
