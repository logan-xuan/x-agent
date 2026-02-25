#!/usr/bin/env python3
"""Create a multi-page PDF from Markdown file with Chinese text support.

Usage:
    python create_pdf_from_md.py <output.pdf> <input.md> [title]
    
Example:
    python create_pdf_from_md.py report.pdf report.pdf "2026 AI 趋势报告"
    
Features:
    - Reads content from Markdown file
    - Supports multi-page PDF generation
    - Chinese font support (PingFang/STHeiti)
    - Automatic line wrapping and page breaks
    - Section headers and content formatting
    - Footer with page numbers
"""

import sys
import os
from pathlib import Path
from typing import List, Tuple


def register_chinese_font():
    """Register macOS system Chinese fonts"""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        
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
                        font = TTFont('Chinese', font_path, subfontIndex=0)
                    else:
                        font = TTFont('Chinese', font_path)
                    
                    pdfmetrics.registerFont(font)
                    print(f"✅ Registered Chinese font: {font_path}")
                    return True
                except Exception as e:
                    print(f"⚠️ Failed to register {font_path}: {e}")
                    continue
        
        print("⚠️ No Chinese font available, using default")
        return False
    except ImportError:
        print("❌ reportlab not installed. Run: pip3 install reportlab")
        return False


def parse_markdown_content(content: str) -> List[Tuple[str, str, int]]:
    """Parse markdown content into sections.
    
    Returns:
        List of tuples: (section_title, section_content, level)
    """
    sections = []
    lines = content.split('\n')
    current_section = None
    current_content = []
    current_level = 0
    
    for line in lines:
        # Check for headers
        if line.startswith('### '):
            # Save previous section
            if current_section:
                sections.append((current_section, '\n'.join(current_content), current_level))
            
            current_section = line[4:].strip()
            current_content = []
            current_level = 3
        elif line.startswith('## '):
            # Save previous section
            if current_section:
                sections.append((current_section, '\n'.join(current_content), current_level))
            
            current_section = line[3:].strip()
            current_content = []
            current_level = 2
        elif line.startswith('# '):
            # Save previous section
            if current_section:
                sections.append((current_section, '\n'.join(current_content), current_level))
            
            current_section = line[2:].strip()
            current_content = []
            current_level = 1
        else:
            # Add content to current section
            if line.strip():  # Skip empty lines
                current_content.append(line.strip())
    
    # Save last section
    if current_section:
        sections.append((current_section, '\n'.join(current_content), current_level))
    
    return sections


def wrap_text(text: str, max_width: int, font_name: str, font_size: int, canvas) -> List[str]:
    """Wrap text to fit within max_width."""
    try:
        from reportlab.pdfbase.pdfmetrics import stringWidth
    except ImportError:
        return [text]
    
    words = text.replace(' ', '\n').split('\n')
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word]) if current_line else word
        width = stringWidth(test_line, font_name, font_size)
        
        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return lines


