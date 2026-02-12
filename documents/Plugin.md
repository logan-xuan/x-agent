# ✅ X-Agent 插件化架构设计（v1.0）  

## —— 构建一个**可插拔、热加载、安全隔离**的模块扩展系统

> 目标：让开发者像安装 App 一样为 AI Agent 添加新能力，无需修改主代码。

---

## 🎯 一、核心目标

| 能力 | 实现方式 |
|------|----------|
| ✅ **即插即用** | 放入 `plugins/` 目录自动识别 |
| ✅ **热加载卸载** | 不重启服务动态启用/禁用 |
| ✅ **功能独立** | 每个插件职责单一 |
| ✅ **权限控制** | 可配置是否允许执行危险操作 |
| ✅ **依赖隔离** | 使用虚拟环境或容器化运行 |
| ✅ **通信标准化** | 所有插件通过统一接口与主系统交互 |
| ✅ **前端可见** | 用户可在界面查看和管理插件 |

---

## 🖼️ 二、整体架构图

```
                    +------------------+
                    |   主 Agent Core    |
                    | (Plugin Manager)  |
                    +--------+---------+
                             │
           ┌────────────────┼────────────────┐
           ▼                ▼                ▼
+----------v----------+ +---v----+ +----------v----------+
| web-search-plugin/  | | clock/ | | code-exec-plugin/   |
| - manifest.json     | | - main.py        |
| - search.py         | | - manifest.json  |
+---------------------+ +--------+ +---------------------+

          ↑________________________________↓
                 通过 Plugin Host Runtime 通信
```

---

## 📁 三、插件目录结构规范

```bash
plugins/
├── web-search/
│   ├── manifest.json    ← 插件元信息
│   ├── main.py          ← 入口文件（必须）
│   ├── utils.py         ← 工具函数
│   └── requirements.txt ← 依赖声明
│
├── calendar/
│   ├── manifest.json
│   └── main.py
│
└── disabled/
    └── risky-cmds/      ← 禁用的插件（保留但不加载）
```

---

## 🧩 四、插件描述文件：`manifest.json`

```json
{
  "name": "web-search",
  "version": "1.0.0",
  "author": "me",
  "description": "使用搜索引擎获取实时信息",
  "entry": "main.py",
  "permissions": [
    "network-call",
    "read-memory"
  ],
  "provides": [
    "tool:search_web"
  ],
  "requires": [],
  "ui": {
    "show_in_sidebar": true,
    "icon": "globe",
    "title": "网页搜索"
  },
  "config": {
    "default_engine": {
      "type": "string",
      "enum": ["google", "bing", "duckduckgo"],
      "default": "google"
    },
    "timeout": {
      "type": "number",
      "min": 5,
      "max": 30,
      "default": 10
    }
  },
  "auto_start": true,
  "dangerous": false
}
```

> ✅ 这是插件的“身份证”，决定了它能做什么、如何被调用。

---

## 🔌 五、插件接口标准（Plugin Interface）

所有插件必须实现以下方法：

```python
# plugins/example/main.py
class Plugin:
    def __init__(self, agent_context):
        self.agent = agent_context
        self.name = "example"
        self.config = {}

    def setup(self, config: dict):
        """初始化"""
        self.config.update(config)
        return {"status": "ok"}

    def serve(self):
        """启动后台服务（可选）"""
        pass

    def handle_call(self, call_data: dict) -> dict:
        """
        处理来自主系统的调用
        示例输入: {"action": "search", "query": "天气预报"}
        """
        action = call_data.get("action")
        if action == "search":
            result = self._do_search(call_data["query"])
            return {"success": True, "data": result}
        return {"error": "未知操作"}

    def teardown(self):
        """关闭资源"""
        pass
```

---

## ⚙️ 六、主系统插件管理器（PluginManager）

