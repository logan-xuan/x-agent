# Web Search SSL 证书错误解决方案

## ❌ 错误信息

```
Search Error
Could not complete search. Error: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] 
certificate verify failed: self-signed certificate in certificate chain (_ssl.c:1028)>
```

## 🔍 问题原因

这个错误通常发生在以下场景：

1. **企业网络环境**：公司网络使用自签名证书进行 HTTPS 代理
2. **开发环境**：本地配置了自定义 CA 证书
3. **代理服务器**：使用了中间人代理（如 Charles、Fiddler）
4. **证书链不完整**：DuckDuckGo API 的证书链在你的系统中不被完全信任

## ✅ 解决方案

### 方案 1：推荐 - 保持 SSL 验证（默认）

代码已经更新为使用标准的 SSL 上下文，应该能处理大多数证书验证问题。

**测试方法：**
```bash
cd backend
uv run python -c "
from src.tools.builtin.web_search import WebSearchTool
import asyncio

async def test():
    tool = WebSearchTool()
    result = await tool.execute(query='Python programming', max_results=3)
    print(f'Success: {result.success}')
    if result.output:
        print(result.output[:200])

asyncio.run(test())
"
```

### 方案 2：临时禁用 SSL 验证（仅限开发环境）

⚠️ **警告**：仅在生产环境中不要使用此方法，存在安全风险！

**设置环境变量：**
```bash
# macOS/Linux
export WEB_SEARCH_VERIFY_SSL=false

# Windows PowerShell
$env:WEB_SEARCH_VERIFY_SSL="false"

# Windows CMD
set WEB_SEARCH_VERIFY_SSL=false
```

然后在你的代码中运行搜索。系统会记录警告日志提醒你 SSL 验证已禁用。

### 方案 3：更新系统 CA 证书（推荐用于生产环境）

**macOS:**
```bash
# 使用 Homebrew 安装 certifi
brew install certifi

# 或者更新系统根证书
sudo security find-certificate -a -p /System/Library/Keychains/SystemRootCertificates.keychain >> ~/certificates.pem
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install --reinstall ca-certificates
```

**Linux (CentOS/RHEL):**
```bash
sudo yum reinstall ca-certificates
```

### 方案 4：指定自定义 CA 证书路径

如果你有自定义的 CA 证书文件，可以设置 SSL_CERT_FILE 环境变量：

```bash
export SSL_CERT_FILE=/path/to/your/cacert.pem
```

## 🔧 调试步骤

### 1. 检查网络连接

```bash
# 测试是否能访问 DuckDuckGo
curl -v https://api.duckduckgo.com/?q=test&format=json
```

如果 curl 也报 SSL 错误，说明是系统证书问题。

### 2. 查看证书链

```bash
# 查看 DuckDuckGo 的证书链
openssl s_client -showcerts -connect api.duckduckgo.com:443
```

### 3. 检查 Python 证书路径

```python
import ssl
print(ssl.get_default_verify_paths())
```

确保输出的 `cafile` 或 `capath` 指向有效的证书文件。

### 4. 使用 certifi 包

```bash
# 安装 certifi
pip install certifi

# 在代码中使用
import certifi
import ssl
import urllib.request

ssl_context = ssl.create_default_context(cafile=certifi.where())
```

## 📝 代码修改说明

### 更新内容

1. **添加 SSL 模块导入**
   ```python
   import ssl
   ```

2. **创建 SSL 上下文**
   ```python
   ssl_context = ssl.create_default_context()
   ```

3. **使用 SSL 上下文进行 HTTPS 请求**
   ```python
   with urllib.request.urlopen(request, timeout=10, context=ssl_context) as response:
       data = json.loads(response.read().decode())
   ```

4. **可选的 SSL 验证开关**
   ```python
   verify_ssl = os.getenv('WEB_SEARCH_VERIFY_SSL', 'true').lower() != 'false'
   ```

## 🎯 验证修复

运行单元测试验证所有功能正常：

```bash
cd backend
uv run pytest tests/unit/test_web_search.py::TestDuckDuckGoSearch -v
```

应该看到所有测试通过：
```
✓ test_search_duckduckgo_related_topics
✓ test_search_duckduckgo_abstract
✓ test_search_duckduckgo_fallback
✓ test_search_duckduckgo_timeout
```

## 💡 最佳实践

1. **生产环境**：始终保持 SSL 验证启用
2. **开发环境**：如遇证书问题，可临时禁用但要及时修复
3. **企业网络**：联系 IT 部门获取正确的 CA 证书并安装到系统
4. **定期更新**：保持系统 CA 证书为最新版本

## 📚 相关资源

- [Python SSL 文档](https://docs.python.org/3/library/ssl.html)
- [urllib.request 文档](https://docs.python.org/3/library/urllib.request.html)
- [certifi 包](https://pypi.org/project/certifi/)
- [DuckDuckGo API](https://duckduckgo.com/api)

## 🆘 仍然有问题？

如果以上方法都不能解决问题，请提供：

1. 操作系统版本
2. Python 版本 (`python --version`)
3. 完整的错误堆栈
4. 网络环境描述（是否使用代理、企业网络等）

这样可以更准确地诊断问题。
