---
name: ai-intro-course-setup
display_name: 人工智能概论教师项目快捷安装
display_name_en: AI Course Teacher Setup
description: 当用户要求安装、配置或更新《人工智能概论》教师项目时使用。配置教师专家团、共享教学Skill、AI周报和自动签到Skill；按用户明确选择接入WorkBuddy原生周报定时任务或本机签到任务。
description_zh: 自动配置教师专家团和教师助手，保留原项目设置并核对安装结果。
description_en: Set up or update the AI course teacher experts and their shared Skill using available WorkBuddy management capabilities.
version: 1.4.0
author: 人工智能概论课程组
examples_zh:
  - 把教师专家团和教师助手配置到我的备课项目，能自动完成的直接做。
  - 更新这个教师项目的课程套件，保留其他专家、技能和指令。
examples_en:
  - Set up the AI course experts and shared Skill in my teacher project.
  - Update my teacher project while preserving unrelated settings.
---

# 教师项目快捷安装

仅在用户提出教师套件安装、配置、更新或安装检查任务时运行。用途固定为教师项目，不询问模式。日常教学任务交给 `ai-intro-course`，不要反复启动安装。

先完整读取 [给 WorkBuddy Agent 的安装配置说明](references/installation.md)。收到setup安装包时再读其中的 `assets/install-plan.json`，按清单核对真实资源和载荷位置。收到GitHub源码时，按说明使用源码实际路径；未构建的assets目录不能当作已经存在。不要凭文件夹名猜测平台管理接口。

优先用当前实际可用的WorkBuddy原生管理能力创建或更新五位教师专家、安装教师助手并关联目标项目。能自动完成就直接执行，不让用户逐项填写。目标项目无法确定时，先完成独立检查，再只补齐项目位置；不要为选择用途增加一步。

安装后分别回读资源登记、项目关联与资料正文读取。文件写入或请求返回不能替代这些结果。按资源ID和内容指纹复用已有登记，不因显示名称变化创建副本。

原生管理能力不足时，可在用户明确指定的本地项目目录中，使用本包 `scripts/install_project.py` 配置项目级 `.codebuddy` 文件。具体参数、冲突处理与结果口径见安装说明。此路径不证明云端“我的专家”或新建项目选择列表已经注册。

同时安装随附的独立 `workbuddy-auto-signin` Skill，不绑定到五位教学专家。只复制或注册Skill不会启动自动签到。用户明确要求“同时开启自动签到与成长中心”时，读取该Skill的说明并继续自动配置本机任务，不重复询问已明确选择的功能；只有教师课程安装请求时，先完成课程和Skill安装，再简短询问是否开启此附加功能。已明确拒绝或暂不开启时，不再询问，也不据此卸载已有任务；不能从下载行为推断持续账号操作授权。

同时安装独立 `ai-frontier-weekly` 周报Skill并关联教师项目，不改变五位专家的共享教学Skill绑定。用户要求定期生成时，读取周报的 `references/workbuddy-setup.md`，按实际原生工具创建或更新项目定时任务，并回读真实ID与时间；不把配置模板当已经注册。普通安装不创建任务、不生成当期新闻、不发布网页。已有时间、教师信源配置及发布范围保留，不能因升级改掉。

只管理本套件可识别的资源；保留其他专家、技能、项目指令和会话。不要改资料分享范围、账号权限或全局安全设置，不索取凭据，不调用猜测的接口。最后用简短结果说明已完成什么、验证到哪一步、还有哪项需要用户处理。
