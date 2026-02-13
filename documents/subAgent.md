
# 需求目标
按需启动：subagent 默认不开启，避免资源浪费  
有main agent 精准投喂：为每个子代理定制最小化 Prompt，提升识别精度、降低 token 消耗
基于显式指令触发 + 职责隔离 + 精准 Prompt 注入到各自的subagent
每个subagent的内部执行流程与main agent一致是一个透明、自循环、可追溯、能意图识别、自规划的 AI Agent 执行系统，但不能再次开启subagent
每个subagent完成任务后汇报给main agent 等待新的规划任务。
