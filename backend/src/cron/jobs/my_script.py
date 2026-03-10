"""示例：每隔5分钟执行的脚本任务"""

import asyncio
from datetime import datetime
from .base import BaseJob


class MyScriptJob(BaseJob):
    """自定义脚本任务示例"""
    
    def __init__(self):
        super().__init__("my_script", "My Script Job")
    
    async def _run(self, **kwargs):
        """实际执行的任务逻辑"""
        # 在这里编写你的脚本逻辑
        current_time = datetime.now().isoformat()
        
        # 示例：执行一些操作
        result = {
            "message": "脚本执行成功",
            "timestamp": current_time,
            "params": kwargs,
        }
        
        # 你可以在这里添加：
        # - 数据备份
        # - 发送通知
        # - 清理临时文件
        # - 调用外部API
        # - 等等...
        
        self.logger.info(f"脚本执行完成: {result}")
        return result


# 这是调度器调用的入口函数
async def my_script_task(**kwargs):
    """任务入口函数"""
    job = MyScriptJob()
    return await job.execute()
