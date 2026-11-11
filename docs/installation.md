# WorkBuddy安装与首轮运行

## 教师通过ZIP安装

在本地WorkBuddy打开「专家·技能·连接器」，进入「技能 → 添加技能 → 上传技能」，选择 `ai-intro-course-1.0.0-workbuddy.zip`。上传的是仅含技能目录的包，不能上传整个GitHub源码目录当技能包。

在项目页面建立 `AI概论-教师备课` 和 `AI概论-学生助手`，将同一个课程Skill关联到两边。分别把 [教师模板](../configs/teacher-project.md) 与 [学生模板](../configs/student-project.md) 中的文本填入各自项目指令，并填写资料入口。

教师项目只加入授权教师；学生资料和教师资料分别配置实际访问权限。将课程空间或相关文档添加到任务，或在项目资产中关联/上传相应资料。只填URL不保证已取得正文。

在教师项目新任务中选中课程Skill，输入：“根据本项目已经添加的课件，设计一节90分钟课程，附完整活动材料与教师参考答案。”再在学生账号的学生项目中问同一章节的概念。先确认触发与正文读取，再做自然触发测试。

## 维护人员用GitHub源码

源码中 `.codebuddy/skills/ai-intro-course/` 是完整技能目录。WorkBuddy官方文档列有项目级 `.codebuddy/skills/`；使用源码方式时，项目工作目录必须指向包含该隐藏目录的仓库。项目工作目录识别情况仍需本机实测，不要假定克隆任意位置就生效。

ZIP方式与项目目录方式选择一种，避免同名不同版本混用。不要在学生项目加入本地教师原件目录。不要将教师账号拥有的整个课程工作区交给学生运行。

## 更新与回退

GitHub提交变更后，由维护人员检查并重新打包：在 `.codebuddy/skills/` 下将完整的 `ai-intro-course` 文件夹压缩为ZIP，包内应有 `ai-intro-course/SKILL.md` 及其全部子文件；不要只打包SKILL.md。按当前WorkBuddy支持方式更新/重新导入，不假定自动同步。记录实际安装版本，保留上一个已验证包，更新后重测触发、引用和权限关键用例。

此前v1.1专家团插件与本单Skill可以保存于不同目录。测试本包时，在任务中移除旧同类专家/技能，避免两套指令同时干预；不删除旧包作为安装前提。

## 官方能力依据

2026-11-11查阅：WorkBuddy文档提供[技能上传路径](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)，以及[项目配置、项目级技能目录和资产检索说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)。[开放平台技能规范](https://open.workbuddy.cn/docs/skill)列出了入口文件和展示元数据。

以上是平台文档依据，不是本机导入成功记录。遇到版本界面差异，以当前客户端显示为准，并记录实际步骤。
