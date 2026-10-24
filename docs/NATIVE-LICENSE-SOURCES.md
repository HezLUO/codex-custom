# 原生发行包的依赖许可原文

本记录解释各平台构建中，依赖包未附许可证文件时所采用的原始资料。它补充发行包内的 `DEPENDENCY-NOTICES.txt`，不替代各依赖原有条款，也不将保守的构建依赖清单解释为精确的最终链接清单。

调查按精确版本进行：registry 依赖先读取发布包的 `.cargo_vcs_info.json`，再到该提交的第一方仓库查找许可证；Git 依赖直接使用锁定的提交。工作区根许可证适用于相应子 crate 时，复制实际根文件，不把指向它的符号链接内容当成许可证。所有下表摘要均为下载原始字节的 SHA-256。

## 恢复的原文

下表每个链接均固定到具体 Git 提交。上游原始署名随完整文件保留；不使用 Cargo 作者信息猜测版权持有人或年份。

| 精确依赖版本 | 第一方原文 | 原始文件 SHA-256 |
| --- | --- | --- |
| `clipboard-win@5.4.1` | [原文](https://raw.githubusercontent.com/DoumanAsh/clipboard-win/3b27cf2bfd1adcfa6e0264eb51c1025ddaf0f342/LICENSE) | `c9bff75738922193e67fa726fa225535870d2aa1059f91452c411736284ad566` |
| `defmt-parser@1.0.0` | [原文](https://raw.githubusercontent.com/knurling-rs/defmt/4a8cdb44891ed57b8ff5a023b6bec7137c48708f/LICENSE-MIT) | `2710a622a896bba67356913d4d0492cab5465f61b2ecce6d880aeb483834fb50` |
| `defmt-parser@1.0.0` | [原文](https://raw.githubusercontent.com/knurling-rs/defmt/4a8cdb44891ed57b8ff5a023b6bec7137c48708f/LICENSE-APACHE) | `8173d5c29b4f956d532781d2b86e4e30f83e6b7878dce18c919451d6ba707c90` |
| `defmt@0.3.100` | [原文](https://raw.githubusercontent.com/knurling-rs/defmt/f6decae6e09d1216aff052aa0733a6b5e632a100/LICENSE-MIT) | `2710a622a896bba67356913d4d0492cab5465f61b2ecce6d880aeb483834fb50` |
| `defmt@0.3.100` | [原文](https://raw.githubusercontent.com/knurling-rs/defmt/f6decae6e09d1216aff052aa0733a6b5e632a100/LICENSE-APACHE) | `8173d5c29b4f956d532781d2b86e4e30f83e6b7878dce18c919451d6ba707c90` |
| `difflib@0.4.0` | [原文](https://raw.githubusercontent.com/DimaKudosh/difflib/f035fb8e656f27119e23eca9d5b996df14f3885e/LICENSE) | `6725d1437fc6c77301f2ff0e7d52914cf4f9509213e1078dc77d9356dbe6eac5` |
| `dispatch2@0.3.0` | [原文](https://raw.githubusercontent.com/madsmtm/objc2/e68410e22a2d29d5f37a0b4c1b7e8e194808eade/LICENSE.md) | `7f976f7e9cb2d87df7230606feb932c3f21ac0e664045a775b600046ff850c54` |
| `h3-quinn@0.0.10` | [原文](https://raw.githubusercontent.com/hyperium/h3/e07e69412876f7e26f026bd75a48b2704d8c8283/LICENSE) | `a0d039cdafe68f363893abddb5e4d50dbe6f8b56611e2650aaab4237103285f1` |
| `h3@0.0.8` | [原文](https://raw.githubusercontent.com/hyperium/h3/e07e69412876f7e26f026bd75a48b2704d8c8283/LICENSE) | `a0d039cdafe68f363893abddb5e4d50dbe6f8b56611e2650aaab4237103285f1` |
| `linux-keyutils@0.2.4` | [原文](https://raw.githubusercontent.com/landhb/linux-keyutils/2e81f726ffd3c0165e11fcdbde279b5d8638f47d/README.md) | `60eaaa21859394c2a1679d47763c4d2c31b3fdab7de327ac72f4b4244cac5695` |
| `mxc-sdk@1.0.0` | [原文](https://raw.githubusercontent.com/microsoft/mxc/b21120168d70befe12356411423266bfef168446/LICENSE.md) | `d9a1b1e30d633d5732ea18e3cba9538d293ebc53e1a9e4e96ab739e0c5c4f1cb` |
| `nucleo-matcher@0.3.1` | [原文](https://raw.githubusercontent.com/helix-editor/nucleo/4253de9faabb4e5c6d81d946a5e35a90f87347ee/LICENSE) | `1f256ecad192880510e84ad60474eab7589218784b9a50bc7ceee34c2b91f1d5` |
| `objc2-io-surface@0.3.2` | [原文](https://raw.githubusercontent.com/madsmtm/objc2/7b1abfd750a2cacaea71d6a56ecfb83cb7de560b/LICENSE.md) | `7f976f7e9cb2d87df7230606feb932c3f21ac0e664045a775b600046ff850c54` |
| `ratatui-termina@0.1.0` | [原文](https://raw.githubusercontent.com/ratatui/ratatui/e665c36cb14752a61cd777fbd06dbef8474f2add/LICENSE) | `50eb43e8d742c9c61a9391e42b2184fce54dbd1893a1bb1c85b8c9ee217ab1f5` |
| `rmcp-macros@3.5.1` | [原文](https://raw.githubusercontent.com/modelcontextprotocol/rust-sdk/98a54789b80110ad210495c4ad845c89e1980471/LICENSE) | `0382b0057770ca05e9c350a50aa3b1c1fea84da0bc81d723bf00b9aa841be58a` |
| `rmcp@3.5.1` | [原文](https://raw.githubusercontent.com/modelcontextprotocol/rust-sdk/98a54789b80110ad210495c4ad845c89e1980471/LICENSE) | `0382b0057770ca05e9c350a50aa3b1c1fea84da0bc81d723bf00b9aa841be58a` |
| `runfiles@0.1.0` | [原文](https://raw.githubusercontent.com/dzbarsky/rules_rust/b56cbaa8465e74127f1ea216f813cd377295ad81/LICENSE.txt) | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| `tracelogging@1.2.3` | [原文](https://raw.githubusercontent.com/microsoft/tracelogging/4d3c8b02da568d34daf977db7052a819ab4b18ec/LICENSE) | `7dc541691bf807a74bf7c1090662712af131571f9be8fb8a6f6c1e6dbfbe2fbb` |
| `tracelogging_macros@1.2.3` | [原文](https://raw.githubusercontent.com/microsoft/tracelogging/4d3c8b02da568d34daf977db7052a819ab4b18ec/LICENSE) | `7dc541691bf807a74bf7c1090662712af131571f9be8fb8a6f6c1e6dbfbe2fbb` |
| `vtparse@0.6.2` | [原文](https://raw.githubusercontent.com/wez/wezterm/edeae72b5fc55c7fa4aa1d08bbefd08c5493f757/LICENSE.md) | `37db33bbbd7348969eda397b89a16f252d56c1ca7481b6ccaf56ccdcbab5dcca` |
| `wezterm-input-types@0.1.0` | [原文](https://raw.githubusercontent.com/wez/wezterm/d5ca5509b95edc31291ba29bd1fcbf3f0b12c92d/LICENSE.md) | `37db33bbbd7348969eda397b89a16f252d56c1ca7481b6ccaf56ccdcbab5dcca` |
| `winsplit@0.1.0` | [原文](https://raw.githubusercontent.com/chipsenkbeil/winsplit-rs/691e800ac384bc7fc815ca55d1dd2b09b1f15d96/README.md) | `39bb1a6d7befd101a9f8228db3b2deab823042b54dc82a410534cb68ba93edbc` |

## 需要保留的具体解释

`h3 0.0.8` 与 `h3-quinn 0.0.10` 的子目录许可证是指向工作区根文件的链接。映射使用同一提交的完整根 `LICENSE`，而不是 `../LICENSE` 这几个字符。`rmcp 3.5.1` 与 `rmcp-macros 3.5.1` 同理：使用固定提交的根许可证，完整保留其 MIT 到 Apache-2.0 过渡声明及后面的所有条款，不能仅凭 manifest 的 Apache 声明删除仍受 MIT 约束部分的说明。[h3 子目录文件](https://github.com/hyperium/h3/blob/e07e69412876f7e26f026bd75a48b2704d8c8283/h3/LICENSE)、[rmcp 子目录文件](https://github.com/modelcontextprotocol/rust-sdk/blob/98a54789b80110ad210495c4ad845c89e1980471/crates/rmcp/LICENSE)。

`mxc-sdk` 在此记录中的实际版本是 `1.0.0`，来源是锁定的 Microsoft mxc 提交，许可证为 MIT；`rmcp` 和 `rmcp-macros` 是 `3.5.1`，来源是锁定的 MCP Rust SDK 提交。不能把外层 Codex 工作区的版本和许可证继承给这些 Git 依赖。[mxc-sdk 原文](https://github.com/microsoft/mxc/blob/b21120168d70befe12356411423266bfef168446/LICENSE.md)、[MCP 原文](https://github.com/modelcontextprotocol/rust-sdk/blob/98a54789b80110ad210495c4ad845c89e1980471/LICENSE)。

`difflib 0.4.0` 的旧发布包没有 VCS 元数据，不能假定仓库最新提交就是打包来源。本次核对固定提交 `f035fb8e656f27119e23eca9d5b996df14f3885e` 的 manifest 版本为 `0.4.0`，六个打包 Rust 源文件与对应发布包逐字相同，因而使用该源码树保留的 MIT 原文。原许可证的署名是 Kevin B. Knapp，与 manifest 中的作者姓名不同；两类资料分别保留，不互相替换。[该提交](https://github.com/DimaKudosh/difflib/tree/f035fb8e656f27119e23eca9d5b996df14f3885e)、[原始许可证](https://github.com/DimaKudosh/difflib/blob/f035fb8e656f27119e23eca9d5b996df14f3885e/LICENSE)。

`clipboard-win 5.4.1` 的发布包省略许可证，但同一 VCS 提交有完整 Boost Software License 1.0 原文；使用这一原文，不能把它视作 MIT。[原文](https://github.com/DoumanAsh/clipboard-win/blob/3b27cf2bfd1adcfa6e0264eb51c1025ddaf0f342/LICENSE)。两个 `tracelogging` crate 的 VCS 提交相同，使用该工作区保留 Microsoft 署名的完整 MIT 文本。[原文](https://github.com/microsoft/tracelogging/blob/4d3c8b02da568d34daf977db7052a819ab4b18ec/LICENSE)。

## 显式选择 Apache-2.0 的原始声明

以下四项保留原始声明文件与发布的作者元数据，并另外附上完整 Apache-2.0 条款。声明文件本身并非一份完整的许可证全文。构建收集器须校验实际 manifest 确实允许 Apache-2.0，再应用此选择；不能据此对其他未知许可证作通用替代。

| 依赖 | 可核实的原始声明 | 本次处理 |
| --- | --- | --- |
| `dispatch2 0.3.0` | 同一提交的工作区 `LICENSE.md` 明确说明该 crate 可选 Zlib、Apache-2.0 或 MIT | 保留完整工作区说明，选择 Apache-2.0 并附完整条款 |
| `objc2-io-surface 0.3.2` | 同一提交的工作区 `LICENSE.md` 明确说明适用的三选一许可 | 同上 |
| `linux-keyutils 0.2.4` | 精确提交的 README 明确允许 Apache-2.0 或 MIT，并链接 Apache 原文 | 保留 README 原声明，选择 Apache-2.0 并附完整条款 |
| `winsplit 0.1.0` | 精确提交的 README 明确允许 Apache-2.0 或 MIT，并链接 Apache 原文 | 同上 |

`dispatch2` 与 `objc2-io-surface` 工作区中只有原始 `LICENSE.md` 说明，没有额外许可证全文或 NOTICE 文件。该说明还记录了 Apple SDK 派生绑定的背景，复制时完整保留，不删除上游说明。[dispatch2 所属工作区](https://github.com/madsmtm/objc2/blob/e68410e22a2d29d5f37a0b4c1b7e8e194808eade/LICENSE.md)、[IOSurface 所属工作区](https://github.com/madsmtm/objc2/blob/7b1abfd750a2cacaea71d6a56ecfb83cb7de560b/LICENSE.md)。

`linux-keyutils` 精确提交的完整源树与发布包均没有单独的 LICENSE、NOTICE 或版权头；`winsplit` 精确提交的完整目录和发布包也没有这些文本。本记录保留确实存在的许可声明，并附上它们明确允许的 Apache-2.0 完整条款；没有编造一个缺失的版权行，也没有把声明为双许可证的项目标成“无许可证”。[linux-keyutils 原声明](https://github.com/landhb/linux-keyutils/blob/2e81f726ffd3c0165e11fcdbde279b5d8638f47d/README.md)、[winsplit 原声明](https://github.com/chipsenkbeil/winsplit-rs/blob/691e800ac384bc7fc815ca55d1dd2b09b1f15d96/README.md)、[Apache-2.0 完整条款](https://www.apache.org/licenses/LICENSE-2.0)。

## fxhash 的原始行注释版权头

`fxhash 0.2.1` 的发布包没有单独的许可证文件及 VCS 元数据，但 `lib.rs` 开头已有 Rust Project Developers 的原始版权声明，并明确提供 Apache-2.0 或 MIT 选项。收集器应读取实际发布包内的 `//` 连续行注释，保留原始版权头，再附完整的 Apache-2.0 条款。不能仅支持 `/* ... */` 头而漏掉这类资料。[精确版本源码](https://docs.rs/crate/fxhash/0.2.1/source/lib.rs)、[精确发布包](https://static.crates.io/crates/fxhash/fxhash-0.2.1.crate)。

没有将现存 fxhash 仓库最新提交伪装成该发布包的精确来源；其 `lib.rs` 与发布包存在差异，因此这里直接使用发布包本身的原始版权头。该处理不需要补造一个当前仓库版权年，也不需要让用户自行判断署名。

## 范围与验证边界

本记录新增 20 个精确依赖版本的原文映射，另为 `fxhash 0.2.1` 指定原始行注释头的处理，共对应此次补充调查的 21 项缺口。已有其他精确版本证据继续单独使用，不在本次重复调查。所有文本来自第一方源码、精确发布包或它们明确指向的许可条款；原始下载的字节摘要可供复核。

这份记录说明资料来源及收集方式，不宣称新的平台已经构建成功，也不构成对每个依赖所有贡献者权属的独立审计。发行包仍需运行各平台的许可收集和完整性验证，以实际产物为准。

## 四个仅声明 MIT 的 Objective-C crate

对旧映射进一步复核后，以下四项需要单独处理。它们的工作区 `LICENSE.md` 明确把这些 crate 列在 MIT 一组；该文件是许可说明，未提供 MIT 完整条款或原始版权行。这四项不能沿用其他 Objective-C crate 的 Apache-2.0 选择。

| 精确依赖版本 | 与发布包 VCS 记录对应的原始说明 | 许可选择 |
| --- | --- | --- |
| `block2 0.6.2` | [固定提交的 LICENSE.md](https://github.com/madsmtm/objc2/blob/b4167b582b2f75f9a1be75495c41b765344fd03c/LICENSE.md) | MIT |
| `objc2 0.6.3` | [固定提交的 LICENSE.md](https://github.com/madsmtm/objc2/blob/b4167b582b2f75f9a1be75495c41b765344fd03c/LICENSE.md) | MIT |
| `objc2-encode 4.1.0` | [固定提交的 LICENSE.md](https://github.com/madsmtm/objc2/blob/8d214f5477365ffcbcbb7de058c86ed9a518efb7/LICENSE.md) | MIT |
| `objc2-foundation 0.3.2` | [固定提交的 LICENSE.md](https://github.com/madsmtm/objc2/blob/7b1abfd750a2cacaea71d6a56ecfb83cb7de560b/LICENSE.md) | MIT |

上述三份固定提交的说明原文内容相同，SHA-256 均为 `7f976f7e9cb2d87df7230606feb932c3f21ac0e664045a775b600046ff850c54`。本次复用已下载的原始说明和精确版本发布包缓存，检查四个包合计 392 个文件的文件名及可读 Rust、Markdown、文本内容：未发现独立的 LICENSE、NOTICE、版权文件，亦未找到原始版权声明或完整 MIT 授权头。这是对已检查资料的事实记录，不表示作者没有版权，也不证明其他历史资料中不存在署名。

发行包应保留原工作区说明、实际 manifest 提供的作者元数据，并附完整 MIT 许可及免责声明；不得依据作者字段或 Git 时间制造一个“Copyright + 年份 + 姓名”的行。映射对这四个具体版本明确标记 `selected_license: "MIT"`，收集器必须先核实实际声明允许 MIT，再补充条款。MIT 许可正文使用规范的授权及免责声明部分，不从其他项目借用其版权署名。[MIT 规范条款](https://opensource.org/license/mit)。

`objc2-foundation` 的 `src/copying.rs` 和 `src/tests/copying.rs` 是实现、测试 `NSCopying` 的普通源码，并非 COPYING 许可证。不能仅凭文件名包含 `copying` 就将它们算作已找到完整许可。附上原始声明后仍需执行上述 MIT 条款补充。
