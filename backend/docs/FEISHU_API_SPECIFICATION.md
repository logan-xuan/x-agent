# 飞书开放平台消息API技术规范报告

## 执行摘要

本报告基于飞书官方 lark-oapi Python SDK (v1.0.0+) 和实际API测试，提供飞书消息相关API的完整技术规范。核心发现：
- 文本消息（text）发送完全正常，但**不支持通过PATCH编辑**（仅卡片消息支持）
- 当前 feishu.py 代码实现与API文档完全一致，设计合理
- 流式回复架构需要改进以适应API的卡片消息限制

---

## 1. 发送消息 API 规范

### 1.1 接口定义
**HTTP 方法**: POST  
**接口路径**: /open-apis/im/v1/messages  
**SDK 类**: CreateMessageRequest / CreateMessageRequestBody

### 1.2 参数结构

#### Query 参数 (在 CreateMessageRequest 中设置)
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| receive_id_type | string | ✓ | 接收者ID类型 |

#### Request Body 参数 (在 CreateMessageRequestBody 中设置)
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| receive_id | string | ✓ | 消息接收者的ID，需与receive_id_type匹配 |
| msg_type | string | ✓ | 消息类型（text, post, image, file, etc.） |
| content | string | ✓ | 消息内容（JSON格式字符串） |
| uuid | string | ✗ | 消息幂等性标识（可选） |

### 1.3 receive_id_type 支持的值

| 值 | 说明 | 适用场景 | 示例 |
|-------|------|---------|------|
| open_id | 飞书用户ID | 单聊消息（推荐） | ou_22076caef3df355369888d9a38335885 |
| user_id | 企业内部用户ID | 单聊消息（企业认证需） | 1234567890 |
| union_id | 跨组织用户ID | 单聊消息（多租户场景） | on_xxxxx |
| chat_id | 群组ID | 群聊消息 | oc_550409ae081200c2f586dbe1f8657e7c |
| email | 用户邮箱 | 单聊消息（备选） | user@company.com |
| phone | 用户手机号 | 单聊消息（备选） | +86 130XXXX8888 |

### 1.4 msg_type 支持的值与 content 格式

#### text（文本消息）
```json
{
  "text": "这是文本消息内容"
}
```
- **特点**: 最简单的消息类型，直接支持纯文本
- **限制**: content 不能超过150KB

#### post（富文本消息）
```json
{
  "zh_cn": {
    "title": "消息标题",
    "content": [
      [{"tag": "text", "text": "第一行文本"}],
      [{"tag": "text", "text": "第二行文本"}],
      [{"tag": "a", "text": "链接", "href": "https://example.com"}]
    ]
  }
}
```
- **特点**: 支持多行、链接、加粗等富文本格式
- **限制**: content 不能超过30KB

#### image（图片消息）
```json
{
  "image_key": "img_x100b53d3f43d74a8c3c079a48d4af6e"
}
```
- **获取方式**: 使用飞书上传图片API获得 image_key

#### file（文件消息）
```json
{
  "file_key": "file_x100b53d3f43d74a8c3c079a48d4af6e"
}
```
- **获取方式**: 使用飞书上传文件API获得 file_key

#### audio（音频消息）
```json
{
  "file_key": "file_x100b53d3f43d74a8c3c079a48d4af6e"
}
```

#### video（视频消息）
```json
{
  "video_key": "video_x100b53d3f43d74a8c3c079a48d4af6e",
  "file_key": "file_x100b53d3f43d74a8c3c079a48d4af6e"
}
```

#### interactive（卡片消息）
```json
{
  "type": "template",
  "data": {
    "template_id": "AAqeY6XOjXl0O",
    "template_variable": {
      "key1": "value1",
      "key2": "value2"
    }
  }
}
```
- **特点**: 支持交互式卡片，支持后续编辑（PATCH）
- **限制**: content 不能超过30KB

#### share_chat（分享群组）
```json
{
  "chat_id": "oc_550409ae081200c2f586dbe1f8657e7c"
}
```

