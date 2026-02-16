# X-Agent 对话管理系统（Conversation Management）

## 概述

X-Agent 对话管理系统旨在实现高效的对话管理与上下文压缩，通过多轮压缩抽取关键事实并卸载至长期记忆，解决上下文长度限制和性能问题。系统在达到预设阈值（如100轮）时自动触发分段归档，并保留最近N轮对话加上前段生成的摘要，从而生成包含身份、用户画像和混合检索记忆的综合提示。

## 核心功能

### 1. 多轮对话压缩机制

#### 1.1 关键事实抽取
- 从多轮对话中识别并提取关键信息
- 保留重要决策点、实体关系和状态变更
- 丢弃冗余对话和无关信息

#### 1.2 智能压缩策略
- **摘要压缩**: 将长对话历史压缩为关键摘要
- **滑动窗口**: 仅保留最近N轮对话
- **语义压缩**: 基于语义相似性合并重复内容
- **重要性评分**: 为对话内容分配重要性分数

#### 1.3 压缩触发机制
- **自动触发**: 当对话轮数超过阈值时自动压缩
- **手动触发**: 支持用户主动请求上下文压缩
- **混合触发**: 基于轮数、token数量和语义密度

### 2. 长期记忆管理系统

#### 2.1 关键事实卸载
- 将压缩后的关键事实转移到长期记忆存储
- 维护事实间的语义关系和时间顺序
- 支持增量更新和记忆演化

#### 2.2 记忆分类存储
- **个人偏好记忆**: 用户行为习惯、喜好、倾向
- **任务状态记忆**: 当前任务进展、待办事项
- **知识记忆**: 专业知识、经验积累
- **关系记忆**: 实体间的关系和连接

### 3. 分段归档机制

#### 3.1 阈值触发归档
- 设置对话轮数阈值（如100轮）自动触发归档
- 评估当前上下文token数量，超过限制时触发
- 监控对话主题漂移，显著变化时触发归档

#### 3.2 归档策略
- 生成当前段落的综合摘要
- 将摘要保存至长期记忆
- 清理短期上下文，保留最近N轮对话
- 维护段落间的连续性信息

### 4. 上下文重构机制

#### 4.1 最近对话保留
- 固定保留最近N轮完整对话
- 动态调整保留轮数基于对话复杂性
- 根据话题相关性优先保留重要对话

#### 4.2 前段摘要整合
- 将归档段落的摘要整合到当前上下文中
- 维护摘要与当前对话的语义连贯性
- 支持按需扩展摘要为详细信息

## 混合检索与评分机制

### 1. 混合检索系统

#### 1.1 向量相似度检索
- 使用向量嵌入进行语义相似度匹配
- 在长期记忆中搜索相关上下文
- 支持多模态向量表示

#### 1.2 文本相似度检索
- 基于关键词和短语的传统检索
- 支持模糊匹配和同义词识别
- 结合语法分析进行精确匹配

### 2. 混合评分公式

应用混合评分机制：`final_score = 0.7*vss + 0.3*text`

```python
def calculate_final_score(vss_score: float, text_score: float) -> float:
    """
    计算最终相似度得分
    :param vss_score: 向量语义搜索得分 (0-1)
    :param text_score: 文本匹配得分 (0-1)
    :return: 最终得分 (0-1)
    """
    final_score = 0.7 * vss_score + 0.3 * text_score
    return final_score
```

### 3. 检索优化策略
- **优先级排序**: 基于混合得分对检索结果排序
- **多样性平衡**: 避免检索结果过于集中
- **时效性考虑**: 给予较新记忆更高的权重

## 最终 Prompt 生成

### 1. 多信号融合
最终的 Prompt 包含以下关键组件：

#### 1.1 身份信息
- AI助手的核心角色设定
- 人格特质和交互风格
- 能力边界和限制

#### 1.2 用户画像
- 基于历史对话构建的用户特征
- 个人偏好和行为模式
- 当前会话的上下文

#### 1.3 混合检索记忆
- 从长期记忆中检索的相关信息
- 与当前话题相关的过往经验
- 历史对话中的关键决策点

