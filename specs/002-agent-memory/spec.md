# Feature Specification: AI Agent 记忆系统

**Feature Branch**: `002-agent-memory`  
**Created**: 2026-02-14  
**Status**: Draft  
**Input**: 设计 AI agent 的记忆系统，确保 AI 具备"自我认知"与"记忆演化能力"。参考 arch/memory.md 设计方案。

## Clarifications

### Session 2026-02-14

- Q: 记忆条目如何唯一标识？ → A: UUID 作为唯一标识符，同时增加时间属性（created_at, updated_at）
- Q: 记忆文件损坏时如何恢复？ → A: 从向量存储反向重建损坏的 Markdown 文件
- Q: 向量嵌入如何生成？ → A: 使用本地嵌入模型（如 sentence-transformers），无外部依赖
- Q: 如何识别"重要内容"进行记录？ → A: 混合模式 - AI 自动识别决策/重要内容，用户也可手动标记
- Q: 用户身份信息如何更新？ → A: 混合模式 - 支持交互式对话引导更新，也支持用户直接手动编辑 OWNER.md
- Q: 身份文件变更后如何生效？ → A: 热加载，文件修改保存后自动生效，无需重启系统

## User Scenarios & Testing *(mandatory)*

### User Story 1 - AI 身份初始化 (Priority: P1)

作为用户，我希望在首次启动 AI Agent 时，系统引导我完成身份设定，让 AI 了解我是谁以及它自己的角色定位。

**Why this priority**: 这是记忆系统的基础，没有身份认知，AI 无法提供个性化服务。

**Independent Test**: 可以通过首次启动流程测试，验证 SPIRIT.md 和 OWNER.md 文件是否正确生成。

**Acceptance Scenarios**:

1. **Given** AI Agent 首次启动且无现有记忆文件，**When** 用户启动系统，**Then** 系统发起交互式对话引导用户完成身份初始化
2. **Given** 用户正在完成身份初始化，**When** 用户回答 AI 关于自己的问题，**Then** 系统将用户画像信息持久化存储
3. **Given** 用户正在完成身份初始化，**When** 用户设定 AI 的角色和行为准则，**Then** 系统将 AI 人格设定持久化存储
4. **Given** 身份初始化已完成，**When** 身份文件被修改保存，**Then** 系统热加载更新后的身份信息，无需重启

---

### User Story 2 - 上下文自动加载 (Priority: P1)

作为 AI Agent，我希望在每次响应用户前，自动加载相关上下文信息，确保我的回答连贯且个性化。

**Why this priority**: 上下文加载是实现"记忆"功能的核心，直接影响用户体验。

**Independent Test**: 可以通过发送消息后检查 AI 是否引用了之前的对话或用户偏好来测试。

**Acceptance Scenarios**:

1. **Given** AI Agent 启动，**When** 系统初始化完成，**Then** 按AGENTS.md 引导文件自动按层级加载 SPIRIT.md、OWNER.md、TOOLS.md、最近两日的日志文件
2. **Given** 用户与 AI 进行主会话对话，**When** AI 准备响应，**Then** AI 同时加载长期记忆文件 MEMORY.md
3. **Given** 上下文加载完成，**When** 用户提问，**Then** AI 的回答反映已加载的身份信息和历史上下文

---

### User Story 3 - 每日记忆记录 (Priority: P2)

作为用户，我希望 AI 自动记录每天的重要对话和决策，形成可追溯的日志。

**Why this priority**: 每日日志是记忆演化的基础，但可以在核心身份功能完成后实现。

**Independent Test**: 可以通过检查 memory/ 目录下是否生成当日日志文件来测试。

**Acceptance Scenarios**:

1. **Given** AI Agent 正在运行，**When** 新的一天开始，**Then** 系统自动创建当日日志文件
2. **Given** 用户与 AI 进行对话，**When** 对话产生重要内容，**Then** AI 自动识别决策类内容并记录，用户也可手动标记重要内容
3. **Given** 日志文件存在，**When** 用户或 AI 查询历史，**Then** 可以检索到相关日志内容

---

### User Story 4 - 混合搜索能力 (Priority: P2)

作为 AI Agent，我希望能够通过语义理解快速检索相关记忆，而不仅仅是关键词匹配。

**Why this priority**: 提升记忆检索的准确性和智能性，但不影响基础记忆功能。

**Independent Test**: 可以通过语义相似的查询验证是否能检索到相关记忆。

**Acceptance Scenarios**:

1. **Given** 记忆库中存在多条记录，**When** AI 需要检索相关记忆，**Then** 系统使用混合搜索（向量搜索 + 文本相似度）返回最相关结果
2. **Given** 用户询问与历史对话语义相关的问题，**When** AI 检索记忆，**Then** 返回语义相近的历史记录，即使没有关键词匹配
3. **Given** 搜索结果返回，**When** AI 展示结果，**Then** 结果按混合评分排序（向量得分权重 0.7，文本相似度权重 0.3）

