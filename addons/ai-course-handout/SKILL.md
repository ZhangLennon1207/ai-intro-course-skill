---
name: ai-course-handout
display_name: 课程讲义编写
display_name_en: Course Handout Production
description: 将课程正文、课件故事板或章节内容制作成实际Word讲义时使用。输出教师参考版与去除练习答案的分发版，可保留来源和知识点编号；普通课堂解释不必启动文档生成。
description_zh: 生成可编辑Word讲义，分开教师答案与学生分发内容，并保留来源对应。
description_en: Produce editable Word handouts with separate teacher answers and student-facing files from verified teaching material.
version: 1.5.0
author: 人工智能概论课程组
---

# 课程讲义编写

服务教师制作讲义；“学生版”指教师要分发的文件，不是另设学生项目或身份模式。按本次要求交付教师版、学生版或两版，未要求分发时不强制另做学生版。复用当前主题、受众和资料，必要输入缺失时再补齐，不重复询问已提供内容。

1. 按[课程依据](references/course-context.md)取得正文，确认本次范围。使用已有故事板时，可运行 `from_slides.py 故事板.json -o outputs/讲义源.json` 形成待补齐骨架；骨架不等于已经写好讲义，不能直接照抄PPT讲稿。
2. 采用 `assets/sample-handout.json` 的结构：每节有主要结论、概念及边界、正反例、易错点、分层练习；明确题面和`answer`字段。样例是演示资料，不能当作当前课程权威或核过页码的依据。
3. 符号、案例与解释按实际读到的来源核对，补充内容注明自拟或来源。默认版式见[讲义样式](references/handout-style.md)，用户提供模板或排版要求时优先遵从；这些默认值不是学校规定。
4. 跨课件、讲义、出题和学情统一使用当前项目的知识点映射。显式提供 `--kp "实际编码表.csv"`，CSV列至少为`kp_id,name`，可加`section,order`。没有表时保留输入中的名称和编号，不自动套用单元3；`assets/knowledge-points-example.csv`只供结构示例。
5. 从项目目录运行，`<SKILL_DIR>`替换为真实安装位置：

```text
python "<SKILL_DIR>/scripts/build_handout.py" "outputs/讲义源.json" -o "outputs/讲义-教师版.docx" --md "outputs/讲义-教师版.md" --check --strict
python "<SKILL_DIR>/scripts/build_handout.py" "outputs/讲义源.json" -o "outputs/讲义-学生版.docx" --student --check --strict
```

需要编码校验时两条命令都加同一个`--kp`。脚本分别生成文件，教师版含练习参考答案，学生版不写`answer`字段；这不能自动识别教师把答案写在题干、概念或图片里的语义泄漏，交付前仍须检查分发文件。

6. 检查五段结构、练习字段、实际DOCX正文、来源及版式。机器检查不等于事实审查和打印预览；无法渲染时明确标注视觉验收未执行。不为讲义制作更改课程成绩、学时或考场携带规则。

输出只写项目工作目录，保留原件。默认内部交教师，需要分发时再检查答案、文件属性、备注及个人信息，见[分发检查](references/deid-rules.md)。依赖是 `requirements.txt` 中的python-docx；在项目虚拟环境按需安装，不在Skill加载时自动改环境。
