"""CLI cron 命令 — 定时任务管理。

用法：
- x-agent cron list                         → 列出所有定时任务
- x-agent cron create                       → 交互式创建（逐步提示输入各参数）
- x-agent cron create -n "每日备份" \
    -s "0 2 * * *" \
    -f "workspace:backup.py:run" \
    -d "每天凌晨2点执行备份" -y             → 非交互式创建（-y 跳过所有确认）
- x-agent cron run <task_id>                → 立即执行任务
- x-agent cron pause <task_id>              → 暂停任务
- x-agent cron resume <task_id>             → 恢复任务
- x-agent cron delete <task_id>             → 删除任务
- x-agent cron history                      → 查看执行历史
- x-agent cron info <task_id>               → 查看任务详情

create 参数说明：
  --name/-n      必填  任务名称（也用于生成任务ID）
  --schedule/-s  必填  定时表达式：cron 格式 '0 2 * * *' 或间隔格式 '30m'/'1h'/'2d'
  --func/-f      必填  函数路径：'workspace:backup.py:run' / '/abs/path.py:main'
  --desc/-d      可选  任务描述。-d "xxx" 直接使用；-y 模式未传则默认为空；交互模式会提示输入（可留空）
  --yes/-y       可选  跳过所有交互确认，直接创建。需同时提供 -n、-s、-f
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from ..config import CLIConfig

cron_app = typer.Typer()
console = Console()


def _derive_task_id(name: str) -> str:
    """根据任务名称自动生成 task_id。"""
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKC", name)
    task_id = re.sub(r"[^\w\u4e00-\u9fff]", "_", normalized, flags=re.UNICODE)
    task_id = task_id.lower()
    task_id = re.sub(r"_+", "_", task_id)
    task_id = task_id.strip("_")
    return task_id or "task"


def _parse_schedule(schedule: str) -> tuple[str, dict[str, Any]]:
    """解析 schedule 表达式，返回 (trigger_type, trigger_args)。

    APScheduler 4.0 CronTrigger 接受的字段: minute, hour, day, month, day_of_week
    """
    schedule = schedule.strip()

    # Cron 表达式检测: 包含空格且有5个部分 (分 时 日 月 周)
    parts = schedule.split()
    if len(parts) == 5:
        cron_fields = {
            "minute": parts[0],
            "hour": parts[1],
            "day": parts[2],
            "month": parts[3],
            "day_of_week": parts[4],
        }
        # 省略默认值 '*' 的字段，让 APScheduler 使用默认值
        filtered = {k: v for k, v in cron_fields.items() if v != "*"}
        return "cron", filtered

    # 间隔表达式检测: 如 "30m", "1h", "2d"
    if len(schedule) >= 2 and schedule[-1] in ["m", "h", "d", "s"]:
        try:
            value = int(schedule[:-1])
        except ValueError:
            raise ValueError(f"无法解析间隔值: {schedule}")
        unit = schedule[-1]
        if unit == "s":
            return "interval", {"seconds": value}
        elif unit == "m":
            return "interval", {"minutes": value}
        elif unit == "h":
            return "interval", {"hours": value}
        elif unit == "d":
            return "interval", {"days": value}

    raise ValueError(
        f"无法识别的定时表达式: '{schedule}'\n"
        "支持格式: '0 2 * * *' (cron) 或 '30m'/'1h'/'2d' (间隔)"
    )


@cron_app.command("list")
def cron_list(
    enabled_only: bool = typer.Option(False, "--enabled", "-e", help="仅显示启用的任务"),
    limit: int = typer.Option(50, "--limit", "-l", help="最大返回数量", min=1, max=500),
) -> None:
    """列出所有定时任务。"""
    asyncio.run(_list_tasks(enabled_only=enabled_only, limit=limit))


async def _list_tasks(enabled_only: bool, limit: int) -> None:
    """从 Backend 获取定时任务列表。"""
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            headers = {"X-Admin-Token": config.admin_token}
            response = await client.get(
                "/api/v1/cron/schedules",
                headers=headers,
                timeout=config.timeout,
            )

            if response.status_code == 401:
                console.print("[red]认证失败：admin token 无效[/red]")
                return

            if response.status_code != 200:
                console.print(f"[red]获取任务列表失败: {response.status_code}[/red]")
                console.print(f"[dim]{response.text}[/dim]")
                return

            result = response.json()

            # API 返回的是列表格式
            if isinstance(result, list):
                tasks = result
            else:
                tasks = result.get("tasks", []) if isinstance(result, dict) else []

            if not tasks:
                console.print("[yellow]暂无定时任务[/yellow]")
                return

            table = Table(
                title=f"定时任务列表 (共 {len(tasks)} 个)",
                show_header=True,
                box=box.ROUNDED,
            )
            table.add_column("任务ID", style="cyan", max_width=30)
            table.add_column("名称", style="green")
            table.add_column("触发器", style="yellow")
            table.add_column("状态", style="magenta")
            table.add_column("下次执行", style="blue")

            for task in tasks:
                task_id = task.get("id", task.get("schedule_id", ""))
                metadata = task.get("metadata", {})
                task_name = metadata.get("task_name", task.get("name", task_id))

                trigger_info = task.get("trigger", {})
                trigger_type = trigger_info.get("type", "unknown")
                trigger_args = trigger_info.get("args", {})

                # 优先从 metadata 中读取原始 schedule 表达式
                schedule_expr = metadata.get("schedule_expression", "")
                if schedule_expr:
                    trigger_desc = schedule_expr
                elif trigger_type == "cron":
                    minute = trigger_args.get("minute", "*")
                    hour = trigger_args.get("hour", "*")
                    day = trigger_args.get("day", "*")
                    month = trigger_args.get("month", "*")
                    day_of_week = trigger_args.get("day_of_week", "*")
                    trigger_desc = f"{minute} {hour} {day} {month} {day_of_week}"
                elif trigger_type == "interval":
                    if "days" in trigger_args:
                        trigger_desc = f"每{trigger_args['days']}天"
                    elif "hours" in trigger_args:
                        trigger_desc = f"每{trigger_args['hours']}小时"
                    elif "minutes" in trigger_args:
                        trigger_desc = f"每{trigger_args['minutes']}分钟"
                    elif "seconds" in trigger_args:
                        trigger_desc = f"每{trigger_args['seconds']}秒"
                    else:
                        trigger_desc = str(trigger_args)
                else:
                    trigger_desc = f"{trigger_type}: {trigger_args}"

                paused = task.get("paused", False)
                enabled = task.get("enabled", True)
                if paused:
                    status = "[yellow]⏸ 暂停[/yellow]"
                elif enabled:
                    status = "[green]▶ 运行中[/green]"
                else:
                    status = "[red]⏹ 禁用[/red]"

                next_run = task.get("next_fire_time", task.get("next_run_time", "N/A"))
                if next_run and next_run != "N/A":
                    try:
                        dt = datetime.fromisoformat(str(next_run).replace("Z", "+00:00"))
                        next_run = dt.strftime("%m-%d %H:%M")
                    except Exception:
                        pass

                table.add_row(task_id[:28], str(task_name)[:20], trigger_desc, status, str(next_run))

            console.print(table)

    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")
        console.print("[dim]请确保后端服务已启动[/dim]")


@cron_app.command("create")
def cron_create(
    name: str = typer.Option(None, "--name", "-n", help="任务名称 (也用于生成任务ID)"),
    schedule: str = typer.Option(None, "--schedule", "-s", help="定时表达式 (如: '0 2 * * *' 或 '30m' 或 '1h')"),
    func: str = typer.Option(None, "--func", "-f", help="函数路径 (如: 'workspace:backup.py:run' 或 '/abs/path/script.py:main')"),
    description: str = typer.Option(None, "--desc", "-d", help="任务描述"),
    enabled: bool = typer.Option(True, "--enabled/--disabled", help="是否立即启用"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认，直接创建"),
) -> None:
    """创建新的定时任务。

    参数行为：
      -d "xxx"        直接使用提供的描述
      -y 但未传 -d    描述默认为空，不弹交互
      交互模式(无 -y)  提示输入描述，可留空

    func 路径支持多种格式：
      workspace:my_task.py:run_task  → workspace 相对路径
      /abs/path/script.py:main       → 绝对路径
      my_task.py:run_task             → 自动在 workspace/jobs/ 下查找
    """
    asyncio.run(_create_task_impl(
        name=name,
        schedule=schedule,
        func_path=func,
        description=description,
        enabled=enabled,
        skip_confirm=yes,
    ))


async def _create_task_impl(
    name: str | None,
    schedule: str | None,
    func_path: str | None,
    description: str | None,
    enabled: bool,
    skip_confirm: bool = False,
) -> None:
    """交互式收集参数并创建定时任务。"""
    if name:
        resolved_name: str = name
    elif skip_confirm:
        console.print("[red]非交互模式下必须提供 --name/-n 参数[/red]")
        return
    else:
        resolved_name = typer.prompt("任务名称")

    if schedule:
        resolved_schedule: str = schedule
    elif skip_confirm:
        console.print("[red]非交互模式下必须提供 --schedule/-s 参数[/red]")
        return
    else:
        console.print("[dim]支持格式:[/dim]")
        console.print("  • Cron表达式: '0 2 * * *' (每天2点)")
        console.print("  • 间隔时间: '30m'(30分钟), '1h'(1小时), '2d'(2天)")
        resolved_schedule = typer.prompt("定时表达式")

    if func_path:
        resolved_func: str = func_path
    elif skip_confirm:
        console.print("[red]非交互模式下必须提供 --func/-f 参数[/red]")
        return
    else:
        console.print("[dim]函数路径格式:[/dim]")
        console.print("  • workspace:my_task.py:run_task  (workspace 相对路径)")
        console.print("  • /abs/path/script.py:main       (绝对路径)")
        console.print("  • my_task.py:run_task             (workspace/jobs/ 下查找)")
        resolved_func = typer.prompt("函数路径")

    if description is not None:
        resolved_description: str = description
    elif skip_confirm:
        resolved_description = ""
    else:
        resolved_description = typer.prompt("任务描述 (可留空)", default="")

    # 解析 schedule
    try:
        trigger_type, trigger_args = _parse_schedule(resolved_schedule)
    except ValueError as parse_error:
        console.print(f"[red]定时表达式解析失败: {parse_error}[/red]")
        return

    # 预览确认
    console.print()
    console.print(Panel(
        f"[bold]任务名称:[/bold] {resolved_name}\n"
        f"[bold]定时规则:[/bold] {resolved_schedule} ({trigger_type})\n"
        f"[bold]函数路径:[/bold] {resolved_func}\n"
        f"[bold]任务描述:[/bold] {resolved_description or '(无)'}\n"
        f"[bold]立即启用:[/bold] {'是' if enabled else '否'}",
        title="即将创建定时任务",
        border_style="cyan",
    ))

    if not skip_confirm:
        confirmed = typer.confirm("确认创建？", default=True)
        if not confirmed:
            console.print("[yellow]已取消[/yellow]")
            return

    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            headers = {"X-Admin-Token": config.admin_token}

            task_id = _derive_task_id(resolved_name)

            # 构建 JobConfig 请求体，字段与后端 JobConfig 模型对齐
            job_config = {
                "id": task_id,
                "func": resolved_func,
                "trigger_type": trigger_type,
                "trigger_args": trigger_args,
                "enabled": enabled,
                "metadata": {
                    "task_name": resolved_name,
                    "task_description": resolved_description,
                    "func_path": resolved_func,
                    "created_by": "cli",
                    "schedule_expression": resolved_schedule,
                    "trigger_type": trigger_type,
                },
            }

            response = await client.post(
                "/api/v1/cron/schedules",
                headers=headers,
                json=job_config,
                timeout=config.timeout,
            )

            if response.status_code == 401:
                console.print("[red]认证失败：admin token 无效[/red]")
                return

            if response.status_code != 200:
                console.print(f"[red]创建任务失败: {response.status_code}[/red]")
                console.print(f"[dim]{response.text}[/dim]")
                return

            result = response.json()
            result_id = result.get("id", result.get("schedule_id", task_id))
            console.print("[green]✓ 定时任务创建成功！[/green]")
            console.print(f"[dim]任务ID: {result_id}[/dim]")
            console.print("[dim]使用 'x-agent cron list' 查看所有任务[/dim]")

    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")


@cron_app.command("run")
def cron_run(
    task_id: str = typer.Argument(help="任务ID"),
) -> None:
    """立即执行指定的定时任务（无视定时规则）。"""
    asyncio.run(_run_task(task_id))


async def _run_task(task_id: str) -> None:
    """立即执行任务。"""
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            headers = {"X-Admin-Token": config.admin_token}
            response = await client.post(
                f"/api/v1/cron/tasks/{task_id}/run",
                headers=headers,
                json={},
                timeout=config.timeout,
            )

            if response.status_code == 401:
                console.print("[red]认证失败：admin token 无效[/red]")
                return

            if response.status_code != 200:
                console.print(f"[red]执行任务失败: {response.status_code}[/red]")
                return

            console.print(f"[green]✓ 任务 {task_id} 已触发执行[/green]")
            console.print("[dim]使用 'x-agent cron history' 查看执行结果[/dim]")

    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")


@cron_app.command("pause")
def cron_pause(
    task_id: str = typer.Argument(help="任务ID"),
) -> None:
    """暂停指定的定时任务。"""
    asyncio.run(_pause_task(task_id))


async def _pause_task(task_id: str) -> None:
    """暂停任务。"""
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            headers = {"X-Admin-Token": config.admin_token}
            response = await client.post(
                f"/api/v1/cron/schedules/{task_id}/pause",
                headers=headers,
                timeout=config.timeout,
            )

            if response.status_code == 401:
                console.print("[red]认证失败：admin token 无效[/red]")
                return

            if response.status_code != 200:
                console.print(f"[red]暂停任务失败: {response.status_code}[/red]")
                return

            console.print(f"[yellow]⏸ 任务 {task_id} 已暂停[/yellow]")

    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")


@cron_app.command("resume")
def cron_resume(
    task_id: str = typer.Argument(help="任务ID"),
) -> None:
    """恢复指定的定时任务。"""
    asyncio.run(_resume_task(task_id))


async def _resume_task(task_id: str) -> None:
    """恢复任务。"""
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            headers = {"X-Admin-Token": config.admin_token}
            response = await client.post(
                f"/api/v1/cron/schedules/{task_id}/resume",
                headers=headers,
                json={"resume_from": "now"},
                timeout=config.timeout,
            )

            if response.status_code == 401:
                console.print("[red]认证失败：admin token 无效[/red]")
                return

            if response.status_code != 200:
                console.print(f"[red]恢复任务失败: {response.status_code}[/red]")
                return

            console.print(f"[green]▶ 任务 {task_id} 已恢复[/green]")

    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")


@cron_app.command("delete")
def cron_delete(
    task_id: str = typer.Argument(help="任务ID"),
    force: bool = typer.Option(False, "--force", "-f", help="强制删除，不确认"),
) -> None:
    """删除指定的定时任务。"""
    asyncio.run(_delete_task(task_id, force))


async def _delete_task(task_id: str, force: bool) -> None:
    """删除任务。"""
    if not force:
        confirmed = typer.confirm(f"确定要删除任务 {task_id}？此操作不可恢复", default=False)
        if not confirmed:
            console.print("[yellow]已取消删除[/yellow]")
            return

    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            headers = {"X-Admin-Token": config.admin_token}
            response = await client.delete(
                f"/api/v1/cron/schedules/{task_id}",
                headers=headers,
                timeout=config.timeout,
            )

            if response.status_code == 401:
                console.print("[red]认证失败：admin token 无效[/red]")
                return

            if response.status_code != 200:
                console.print(f"[red]删除任务失败: {response.status_code}[/red]")
                return

            console.print(f"[green]✓ 任务 {task_id} 已删除[/green]")

    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")


@cron_app.command("history")
def cron_history(
    task_id: str = typer.Option(None, "--task", "-t", help="指定任务ID"),
    limit: int = typer.Option(50, "--limit", "-l", help="最大返回数量", min=1, max=500),
) -> None:
    """查看定时任务的执行历史。"""
    asyncio.run(_get_history(task_id=task_id, limit=limit))


async def _get_history(task_id: str | None, limit: int) -> None:
    """获取执行历史。"""
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            headers = {"X-Admin-Token": config.admin_token}

            response = await client.get(
                "/api/v1/cron/jobs",
                headers=headers,
                timeout=config.timeout,
            )

            if response.status_code == 401:
                console.print("[red]认证失败：admin token 无效[/red]")
                return

            if response.status_code != 200:
                console.print(f"[red]获取历史记录失败: {response.status_code}[/red]")
                return

            result = response.json()

            if isinstance(result, list):
                records = result
            else:
                records = result.get("records", []) if isinstance(result, dict) else []

            if not records:
                console.print("[yellow]暂无执行记录[/yellow]")
                return

            table = Table(
                title=f"执行历史 (共 {len(records)} 条)",
                show_header=True,
                box=box.ROUNDED,
            )
            table.add_column("任务ID", style="cyan", max_width=30)
            table.add_column("执行时间", style="green")
            table.add_column("状态", style="magenta")
            table.add_column("耗时", style="yellow")

            for record in records:
                tid = record.get("task_id", record.get("id", ""))[:28]
                exec_time = record.get("started_at", record.get("execution_time", "N/A"))
                if exec_time and exec_time != "N/A":
                    try:
                        dt = datetime.fromisoformat(str(exec_time).replace("Z", "+00:00"))
                        exec_time = dt.strftime("%m-%d %H:%M:%S")
                    except Exception:
                        exec_time = str(exec_time)[:19]
                else:
                    exec_time = "N/A"

                state = record.get("state", "unknown")
                state_colors = {
                    "completed": "[green]✓ 成功[/green]",
                    "failed": "[red]✗ 失败[/red]",
                    "running": "[blue]⟳ 运行中[/blue]",
                    "cancelled": "[yellow]⊘ 取消[/yellow]",
                    "missed": "[dim]◌ 错过[/dim]",
                }
                state_str = state_colors.get(state, f"[dim]{state}[/dim]")

                duration = record.get("duration_ms", 0)
                duration_str = f"{duration}ms" if duration else "-"

                table.add_row(tid, exec_time, state_str, duration_str)

            console.print(table)

    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")


@cron_app.command("info")
def cron_info(
    task_id: str = typer.Argument(help="任务ID"),
) -> None:
    """查看指定定时任务的详细信息。"""
    asyncio.run(_get_task_info(task_id))


async def _get_task_info(task_id: str) -> None:
    """获取任务详情。"""
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            headers = {"X-Admin-Token": config.admin_token}
            response = await client.get(
                f"/api/v1/cron/schedules/{task_id}",
                headers=headers,
                timeout=config.timeout,
            )

            if response.status_code == 401:
                console.print("[red]认证失败：admin token 无效[/red]")
                return

            if response.status_code != 200:
                console.print(f"[red]获取任务详情失败: {response.status_code}[/red]")
                return

            result = response.json()

            if isinstance(result, dict) and "data" in result:
                task = result.get("data")
            else:
                task = result

            if not task or (isinstance(task, dict) and task.get("success") is False):
                console.print(f"[yellow]任务 {task_id} 未找到[/yellow]")
                return

            metadata = task.get("metadata", {})
            trigger_info = task.get("trigger", {})

            paused = task.get("paused", False)
            enabled = task.get("enabled", True)

            status = "运行中" if enabled and not paused else "已暂停" if paused else "已禁用"
            status_color = "green" if enabled and not paused else "yellow" if paused else "red"

            # 从 metadata 读取原始 schedule 表达式，否则从 trigger args 还原
            schedule_expr = metadata.get("schedule_expression", "")
            if not schedule_expr:
                trigger_type = trigger_info.get("type", "unknown")
                trigger_args = trigger_info.get("args", {})
                if trigger_type == "cron":
                    minute = trigger_args.get("minute", "*")
                    hour = trigger_args.get("hour", "*")
                    day = trigger_args.get("day", "*")
                    month = trigger_args.get("month", "*")
                    day_of_week = trigger_args.get("day_of_week", "*")
                    schedule_expr = f"{minute} {hour} {day} {month} {day_of_week}"
                elif trigger_type == "interval":
                    if "days" in trigger_args:
                        schedule_expr = f"每{trigger_args['days']}天"
                    elif "hours" in trigger_args:
                        schedule_expr = f"每{trigger_args['hours']}小时"
                    elif "minutes" in trigger_args:
                        schedule_expr = f"每{trigger_args['minutes']}分钟"
                    elif "seconds" in trigger_args:
                        schedule_expr = f"每{trigger_args['seconds']}秒"
                    else:
                        schedule_expr = str(trigger_args)
                else:
                    schedule_expr = "N/A"

            console.print(Panel(
                f"[bold]任务ID:[/bold] {task.get('id', task.get('schedule_id', 'N/A'))}\n"
                f"[bold]名称:[/bold] {metadata.get('task_name', task.get('name', 'N/A'))}\n"
                f"[bold]描述:[/bold] {metadata.get('task_description', 'N/A') or '(无)'}\n"
                f"[bold]状态:[/bold] [{status_color}]{status}[/{status_color}]\n"
                f"[bold]定时规则:[/bold] {schedule_expr} ({trigger_info.get('type', 'N/A')})\n"
                f"[bold]下次执行:[/bold] {task.get('next_fire_time', task.get('next_run_time', 'N/A'))}\n"
                f"[bold]执行函数:[/bold] {task.get('func_path', 'N/A')}",
                title="任务详情",
                border_style="cyan",
            ))

    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")
