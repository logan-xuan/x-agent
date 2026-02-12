import markdown
import pdfkit
import sys
import os

def generate_pdf(md_file, pdf_file, title="Content"):
    # Read markdown content
    with open(md_file, 'r', encoding='utf-8') as f:
        text = f.read()

    # Convert markdown to HTML
    html_content = markdown.markdown(text, extensions=['extra', 'codehilite'])

    # HTML wrapper with CSS for Chinese support and styling
    full_html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: "STHeiti Light", "Heiti SC", "PingFang SC", "Microsoft YaHei", sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 900px;
                margin: 0 auto;
                padding: 30px;
            }}
            h1, h2, h3 {{
                color: #2c3e50;
                border-bottom: 1px solid #eee;
                padding-bottom: 10px;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 20px 0;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 12px;
                text-align: left;
            }}
            th {{
                background-color: #f8f9fa;
            }}
            img {{
                max-width: 100%;
                height: auto;
                display: block;
                margin: 20px auto;
            }}
            code {{
                background-color: #f4f4f4;
                padding: 2px 4px;
                border-radius: 4px;
                font-family: monospace;
            }}
            pre {{
                background-color: #f4f4f4;
                padding: 15px;
                border-radius: 4px;
                overflow-x: auto;
            }}
        </style>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """

    options = {
        'page-size': 'A4',
        'margin-top': '0.75in',
        'margin-right': '0.75in',
        'margin-bottom': '0.75in',
        'margin-left': '0.75in',
        'encoding': "UTF-8",
        'enable-local-file-access': None
    }

    try:
        pdfkit.from_string(full_html, pdf_file, options=options)
        print(f"Successfully generated {pdf_file}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 md_to_pdf.py <input.md> <output.pdf>")
    else:
        generate_pdf(sys.argv[1], sys.argv[2])
