---
name: x-url-pdf
description: 使用浏览器抓取外部网页内容并导出为高清 PDF 格式（支持中文、表格、图片）。适用于需要将文档、技术规范或网页文章固化为标准化 PDF 输出的场景。
---

# x-url-pdf

此技能通过 `Browser` subagent 与 Python PDF 生成脚本相结合，实现从外部 URL 到结构化 PDF 的转换。

## 工作流

1. **抓取内容**：使用 `task` 工具启动 `Browser` subagent 访问目标 URL。
   - 要求提取：页面标题、核心正文、关键图片 URL、Markdown 格式的表格。
   - 提示：如果页面包含懒加载内容，指示 subagent 先向下滚动。
2. **格式化 Markdown**：将抓取的数据整理为整洁的 Markdown 文件（临时）。
3. **转换为 PDF**：调用 `scripts/md_to_pdf.py` 将 Markdown 转换为 PDF。
   - 命令：`python3 .qoder/skills/x-url-pdf/scripts/md_to_pdf.py temp.md output.pdf`
4. **清理**：删除临时的 Markdown 文件。

## 指令细节

### 抓取要求
- **标题**：提取主标题作为 PDF 的内部 H1。
- **图片**：保持图片链接有效。
- **表格**：确保表格行列对齐，使用标准 Markdown 语法。

### 导出配置
- 字体：默认使用 `STHeiti Light` 以支持中文字符。
- 布局：A4 纸张，标准页边距。

## 故障排除
- **图片丢失**：确认图片 URL 是绝对路径而非相对路径。
- **乱码**：确保系统安装了 `wkhtmltopdf` 并支持中文字体。
