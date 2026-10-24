# codex-custom

社区维护的 Codex CLI 前端补丁与预编译安装工具。新增 `context-details` 底栏字段，显示与 `/status` 一致的当前上下文 tokens、容量和剩余百分比，例如：

```text
Context 95% left (33.8K used / 475K)
```

当前上下文用量来自官方 `last_token_usage`，使用官方百分比公式；累计会话 token 不作为当前用量。上下文未知或更新尚未完成时，字段按补丁规则隐藏。

这是可审查的本地开源候选版本，与 OpenAI 无隶属或背书关系。项目使用 HezLUO/codex-custom 私有 GitHub 仓库管理任务，源码尚未推送或公开，许可方案尚待审定。已确定的发行目标是通过一条终端命令下载安装经过验证的预编译版本，源码构建保留为可选方式，见[安装方式决定](docs/adr/0001-precompiled-installation.md)。

已实现预编译候选的下载、本地安装、匹配更新、离线启动及安全卸载。目前没有公开安装地址，实际下载验收使用本地测试服务；源码与产物保留在本机供审查。

## 支持范围

- 已有运行验收：macOS Apple Silicon，官方 CLI **0.164.0**，官方 standalone `codex` 包布局 v1。
- Intel Mac、Linux x64/ARM64、Windows x64 的安装器与构建流程正在准备，尚待各平台真实构建验收；npm/Homebrew 布局尚未支持。官方版本变化后仅取得明确匹配的发行；尚无发行便停止。未来版本须由维护者移植与验收，不宣称已有真实兼容。
- 默认预编译安装需要 Python 3.9+ 和匹配官方包；macOS 另需系统 codesign；无需 Rust、Cargo、Git 或源码目录。官方包必须位于当前 `CODEX_HOME`（默认 `~/.codex`）的 `packages/standalone/releases` 中。
- 显式开发者源码构建还需要 Git、Xcode Command Line Tools（含 `strip`、`codesign`）、通过 rustup 安装的 `cargo` 和 `rustup`（在 PATH 中），以及下载上游源码和 Rust 依赖的网络。
- 更新器根据匹配版本源码的 `codex-rs/rust-toolchain.toml` 安装工具链。0.164.0 使用 Rust 1.99.1。首次构建为大型 Rust 工作区的优化构建，预留数十 GB 空间和较长编译时间；具体开销随机器、缓存而异，尚无全新环境基准。

## 正在准备的其他平台

新增候选目标为 Intel Mac、Linux x64/ARM64 和 Windows x64，详见[平台决定及验收边界](docs/adr/0002-native-platform-candidates.md)。这些目标的安装包尚未经过原生构建和验收，因此当前已验证支持范围仍是上面的 Apple Silicon 版本。

维护者可在私有 GitHub 仓库手动运行 `Build private platform candidates`。它固定上游源码、工具链及官方资源，在对应系统构建，并在临时目录安装、更新、离线启动和卸载；Linux 另检查沙箱。缺失许可文本阻止打包。流程没有公开 Release 或更改仓库可见性的步骤。构建工具需要 Python 3.12+；普通用户仍只需 Python 3.9+，不编译 Rust。显式开发者源码构建入口仍限原有 macOS Apple Silicon 流程。

Windows 成品就绪并发布后，预期使用 PowerShell：

```powershell
irm https://raw.githubusercontent.com/HezLUO/codex-custom/main/bootstrap.ps1 | iex
```

这同样是尚未启用的发布后命令格式。Python 需在 PATH，官方程序默认从 LocalAppData 的 OpenAI/Codex 安装目录识别；其他位置使用 `CODEX_OFFICIAL_BIN` 明确指定完整 standalone 包内的 `codex.exe`。定制入口是 `codex-custom.cmd`，默认写入用户 `.local/bin`，按安装提示加入 PATH。Linux 与 Intel Mac 使用下面的 shell 入口；只在存在明确匹配且通过审查的成品时安装。

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

