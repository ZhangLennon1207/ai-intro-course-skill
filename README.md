# 人工智能概论教师项目

本项目只服务教师备课：检索课程资料，生成教案、课堂活动、实验、题目和课堂答疑准备材料。保留五位专家共用一个课程Skill，由WorkBuddy运行，GitHub管理源码。

当前版本 **1.2.0**。安装和使用都按教师项目处理，无需选择用途模式。

## 快捷开始

从[版本下载页](https://github.com/ZhangLennon1207/ai-intro-course-skill/releases)取得 `ai-intro-course-setup-1.2.0.zip`，交给WorkBuddy Agent，说明目标项目：

> 请按安装说明，把教师专家团和教师助手配置到我的“AI概论-教师备课”项目。能自动完成的直接做，保留原有配置，完成后核对登记和关联结果。

也可通过WorkBuddy“技能 → 添加技能 → 上传技能”导入安装包后发起同一请求。安装Agent优先自动注册专家、安装Skill并关联项目；只有无法自动完成的操作才提示用户处理。

## 两份说明

- [给使用者的安装与使用说明](docs/user-guide.md)
- [给WorkBuddy Agent的安装配置说明](bootstrap/ai-intro-course-setup/references/installation.md)

专家团包含课程主管、教学设计、AI领域、出题评测和课堂答疑准备。最后一位帮助教师预备常见问题与讲解，不提供独立学习端。普通备课只交需要的成品，检索用于支撑内容，不固定增加专项报告。

源码中的 `.codebuddy/agents/` 保存五个专家定义，`.codebuddy/skills/ai-intro-course/` 保存唯一教学Skill。`bootstrap/` 是安装入口，`packaging/` 是原生套件配置，`tools/` 负责安装和打包。维护人员运行 `python tools/build_packages.py` 生成 `dist/` 下的交付包。

真实资料入口由教师项目配置。课程原件、题库、答案、内部资料和密钥不进入源码或安装包。仓库为私有，其他使用者需获得访问权或由课程负责人提供安装包。

本版提供安装材料和自动配置流程；WorkBuddy中的登记、项目选择器、实际检索和运行效果仍以接收端回读及测试为准。
