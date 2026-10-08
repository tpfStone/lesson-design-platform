# Prompt registry

本目录冻结真实模型调用使用的角色提示词。当前实验加载 Design Architect v1.0 与其余六角色 v1.2；v1.0/v1.1 文件保留用于结果对照。运行时会把 `prompt_id`、版本、SHA-256、模型名、采样参数、响应 ID、结束原因和真实重试次数写入 trace。Prompt 内容变更必须提升版本号，不能在同一实验 ID 下静默修改。
