#!/usr/bin/env python3
import markdown2
import pdfkit
from pathlib import Path

def md_to_pdf(md_file_path, pdf_file_path):
    """Convert markdown file to PDF"""
    # Read markdown file
    with open(md_file_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # Convert markdown to HTML
    html = markdown2.markdown(md_content, extras=['tables', 'fenced-code-blocks'])
    
    # Create full HTML document
    full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>2026年人工智能发展趋势研究报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1, h2, h3 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        code {{ background-color: #f4f4f4; padding: 2px 4px; }}
    </style>
</head>
<body>
    {html}
</body>
</html>"""
    
    # Convert HTML to PDF
    options = {
        'page-size': 'A4',
        'margin-top': '0.75in',
        'margin-right': '0.75in',
        'margin-bottom': '0.75in',
        'margin-left': '0.75in',
        'encoding': "UTF-8",
        'no-outline': None
    }
    
    try:
        pdfkit.from_string(full_html, pdf_file_path, options=options)
        print(f"PDF generated successfully: {pdf_file_path}")
    except Exception as e:
        print(f"Error generating PDF: {e}")
        # Fallback: save HTML file instead
        html_path = pdf_file_path.replace('.pdf', '.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(full_html)
        print(f"Saved HTML file instead: {html_path}")

if __name__ == "__main__":
    md_path = "/Users/xuan.lx/Documents/x-agent/x-agent/workspace/documents/AI_Trends_2026_Research.md"
    pdf_path = "/Users/xuan.lx/Documents/x-agent/x-agent/workspace/pdfs/AI_Trends_2026_Research.pdf"
    
    # Ensure output directory exists
    Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
    
    md_to_pdf(md_path, pdf_path)