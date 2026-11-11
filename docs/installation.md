# WorkBuddy安装与首轮运行

## 默认通过安装Agent配置

使用 `ai-intro-course-setup-1.1.0.zip`。在本地WorkBuddy“技能 → 添加技能 → 上传技能”导入安装Skill，然后说明目标项目和教师/学生用途。安装Agent按 [安装配置说明](../bootstrap/ai-intro-course-setup/references/installation.md) 自动检查和执行可用管理能力。已能自动完成的部分不再要求用户逐项配置。

默认先查询并复用已有资源，安装一个课程Skill，创建或更新五个原生专家，并在平台支持时关联目标项目。现有无关指令、专家、技能和连接器都保留。新建项目仅在用户要求时执行。项目用途规则使用 [教师模板](../configs/teacher-project.md) 或 [学生模板](../configs/student-project.md)，优先由安装Agent合并到受管区段。

教师项目只加入授权教师，资料权限由账号和空间配置。平台支持资料关联时由安装Agent完成；不支持时只提示缺少的具体操作。关联后读取一份正文核对，不把填写URL或读取目录当作检索通过。

选择器中预期教师选择“人工智能概论课程专家团”或“人工智能概论课程主管”及“人工智能概论课程助手”，学生选择“人工智能概论课程答疑”及同一课程Skill。只有实际注册和回读后，才能报告这些条目已可选。

## 没有原生管理工具时

源码中的 `.codebuddy/agents/` 和 `.codebuddy/skills/ai-intro-course/` 可安装到用户指定的项目工作目录。本地安装器仅使用Python标准库：先执行 `python tools/install_project.py --target "实际项目目录" --mode teacher --dry-run` 查看计划，检查后去掉 `--dry-run` 安装；学生项目用 `student`。安装Skill中已附这个脚本和完整载荷，路径以包内说明为准。

文件部署不创建云端项目或个人专家记录，回读状态是 `filesystem_installed`，不能宣称截图的下拉列表已出现条目。WorkBuddy文档确认项目工作目录可发现这些配置，实际选择器和平台管理能力仍需单独验证。

## 维护人员构建

开发环境安装 `requirements-dev.txt` 中的依赖，运行 `python tools/build_packages.py`，生成：

- `ai-intro-course-setup-1.1.0.zip`：推荐给使用者，含安装说明、完整载荷和原生ZIP。
- `ai-intro-course-team-1.1.0.zip`：开放平台格式的原生专家团资产包，不等于客户端存在本地专家团ZIP上传入口。
- `ai-intro-course-1.1.0-workbuddy.zip`：仅课程Skill，供原生技能管理工具单独登记。
- `ai-intro-course-source-1.1.0.zip`：可分发源码，排除本地配置和真实资料。

更新时复用记录中的本套件资源，核对原内容指纹后升级，不覆盖使用者自改内容。文件安装器保留已管理更新的备份，不自动删除旧版。GitHub提交不会自动同步到已安装WorkBuddy，需要通过安装Agent更新，并复测关键路径。

## 官方能力依据

2026-11-11查阅：WorkBuddy文档提供[技能上传路径](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)，以及[项目配置、项目级技能目录和资产检索说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)。[开放平台技能规范](https://open.workbuddy.cn/docs/skill)列出了入口文件和展示元数据。

以上是平台文档依据，不是本机导入成功记录。遇到版本界面差异，以当前客户端显示为准，并记录实际步骤。
