# Aliyun OpenSearch Configuration Guide

## 阿里云 OpenSearch 联网搜索配置指南

### 1. 获取 API Key 和服务地址

#### 步骤 1: 登录控制台
访问 [阿里云 AI 搜索开放平台](https://opensearch.console.aliyun.com/)

#### 步骤 2: 创建工作空间
1. 选择地域（推荐：上海或法兰克福）
2. 创建新工作空间（或使用默认的 `default`）

#### 步骤 3: 创建 API Key
1. 导航至 **API Keys** 菜单
2. 点击 "创建 API Key"
3. 保存生成的 API Key（仅显示一次）
4. 记录服务访问地址（公网或 VPC 地址）

### 2. 配置环境变量

在 `.env` 文件或系统环境变量中添加以下配置：

```bash
# Aliyun OpenSearch 配置
ALIYUN_OPENSEARCH_API_KEY=OS-your_api_key_here
ALIYUN_OPENSEARCH_HOST=http://xxxx-hangzhou.opensearch.aliyuncs.com
ALIYUN_OPENSEARCH_WORKSPACE=default
```

### 3. 验证配置

运行以下命令测试配置：

```bash
cd backend
uv run python -c "
import os
from src.tools.builtin import AliyunWebSearchTool
import asyncio

async def test():
    tool = AliyunWebSearchTool()
    result = await tool.execute(query='Python 编程', max_results=3)
    print(result.output)

asyncio.run(test())
"
```

### 4. 使用方式

#### 在对话中自动使用
配置完成后，Agent 会自动根据需求选择合适的搜索工具：
- **DuckDuckGo**: 快速查询、英文内容
- **Baidu Search**: 中文内容、本地信息
- **Aliyun OpenSearch**: 深度研究、高质量结果

#### 手动指定工具
在提示词中明确要求：
```
请使用 aliyan_web_search 搜索最新的人工智能发展趋势
```

### 5. 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| query | String | - | 搜索关键词（必填） |
| max_results | Integer | 5 | 返回结果数量 |
| content_type | String | snippet | `snippet`: 摘要，`full`: 完整内容 |

### 6. 计费说明

- **计费模式**: LCU (Logical Compute Units)
- **Token 消耗**: 
  - 查询重写模型（rewrite_model）
  - 结果过滤模型（filter_model）
- **速率限制**: 10 QPS（可申请提升）

### 7. 常见问题

#### Q: API Key 无效？
A: 检查以下几点：
- API Key 是否正确复制（无多余空格）
- API Key 是否已启用
- 工作空间名称是否匹配

#### Q: 返回结果为空？
A: 尝试：
- 更换搜索关键词
- 增加 `max_results` 数量
- 检查网络连接

#### Q: Token 消耗过高？
A: 优化建议：
- 减少不必要的对话历史
- 使用 `snippet` 而非 `full` 内容
- 合理设置 `top_k` 值

### 8. 最佳实践

1. **查询优化**: 使用具体、明确的关键词
2. **结果筛选**: 根据标题和摘要判断相关性
3. **成本控制**: 监控 Token 使用情况
4. **错误处理**: 实现重试机制应对临时错误

### 9. 支持的服务地域

- **华东 2（上海）**: `ops-shanghai`
- **欧洲中部 1（法兰克福）**: `ops-frankfurt`
- **VPC 跨地域支持**: 杭州、深圳、北京、张家口、青岛

### 10. 相关文档

- [OpenSearch 官方文档](https://help.aliyun.com/zh/open-search/)
- [AI 搜索开放平台](https://help.aliyun.com/zh/open-search/search-platform/)
- [Web 搜索 API 参考](https://help.aliyun.com/zh/open-search/search-platform/developer-reference/web-search)

---

**注意**: 
- API Key 请妥善保管，不要提交到版本控制系统
- 生产环境建议使用 HTTPS 加密传输
- 定期轮换 API Key 以增强安全性
