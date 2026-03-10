#!/usr/bin/env python3
"""将 workspace:scripts/hello_cron.py:main 注入到 APScheduler jobstore。

这个脚本会：
1. 初始化 APScheduler
2. 创建一个定时任务（1分钟后执行）
3. 将任务添加到 jobstore
4. 验证任务是否成功添加
"""

import sys
import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 确保从 backend 目录运行
backend_dir = Path(__file__).parent.parent
if Path.cwd() != backend_dir:
    print(f"请从 backend 目录运行此脚本")
    print(f"当前目录: {Path.cwd()}")
    print(f"预期目录: {backend_dir}")
    sys.exit(1)

from src.cron.scheduler import get_scheduler
from src.cron.config import JobConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def inject_hello_cron_job():
    """注入 hello_cron 任务到 jobstore"""
    
    print("="*60)
    print("注入 workspace:scripts/hello_cron.py:main 到 jobstore")
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
    
    # 计算执行时间（1分钟后）
    run_time = datetime.now(timezone.utc) + timedelta(minutes=1)
    
    job_config = JobConfig(
        id="hello_cron_test",
        name="Hello Cron Test",
        func="workspace:scripts/hello_cron.py:main",
        trigger_type="date",
        trigger_args={"run_time": run_time.isoformat()},
        enabled=True,
        metadata={
            "description": "测试 APScheduler 调用 workspace 脚本",
            "created_by": "inject_hello_cron_job.py",
        }
    )
    
    print(f"   Task ID: {job_config.id}")
    print(f"   Name: {job_config.name}")
    print(f"   Func: {job_config.func}")
    print(f"   Trigger: {job_config.trigger_type}")
    print(f"   Run Time: {run_time} (UTC)")
    
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
        return
    
    # 验证任务是否在 jobstore 中
    print("\n4. 验证任务是否在 jobstore 中...")
    try:
        schedules = await scheduler.get_schedules()
        
        found = False
        for sched in schedules:
            if sched['id'] == job_config.id:
                found = True
                print(f"✅ 找到任务:")
                print(f"   ID: {sched['id']}")
                print(f"   Task ID: {sched['task_id']}")
                print(f"   Trigger Type: {sched['trigger']['type']}")
                print(f"   Trigger Args: {sched['trigger']['args']}")
                print(f"   Next Fire Time: {sched['next_fire_time']}")
                print(f"   Paused: {sched['paused']}")
                break
        
        if not found:
            print(f"❌ 任务未在 jobstore 中找到")
        else:
            print(f"\n✅ 任务验证成功！")
            
    except Exception as e:
        print(f"❌ 验证任务失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 列出所有任务
    print("\n5. 当前 jobstore 中的所有任务:")
    try:
        schedules = await scheduler.get_schedules()
        print(f"   总计: {len(schedules)} 个任务")
        for i, sched in enumerate(schedules, 1):
            print(f"\n   任务 {i}:")
            print(f"     ID: {sched['id']}")
            print(f"     Task ID: {sched['task_id']}")
            print(f"     Trigger: {sched['trigger']['type']}")
            print(f"     Next Run: {sched['next_fire_time']}")
    except Exception as e:
        print(f"❌ 列出任务失败: {e}")
    
    print("\n" + "="*60)
    print("注入完成！")
    print("="*60)
    print("\n提示：")
    print(f"1. 任务将在 {run_time} (UTC) 执行")
    print("2. 可以查看日志文件确认执行情况")
    print("3. Scheduler 将继续运行，按 Ctrl+C 停止")
    print()
    
    # 保持运行以便观察任务执行
    try:
        print("等待任务执行... (按 Ctrl+C 停止)")
        # 等待 2 分钟以确保任务执行
        await asyncio.sleep(120)
    except KeyboardInterrupt:
        print("\n\n正在停止 scheduler...")
    finally:
        await scheduler.stop()
        print("✅ Scheduler 已停止")


if __name__ == "__main__":
    asyncio.run(inject_hello_cron_job())
