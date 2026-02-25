#!/usr/bin/env python3
"""
生成杭州天气旅游指南 PDF
使用 reportlab 库，完美支持中文
"""

import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# 注册中文字体
def register_chinese_font():
    """注册 macOS 系统中文字体"""
    font_paths = [
        '/System/Library/Fonts/PingFang.ttc',
        '/System/Library/Fonts/STHeiti Light.ttc',
        '/System/Library/Fonts/STHeiti Medium.ttc',
        '/Library/Fonts/Arial Unicode.ttf',
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                if font_path.endswith('.ttc'):
                    # TTC 字体需要指定 subfontIndex
                    font = TTFont('Chinese', font_path, subfontIndex=0)
                else:
                    font = TTFont('Chinese', font_path)
                
                pdfmetrics.registerFont(font)
                print(f"✅ 成功注册字体: {font_path}")
                return True
            except Exception as e:
                print(f"⚠️  尝试注册 {font_path} 失败: {e}")
                continue
    
    print("❌ 未找到可用的中文字体")
    return False

# 生成 PDF
def create_pdf():
    """生成杭州天气旅游指南 PDF"""
    if not register_chinese_font():
        sys.exit(1)
    
    # 输出路径
    output_dir = '/Users/xuan.lx/Documents/x-agent/x-agent/workspace/pdfs'
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'hangzhou_weather_report.pdf')
    
    # 创建 PDF
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    
    # 标题
    c.setFont('Chinese', 20)
    c.drawString(100, height - 100, '杭州明日天气旅游指南')
    
    # 天气信息
    c.setFont('Chinese', 14)
    c.drawString(100, height - 150, '日期: 2026年2月24日')
    c.drawString(100, height - 170, '天气: 小雨转多云')
    c.drawString(100, height - 190, '温度: 8°C ~ 13°C')
    c.drawString(100, height - 210, '风力: 北风<3级')
    
    # 推荐活动
    c.setFont('Chinese', 16)
    c.drawString(100, height - 250, '推荐活动:')
    c.setFont('Chinese', 12)
    c.drawString(100, height - 280, '1. 中国丝绸博物馆 - 室内景点，不受天气影响')
    c.drawString(100, height - 300, '2. 浙江省博物馆 - 欣赏江南文化和艺术品')
    c.drawString(100, height - 320, '3. 河坊街-南宋御街 - 古色古香的步行街，部分路段有遮蔽')
    c.drawString(100, height - 340, '4. 中国茶叶博物馆 - 了解龙井茶文化，室内参观')
    c.drawString(100, height - 360, '5. 京杭大运河游船 - 雨天乘船别有一番风味')
    
    # 一日旅游计划
    c.setFont('Chinese', 16)
    c.drawString(100, height - 400, '一日旅游计划:')
    c.setFont('Chinese', 12)
    c.drawString(100, height - 430, '上午 (9:00-12:00): 中国丝绸博物馆 -> 浙江省博物馆')
    c.drawString(100, height - 450, '下午 (13:30-17:00): 河坊街-南宋御街 -> 中国茶叶博物馆')
    c.drawString(100, height - 470, '傍晚 (17:00-19:00): 京杭大运河游船')
    
    # 出行提示
    c.setFont('Chinese', 16)
    c.drawString(100, height - 510, '出行提示:')
    c.setFont('Chinese', 12)
    c.drawString(100, height - 540, '• 必备物品: 雨伞或雨衣、防滑鞋')
    c.drawString(100, height - 560, '• 衣物建议: 保暖外套，温度较低')
    c.drawString(100, height - 580, '• 预约提醒: 热门景点建议提前在官方公众号预约')
    c.drawString(100, height - 600, '• 交通: 雨天路滑，请注意交通安全')
    
    # 保存
    c.save()
    
    file_size = os.path.getsize(output_path) / 1024
    print(f"\n✅ PDF 生成成功!")
    print(f"   文件路径: {output_path}")
    print(f"   文件大小: {file_size:.1f} KB")
    
    return output_path

if __name__ == '__main__':
    create_pdf()