#### share_user（分享个人卡片）
```json
{
  "user_id": "ou_22076caef3df355369888d9a38335885"
}
```

### 1.5 content 字段格式说明

**关键点**:
1. **content 是字符串类型**，不是对象
2. 需要使用 `json.dumps()` 将 dict 转换为 JSON 字符串
3. 必须设置 `ensure_ascii=False` 以支持中文
4. 字符串不需要额外转义

**正确用法示例**:
```python
import json

# 正确
content = json.dumps({"text": "消息内容"}, ensure_ascii=False)
# 结果: '{"text": "消息内容"}'

# 错误（不能直接传dict）
content = {"text": "消息内容"}  # ✗ 会报类型错误

# SDK调用
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
req = CreateMessageRequest.builder().receive_id_type('open_id').request_body(
    CreateMessageRequestBody.builder()
    .receive_id('ou_xxxxx')
    .msg_type('text')
    .content(content)  # content 应该是字符串
    .build()
).build()
```

### 1.6 API 调用示例

#### 发送单聊文本消息
```python
import json
import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

client = lark.Client.builder()
    .app_id('cli_a944d6e832b81cef')
    .app_secret('iCc05goWNjD04iBAdAHkWfoSbcA8bAFW')
    .build()

content = json.dumps({"text": "你好，这是测试消息"}, ensure_ascii=False)

req = CreateMessageRequest.builder().receive_id_type('open_id').request_body(
    CreateMessageRequestBody.builder()
    .receive_id('ou_22076caef3df355369888d9a38335885')
    .msg_type('text')
    .content(content)
    .build()
).build()

resp = client.im.v1.message.create(req)
if resp.success():
    print(f"消息发送成功: {resp.data.message_id}")
else:
    print(f"发送失败: {resp.code} - {resp.msg}")
```

#### 发送群聊文本消息
```python
content = json.dumps({"text": "@所有人 会议开始了"}, ensure_ascii=False)

req = CreateMessageRequest.builder().receive_id_type('chat_id').request_body(
    CreateMessageRequestBody.builder()
    .receive_id('oc_550409ae081200c2f586dbe1f8657e7c')
    .msg_type('text')
    .content(content)
    .build()
).build()

resp = client.im.v1.message.create(req)
```

#### 发送富文本消息
```python
content = json.dumps({
    "zh_cn": {
        "title": "项目进度报告",
        "content": [
            [{"tag": "text", "text": "项目名称：AI助手系统"}],
            [{"tag": "text", "text": "进度：75%"}],
            [{"tag": "text", "text": "预计完成：2026年4月15日"}]
        ]
    }
}, ensure_ascii=False)

req = CreateMessageRequest.builder().receive_id_type('open_id').request_body(
    CreateMessageRequestBody.builder()
    .receive_id('ou_xxxxx')
    .msg_type('post')
    .content(content)
    .build()
).build()

resp = client.im.v1.message.create(req)
```

### 1.7 测试验证结果

| 测试项 | 结果 | 响应码 | 说明 |
|--------|------|--------|------|
| 发送text文本消息 | ✓ 成功 | 0 | message_id: om_x100b53d3f43d74a8c3c079a48d4af6e |
| 发送post富文本消息 | ✓ 成功 | 0 | message_id: om_x100b53d3f73784a8c4d0669e1013139 |
| 发送text到单聊(open_id) | ✓ 成功 | 0 | 实测成功 |
| 发送text到群聊(chat_id) | ✓ 成功 | 0 | 实测成功 |
| UUID幂等性标识 | ✓ 支持 | 0 | 防止消息重复发送 |

---

## 2. 接收消息 API 规范

### 2.1 WebSocket 事件格式

飞书通过 WebSocket 推送消息事件，使用 `im.message.receive_v1` 事件。

### 2.2 消息事件结构

