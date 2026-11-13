---
name: ai-course-visual
display_name: 课程关系图与素材
display_name_en: Teaching Diagram Production
description: 为课件、讲义或复习材料制作实际SVG和PNG关系图时使用。支持流程、闭环、层级、对比矩阵、知识卡和时间轴；不用于获取照片、仿制教材原图或把示意图当作实验结果。
description_zh: 按教学关系生成SVG与PNG，校验节点、图注、来源及图片尺寸。
description_en: Generate editable SVG and PNG teaching diagrams with source captions and checked relationship structures.
version: 1.5.0
author: 人工智能概论课程组
---

# 课程关系图与素材

先确定图要解释的关系和挂载位置，复用当前项目已有的内容及版式；只有信息不足会影响结果时再问。图服务教学，不因“好看”改动课程事实。

1. 按[课程依据](references/course-context.md)核对节点及关系。流程选`flow`、反馈选`loop`、层次选`tree`、同维比较选`compare`、单概念选`card`、阶段发展选`timeline`，详见[选图规则](references/figure-rules.md)。
2. 写配图计划，结构见 `assets/sample-figures.json`。每图含`id,type,title,caption,source`及对应节点。`id`只用字母、数字、下划线和短横线，不作为输出路径。数字是自拟或示意数据时明确标“示意”；没有实测来源不伪装曲线或统计图。
3. 在项目目录运行，资源从实际Skill目录解析：

```text
python "<SKILL_DIR>/scripts/build_figures.py" "outputs/配图计划.json" --check --strict
python "<SKILL_DIR>/scripts/build_figures.py" "outputs/配图计划.json" -o "outputs/figures" --strict
```

4. 同一张图输出SVG与200dpi PNG；SVG文字保持可编辑。检查箭头方向、节点层次、图注和最终图片；格式检查不能判断教学关系一定正确。中文字体不可用时明确提示并核对渲染，不能以生成文件成功代替可读性检查。
5. 交给课件或讲义时引用实际输出文件及图源，沿用用户指定配色与版式约束。照片、截图与教材原件不属于本生成器范围；不能以关系示意图冒充原图。来源与个人信息按[分发检查](references/deid-rules.md)处理。

本Skill不发布网页、不改课程政策，不自动处理周报配图；周报继续使用可溯源原文图规则。`requirements.txt`列明matplotlib依赖，安装放项目环境。样例仅演示结构，不代表读过真实课件或取得原图使用许可。