def create_pdf_from_md(filename: str, md_file: str, title: str = None):
    """Create a multi-page PDF from Markdown file.
    
    Args:
        filename: Output PDF filename
        md_file: Input Markdown file path
        title: Optional document title (uses first header if not provided)
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm, inch
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import black, gray
    except ImportError:
        print("❌ reportlab not installed. Run: pip3 install reportlab")
        sys.exit(1)
    
    # Read markdown content
    if not os.path.exists(md_file):
        print(f"❌ Markdown file not found: {md_file}")
        sys.exit(1)
    
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse markdown
    sections = parse_markdown_content(content)
    
    if not sections:
        print("⚠️ No content found in markdown file")
        sys.exit(1)
    
    # Use first header as title if not provided
    if not title:
        title = sections[0][0] if sections else "Report"
    
    # Register Chinese font
    has_chinese_font = register_chinese_font()
    
    # Create PDF
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    
    # Margins
    left_margin = 2.5 * cm
    right_margin = 2.5 * cm
    top_margin = 2.5 * cm
    bottom_margin = 2.5 * cm
    
    # Content width
    content_width = width - left_margin - right_margin
    
    # Starting position
    y_position = height - top_margin
    
    # Page counter
    page_number = 1
    
    # Draw title page
    if has_chinese_font:
        c.setFont('Chinese', 28)
    else:
        c.setFont("Helvetica-Bold", 28)
    
    # Center title
    title_width = c.stringWidth(title, c._fontname, c._fontsize)
    c.drawString((width - title_width) / 2, height / 2, title)
    
    # Subtitle or info
    if has_chinese_font:
        c.setFont('Chinese', 14)
    else:
        c.setFont("Helvetica", 14)
    
    subtitle = f"Generated by X-Agent PDF Skill"
    subtitle_width = c.stringWidth(subtitle, c._fontname, c._fontsize)
    c.drawString((width - subtitle_width) / 2, height / 2 - 50, subtitle)
    
    # Show total sections
    info_text = f"Total sections: {len(sections)}"
    info_width = c.stringWidth(info_text, c._fontname, c._fontsize)
    c.drawString((width - info_width) / 2, height / 2 - 100, info_text)
    
    # Page number
    if has_chinese_font:
        c.setFont('Chinese', 10)
    else:
        c.setFont("Helvetica", 10)
    
    c.drawCentredString(width / 2, 1.5 * cm, f"Page {page_number}")
    
    # Start new page for content
    c.showPage()
    page_number += 1
    
    # Reset position
    y_position = height - top_margin
    
    # Process each section
    for section_title, section_content, level in sections:
        # Set font based on level
        if level == 1:
            font_size = 20
            font_style = 'Bold'
        elif level == 2:
            font_size = 16
            font_style = 'Bold'
        else:
            font_size = 14
            font_style = 'Regular'
        
        if has_chinese_font:
            c.setFont('Chinese', font_size)
        else:
            c.setFont(f"Helvetica-{font_style}", font_size)
        
        # Check if we need a new page
        if y_position < bottom_margin + 50:
            # Add page number to current page
            if has_chinese_font:
                c.setFont('Chinese', 10)
            else:
                c.setFont("Helvetica", 10)
            c.drawCentredString(width / 2, 1.5 * cm, f"Page {page_number}")
            
            # New page
            c.showPage()
            page_number += 1
            y_position = height - top_margin
            
            # Reset font
            if has_chinese_font:
                c.setFont('Chinese', font_size)
            else:
                c.setFont(f"Helvetica-{font_style}", font_size)
        
        # Draw section title
        c.drawString(left_margin, y_position, section_title)
        y_position -= (font_size + 5)
        
        # Draw section content
        if has_chinese_font:
            c.setFont('Chinese', 12)
        else:
            c.setFont("Helvetica", 12)
        
        content_lines = section_content.split('\n')
        for line in content_lines:
            # Wrap long lines
            wrapped_lines = wrap_text(line, content_width, c._fontname, c._fontsize, c)
            
            for wrapped_line in wrapped_lines:
                # Check if we need a new page
                if y_position < bottom_margin:
                    # Add page number
                    if has_chinese_font:
                        c.setFont('Chinese', 10)
                    else:
                        c.setFont("Helvetica", 10)
                    c.drawCentredString(width / 2, 1.5 * cm, f"Page {page_number}")
                    
                    # New page
                    c.showPage()
                    page_number += 1
                    y_position = height - top_margin
                    
                    # Reset font
                    if has_chinese_font:
                        c.setFont('Chinese', 12)
                    else:
                        c.setFont("Helvetica", 12)
                
                c.drawString(left_margin, y_position, wrapped_line)
                y_position -= 18  # Line spacing
        
        # Add space after section
        y_position -= 10
    
    # Add page number to last page
    if has_chinese_font:
        c.setFont('Chinese', 10)
    else:
        c.setFont("Helvetica", 10)
    c.drawCentredString(width / 2, 1.5 * cm, f"Page {page_number}")
    
    # Save PDF
    c.save()
    
    print(f"✅ PDF created: {filename}")
    print(f"   Title: {title}")
    print(f"   Sections: {len(sections)}")
    print(f"   Pages: {page_number}")
    print(f"   File size: {Path(filename).stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    
    output_file = sys.argv[1]
    md_file = sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else None
    
    create_pdf_from_md(output_file, md_file, title)
