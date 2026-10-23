# Issue tracker: GitHub

规格与任务记录为 [HezLUO/codex-custom 的 GitHub Issues](https://github.com/HezLUO/codex-custom/issues)。

## 操作约定

- 优先使用 GitHub 连接工具；缺少能力时使用 `gh` CLI。
- 所有操作明确指定 `HezLUO/codex-custom`；CLI 使用 `--repo HezLUO/codex-custom`，API 使用对应仓库路径，不依赖本地 remote 推断。
- 技能要求“发布到任务系统”时创建 GitHub Issue；要求“读取任务”时读取 Issue 正文、标签及完整评论。
- 已明确规格与验收条件的任务使用 `ready-for-agent` 标签；其他状态见 [任务状态定义](triage-labels.md)。
- 子任务关联父任务，依赖优先使用 GitHub 原生阻塞关系；接口不支持时，在正文记录 `Part of #<父任务>` 及 `Blocked by: #<阻塞任务>`。
- 使用 CLI 发布多行正文或评论时，先保存临时正文文件，再通过 `--body-file` 传入。

## Pull requests as a triage surface

**PRs as a request surface: no.**

GitHub Issues 与 PR 共用编号；处理裸编号前核对对象类型。