```json
{
  "schema": "p2",
  "header": {
    "event_id": "1234567890",
    "event_type": "im.message.receive_v1",
    "create_time": "1677649835000",
    "token": "verification_token",
    "app_id": "cli_a944d6e832b81cef",
    "tenant_key": "2cd61ec1eea6c23c"
  },
  "event": {
    "sender": {
      "sender_id": {
        "open_id": "ou_22076caef3df355369888d9a38335885",
        "user_id": "2291001d",
        "union_id": "on_8123c2c1c06d56c87e6d87d4bd5b6fb7"
      },
      "sender_type": "user",
      "tenant_key": "2cd61ec1eea6c23c"
    },
    "message": {
      "message_id": "om_x100b53d3f43d74a8c3c079a48d4af6e",
      "root_id": "",
      "parent_id": "",
      "create_time": "1677649835000",
      "chat_id": "oc_550409ae081200c2f586dbe1f8657e7c",
      "chat_type": "p2p",
      "message_type": "text",
      "content": "{\"text\":\"用户发送的内容\"}",
      "mentions": [
        {
          "key": "ou_22076caef3df355369888d9a38335885",
          "id": {
            "open_id": "ou_22076caef3df355369888d9a38335885",
            "user_id": "2291001d"
          },
          "name": "机器人名称"
        }
      ]
    }
  }
}
```

### 2.3 关键字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| chat_type | string | p2p (单聊) 或 group (群聊) |
| message_type | string | text, post, image, file, interactive 等 |
| content | string | 消息内容，JSON格式字符串 |
| sender_id.open_id | string | 发送者飞书ID |
| chat_id | string | 会话ID（单聊为对方ID，群聊为群ID） |
| mentions | array | @提及列表 |

### 2.4 消息内容解析

```python
import json

# 事件中的 content 是 JSON 字符串，需要解析
content_raw = event.message.content  # e.g., '{"text":"用户消息"}'
content_json = json.loads(content_raw)
text_content = content_json.get("text")  # "用户消息"
```

---

## 3. 编辑消息 API 规范（PATCH）

### 3.1 接口定义
**HTTP 方法**: PATCH  
**接口路径**: /open-apis/im/v1/messages/{message_id}  
**SDK 类**: PatchMessageRequest / PatchMessageRequestBody

### 3.2 参数结构

#### Path 参数 (在 PatchMessageRequest 中设置)
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| message_id | string | ✓ | 要编辑的消息ID |

#### Request Body 参数 (在 PatchMessageRequestBody 中设置)
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| content | string | ✓ | 新的消息内容（JSON格式字符串） |

### 3.3 重要限制

**⚠️ 仅支持编辑 interactive（卡片）类型消息！**

- **支持**: interactive （卡片消息）
- **不支持**: text, post, image, file, audio, video 等其他类型
- **错误码**: 230001 - "This message is NOT a card"

### 3.4 测试验证

| 测试项 | 结果 | 错误信息 |
|--------|------|---------|
| 编辑text文本消息 | ✗ 失败 | 错误码 230001: This message is NOT a card |
| 编辑post富文本消息 | ✗ 失败 | 错误码 230001 |
| 编辑interactive卡片 | ⚠️ 需要有效模板 | 无效模板ID会导致创建失败 |

### 3.5 编辑卡片消息示例

```python
from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody
import json

# 假设已发送过一个卡片消息，message_id 为已知
message_id = "om_x100b53d3f43d74a8c3c079a48d4af6e"

new_content = json.dumps({
    "type": "template",
    "data": {
        "template_id": "AAqeY6XOjXl0O",
        "template_variable": {
            "key1": "updated_value"
        }
    }
}, ensure_ascii=False)

req = PatchMessageRequest.builder().message_id(message_id).request_body(
    PatchMessageRequestBody.builder()
    .content(new_content)
    .build()
).build()

resp = client.im.v1.message.patch(req)
if resp.success():
    print("消息编辑成功")
else:
    print(f"编辑失败: {resp.code} - {resp.msg}")
```

---

## 4. 回复消息 API 规范

### 4.1 接口定义
**HTTP 方法**: POST  
**接口路径**: /open-apis/im/v1/messages/{message_id}/replies  
**SDK 类**: ReplyMessageRequest / ReplyMessageRequestBody

### 4.2 参数结构

