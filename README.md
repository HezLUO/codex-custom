# codex-custom

社区维护的 Codex CLI 前端补丁与本地构建工具。新增 `context-details` 底栏字段，显示与 `/status` 一致的当前上下文 tokens、容量和剩余百分比，例如：

```text
Context 95% left (33.8K used / 475K)
```

当前上下文用量来自官方 `last_token_usage`，使用官方百分比公式；累计会话 token 不作为当前用量。上下文未知或更新尚未完成时，字段按补丁规则隐藏。

这是可审查的本地开源候选版本，与 OpenAI 无隶属或背书关系。项目使用 HezLUO/codex-custom 私有 GitHub 仓库管理任务，源码尚未推送或公开，许可方案尚待审定。已确定的发行目标是通过一条终端命令下载安装经过验证的预编译版本，源码构建保留为可选方式，见[安装方式决定](docs/adr/0001-precompiled-installation.md)。

已实现本地预编译候选安装与离线启动。已实现从精确版本发行源下载；生命周期更新仍待后续任务完成。目前没有公开安装地址。不包含用户数据或旧项目历史。

## 支持范围

- 已有运行验收：macOS Apple Silicon，官方 CLI **0.164.0**，官方 standalone `codex` 包布局 v1。
- 其他平台、npm/Homebrew 等安装方式尚未支持。未来版本会尝试应用同一补丁，但不保证兼容；冲突会停止，需人工移植与验收。
- 本地预编译安装只需要 Python 3.9+、系统 codesign 和匹配官方包；无需 Rust、Cargo、Git 或源码目录。官方包必须位于当前 `CODEX_HOME`（默认 `~/.codex`）的 `packages/standalone/releases` 中。
- 显式开发者源码构建还需要 Git、Xcode Command Line Tools（含 `strip`、`codesign`）、通过 rustup 安装的 `cargo` 和 `rustup`（在 PATH 中），以及下载上游源码和 Rust 依赖的网络。
- 更新器根据匹配版本源码的 `codex-rs/rust-toolchain.toml` 安装工具链。0.164.0 使用 Rust 1.99.1。首次构建为大型 Rust 工作区的优化构建，预留数十 GB 空间和较长编译时间；具体开销随机器、缓存而异，尚无全新环境基准。

## 一条命令下载安装

以下地址是发布后的命令格式；仓库仍为私有、源码与发行尚未上传，因此目前不能从该公开地址安装：

```sh
curl -fsSL https://raw.githubusercontent.com/HezLUO/codex-custom/main/bootstrap.sh | sh
```

要求 Python 3.9+、macOS Apple Silicon、系统 codesign 与完整匹配的官方 standalone CLI 0.164.0；普通用户无需 Rust、Cargo 或 Git。shell 在下载 Python 引导器前检查 Python 与系统；Python 在下载发行前检查官方包和资源。安装器只选择明确绑定官方版本与平台的 tag，从不盲用 latest。初始 shell/Python 引导器由所选源码地址提供，属于安装信任入口；HTTPS 和同源摘要不等于独立发布者签名，详见[产物格式与验证边界](docs/PRECOMPILED-FORMAT.md)。

在已下载的源码候选中可运行 `python3 scripts/install.py`；它走相同在线下载与统一安装过程。安装成功后运行 `codex-custom --version` 或 `codex-custom`；若命令目录不在 PATH 中，使用完整入口路径。未知发行、网络中断、错误摘要或签名均停止并保留原有效安装，使用官方 `codex` 恢复工作。没有隐式源码构建。

本地测试服务使用同一入口：

```sh
curl -fsSL http://127.0.0.1:PORT/bootstrap.sh | CODEX_CUSTOM_BOOTSTRAP_URL=http://127.0.0.1:PORT/bootstrap.py CODEX_CUSTOM_RELEASE_SOURCE=http://127.0.0.1:PORT sh -s -- --bin-dir "$HOME/.local/candidate-bin"
```

仅 loopback 测试来源允许 HTTP；这条测试命令并不表示 GitHub 上已有可下载的公开发行。

## 本地预编译安装

先准备经过审查、包含运行组件的候选及其 SHA-256；校验信息只证明完整性，ad hoc 签名不认证发布者身份。

```sh
python3 scripts/install.py --archive ../candidate/codex-custom.tar.gz --sha256 EXPECTED_SHA256
# 自定义命令位置；未知已有命令（包括失效链接）会拒绝覆盖
python3 scripts/install.py --archive ../candidate/codex-custom.tar.gz --sha256 EXPECTED_SHA256 --bin-dir "$HOME/.local/custom-bin"
codex-custom --version
codex-custom resume --last
```

预编译入口复制自己的运行组件，可移走 checkout。默认状态目录为 `~/.local/share/codex-custom/precompiled`，可用 `CODEX_CUSTOM_STATE_DIR` 选择全新目录；安装后 shim 固定该目录。拒绝自动接管旧源码安装。校验归档、签名、版本、官方完整资源及逐文件收据后才激活；有效匹配版本可离线启动。默认启动从不隐式编译。官方版本或资源变化时会停止并提示使用官方 `codex`。安全卸载和匹配成品更新由后续生命周期任务提供。

## 显式开发者源码构建方式

以下命令用于当前源码方案，会在首次运行时本地编译；不是计划中的预编译安装入口。

