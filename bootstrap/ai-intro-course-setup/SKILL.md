---
name: ai-intro-course-setup
display_name: 人工智能概论课程快捷安装
display_name_en: AI Course Quick Setup
description: 当用户要求安装、配置或更新《人工智能概论》课程专家团与课程技能时使用。检查WorkBuddy实际管理能力，自动完成可支持的注册与项目关联，并核实结果。
description_zh: 配置课程主管、四位专家和一个课程Skill；优先自动注册、关联项目和检查安装结果。
description_en: Install or update the AI course expert suite and its shared Skill using the available WorkBuddy management capabilities.
version: 1.1.0
author: 人工智能概论课程组
examples_zh:
  - 把课程专家团和课程Skill安装到我的教师备课项目，能自动配置的直接完成。
  - 更新这个项目的人工智能概论课程套件，保留其他专家、技能和项目指令。
examples_en:
  - Install the AI course experts and shared Skill in my teaching project.
  - Update the course suite while preserving unrelated project settings.
---

# 课程快捷安装

仅在用户提出课程套件安装、配置、更新或安装检查任务时运行。日常备课与答疑交给 `ai-intro-course`，不要反复启动安装流程。

先完整读取 [给 WorkBuddy Agent 的安装配置说明](references/installation.md)，再读取本包的 `assets/install-plan.json`。安装清单给出真实资源名称和载荷位置；不要凭文件夹名猜测平台管理接口。

优先使用当前会话实际可用的 WorkBuddy 原生管理能力创建或更新专家、安装课程 Skill、关联目标项目。能够自动完成就直接执行，不要求用户逐项填写或点击。项目或用途无法从当前上下文确定时，先完成与这些信息无关的材料检查，再只补齐缺少的目标信息。

安装后分别回读：专家和课程 Skill 是否实际登记、项目是否实际关联、资料正文是否能读取。写出文件、发出请求或生成一段配置说明，都不能记为这些检查已经通过。

原生管理能力不足时，可在用户明确指定的本地项目目录中，使用本包 `scripts/install_project.py` 配置项目级 `.codebuddy` 文件。具体参数、冲突处理与结果口径见安装说明。此路径不证明云端“我的专家”或新建项目选择列表已经注册。

只管理本套件可识别的资源；保留其他专家、技能、项目指令和会话。不要改资料分享范围、账号权限或全局安全设置，不索取凭据，不调用猜测的接口。最后用简短结果说明已完成什么、验证到哪一步、还有哪项需要用户处理。
