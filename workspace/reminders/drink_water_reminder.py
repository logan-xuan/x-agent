#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
喝水提醒脚本
"""
import os
import sys
from datetime import datetime

def main():
    """发送喝水提醒"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"[{timestamp}] 提醒：天尊，该喝水啦！记得补充水分哦~"
    
    # 将提醒写入日志
    log_file = os.path.expanduser("~/Documents/qoder-workspace/x-agent/workspace/reminders/water_reminder.log")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(message + "\n")

if __name__ == "__main__":
    main()