预编译入口复制自己的运行组件，可移走 checkout。默认状态目录为 `~/.local/share/codex-custom/precompiled`，可用 `CODEX_CUSTOM_STATE_DIR` 选择全新目录；安装后 shim 固定该目录。拒绝自动接管旧源码安装。校验归档、签名、版本、官方完整资源及逐文件收据后才激活；有效匹配版本可离线启动。默认启动从不隐式编译。官方版本或资源变化时自动取得明确匹配的预编译发行；下载或校验失败便停止并提示使用官方 `codex`，保留原产物供诊断，不运行不匹配的旧前端。

## 预编译更新、恢复和卸载

官方界面的 **Update now / Later** 保留官方职责；下次运行定制入口时，检查官方版本及逐文件资源收据。匹配本地安装直接离线启动；需要新成品时自动下载该官方版本与平台的精确发行，不新增确认、不编译。真实未来官方升级尚未实测；当前兼容声明仍仅为 0.164.0。

同一官方版本发布了新的定制修订时，显式运行：

```sh
codex-custom --update
# 下载失败时使用官方程序继续工作；修复网络/官方安装后重试相同命令
codex --version
```

失败不切换当前版本，归档暂存下载目录由本次进程清理；中断可能留下未激活发行，保留供本机诊断，不上传收据、绝对路径或日志。没有自动降级到旧的不同官方版本。若安装收据、入口或组件已被替换，管理命令拒绝操作；从审查过的源码或初始安装入口选择全新 state/bin 安装，勿手动伪造归属。

```sh
codex-custom --uninstall          # 只移除所属入口，保留发行与本机收据
# 如要同时清理该安装自己的全部发行，在卸载入口前选择：
codex-custom --uninstall --purge
# 入口已卸载时可通过同一源码、相同 state 和 bin-dir 重复管理：
python3 scripts/install.py --uninstall --purge --bin-dir "$HOME/.local/bin"
```

默认不删除发行、缓存或诊断文件；预编译路径没有持久下载缓存或运行日志。可选 `--purge` 只删除收据确认的本安装发行及其独立资源包，保留 state 的归属标记和锁文件，便于重复执行。不删除官方程序、官方 current、服务、登录、配置、会话、源码构建缓存或其他安装的包。活动定制会话持有运行租约，清理时会拒绝；先退出这些会话再重试。安装、更新、卸载共享同一个 state 锁，遇另一项管理操作时停止并提示重试。

## 显式开发者源码构建方式

以下命令用于开发者源码方案，会在首次运行时本地编译；不是默认的预编译安装入口。

先按官方方式安装并验证 `codex --version`，准备上述依赖，然后在本仓库运行：

```sh
CODEX_CUSTOM_BUILD_FROM_SOURCE=1 ./codex-custom --version
CODEX_CUSTOM_BUILD_FROM_SOURCE=1 ./codex-custom
CODEX_CUSTOM_BUILD_FROM_SOURCE=1 ./codex-custom resume --last
```

显式源码入口首次运行会构建与本机官方版本匹配的前端。它会访问官方配置、登录和会话；不会创建另一套账户。已有可用安装无需迁移。**首次构建会下载源码/依赖并在官方 releases 的独立子目录中生成定制包。**

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

候选项目采用 Apache-2.0，见 [LICENSE](LICENSE)。补丁包含来自 OpenAI Codex 的上下文，保留上游 [NOTICE](NOTICE)；修改说明见 [维护说明](docs/MAINTENANCE.md)。上游源码为 [openai/codex](https://github.com/openai/codex)，基线 tag 为 `rust-v0.164.0`。许可证及通知保留方案依据 [Apache-2.0 第 4 节](https://www.apache.org/licenses/LICENSE-2.0)。实际候选已附依赖通知并完成本地检查；四个精确依赖版本缺少独立 MIT 许可文本，仍需维护者在公开分发前审定。ad hoc 签名不认证发布者、未公证。源码审计和本地验收均不代表公开发布授权。
