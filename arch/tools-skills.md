当 Tools / Skills 达到 100–10000 个时，如何

可扩展注册

精准调度

按计划稳定执行

避免 LLM 随机乱选工具

生产系统用的是：

Tool Registry + Skill Registry + Semantic Router + Planner + Execution Controller


一、先明确：Tool vs Skill 的区别（关键）

很多系统失败是因为没区分这两个层级。

Tool（原子能力）

最小执行单元：

HTTP request
Search API
Run SQL
Send email
Execute code

例子：

search_tool.run("OpenAI news")

特点：

原子级

无复杂逻辑

无状态



Skill（组合能力）

Skill 是 Tool 的组合，带执行逻辑：

"Research Company"

包含：

search_tool
browser_tool
summarize_tool

Skill 是：

def research_company(name):
    data = search(name)
    summary = summarize(data)
    return summary

Skill 是：

可复用的能力模块
二、生产级架构：Tool / Skill 扩展架构

                Agent
                 │
                 ▼
          Skill Router Layer
                 │
        ┌────────┴────────┐
        ▼                 ▼
   Skill Registry     Tool Registry
        │                 │
        ▼                 ▼
   Skill Executor     Tool Executor

关键思想：

Agent 不直接选 Tool
Agent 选 Skill
Skill 控制 Tool

这是工业标准。

三、Tool Registry 设计（支持无限扩展）
class Tool:

    def __init__(self, name, description, func, embedding):

        self.name = name
        self.description = description
        self.func = func
        self.embedding = embedding


class ToolRegistry:

    def __init__(self):

        self.tools = {}
        self.embeddings = []

    def register(self, tool):

        self.tools[tool.name] = tool
        self.embeddings.append(tool.embedding)

    def get(self, name):

        return self.tools.get(name)

注册：

tool_registry.register(
    Tool(
        name="search",
        description="Search internet",
        func=search_func,
        embedding=embed("Search internet")
    )
)
四、Skill Registry 设计（核心）

Skill 必须包含：

name
description
steps
tools_used
embedding

实现：

class Skill:

    def __init__(
        self,
        name,
        description,
        steps,
        tools,
        embedding
    ):

        self.name = name
        self.description = description
        self.steps = steps
        self.tools = tools
        self.embedding = embedding

注册：

skill_registry.register(
    Skill(
        name="research_company",
        description="Research company info",
        steps=[
            "search company",
            "extract info",
            "summarize"
        ],
        tools=["search", "browser", "summarizer"],
        embedding=embed("research company info")
    )
)
五、关键核心：如何精准调度 Skill？

生产级系统用：

Embedding Semantic Matching

而不是：

if keyword == ...

流程：

Task
 │
 ▼
Embedding(task)
 │
 ▼
Vector Search
 │
 ▼
Top K Skills
 │
 ▼
LLM Final Selection
 │
 ▼
Execute Skill
六、Skill Router 实现（生产级）
class SkillRouter:

    def __init__(self, skill_registry, embedding_model):

        self.registry = skill_registry
        self.embedding_model = embedding_model

    def route(self, task):

        task_embedding = self.embedding_model.embed(task)

        best_skill = self.vector_search(task_embedding)

        return best_skill

    def vector_search(self, embedding):

        similarities = []

        for skill in self.registry.skills:

            score = cosine_similarity(
                embedding,
                skill.embedding
            )

            similarities.append((score, skill))

        similarities.sort(reverse=True)

        return similarities[0][1]

这是工业标准方法。

七、Planner 如何保证按计划执行？

Planner 输出结构化 Plan：

{
  "steps": [
    {
      "skill": "research_company",
      "input": "OpenAI"
    },
    {
      "skill": "write_report",
      "input": "research result"
    }
  ]
}

执行器严格执行：

for step in plan:

    skill = skill_registry.get(step.skill)

    result = skill.execute(step.input)

不是让 LLM 每一步重新决定。

这是关键。

八、Skill Executor（生产级）
class SkillExecutor:

    def __init__(self, tool_registry):

        self.tools = tool_registry

    def execute(self, skill, input):

        context = input

        for step in skill.steps:

            tool = self.select_tool(step)

            context = tool.run(context)

        return context
九、防止 LLM 乱选工具的关键机制（必须实现）

生产系统使用：

Constrained Tool Selection

不是：

LLM: choose any tool

而是：

LLM: choose from [skill tools only]

实现：

allowed_tools = skill.tools

prompt = f"""
Choose tool from:

{allowed_tools}

Task: {step}
"""

