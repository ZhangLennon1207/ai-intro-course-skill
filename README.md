# 人工智能概论课程专家团与快捷安装

把课程主管、教学设计、AI领域、出题评测、课程答疑五个原生专家，与一个共享课程Skill交给WorkBuddy配置。用户发起安装后，安装Agent优先自动注册资源、关联目标项目，再核对结果；日常使用只需在课程项目中提问。

当前版本 **1.1.0**。这是可交付的安装候选，真实选择器显示、平台注册与资料检索仍须在接收者的WorkBuddy中验证。

## 两份说明

- **给使用者：** [快捷配置与使用说明](docs/user-guide.md)，说明如何发起安装、项目里选择什么、怎样备课和答疑。
- **给对方WorkBuddy Agent：** [安装配置说明](bootstrap/ai-intro-course-setup/references/installation.md)，说明如何发现实际管理能力、自动配置、保留用户设置及回读验收。

## 快捷开始

在仓库的[版本下载页](https://github.com/ZhangLennon1207/ai-intro-course-skill/releases)取得 `ai-intro-course-setup-1.1.0.zip`。通过WorkBuddy“技能 → 添加技能 → 上传技能”导入这个安装入口，然后说：

> 把课程专家团和课程Skill配置到我的教师备课项目。先读取安装说明，能自动完成的直接做，保留原有配置，完成后核对专家与技能是否实际登记和关联。

安装Agent会使用当前平台确实提供的原生工具。没有管理能力时，可自动部署到明确指定的本地项目；该步骤只证明文件配置完成，不能冒称已出现在“我的专家”或新建项目的选择列表。账号登录、目标项目和资料授权等无法自行确定的事项才需要用户处理。

本仓库是私有仓库，其他使用者需获得仓库访问权，或由课程负责人提供安装包。GitHub只保存规则、模板、程序与模拟测试，不存课程原件、题库、标准答案、内部材料或真实密钥。实际资料入口在各自项目配置，本地入口记录不进入分发包。

## 源码结构

```text
.codebuddy/
  agents/                         五个原生专家定义
  skills/ai-intro-course/          唯一日常课程Skill及七项工作流
bootstrap/ai-intro-course-setup/   安装Skill与给安装Agent的说明
packaging/                        原生专家团清单、主管设置、头像
configs/                          教师/学生项目指令模板
docs/user-guide.md                给使用者的说明
tools/                            打包工具、项目文件安装器
tests/                            安装器测试与WorkBuddy验收设计
```

一个安装入口负责配置，另一个课程Skill负责日常教学。五个原生专家绑定同一课程Skill，不再分装七个教学Skill。专家受派时只处理自己的子任务；主管按需协调，有真实委派才报告委派，没有时顺序处理。

课程任务以实际检索的正文为依据，正常备课交完整成品，不固定添加技术核查报告。教师/学生用途控制工作方式，资料访问由实际账号和空间权限决定。

## 维护与验证

维护人员安装开发依赖后运行 `python tools/build_packages.py`，在 `dist/` 生成快捷安装包、原生专家团资产包、单独课程Skill包和源码包。日常运行使用WorkBuddy，本目录的程序只负责安装与打包。

详见 [安装与构建](docs/installation.md)、[验证记录](docs/validation.md)、[权限方案](docs/access-policy.md) 和 [迁移说明](docs/migration.md)。
