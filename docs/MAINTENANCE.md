# 维护与补丁边界

## 基线和源码修改

上游：<https://github.com/openai/codex>，tag `rust-v0.164.0`，commit `6aaac694803004a63c6f393d153c96d22521a6b9`。根目录 LICENSE 与 NOTICE 从该基线保留，项目自身新增代码也按 Apache-2.0 准备。

`patches/codex-0.164.0-context-details.patch` 修改以下文件，每个文件均添加了 codex-custom 修改声明：

| 上游路径（相对 codex-rs/tui/src） | 修改 |
| --- | --- |
| bottom_pane/status_line_setup.rs | 增加 context-details 字段、说明及预览映射 |
| bottom_pane/status_line_style.rs | 沿用上下文样式 |
| bottom_pane/status_surface_preview.rs | 增加预览值与字段遍历 |
| chatwidget/status_surfaces.rs | 复用官方当前用量及百分比公式，构造底栏值 |
| chatwidget/tests/status_and_layout.rs | 对照 /status，覆盖压缩后用量、零、超容量、未知及等待中状态 |
| local_settings.rs | 在前端偏好层读取 CODEX_CUSTOM_STATUS_LINE，不改服务配置 |

与迁移前运行补丁相比，仅新增上述文件头声明；去除声明后的完整 diff 已逐字节对比相同。没有加入历史诊断期间的临时快照修正。

## 显式源码构建器的保证与限制

构建目录、源码缓存、工具链和运行状态不依赖源码父目录。Rust 工具使用 PATH 中的 rustup/cargo，并遵循标准 CARGO_HOME/RUSTUP_HOME；`CARGO_TARGET_DIR` 固定指向选定 cache 下的 target。新构建清单 schema 为 3，旧清单需重新构建，不直接迁入旧安装产物。

从官方仓库获取本机版本对应 tag；严格 `git apply --check`，不使用模糊应用，不自动改补丁。`--source` 为维护用途：须是匹配 release tag 的已打补丁 checkout，拒绝未跟踪文件及额外 tracked diff（含暂存变更）。构建可能改写其 Cargo.lock，因此只用于一次性源码 checkout。

上游 release tag 可能只更新本地 workspace 包版本而未同步锁文件。更新器仅依据 cargo metadata 修正无 source 的本地包版本，外部依赖版本、来源和 checksum 不得变更；其他 lockfile diff 会停止。之后使用 `--locked` 测试和编译，记录锁文件 diff。

完整定制包保留原生 standalone 身份与包资源。当前官方按包目录命名和根元数据筛选旧包，独立 codex-custom 父目录不满足清理条件；这项上游假设需要每次移植复核。更新器不安装或升级后台服务，服务复用/选择由官方代码处理。

每次启动核对官方版本、匹配包、补丁与更新器哈希、release 标记和定制包清单；不把清单校验当作远程签名验证或供应链证明。新包的签名是本地 ad-hoc 签名，不是 OpenAI 签名。

构建失败不切换生效链接；未激活产物、日志及下载缓存可能留下。进程并发由 state 目录内文件锁保护。不同 state 目录使用不同锁，不应共用同一 cache 并发构建。

## 上游升级流程

1. 保留独立官方 codex 作为恢复入口。记录官方版本，核对 tag、目标和安装布局。
2. 在一次性上游 checkout 应用补丁；冲突时人工移植。若官方已提供相同功能，评估移除补丁。
3. 复核当前上下文与累计 token 的区别、`/status` 的窗口和百分比算法、前端偏好与后台服务选择边界。
4. 复核 standalone 身份识别、Update now 安装入口、包清理规则、helper/资源及元数据要求。
5. 运行 Python 测试与隐私审计；构建流程必须经过格式、五组 TUI 测试、release 编译、签名与包校验。
6. 按 VALIDATION.md 的真实升级流程做交互验收，记录已测范围和限制后再扩大兼容声明。
7. 更新补丁名、常量及文档中的基线，保留修改声明、LICENSE 和 NOTICE。勿把日志、会话、截图或用户构建清单加入源码历史。

## 再分发范围

源码仓库不携带二进制。默认预编译流程已实现，见[安装方式决定](adr/0001-precompiled-installation.md)和[候选格式](PRECOMPILED-FORMAT.md)。发行归档只带定制前端、运行/引导组件、元数据与许可通知；helper 和语音资源在本机从精确匹配官方包复制。实际依赖通知覆盖保守构建图，不等同精确链接清单；四个 MIT 依赖仍需公开前审定，不能仅凭根许可证宣称整个二进制许可审查完成。

## 预编译生命周期维护

安装收据包含随机安装标识、入口归属、发行清单及完整包文件摘要。相同官方版本的新定制发行由 `--update` 显式取得；正常匹配启动无需网络。官方变化只下载明确版本与平台 tag 下的匹配发行；下载元数据、归档成员、Mach-O 架构、签名、程序版本及官方稳定性均通过才切换 `current`。下载器验证归档全部成员之后加载新运行组件；更新时不复用旧 Python 验证模块缓存。

所有管理操作共享 state 锁；更新下载期间保留该锁。启动在锁内核对收据并取得运行租约，租约跨 exec 保留；清理必须取得该发行的排他租约。发行目录及资源包不就地修改，因此更新不会删除运行中的旧包。卸载默认移除精确匹配 shim，可选清理只作用于同安装标识、state 和资源目录对应的完整收据；未知或篡改内容拒绝，其他安装保持。

移植新官方版本时，需要新补丁、来源与通知审查，并使用新版本实际包做功能验收。下载选择支持以夹具验证未来匹配版本路径，并不代表任意未来版本已经兼容。当前打包器只生产 0.164.0 候选，不能仅修改描述文件让旧二进制冒充新版。
