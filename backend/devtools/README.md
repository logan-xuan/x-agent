# Development Tools (devtools)

开发调试工具，用于分析 Trace 日志和排查问题。

## 📁 目录结构

```
devtools/
├── trace_analysis/     # Trace 执行流程分析工具
│   ├── analyze_trace_install.py    # 依赖重复安装问题
│   ├── full_trace_analysis.py      # 完整执行流程
│   ├── timeline_analysis.py        # 时间线分析
│   └── ...
└── debug/              # 通用调试工具
    └── analyze_trace.py
```

## 🎯 与 src/tools 的区别

**重要区分**：
- **`devtools/`** - 开发调试脚本（分析日志、排查问题）**✅ 应该提交到 git**
- **`src/tools/`** - Agent 内置工具模块（run_in_terminal, read_file, web_search 等）

两者职责完全不同，不要混淆！

## 📦 版本控制

**重要**: `devtools/` 目录下的工具**应该被提交到 git**，因为：

1. ✅ **可复用性** - 这些工具可以反复使用来排查问题
2. ✅ **团队价值** - 其他团队成员也会遇到类似问题
3. ✅ **知识沉淀** - 记录了解决问题的方法和思路
4. ✅ **效率提升** - 避免重复造轮子

**什么应该提交？**
- Trace 分析工具（如 `analyze_trace_install.py`）
- 通用调试脚本
- 问题排查工具
- 数据迁移脚本（可能需要重复运行）

**什么不应该提交？**
- 一次性的临时脚本
- 包含敏感信息的配置
- 测试用的脏数据文件

## 使用方法

### 1. 分析特定 Trace 的执行流程

```bash
# 分析依赖安装重复执行问题
python tools/trace_analysis/analyze_trace_install.py

# 分析完整的执行时间线
python tools/trace_analysis/full_trace_analysis.py

# 分析错误重复发生的原因
python tools/trace_analysis/analyze_trace_f861b6ff.py

# 详细的错误诊断
python tools/trace_analysis/detailed_trace_analysis.py
```

### 2. 调试工具

```bash
# 通用的 Trace 分析
python tools/debug/analyze_trace.py
```

## 脚本说明

### trace_analysis/

- **analyze_trace_install.py** - 分析依赖包重复安装问题
- **full_trace_analysis.py** - 完整的 Trace 执行流程分析
- **timeline_analysis.py** - 时间线分析，查看事件顺序
- **analyze_trace_f861b6ff.py** - 针对特定 Trace ID 的错误分析
- **detailed_trace_analysis.py** - 详细的 JavaScript 错误诊断

### debug/

- **analyze_trace.py** - 通用的 Trace 日志分析工具

## 输出格式

所有分析脚本都会：
1. 从 `logs/x-agent.log` 读取日志
2. 提取指定 Trace ID 的相关事件
3. 统计关键事件（工具调用、错误、重规划等）
4. 提供诊断结论和建议

## 最佳实践

1. **分析前先确认 Trace ID** - 从前端或日志中获取正确的 Trace ID
2. **选择合适的分析工具** - 根据问题类型选择对应的脚本
3. **保存分析结果** - 将输出保存为文件便于后续参考
4. **清理临时文件** - 分析完成后删除不再需要的脚本
