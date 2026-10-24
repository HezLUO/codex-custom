# 为 Intel Mac、Linux 和 Windows 准备原生候选

用户要求增加 Intel Mac、Linux 和 Windows 的预编译安装包。此决定扩展 [首版安装决定](0001-precompiled-installation.md) 的候选范围，不把构建配置等同已验证支持。

| 平台 | 精确发行 target | 原生 GitHub runner | 当前实测状态 |
| --- | --- | --- | --- |
| Apple Silicon Mac | aarch64-apple-darwin | macos-15 | 既有 `.7` 候选已验证；新运行组件另行验收 |
| Intel Mac | x86_64-apple-darwin | macos-15-intel | 待原生构建与验收 |
| Linux x64 | x86_64-unknown-linux-musl | ubuntu-24.04 | [原生构建、隔离生命周期及成品复核通过](https://github.com/HezLUO/codex-custom/actions/runs/40088351134) |
| Linux ARM64 | aarch64-unknown-linux-musl | ubuntu-24.04-arm | [原生构建、隔离生命周期及成品复核通过](https://github.com/HezLUO/codex-custom/actions/runs/40088705811) |
| Windows x64 | x86_64-pc-windows-msvc | windows-2022 | 待原生构建与验收 |

平台范围来自用户选择：Intel Mac、Linux 和 Windows 都增加。Windows ARM64、Linux 32 位和任意 Linux 发行版的兼容保证不在本轮声明内。Linux 主程序使用与官方发行相同的 MUSL target；官方 voice 仍依赖 GNU/glibc 环境，不能据此声称支持全部 MUSL-only 系统。

## 安装与完整性边界

普通用户仍下载成品，Python 3.9+ 足够，不在用户电脑编译。Unix 使用 shell 引导器；Windows 使用 PowerShell 引导器，Python 必须在 PATH。描述文件按官方版本和精确 target 选取，不使用 latest，不自动降级为源码构建。当前官方版本仍固定 0.164.0 / standalone layout 1。

运行组件共用 `release_artifact.py` 的平台边界：Mach-O arm64/x64、ELF64 little-endian x64/ARM64、PE32+ AMD64 分别检查；macOS 执行严格 ad-hoc 签名检查，Linux/Windows 不声称拥有 OpenAI 或其他发布者签名。文件摘要不能替代发布者身份认证。

保留原三个 runtime 文件的自包含加载接口。Unix 归档不增加旧 `.7` 下载器无法识别的新成员，使旧客户端可以更新；Windows 归档可附带 PowerShell 引导器。新增平台不依赖从同一 checkout 导入额外 Python 模块。

Windows 使用拥有明确归属的 `.cmd` 启动器和原子替换的 `current.json` 选择文件，不要求创建文件符号链接或启用开发者模式。启动器以编码后的 Python 常量保存安装路径，避免 `%` 等路径字符被 cmd 当作变量。共享会话租约与排他管理锁使用 [LockFileEx](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex)；CRT `_locking` 的读模式仍是排他锁，不用于共享租约。拒绝收据路径中的 junction/reparse-point 跳转；清理只删除所属 package，保留旁边未知文件。

官方完整包从用户已有安装复制到 native releases 下的私有子目录，不改官方选择链接。替换主程序后同步更新 voice 外层 manifest 的该程序摘要；其余字段及 voice 运行时字节保持不变。Linux 编译前固定匹配官方包的 bwrap 摘要，安装时再次匹配，禁止把绑定不同 bwrap 的前端装入现有资源包。Windows 识别官方默认的 LocalAppData 安装入口，以及显式 CODEX_OFFICIAL_BIN / CODEX_INSTALL_DIR。

## 构建与验收

`.github/workflows/build-platforms.yml` 仅支持手动执行，权限为 contents:read，没有创建 Release、推送源码或改公开状态的步骤。默认只编译新增的四个 target，既有 Apple Silicon 二进制继续复用，不因安装器变化重复编译。固定上游 commit 与 Rust 工具链；使用原生 runner，固定并核对官方完整包及 V8/Zig 输入，保留上游 MSVC 栈和 CRT 参数，并映射构建路径。构建工具需要 Python 3.12+，与普通用户的运行依赖分开。

官方包与 checksum 清单摘要已按官方 0.164.0 Release 的资产记录固定；上游同名资产变化会停止构建。Linux 沙箱的 userns/AppArmor 前提只设置于临时 GitHub runner，不在用户电脑执行。PowerShell 内嵌下载逻辑由 shell 中的单一来源生成，`scripts/sync-bootstraps.py --check` 防止安全修正只进入其中一份。

每个平台重新收集其 Cargo 解析图、源许可及标准库通知，包含构建依赖，不复用 Mac 图冒充 Windows/Linux 图。已核实的许可补充固定原文 URL 和 SHA-256；未知缺失文本阻止生成安装包，收集结果留作审查。CI 成品仍是候选，需要对应平台的通知复核；公开仓库中的日志与候选产物可见，不能直接作为已验证的正式发行。

`scripts/accept-platform.py` 在临时 HOME/CODEX_HOME 与复制的官方包中，运行安装、版本、resume 参数、HTTP 更新、断网启动、重复卸载、重装和清理，核对官方及合成用户资料未改动，保留未知目录同级文件。Linux 另运行实际 bwrap 沙箱。它不提供账号、不请求模型，不把启动器不含源码路径描述为 OS 级源码读取拒绝。完整 TUI、voice 功能、Windows 普通权限与控制台信号仍需实际验收，不能由架构夹具代替。

最初获准推送至私有仓库并运行 Actions；在完成源码、提交历史、Issues（包括历史编辑版本）的隐私复查，并移除旧的未执行构建记录后，用户另行确认公开仓库，使用免费标准 runner 构建。公开源码与候选构建不代表正式 Release 获准发布。原生构建、许可复核与验收通过后，才扩大 README 的实际支持声明。新增平台必须实际编译，和此前仅搬动源码目录无需重编译的情况不同。

实现依据：[固定上游 target 定义](https://github.com/openai/codex/blob/6aaac694803004a63c6f393d153c96d22521a6b9/scripts/codex_package/targets.py)、[完整包布局](https://github.com/openai/codex/blob/6aaac694803004a63c6f393d153c96d22521a6b9/scripts/codex_package/layout.py)、[Linux bwrap 校验](https://github.com/openai/codex/blob/6aaac694803004a63c6f393d153c96d22521a6b9/codex-rs/linux-sandbox/src/bundled_bwrap.rs)、[voice 外层清单](https://github.com/openai/codex/blob/6aaac694803004a63c6f393d153c96d22521a6b9/third_party/voice/assemble_package.py)、[Windows 官方安装器](https://github.com/openai/codex/blob/6aaac694803004a63c6f393d153c96d22521a6b9/scripts/install/install.ps1)、[GitHub runner 配置](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)。

原生测试已经在固定输入上通过、且修复只涉及 Python 准入时，可以显式开启默认关闭的测试证据复用。记录严格绑定特定已复核任务、Rust 源码及补丁、工具链、实际编译准备/执行代码、锁文件规范化模块、完整已审查 workflow 与 runner image；任一绑定不符便停止复用。新 CLI 仍实际编译并进行全部准入与生命周期检查。provenance 区分本轮测试执行与引用既有原生结果；此优化不扩大安装或交互验收声明。
