---
name: ai-course-analytics
display_name: 课程学情分析
display_name_en: Course Learning Analytics
description: 教师提供作答CSV、逐题给分、总分或实验评分后，生成本地统计、聚合分析报告与图。按数据实际支持的范围分析，不从总分反推知识点能力，不自动评主观题文本，不对学生排名或写回正式成绩。
description_zh: 从真实作答与评分提取逐题证据、统计与改课建议，明确缺考和未评。
description_en: Analyze authorized response data or total scores with explicit missing-data handling and evidence-linked teaching observations.
version: 1.5.0
author: 人工智能概论课程组
---

# 课程学情分析

服务教师项目。先看数据能支持什么，不先套报告。沿用实际已有题库、列名、分值、知识点映射与课程规则，仅补齐必要缺口。原始文件不修改，明细含学生标识只能留在教师受控目录，不能称其已经匿名化。默认报告只给聚合统计，不列个人ID、姓名、分数或排名，不公开上传、不写回成绩系统。

| 实际资料 | 可以交付 | 不作结论 |
| --- | --- | --- |
| 逐题作答与标准答案/分值 | 逐题得分率、选择分布、与题号对应的知识点得分表现 | 不把一次测验当完整能力评定 |
| 只有总分 | 均值、中位数、分布及明确参考线下的通过比例 | 不反推知识点、区分度或误区 |
| 只有提问记录 | 去标识后的主题整理 | 不猜个人成绩及因果 |
| 没有真实数据 | 分析模板；用户要求演示时用明确DEMO数据 | 不生成真实学情结论 |

## 执行

1. **检查口径。** 读取[指标规则](references/analysis-rules.md)。逐题CSV一人一行，student_id仅作本地关联键，列名对应题号；主观题填人工给分，答案文本不会自动判分。缺失ID或重复记录停止，先核对重考/重复导出，不自动保留最后一条。未知考试版本不能混算。
2. **明确缺失。** 有 `attendance` 列时“缺考/absent”是明确缺考；没有时全空作答行只是缺考推定，需要核对。出席者客观题空白计0；主观题空白/文本、缺题列或越界给分不计0，不形成完整总分。0分不是缺考。只有总分时用专用模式。
3. **运行统计。** `grade.py` 输出教师本地明细CSV、统计JSON与聚合MD。完整总分样本才进入全卷均值；通过比例仅在本次明确配置 `--pass-fraction` 或题库meta.pass_fraction时计算，不默认60%。未评/缺列数另列。知识点用本次明确提供的 `--kp` 映射；没有表就保留输入名称与编号，不套单元3示例。默认区分度门槛为30个完整总分样本，按高低各27%计算，阈值只是保守实现约定，不是可靠性保证。
4. **画已有数据。** `charts.py` 只画统计JSON里真实存在的得分率、D与知识点表现，缺数据就跳过对应图，不用均值/标准差伪造正态分布。图与报告不带个人排名。
5. **解释与建议分开。** 每个建议挂真实题号与可见统计；“得分低”是观察，“可能没理解”是待核解释。先查题意、答案、教学覆盖，再建议变式题复核；不凭一次小测给学生贴能力标签，也不声称证明教学干预有效。

## 命令

脚本从本Skill安装根解析，数据与输出从教师项目解析。使用项目专用环境，依赖见 `requirements.txt`。

```text
python "<SKILL_DIR>/scripts/grade.py" "题库.json" "作答.csv" --kp "项目知识点.csv" -o "outputs/本次测验"
python "<SKILL_DIR>/scripts/grade.py" --totals "总分.csv" --full-score 100 -o "outputs/总分分析"
python "<SKILL_DIR>/scripts/charts.py" "outputs/本次测验_统计.json" -o "outputs/本次测验图"
```

省略 `--kp` 不会自动套示例。总分CSV需要student_id,total；越界或无法识别的总分会停止，不悄悄截断。

## 合并实验评分

`merge_scores.py` 接受教师本地的互评与AI评分，先在原始层面拒绝越界和重复，再做暂定等权平均；并不认为AI评分天然正确。默认只有两侧都有分才合并，单侧缺失不冒充完整；用户明确采用可用侧时才加 `--allow-single-source`。`--experiments 1,2,3` 可指定实际实验清单，没有时只分析输入出现的编号，不默认6次实验。跨实验均值是有效记录均值，不能当正式课程成绩。

```text
python "<SKILL_DIR>/scripts/merge_scores.py" --peer "互评.csv" --ai "AI评分.csv" --experiments 1,2,3 -o "outputs/评分合并草稿"
```

## 演示和交付

`assets/demo_answers.csv` 与 `make_demo.py` 只用于演示，标识以DEMO开头；演示报告显式带DEMO，不能改名装作真实结果。交付真实文件链接、使用的数据范围、清洗/排除数量与局限。个别辅导明细仅在教师明确要求时另外处理，不能把完整学号或尾号称为匿名化。[课程口径](references/course-context.md)和[隐私检查](references/deid-rules.md)不授予访问、发送或发布权限。
