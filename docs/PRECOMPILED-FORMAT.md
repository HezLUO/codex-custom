# 本地预编译候选格式

`python3 scripts/release_artifact.py package` 从单个前端、独立来源记录及依赖通知生成 tar.gz 与 SHA-256 文件。归档外保留原始证据，不能把现有安装目录作为输入目录。`inspect` 检查归档结构、隐私规则、元数据与逐文件摘要，不执行归档中的程序；安装器必须在独立暂存目录另行调用 `verify_binary`，核对 Mach-O arm64、严格 ad hoc 签名及 `codex-cli 0.164.0`。

```sh
python3 scripts/release_artifact.py package \
  --binary ../candidate/codex --provenance ../candidate/provenance.json \
  --dependency-notices ../candidate/DEPENDENCY-NOTICES.txt \
  --release-id 0.164.0-custom.1 --output ../candidate/codex-custom.tar.gz
python3 scripts/release_artifact.py inspect ../candidate/codex-custom.tar.gz
```

格式版本为 `release.json` 中的 `schema: 1`。必要字段为 `release_id`、`official_version`、`target`、`layout_version`、`source_commit`、`patch_sha256`、`signing`、`provenance` 与 `members`。首版固定官方 0.164.0、aarch64-apple-darwin、standalone layout 1。`members` 对每个有效负载记录 SHA-256 与 Unix mode；不包含清单本身，以免递归。打包器生成全归档 SHA-256 sidecar。安装下载需要可信传输及明确发行定位；同来源摘要只是完整性检查，不能独立证明发布者身份。

必要成员为 `bin/codex`、`LICENSE`、`NOTICE`、`DEPENDENCY-NOTICES.txt`。安装阶段可以明确加入 `runtime/precompiled.py`、`runtime/release_artifact.py`、`runtime/update-codex-custom.py` 和 `bootstrap.sh`，每个组件同样列入摘要及隐私审查。拒绝未声明成员、目录、链接、重复成员、PAX 扩展、未知权限、越界名称和单文件超限。安装器在读取总下载量时还应限制归档大小。官方 helper 与语音资源从用户本机匹配官方包复制，不放进归档。

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
