import markdown
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

def create_pdf_from_md(md_file, pdf_file):
    # 注册中文字体（如果可用）
    try:
        # 尝试使用系统中文字体
        pdfmetrics.registerFont(TTFont('SimSun', '/System/Library/Fonts/SimSun.ttc'))
        font_registered = True
    except:
        print("Warning: Could not register SimSun font, using default")
        font_registered = False

    # 读取markdown文件
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()

    # 转换markdown为HTML
    html_content = markdown.markdown(md_content, extensions=['extra', 'codehilite'])

    # 创建PDF文档
    doc = SimpleDocTemplate(pdf_file, pagesize=letter)
    story = []

    # 设置样式
    styles = getSampleStyleSheet()
    
    # 定义标题和正文样式
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=1,  # 居中
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=18,
        spaceAfter=15,
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=12,
        leading=14,
    )

    # 解析HTML内容并转换为PDF元素
    lines = html_content.split('\n')
    
    for line in lines:
        line = line.strip()
        
        if line.startswith('<h1>') or line.startswith('# '):
            # 处理一级标题
            text = line.replace('<h1>', '').replace('</h1>', '').replace('# ', '')
            if font_registered:
                story.append(Paragraph(text, title_style))
            else:
                story.append(Paragraph(text, title_style))
                
        elif line.startswith('<h2>') or line.startswith('## '):
            # 处理二级标题
            text = line.replace('<h2>', '').replace('</h2>', '').replace('## ', '')
            if font_registered:
                story.append(Paragraph(text, heading_style))
            else:
                story.append(Paragraph(text, heading_style))
                
        elif line.startswith('<h3>') or line.startswith('### '):
            # 处理三级标题
            text = line.replace('<h3>', '').replace('</h3>', '').replace('### ', '')
            h3_style = ParagraphStyle(
                'CustomH3',
                parent=styles['Heading3'],
                fontSize=14,
                spaceAfter=10,
            )
            if font_registered:
                story.append(Paragraph(text, h3_style))
            else:
                story.append(Paragraph(text, h3_style))
                
        elif line and not line.startswith('<'):
            # 处理普通段落
            if '<p>' in line:
                text = line.replace('<p>', '').replace('</p>', '')
            else:
                text = line
                
            # 替换特殊字符
            text = text.replace('&nbsp;', '&amp;nbsp;')
            
            if font_registered:
                story.append(Paragraph(text, body_style))
            else:
                story.append(Paragraph(text, body_style))
        
        # 添加间距
        if line and not line.startswith('<h'):
            story.append(Spacer(1, 12))

    # 构建PDF
    doc.build(story)
    print(f"PDF generated successfully: {pdf_file}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 3:
        print("Usage: python generate_pdf.py <input.md> <output.pdf>")
        sys.exit(1)
    
    md_file = sys.argv[1]
    pdf_file = sys.argv[2]
    
    if not os.path.exists(md_file):
        print(f"Error: Markdown file {md_file} does not exist")
        sys.exit(1)
    
    create_pdf_from_md(md_file, pdf_file)