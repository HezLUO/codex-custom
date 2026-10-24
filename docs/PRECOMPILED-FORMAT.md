# 本地预编译候选格式

`python3 scripts/release_artifact.py package` 从单个前端、独立来源记录及依赖通知生成 tar.gz 与 SHA-256 文件。归档外保留原始证据，不能把现有安装目录作为输入目录。`inspect` 检查归档结构、隐私规则、元数据与逐文件摘要，不执行归档中的程序；安装器必须在独立暂存目录另行调用 `verify_binary`，核对 Mach-O arm64、严格 ad hoc 签名及 `codex-cli 0.164.0`。

```sh
python3 scripts/release_artifact.py package \
  --binary ../candidate/codex --provenance ../candidate/provenance.json \
  --dependency-notices ../candidate/DEPENDENCY-NOTICES.txt \
  --release-id 0.164.0-custom.1 --output ../candidate/codex-custom.tar.gz \
  --runtime runtime/precompiled.py=scripts/precompiled.py \
  --runtime runtime/release_artifact.py=scripts/release_artifact.py \
  --runtime runtime/update-codex-custom.py=update-codex-custom.py \
  --runtime bootstrap.sh=bootstrap.sh \
  --runtime bootstrap.py=bootstrap.py
python3 scripts/release_artifact.py inspect ../candidate/codex-custom.tar.gz
```

格式版本为 `release.json` 中的 `schema: 1`。必要字段为 `release_id`、`official_version`、`target`、`layout_version`、`source_commit`、`patch_sha256`、`signing`、`provenance` 与 `members`。首版固定官方 0.164.0、aarch64-apple-darwin、standalone layout 1。`members` 对每个有效负载记录 SHA-256 与 Unix mode；不包含清单本身，以免递归。打包器生成全归档 SHA-256 sidecar。安装下载需要可信传输及明确发行定位；同来源摘要只是完整性检查，不能独立证明发布者身份。

必要成员为 `bin/codex`、`LICENSE`、`NOTICE`、`DEPENDENCY-NOTICES.txt`。安装阶段可以明确加入 `runtime/precompiled.py`、`runtime/release_artifact.py`、`runtime/update-codex-custom.py` 、`bootstrap.sh` 和 `bootstrap.py`，每个组件同样列入摘要及隐私审查。拒绝未声明成员、目录、链接、重复成员、PAX 扩展、未知权限、越界名称、单文件超限、256 MiB 压缩归档超限及 768 MiB 累计解压内容超限。下载时同样限制读取总量。官方 helper 与语音资源从用户本机匹配官方包复制，不放进归档。

## 现有二进制复用

现有优化构建的原始前端确实残留编译时 home 前缀，故不能原样分发。没有因迁移而重编译；`sanitize` 在独立副本中，仅将 Mach-O `__TEXT` 的 `__cstring` / `__const` 中 home 前缀改成等长通用构建前缀。原有字符串长度、偏移、指令及常量后缀保持不变，主要影响源文件诊断路径。其他区段出现此类内容会拒绝，不能盲目修改代码或语义数据。修改后重新 ad hoc 签名，并核对签名与版本。来源记录包含原始/转换后摘要、转换方式与替换数量。原件和日常入口不变。清理后的副本已完成真实隔离安装与交互验收，见验证记录。

```sh
python3 scripts/release_artifact.py sanitize \
  --binary ../original/codex --output ../candidate/codex \
  > ../candidate/provenance.json
```

扫描不打印敏感内容，只报告规则。二进制中存在上游静态 UUID 常量（配置示例、云配置常量、WebSocket 协议 GUID）和连续静态字符串误触凭据正则的情况。代码按已审阅完整匹配内容的 SHA-256 精确豁免，新增不同值仍会拒绝。这些不是从本机账户、会话或配置读取的值；该人工审阅规则不能证明不存在所有隐私问题。源码历史另行执行 `audit-release.py`，不能用归档验证替代历史验证。

## 分发审查

前端派生自 OpenAI Codex，保留 Apache-2.0 LICENSE 和上游 NOTICE；补丁与本仓库说明记录上下文显示修改。`DEPENDENCY-NOTICES.txt` 必须来自实际锁定依赖及对应源码许可审查，不能用本仓库顶层许可证替代全部依赖通知。必须准确标出不确定依赖与缺失证据；打包成功也不自动代表法律审查完成或批准公开。来源记录可附带分发审查状态与证据摘要。签名目前只提供本地代码完整性验证，不具备开发者身份认证，也没有公证。发行包与原始检查材料留在仓库外，不上传。

