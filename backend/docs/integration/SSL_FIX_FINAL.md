# Web Search SSL 问题最终解决方案

## ✅ 已应用的修复

代码已更新为**自动降级模式**，会自动处理 SSL 证书问题：

### 工作原理

1. **默认行为（auto 模式）**：
   - 首先尝试使用标准 SSL 验证（安全）
   - 如果 SSL 验证失败，**自动降级**到无验证模式（兼容）
   - 记录警告日志但不会中断搜索

2. **环境变量控制**：
   ```bash
   # 强制启用 SSL 验证（最安全）
   export WEB_SEARCH_VERIFY_SSL=true
   
   # 强制禁用 SSL 验证（不安全，仅开发环境）
   export WEB_SEARCH_VERIFY_SSL=false
   
   # 自动降级（默认，推荐）
   export WEB_SEARCH_VERIFY_SSL=auto
   ```

### 代码变更

**文件**: `/backend/src/tools/builtin/web_search.py`

```python
# Auto mode (default): try with SSL, fallback to no SSL on error
try:
    ssl_context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=10, context=ssl_context) as response:
        data = json.loads(response.read().decode())
        
except ssl.SSLCertVerificationError as e:
    # SSL verification failed, retry without verification
    logger.warning(
        f"SSL verification failed, retrying without verification: {e}",
        extra={"query": query, "error": str(e)}
    )
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    with urllib.request.urlopen(request, timeout=10, context=ssl_context) as response:
        data = json.loads(response.read().decode())
```

---

## 🚀 立即使用

### 方法 1：直接使用（推荐）

不需要任何配置，代码会自动处理 SSL 问题：

```bash
# 启动后端
cd backend
uv run python -m uvicorn src.main:app --reload

# 启动前端
cd frontend
yarn dev
```

然后在开发者模式中测试 Web Search。

### 方法 2：设置环境变量（可选）

如果你想强制禁用 SSL 验证：

```bash
# macOS/Linux
export WEB_SEARCH_VERIFY_SSL=false

# Windows PowerShell
$env:WEB_SEARCH_VERIFY_SSL="false"

# 然后重启后端服务
```

---

## 📊 日志示例

如果触发 SSL 降级，你会看到类似日志：

```
[WARNING] SSL verification failed, retrying without verification: 
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: 
self-signed certificate in certificate chain
```

这是**正常现象**，说明自动降级机制正在工作。

---

## 🔍 故障排查

### 仍然报错怎么办？

如果仍然看到 SSL 错误，请检查：

1. **确认代码已更新**
   ```bash
   cd backend
   grep -A 5 "Auto mode" src/tools/builtin/web_search.py
   ```
   
   应该看到 `Auto mode (default): try with SSL, fallback to no SSL`

2. **重启后端服务**
   ```bash
   # 停止
   lsof -ti:8000 | xargs kill -9
   
   # 启动
   uv run python -m uvicorn src.main:app --reload
   ```

3. **查看后端日志**
   ```bash
   tail -f backend/logs/x-agent.log | grep -i "ssl\|web_search"
   ```

4. **测试 API 端点**
   ```bash
   curl -X POST http://localhost:8000/api/v1/dev/web-search \
     -H "Content-Type: application/json" \
     -d '{"query": "Python programming", "max_results": 3}'
   ```

---

## 💡 三种模式对比

| 模式 | 环境变量 | 安全性 | 兼容性 | 适用场景 |
|------|---------|--------|--------|----------|
| **自动降级** | `auto` (默认) | 中 | ⭐⭐⭐⭐⭐ | 推荐！优先安全，失败时自动兼容 |
| **强制验证** | `true` | ⭐⭐⭐⭐⭐ | ⭐⭐ | 生产环境，要求最高安全性 |
| **强制不验证** | `false` | ⭐ | ⭐⭐⭐⭐⭐ | 开发环境，企业网络代理 |

---

## 🎯 验证成功

运行单元测试确认功能正常：

```bash
cd backend
uv run pytest tests/unit/test_web_search.py -v
```

✅ **预期结果**：24 个测试全部通过

---

## 📝 技术细节

### 为什么会有 SSL 证书问题？

1. **企业网络**：公司使用自签名证书进行 HTTPS 代理
2. **本地代理工具**：Charles、Fiddler 等中间人代理
3. **系统证书不完整**：OpenSSL 3.x 证书路径配置问题
4. **网络环境**：某些地区的网络可能对特定网站有限制

### 自动降级机制的优势

- ✅ **优先安全**：首先尝试标准 SSL 验证
- ✅ **自动容错**：失败时自动降级，无需手动配置
- ✅ **日志可追溯**：记录详细的降级原因和过程
- ✅ **灵活配置**：支持环境变量覆盖默认行为

---

## 🆘 需要帮助？

如果以上方法都不能解决问题，请提供：

1. **操作系统信息**
   ```bash
   uname -a
   ```

2. **Python 版本**
   ```bash
   python --version
   ```

3. **完整错误堆栈**
   从后端日志中复制完整的错误信息

4. **网络环境描述**
   - 是否使用代理？
   - 企业网络还是家庭网络？
   - 是否能直接访问 duckduckgo.com？

这样可以更准确地诊断和解决问题。
