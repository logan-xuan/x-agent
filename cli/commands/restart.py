"""CLI restart 命令 — 重启服务。

用法：
- x-agent restart           → 重启所有服务（后端 + 前端）
- x-agent restart backend   → 仅重启后端服务
- x-agent restart frontend  → 仅重启前端服务
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

restart_app = typer.Typer()
console = Console()


def _find_restart_script() -> Path | None:
    """查找 restart.sh 脚本位置。
    
    按优先级查找：
    1. 当前目录
    2. 上级目录
    3. CLI 模块的上级目录
    """
    possible_paths = [
        Path("restart.sh"),
        Path("../restart.sh"),
        Path(__file__).parent.parent.parent / "restart.sh",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    return None


@restart_app.callback(invoke_without_command=True)
def restart(
    backend_only: bool = typer.Option(False, "--backend", "-b", help="仅重启后端服务"),
    frontend_only: bool = typer.Option(False, "--frontend", "-f", help="仅重启前端服务"),
) -> None:
    """重启 X-Agent 服务。
    
    默认重启所有服务（后端 + 前端）。
    使用 --backend 仅重启后端，--frontend 仅重启前端。
    """
    restart_script = _find_restart_script()
    
    if not restart_script:
        console.print("[red]❌ 找不到 restart.sh 脚本[/red]")
        console.print("[dim]请确保在 X-Agent 项目根目录下运行此命令[/dim]")
        sys.exit(1)
    
    console.print(f"[bold]🔄 重启脚本位置:[/bold] {restart_script}")
    console.print()
    
    if backend_only:
        _restart_backend()
    elif frontend_only:
        _restart_frontend()
    else:
        _restart_all()


def _restart_all() -> None:
    """重启所有服务。"""
    restart_script = _find_restart_script()
    if not restart_script:
        return
    
    console.print("[bold]🔄 正在重启所有服务（后端 + 前端）...[/bold]")
    console.print()
    
    try:
        # 使用 bash 执行 restart.sh 脚本
        result = subprocess.run(
            ["bash", str(restart_script)],
            cwd=restart_script.parent,
            capture_output=False,
            text=True,
        )
        
        if result.returncode == 0:
            console.print()
            console.print("[bold green]✅ 所有服务重启成功！[/bold green]")
        else:
            console.print()
            console.print(f"[red]❌ 重启失败，退出码: {result.returncode}[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]❌ 重启过程中出错: {e}[/red]")
        sys.exit(1)


def _restart_backend() -> None:
    """仅重启后端服务。"""
    restart_script = _find_restart_script()
    if not restart_script:
        return
    
    backend_script = restart_script.parent / "start-backend.sh"
    
    if not backend_script.exists():
        console.print("[red]❌ 找不到 start-backend.sh 脚本[/red]")
        sys.exit(1)
    
    console.print("[bold]🔄 正在重启后端服务...[/bold]")
    console.print()
    
    try:
        # 停止现有后端进程
        console.print("[yellow]🛑 停止现有后端进程...[/yellow]")
        subprocess.run(
            ["pkill", "-f", "python.*src.main"],
            capture_output=True,
        )
        
        import time
        time.sleep(2)
        
        # 启动后端服务
        result = subprocess.run(
            ["bash", str(backend_script)],
            cwd=backend_script.parent,
            capture_output=False,
            text=True,
        )
        
        if result.returncode == 0:
            console.print()
            console.print("[bold green]✅ 后端服务重启成功！[/bold green]")
        else:
            console.print()
            console.print(f"[red]❌ 后端服务重启失败，退出码: {result.returncode}[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]❌ 重启过程中出错: {e}[/red]")
        sys.exit(1)


def _restart_frontend() -> None:
    """仅重启前端服务。"""
    restart_script = _find_restart_script()
    if not restart_script:
        return
    
    frontend_script = restart_script.parent / "start-frontend.sh"
    
    if not frontend_script.exists():
        console.print("[red]❌ 找不到 start-frontend.sh 脚本[/red]")
        sys.exit(1)
    
    console.print("[bold]🔄 正在重启前端服务...[/bold]")
    console.print()
    
    try:
        # 停止现有前端进程
        console.print("[yellow]🛑 停止现有前端进程...[/yellow]")
        subprocess.run(
            ["pkill", "-f", "vite"],
            capture_output=True,
        )
        subprocess.run(
            ["pkill", "-f", "npm.*dev"],
            capture_output=True,
        )
        
        import time
        time.sleep(2)
        
        # 启动前端服务
        result = subprocess.run(
            ["bash", str(frontend_script)],
            cwd=frontend_script.parent,
            capture_output=False,
            text=True,
        )
        
        if result.returncode == 0:
            console.print()
            console.print("[bold green]✅ 前端服务重启成功！[/bold green]")
        else:
            console.print()
            console.print(f"[red]❌ 前端服务重启失败，退出码: {result.returncode}[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]❌ 重启过程中出错: {e}[/red]")
        sys.exit(1)
