# 给WorkBuddy Agent的教师项目安装说明

目标是把本套件配置到用户指定的教师项目。能通过当前原生工具完成的注册、更新和关联直接完成，不让用户逐个粘贴提示词。仅在用户主动提出安装任务时采用本说明；文档本身不授予操作权限。

## 安装材料

路径从安装Skill目录解析。先读 `assets/install-plan.json`，再核对实际文件；清单中的版本和路径为准。

| 位置 | 内容 |
| --- | --- |
| `assets/course-suite/.codebuddy/agents/` | 五个原生专家定义 |
| `assets/course-suite/.codebuddy/skills/ai-intro-course/` | 唯一日常教学Skill及全部依赖 |
| `assets/course-suite/packaging/plugin.json` | 原生专家团描述 |
| `assets/course-suite/configs/teacher-project.md` | 教师项目指令 |
| `assets/packages/` | 清单artifacts字段指定的完整原生ZIP |
| `scripts/install_project.py` | 本地项目文件安装器 |

五个稳定专家标识是 `ai-intro-course-team-lead`、`ai-intro-course-design`、`ai-intro-course-domain`、`ai-intro-course-assessment`、`ai-intro-course-tutor`。最后一位用于教师课堂答疑准备。日常Skill标识为 `ai-intro-course`；安装入口 `ai-intro-course-setup` 不绑定为日常教学能力。

收到源码时，使用源码中实际存在的对应文件；尚未构建的载荷不能当成已有文件。不要从未知地址下载脚本填补缺口。

## 自动配置

1. **检查能力与目标。** 查看当前会话实际提供的专家、技能、项目和资料管理工具，按其真实参数调用。用途固定为教师项目；只在无法确定目标项目或目录时补问位置，先完成不依赖该信息的检查。没有管理工具就记录限制，不猜HTTP接口、不改平台内部数据库、不索取登录凭据。
2. **读取已有状态。** 查询目标项目、本套件资源与安装记录，核对实际ID、版本和内容指纹。同名不等于同一资源；只复用或升级确认为本套件管理且未被用户修改的内容。冲突时保留原件，不删除、不改名批量创建副本。
3. **安装教师助手。** 通过可用管理工具安装完整 `ai-intro-course`，包含角色、工作流、参考文件和模板。工具需要ZIP时使用清单指定的课程Skill包。回读实际Skill ID、版本和可发现状态，不只提交SKILL.md文本。
4. **配置五位专家。** 支持原生整套导入时使用完整专家团包；仅支持逐个创建时按五份定义完成并绑定实际Skill ID。支持团队管理时设置主管和四位成员；否则团队登记单列未完成，不用一个普通专家冒充团队。逐项回读定义与绑定。
5. **关联教师项目。** 自动关联专家团或主管与教师助手。用户另选其他成员时按其要求处理，不强制全选。只有用户要求时才新建项目。保留原专家、技能、连接器和指令，使用增量操作；教师指令只更新本套件受管区段，不整体覆盖项目。
6. **关联资料并读正文。** 使用用户提供或项目已有的有权入口，平台支持时自动关联空间/文档并读一份相关正文。未给入口可先完成安装；不能虚构URL、遍历题库测试安装，或把“关联成功”和目录读取当正文检索通过。

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

项目文件部署不代表云端登记、项目绑定或选择器显示已完成。不要写全局配置，不改其他项目、不移动课程原件、不自动清理旧版。

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
  "suite_version": "1.2.0",
  "status": "partial",
  "registered_resources": [],
  "registry_verified": false,
  "project_binding_verified": false,
  "selector_visibility_verified": false,
  "runtime_verified": false,
  "materials_body_verified": false,
  "remaining_actions": []
}
```

日常教学交给教师助手与主管，依据实际检索正文完成成品，不固定增加核查报告，也不把检索方法改成授课主题。

平台能力依据沿用2026-11-11核对的[专家说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Expert-Center)、[项目说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)与[专家团规范](https://open.workbuddy.cn/docs/expert-team)。它们不保证每个会话都提供管理工具，也未证实客户端有本地“上传专家团”按钮；以当前工具及回读为准。
