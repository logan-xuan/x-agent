---
name: browser-automation
description: Automate browser interactions using agent-browser CLI (Vercel Labs)
version: 1.0.0
author: X-Agent Team
user_invocable: true
argument_hint: "[command]"
allowed_tools:
  - run_in_terminal
  - read_file
  - write_file
tags:
  - browser
  - automation
  - web
  - cli
---

# Browser Automation Skill

此技能使用 `agent-browser` CLI（Vercel Labs）实现浏览器自动化操作。支持网页导航、元素交互、表单填写、数据提取等功能。

## ⚡ 重要：CLI 命令格式

### ✅ 正确的命令格式（触发 FAST PATH）

直接使用 CLI 命令前缀，系统会**快速执行**：

```bash
open https://example.com          # 打开网页
get text ".content"               # 获取文本内容
click @e2                         # 点击元素
screenshot                        # 截图
fill "#email" "test@example.com"  # 填写表单
```

### ❌ 避免自然语言格式（会进入 ReAct Loop）

```bash
帮我打开 example.com              # ← 会进入 ReAct Loop，LLM 可能用 curl 而非 agent-browser
获取这个页面的内容                 # ← 会进入 ReAct Loop，LLM 可能用 curl 而非 agent-browser
请截图这个页面                     # ← 会进入 ReAct Loop
```

**原因**：以 CLI 命令开头的参数会直接进入 FAST PATH，使用 `agent-browser` CLI 执行。包含自然语言词汇（如"帮我"、"获取"）会进入 ReAct Loop，由 LLM 决定如何执行（可能选择 curl 等工具）。

## 🚀 快速开始

### 安装要求

1. **安装 agent-browser CLI**:
```bash
npm install -g agent-browser
```

2. **下载 Chromium 浏览器**:
```bash
agent-browser install
```

3. **验证安装**:
```bash
agent-browser --version
```

### 基本用法

```bash
# 打开网页
agent-browser open https://example.com

# 查看可交互元素
agent-browser snapshot

# 点击元素（通过引用）
agent-browser click @e2

# 填写表单
agent-browser fill @e3 "test@example.com"

# 截图
agent-browser screenshot page.png

# 关闭浏览器
agent-browser close
```

## 📚 可用命令

### 导航命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `open <url>` | 导航到 URL | `open https://example.com` |
| `back` | 后退 | `back` |
| `forward` | 前进 | `forward` |
| `reload` | 刷新页面 | `reload` |

### 交互命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `click <selector>` | 点击元素 | `click @e2` 或 `click "#submit"` |
| `dblclick <sel>` | 双击元素 | `dblclick @e5` |
| `focus <sel>` | 聚焦元素 | `focus "#email"` |
| `hover <sel>` | 悬停元素 | `hover ".menu"` |
| `scroll <dir>` | 滚动页面 | `scroll down` |

### 输入命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `type <sel> <text>` | 输入文本 | `type "#name" "John"` |
| `fill <sel> <text>` | 清空并填写 | `fill "#email" "test@test.com"` |
| `press <key>` | 按键 | `press Enter` |
| `select <sel> <val>` | 选择下拉项 | `select "#country" "USA"` |
| `check <sel>` | 勾选复选框 | `check "#agree"` |
| `uncheck <sel>` | 取消勾选 | `uncheck "#subscribe"` |

### 信息提取

| 命令 | 说明 | 示例 |
|------|------|------|
| `snapshot` | 获取无障碍树（推荐） | `snapshot` |
| `get text <sel>` | 获取文本内容 | `get text ".title"` |
| `get html <sel>` | 获取 HTML | `get html "#content"` |
| `get value <sel>` | 获取输入值 | `get value "#email"` |
| `get url` | 获取当前 URL | `get url` |
| `get title` | 获取页面标题 | `get title` |
| `screenshot [path]` | 截图 | `screenshot page.png` |

### 查找元素（语义化）

| 命令 | 说明 | 示例 |
|------|------|------|
| `find role <role> <action>` | 按 ARIA 角色查找 | `find role button click --name "Submit"` |
| `find text <text> <action>` | 按文本查找 | `find text "Sign In" click` |
| `find label <label> <action>` | 按标签查找 | `find label "Email" fill "test@test.com"` |
| `find placeholder <ph> <action>` | 按占位符查找 | `find placeholder "Search" type "keyword"` |
| `find alt <text> <action>` | 按 alt 文本查找 | `find alt "Logo" click` |

### 等待命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `wait <ms>` | 等待毫秒数 | `wait 2000` |
| `wait <selector>` | 等待元素出现 | `wait "#content"` |
| `wait --text "..."` | 等待文本出现 | `wait --text "Loading complete"` |
| `wait --url "pattern"` | 等待 URL 匹配 | `wait --url "**/success"` |
| `wait --load networkidle` | 等待加载状态 | `wait --load networkidle` |

## 💡 使用示例

### 示例 1: 登录网站

```bash
# 打开登录页面
agent-browser open https://example.com/login

# 填写表单
agent-browser fill "#email" "user@example.com"
agent-browser fill "#password" "secret123"

# 点击提交
agent-browser click "#submit"

# 等待跳转
agent-browser wait --url "**/dashboard"

# 截图确认
agent-browser screenshot login-success.png
```

### 示例 2: 表单自动化

```bash
# 打开表单页面
agent-browser open https://example.com/form

# 填写各项内容
agent-browser fill "#name" "John Doe"
agent-browser fill "#email" "john@example.com"
agent-browser select "#country" "United States"
agent-browser check "#terms"
agent-browser check "#newsletter"

# 提交
agent-browser click "#submit"

# 等待成功消息
agent-browser wait --text "Form submitted successfully"
```

