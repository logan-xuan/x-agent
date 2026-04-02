# 文件组织规范

## 目录结构
```
research-agent/
├── AGENTS.md          # 工作空间规则（本文件）
├── SPIRIT.md          # 价值观与偏好
├── IDENTITY.md        # 身份认知
├── OWNER.md           # 主人信息
├── MEMORY.md          # 长期记忆
├── TOOLS.md           # 工具定义
├── HEARTBEAT.md       # 定时任务配置
├── FILE_ORGANIZATION.md # 本文件
├── memory/            # 每日记忆
│   └── YYYY-MM-DD.md
└── research/          # 调研报告存储
    ├── tech/          # 技术调研
    ├── product/       # 产品调研
    ├── market/        # 市场调研
    └── adhoc/         # 临时调研
```

## 文件命名规范
- 每日记忆: `YYYY-MM-DD.md`
- 调研报告: `YYYY-MM-DD_主题.md`
- 临时笔记: `notes_主题.md`

## 调研报告模板
```markdown
# 调研报告：[主题]

## 调研背景
[为什么要做这个调研]

## 核心发现
[关键结论]

## 详细分析
[正文内容]

## 数据来源
[信息来源列表]

## 建议与结论
[行动建议]
```