这会极大提升稳定性。

十、当 tools > 1000 时必须用向量数据库

架构：

Tool Embeddings
     │
     ▼
Vector DB (FAISS / Pinecone)
     │
     ▼
Top K tools
     │
     ▼
LLM select

否则 token 会爆炸。

十一、完整生产流程（真实系统）
User Task
   │
   ▼
Planner
   │
   ▼
Plan Steps
   │
   ▼
Skill Router
   │
   ▼
Skill Selected
   │
   ▼
Skill Executor
   │
   ▼
Tool Router
   │
   ▼
Tool Execution
   │
   ▼
Memory Store
十二、现代系统真实架构（OpenAI / Claude / Devin 类似）
Planner Agent
    │
    ▼
Skill Selector (Embedding)
    │
    ▼
Skill Executor
    │
    ▼
Tool Selector (Embedding)
    │
    ▼
Tool Execution
    │
    ▼
Memory
十三、关键优化：Skill 分层（必须）
Level 1: Tool
Level 2: Skill
Level 3: Meta Skill
Level 4: Agent

例子：

Tool:
    search

Skill:
    research_company

Meta Skill:
    market_analysis

Agent:
    business_analyst_agent

这是 Devin 使用的结构。

十四、最终生产级核心组件总结

必须有：

Tool Registry
Skill Registry
Embedding Router
Planner
Execution Controller
Memory
Reflection
Vector DB
十五、最关键原则（工业标准）

永远不要：

让 LLM 从 1000 tools 直接选

必须：

embedding → shortlist → LLM select

两阶段选择：

coarse selection → fine selection
十六、给你一个完整调度流程伪代码（生产级）
task = "Research OpenAI"

plan = planner.create_plan(task)

for step in plan:

    skill = skill_router.route(step)

    result = skill_executor.execute(skill, step.input)

    memory.store(result)
十七、一句话总结（生产级核心）
Embedding Router 决定 Skill
Skill 决定 Tool
Execution Controller 强制执行 Plan
Memory 提供上下文

如果你愿意，我可以进一步给你：

一个完整可运行的 Skill / Tool / Router Python 框架（300 行）

或讲 Devin / OpenAI Agents 如何实现 Skill Graph（真正高级架构）

详细讲解Devin / OpenAI Agents 如何实现 Skill Graph（真正高级架构）

下面我给你完整拆解 Devin / OpenAI Agents 类系统的 Skill Graph 架构。这是当前最先进的 Agent 架构之一，它解决了：

tools 太多无法调度

skills 难以复用

复杂任务无法稳定执行

agent 无法长期规划

Skill Graph 本质是：

从 “列表调度” 升级为 “图调度”

不是：

skills = [skill1, skill2, skill3]

而是：

skills = graph(nodes, edges)
一、什么是 Skill Graph（核心定义）

Skill Graph 是一个：

有向图（Directed Graph）

节点 = Skill
边 = Skill 依赖关系 / 转换关系

结构：

Skill A ───► Skill B ───► Skill C
   │
   ▼
Skill D

每个 Skill 是：

可执行节点

每条边是：

执行路径
二、为什么必须用 Skill Graph？

当 skill 数量超过：

50+

列表结构就会崩溃。

原因：

LLM 无法稳定选择

Skill 组合爆炸

无法复用复杂流程

Skill Graph 解决：

规划问题 → 图搜索问题

而不是：

规划问题 → prompt问题

这是关键跃迁。

三、Devin 的核心架构（真实结构抽象）
                ┌─────────────────┐
                │   Task Goal     │
                └────────┬────────┘
                         ▼
                 Graph Planner
                         │
                         ▼
                  Skill Graph
                         │
        ┌────────────────┼──────────────┐
        ▼                ▼              ▼

  Code Skill       Search Skill    Test Skill
        │                │              │
        ▼                ▼              ▼

    Tool Graph       Tool Graph      Tool Graph

Devin 实际运行的是：

Graph Execution Engine

不是简单 loop。

四、Skill Graph 节点结构（生产级）

每个 Skill Node 包含：

class SkillNode:

    id: str

    description: str

    input_schema: dict

    output_schema: dict

    tools: list

    embedding: vector

    next_skills: list   # edges

    execution_fn: callable

示例：

SkillNode(
    id="write_code",

    description="Write Python code",

    tools=["editor", "linter"],

    next_skills=[
        "run_code",
        "write_test"
    ]
)
五、Skill Graph 示例（真实 coding graph）
          plan_task
              │
     ┌────────┴────────┐
     ▼                 ▼