### 2. Prompt 构造算法

```python
def construct_final_prompt(context_params: dict) -> str:
    """
    构造最终的 Prompt
    :param context_params: 包含所有上下文信息的字典
    :return: 完整的 Prompt 字符串
    """
    prompt_parts = []

    # 添加身份信息
    identity_section = f"你是{context_params['identity']}..."
    prompt_parts.append(identity_section)

    # 添加用户画像
    user_profile = f"用户画像: {context_params['user_profile']}"
    prompt_parts.append(user_profile)

    # 添加检索到的记忆
    retrieved_memory = f"相关记忆: {context_params['retrieved_memory']}"
    prompt_parts.append(retrieved_memory)

    # 添加当前对话历史
    current_context = f"当前对话: {context_params['current_context']}"
    prompt_parts.append(current_context)

    # 添加指令和任务
    instruction = context_params['instruction']
    prompt_parts.append(instruction)

    return "\n".join(prompt_parts)
```

## 系统架构

### 1. 数据流架构
```
用户输入 → 会话管理器 → 上下文压缩器 → 记忆卸载器 → 长期记忆库
                                      ↓
                                检索增强器 → Prompt 生成器 → LLM
                                      ↑
                             混合检索系统 ← 记忆索引器
```

### 2. 核心组件

#### 2.1 会话管理器
- 追踪对话轮数和上下文长度
- 监控压缩阈值并触发相应操作
- 维护对话状态和上下文信息

#### 2.2 上下文压缩器
- 实现多种压缩策略
- 执行关键信息提取
- 生成段落摘要

#### 2.3 记忆管理系统
- 管理长期记忆的存储和检索
- 实现记忆的索引和更新
- 维护记忆的时效性和相关性

## 实现细节

### 1. 阈值配置
```python
class ConversationConfig:
    COMPRESSION_THRESHOLD_ROUNDS = 140  # 对话轮数阈值
    COMPRESSION_THRESHOLD_TOKENS = 2000  # token 数量阈值
    RECENT_RETENTION_COUNT = 20  # 保留最近对话轮数
    MIN_IMPORTANCE_SCORE = 0.3  # 重要性最低分数
    VSS_WEIGHT = 0.7  # 向量相似度权重
    TEXT_WEIGHT = 0.3  # 文本相似度权重
```

### 2. 压缩算法实现

```python
def compress_conversation_history(history: List[Dict], threshold: int = 140) -> Dict:
    """
    压缩对话历史
    :param history: 完整对话历史
    :param threshold: 压缩阈值
    :return: 压缩后的上下文信息
    """
    if len(history) <= threshold:
        return {
            'recent': history[-20:],  # 保留最近20轮
            'summary': '',  # 不需要摘要
            'needs_archiving': False
        }

    # 提取需要归档的历史
    archive_history = history[:-20]  # 除了最近20轮都需要归档

    # 生成摘要
    summary = generate_summary(archive_history)

    # 卸载至长期记忆
    facts = extract_key_facts(archive_history)
    store_to_longterm_memory(facts)

    return {
        'recent': history[-20:],  # 保留最近20轮
        'summary': summary,
        'needs_archiving': True
    }
```

## 性能优化

### 1. 效率优化
- 使用缓存减少重复计算
- 异步处理记忆卸载任务
- 批量处理多个检索请求

### 2. 质量保证
- 压缩后上下文的相关性验证
- 重要信息完整性检查
- 压缩质量监控和反馈机制

### 3. 扩展性考虑
- 支持多种压缩策略的动态切换
- 可配置的阈值和参数
- 插件化的检索算法

## 应用场景

### 1. 长时任务
- 支持需要多轮交互的复杂任务
- 维护任务状态和进展
- 避免上下文溢出

### 2. 个性化交互
- 基于历史记忆提供个性化服务
- 维护用户偏好和习惯
- 增强交互连贯性

### 3. 知识密集任务
- 高效检索相关历史信息
- 整合分散的知识片段
- 提供全面的上下文支持