# ModelScope 生图 Skill 设计

日期：2026-04-11

## 背景

当前仓库已经具备：

- 系统级 skill 注册与发现机制，系统 skill 放在 `backend/src/skills/`
- 内置工具体系，统一通过 `backend/src/tools/builtin/` 注册给 agent 使用
- REST/SSE 会话模型，用户请求会绑定 `session_id` 与 `agent_id`
- 运行时工具结果归一化与 artifact 化能力

用户希望新增一个“内置生图 skill”，参考 ModelScope 的 `Tongyi-MAI/Z-Image-Turbo` 模型。能力目标是：用户只通过自然语言描述想要的图片，agent 就能调用后端 API 生成图片并返回可访问地址。

额外约束已经明确：

- 不把图片保存到用户 workspace，因为用户 workspace 不一定可访问
- 图片按 `agent_id` 维度存放，而不是按 `session_id` 维度隔离
- 资产地址不做鉴权，只要知道地址即可访问
- 仍然需要在元数据里记录生成来源，便于排查和清理

## 目标

- 新增一个可被 agent 自动发现和使用的系统 skill：`imagegen`
- 新增一个统一的内置工具：`generate_image`
- 通过 ModelScope API-Inference 文生图接口生成图片
- 将生成结果下载到项目内统一资产空间
- 通过后端公开 URL 暴露图片，供前端、聊天消息和外部客户端访问
- 返回稳定、可读、可追踪的工具结果格式

## 非目标

- 不实现图像编辑、局部重绘、图生图
- 不实现复杂 prompt 模板市场或多模型编排
- 不实现带鉴权的私有资产访问控制
- 不在本次范围内新增前端专用生图页面
- 不把生成结果回写到用户 workspace

## 推荐方案

推荐采用“系统 skill + 内置工具 + 项目资产空间 + 公开访问 URL”的组合方案。

原因：

- skill 负责触发和指令约束，避免模型自己写脚本直连第三方 API
- 内置工具统一鉴权、错误处理、落盘、日志和结果格式
- 项目级资产空间解决用户 workspace 不可访问的问题
- 公开 URL 适合当前“知道地址即可访问”的约束，集成成本最低

## 架构概览

新增四个部件：

1. 系统 skill：`backend/src/skills/imagegen/SKILL.md`
2. 内置工具：`backend/src/tools/builtin/generate_image.py`
3. 资产服务：`/api/v1/assets/generated-images/...`
4. 配置段：`image_generation`

逻辑关系如下：

1. 用户发送“画一张图”“生成海报”“根据描述出图”等自然语言请求
2. agent 匹配到 `imagegen` skill，并按 skill 指引调用 `generate_image`
3. `generate_image` 使用配置中的 ModelScope Token 和 endpoint 调用文生图 API
4. 工具下载生成出的图片到项目资产目录
5. 工具返回资产 URL、本地路径和生成元数据
6. 后端资产接口按 URL 提供静态访问

## 配置设计

在 `backend/x-agent.yaml` 中新增：

```yaml
image_generation:
  enabled: true
  provider: modelscope
  endpoint: https://api-inference.modelscope.cn/v1/images/generations
  api_key: ms-your-modelscope-token
  model: Tongyi-MAI/Z-Image-Turbo
  timeout: 180
  download_timeout: 180
  assets_dir: backend/assets/generated-images
  public_base_url: http://localhost:8888/api/v1/assets/generated-images
  default_size: 1024x1024
  default_count: 1
  max_count: 4
```

配置规则：

- `enabled=false` 时工具直接报“功能未启用”
- `api_key` 必填，缺失时配置校验报错
- `model` 默认预置为 `Tongyi-MAI/Z-Image-Turbo`
- `assets_dir` 为相对仓库根目录的项目内路径，运行时会解析成仓库绝对路径
- `public_base_url` 用于生成返回给用户的绝对访问地址

## Skill 设计

skill 名称：`imagegen`

触发语义：

