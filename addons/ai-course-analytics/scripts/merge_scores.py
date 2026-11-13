"""Merge local peer/AI scores using an explicitly described provisional rule.

No course weighting, experiment count, official grade or public ranking is inferred.
Invalid raw scores and ambiguous duplicate records stop before any output is written.
"""
from __future__ import annotations
import argparse
import math
from pathlib import Path
import pandas as pd

ID_KEYS = ("student_id", "学号", "sid", "id")
EXP_KEYS = ("exp", "experiment", "实验", "实验序号", "实验次")
SCORE_KEYS = ("score", "成绩", "分数", "得分")


def _pick(frame, keys, label):
    found = [key for key in keys if key in frame]
    if not found: raise ValueError(label + "缺少所需列")
    return found[0]


def norm(path, label):
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    columns = [_pick(frame, keys, label) for keys in (ID_KEYS, EXP_KEYS, SCORE_KEYS)]
    result = frame[columns].copy()
    result.columns = ["student_id", "exp", "score"]
    result["student_id"] = result["student_id"].str.strip()
    result["exp"] = result["exp"].str.strip()
    text = result["score"].str.strip()
    result["score"] = pd.to_numeric(text, errors="coerce")
    if (result["score"].isna() & ~text.str.casefold().isin(["", "缺考", "未评", "nan", "none"])).any():
        raise ValueError("给分列包含无法识别的内容，未按0或缺考处理")
    result["source"] = label
    return result


def merge(peer, ai, max_score=100, allow_single_source=False, experiments=None):
    if not math.isfinite(max_score) or max_score <= 0: raise ValueError("满分需为有限正数")
    both = pd.concat([peer.copy(deep=True), ai.copy(deep=True)], ignore_index=True)
    if not {"student_id", "exp", "score", "source"} <= set(both): raise ValueError("合并输入缺少必要字段")
    if both.empty: raise ValueError("没有评分记录")
    if both[["student_id", "exp"]].isna().any().any() or both[["student_id", "exp"]].astype(str).apply(lambda col: col.str.strip().eq("")).any().any():
        raise ValueError("学生标识或实验编号缺失")
    if both.duplicated(["student_id", "exp", "source"]).any():
        raise ValueError("同一学生/实验/来源出现重复记录，需核对重评与重复导出，未自动保留最后一条")
    raw = pd.to_numeric(both["score"], errors="coerce")
    if (both["score"].notna() & raw.isna()).any(): raise ValueError("给分不是数字")
    if (raw.notna() & (~raw.between(0, max_score) | ~raw.map(lambda value: pd.isna(value) or math.isfinite(value)))).any():
        raise ValueError("原始给分越界或非有限数；未平均、截断或输出成绩")
    both["score"] = raw
    if not set(both["source"]) <= {"peer", "ai"}: raise ValueError("评分来源应为peer或ai")
    observed = sorted(both["exp"].astype(str).unique())
    exps = [str(value).strip() for value in experiments] if experiments else observed
    if not exps or len(set(exps)) != len(exps) or not set(observed) <= set(exps):
        raise ValueError("实验清单为空、重复或遗漏了输入中的实验")
    index = pd.MultiIndex.from_product([sorted(both["student_id"].astype(str).unique()), exps], names=["student_id", "exp"])
    wide = both.pivot(index=["student_id", "exp"], columns="source", values="score").reindex(index)
    for column in ("peer", "ai"):
        if column not in wide: wide[column] = float("nan")
    wide["single_source"] = wide[["peer", "ai"]].notna().sum(axis=1).eq(1)
    wide["score"] = wide[["peer", "ai"]].mean(axis=1, skipna=allow_single_source)
    wide["no_score"] = wide["score"].isna()
    detail = wide.reset_index().sort_values(["student_id", "exp"]).reset_index(drop=True)
    return detail, {"students": detail["student_id"].nunique(), "pairs": len(detail), "records": len(both),
                    "only_one_side": int(detail["single_source"].sum()), "no_score": int(detail["no_score"].sum()),
                    "experiments": exps, "experiment_list_explicit": bool(experiments),
                    "allow_single_source": allow_single_source, "max_score": max_score,
                    "status": "临时统计，未经课程正式成绩政策确认"}


def per_student(detail):
    grouped = detail.groupby("student_id")["score"]
    return pd.DataFrame({"有效实验次数": grouped.count(), "有效记录均值_非正式成绩": grouped.mean()}).reset_index()


def to_md(detail, students, quality, title="实验评分合并（统计草稿）"):
    mode = "单侧可暂用，并标单来源" if quality["allow_single_source"] else "单侧缺失时不计算该次合并分"
    lines = ["# " + title, "", "> 临时统计，不是正式课程成绩；明细含原始学生标识，仅留教师本地受控范围。", "",
             "计算约定：两侧都有时等权平均；" + mode + "。个人跨实验均值只对有效记录计算。", "",
             f"参与{quality['students']}人，学生×实验{quality['pairs']}条；单侧{quality['only_one_side']}条，未形成合并分{quality['no_score']}条。",
             "实验范围：" + "、".join(quality["experiments"]) + ("（用户显式清单）" if quality["experiment_list_explicit"] else "（仅输入出现过的编号，无法推断完全漏导的实验）"),
             "", "|实验|有效人数|均值|", "|---|---|---|"]
    for experiment, group in detail.groupby("exp"):
        valid = group["score"].dropna()
        average = f"{valid.mean():.2f}" if len(valid) else "—"
        lines.append(f"|{experiment}|{len(valid)}|{average}|")
    lines += ["", "报告不列学生ID、姓名、个人成绩或排名。个别辅导只在教师明确要求时另交受控明细，不把学号称为匿名化。",
              "平均差异只能提示评分口径可能不同，不能据此断言学生能力、抄袭或AI评分优劣。"]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peer", required=True)
    parser.add_argument("--ai", required=True)
    parser.add_argument("-o", "--out-prefix", required=True)
    parser.add_argument("--title", default="实验评分合并（统计草稿）")
    parser.add_argument("--max-score", type=float, default=100)
    parser.add_argument("--allow-single-source", action="store_true")
    parser.add_argument("--experiments", help="显式实验编号，逗号分隔；不预设6次")
    args = parser.parse_args(argv)
    detail, quality = merge(norm(args.peer, "peer"), norm(args.ai, "ai"), args.max_score,
                            args.allow_single_source, args.experiments.split(",") if args.experiments else None)
    students = per_student(detail)
    prefix = Path(args.out_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    detail.to_csv(str(prefix) + "_合并明细.csv", index=False, encoding="utf-8-sig")
    students.to_csv(str(prefix) + "_学生总表.csv", index=False, encoding="utf-8-sig")
    Path(str(prefix) + "_统计.md").write_text(to_md(detail, students, quality, args.title), encoding="utf-8")
    print("已生成教师本地合并草稿；没有排名、发布或写回正式成绩。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