search_codebase    write_code
     │                 │
     ▼                 ▼

modify_code      write_test
     │                 │
     └─────────┬───────┘
               ▼
            run_test
               │
        ┌──────┴──────┐
        ▼             ▼

     success       debug_code
                       │
                       ▼
                   modify_code

这是一个循环图（支持自修复）。

Devin 核心能力来源于这个。

六、Graph Planner（最关键组件）

Planner 不再输出：

["step1", "step2", "step3"]

而是：

Graph Path

例如：

plan_task
  ↓
search_codebase
  ↓
write_code
  ↓
run_test
  ↓
debug_code
  ↓
run_test

Planner 实际执行：

path = graph.search(goal)
七、Graph Search 如何工作（核心算法）

使用：

Embedding + Heuristic Search

类似：

A*
BFS
DFS
Best First Search

实现：

def find_best_skill(goal):

    goal_embedding = embed(goal)

    best_nodes = vector_db.search(goal_embedding)

    return best_nodes

不是靠 prompt。

八、Execution Engine（真正执行核心）

执行不是：

for step in plan:
    execute(step)

而是：

current_node = start_node

while current_node != goal_node:

    result = execute(current_node)

    next_node = select_next_node(
        current_node,
        result
    )

    current_node = next_node

这是状态机执行。

九、Skill Graph 状态机（关键）
State Machine

state = skill node

transition = edge

execution = node function

示例：

class GraphExecutor:

    def run(self, start_node):

        node = start_node

        while node:

            result = node.execute()

            node = self.select_next(node, result)
十、OpenAI Agents 使用的结构（真实架构抽象）
Agent
 │
 ▼
Task Graph
 │
 ▼
Skill Graph
 │
 ▼
Tool Graph
 │
 ▼
Execution Engine

三层图：

Task Graph
Skill Graph
Tool Graph
十一、为什么 Graph 比 Loop 强 100 倍？

Loop：

A → B → C → fail

Graph：

A → B → C → fail
         ↓
         D → E → success

Graph 支持：

回退
分支
并行
自修复

这是 Devin 能 debug 自己代码的原因。

十二、Memory 如何融入 Graph

Memory 实际是：

Graph Augmentation

Memory 改变 graph 权重：

if skill.success_rate > 0.9:
    increase_priority(skill)

Graph 变成：

Weighted Graph
十三、Tool Graph（Graph 的下一层）

Skill：

write_code

对应 Tool Graph：

open_editor
   ↓
write_file
   ↓
save_file

这是 graph 的 graph。

十四、完整 Devin 架构（简化但真实）
                 User Goal
                     │
                     ▼
               Task Graph Planner
                     │
                     ▼
                 Skill Graph
                     │
                     ▼
                Tool Graph
                     │
                     ▼
              Execution Engine
                     │
                     ▼
                  Memory
                     │
                     ▼
               Graph Update

循环执行。

十五、生产级 Skill Graph 存储方式

使用：

Neo4j
NetworkX
Custom Graph DB

结构：

graph.add_node(skill)
graph.add_edge(skill_a, skill_b)
十六、真实生产级伪代码（接近 Devin）
class SkillGraph:

    def __init__(self):

        self.nodes = {}
        self.edges = {}

    def execute(self, goal):

        current = self.find_start(goal)

        while current:

            result = current.run()

            current = self.select_next(current, result)
十七、Skill Graph vs 传统 Agent（本质区别）

传统 Agent：

LLM 决定每一步

Skill Graph Agent：

Graph 决定路径
LLM 只负责局部决策

稳定性提升巨大。

十八、为什么 Devin 几乎不会“迷路”

因为：

Graph 限制了行动空间

不是无限选择。

类似：

GPS 路网

不是：

随机走
十九、终极架构总结（真正生产级）
                LLM
                 │
                 ▼
           Graph Planner
                 │
                 ▼
           Skill Graph
                 │
                 ▼
           Tool Graph
                 │
                 ▼
         Execution Engine
                 │
                 ▼
               Memory

Graph 是核心，不是 LLM。

二十、一句话总结（最重要）

Skill Graph 本质是：

把 Agent 从 “token预测机器”

升级为

“图搜索 + 状态机执行系统”

如果你愿意，我可以继续给你：

一个完整 Python Skill Graph mini-framework（可运行）

或 Devin 的 self-healing graph（自修复机制）详细实现