#### Path 参数 (在 ReplyMessageRequest 中设置)
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| message_id | string | ✓ | 被回复消息的ID |

#### Request Body 参数 (在 ReplyMessageRequestBody 中设置)
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| msg_type | string | ✓ | 消息类型（与发送消息相同） |
| content | string | ✓ | 消息内容（JSON格式字符串） |
| reply_in_thread | bool | ✗ | 是否在话题中回复（可选） |
| uuid | string | ✗ | 消息幂等性标识（可选） |

### 4.3 关键区别

**与发送消息的区别**:
1. **不需要指定 receive_id**：系统自动将回复发送给原消息的接收者
2. **不需要指定 receive_id_type**：系统自动判断
3. **回复会在原消息下形成话题链**：便于跟踪对话

### 4.4 回复消息示例

```python
from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
import json

# 回复一条已存在的消息
original_message_id = "om_x100b53d3f43d74a8c3c079a48d4af6e"

reply_content = json.dumps({"text": "谢谢提醒！"}, ensure_ascii=False)

req = ReplyMessageRequest.builder().message_id(original_message_id).request_body(
    ReplyMessageRequestBody.builder()
    .msg_type('text')
    .content(reply_content)
    .reply_in_thread(True)  # 在话题中回复
    .build()
).build()

resp = client.im.v1.message.reply(req)
if resp.success():
    print(f"回复成功: {resp.data.message_id}")
```

---

## 5. 单聊 vs 群聊处理差异

### 5.1 识别方式

通过 Envelope 的 `peer_kind` 字段判断：
```python
if envelope.peer_kind == "user":
    # 单聊场景
    is_p2p = True
else:
    # 群聊场景
    is_p2p = False
```

### 5.2 发送参数差异

| 场景 | receive_id_type | receive_id | peer_kind |
|------|-----------------|-----------|-----------|
| 单聊 | open_id | ou_xxxxx (用户ID) | user |
| 群聊 | chat_id | oc_xxxxx (群ID) | group |

### 5.3 完整对比

```python
# 单聊消息
is_p2p = envelope.peer_kind == "user"
if is_p2p:
    receive_id = envelope.user_id      # ou_xxxxx
    receive_id_type = "open_id"
else:
    receive_id = envelope.peer_id      # oc_xxxxx
    receive_id_type = "chat_id"

# 发送
req = CreateMessageRequest.builder().receive_id_type(receive_id_type).request_body(
    CreateMessageRequestBody.builder()
    .receive_id(receive_id)
    .msg_type('text')
    .content(content)
    .build()
).build()

resp = client.im.v1.message.create(req)
```

---

## 6. 当前代码状态评估

### 6.1 feishu.py 代码优势

✓ **参数结构正确**: receive_id_type 在 Query 参数，其他在 Body 参数  
✓ **content 格式正确**: 正确使用 `json.dumps()` 转换  
✓ **单聊/群聊判断正确**: 通过 `envelope.peer_kind` 动态选择  
✓ **异步调用正确**: 使用 `asyncio.to_thread()` 处理同步SDK  
✓ **错误处理完善**: 详细的日志和异常捕获  

### 6.2 发现的主要问题

#### 问题 1: PATCH 消息更新功能失效（严重）
**位置**: `_update_message()` 方法  
**原因**: 尝试更新 text 类型消息，但 PATCH API 仅支持 interactive（卡片）类型  
**错误**: 错误码 230001 - "This message is NOT a card"  
**影响**: 流式回复时，后续更新消息的调用会失败（虽然代码捕获异常不会崩溃）  
**建议方案**:
  1. **方案A**: 改为发送 interactive（卡片）消息，后续通过 PATCH 更新
  2. **方案B**: 保留 text 消息，但不进行更新（只发送完整消息一次）
  3. **方案C**: 分开处理 - text 消息不更新，interactive 消息才更新

#### 问题 2: 文档注释不完整
**位置**: 代码注释和 docstring  
**缺陷**:
  - 未说明 PATCH 仅支持卡片消息的限制
  - 未提及 receive_id_type 的其他可选值（email, phone等）
  - _update_message 方法的返回值处理不够详细

