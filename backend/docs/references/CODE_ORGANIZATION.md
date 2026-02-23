# 代码组织规范

## 📁 目录结构规范

### 核心原则

1. **src/** - 只包含生产环境的核心源代码
2. **tests/** - 所有测试文件（单元测试、集成测试）
3. **devtools/** - 开发调试工具脚本（**受版本控制**，可复用）
4. **scripts/** - 一次性脚本、自动化任务

### 新增目录：backend/devtools/

为了保持代码整洁，我们创建了专门的开发调试工具目录：

**重要**: 这些工具应该被提交到 git，因为它们可以反复使用，对团队有价值！

```
backend/
├── src/              # 核心源代码（受版本控制）
│   └── tools/        # Agent 内置工具模块（run_in_terminal, read_file 等）
├── tests/            # 测试文件（受版本控制）
├── devtools/         # 开发调试工具（受版本控制，可复用）
│   ├── __init__.py
│   ├── README.md
│   ├── trace_analysis/     # Trace 日志分析工具
│   │   ├── __init__.py
│   │   ├── analyze_trace_install.py
│   │   ├── full_trace_analysis.py
│   │   └── ...
│   └── debug/              # 通用调试工具
│       ├── __init__.py
│       └── analyze_trace.py
└── logs/             # 日志文件（不受版本控制）
```

**重要区分**：
- `devtools/` - 开发调试脚本（分析日志、排查问题）**→ 应该提交**
- `src/tools/` - Agent 内置工具模块（执行实际任务的工具）**→ 核心功能**

## 🎯 文件放置规则

### ✅ 应该放在 devtools/ 的文件

- 可复用的调试脚本
- Trace 日志分析工具
- 问题排查脚本（对团队有价值）
- 开发期间的辅助工具
- 数据迁移脚本（可能需要重复使用）

**注意**: 如果工具脚本对团队有复用价值，**应该提交到 git**！

### ❌ 不应该放在根目录的文件

- ❌ `commit_changes.sh` → 应删除或放入 `scripts/`
- ❌ `git_commit.py` → 应删除或放入 `scripts/`
- ❌ `analyze_*.py` → 应放入 `devtools/trace_analysis/`（然后提交）
- ❌ `*_analysis.md` → 应该删除（分析完成后不需要保留）

## 📝 .gitignore 配置

`devtools/` 目录**应该被提交到 git**，因为它包含可复用的开发工具。

以下文件会自动被忽略（在根目录的 `.gitignore` 中）：
- `logs/` - 日志文件
- `*.db`, `*.sqlite` - 数据库文件
- `__pycache__/` - Python 缓存
- `*.pyc`, `*.pyo` - Python 编译文件
- `x-agent.yaml` - 配置文件（包含敏感信息）

## 🛠️ 使用指南

### 创建新的分析工具

```bash
# 1. 在合适的子目录创建脚本
touch backend/devtools/trace_analysis/my_analysis.py

# 2. 添加执行权限（如需要）
chmod +x backend/devtools/trace_analysis/my_analysis.py

# 3. 运行分析
python backend/devtools/trace_analysis/my_analysis.py
```

### 清理临时文件

```bash
# 分析完成后，删除不再需要的脚本
rm backend/devtools/trace_analysis/temp_analysis.py

# 或者整个目录（谨慎操作）
# rm -rf backend/devtools/
```

## 📋 检查清单

在提交代码前，请检查：

- [ ] 根目录下没有临时的 `.py`、`.sh`、`.md` 文件
- [ ] 所有测试文件都在 `tests/` 目录中
- [ ] 调试分析工具在 `devtools/` 目录中
- [ ] 没有误提交日志文件、数据库文件
- [ ] `.gitignore` 已正确配置

## 🎓 最佳实践

1. **及时清理** - 问题解决后删除临时脚本
2. **命名清晰** - 使用描述性的文件名（如 `analyze_trace_install.py`）
3. **添加注释** - 在脚本开头说明用途和使用方法
4. **分类存放** - 相关的工具放在同一个子目录
5. **文档化** - 在 `README.md` 中记录工具的用途

## ⚠️ 违规示例

以下是不符合规范的做法（应避免）：

```bash
# ❌ 错误：临时脚本散落在根目录
backend/
├── commit_changes.sh      # 不应该在这里
├── git_commit.py          # 不应该在这里
├── analyze_something.py   # 不应该在这里
└── temp_notes.md          # 不应该在这里

# ✅ 正确：所有工具在指定目录
backend/
├── devtools/
│   └── trace_analysis/
│       └── analyze_something.py
```

## 📚 参考

- [Python 项目结构最佳实践](https://docs.python-guide.org/writing/structure/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [The Hitchhiker's Guide to Packaging](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