### 示例 3: 数据抓取

```bash
# 打开新闻网站
agent-browser open https://news.ycombinator.com

# 获取所有头条
agent-browser get text ".titleline"

# 统计文章数量
agent-browser get count ".storylink"

# 截图保存
agent-browser screenshot hn-frontpage.png
```

### 示例 4: 复杂交互

```bash
# 打开 Web 应用
agent-browser open https://app.example.com

# 使用语义化查找
agent-browser find role button click --name "Create New"
agent-browser find label "Project Name" fill "My Project"
agent-browser find role dialog click --name "Cancel"

# 鼠标控制
agent-browser mouse move 100 200
agent-browser mouse down
agent-browser mouse up
```

## 🔧 与 X-Agent 集成

### 自然语言调用

用户可以直接用自然语言让 AI 执行浏览器操作：

**用户**: "帮我打开 example.com 并截图"

**AI 思考**: 需要使用 browser-automation skill
- 打开 URL: `agent-browser open https://example.com`
- 截图：`agent-browser screenshot`

### 通过 /命令调用

```
/browser-automation open https://example.com
/browser-automation snapshot
/browser-automation click @e2
```

### 在 ReAct 循环中

AI 会在以下场景使用此技能：

1. **需要实时网络信息**: 访问网站获取最新数据
2. **表单填写**: 自动化注册、登录、提交等操作
3. **端到端测试**: 验证 Web 应用功能
4. **数据提取**: 抓取公开网页信息
5. **截图证明**: 生成页面快照作为证据

## ⚠️ 安全注意事项

### 权限控制

插件默认配置下：

**允许的 safe commands**:
- navigation: open, back, forward, reload
- interaction: click, dblclick, focus, hover, scroll
- input: type, fill, press, select, check, uncheck
- extraction: get text, get html, get value, get url, get title
- find: find role, find text, find label, etc.
- wait: wait
- info: snapshot, get count, get box

**禁止的 commands**:
- `eval` - 防止任意 JavaScript 执行
- `trace start` - 防止调试开销
- `profiler` - 防止性能分析
- `network route` - 防止请求拦截（除非明确配置）

### 配置示例

在 `x-agent.yaml` 中配置：

```yaml
plugins:
  agent-browser:
    enabled: true
    allowed_commands:
      - open
      - click
      - fill
      - type
      - snapshot
      - screenshot
      - get text
      - find
    blocked_commands:
      - eval
      - trace start
      - profiler
    timeout: 30  # 命令超时时间（秒）
```

### 最佳实践

1. **会话管理**: 敏感操作后清除 cookies
   ```bash
   agent-browser cookies clear
   ```

2. **状态保存**: 登录状态可以保存复用
   ```bash
   agent-browser state save my-session
   # 下次加载
   agent-browser state load my-session
   ```

3. **沙盒环境**: 不受信任的任务应在隔离环境运行

4. **超时设置**: 始终设置合理的超时时间

## 🐛 错误处理

### 常见错误及解决方案

**Element not found**:
```bash
# 先查看可用元素
agent-browser snapshot
# 使用正确的选择器
agent-browser click @e3  # 或使用语义化查找
```

**Timeout**:
```bash
# 增加等待时间
agent-browser wait 5000
# 或等待特定条件
agent-browser wait --text "Welcome"
```

**CLI not found**:
```bash
# 检查安装
which agent-browser
# 重新安装
npm install -g agent-browser
agent-browser install
```

### 错误响应格式

```json
{
  "success": false,
  "error": "Command failed: Element @e99 not found",
  "metadata": {
    "command": "click @e99",
    "returncode": 1
  }
}
```

## 📊 性能指标

- **CLI 启动时间**: <10ms (Rust 原生实现)
- **浏览器启动**: 1-2 秒
- **命令执行**: 100-500ms（简单操作）
- **内存占用**: ~50MB (CLI) + ~200MB (浏览器)

## 🔗 相关资源

- [GitHub Repository](https://github.com/vercel-labs/agent-browser)
- [官方文档](https://agent-browser.dev)
- [Vercel Skills](https://skills.sh)
- [X-Agent Plugin Architecture](../../../arch/plugin.md)

## 🎯 高级功能

### 多标签页管理

```bash
# 列出标签页
agent-browser tab

# 新建标签页
agent-browser tab new https://example.com

# 切换到第 2 个标签页
agent-browser tab 2

# 关闭标签页
agent-browser tab close 1
```

### Cookies 和存储

```bash
# 获取所有 cookies
agent-browser cookies

# 设置 cookie
agent-browser cookies set session abc123

# localStorage 操作
agent-browser storage local
agent-browser storage local set key value
agent-browser storage local clear
```

### iframe 支持

```bash
# 切换到 iframe
agent-browser frame "#my-frame"

# 返回主框架
agent-browser frame main
```

### 对话框处理

```bash
# 接受 alert/confirm
agent-browser dialog accept

# 带提示的接受
agent-browser dialog accept "custom text"

# 拒绝对话框
agent-browser dialog dismiss
```

### 网络控制

```bash
# 拦截请求
agent-browser network route https://api.example.com

# 阻止请求
agent-browser network route https://ads.com --abort

# 模拟响应
agent-browser network route /api/data --body '{"status":"ok"}'

# 查看请求日志
agent-browser network requests
```

## 📝 版本历史

- **v1.0.0** (2026-02): 初始版本，基于 agent-browser v0.11.1
  - 完整的 CLI 命令支持
  - 权限控制系统
  - 会话管理
  - 错误处理增强

---

*Last updated: 2026-02-19*
