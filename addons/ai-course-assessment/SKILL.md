---
name: ai-course-assessment
display_name: 课程出题与组卷
display_name_en: Course Assessment Builder
description: 为教师把知识点或已有题目制成双向细目表、学生题面与教师答案DOCX、项目量规及复核记录。用户明确要组卷、正式文件或量规时调用；零散课堂练习可仍由共享教学Skill直接完成。
description_zh: 出题、细目表、分离的学生卷与教师卷，以及评分量规文件。
description_en: Build teacher-requested assessment blueprints, separate student and teacher papers, and explicit scoring rubrics.
version: 1.5.0
author: 人工智能概论课程组
---

# 课程出题与组卷

在教师项目中完成任务，不重新询问教师/学生模式。学生卷是给教师分发的产物，不是另外创建学生账号或项目。题库与答案只使用当前账号和工具实际有权取得的资料；默认不发布、不写回正式题库或成绩系统。

先用项目实际资料检索取得对应章节和知识点。已有用途、分数、时长、题型与交付形式直接沿用；只补问会改变试卷范围的缺项。用户只要随堂练习时，不强制100分、120分钟或期末口径。缺正式规则可提建议，并标清“建议稿”。[课程口径](references/course-context.md)和[题型规则](references/item-rules.md)提供执行边界。

## 执行

1. **确定考查范围。** 列实际知识点及来源，知识点表沿用项目明确提供的CSV。脚本通过 `--kp` 接收；没有表就保留名称与输入已有编号，不自动加载包内单元3示例，也不自造编号冒充正式课程结构。
2. **先做细目表。** 记录知识点、题型、认知动作、分值和时间。`make_blueprint.py` 可提供建议分配，预设不是课程政策。细目表里的认知层次不是实测难度，不能写成已证明的信效度。
3. **写题与答案。** 依实际内容写题库JSON，结构参考 `assets/sample-questions.json`，该文件是DEMO而非正式题库。每题要有唯一id、type、stem、score、points、标准答案/评分点和来源。选项对应真实误解；材料题自带必要材料。主观题rubric合计与分值一致，允许合理替代路径。
4. **复核并导出。** 运行 `build_paper.py`，核对题号、题干/选项重复、答案范围、填空数、rubric与总分、细目表覆盖。发现error不生成试卷，修好再出。分别生成学生卷、教师卷和复核记录；学生卷不写答案、解析和评分细则。结构检查不能判断语义多解或内容正确，需教师审读。
5. **量规按显式规则生成。** `build_rubric.py --dims` 使用教师给出的维度JSON；仅演示时用 `--example`。不套用其他课程的固定6维度、成绩比例、处罚红线或“AI感”判断。

## 命令与路径

脚本路径从本Skill实际安装根解析，输入输出从教师项目解析，以下把 `<SKILL_DIR>` 换成真实目录。

```text
python "<SKILL_DIR>/scripts/make_blueprint.py" --points "知识点.txt" --total 20 --profile 随堂 --kp "项目知识点.csv" -o "outputs/细目表.json" --md "outputs/细目表.md"
python "<SKILL_DIR>/scripts/build_paper.py" "outputs/题库.json" --blueprint "outputs/细目表.json" --kp "项目知识点.csv" -o "outputs/单元测" --strict
python "<SKILL_DIR>/scripts/build_rubric.py" --dims "评分维度.json" --total 100 -o "outputs/评分表.docx"
```

没有项目编码表时去掉 `--kp`，其他流程照常，不把示例当真实课程数据。Word生成需 `requirements.txt` 中的python-docx；使用项目环境，不自动改全局依赖。

## 交付

按请求交完整文件、必要来源和影响采用的缺口。用户只要题目时不增加无关实验量规；只有组卷时才交细目表与复核。未渲染或打印预览时说明尚未检查版式，不能把文件生成说成视觉验收。学生版交前检查正文、备注、页眉页脚和文件属性，保留教师参考答案在独立文件。[隐私检查边界](references/deid-rules.md)不等于全文匿名化保证。
