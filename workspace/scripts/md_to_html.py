#!/usr/bin/env python3
import markdown
from pathlib import Path

def md_to_html(md_content):
    """Convert markdown to HTML"""
    md = markdown.Markdown(extensions=['tables', 'fenced_code'])
    html = md.convert(md_content)
    full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>2026年AI发展趋势研究报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
        h1, h2, h3 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
{html}
</body>
</html>"""
    return full_html

# Read the markdown report
md_file_path = "/Users/xuan.lx/Documents/x-agent/x-agent/workspace/documents/AI_Trends_2026_Research.md"
with open(md_file_path, 'r', encoding='utf-8') as f:
    md_content = f.read()

# Convert to HTML
html_content = md_to_html(md_content)

# Write HTML file
html_file_path = "/Users/xuan.lx/Documents/x-agent/x-agent/workspace/documents/AI_Trends_2026_Research.html"
with open(html_file_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"HTML file created at {html_file_path}")