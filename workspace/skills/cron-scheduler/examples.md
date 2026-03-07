# 使用示例：Cron调度器框架

## 1. 基础安装和配置

首先运行安装脚本：
```bash
cd ~/Documents/qoder-workspace/x-agent/workspace/skills/cron-scheduler
chmod +x scripts/install.sh
./scripts/install.sh
```

## 2. 创建示例任务

让我们创建几个实用的任务示例：

### 示例1：每日备份任务
```bash
python3 scripts/task_manager.py create \
  --id daily-backup \
  --name "Daily System Backup" \
  --schedule "0 2 * * *" \
  --command "tar -czf /backups/system-backup-$(date +\\%Y\\%m\\%d).tar.gz /important/data/" \
  --description "Creates a daily backup of important system data at 2 AM"
```

### 示例2：每周清理临时文件
```bash
python3 scripts/task_manager.py create \
  --id weekly-cleanup \
  --name "Weekly Temp File Cleanup" \
  --schedule "0 3 * * 0" \
  --command "find /tmp -name 'temp-*' -mtime +7 -delete && find /var/log -name '*.log.*' -mtime +30 -delete" \
  --description "Cleans up temporary files older than 7 days and old log files older than 30 days every Sunday at 3 AM"
```

### 示例3：每小时监控系统状态
```bash
python3 scripts/task_manager.py create \
  --id hourly-monitor \
  --name "Hourly System Monitoring" \
  --schedule "0 * * * *" \
  --command "df -h >> /var/log/system-status.log && echo $(date): Memory usage $(free -m | awk 'NR==2{printf \"%.2f%%\", $3*100/$2}') >> /var/log/system-status.log" \
  --description "Logs disk space and memory usage every hour"
```

## 3. 验证任务定义

检查我们创建的cron表达式是否正确：
```bash
# 检查每日备份的cron表达式
python3 scripts/validator.py "0 2 * * *" --explain
# 输出：Every minute 0 past hour 2 on day 1 of the month in January on Sunday

# 检查每周清理的cron表达式
python3 scripts/validator.py "0 3 * * 0" --explain
# 输出：Every minute 0 past hour 3 on day 1 of the month in January on Sunday

# 查看下一个执行时间
python3 scripts/validator.py "0 2 * * *" --next-runs 3
```

## 4. 启动调度器

启动调度器服务：
```bash
python3 scripts/scheduler_daemon.py start
```

## 5. 管理任务

### 查看所有任务
```bash
python3 scripts/task_manager.py list
```

### 查看特定任务状态
```bash
python3 scripts/task_manager.py status --id daily-backup
```

### 更新任务
如果我们想改变备份时间到凌晨3点：
```bash
python3 scripts/task_manager.py update --id daily-backup --schedule "0 3 * * *"
```

### 禁用任务
如果需要暂时停止周清理任务：
```bash
python3 scripts/task_manager.py update --id weekly-cleanup --disable
```

### 重新启用任务
```bash
python3 scripts/task_manager.py update --id weekly-cleanup --enable
```

### 删除任务
如果不再需要某个任务：
```bash
python3 scripts/task_manager.py delete --id hourly-monitor
```

## 6. 监控和调试

### 查看正在运行的调度器进程
```bash
ps aux | grep scheduler_daemon
```

### 查看任务日志
```bash
tail -f ~/.cron-scheduler/logs/daily-backup.log
```

### 运行调度器在前台以便调试
```bash
python3 scripts/scheduler_daemon.py run
```

## 7. 高级配置示例

如果你想手动编辑任务配置文件（位于 `~/.cron-scheduler/config/tasks.json`），这里是一个高级配置示例：

```json
[
  {
    "id": "complex-task",
    "name": "Complex Scheduled Task",
    "schedule": "30 1-5 * * 1-5",
    "command": "/path/to/complex/script.sh --option1=value1 --option2=value2",
    "enabled": true,
    "description": "Runs complex script at 1:30 AM, 2:30 AM, ..., 5:30 AM on weekdays",
    "logging": {
      "level": "DEBUG",
      "file": "complex-task-debug.log"
    },
    "retry_policy": {
      "max_retries": 5,
      "backoff_multiplier": 3
    }
  },
  {
    "id": "web-scraping-task",
    "name": "Web Scraping Task",
    "schedule": "*/15 9-17 * * 1-5",
    "command": "python3 /path/to/web_scraper.py",
    "enabled": true,
    "description": "Scrapes data every 15 minutes during business hours on weekdays",
    "logging": {
      "level": "INFO",
      "file": "web-scraper.log"
    },
    "retry_policy": {
      "max_retries": 3,
      "backoff_multiplier": 2
    }
  }
]
```

这个配置定义了一个任务，在工作日上午9点到下午5点之间每15分钟运行一次，适用于数据抓取等场景。

## 8. 停止调度器

当需要停止调度器时：
```bash
python3 scripts/scheduler_daemon.py stop
```

这样我们就完成了cron调度器框架的完整示例，包括安装、配置、管理和监控任务的全过程。