#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
哪吒闹海故事生成器 - 任务执行函数
用于定时任务调用
"""

import os
import sys
from datetime import datetime

def generate_nezhao_story_task(**kwargs):
    """
    生成哪吒闹海故事的任务函数
    这个函数将被定时任务调用
    """
    print(f"开始执行哪吒闹海故事生成任务 - {datetime.now()}")
    
    # 添加当前目录到模块搜索路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, current_dir)
    
    try:
        # 尝试导入我们的故事生成模块
        from nezhao_nao_hai import write_nezhao_story
        write_nezhao_story()
        print("哪吒闹海故事生成任务成功完成")
        return {"status": "success", "message": "故事生成成功"}
    except ImportError as e:
        print(f"导入模块失败: {e}")
        # 如果导入失败，使用备用方案
        def write_nezhao_story_fallback():
            """备用的故事生成函数"""
            import random
            
            # 故事元素
            opening_lines = [
                "话说那东海龙宫，水族万千，威严无比。",
                "传说东海之滨，波涛汹涌，龙宫巍峨。",
                "昔日东海龙宫，乃是四海之中最为威严之所。"
            ]
            
            conflict_lines = [
                "一日，小英雄哪吒来到海边嬉戏，见那海水清澈，便脱了衣裳下海游玩。",
                "那哪吒天生神力，趁兴来到海边玩耍，一入海中便搅动了龙宫。",
                "却说那哪吒年少气盛，来到海边游玩，一时兴起便潜入海中。"
            ]
            
            climax_lines = [
                "此举惊动了巡海夜叉李艮，提斧前来查探，却被哪吒以混天绫制服。",
                "龙王三太子敖丙见状大怒，手持画戟前来驱赶，不料反被哪吒所败。",
                "龙宫水族纷纷前来围攻，均不是哪吒的对手。"
            ]
            
            ending_lines = [
                "从此，哪吒闹海的故事传遍四海，成为千古佳话。",
                "哪吒神威震动东海，令龙王不敢小觑。",
                "这便是著名的哪吒闹海，流传至今仍为人津津乐道。"
            ]
            
            # 组合故事
            story = (
                f"# 哪吒闹海\n\n"
                f"## {random.choice(opening_lines)}\n\n"
                f"{random.choice(conflict_lines)}\n\n"
                f"{random.choice(climax_lines)}\n\n"
                f"{random.choice(ending_lines)}\n\n"
                f"*生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
            )
            
            # 写入文件
            filename = os.path.join(current_dir, "nezhao_story.txt")
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(story)
            
            print(f"哪吒闹海故事已生成并保存到 {filename} (时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        
        write_nezhao_story_fallback()
        print("哪吒闹海故事生成任务使用备用方案完成")
        return {"status": "success", "message": "故事生成成功(备用方案)"}
    except Exception as e:
        print(f"执行过程中出现错误: {e}")
        return {"status": "error", "message": f"执行失败: {str(e)}"}

# 如果直接运行此脚本，则执行任务
if __name__ == "__main__":
    result = generate_nezhao_story_task()
    print(result)