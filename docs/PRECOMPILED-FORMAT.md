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

现有优化构建的原始前端确实残留编译时 home 前缀，故不能原样分发。没有因迁移而重编译；`sanitize` 在独立副本中，仅将 Mach-O `__TEXT` 的 `__cstring` / `__const` 中 home 前缀改成等长通用构建前缀。原有字符串长度、偏移、指令及常量后缀保持不变，主要影响源文件诊断路径。其他区段出现此类内容会拒绝，不能盲目修改代码或语义数据。修改后重新 ad hoc 签名，并核对签名与版本。来源记录包含原始/转换后摘要、转换方式与替换数量。原件和日常入口不变。交互功能仍需后续真实安装验收。

```sh
python3 scripts/release_artifact.py sanitize \
  --binary ../original/codex --output ../candidate/codex \
  > ../candidate/provenance.json
```

扫描不打印敏感内容，只报告规则。二进制中存在上游静态 UUID 常量（配置示例、云配置常量、WebSocket 协议 GUID）和连续静态字符串误触凭据正则的情况。代码按已审阅完整匹配内容的 SHA-256 精确豁免，新增不同值仍会拒绝。这些不是从本机账户、会话或配置读取的值；该人工审阅规则不能证明不存在所有隐私问题。源码历史另行执行 `audit-release.py`，不能用归档验证替代历史验证。

## 分发审查

前端派生自 OpenAI Codex，保留 Apache-2.0 LICENSE 和上游 NOTICE；补丁与本仓库说明记录上下文显示修改。`DEPENDENCY-NOTICES.txt` 必须来自实际锁定依赖及对应源码许可审查，不能用本仓库顶层许可证替代全部依赖通知。必须准确标出不确定依赖与缺失证据；打包成功也不自动代表法律审查完成或批准公开。来源记录可附带分发审查状态与证据摘要。签名目前只提供本地代码完整性验证，不具备开发者身份认证，也没有公证。发行包与原始检查材料留在仓库外，不上传。

## 首个本地候选的实际审查结果

首个 `0.164.0-custom.1` 前端来源提交与历史 receipt 一致；原工作树差异逐字节匹配原补丁，公开补丁相较原运行补丁新增六行归属注释。原前端 SHA-256 为 `f0db692e37868cf47dc688a9d9160a3ba2ad38f4ce18985e2c4d8b09781c8aed`。对独立副本完成 5,641 处等长 home 前缀清理并重新签名后，前端 SHA-256 为 `6c1beb1f82e549ca7b9122fdb6af6da6293e8c367a46cc3687d862aa129a23c4`。严格签名核对、隔离 HOME 下 `--version` 和 `--help` 均通过。没有重跑 Rust 编译，原安装前端摘要保持不变。新前端的真实交互安装验收由后续安装任务完成。

依赖通知来自现有 release 前端 fingerprint 图及精确缓存源码记录：1,366 个图节点全部解析，保守收集 1,029 个软件包，包含构建依赖，不能等同最终链接组件的精确清单。另纳入 Rust 标准库、现有内嵌技能和本地原生依赖通知；动态依赖只有 macOS 系统库，不复制这些系统文件。MPL 组件提供对应版本源码 URL。通知文本 SHA-256 为 `c339b8a87f9eedfbd0e10c1b0fd08aa1bce36338f9f313b6b8f89dc26dfe62e7`。

六个上游软件包在精确版本源码中缺少独立许可文本，通知保留声明条款、可用作者资料及来源依据。cookie-factory、debugserver-types、fax、fax_derive 四个 MIT 情况仍需维护者在公开分发前审查；eventsource-stream 和 io_tee 使用其声明的 Apache-2.0 选项。不虚构版权人或年份。来源记录将状态标为 `local-reviewed/public-maintainer-review-required`，允许本地候选验证，不表示许可、公开分发或发布授权已全部完成。全量历史 TUI 测试的 38 个已诊断失败继续保留，不能描述为全部通过。

本地安装要求三个 runtime 成员齐备；源码构建模块仅复用官方包识别与复制边界，默认运行路径不调用其构建入口。预编译 receipt 覆盖前端、运行组件及复制的完整资源；共享 state 锁保护安装和启动核对。

## 在线发行发现

引导入口默认读取 `https://github.com/HezLUO/codex-custom/releases/download/official-0.164.0-aarch64-apple-darwin/release.json`。tag 明确绑定官方版本和平台，不使用 latest。该描述文件应包含：

```json
{"schema":1,"official_version":"0.164.0","target":"aarch64-apple-darwin","layout_version":1,"release_id":"0.164.0-custom.1","archive":"codex-custom.tar.gz","sha256":"ARCHIVE_SHA256"}
```

`sha256` 必须替换成实际归档的 64 位小写十六进制摘要；`release_id` 必须与归档内 `release.json` 一致。发布新定制修订时更新同一精确兼容 tag 下的描述与资产，不能将不兼容前端放入该 tag。描述文件上限 64 KiB、归档上限 256 MiB；固定归档文件名防止通过描述重定向到任意路径。每个归档成员必须与清单的名称、权限和摘要一致，之后才加载运行组件，统一安装器继续检查隐私、签名、版本和完整资源。描述与归档来自同一发行来源，SHA-256 不提供独立发布者认证。

`bootstrap.sh` 与它取得的 `bootstrap.py` 是初始安装信任入口，来自用户选择的源码地址；它们尚无独立签名或固定外部信任摘要。shell 先检查 Python 3.9+ 和 macOS ARM64，再以 HTTPS 读取 Python 引导器；Python 在请求发行描述与归档前核对 codesign、完整官方包与资源。引导器也列入实际候选的摘要和隐私审查，但不能用归档自述的摘要反向证明最初下载的引导器身份。HTTPS 重定向不得降级到 HTTP。

离线审查使用 `python3 scripts/install.py --archive FILE --sha256 SHA256`；在线审查使用 `python3 scripts/install.py --release-source URL`。`CODEX_CUSTOM_RELEASE_SOURCE` 覆盖默认发行根地址，`CODEX_CUSTOM_BOOTSTRAP_URL` 覆盖 shell 的 Python 引导器地址；仅 HTTPS 或 loopback HTTP 测试来源被允许。测试目录下放置 `official-0.164.0-aarch64-apple-darwin/release.json` 和 `codex-custom.tar.gz`，shell/Python 引导器可置于服务器根目录。这些选项不跳过任何归档或安装校验。
