---
name: demo-skill
description: "Demo skill for testing Phase 2 argument passing feature"
argument-hint: "[action] [target]"
allowed-tools: [read_file, write_file, list_dir]
user-invocable: true
disable-model-invocation: false
context: fork
license: MIT
---

# Demo Skill - Phase 2 Test

这是一个用于测试 Phase 2 参数传递功能的示例技能。

## 使用方法

```bash
/demo-skill create test.txt
/demo-skill read file.txt
/demo-skill list directory
```

## 参数说明

- `action`: 要执行的动作 (create, read, list)
- `target`: 目标文件或目录

## 可用工具

此技能限制只能使用以下工具：
- `read_file` - 读取文件
- `write_file` - 创建/写入文件
- `list_dir` - 列出目录内容

## 测试要点

1. ✅ 参数正确解析并传递给 LLM
2. ✅ allowed-tools 限制生效
3. ✅ 技能上下文正确注入到系统提示