先按官方方式安装并验证 `codex --version`，准备上述依赖，然后在本仓库运行：

```sh
CODEX_CUSTOM_BUILD_FROM_SOURCE=1 ./codex-custom --version
CODEX_CUSTOM_BUILD_FROM_SOURCE=1 ./codex-custom
CODEX_CUSTOM_BUILD_FROM_SOURCE=1 ./codex-custom resume --last
```

首次运行会构建与本机官方版本匹配的前端。它会访问官方配置、登录和会话；不会创建另一套账户。已有可用安装无需迁移。**首次构建会下载源码/依赖并在官方 releases 的独立子目录中生成定制包。**

可选安装启动入口（需保留本源码目录）：

```sh
python3 scripts/install-source.py
# 已存在 codex-custom 时拒绝覆盖；可另选目录并加入 PATH：
python3 scripts/install-source.py --bin-dir "$HOME/.local/codex-custom-candidate-bin"
# 移动源码目录前，使用同一 checkout 和同一 bin-dir 卸载入口再重新安装
python3 scripts/install-source.py --uninstall
```

启动器只传递用户参数，并设置 `CODEX_CUSTOM_STATUS_LINE` 前端偏好；不自动添加 `--no-daemon` 或 `-c tui.status_line=...`，因此遵循官方后台服务选择逻辑。用户主动提供的参数仍可能按官方规则选择 embedded 模式。

```sh
CODEX_CUSTOM_STATUS_LINE='["context-details"]' ./codex-custom
python3 update-codex-custom.py --check  # 就绪返回 0，需要重建返回 2；错误返回 1
python3 update-codex-custom.py          # 构建但不进入交互
python3 update-codex-custom.py --force  # 强制重建
```

## 路径和构建选项

| 环境变量 | 默认值 / 行为 |
| --- | --- |
| `CODEX_OFFICIAL_BIN` | `~/.local/bin/codex`；必须指向完整匹配的官方 standalone 包入口 |
| `CODEX_CUSTOM_STATE_DIR` | `~/.local/share/codex-custom/builds`；日志、构建清单和定制 `current` 链接 |
| `CODEX_CUSTOM_CACHE_DIR` | `~/.cache/codex-custom`；上游 Git 缓存、源码 worktree 和 Cargo target |
| `CARGO_HOME` / `RUSTUP_HOME` | 遵循 rustup/cargo 标准行为；不再依赖旧工作区私有工具链 |
| `CARGO_BUILD_JOBS` | 默认 6，可按内存调整 |
| `CODEX_CUSTOM_STATUS_LINE` | 未设置时使用启动器默认字段；显式设置则原样传递 |

相对自定义目录按启动时工作目录解析，建议使用绝对路径。源码可放在含空格的路径中。从符号链接调用源码启动器时，请使用安装脚本生成的 shim；直接 `ln -s` 不受支持。

为保留官方 standalone 安装身份，完整定制包写入解析后的官方包父目录下 `codex-custom/<唯一构建编号>/package`。它不替换官方程序或官方选择链接。只有主程序被替换，helper、rg、语音资源及元数据逐文件核对保留；对定制主程序执行 strip 和本地 ad-hoc 签名。

## 开发者源码路径的更新、失败与卸载

官方界面的 **Update now / Later** 继续使用官方逻辑；Update now 安装官方新版并提示重启。下次运行本启动器时才按本机已安装版本重建，不另加确认流程。版本、补丁、更新器、包文件和构建清单匹配时直接启动。

补丁、格式、75 项相关 Rust 测试、release 编译、版本/帮助及签名检查全部通过，且官方版本未在构建中改变后，才原子切换定制 `current`。失败保留上次生效版本并停止本次启动；直接运行官方 `codex` 恢复工作。失败可能留下未激活的构建目录和日志，不自动删除以便诊断。

卸载脚本只删除本 checkout 生成的启动入口，拒绝删除其他入口。确认没有构建或运行进程后，可手动清理自己配置的 state/cache 目录；完整包需按各构建的 `package` 链接核实后逐个删除。不要整体删除共享 `releases/codex-custom`：其中可能含旧安装的有效包。不要删除官方包、官方 current、后台服务、配置、登录或会话。

## 验证和维护

```sh
python3 -m unittest discover -s tests -v
sh -n codex-custom
python3 scripts/audit-release.py
```

本次迁移验证、历史测试限制与真实新版升级计划见 [验证记录](docs/VALIDATION.md)。补丁边界与维护流程见 [维护说明](docs/MAINTENANCE.md)。公开内容及隐私审计边界见 [开源审查清单](docs/RELEASE.md)。不承诺所有命令或未来版本与官方绝对等价。

## 许可与归属

候选项目采用 Apache-2.0，见 [LICENSE](LICENSE)。补丁包含来自 OpenAI Codex 的上下文，保留上游 [NOTICE](NOTICE)；修改说明见 [维护说明](docs/MAINTENANCE.md)。上游源码为 [openai/codex](https://github.com/openai/codex)，基线 tag 为 `rust-v0.164.0`。许可证及通知保留方案依据 [Apache-2.0 第 4 节](https://www.apache.org/licenses/LICENSE-2.0)。计划中的预编译发行还需完成实际产物、依赖、资源许可和再分发通知审查；当前源码审计不代表该发行审查已完成。
