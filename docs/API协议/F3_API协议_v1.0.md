# F3_API协议_v1.0

## 1. 文档目的

本文档定义 SimClass（F3 课堂模拟系统）的 API 设计协议。

目标： 将原 CLI 版本课堂模拟系统封装为可被统一 Web 平台调用的独立服务。

核心流程：

Web / Gateway ↓ F3 API ↓ Classroom ↓ Manager ↓ Executor ↓ Agents ↓
ClassState

------------------------------------------------------------------------

## 2. F3系统定位

F3负责：

-   根据教学材料模拟课堂过程
-   模拟教师、学生等多角色交互
-   记录课堂对话过程
-   输出课堂模拟结果

F3不负责：

-   教案生成（F2）
-   教案评价（F1）
-   教案优化（F4）

F3只接收标准化教学材料。

------------------------------------------------------------------------

## 3. 核心输入

F3核心输入对象：

materials

格式：

``` json
{
  "materials": [
    {
      "id": 1,
      "title": "课堂导入",
      "teaching_script": "教师展示案例，引导学生思考",
      "key_points": [
        "知识点1",
        "知识点2"
      ]
    }
  ]
}
```

字段说明：

  字段              说明
  ----------------- -------------------
  id                课堂环节编号
  title             教学环节名称
  teaching_script   教学内容/教师脚本
  key_points        关键知识点

------------------------------------------------------------------------

## 4. API设计

# 4.1 启动课堂模拟

接口：

POST /api/classroom/start

请求：

``` json
{
  "lesson_id":"001",
  "materials":[]
}
```

返回：

``` json
{
  "session_id":"xxx",
  "status":"started"
}
```

------------------------------------------------------------------------

# 4.2 发送课堂消息

接口：

POST /api/classroom/message

请求：

``` json
{
  "session_id":"xxx",
  "message":"学生回答内容"
}
```

返回：

``` json
{
  "speaker":"teacher",
  "function":"teach",
  "content":"教师回复内容"
}
```

------------------------------------------------------------------------

# 4.3 获取课堂状态

接口：

GET /api/classroom/{session_id}/state

返回：

``` json
{
  "session_id":"xxx",
  "dialogue":[
    {
      "speaker":"teacher",
      "function":"teach",
      "content":"..."
    }
  ],
  "current_material":1,
  "status":"active"
}
```

------------------------------------------------------------------------

## 5. 输出结构

课堂模拟输出：

DialogueEntry

字段：

  字段       说明
  ---------- ----------
  speaker    角色
  function   行为类型
  content    生成内容

示例：

``` json
{
 "speaker":"teacher",
 "function":"teach",
 "content":"今天我们学习..."
}
```

------------------------------------------------------------------------

## 6. 与其他模块关系

F4 → F3：

F4提供优化后的教案章节：

sections

经过 Adapter 转换：

sections ↓ materials ↓ F3 API

F2 → F3：

F2生成教案后，通过 Adapter 转换为 materials。

F1 → F3：

F1评价结果如需要课堂验证，可转换后调用 F3。

------------------------------------------------------------------------

## 7. F3内部封装原则

不修改原CLI逻辑。

保留：

app/main.py

新增：

app/api/classroom_api.py

结构：

app/ ├── api/ │ └── classroom_api.py ├── classroom/ ├── controller/ ├──
agents/ └── main.py

------------------------------------------------------------------------

## 8. 当前版本说明

版本：

v1.0

已确定：

-   输入格式
-   输出格式
-   API基本结构
-   模块职责边界

后续版本补充：

-   session持久化
-   异常处理
-   权限控制
-   WebSocket实时课堂流