- 画一张图
- 生图
- 生成图片
- 生成海报
- 按描述生成插画、封面、配图、宣传图

skill 责任：

- 识别这是“文生图”而不是“图像编辑”
- 将用户自然语言整理为适合文生图的 prompt
- 在用户没有明确指定时，默认使用配置里的尺寸和数量
- 明确要求优先使用 `generate_image`，而不是自己编写脚本请求第三方 API

skill 不负责：

- 第三方鉴权
- 网络请求重试
- 文件下载和落盘
- 访问 URL 生成

建议 frontmatter：

```yaml
name: imagegen
description: "根据用户自然语言描述调用内置生图工具生成图片，并返回可访问地址"
keywords:
  - 生图
  - 画图
  - 生成图片
  - 海报
  - 插画
  - text to image
auto-trigger: true
priority: 1
allowed_tools:
  - generate_image
  - read_file
```

## 工具设计

工具名：`generate_image`

### 输入参数

- `prompt: str`
  - 必填，用户最终描述
- `size: str | None`
  - 可选，默认取配置值
  - 允许值先限制为常见规格，如 `1024x1024`、`768x1024`、`1024x768`
- `count: int | None`
  - 可选，默认取配置值
  - 最大不能超过配置 `max_count`
- `style_hint: str | None`
  - 可选，用于补充风格倾向

运行时额外上下文：

- `agent_id` 不由模型传入，而是由当前请求上下文自动注入或读取

### 输出结果

成功时返回：

- 简短文本摘要
- `model`
- `final_prompt`
- `size`
- `count`
- `agent_id`
- `assets`

每个 `asset` 包含：

- `file_path`
- `public_url`
- `relative_path`
- `mime_type`
- `width`
- `height`
- `provider_asset_url`（可选，仅用于追踪）

### 存储路径

按 `agent_id` 维度存储：

```text
backend/assets/generated-images/{agent_id}/{yyyy-mm-dd}/img_{asset_id}.png
```

例如：

```text
backend/assets/generated-images/main-agent/2026-04-11/img_8f3c1a2b.png
```

### 公开访问 URL

统一走后端接口暴露：

```text
/api/v1/assets/generated-images/{agent_id}/{yyyy-mm-dd}/{filename}
```

例如：

```text
http://localhost:8888/api/v1/assets/generated-images/main-agent/2026-04-11/img_8f3c1a2b.png
```

当前访问策略：

- 不做鉴权
- 只要知道 URL 即可访问
- 仍在元数据中记录 `agent_id` 和 `session_id`

## ModelScope 调用约定

默认使用：

- endpoint: `https://api-inference.modelscope.cn/v1/images/generations`
- model: `Tongyi-MAI/Z-Image-Turbo`
- 认证：`Authorization: Bearer {configured_api_key}`

请求体采用“文生图”形式，至少包含：

- `model`
- `prompt`
- `size`
- `n`

如果接口未来返回字段名略有差异，工具层需要做兼容解析，而不是把不稳定细节暴露给 skill。

## 资产服务设计

新增一个只读下载接口，用于把项目资产空间中的图片暴露为 HTTP 资源。

接口建议：

- `GET /api/v1/assets/generated-images/{agent_id}/{date}/{filename}`

行为要求：

- 只允许访问 `assets_dir` 根目录之下的文件
- 需要显式防御路径穿越，例如 `../`、绝对路径、符号链接逃逸
- 文件不存在时返回 404
- 仅返回图片等允许的媒体类型
- 响应头包含合理的 `Content-Type` 与缓存策略

## 数据与索引

除了真实图片文件，还应记录一个轻量元数据索引，便于后续治理。

元数据至少包含：

- `asset_id`
- `agent_id`
- `session_id`
- `prompt`
- `model`
- `size`
- `created_at`
- `relative_path`
- `public_url`
- `provider`

索引明确采用当前项目已有的 SQLite 主库 `backend/x-agent.db`，新增独立表记录图片资产元数据，不使用本地 JSON。

