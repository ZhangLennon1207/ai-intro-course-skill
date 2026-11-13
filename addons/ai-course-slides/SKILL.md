---
name: ai-course-slides
display_name: 课程课件生成
display_name_en: Course Slide Production
description: 将已核对的教材、教师课件或教学内容制作成实际可编辑PPTX时使用。支持教师模板分析、故事板、覆盖核对、讲稿和图片渲染检查；仅需教案或PPT提纲时仍由教师助手完成。
description_zh: 从课程依据生成可编辑PPTX，保留教师模板并检查内容覆盖与版式。
description_en: Build editable teaching PowerPoint files from verified material, preserving supplied templates and checking declared coverage.
version: 1.5.0
author: 人工智能概论课程组
---

# 课程课件生成

本Skill承担实际PPTX制作，不接管主管和教学设计专家。收到主管给定的目标、资料、受众、时长或用户直接请求后，先复用当前项目已有信息。缺少主题或必要原件时再问；未指定模板就可使用内置模板并说明，不要求用户重新回答一轮固定问题。

## 制作流程

1. 读取[课程依据规则](references/course-context.md)。通过当前WorkBuddy真实资料工具取得相关正文，或读取用户指定本地文件。知识库节点ID不是已取得正文；本包不调用隐藏的本机接口。只有相关片段时说明覆盖限制，不保证原件顺序已还原。
2. 有教师原件时优先沿其内容顺序和模板，按本次要求取舍，不把别的学校、课程或样例课时当权威。需要原样保真时用原件另存修改，不声称重绘模板能像素级复原。只有扫描图时说明文字抽取限制。
3. 写故事板JSON：`meta`说明主题、受众和依据；`coverage`列本次知识点；每页`covers`注明实际主讲点；`slides`按本次时长编排。格式见 `assets/sample-storyboard.json` 与[故事板说明](references/storyboard.md)。样例只演示结构，不是本次教材证据。
4. A/B/C/D是可选的排版与解释预设，见[深度选择](references/depth-modes.md)，不要求教师选择字母。页数由用户要求及内容决定，没有固定的26页或90分钟验收线。模型概念、公式和例子的准确性仍需依据原文核对。
5. 在项目工作目录运行下面命令，`<SKILL_DIR>`为本Skill真实安装位置；不要把输出写进安装目录。

```text
python "<SKILL_DIR>/scripts/envcheck.py"
python "<SKILL_DIR>/scripts/build_deck.py" "outputs/storyboard.json" "outputs/课程课件.pptx" --check --strict
```

有教师PPTX时先运行 `inspect_template.py 原件.pptx -o outputs/profile.json --assets outputs/template-assets`，再给生成器加 `--template 原件.pptx --profile outputs/profile.json`。原件只读，不覆盖。没有完整原件时不宣称母版、动画及字体已经保真。

6. 用 `coverage_check.py` 核对已声明知识点与页内对应；有教师原件时可用 `diff_deck.py` 查疑似遗漏。结构检查不能证明知识点清单完整或内容正确。文案检查 `voice_check.py` 只提示措辞线索，不能为降分删事实或改术语。
7. 有实际图页就使用真实存在的图，可调用独立 `ai-course-visual` 生成SVG/PNG关系图；`make_figures.py`的内置教学图也只作示意。缺图时改页型或报告缺口，不能交灰框。用户要照片或原件插图时不能用示意图冒充。
8. 需要逐页视觉验收时运行 `render_check.py 输出.pptx 新的渲染目录`，查看实际图片。它仅在可用PowerPoint/pywin32环境运行；缺失返回未验证，不把代码检查写成渲染通过。按用户需要再用 `make_peripherals.py` 导出速记卡、提问单和讲稿提示，不强制附加全部文件。

## 交付

交实际PPTX、必要来源及仍影响使用的限制。默认不公开发布、不上传原件、不改课程政策。学生分发版需检查答案、教师备注、隐藏页和个人信息；内部制作文件不自动成为分发稿。所有相对资源从本Skill根解析，输入和输出从教师项目解析。

依赖见 `requirements.txt`，可选PDF大纲与Office渲染依赖见 `requirements-optional.txt`。依赖安装放项目虚拟环境；`envcheck.py --install`仅允许当前解释器已经是虚拟环境时显式运行，不改全局Python。
