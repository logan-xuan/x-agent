#!/usr/bin/env python3
"""
将Markdown文件转换为PDF
"""

import markdown
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration

def markdown_to_pdf(md_file, pdf_file):
    # 读取Markdown文件
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # 将Markdown转换为HTML
    html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])
    
    # 添加基本的HTML结构和样式
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>2026年AI发展趋势深度研究报告</title>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """
    
    # 创建PDF
    font_config = FontConfiguration()
    html_doc = HTML(string=full_html)
    css = CSS(string='''
        @page {
            margin: 1in;
        }
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            font-size: 12pt;
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #000;
        }
        h2 {
            color: #555;
            margin-top: 1.5em;
        }
        table {
            border-collapse: collapse;
            width: 100%;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }
        th {
            background-color: #f2f2f2;
        }
    ''', font_config=font_config)
    
    html_doc.write_pdf(pdf_file, stylesheets=[css], font_config=font_config)

if __name__ == "__main__":
    # 输入和输出文件路径
    input_md = "workspace/documents/2026_ai_trends_research.md"
    output_pdf = "workspace/pdfs/2026_ai_trends_research.pdf"
    
    # 转换
    markdown_to_pdf(input_md, output_pdf)
    print(f"PDF已生成: {output_pdf}")