## 首个本地候选的实际审查结果

首个 `0.164.0-custom.1` 前端来源提交与历史 receipt 一致；原工作树差异逐字节匹配原补丁，公开补丁相较原运行补丁新增六行归属注释。原前端 SHA-256 为 `f0db692e37868cf47dc688a9d9160a3ba2ad38f4ce18985e2c4d8b09781c8aed`。对独立副本完成 5,641 处等长 home 前缀清理并重新签名后，前端 SHA-256 为 `6c1beb1f82e549ca7b9122fdb6af6da6293e8c367a46cc3687d862aa129a23c4`。严格签名核对、隔离 HOME 下 `--version` 和 `--help` 均通过。没有重跑 Rust 编译，原安装前端摘要保持不变。新前端随后已在无构建工具且禁止源码读取的隔离环境完成真实安装与交互验收。

依赖通知来自现有 release 前端 fingerprint 图及精确缓存源码记录：1,366 个图节点全部解析，保守收集 1,029 个软件包，包含构建依赖，不能等同最终链接组件的精确清单。另纳入 Rust 标准库、现有内嵌技能和本地原生依赖通知；动态依赖只有 macOS 系统库，不复制这些系统文件。MPL 组件提供对应版本源码 URL。通知文本 SHA-256 为 `c2e1968ec88eee2c032fa25237e0ba80b571bab57e94fe1b99e64add4a4860e1`。

四项 MIT 依赖已完成来源复核。先前将 cookie-factory 列为上游文本缺失并不准确：registry 包缺少这些文件，但精确上游提交内有 `.reuse/dep5` 和 `LICENSES/MIT.txt`，此前扫描漏掉了特殊目录。现在已补入原始文件，不能把本次修正描述成原先已审清。

