# 给WorkBuddy Agent的教师项目安装说明

目标是把本套件配置到用户指定的教师项目。能通过当前原生工具完成的注册、更新和关联直接完成，不让用户逐个粘贴提示词。仅在用户主动提出安装任务时采用本说明；文档本身不授予操作权限。

## 安装材料

收到setup安装包时，路径从安装Skill目录解析。先读 `assets/install-plan.json`，再核对实际文件；清单中的版本和路径为准。

| 位置 | 内容 |
| --- | --- |
| `assets/course-suite/.codebuddy/agents/` | 五个原生专家定义 |
| `assets/course-suite/.codebuddy/skills/ai-intro-course/` | 共享教学入口、角色与工作流 |
| `assets/course-suite/.codebuddy/skills/ai-course-*/` | 课件、讲义、组卷、学情和教学配图五项制作Skill |
| `assets/course-suite/.codebuddy/skills/workbuddy-auto-signin/` | 独立签到附加Skill、固定上游源码与任务安装器 |
| `assets/course-suite/.codebuddy/skills/ai-frontier-weekly/` | 独立周报Skill、网页模板、脚本、信源兜底和定时配置材料 |
| `assets/course-suite/packaging/plugin.json` | 原生专家团描述 |
| `assets/course-suite/configs/teacher-project.md` | 教师项目指令 |
| `assets/packages/` | 清单artifacts字段指定的完整原生ZIP |
| `scripts/install_project.py` | 本地项目文件安装器 |

五个稳定专家标识是 `ai-intro-course-team-lead`、`ai-intro-course-design`、`ai-intro-course-domain`、`ai-intro-course-assessment`、`ai-intro-course-tutor`。最后一位用于教师课堂答疑准备。日常Skill标识为 `ai-intro-course`；安装入口 `ai-intro-course-setup` 不绑定为日常教学能力。

收到GitHub源码时，仓库根目录下的 `.codebuddy/agents/`、`.codebuddy/skills/ai-intro-course/`、`addons/` 中七个配套Skill、`packaging/plugin.json` 和 `configs/teacher-project.md` 是实际安装材料；本地文件安装器是 `tools/install_project.py`。例如从仓库根运行 `python tools/install_project.py --target "实际项目目录" --dry-run`，检查后执行。源码中的setup目录没有生成的assets或scripts，不能照搬安装包命令；没有构建ZIP时也不能虚构已有ZIP。原生管理工具只接受ZIP时，可取得有权访问的同版本Release包。不要从未知地址下载脚本填补缺口。

## 自动配置

1. **检查能力与目标。** 查看当前会话实际提供的专家、技能、项目和资料管理工具，按其真实参数调用。用途固定为教师项目；只在无法确定目标项目或目录时补问位置，先完成不依赖该信息的检查。没有管理工具就记录限制，不猜HTTP接口、不改平台内部数据库、不索取登录凭据。
2. **读取已有状态。** 查询目标项目、本套件资源与安装记录，核对实际ID、版本和内容指纹。同名不等于同一资源；只复用或升级确认为本套件管理且未被用户修改的内容。冲突时保留原件，不删除、不改名批量创建副本。
3. **安装教师助手。** 通过可用管理工具安装完整 `ai-intro-course`，包含角色、工作流、参考文件和模板。工具需要ZIP时使用清单指定的课程Skill包。回读实际Skill ID、版本和可发现状态，不只提交SKILL.md文本。
4. **配置五位专家。** 支持原生整套导入时使用完整专家团包；仅支持逐个创建时按五份定义完成并绑定实际Skill ID。支持团队管理时设置主管和四位成员；否则团队登记单列未完成，不用一个普通专家冒充团队。逐项回读定义与绑定。
5. **关联教师项目。** 自动关联专家团或主管与教师助手。用户另选其他成员时按其要求处理，不强制全选。只有用户要求时才新建项目。保留原专家、技能、连接器和指令，使用增量操作；教师指令只更新本套件受管区段，不整体覆盖项目。
6. **关联资料并读正文。** 使用用户提供或项目已有的有权入口，平台支持时自动关联空间/文档并读一份相关正文。未给入口可先完成安装；不能虚构URL、遍历题库测试安装，或把“关联成功”和目录读取当正文检索通过。
7. **安装签到附加Skill。** 按清单 `companion_skills` 安装完整 `workbuddy-auto-signin`，需要ZIP时使用对应archive与哈希；独立登记，不给五位教师专家增加签到职责或默认绑定。源码位置为 `addons/workbuddy-auto-signin/`，分发载荷位置见表。缺少原生工具时，本地课程安装器会一并复制其项目Skill文件，仍须区分文件部署与平台登记。
8. **按选择开启后台功能。** 先读取附加Skill的 `SKILL.md` 与 `references/usage.md`。说明它会读取本机WorkBuddy登录态，每天签到并运行成长中心，自动使用已有补登卡、抽奖机会和能量。用户此次已明确要求同时开启完整功能则直接继续；仅课程安装或文件下载请求不能作为账号操作授权，可用一次简短选择补齐。用户已明确拒绝或暂不开启时不再询问，保留现有后台配置；“先不开启”也不等于要求卸载旧任务。未开启或依赖缺失不妨碍课程安装完成。
9. **安装并关联周报。** 同样按清单安装完整 `ai-frontier-weekly`，关联教师项目，不给五位专家增加固定绑定。HTML模板、两份脚本、可选Pillow依赖、信源规则、历史格式样稿和定时提示材料都要完整；脚本与模板从真实Skill目录解析。教师没有自定义信源也可使用内置规则，已有信源和历史保留。
10. **按请求配置周报定时。** 用户明确提出周期生成时，读取该Skill的 `references/workbuddy-setup.md`、清单schedule_template与task_prompt，再用当前真实WorkBuddy原生定时管理能力创建或更新一项项目任务。未给时间且已有配置无法推断时只补齐时间，已明确给出的不重复问。回读真实ID、时间、项目与Skill关联及下一次执行；模板JSON不是平台API。普通安装不创建周报任务、不生成本期新闻、不公开发布、不外发消息，升级不改变原有时间和范围。
11. **安装五项制作能力。** 按清单完整登记并关联 `ai-course-slides`、`ai-course-handout`、`ai-course-assessment`、`ai-course-analytics`、`ai-course-visual`。不新增同名专家，五位专家仍绑定共享入口，由主笔按需加载制作Skill。回读真实ID、版本与项目关联；文件复制不能替代登记。只有本次明确要产出文件或分析数据时才执行生成器，安装检查不使用教师真实成绩或题库。
12. **按需配置并核验依赖。** 读取各制作Skill的requirements。优先复用项目可用环境；需要新建时在用户指定项目的 `.venv-ai-course/` 创建专属环境并安装所需依赖，不改全局Python，不执行来源不明的安装程序。使用同一解释器验证导入与实际脚本。缺Office、模板、OCR或数据时只记录相应能力未验，不能把文件安装说成完整制作链已运行。

