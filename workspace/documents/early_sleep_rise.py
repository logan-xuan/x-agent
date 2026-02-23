from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors

def create_early_sleep_rise_pdf():
    # 创建PDF文档
    doc = SimpleDocTemplate(
        "documents/早睡早起健康生活指南.pdf",
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18,
    )
    
    # 获取样式
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CustomTitle', fontSize=24, alignment=1, spaceAfter=30, textColor=colors.darkblue))
    styles.add(ParagraphStyle(name='Heading2', fontSize=16, spaceAfter=12, textColor=colors.darkgreen))
    
    # 构建内容
    story = []
    
    # 标题
    title = Paragraph("早睡早起，健康生活指南", styles['CustomTitle'])
    story.append(title)
    
    # 引言
    intro_text = """
    早睡早起是一种健康的生活习惯，有助于身心健康和工作效率的提升。
    本指南将为您介绍早睡早起的重要性及实践方法。
    """
    intro = Paragraph(intro_text, styles['Normal'])
    story.append(intro)
    story.append(Spacer(1, 12))
    
    # 早睡早起的好处
    benefits_title = Paragraph("早睡早起的好处", styles['Heading2'])
    story.append(benefits_title)
    
    benefits_list = [
        "增强免疫力：充足睡眠有助于身体修复和免疫系统功能",
        "改善记忆力：睡眠有助于巩固记忆，提高学习效率",
        "促进新陈代谢：规律作息有助于维持健康的体重",
        "提升情绪：良好睡眠有助于情绪稳定和心理健康",
        "增强专注力：充足休息可以提高白天的工作效率"
    ]
    
    for benefit in benefits_list:
        story.append(Paragraph(f"• {benefit}", styles['Normal']))
        story.append(Spacer(1, 6))
    
    story.append(Spacer(1, 12))
    
    # 实践建议
    tips_title = Paragraph("如何养成早睡早起的习惯", styles['Heading2'])
    story.append(tips_title)
    
    tips_list = [
        "设定固定的睡觉和起床时间，即使在周末也要保持一致",
        "睡前避免使用电子设备，减少蓝光对睡眠的影响",
        "营造舒适的睡眠环境，保持房间凉爽、安静和黑暗",
        "建立睡前放松仪式，如阅读、冥想或温水泡脚",
        "早晨起床后立即接触自然光线，有助于调节生物钟",
        "适量运动，但避免在睡前3小时内进行剧烈运动"
    ]
    
    for tip in tips_list:
        story.append(Paragraph(f"• {tip}", styles['Normal']))
        story.append(Spacer(1, 6))
    
    story.append(Spacer(1, 12))
    
    # 生物钟调节
    circadian_title = Paragraph("了解您的生物钟", styles['Heading2'])
    story.append(circadian_title)
    
    circadian_text = """
    人体有一个内在的生物钟，大约以24小时为周期调节生理活动。
    早睡早起有助于与自然的昼夜节律同步，使身体各系统协调运作。
    当我们违背生物钟规律时，可能会出现疲劳、注意力不集中等问题。
    """
    story.append(Paragraph(circadian_text, styles['Normal']))
    story.append(Spacer(1, 12))
    
    # 结论
    conclusion_title = Paragraph("结语", styles['Heading2'])
    story.append(conclusion_title)
    
    conclusion_text = """
    早睡早起不仅是一种生活习惯，更是一种生活态度。
    通过坚持这一简单而有效的生活方式，您可以显著改善身心健康，
    提升生活质量，并在日常生活中获得更多的活力和幸福感。
    记住，改变需要时间和毅力，从小步开始，逐步形成稳定的作息规律。
    """
    story.append(Paragraph(conclusion_text, styles['Normal']))
    
    # 生成PDF
    doc.build(story)
    print("PDF文档已成功创建：documents/早睡早起健康生活指南.pdf")

if __name__ == "__main__":
    create_early_sleep_rise_pdf()