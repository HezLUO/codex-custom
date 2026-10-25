# Codex Custom 首次预编译发行说明

发布草案，待维护者确认后发布。兼容官方 **Codex CLI 0.164.0 standalone layout v1**。

新增 `context-details` 底栏字段，显示与 `/status` 一致的当前上下文用量、容量和剩余百分比：

```text
Context 95% left (33.8K used / 475K)
```

支持通过终端命令下载预编译程序，普通用户无需 Rust、Cargo 或本地编译。定制入口独立于官方入口，复用既有官方账户、配置及会话；支持匹配更新、离线启动和按归属卸载。具体步骤见[安装指令](INSTALLATION.md)。

## 本次发布文件

安装器按官方版本和平台选择下表 tag。五个条目共同构成本次发行，不以 GitHub 的 latest 选包。不同平台保留各自已验收的定制修订，不为统一版本号重新打包。

| 平台 | 归档内修订 | GitHub Release tag |
| --- | --- | --- |
| Apple Silicon Mac | 0.164.0-custom.9 | official-0.164.0-aarch64-apple-darwin |
| Intel Mac | 0.164.0-custom.8 | official-0.164.0-x86_64-apple-darwin |
| Linux x64 | 0.164.0-custom.8 | official-0.164.0-x86_64-unknown-linux-musl |
| Linux ARM64 | 0.164.0-custom.8 | official-0.164.0-aarch64-unknown-linux-musl |
| Windows x64 | 0.164.0-custom.10 | official-0.164.0-x86_64-pc-windows-msvc |

每个平台提供归档、SHA-256 sidecar、在线安装描述 `release.json`、对应项目源码归档及重新编写的 `provenance-summary.json`。归档内包含 LICENSE、NOTICE、目标依赖通知和必要运行组件。Apple Silicon 另附通知补充对应的源码归档。不会附带原始本地日志、安装收据、账户资料、会话、截图或私有审阅材料。

### 归档 SHA-256

```text
aarch64-apple-darwin       2e5b161c67b64e4d9e2b98f80d7517e24ae12c2af02e1c39590119d055e69eb6
x86_64-apple-darwin        dcc405f5e7c0079f5fd5059095f7751c477f3a901cbe3cd5f504fc535cbdbd2b
x86_64-unknown-linux-musl  b05538064df196dac9fe235107ad1becb650f9fac23f745104b990ee2ebaee45
aarch64-unknown-linux-musl 0f039eeb68e9483f1ce2bb5b442798505c85efb55568e94033c426ed6ac59133
x86_64-pc-windows-msvc     e0f198be572751749ae4748f6b5903b1438dfa05eda377b1f18fa66b12a40d7d
```

## 验证与修复

Intel Mac、Linux x64/ARM64、Windows x64 在对应原生 runner 上完成安装、更新到不同修订、离线启动、卸载、重复卸载、重新安装及清理；Linux 另执行实际 bwrap。Windows 修复 `.cmd` 自删除导致成功卸载仍返回失败的问题，并验证通过旧候选自身组件升级到修正版；未知入口替换内容会被保留。

Windows 修正版复用原任务编译好的前端和依赖通知，仅更新运行组件，没有重编译 Rust。Intel Mac 本轮实际编译前端，75 项相关 Rust 测试引用严格绑定的既有成功原生任务。Linux 两个平台实际构建并执行对应测试。

Apple Silicon 复用已完成真实隔离安装与交互验收的相同前端；本次仅补充依赖通知，重查摘要、隐私、严格 ad hoc 签名和隔离版本/resume 帮助，没有重跑 Rust 或完整生命周期。原始通知保留，补充依赖解析图不冒充最终链接图。

四个新增平台的原生结果：

- [Intel Mac](https://github.com/HezLUO/codex-custom/actions/runs/40102972110)
- [Linux x64](https://github.com/HezLUO/codex-custom/actions/runs/40088351134)
- [Linux ARM64](https://github.com/HezLUO/codex-custom/actions/runs/40088705811)
- [Windows x64 修复验收](https://github.com/HezLUO/codex-custom/actions/runs/40129684969)，[原编译与 Rust 测试](https://github.com/HezLUO/codex-custom/actions/runs/40103098988)

详细验证范围、项目提交及来源见[验证记录](VALIDATION.md)。候选内的 provenance 保留生成时状态（如 `target-source-review-required`）；本次后续复核由外部摘要记录，不改写已经验收的归档。

## 已知限制与许可

仅支持上述精确官方版本、平台及完整 standalone 包；npm/Homebrew、Windows ARM64、任意 Linux 发行版兼容保证和未来官方版本不在本次范围。新增平台尚未覆盖完整 TUI、voice、模型推理或 Windows 普通权限控制台专项验收。历史完整 TUI 测试存在已记录的失败，不能将 75 项相关测试通过表述为完整上游测试全绿。

macOS 使用 ad hoc 签名，未公证；Linux/Windows 不提供发布者身份签名。源码、提交历史和发行文件均经过隐私规则扫描及来源复核，但摘要和扫描不能证明发布者身份或不存在所有秘密。

项目采用 Apache-2.0，保留 OpenAI Codex 的 LICENSE/NOTICE 及各目标依赖许可文本。个别 MIT 上游未提供独立原始版权行，保留已发布作者、声明及完整条款，不虚构署名；来源限制见[许可来源记录](NATIVE-LICENSE-SOURCES.md)。本项目与 OpenAI 无隶属或背书关系。
