---
name: workbuddy-auto-signin
display_name: WorkBuddy自动签到与成长中心
display_name_en: WorkBuddy Sign-in and Growth Automation
description: 当用户要求安装、检查或卸载本机WorkBuddy自动签到与成长中心定时任务时使用。基于固定版本的88lin/workbuddy-auto-signin，在Windows当前用户下配置后台任务。
description_zh: 快捷配置本机自动签到和成长中心，检查定时任务并支持卸载。
description_en: Install, inspect, or remove current-user Windows tasks for the pinned WorkBuddy sign-in and growth add-on.
version: 1.3.0
author: 人工智能概论课程组；上游脚本88lin（MIT）
examples_zh:
  - 同时安装自动签到与成长中心，按说明配置后台任务。
  - 检查自动签到配置，告诉我下一次运行时间。
  - 卸载本套件的自动签到定时任务，保留日志。
examples_en:
  - Set up WorkBuddy sign-in and growth automation on this Windows computer.
  - Remove the scheduled tasks created by this add-on and keep its logs.
---

# WorkBuddy自动签到与成长中心

此Skill独立于教师备课，由安装入口一并提供。用户只做备课时不执行它；安装Skill文件也不会创建后台任务。

先读[安装与停用说明](references/usage.md)。本包带有固定提交的上游源码、MIT许可和SHA-256清单，不下载或执行动态main分支。它需要已登录的WorkBuddy和现有Python，不是WorkBuddy官方功能。

开启前，用一句话告知：后台运行将读取本机WorkBuddy登录态，每天签到并处理成长中心，包含使用补登卡、抽奖机会和能量。用户已明确要求同时开启这些功能时直接执行；只要求安装教师课程或只下载文件时，不据此开启账号操作，可简短询问是否一并开启。授权不沿用到其他使用者或其他电脑。

在此Skill目录运行 `python scripts/manage_signin.py plan`，查看锁定版本、预期哈希和运行范围；安装时才实际校验文件与依赖。按用户意图执行：

- **开启**：`python scripts/manage_signin.py install --mode signin-growth`。使用本套件带归属检查的安装器，不直接运行上游 `install-windows.ps1`。
- **检查**：`python scripts/manage_signin.py status`。检查本地文件和Windows任务，不读取登录文件、不联网签到。
- **卸载**：`python scripts/manage_signin.py uninstall`。只移除本套件拥有的任务，保留脚本和日志。

本版只提供完整“签到与成长中心”配置。如果用户只要求签到，先说明范围不符，不能用完整配置冒充只签到；也不要自行编造新的接口或刷完成事件。

安装器不立即调用业务接口。成功后回读两个任务的动作与时间，区分“已配置后台任务”和“实际签到已成功”。没有真实运行记录就保持签到结果未验证。遇到登录失效、接口变更、任务冲突或脚本修改时报告具体问题，不循环重试、不覆盖外部任务，不提升系统权限。

不要让用户粘贴token、解密密钥或登录文件，不把凭据写入提示词、GitHub或安装回执；运行时由本机上游脚本处理现有登录态。它不会完成实质性的聊天、编程、邀请或分享任务，任务奖励仅向服务器已标记完成的项目申请领取。
