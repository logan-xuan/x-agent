# 阿里云 OpenSearch Web Search 开发者模式测试指南

## 📋 功能概述

已在开发者模式中集成阿里云 OpenSearch Web Search 测试功能，提供以下能力：

- **可视化调试界面**：前端 React 组件，支持参数配置和结果展示
- **后端 API 端点**：`POST /api/v1/dev/aliyun-web-search`
- **命令行测试脚本**：快速验证功能
- **Token 使用统计**：显示搜索次数和 Token 消耗

## 🚀 使用方法

### 方法一：前端界面测试（推荐）

1. **启动服务**
   ```bash
   # 确保后端服务运行
   cd backend
   uv run uvicorn src.main:app --reload
   
   # 启动前端（新终端）
   cd frontend
   yarn dev
   ```

2. **打开开发者模式窗口**
   - 访问前端应用（通常是 http://localhost:5173）
   - 按 `F12` 或点击开发者工具按钮打开 Dev Mode Window
   - 选择 **"阿里云搜索"** 标签页

3. **配置搜索参数**
   - **搜索查询**：输入要搜索的关键词（必填）
   - **结果数量**：选择返回结果数（3/5/10/15）
   - **内容类型**：选择摘要或完整内容

4. **查看结果**
   - 结构化结果：标题、摘要、URL
   - 原始输出：格式化文本
   - Token 使用情况（如有）

### 方法二：curl 命令测试

```bash
# 基本搜索
curl -X POST "http://localhost:8000/api/v1/dev/aliyun-web-search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "北京今天天气怎么样？",
    "max_results": 5,
    "content_type": "snippet"
  }' | jq .

# 自定义参数
curl -X POST "http://localhost:8000/api/v1/dev/aliyun-web-search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "2026 年人工智能发展趋势",
    "max_results": 3,
    "content_type": "full"
  }' | jq .
```

### 方法三：Python 测试脚本

```bash
# 进入后端目录
cd backend

# 运行测试脚本
uv run python scripts/test_aliyun_web_search.py
```

测试脚本会自动执行多个测试用例并显示详细结果。

## 📊 API 接口文档

### 请求格式

```json
{
  "query": "string (required)",      // 搜索关键词
  "max_results": "number (optional)", // 结果数量，默认 5
  "content_type": "string (optional)" // 内容类型："snippet" 或 "full"
}
```

### 响应格式

```json
{
  "success": "boolean",              // 是否成功
  "query": "string",                 // 原始查询
  "results": [                       // 搜索结果列表
    {
      "title": "string",             // 标题
      "snippet": "string",           // 摘要
      "url": "string"                // URL
    }
  ],
  "output": "string | null",         // 格式化输出
  "error": "string | null",          // 错误信息
  "metadata": "object | null",       // 元数据
  "usage": "object | null"           // Token 使用统计
}
```

### Token 使用统计字段

```json
{
  "search_count": "number",          // 搜索次数
  "rewrite_tokens": "number",        // 重写模型 Token
  "filter_tokens": "number",         // 过滤模型 Token
  "total_tokens": "number"           // 总 Token 数
}
```

## 🔍 测试用例建议

### 基础测试
- 简单查询：`"天气"`
- 具体查询：`"北京今天天气怎么样？"`
- 技术查询：`"Python FastAPI 教程"`

### 压力测试
- 多结果：设置 `max_results=15`
- 复杂查询：`"2026 年人工智能发展趋势及行业应用"`
- 边界测试：空查询、超长查询

### 对比测试
- 同时测试 DuckDuckGo 和阿里云搜索
- 比较结果质量、响应速度、Token 消耗

## ⚠️ 注意事项

1. **环境要求**
   - 确保已配置阿里云 OpenSearch 凭证
   - 检查 `x-agent.yaml` 中的相关配置
   - 需要网络连接以访问阿里云 API

2. **错误处理**
   - 如遇到 SSL 证书错误，请检查环境变量配置
   - 500 错误通常表示阿里云 API 调用失败
   - 超时错误可能需要增加 timeout 参数

3. **性能优化**
   - 建议使用 `snippet` 模式进行快速测试
   - 减少 `max_results` 以降低 Token 消耗
   - 批量测试时注意请求频率限制

## 🛠️ 故障排查

### 常见问题

**Q: 前端看不到"阿里云搜索"标签页？**
A: 清除浏览器缓存，刷新页面；确认前端代码已重新编译

**Q: 搜索返回空结果？**
A: 检查阿里云 API Key 配置；验证网络连接；尝试简单查询

**Q: Token 使用统计不显示？**
A: 某些模式下可能不返回 usage 信息；属正常现象

**Q: CORS 错误？**
A: 确认后端服务已正确配置 CORS；重启后端服务

### 日志查看

```bash
# 查看后端日志
tail -f backend/logs/x-agent.log

# 查看 Prompt 交互日志
tail -f backend/logs/prompt-llm.log
```

## 📝 与其他工具的对比

| 功能 | DuckDuckGo | 阿里云 OpenSearch |
|------|------------|-------------------|
| 数据源 | 通用搜索引擎 | 定制化知识库 |
| 响应速度 | 快 | 中等 |
| Token 消耗 | 无 | 有 |
| 可定制性 | 低 | 高 |
| 适用场景 | 通用搜索 | 专业领域搜索 |

## 🎯 下一步

- ✅ 前端界面测试
- ✅ API 端点验证
- ✅ 命令行脚本测试
- ⏳ 添加更多测试用例
- ⏳ 性能基准测试
- ⏳ 结果质量评估

## 📚 相关文档

- [阿里云 OpenSearch 官方文档](https://help.aliyun.com/product/49320.html)
- [开发者模式使用说明](./DEV_MODE.md)
- [Web Search 工具实现](../../backend/src/tools/aliyun_web_search.py)

---

**创建时间**: 2026-02-18  
**最后更新**: 2026-02-18