```python
# core/plugin_manager.py
import importlib.util
import json
import os
from pathlib import Path
from typing import Dict, Any

class PluginManager:
    def __init__(self, plugins_dir="plugins", allow_disabled=False):
        self.plugins_dir = Path(plugins_dir)
        self.allow_disabled = allow_disabled
        self.plugins: Dict[str, Any] = {}
        self.load_all_plugins()

    def load_manifest(self, plugin_path: Path) -> dict:
        with open(plugin_path / "manifest.json", encoding="utf-8") as f:
            return json.load(f)

    def load_plugin_module(self, plugin_path: Path, entry_file: str):
        spec = importlib.util.spec_from_file_location(
            f"plugin_{plugin_path.name}",
            plugin_path / entry_file
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Plugin

    def load_all_plugins(self):
        for p in self.plugins_dir.iterdir():
            if not p.is_dir() or (not self.allow_disabled and "disabled" in str(p)):
                continue
            try:
                manifest = self.load_manifest(p)
                if not manifest.get("auto_start"):
                    continue
                cls = self.load_plugin_module(p, manifest["entry"])
                instance = cls(agent_context=self.get_agent_context())
                config = self.load_user_config(manifest)
                instance.setup(config)
                self.plugins[manifest["name"]] = {
                    "instance": instance,
                    "manifest": manifest,
                    "path": p
                }
                print(f"✅ 加载插件：{manifest['name']}")
            except Exception as e:
                print(f"❌ 加载失败 {p}：{e}")

    def call_plugin(self, name: str, data: dict) -> dict:
        if name not in self.plugins:
            return {"error": "插件未加载"}
        try:
            return self.plugins[name]["instance"].handle_call(data)
        except Exception as e:
            return {"error": str(e)}

    def reload_plugin(self, name: str):
        # 卸载并重新加载
        pass

    def unload_plugin(self, name: str):
        if name in self.plugins:
            self.plugins[name]["instance"].teardown()
            del self.plugins[name]
```

---

## 🔄 七、插件调用流程

### 场景：用户说“帮我查今天北京天气”

```text
[LLM] → 选择工具：web-search
       ↓
[Agent Core] → 调用插件：
               plugin_manager.call_plugin(
                 "web-search",
                 {"action": "search", "query": "北京 今天 天气预报"}
               )
       ↓
[web-search-plugin] → 执行请求 → 返回结果
       ↓
[Agent Core] → 注入上下文 → 回答用户
```

---

## 🔐 八、权限与安全控制

### 1. 权限类型

| 权限 | 说明 |
|------|------|
| `network-call` | 可发起网络请求 |
| `read-memory` | 可读取长期记忆 |
| `write-file` | 可写入文件 |
| `execute-command` | 可执行本地命令 |
| `listen-mic` | 可访问麦克风 |

### 2. 配置级控制

```json
// x-agent.json
"plugins": {
  "enabled": true,
  "allowlist": ["web-search", "calendar"],
  "blocklist": ["dangerous-cmds"],
  "require_confirm_for": ["execute-command"]
}
```

---

## 🧪 九、示例插件：`code-exec-plugin`

```json
// plugins/code-exec/manifest.json
{
  "name": "code-exec",
  "description": "在沙箱中执行 Python 代码",
  "entry": "main.py",
  "permissions": ["execute-command"],
  "provides": ["tool:run_python_code"],
  "config": {
    "timeout": 10,
    "sandbox_mode": {
      "type": "bool",
      "default": true
    }
  },
  "dangerous": true,
  "require_confirm": true
}
```

```python
# plugins/code-exec/main.py
import subprocess
import tempfile
import os

class Plugin:
    def setup(self, config):
        self.timeout = config.get("timeout", 10)
        return {"status": "ready"}

    def handle_call(self, data):
        code = data["code"]
        if len(code) > 10_000:
            return {"error": "代码过长"}

        with tempfile.NamedTemporaryFile(suffix=".py") as f:
            f.write(code.encode())
            f.flush()

            try:
                proc = subprocess.run(
                    ["python", f.name],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout
                )
                return {
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "returncode": proc.returncode
                }
            except Exception as e:
                return {"error": str(e)}
```

---


