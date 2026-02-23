# 日志滚动配置快速参考

## 📋 当前生产配置

```yaml
logging:
  backup_count: 10
  console: true
  file: logs/x-agent.log
  format: json
  level: INFO
  max_size: 10MB
  when: D
  interval: 1
```

**效果**：
- ✅ 每天滚动一次（午夜）
- ✅ 每个文件最大 10MB
- ✅ 保留最近 10 个备份文件
- ✅ 同时输出到控制台

## 🎯 常用场景配置

### 场景 1：开发环境（详细日志）
```yaml
logging:
  level: DEBUG
  format: text          # 文本格式易读
  max_size: 5MB
  backup_count: 3       # 只保留 3 天
  when: D
  interval: 1
```

### 场景 2：高流量生产环境
```yaml
logging:
  level: WARNING        # 只记录警告和错误
  format: json
  max_size: 50MB
  backup_count: 30      # 保留一个月
  when: D
  interval: 1
```

### 场景 3：小时级滚动（高频监控）
```yaml
logging:
  level: INFO
  format: json
  max_size: 20MB
  backup_count: 24      # 保留 24 小时
  when: H               # 每小时滚动
  interval: 1
```

### 场景 4：周滚动（节省空间）
```yaml
logging:
  level: ERROR          # 只记录错误
  format: json
  max_size: 100MB
  backup_count: 4       # 保留一个月（4 周）
  when: W               # 每周滚动
  interval: 1
```

## 🔧 参数速查表

| 参数 | 含义 | 推荐值（生产） | 推荐值（开发） |
|------|------|---------------|---------------|
| `level` | 日志级别 | INFO | DEBUG |
| `format` | 输出格式 | json | text |
| `max_size` | 单文件大小 | 10MB | 5MB |
| `backup_count` | 备份数量 | 10 | 3 |
| `when` | 滚动周期 | D（天） | D（天） |
| `interval` | 滚动间隔 | 1 | 1 |
| `console` | 控制台输出 | true | true |

## 📊 when 参数选项

| 代码 | 周期 | 使用场景 |
|------|------|---------|
| S | 秒 | 性能测试（不推荐生产） |
| M | 分钟 | 短时高频任务 |
| H | 小时 | 实时监控场景 |
| D | 天 | **默认推荐** |
| W | 周 | 低频应用 |

## 🚀 立即应用

1. **编辑配置**
   ```bash
   vim backend/x-agent.yaml
   ```

2. **重启服务**
   ```bash
   # 停止现有服务
   Ctrl+C
   
   # 重新启动
   cd backend && uvicorn src.main:app --reload
   ```

3. **验证效果**
   ```bash
   ls -lh backend/logs/
   # 应该看到带日期的新文件名
   ```

## ⚠️ 注意事项

- ❗ 配置修改后必须**重启服务**才能生效
- ❗ 实际文件大小可能略大于设定值（JSON 格式化开销）
- ❗ 确保对日志目录有写权限
- ❗ 定期清理非常旧的日志（超出 backup_count 的）

## 🔍 监控命令

```bash
# 查看日志文件大小
du -sh backend/logs/*

# 查看最新的日志文件
tail -f backend/logs/x-agent.log

# 统计日志文件数量
ls backend/logs/*.log | wc -l

# 查找特定日期的日志
ls backend/logs/ | grep "2026-02"
```

---

**快速参考版本**：v1.0  
**更新日期**：2026-02-19
