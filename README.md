<p align="center"><img src="./docs/assets/artemis-banner-cn.png?v=7" alt="ARTEMIS" width="100%" /></p>

# Artemis 中文二次开发版

让 AI 助手通过 MCP 像人一样操作 Android 真机。

> 本仓库是面向中文使用场景的 ARTEMIS 二次开发版本。原始项目架构与 Apache-2.0 许可保持不变；本分支持续完善 Windows 一键部署、中文控制台和无线真机连接体验。

## 核心能力

- **自然语言操控真机**：把测试、巡检或日常任务交给 AI，在 Android 真机上完成操作。
- **Flash / Pro 双模式**：Flash 用于明确、快速的操作；Pro 用于需要规划、校验和诊断的复杂流程。
- **MCP 原生接入**：支持 Codex、Claude Code、Cursor、Windsurf、VS Code、Cline/Roo 等 MCP 工具。
- **Web 控制台**：提供环境体检、模型配置、设备连接、任务执行、投屏和执行记录。
- **安全人工接管**：验证码、短信 OTP、支付密码等敏感步骤会暂停，等待用户处理后继续。

## 本分支增强

- Windows 一键脚本在后台启动 Web 服务；关闭安装窗口后，控制台仍可访问。
- 前端图标字体随应用发布，不依赖 Google Fonts，避免网络受限时图标显示为文字。
- 无线 ADB 成功连接后会保存端点；服务启动时通过 mDNS 主动发现已配对设备。
- 无线断线后约每 **2 秒**检测并重连；Android 11+ 动态端口变化时自动 mDNS 重新发现。
- Flash 模式在当前 UI 元素列表为空时不再复用历史索引，改用 Explorer 或归一化坐标定位。

## 快速开始

### Windows：一键安装（推荐）

下载根目录的 [`install_artemis.bat`](./install_artemis.bat)，双击运行即可。它会自动拉取源码、准备 Python/uv、检测或安装 ADB、FFmpeg、scrcpy、同步依赖、构建前端并打开 `http://localhost:8000`。

已有源码时，在项目根目录执行：

```powershell
.\deploy_windows.bat
```

也可以使用完整菜单：

```powershell
.\install_artemis.bat
```

### macOS / Linux

```bash
git clone https://github.com/yys9253462-gif/artemis.git
cd artemis
./start.sh
```

### 启动与诊断

```powershell
# 启动 Web 控制台
uv run artemis ui

# 检查 Python、模型、ADB、设备和前端状态
uv run artemis doctor

# 重启后台 Web 服务
uv run artemis restart --force
```

## 连接 Android 设备

### USB 调试

1. 在手机开发者选项中开启“USB 调试”。
2. 连接数据线，并在手机上允许调试授权。
3. 执行 `adb devices -l`，确认设备状态为 `device`。

### 无线 ADB 自动恢复

1. 手机与电脑保持在同一局域网。
2. 在开发者选项开启“无线调试”。
3. 在 Web 控制台“Android 设备与真机连接”区域用配对码完成首次配对。
4. 首次成功连接后，服务会在启动和短暂断线后自动恢复连接。

> Android 关闭无线调试、撤销配对、切换到不同局域网或进入飞行模式后，需要重新配对；这是 Android 的系统安全限制。

## 模型配置

首次运行可在 Web 控制台填写模型密钥，也可在项目根目录 `.env` 中配置：

```dotenv
OPENAI_API_KEY=你的密钥
OPENAI_BASE_URL=https://你的兼容接口/v1
```

模型路由位于 [`config/artemis.jsonc`](./config/artemis.jsonc)。配置后执行：

```powershell
uv run artemis doctor
```

出现 `Status: Ready` 即表示环境、模型与设备均已就绪。

## 使用方式

### Web 控制台

打开 `http://localhost:8000`，输入任务目标，选择 Flash 或 Pro 即可执行。

### 命令行

```powershell
uv run artemis run "打开设置，查看电池电量" --profile flash
uv run artemis run "打开设置，检查 Wi-Fi 是否已连接，并报告结果" --profile pro
```

### MCP 接入 IDE

```powershell
uv run artemis mcp --install all
```

安装后可在 AI IDE 中描述真机测试目标；建议同时阅读 [`mcp_server/rules.md`](./mcp_server/rules.md)。

## 常见问题

### 控制台无法打开或持续加载

```powershell
uv run artemis restart --force
uv run artemis doctor
```

然后刷新 `http://localhost:8000`。日志位于 `%LOCALAPPDATA%\Artemis\logs`。

### 无线设备没有自动重连

确认手机仍开启无线调试、与电脑处于同一 Wi-Fi，然后执行：

```powershell
adb devices -l
```

若 Android 已关闭无线调试或配对失效，请在控制台重新配对一次。

## 项目说明

- 二次开发仓库：<https://github.com/yys9253462-gif/artemis>
- 上游项目：<https://github.com/google/artemis>
- 开源许可证：[Apache License 2.0](./LICENSE)

欢迎提交 Issue 和 Pull Request，一起完善中文 Android 自动化体验。
