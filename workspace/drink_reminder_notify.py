#!/usr/bin/env python3
import os
import sys

def send_notification(message):
    """发送桌面通知"""
    script = f'''
    osascript -e 'display notification "{message}" with title "喝水提醒" subtitle "虾铁蛋温馨提示"'
    '''
    os.system(script)

if __name__ == "__main__":
    message = "天尊，该喝水啦！💧 记得多喝水保持健康哦~"
    if len(sys.argv) > 1:
        message = sys.argv[1]
    
    send_notification(message)
    print(f"Notification sent: {message}")