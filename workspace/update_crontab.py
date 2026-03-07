#!/usr/bin/env python3
import os
import subprocess
import tempfile

def get_current_crontab():
    """获取当前的crontab配置"""
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout
        else:
            return ""
    except Exception as e:
        print(f"获取当前crontab失败: {e}")
        return ""

def add_drink_reminder(crontab_content):
    """添加喝水提醒到crontab"""
    # 检查是否已经存在喝水提醒
    if "drink_reminder_notify.py" not in crontab_content:
        # 添加新的喝水提醒行
        lines = crontab_content.split('\n')
        # 找到最后一个非空行的位置
        last_non_empty = -1
        for i, line in enumerate(lines):
            if line.strip():
                last_non_empty = i
        
        # 在最后添加喝水提醒
        new_line = "*/5 * * * * /usr/bin/python3 /Users/hzliuxuan/Documents/qoder-workspace/x-agent/workspace/drink_reminder_notify.py \"天尊，该喝水啦！💧 记得多喝水保持健康哦~\""
        
        if last_non_empty >= 0:
            lines.insert(last_non_empty + 1, new_line)
        else:
            lines.append(new_line)
        
        return '\n'.join(lines)
    else:
        print("喝水提醒已存在于crontab中")
        return crontab_content

def save_to_temp_file(content):
    """将内容保存到临时文件"""
    temp_file = '/tmp/new_crontab.txt'
    with open(temp_file, 'w') as f:
        f.write(content)
    return temp_file

if __name__ == "__main__":
    print("正在更新crontab配置...")
    
    # 获取当前crontab
    current_crontab = get_current_crontab()
    print("当前crontab内容:")
    print(current_crontab)
    
    # 添加喝水提醒
    updated_crontab = add_drink_reminder(current_crontab)
    print("\n更新后的crontab内容:")
    print(updated_crontab)
    
    # 保存到临时文件
    temp_file = save_to_temp_file(updated_crontab)
    print(f"\n更新内容已保存到临时文件: {temp_file}")
    print("请使用以下命令手动更新crontab:")
    print(f"crontab {temp_file}")
    print("\n或者您可以复制以下内容手动添加到crontab中:")
    print("-" * 50)
    print("*/5 * * * * /usr/bin/python3 /Users/hzliuxuan/Documents/qoder-workspace/x-agent/workspace/drink_reminder_notify.py \"天尊，该喝水啦！💧 记得多喝水保持健康哦~\"")
    print("-" * 50)