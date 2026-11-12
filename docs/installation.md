# 教师项目安装与构建

使用者按 [教师使用说明](user-guide.md) 发起安装。对方WorkBuddy Agent按 [安装配置说明](../bootstrap/ai-intro-course-setup/references/installation.md) 检查原生管理能力，自动注册或更新五位专家、安装共享Skill、关联目标教师项目，并合并 [教师项目指令](../configs/teacher-project.md)。保留已有无关配置，仅在用户要求时新建项目。

默认选择“人工智能概论教师专家团”或“人工智能概论课程主管”，绑定“人工智能概论教师助手”。安装用途固定，不再询问模式。只有回读到实际资源和绑定，才能记为平台配置完成。

## 本地项目安装

没有原生管理工具时，可将源码的 `.codebuddy/agents/`、完整课程Skill及随附签到Skill部署到明确指定的项目目录。脚本只依赖Python标准库：

```text
python tools/install_project.py --target "实际项目目录" --dry-run
```

检查计划后去掉 `--dry-run` 执行。提供资料入口时增加 `--materials-entry "有权访问的课程入口"`；更新省略该参数会保留原入口。安装包中已附脚本和完整载荷，路径以包内说明为准。

`filesystem_installed`仅表示文件配置完成，不证明云端登记或项目选择器可见。文件更新先核对内容归属，保护用户修改，保留受管备份；失败恢复情况由实际结果报告。

本地安装器一并复制签到Skill，但不执行其代码、不读取登录凭据、不注册Windows任务。用户要求同时开启时，安装Agent再按[签到说明](../addons/workbuddy-auto-signin/references/usage.md)调用其管理脚本，核对后独立记录结果。不要直接运行上游覆盖固定名称任务的安装器，也不要重复创建WorkBuddy原生签到任务。

## 构建交付包

开发环境安装 `requirements-dev.txt` 中的依赖，运行 `python tools/build_packages.py`，在 `dist/` 生成：

| 文件 | 用途 |
| --- | --- |
| `ai-intro-course-setup-1.3.0.zip` | 默认交付，包含教师项目、签到Skill、安装说明及各原生ZIP |
| `ai-intro-course-team-1.3.0.zip` | 开放平台格式的教师专家团资产包 |
| `ai-intro-course-1.3.0-workbuddy.zip` | 单独教学Skill，供真实技能管理工具登记 |
| `workbuddy-auto-signin-1.3.0-workbuddy.zip` | 独立的签到与成长中心Skill |
| `ai-intro-course-source-1.3.0.zip` | 排除本地配置和课程原件的源码 |

专家团原生ZIP仍只有一个共享教学Skill；它不是完整快捷安装包。要一起取得签到附加功能，应使用setup包或另外安装签到Skill包。打包器校验固定上游提交和文件哈希，保留许可，不联网安装或执行签到。

GitHub更新不会自动同步到已安装WorkBuddy；使用新包发起更新并复测登记、关联和正文读取。

平台依据沿用2026-11-11核对的[专家管理说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Expert-Center)、[项目配置说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)和[技能规范](https://open.workbuddy.cn/docs/skill)。原生资产格式不证明客户端存在本地“上传专家团”按钮；实际能力仍须在接收端确认。