---

### User Story 5 - 记忆双写同步 (Priority: P3)

作为系统管理员，我希望记忆文件变更时自动同步到向量数据库，确保数据一致性。

**Why this priority**: 自动化同步提升系统可靠性，但可以在核心功能稳定后实现。

**Independent Test**: 可以通过修改 .md 文件后检查向量数据库是否同步更新来测试。

**Acceptance Scenarios**:

1. **Given** 用户编辑了记忆文件，**When** 文件保存完成，**Then** 系统自动检测变更并更新向量索引
2. **Given** 向量索引更新失败，**When** 系统检测到错误，**Then** 记录错误日志并重试
3. **Given** 新的记忆文件被创建，**When** 文件监听器检测到新文件，**Then** 自动将其加入向量索引

---

### Edge Cases

- 用户长时间（超过 30 天）未使用系统，旧日志文件如何处理？
- 记忆文件损坏时，系统从向量存储反向重建损坏的 Markdown 文件
- 用户身份信息变更时，支持交互式对话引导更新或直接手动编辑 OWNER.md
- 向量数据库存储空间不足时如何处理？
- 多个 AI Agent 实例同时访问记忆库时如何保证一致性？

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 在首次启动时通过交互式对话引导用户完成身份初始化，生成 SPIRIT.md 和 OWNER.md
- **FR-002**: 系统 MUST 在每次启动时自动加载多级上下文文件（SPIRIT.md、OWNER.md、TOOLS.md、近期日志）
- **FR-003**: 系统 MUST 支持将对话内容记录到每日日志文件（memory/YYYY-MM-DD.md）
- **FR-004**: 系统 MUST 支持长期记忆摘要存储（MEMORY.md）
- **FR-005**: 系统 MUST 提供混合搜索能力，结合向量搜索和文本相似度
- **FR-006**: 系统 MUST 监听记忆文件变更并同步到向量存储
- **FR-007**: AI MUST 在响应用户前完成上下文加载
- **FR-008**: 系统 MUST 支持工具和能力定义文件（TOOLS.md）
- **FR-009**: 系统 MUST 保证 Markdown 文件与向量存储的数据一致性
- **FR-010**: 系统 MUST 提供记忆检索 API 供 AI Agent 调用
- **FR-011**: 系统 MUST 支持身份文件热加载，文件变更后自动生效无需重启

### Key Entities

- **SPIRIT（AI 人格）**: 定义 AI 的角色定位、性格特征、价值观和行为准则，启动时必须加载
- **OWNER（用户画像）**: 定义用户的个人信息、偏好、目标和习惯，支持 AI 提供个性化服务
- **Memory Entry（记忆条目）**: 单条记忆记录，包含 UUID 唯一标识、内容、时间戳（created_at, updated_at）、类型（对话/决策/摘要）和向量嵌入
- **Daily Log（每日日志）**: 按日期组织的记忆集合，记录当天的重要对话和事件
- **Long-term Memory（长期记忆）**: 经过提炼的持久化记忆摘要，跨日期的重要信息
- **Tool Definition（工具定义）**: AI 可使用的工具和能力描述，包含调用方式和参数规范

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 用户首次启动时，身份初始化流程在 5 分钟内完成
- **SC-002**: AI 在每次响应前，上下文加载时间不超过 2 秒
- **SC-003**: 混合搜索返回结果的准确率不低于 85%（用户主观评价）
- **SC-004**: 记忆文件变更后，向量索引同步延迟不超过 3 秒
- **SC-005**: 用户可以追溯到过去 90 天内的任意一次重要对话
- **SC-006**: AI 的回答中体现用户偏好的比例达到 80% 以上（基于用户反馈）
- **SC-007**: 系统支持存储至少 10,000 条记忆记录而不影响检索性能

## Assumptions

- 用户具备基本的文本编辑能力，可以手动修改 Markdown 文件
- 系统运行在本地环境，无需考虑多租户隔离
- 向量数据库使用 sqlite-vss 扩展，无需独立向量数据库服务
- 向量嵌入使用本地模型（如 sentence-transformers）生成，无需外部 API
- 默认保留 90 天的每日日志，超过期限的可归档或压缩
- 用户身份信息可随时手动编辑 OWNER.md 更新
- AI Agent 以单实例运行，暂不考虑分布式场景

## Out of Scope

- 云端同步和多设备，多消息渠道支持
- 记忆内容的自动摘要生成（可作为后续迭代）
- 记忆数据的导入导出功能