| 组件 | 已核对并保留的来源 |
| --- | --- |
| cookie-factory 0.3.3 | 精确提交 `d36b805dbd7dd65f2df947235c5bcc573afe2c76` 的 [署名及适用范围](https://github.com/rust-bakery/cookie-factory/blob/d36b805dbd7dd65f2df947235c5bcc573afe2c76/.reuse/dep5)与[完整 MIT 原文](https://github.com/rust-bakery/cookie-factory/blob/d36b805dbd7dd65f2df947235c5bcc573afe2c76/LICENSES/MIT.txt)，原署名为 2017–2023 Geoffroy Couprie |
| fax 0.2.6 / fax_derive 0.2.0 | 原版本已声明 MIT；其直接后继[提交](https://github.com/pdf-rs/fax/commit/5d70a161e33b62305f8bce7af3f7fbd011cfaf5d)于 2025-09-15 添加[原始许可证](https://github.com/pdf-rs/fax/blob/5d70a161e33b62305f8bce7af3f7fbd011cfaf5d/LICENSE)，署名逐字保留；derive/LICENSE 指向根目录 LICENSE，通知中放入目标全文。明确这是后续上游证据，不声称旧包原本带有该文件 |
| debugserver-types 0.5.0 | [精确版本 manifest](https://github.com/Marwes/debugserver-types/blob/d444f163123af5b4fbce7375d1afead7e9b8a224/Cargo.toml)明确声明 MIT 与作者 Markus Westerlind；所查精确源码及当前上游未提供独立版权行。保留该声明、可用作者资料、固定版本来源及完整 MIT 条款，不虚构版权人或年份，不声称找回了不存在于所查材料中的版权行 |

cookie-factory 原始 MIT 文本 SHA-256 为 `d09216dc1ea5f273997667935a8d6514d80f00b89fb6954ecc3a43e0a6e360de`，fax 根许可证为 `7101390b4c8edd752f4c0de47f35d61b44d9cf0ee8dd032115e25644e277cfff`。eventsource-stream 与 io_tee 继续使用其声明的 Apache-2.0 选项。完成来源核对不等同独立法律背书或公开发布授权；debugserver-types 的上游资料限制仍准确列出。旧 `.6` 候选中的四项待查说明属于本次修订前的历史状态。

本地安装要求三个 runtime 成员齐备；源码构建模块仅复用官方包识别与复制边界，默认运行路径不调用其构建入口。预编译 receipt 覆盖前端、运行组件及复制的完整资源；共享 state 锁保护安装、更新下载、激活、卸载和启动核对；发行运行租约阻止删除正在使用的资源。

安装准入继续对整个归档和前端执行隐私扫描。已安装发行在完整 receipt 所属关系、每个成员权限与 SHA-256、复制资源清单及前端摘要全部一致后，可以复用该前端精确字节的准入隐私结论；架构、严格签名、ad hoc 签名策略和实际版本每次仍核对。不存在用户可选的跳过校验参数。匹配版本启动在同一次 state 锁中完成一次完整核对和运行租约取得，再由监督进程持有租约；仍复查官方包在启动前没有变化。

原生包目录只有成功独占创建后才属于当前操作；复制失败由创建者清理，后续激活失败由接收归属的安装器回滚，不清理碰撞路径中的外来内容。可选清理只删除收据验证的 `package` 子树，其父目录仅在空时移除，旁边未登记的文件保留。

## 在线发行发现

引导入口默认读取 `https://github.com/HezLUO/codex-custom/releases/download/official-0.164.0-aarch64-apple-darwin/release.json`。tag 明确绑定官方版本和平台，不使用 latest。该描述文件应包含：

```json
{"schema":1,"official_version":"0.164.0","target":"aarch64-apple-darwin","layout_version":1,"release_id":"0.164.0-custom.1","archive":"codex-custom.tar.gz","sha256":"ARCHIVE_SHA256"}
```

`sha256` 必须替换成实际归档的 64 位小写十六进制摘要；`release_id` 必须与归档内 `release.json` 一致。发布新定制修订时更新同一精确兼容 tag 下的描述与资产，不能将不兼容前端放入该 tag。描述文件上限 64 KiB、归档上限 256 MiB；固定归档文件名防止通过描述重定向到任意路径。每个归档成员必须与清单的名称、权限和摘要一致，之后才加载运行组件，统一安装器继续检查隐私、签名、版本和完整资源。描述与归档来自同一发行来源，SHA-256 不提供独立发布者认证。

`bootstrap.sh` 与它取得的 `bootstrap.py` 是初始安装信任入口，来自用户选择的源码地址；它们尚无独立签名或固定外部信任摘要。shell 先检查 Python 3.9+ 和 macOS ARM64，再以 HTTPS 读取 Python 引导器；Python 在请求发行描述与归档前核对 codesign、完整官方包与资源。引导器也列入实际候选的摘要和隐私审查，但不能用归档自述的摘要反向证明最初下载的引导器身份。HTTPS 重定向不得降级到 HTTP。

离线审查使用 `python3 scripts/install.py --archive FILE --sha256 SHA256`；在线审查使用 `python3 scripts/install.py --release-source URL`。`CODEX_CUSTOM_RELEASE_SOURCE` 覆盖默认发行根地址，`CODEX_CUSTOM_BOOTSTRAP_URL` 覆盖 shell 的 Python 引导器地址；仅 HTTPS 或 loopback HTTP 测试来源被允许。测试目录下放置 `official-0.164.0-aarch64-apple-darwin/release.json` 和 `codex-custom.tar.gz`，shell/Python 引导器可置于服务器根目录。这些选项不跳过任何归档或安装校验。

## 静态扫描豁免的可复核来源

扫描豁免只接受代码中十一项完整匹配内容的 SHA-256。四个 UUID 形状常量可在固定 Codex 提交 `6aaac694803004a63c6f393d153c96d22521a6b9` 的 `codex-rs/cloud-config/src/cache.rs`、`codex-rs/config/src/config_toml.rs`，以及 headers 0.4.1 的 `src/common/sec_websocket_accept.rs` 找到；用途分别为上游缓存完整性常量、公开配置示例和 WebSocket 协议 GUID。

另外七项凭据正则命中跨越 Rust 合并静态字符串边界：`codex-rs/network-proxy/src/credential_broker/providers/` 的公开前缀分类器和环境变量名；`codex-rs/tui/src/history_cell/mcp.rs` 的标签与 `codex-rs/protocol/src/protocol.rs` 调试字段；`codex-rs/tui/src/bottom_pane/status_line_setup.rs` 的状态标识；`codex-rs/websocket-auth/src/lib.rs` 的四组 clap 帮助、参数名及紧邻静态错误消息。它们不被宣称为单一完整源文字串或可重现构建证明。

复核时固定前端摘要，按相同正则在内存扫描，只输出规则、偏移、长度和匹配摘要；UUID 可与固定源码逐字节匹配，合并字符串则按源码常量与编译文本邻接关系检查。完整私有审阅笔记留在仓库外。新增不同匹配或前端来源变化必须重新审阅，不扩大为规则级豁免。
