#!/usr/bin/env python3
"""快速测试：注入 hello_cron 任务到 jobstore 并立即退出。

这个脚本只验证任务能否成功添加到 jobstore，不等待执行。
"""

import sys
import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 确保从 backend 目录运行
backend_dir = Path(__file__).parent.parent
if Path.cwd() != backend_dir:
    print(f"请从 backend 目录运行此脚本")
    sys.exit(1)

from src.cron.scheduler import get_scheduler
from src.cron.config import JobConfig


async def quick_inject_test():
    """快速注入测试"""
    
    print("="*60)
    print("快速注入测试：workspace:scripts/hello_cron.py:main")
    print("="*60)
    
    # 获取 scheduler 实例
    scheduler = get_scheduler()
    
    # 初始化 scheduler
    print("\n1. 初始化 scheduler...")
    await scheduler.initialize()
    await scheduler.start()
    print("✅ Scheduler 已启动")
    
    # 创建任务配置
    print("\n2. 创建任务配置...")
    run_time = datetime.now(timezone.utc) + timedelta(minutes=1)
    
    job_config = JobConfig(
        id="hello_cron_test",
        name="Hello Cron Test",
        func="workspace:scripts/hello_cron.py:main",
        trigger_type="date",
        trigger_args={"run_time": run_time.isoformat()},
        enabled=True
    )
    
    print(f"   Task ID: {job_config.id}")
    print(f"   Func: {job_config.func}")
    print(f"   Run Time: {run_time}")
    
    # 添加任务到 jobstore
    print("\n3. 添加任务到 jobstore...")
    try:
        schedule_id = await scheduler.add_schedule(job_config)
        print(f"✅ 任务成功添加到 jobstore")
        print(f"   Schedule ID: {schedule_id}")
    except Exception as e:
        print(f"❌ 添加任务失败: {e}")
        import traceback
        traceback.print_exc()
        await scheduler.stop()
        return False
    
    # 验证任务
    print("\n4. 验证任务...")
    try:
        schedules = await scheduler.get_schedules()
        found = any(s['id'] == job_config.id for s in schedules)
        
        if found:
            print(f"✅ 任务验证成功！")
            
            # 显示任务详情
            for sched in schedules:
                if sched['id'] == job_config.id:
                    print(f"\n   任务详情:")
                    print(f"   - ID: {sched['id']}")
                    print(f"   - Task ID: {sched['task_id']}")
                    print(f"   - Trigger: {sched['trigger']['type']}")
                    print(f"   - Next Fire: {sched['next_fire_time']}")
                    break
        else:
            print(f"❌ 任务未找到")
            return False
            
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        return False
    
    # 停止 scheduler
    print("\n5. 停止 scheduler...")
    await scheduler.stop()
    print("✅ Scheduler 已停止")
    
    print("\n" + "="*60)
    print("✅ 测试完成！任务已成功注入到 jobstore")
    print("="*60)
    print(f"\n任务将在 {run_time} (UTC) 执行")
    print("如果 scheduler 正在运行，任务将自动执行")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(quick_inject_test())
    sys.exit(0 if success else 1)