本次不要求前端消费该索引，但后续清理任务、追踪问题和资产列表接口会依赖它。

## 错误处理

错误分层如下。

### 配置错误

- 未启用功能
- 缺失 API key
- endpoint 非法
- 资产目录不可写

返回策略：

- 工具返回清晰可读错误
- 配置校验尽量在启动阶段提前失败

### 上游 API 错误

- 401/403：Token 无效或权限不足
- 429：限流
- 5xx：上游服务异常
- 超时：请求超时

返回策略：

- 保留 HTTP 状态或等价错误类别
- 返回适合用户理解的中文提示
- 日志中记录上游摘要，不记录敏感 key

### 下载与落盘错误

- 生成成功，但图片下载失败
- 下载成功，但本地保存失败

返回策略：

- 明确区分“生成失败”和“落盘失败”
- 如果返回了远程图片地址但本地落盘失败，先视为失败，不返回不可追踪的半成品

## 结果展示策略

工具结果应足够简洁，避免大段 JSON 直接灌入上下文。

推荐展示格式：

```text
已生成 1 张图片
Model: Tongyi-MAI/Z-Image-Turbo
Size: 1024x1024
Asset 1:
- URL: http://localhost:8888/api/v1/assets/generated-images/main-agent/2026-04-11/img_8f3c1a2b.png
- Path: /abs/path/to/backend/assets/generated-images/main-agent/2026-04-11/img_8f3c1a2b.png
```

详细元数据继续放在 `metadata` 中供程序消费。

## 安全边界

本次方案的安全边界是“公开可访问资产”，不是“私有资源”。

因此需要至少保证：

- 资产 URL 只能读取受控目录下的文件
- 不允许任意文件下载
- 不把 API key 写入结果、日志或返回体
- 不让 skill 自行调用任意外部脚本绕过工具层

已接受的限制：

- 任何知道 URL 的人都能访问该图片
- 没有防盗链、过期签名和租户隔离

## 测试策略

实现必须按 TDD 执行，至少覆盖以下测试。

### 工具测试

- 构造正确的 ModelScope 请求体
- 正确解析成功响应
- 正确下载图片并落盘
- `count` 超过限制时失败
- 上游 401/429/5xx/超时错误映射正确

### 资产接口测试

- 已生成文件可通过 URL 正常访问
- 不存在文件返回 404
- 路径穿越请求被拦截
- `Content-Type` 正确

### Skill/注册测试

- `imagegen` skill 可以被注册与发现
- `generate_image` 会出现在 built-in tools 中

### 配置测试

- 缺失 `api_key` 时配置校验失败
- `assets_dir` 和 `public_base_url` 可正确解析

## 实施顺序

推荐按以下顺序落地：

1. 扩展配置模型与校验器，加入 `image_generation`
2. 编写失败测试，锁定 `generate_image` 工具契约
3. 实现 `generate_image` 工具和 ModelScope 客户端
4. 实现资产落盘与公开访问接口
5. 注册 built-in tool
6. 新增 `imagegen` skill
7. 跑通工具、接口与 skill 回归测试

## 开放问题与本次决策

### 已决策

- 默认模型：`Tongyi-MAI/Z-Image-Turbo`
- 默认走 ModelScope API-Inference
- 资产按 `agent_id` 维度存储
- 资产 URL 公开访问
- 不写入用户 workspace

### 暂不展开

- 多模型切换
- 图片二次编辑
- 公开 URL 的签名和过期机制
- 资产管理后台

## 成功标准

满足以下条件即可视为完成：

- 用户输入自然语言描述后，agent 能自动触发 `imagegen` skill
- skill 通过 `generate_image` 成功生成至少一张图片
- 图片存放在项目资产空间而不是用户 workspace
- 返回结果中包含稳定可访问的 URL
- 知道 URL 的任意客户端都能访问图片
- 配置、错误处理和测试覆盖达到本设计要求
