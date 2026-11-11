# 内部任务单

用于复杂任务组织，通常不向用户展开。字段是协作约定，不是WorkBuddy接口；无需编造账号或工具元数据。

| 字段 | 填什么 |
| --- | --- |
| task_id | 当前任务简短标识，可省略 |
| actor_role | 当前负责的专家或工作视角 |
| audience | 本次材料的授课对象及学习基础 |
| unit_id / objective | 用户指定章节和本次要完成的目标 |
| discipline / duration | 专业背景与总分钟数，未指定则说明合理假设 |
| allowed_collection / actions | 本次可读资料及可做动作，以实际授权为限 |
| evidence_refs | 实际取得来源、正文位置和状态 |
| deliverable | 教案、核查报告、学生题面等具体产物 |
| review_status | 未检查/已自检/尚有具体未决，不冒称独立会审 |

只保留本次任务需要的字段；不把空表交给用户要求逐项填写。
