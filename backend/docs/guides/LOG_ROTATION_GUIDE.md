# 日志系统优化说明

## 功能概述

日志系统已升级，支持**日期滚动**和**容量大小分块**的双重滚动机制。

## 主要特性

### 1. 日期滚动
- 历史日志文件自动添加日期后缀：`x-agent-2026-02-17.log`
- 支持多种时间间隔：秒 (S)、分钟 (M)、小时 (H)、天 (D)、周 (W)
- 默认每天滚动一次

### 2. 容量大小分块
- 每个日志文件不超过指定大小（默认 10MB）
- 同一天内按序号分块：`x-agent-2026-02-17-01.log`、`x-agent-2026-02-17-02.log`
- 自动清理超出备份数量的旧日志

### 3. 文件命名规则
```
基础文件名：x-agent.log
历史文件：x-agent-YYYY-MM-DD-NN.log
示例：
  - x-agent-2026-02-17-01.log
  - x-agent-2026-02-17-02.log
  - x-agent-2026-02-18-01.log
```

## 配置说明

配置文件位置：`backend/x-agent.yaml`

```yaml
logging:
  backup_count: 10          # 保留的备份文件数量
  console: true             # 是否输出到控制台
  file: logs/x-agent.log    # 日志文件路径
  format: json              # 日志格式：json 或 text
  level: INFO               # 日志级别
  max_size: 10MB            # 单个文件最大大小
  when: D                   # 滚动类型：D=每天，W=每周
  interval: 1               # 滚动间隔（与 when 配合使用）
```

### 配置参数详解

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `level` | string | INFO | 日志级别：DEBUG, INFO, WARNING, ERROR |
| `format` | string | json | 日志格式：json（结构化）或 text（可读） |
| `file` | string | logs/x-agent.log | 日志文件路径 |
| `max_size` | string | 10MB | 单个日志文件最大大小（支持 KB, MB, GB） |
| `backup_count` | int | 10 | 保留的备份文件数量 |
| `console` | bool | true | 是否同时输出到控制台 |
| `when` | string | D | 时间滚动间隔：S=秒，M=分，H=时，D=天，W=周 |
| `interval` | int | 1 | 滚动间隔倍数（如 2 表示每 2 天） |

### when 参数可选值

| 值 | 说明 | 示例 |
|----|------|------|
| S | 秒 | interval=60 表示每分钟 |
| M | 分钟 | interval=30 表示每 30 分钟 |
| H | 小时 | interval=6 表示每 6 小时 |
| D | 天 | interval=1 表示每天 |
| W | 周 | interval=1 表示每周 |

## 使用示例

### 示例 1：每天滚动，每文件最大 10MB，保留 10 个备份
```yaml
logging:
  level: INFO
  format: json
  file: logs/x-agent.log
  max_size: 10MB
  backup_count: 10
  when: D
  interval: 1
  console: true
```

### 示例 2：每小时滚动，每文件最大 50MB，保留 24 个备份（一天的日志）
```yaml
logging:
  level: INFO
  format: json
  file: logs/x-agent.log
  max_size: 50MB
  backup_count: 24
  when: H
  interval: 1
  console: true
```

### 示例 3：每周滚动，每文件最大 100MB，保留 4 个备份（一个月的日志）
```yaml
logging:
  level: INFO
  format: json
  file: logs/x-agent.log
  max_size: 100MB
  backup_count: 4
  when: W
  interval: 1
  console: true
```

## 实现细节

### TimedSizeRotatingFileHandler

自定义的日志处理器，结合了：
- **时间滚动**：基于 `TimedRotatingFileHandler` 的时间计算逻辑
- **大小滚动**：当文件达到指定大小时触发滚动
- **智能命名**：自动生成带日期和序号的文件名
- **自动清理**：删除超出 `backup_count` 的旧日志

### 滚动触发条件

日志文件会在以下任一条件满足时滚动：
1. 达到指定的时间间隔（如每天午夜）
2. 文件大小超过 `max_size` 限制

### 日志清理策略

- 仅保留最近的 `backup_count` 个备份文件
- 按修改时间排序，删除最旧的备份
- 避免磁盘空间被无限占用

## 验证测试

运行测试脚本验证日志滚动功能：

```bash
cd /Users/xuan.lx/Documents/x-agent/x-agent
python test_log_rotation.py
```

测试会：
1. 创建小型日志文件（1KB 限制）
2. 写入 50 条日志消息
3. 验证文件滚动和命名规则
4. 检查文件大小是否符合限制
5. 自动清理测试文件

## 现有日志文件处理

当前 `backend/logs/` 目录下的日志文件：
- `x-agent.log` (66MB) - 主日志文件
- `prompt-llm.log` (14MB) - LLM 交互日志
- `server.log` - 服务器日志

重启服务后，新的滚动机制将自动生效。现有的日志文件会保持不变，新的日志会按照新规则滚动。

## 注意事项

1. **首次应用**：修改配置后需要重启服务才能生效
2. **文件大小**：实际文件大小可能略大于设定值（JSON 格式化开销）
3. **时区**：使用本地时间进行日期滚动
4. **性能**：日志滚动对性能影响极小，仅在滚动发生时产生少量开销

## 故障排查

### 问题：日志没有滚动
**解决方案**：
- 检查配置文件语法是否正确
- 确认 `when` 和 `interval` 参数设置合理
- 查看是否有权限写入日志目录

### 问题：备份文件被过早删除
**解决方案**：
- 增加 `backup_count` 的值
- 检查是否有其他进程在清理日志目录

### 问题：日志文件过大
**解决方案**：
- 减小 `max_size` 的值
- 缩短 `when` 的时间间隔
- 降低日志级别（如从 DEBUG 改为 INFO）
