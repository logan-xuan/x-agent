---
name: imagegen
description: "根据用户自然语言描述调用内置生图工具生成图片，并返回可访问地址"
keywords:
  - 生图
  - 画图
  - 生成图片
  - 海报
  - 插画
  - text to image
auto-trigger: true
priority: 1
allowed_tools:
  - generate_image
  - read_file
---

# 文生图指南

## Overview

当用户想要“画一张图”“生成海报”“根据描述出图”时，优先使用 `generate_image`。

## Required Behavior

1. 先将用户描述整理成适合文生图的 prompt。
2. 如果用户没有明确说明尺寸和数量，直接使用工具默认值，不额外追问。
3. 不要自己写脚本访问第三方 API。
4. 只使用 `generate_image` 产出图片。
5. 当 `generate_image` 成功后，最终回复必须直接嵌入第一张图片的 Markdown 图片语法：`![生成图片](url)`。
6. 不要只返回反引号包裹的链接或“访问地址”文本。
7. 如果用户要求图像编辑、局部重绘或图生图，说明当前能力仅支持文生图。
