# CLI 安装方式调查

调查日期：2026-10-23。仅查阅项目维护者的文档、README 和安装脚本；未运行任何安装或构建命令。以下示例属于对应项目，不是 codex-custom 已提供的安装入口。

## 同类项目怎么做

| 项目 | 官方终端安装入口 | 命令背后的工作 |
| --- | --- | --- |
| tweakcc（Claude Code 定制工具） | `npx tweakcc`；也可 `npm install -g tweakcc` | 获取并运行 npm 包，修改已有 Claude Code 安装。npm 安装直接修改 JavaScript；native 安装提取嵌入代码、修改后重新封装。不是让用户编译整个 Claude Code。见 [官方 README](https://github.com/Piebald-AI/tweakcc#how-it-works)及[安装方式](https://github.com/Piebald-AI/tweakcc#building-from-source)。 |
| OpenCode 1 | `curl -fsSL https://opencode.ai/install \| bash`；也支持 npm、维护者 Homebrew tap | 安装脚本识别系统和 CPU，下载 GitHub Releases 对应压缩包，解压并安装已编译的 `opencode`；不在用户机器上编译整个项目。见[官方安装文档](https://opencode.ai/docs/#install)及[实际 v1 安装脚本](https://github.com/anomalyco/opencode/blob/v1/install)。 |
| Aider | `curl -LsSf https://aider.chat/install.sh \| sh`；已有 uv 可用 `uv tool install --force --python python3.12 --with pip aider-chat@latest` | 用 uv 在隔离环境安装 Python 包及依赖，必要时安装 Python 3.12。不是分发一个独立原生可执行文件，也不是要求用户编译整套 Rust CLI。依赖是否需要本地构建仍取决于平台与可用包。见[官方安装文档](https://aider.chat/docs/install.html)及[维护者对安装器机制的说明](https://aider.chat/2025/01/15/uv.html)。 |

OpenCode 当前区分 v1 与 v2。上表使用稳定 v1 文档与 `https://opencode.ai/install` 实际指向的 `v1/install`，避免把开发分支的 v2 安装机制混入比较。

## 对 codex-custom 的含义

**可以提供终端指令安装。** “输入一条命令”和“用户无需编译”是两个独立设计决定；`curl`、npm 或 Homebrew 只是入口，不能自动消除构建工作。

按[本项目当前实现](../README.md#本地使用)，入口脚本会获取匹配官方版本的上游源码，应用补丁并本地构建 Rust release 程序。因此可以增加下载源码、检查依赖、安装启动入口的一条命令，但其他用户首次使用仍需要编译。当前 `python3 scripts/install.py` 已能安装命令入口，不过要求先取得源码并保留目录，尚不是公开的一条命令下载安装器。

若目标是“输入一条命令、下载后直接运行”，需要我们提前构建相应平台和官方版本的定制程序，再让安装器下载验证。还应保留当前匹配官方包资源和版本的要求，并明确官方升级后是等待新成品、继续本地构建，还是暂时使用官方程序。这属于新的发行工作，不能仅把已有本机安装压缩后直接发出。

技术比较结论：tweakcc 的安装体验值得参考，但其修改嵌入 JavaScript 的方式不能直接套用到当前 Rust 源码补丁；OpenCode 的预编译下载模式更接近免本地编译的目标。以上是依据公开实现与本项目代码作出的判断，尚未实施新的发行方式。

安装器应只分发可审查的源码或经过独立审查的发行产物，不打包维护者已有安装目录、配置、凭据、会话、缓存或日志。安装便利程度不要求公开这些私人材料。
