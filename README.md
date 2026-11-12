# 人工智能概论教师项目

本项目服务于教师备课：检索课程资料，生成教案、课堂活动、实验、题目和课堂答疑准备材料。保留五位专家共用一个课程Skill，由WorkBuddy运行，GitHub管理源码。

当前版本 **1.4.0**。五位教师专家共用一个教学Skill，快捷安装另附独立的“AI前沿周速递”和“WorkBuddy自动签到与成长中心”Skill。

## 快捷开始

从[版本下载页](https://github.com/ZhangLennon1207/ai-intro-course-skill/releases)取得 `ai-intro-course-setup-1.4.0.zip`，交给WorkBuddy Agent（或者直接把下载页网站粘贴给workbuddy），说明目标项目：

> 请按安装说明，把教师专家团和教师助手配置到我的“AI概论-教师备课”项目。能自动完成的直接做，保留原有配置，完成后核对登记和关联结果。

也可通过WorkBuddy“技能 → 添加技能 → 上传技能”导入安装包后发起同一请求。安装Agent优先自动注册专家、安装Skill并关联项目；只有无法自动完成的操作才提示用户处理。

**课程与自动签到一键配置**，使用这一句：

> 请按安装说明，把教师专家团、教师助手和自动签到Skill配置到我的“AI概论-教师备课”项目，同时开启本机自动签到与成长中心。我了解它会读取本机登录态并使用已有补登卡、抽奖机会和能量。能自动完成的直接做，完成后核对项目和后台任务。

自动签到基于[88lin/workbuddy-auto-signin](https://github.com/88lin/workbuddy-auto-signin)的固定提交，保留MIT许可。功能是当天签到、接收成长任务、领取已完成任务的奖励以及Buddy等活动操作，不会代做聊天、编程、邀请或分享任务。Skill随包安装；后台任务只在使用者明确要求开启时创建。仅下载或安装课程不会启动账号操作，详见[附加功能说明](addons/workbuddy-auto-signin/references/usage.md)。

**周报使用**：安装后说“生成这周的AI前沿周速递，先保存本地文件”。会按四类专业给出带来源、课堂意义和两个讨论问题的MD与HTML，配图可溯源并本地化。要定期生成，可说“每周一北京时间8点在这个教师项目生成周报，不公开发布”，安装Agent按实际原生能力配置并回读；不会因安装就自动创建定时任务。详见[周报配置说明](addons/ai-frontier-weekly/references/workbuddy-setup.md)。

## 两份说明

- [给使用者的安装与使用说明](docs/user-guide.md)
- [给WorkBuddy Agent的安装配置说明](bootstrap/ai-intro-course-setup/references/installation.md)

专家团包含课程主管、教学设计、AI领域、出题评测和课堂答疑准备。最后一位帮助教师预备常见问题与讲解，不提供独立学习端。普通备课只交需要的成品，检索用于支撑内容，不固定增加专项报告。

源码中的 `.codebuddy/agents/` 保存五个专家定义，`.codebuddy/skills/ai-intro-course/` 保存共享教学Skill。`addons/ai-frontier-weekly/` 与 `addons/workbuddy-auto-signin/` 保存独立的周报及签到Skill，不增加教学专家的固定职责。`bootstrap/` 是安装入口，`packaging/` 是原生套件配置，`tools/` 负责安装和打包。维护人员运行 `python tools/build_packages.py` 生成 `dist/` 下的交付包。

真实资料入口由教师项目配置。课程原件、题库、答案、内部资料和密钥不进入源码或安装包。当前GitHub仓库公开，使用者可直接取得源码和Release安装包；课程资料仍按各自WorkBuddy账号的实际权限读取。

本版提供安装材料和自动配置流程；WorkBuddy中的登记、项目选择器、实际检索和运行效果仍以接收端回读及测试为准。签到任务注册与真实签到分别验证，不把离线测试当作领到积分。
