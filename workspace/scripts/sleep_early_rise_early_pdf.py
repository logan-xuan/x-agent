from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
import os

def create_sleep_early_rise_early_pdf():
    # 创建PDF文档
    pdf_path = "/Users/xuan.lx/Documents/x-agent/x-agent/workspace/pdfs/早睡早起健康生活指南.pdf"
    
    # 确保目录存在
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18
    )
    
    # 获取样式
    styles = getSampleStyleSheet()
    
    # 自定义标题样式
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=1,  # 居中
        textColor=colors.darkblue
    )
    
    # 自定义副标题样式
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=20,
        alignment=1,  # 居中
        textColor=colors.darkgreen
    )
    
    # 正文样式
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=12,
        leading=16
    )
    
    # 创建内容列表
    story = []
    
    # 标题页
    title = Paragraph("早睡早起，健康生活指南", title_style)
    story.append(title)
    
    subtitle = Paragraph("养成良好作息习惯，提升生活质量", subtitle_style)
    story.append(subtitle)
    
    story.append(Spacer(1, 30))
    
    # 引言部分
    intro_text = """
    <b>引言</b><br/>
    早睡早起是一种有益健康的生活习惯。这种作息模式符合人体生物钟的自然规律，
    有助于维持身心健康，提高工作效率，并促进整体生活质量的改善。
    """
    intro_para = Paragraph(intro_text, body_style)
    story.append(intro_para)
    
    story.append(Spacer(1, 20))
    
    # 早睡的好处
    benefits_title = Paragraph("<b>早睡的好处</b>", styles['Heading2'])
    story.append(benefits_title)
    
    benefits_list = [
        "增强免疫力：充足的睡眠有助于免疫系统的正常运作",
        "促进身体修复：夜间是细胞修复和再生的重要时期",
        "改善记忆力：睡眠有助于巩固记忆和学习能力",
        "调节情绪：良好的睡眠可以稳定情绪，减少焦虑和抑郁",
        "维护心血管健康：规律的睡眠有助于维持血压和心脏功能"
    ]
    
    for benefit in benefits_list:
        bullet_point = Paragraph(f"• {benefit}", body_style)
        story.append(bullet_point)
    
    story.append(Spacer(1, 20))
    
    # 早起的好处
    early_rise_title = Paragraph("<b>早起的好处</b>", styles['Heading2'])
    story.append(early_rise_title)
    
    early_rise_benefits = [
        "提高效率：早晨大脑清醒，专注力强，适合处理复杂任务",
        "拥有更多时间：早起可以获得一段安静的时间用于自我提升",
        "享受宁静时光：清晨环境安静，适合冥想、运动或阅读",
        "规律作息：早起有助于形成稳定的生物钟",
        "精神状态佳：早起的人通常拥有更积极的心态"
    ]
    
    for benefit in early_rise_benefits:
        bullet_point = Paragraph(f"• {benefit}", body_style)
        story.append(bullet_point)
    
    story.append(Spacer(1, 20))
    
    # 如何养成早睡早起的习惯
    habit_title = Paragraph("<b>如何养成早睡早起的习惯</b>", styles['Heading2'])
    story.append(habit_title)
    
    tips_list = [
        "<b>逐步调整：</b>每天提前15分钟上床，循序渐进地调整作息",
        "<b>创造良好环境：</b>保持卧室安静、黑暗和凉爽",
        "<b>避免睡前刺激：</b>睡前1-2小时避免电子设备和咖啡因",
        "<b>建立睡前仪式：</b>如洗热水澡、读书、冥想等放松活动",
        "<b>坚持固定时间：</b>即使在周末也尽量保持一致的作息时间",
        "<b>晨间阳光：</b>起床后接触自然光，帮助重置生物钟",
        "<b>适量运动：</b>白天适量运动有助于夜间更好入睡"
    ]
    
    for tip in tips_list:
        bullet_point = Paragraph(f"• {tip}", body_style)
        story.append(bullet_point)
    
    story.append(Spacer(1, 20))
    
    # 早睡早起的一天安排示例
    schedule_title = Paragraph("<b>早睡早起的一天安排示例</b>", styles['Heading2'])
    story.append(schedule_title)
    
    schedule_text = """
    <b>22:00 - 准备睡觉</b><br/>
    • 关闭电子设备<br/>
    • 洗漱准备<br/>
    • 放松身心，如阅读或冥想<br/><br/>

    <b>22:30 - 入睡</b><br/>
    • 确保卧室环境舒适<br/>
    • 尝试深呼吸或冥想助眠<br/><br/>

    <b>5:30 - 起床</b><br/>
    • 拉开窗帘让自然光进入<br/>
    • 喝一杯温水<br/>
    • 进行简单拉伸或冥想<br/><br/>

    <b>6:00-8:00 - 晨间活动</b><br/>
    • 运动锻炼（如跑步、瑜伽）<br/>
    • 享用营养早餐<br/>
    • 规划当日任务<br/><br/>

    <b>全天效果</b><br/>
    • 精力充沛，工作效率高<br/>
    • 心情愉悦，压力较小<br/>
    • 有时间进行自我提升<br/>
    """
    schedule_para = Paragraph(schedule_text, body_style)
    story.append(schedule_para)
    
    story.append(Spacer(1, 20))
    
    # 结语
    conclusion_title = Paragraph("<b>结语</b>", styles['Heading2'])
    story.append(conclusion_title)
    
    conclusion_text = """
    早睡早起不仅是一种生活习惯，更是一种生活态度。通过坚持这一简单而有效的生活方式，
    我们可以更好地照顾自己的身心健康，提高生活质量和工作效率。记住，改变需要时间和耐心，
    但只要持之以恒，早睡早起一定会成为您生活中最宝贵的财富之一。
    """
    conclusion_para = Paragraph(conclusion_text, body_style)
    story.append(conclusion_para)
    
    # 添加一页额外的健康贴士
    story.append(PageBreak())
    
    health_tips_title = Paragraph("<b>健康睡眠小贴士</b>", title_style)
    story.append(health_tips_title)
    
    health_tips = [
        "<b>饮食调节：</b>晚餐不宜过饱，避免辛辣、油腻食物，可适当摄入助眠食物如牛奶、香蕉、燕麦等",
        "<b>温度控制：</b>室温保持在18-22°C较为适宜，略低的温度有助于入睡",
        "<b>睡眠时长：</b>成年人每日需7-9小时睡眠，找到适合自己的睡眠时长",
        "<b>午休管理：</b>如有午休，控制在20-30分钟，避免影响夜间睡眠",
        "<b>睡前放松：</b>可尝试泡脚、听轻音乐、做深呼吸练习等放松方法",
        "<b>避免熬夜：</b>即使有紧急事务，也应尽量避免连续熬夜，以免打乱生物钟"
    ]
    
    for tip in health_tips:
        bullet_point = Paragraph(f"• {tip}", body_style)
        story.append(bullet_point)
    
    # 构建PDF
    doc.build(story)
    return pdf_path

if __name__ == "__main__":
    pdf_path = create_sleep_early_rise_early_pdf()
    print(f"PDF文档已成功创建: {pdf_path}")