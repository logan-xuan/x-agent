---
name: x-url-md
description: 抓取指定 URL 的网页内容（标题、主体、内容、图片、表格），并将其转换为 Markdown 格式保存到项目的 xknowledge 目录中。当用户要求“抓取网页”、“保存文章到本地”、“将 URL 转为 MD”或“同步网页内容到知识库”时使用此技能。
---

# x-url-md

## 概览

该技能通过浏览器子代理抓取外部网页的完整内容，包括标题、正文、图片和表格，并将其持久化为 Markdown 文件。所有生成的文件将统一存放在项目根目录的 `xknowledge/` 文件夹中。

## 工作流

### 1. 抓取网页内容
使用 `browser` 子代理访问指定的 URL。
- **任务描述**：明确要求子代理提取标题、主体文本、图片（保留原始链接）和表格。
- **数据完整性**：强调不丢失关键信息，尤其是复杂的表格和嵌入的代码块。

### 2. 下载图片并处理资源
- **目录**：确保 `xknowledge/resource/` 目录存在。
- **下载**：提取网页中的所有图片 URL，并将其下载到 `xknowledge/resource/` 文件夹中。
- **重命名**：为避免冲突，建议使用图片原始文件名的哈希值或文章标题加序号进行重命名。

### 3. 转换为 Markdown
将子代理返回的内容格式化为标准的 Markdown：
- 使用 H1 作为文章标题。
- 使用 H2/H3 区分章节。
- 表格使用标准的 Markdown 表格语法。
- **本地化图片引用**：将 Markdown 中的图片链接替换为指向 `resource/` 文件夹的本地路径，格式为 `![描述](resource/文件名)`。

### 4. 持久化存储
- **目录**：确保文件保存至 `/Users/hzliuxuan/Documents/qoder-workspace/cn-crm/xknowledge/`。
- **文件名**：使用提取的文章标题作为文件名（过滤掉非法字符），后缀为 `.md`。
- **检查**：如果目录不存在，应先创建目录。

## 示例

**用户请求**：
"帮我抓取 https://example.com/article1 的内容并保存到 xknowledge"

**执行逻辑**：
1. 调用 `browser` 抓取 `https://example.com/article1`，提取内容和图片 URL。
2. 创建 `xknowledge/resource/` 目录。
3. 将图片下载至 `xknowledge/resource/`。
4. 提取标题 "Example Article"。
5. 格式化内容，并将图片链接替换为 `resource/xxx.png`。
6. 写入文件：`xknowledge/Example Article.md`。

## 参考模板
查看 [references/template.md](references/template.md) 了解输出的 Markdown 推荐结构。
