# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""ARTEMIS Unified Command Line Interface (CLI)."""

from typing import Annotated

from artemis._version import __version__
from artemis.interfaces.cli.commands.batch import batch_command
from artemis.interfaces.cli.commands.doctor import doctor_command
from artemis.interfaces.cli.commands.helper import helper_app
from artemis.interfaces.cli.commands.init import init_command
from artemis.interfaces.cli.commands.mcp import mcp_command
from artemis.interfaces.cli.commands.run import run_command
from artemis.interfaces.cli.commands.server import server_app
from artemis.interfaces.cli.commands.server_lifecycle import (
    restart_command,
    status_command,
    stop_command,
)
from artemis.interfaces.cli.commands.trace import trace_app
from artemis.interfaces.cli.commands.ui import ui_command
from artemis.utils.logger import get_logger
from rich.console import Console
from rich.panel import Panel
import typer

logger = get_logger(__name__)

app = typer.Typer(
    name="artemis",
    help="☕ Artemis：下一代自主式多模态 Android 智能体与自动化测试框架。",
    add_completion=False,
    pretty_exceptions_enable=False,
    no_args_is_help=True,
)

# Register subcommands
app.command(name="ui", help="在浏览器中启动 Artemis 交互控制台与 Web 调试面板。")(
    ui_command
)
app.command(name="restart", help="重启正在运行的 Artemis Web 服务。")(restart_command)
app.command(name="stop", help="停止运行中的 Artemis Web 服务。")(stop_command)
app.command(name="status", help="查看 Artemis Web 服务当前运行状态。")(status_command)
app.command(name="run", help="在目标移动设备上执行自主自动化任务。")(run_command)
app.command(name="init", help="交互式初始化向导：配置大模型 API 密钥与设备连接。")(
    init_command
)
app.command(name="doctor", help="系统体检：检查运行环境依赖、ADB 连接与配置状态。")(
    doctor_command
)
app.command(name="batch", help="批量执行多个自动化任务工作流。")(batch_command)
app.command(name="mcp", help="启动 Artemis 原生 Model Context Protocol (MCP) 服务。")(mcp_command)
app.add_typer(server_app, name="server", help="服务端代理与云控 Web 仪表盘服务。")
app.add_typer(trace_app, name="trace", help="检查与分析任务执行轨迹 (Traces)。")
app.add_typer(
    helper_app, name="helper", help="管理已连接真机上的轻量无障碍辅助插件 (Accessibility Helper)。"
)


def version_callback(value: bool):
    if value:
        console = Console()
        console.print(
            Panel(
                f"[bold cyan]Artemis 移动智能体平台[/bold cyan] v{__version__}\n"
                "[dim]自主多模态移动端 AI 执行引擎[/dim]",
                title="☕ Artemis",
                expand=False,
            )
        )
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="显示 Artemis 版本号并退出。",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
):
    """ARTEMIS 自主移动端智能体命令行系统。"""
    pass


def cli():
    """Main CLI entrypoint."""
    app()


if __name__ == "__main__":
    cli()