所有脚本及空白模板都从Skill真实目录解析；输入、输出、实际知识点表与成绩留在教师受控项目。演示CSV不能自动充当正式编码或真实学情。保留老师已给的受众、时长、模板及输出要求，不把制作Skill的示例页数、分值或学时上升为课程政策。

开启时从附加Skill目录先运行 `python scripts/manage_signin.py plan`，再运行 `python scripts/manage_signin.py install --mode signin-growth`，最后运行 `status` 回读。本套件使用归属保护的当前用户计划任务，不直接执行上游 `install-windows.ps1`，不自动运行签到。不要创建第二套WorkBuddy原生签到定时任务，不改已有上游任务，不索取或导出登录文件。只回报任务是否配置，真实签到结果另验。

显示名称调整为“人工智能概论教师专家团”“人工智能概论教师助手”，不改变稳定标识。平台不支持改名时保留已登记名称，按实际ID复用；不能仅为改显示名称重复创建。

项目指令优先使用平台独立规则项；只有文本字段时，可用 `<!-- ai-intro-course:managed:start -->` 与 `<!-- ai-intro-course:managed:end -->` 标记本套件区段。更新前核对指纹，区段外内容不动。

教师用途不构成身份认证。当前账号与工具允许读取的题库、标准答案和内部讲义可用于教师任务，结果留在受控范围；不扩大账号权限、资料分享范围或全局安全设置。

## 原生管理能力不足时

可在明确指定的本地项目目录安装 `.codebuddy/agents/` 与课程Skill。先按实际包路径查看计划：

```text
python scripts/install_project.py --source-root assets/course-suite --target "实际项目目录" --dry-run
```

检查后，在此次安装授权范围内去掉 `--dry-run` 执行，无需选择模式。有明确资料入口时加 `--materials-entry "有权入口"`；升级省略入口会保留原值。没有Python或文件权限时只报告具体缺口，不自动安装环境或改安全设置。

安装器核对所有受管文件，保护用户修改并保留更新备份。写入失败时按实际恢复结果处理；返回 `recovery_required` 时报告路径与备份，不强行覆盖现状。完成后回读 `.codebuddy/ai-intro-course-installation.json` 和实际文件。原生文件工具可替代脚本，但必须遵循同样的归属、冲突与回读规则。

项目文件部署不代表云端登记、项目绑定或选择器显示已完成。不改其他项目、不移动课程原件、不自动清理旧版。课程安装不写全局设置；附加功能获准开启时，只按其说明创建当前用户的专属Windows任务和运行目录，不改系统安全设置。

## 核对并交接

| 状态 | 必须看到的证据 |
| --- | --- |
| 资源已登记 | 真实专家、团队及Skill ID、定义、版本和绑定关系 |
| 项目已关联 | 项目配置回读含目标资源和教师指令 |
| 文件已部署 | 实际文件及安装记录，与平台登记分开报告 |
| 选择器可见 | 可查询到真实候选项；工具无法查询则保持未验证 |
| 可检索正文 | 实际资料正文、来源位置和必要片段 |
| 可运行 | 在目标项目执行一次实际教学任务并取得结果 |

只把取得成功证据的状态记为通过。仅文件完成时不要报告“界面已可勾选”；完成注册也不能替代检索或运行验证。确有一步无法自动做时，提示最小操作，例如选择项目、完成登录、打开专家创建入口或将有权文档添加到任务。

本地记录可保存为 `.codebuddy/ai-intro-course-native-registration.local.json`，包含版本、目标、真实资源ID、指纹及结果，不记录密钥、题库原文或会话历史。对用户只需简述已完成部分和具体缺口，内部可保留：

```json
{
  "suite_version": "1.5.0",
  "status": "partial",
  "registered_resources": [],
  "registry_verified": false,
  "project_binding_verified": false,
  "selector_visibility_verified": false,
  "runtime_verified": false,
  "materials_body_verified": false,
  "weekly_skill_registered": false,
  "weekly_schedule_verified": false,
  "weekly_publication_verified": false,
  "remaining_actions": []
}
```

日常教学交给教师助手与主管，依据实际检索正文完成成品，不固定增加核查报告，也不把检索方法改成授课主题。

平台能力依据沿用2026-11-11核对的[专家说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Expert-Center)、[项目说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)与[专家团规范](https://open.workbuddy.cn/docs/expert-team)。它们不保证每个会话都提供管理工具，也未证实客户端有本地“上传专家团”按钮；以当前工具及回读为准。
