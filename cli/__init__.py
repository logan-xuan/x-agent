"""X-Agent CLI.

命令行交互端，支持两种运行模式：
- Remote 模式：通过 HTTP/SSE 连接已运行的 Backend
- Embedded 模式：直接 import Gateway 模块，进程内调用
"""
