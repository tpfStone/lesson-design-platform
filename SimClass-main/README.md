# SimClass MVP

论文 *Simulating Classroom Education with LLM-Empowered Agents* 的功能性 CLI MVP 复现。

实现 SimClass 的核心机制：**Class State → Manager Agent（隐藏 meta-agent）→ Select Speaker + Function → Function Executor → Agent Response → Update Class State → (User Input OR Timeout τ) → 循环**。

## 架构

```
Human User (terminal)                Timeout τ (CLASSROOM_TIMEOUT_SECONDS)
        │ user_input / empty_enter            │ timeout
        ▼                                     ▼
   ClassroomEvent(trigger_type, user_message)   ← 事件源: app/classroom/events.py
        │  （initialization / user_input / empty_enter / timeout —— 同一条决策管线）
        ▼
   ClassState ────► Manager Agent (LLM, 输出 JSON: speaker+function+reason)
        ▲                 │  JSON schema / 权限校验 / retry / fallback
        │                 ▼
        │          FunctionExecutor.execute(speaker, function, state)
        │                 │
        │                 ▼
        └──── Agents (同一个 LLM + 不同 system prompt):
              Teacher / Assistant / Class Clown / Deep Thinker /
              Note Taker / Inquisitive Mind
```

- **Tutoring functions**（仅 Teacher）: `teach`, `next_material`
- **Interaction functions**（按角色权限）: `answer_question`, `ask_question`, `elaborate`, `summarize`, `encourage`, `discuss`, `redirect`

## 自主课堂（Timeout τ）

用户静默 `CLASSROOM_TIMEOUT_SECONDS` 秒后，课堂自主继续（不伪造用户消息，Manager 基于当前状态动态决策）。四种触发类型统一进入同一条 Manager → Executor 管线，区别只在 trigger_type：

| trigger_type | 含义 | 对连续超时计数的影响 |
|---|---|---|
| `initialization` | 课堂开始 | — |
| `user_input` | 用户发送了消息 | 清零 |
| `empty_enter` | 用户按回车示意继续 | 暂停中则清零 |
| `timeout` | 静默 τ 秒超时 | +1 |

防失控：连续 timeout 自主推进达到 `MAX_CONSECUTIVE_TIMEOUT_ACTIONS` 次后进入 `PAUSED_FOR_USER`，等待用户输入；有意义输入或暂停中的空回车（= 授权继续自主运行）都会恢复 `AUTONOMOUS` 并开启新计数周期。暂停状态（`autonomous_mode`）与计数（`consecutive_timeout_count`）是两个独立概念，日志中均逐轮记录。

## 安装

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt     # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # Linux/Mac
```

## 配置 `.env`

```bash
cp .env.example .env    # 然后填写
```

```ini
API_KEY=sk-your-api-key
BASE_URL=https://api.openai.com/v1     # 任何 OpenAI-compatible 接口
MODEL=gpt-4o-mini

