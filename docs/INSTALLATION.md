# 安装预编译版本

五个平台的 [GitHub Release](https://github.com/HezLUO/codex-custom/releases) 已于 2026-10-25 发布，以下命令现在可用；请先确认兼容范围。

## 安装前

需要 Python 3.9+（Unix 命令为 `python3`，Windows 为 `python`），以及已经安装并可运行的官方 **Codex CLI 0.164.0 standalone 包，布局 v1**。本项目不下载或编译替代官方安装，也不支持 npm/Homebrew 包布局。先运行 `codex --version` 确认版本；其他版本暂无兼容保证，不要为了本项目盲目覆盖现有官方安装。

支持 macOS Apple Silicon、Intel Mac、Linux x64/ARM64、Windows x64。macOS 需要系统 `codesign`；Linux 需要官方包所需的 glibc/沙箱环境，已验收环境为 Ubuntu 24.04，不能视为支持所有发行版。Windows ARM64 不在本次范围内。

完整官方包必须在当前 `CODEX_HOME`（默认 `~/.codex`）的 `packages/standalone/releases` 下，包含 helper、rg 和 voice 资源。仅复制单个 `codex` 可执行文件不满足要求。非默认官方入口可用 `CODEX_OFFICIAL_BIN` 指向该完整包内的程序；这不会放宽包布局校验。

## macOS / Linux

```sh
curl -fsSL https://raw.githubusercontent.com/HezLUO/codex-custom/main/bootstrap.sh | sh
```

安装后，如果命令目录尚未在 PATH 中，先按安装器提示加入 PATH；默认目录为 `$HOME/.local/bin`。也可以直接运行：

```sh
"$HOME/.local/bin/codex-custom" --version
"$HOME/.local/bin/codex-custom"
```

## Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/HezLUO/codex-custom/main/bootstrap.ps1 | iex
```

Python 必须在 PATH。官方入口默认从 LocalAppData 下 OpenAI/Codex 的安装位置识别；完整包位置仍遵循上面的 `CODEX_HOME` 约定。默认定制入口为用户 `.local/bin/codex-custom.cmd`。将该目录加入 PATH 后运行 `codex-custom`，或者直接运行：

```powershell
& "$HOME/.local/bin/codex-custom.cmd" --version
& "$HOME/.local/bin/codex-custom.cmd"
```

不要求管理员权限或调整 PowerShell 执行策略。Windows 普通权限控制台、信号处理和完整 TUI 尚无本轮专项验收，不能由安装生命周期通过推定全部交互行为正常。

## 使用、更新与卸载

以下命令在入口已加入 PATH 后适用于上述系统：

```text
codex-custom --version
codex-custom
codex-custom resume --last
codex-custom --update
codex-custom --uninstall
```

`--update` 获取与当前官方版本和平台精确匹配的定制修订。默认卸载只删除所属启动入口并保留发行；要连同该安装所属的发行一起清理，在入口仍存在时运行：

```text
codex-custom --uninstall --purge
```

先退出活动的定制会话。清理保留官方程序、登录、配置、会话和未知文件。该前端使用既有官方账户与会话，不需要把这些数据提交给项目维护者。

首次安装和更新需要网络；匹配并验证通过的已安装版本可以离线启动。未知版本、资源变化、网络或校验失败时停止，使用官方 `codex` 继续工作；不会自动在本机编译。

## 手动下载与核验

到仓库 Releases 选择同时匹配官方版本与平台的条目；每个条目包含 `codex-custom.tar.gz`、`codex-custom.tar.gz.sha256` 和 `release.json`。平台与归档摘要见[发布说明](RELEASE-NOTES.md)。归档文件名相同，下载时为各平台分别保存目录。

使用审查过的源码目录进行本地安装，`SHA256` 替换为对应平台的实际摘要：

```sh
python3 scripts/install.py --archive ./codex-custom.tar.gz --sha256 SHA256
```

Windows 将上面的 `python3` 改为 `python`。下载校验只是完整性检查；初始脚本来自所选 GitHub 源码地址，尚无独立发布者签名。macOS 包只有 ad hoc 签名，未公证；不提供绕过系统安全设置的指令。详细信任边界见[产物格式](PRECOMPILED-FORMAT.md)。