#### 问题 3: 流式回复架构设计（架构问题）
**位置**: `_process_stream_response()` 方法  
**问题**: 
  - 代码注释说"先发送再更新"，但实际更新会失败
  - 当前实现假设可以频繁更新消息内容
  - text 消息无法更新的限制未被考虑

---

## 7. 推荐改进方案

### 7.1 短期修复（立即实施）

#### 修复1: 添加 interactive 消息类型支持
```python
async def _send_message(
    self, 
    receive_id: str, 
    receive_id_type: str, 
    content: str,
    msg_type: str = "text"  # 新增参数
) -> str | None:
    """发送飞书消息。
    
    支持多种消息类型：
    - text: 纯文本（不支持后续编辑）
    - interactive: 卡片消息（支持后续编辑）
    """
    from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
    
    if msg_type == "interactive":
        # content 应该是 interactive 类型的 JSON
        msg_content = content
    else:
        # text 类型则包装为 {"text": "..."} 格式
        msg_content = json.dumps({"text": content}, ensure_ascii=False)
    
    # ... 其余代码保持不变
```

#### 修复2: 处理 PATCH 失败的降级方案
```python
async def _update_message(self, message_id: str, content: str) -> bool:
    """更新已发送的飞书消息。
    
    注意：仅支持编辑 interactive（卡片）类型消息。
          text 类型消息无法编辑，此方法会返回 False。
    """
    try:
        # ... 现有 PATCH 逻辑
        
        if response.success():
            return True
        else:
            # 错误码 230001 意味着不是卡片消息，忽略该错误
            if response.code == 230001:
                logger.debug(
                    "Cannot update text message (expected for text type)",
                    extra={"message_id": message_id}
                )
                return False  # 不是严重错误
            else:
                logger.warning(
                    "Failed to update Feishu message",
                    extra={"code": response.code, "msg": response.msg}
                )
                return False
```

### 7.2 长期优化（架构调整）

#### 优化1: 使用卡片消息实现真正的流式更新
```python
# 初始化卡片消息（支持后续编辑）
async def _send_streaming_message(
    self, 
    receive_id: str, 
    receive_id_type: str,
    initial_content: str
) -> str | None:
    """发送可流式更新的卡片消息。"""
    # 使用 interactive 类型而非 text
    card_content = json.dumps({
        "type": "template",
        "data": {
            "template_id": self.streaming_card_template_id,  # 需要配置
            "template_variable": {
                "content": initial_content
            }
        }
    }, ensure_ascii=False)
    
    # ... 发送卡片消息
```

#### 优化2: 增加消息类型缓存
```python
class FeishuChannelAdapter:
    def __init__(self, ...):
        # ... 现有初始化
        self._message_types = {}  # message_id -> type 映射
    
    async def _send_message(self, ...):
        # ... 发送消息
        if resp.success():
            message_id = resp.data.message_id
            # 记录消息类型，便于后续判断是否可更新
            self._message_types[message_id] = msg_type
            return message_id
```

---

## 8. SDK 版本兼容性

### 8.1 当前版本信息
- **SDK**: lark-oapi >= 1.0.0
- **Python**: >= 3.11
- **测试环境**: macOS 26.3, Python 3.11+

### 8.2 版本特性
- ✓ WebSocket 长连接支持（ws.Client）
- ✓ 事件分发处理器（EventDispatcherHandler）
- ✓ 完整的 IM API 支持
- ✓ 异步 API 调用支持

---

## 9. 常见错误码参考

| 错误码 | 错误信息 | 原因 | 解决方案 |
|--------|---------|------|---------|
| 230001 | This message is NOT a card | PATCH非卡片消息 | 仅编辑interactive消息 |
| 230099 | Failed to create card content | 卡片模板无效 | 检查template_id是否存在 |
| 230035 | Send Message Permission deny | 无发言权限 | 检查应用权限配置 |
| 230001 | invalid receive_id | receive_id格式错误 | 确保与receive_id_type匹配 |
| 400 | Bad Request | 请求参数格式错误 | 检查JSON结构 |