CLASSROOM_TIMEOUT_SECONDS=15           # τ；开发时可设 5
MAX_CONSECUTIVE_TIMEOUT_ACTIONS=3      # 连续 timeout 自主推进上限
```

未配置 `API_KEY` 时自动回退 `MockProvider`（离线模式），CLI 仍可完整运行。

## 运行

```bash
python -m app.main            # 正常模式（读 .env）
python -m app.main --debug    # 显示 [TRIGGER] / [STATE] / Manager reason / end_class
python -m app.main --mock     # 强制离线模式
```

交互：输入消息回车发送；静默 τ 秒后课堂自主继续；连续超时达到上限后暂停，按提示输入问题或直接回车恢复；输入 `quit` 下课。
每轮日志保存到 `logs/session_YYYYMMDD_HHMMSS.json`（含 `turn_id` / `trigger_type` / `consecutive_timeout_count` / `autonomous_mode`）。

离线 Demo 回放：`Get-Content demo_input.txt | python -m app.main --mock --debug`

## 测试

```bash
python -m pytest tests/ -v    # 52 个确定性测试；真实 LLM 冒烟测试默认跳过
```

- 单元/组件测试（MockProvider + ScriptedLLM）：Manager 决策、权限校验、Agent/Executor
- 端到端课堂循环（test_classroom.py）
- Timeout τ 触发机制（test_timeout_trigger.py）
- 暂停/恢复状态机回归（test_pause_resume.py）
- 验证层（test_validation_mock.py + tests/validation/）：负面情绪 / 跑题重定向 / 连续推进三场景的行为判据
- 真实 LLM 冒烟测试（opt-in）：`RUN_REAL_LLM_TESTS=true` 时运行，报告存入 `logs/validation/`

## 论文部分 vs MVP 工程实现

**来自论文**：多 Agent 课堂（Teacher/Assistant/4 类 classmates）、隐藏 Manager 决定 speaker + function、Class State 驱动、Classroom Loop、User Input OR Timeout τ 双触发、情感支持与课堂管理行为、teaching material 流转。

**MVP 工程实现（非论文公开 API）**：具体的 interaction function 划分与命名、JSON 决策 schema（含 `end_class`）、MockProvider 及其离线启发式、CLI 交互方式、日志格式、课程示例内容（Introduction to LLMs）、`empty_enter` 触发类型与暂停/恢复安全机制。

## 已知限制

- `TimedInput` 用后台线程实现跨平台 timed stdin（Windows 无 select-on-stdin）：超时后用户补完的半行输入会在下一轮才被读到
- Manager 的决策质量完全依赖所配 LLM；弱模型可能需要更多 retry
- 无多用户、无 FIAS / Community of Inquiry 评估、无 RAG
- dialogue history 只取最近 8 条进入 prompt，超长课程会丢失早期上下文

## 扩展到 WebUI 的路径

1. `Classroom` 已经把「事件源」抽象为 `event_fn`（返回 `ClassroomEvent`），把「输出」集中在 `_print_*` —— 替换为 WebSocket/SSE 双向通道即可
2. `ClassState` / `ManagerDecision` / `ClassroomEvent` 已是可序列化结构，可直接作为 API schema
3. 加一层 FastAPI：`POST /message`（用户输入）、`GET /stream`（课堂事件流）；前端渲染 dialogue history
4. Timeout τ 已在核心循环实现（`_next_event` / `_process_event`），WebUI 下只需把终端事件源换成 timer + 消息队列

## F3 完整课堂模拟 API（v3）

在保留原 CLI / 四轮式回归用途的基础上，项目新增正式多会话服务层：

- `POST /api/classroom/sessions`：创建并启动独立课堂 session；
- `GET /api/classroom/sessions/{sessionId}`：查询真实状态；
- `GET /api/classroom/sessions/{sessionId}/events`：获取结构化完整事件；
- `POST .../messages`、`pause`、`resume`、`end`：课堂控制；
- `PATCH .../settings`：下一等待周期起修改 timeout 等限制；
- `POST .../analyze`：运行独立 IssueAnalysisAgent；
- `GET .../result`：读取 session + events + statistics + issues；
- `GET .../artifacts/{kind}`：下载 JSON/Markdown 结果。

正式服务继续复用 `ClassState -> Manager -> FunctionExecutor -> Agent -> DialogueEntry`
真实循环；Web/API 层不伪造课堂决策。每个 session 拥有独立 `Classroom`、状态、
事件队列和 EventStore。F3 默认端口为 **8003**，不占用 F4 的 8000。

启动：

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.api.classroom_api:app --host 127.0.0.1 --port 8003
```

健康检查：`GET http://127.0.0.1:8003/api/health`。
详细合同见 `documentation/F3完整课堂模拟_API说明.md` 与
`documentation/F3完整课堂模拟_数据协议.md`。