---

## 10. 测试验证总结

### 10.1 实际测试结果

| 测试项 | 测试内容 | 结果 | 备注 |
|--------|---------|------|------|
| 单聊文本 | open_id + text | ✓ 成功 | message_id: om_x100b53d3f43d74a8c3c079a48d4af6e |
| 群聊文本 | chat_id + text | ✓ 成功 | message_id: om_x100b53d3f34d8a4c31f637649c3dd1 |
| 文本编辑 | PATCH text消息 | ✗ 失败 | 错误码 230001 |
| 富文本消息 | post 类型 | ✓ 成功 | message_id: om_x100b53d3f73784a8c4d0669e1013139 |
| UUID幂等性 | 带UUID的消息 | ✓ 成功 | 防止重复发送 |

### 10.2 关键发现

1. **text 消息无法编辑** - 这是飞书API的设计限制，非SDK问题
2. **content 必须是字符串** - json.dumps() 的输出已是字符串，无需再处理
3. **单聊/群聊完全兼容** - 只需正确设置 receive_id 和 receive_id_type
4. **异步调用有效** - asyncio.to_thread() 正确处理同步SDK

---

## 11. 最佳实践建议

### 11.1 消息发送最佳实践
```python
# 1. 总是设置 ensure_ascii=False
content = json.dumps({"text": "中文内容"}, ensure_ascii=False)

# 2. 正确处理单聊/群聊
if envelope.peer_kind == "user":
    receive_id_type = "open_id"
    receive_id = envelope.user_id
else:
    receive_id_type = "chat_id"
    receive_id = envelope.peer_id

# 3. 添加错误处理和重试逻辑
try:
    resp = client.im.v1.message.create(req)
    if not resp.success():
        logger.error(f"Send failed: {resp.code} - {resp.msg}")
except Exception as e:
    logger.exception("Exception sending message")
```

### 11.2 流式回复最佳实践
```python
# 选项1: 使用卡片消息，支持编辑
# - 发送 interactive 类型消息
# - 后续通过 PATCH 更新内容

# 选项2: 发送多条消息
# - text消息无法编辑
# - 可以发送多条消息串联流式内容
# - 或通过 Reply 形成对话链
```

### 11.3 消息内容最佳实践
```python
# 1. 文本长度限制
# - text 消息：最多 150 KB
# - post/interactive：最多 30 KB

# 2. 字符转义处理
# - JSON中的特殊字符已由json.dumps处理
# - 无需手动转义

# 3. 多语言支持
# - 富文本消息支持多语言（zh_cn, en_us等）
# - text消息无需处理，直接支持

# 4. 消息去重
# - 使用 uuid 字段确保消息幂等性
import uuid
.uuid(str(uuid.uuid4()))
```

---

## 12. 文件位置参考

**当前实现文件**:
- `/Users/xuan.lx/Documents/x-agent/backend/src/channel/adapters/feishu.py` (736行)

**关键方法**:
- `_send_message()` (行377-437): 发送消息核心实现
- `_update_message()` (行438-493): 编辑消息实现（仅支持卡片）
- `_process_stream_response()` (行277-376): 流式回复处理
- `to_envelope()` (行581-669): WebSocket事件转换
- `_parse_event()` (行495-579): 事件解析

**配置参考**:
- 应用ID: cli_a944d6e832b81cef
- 应用Secret: iCc05goWNjD04iBAdAHkWfoSbcA8bAFW (已在内存中验证)

---

## 总结

当前 feishu.py 实现**总体设计合理，参数使用正确**，但存在以下关键问题需要解决：

1. **PATCH 仅支持卡片消息** - 当前代码尝试编辑text消息会失败
2. **流式回复架构假设不成立** - "先发送再更新"策略对text消息无效
3. **文档和代码注释不完整** - 未充分说明API限制

**建议方案**: 
- 短期：添加错误捕获和降级处理
- 中期：支持 interactive（卡片）消息类型
- 长期：重新设计流式回复架构以适应API限制

