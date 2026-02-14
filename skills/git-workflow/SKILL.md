---
name: git-workflow
description: >
  规范化 Git 工作流执行器。用于分支创建、变更检查、提交信息生成、推送与 PR 流程。
  默认先做状态快照与风险提示；涉及提交/推送/reset 等操作时必须先得到用户明确确认。
---

# git-workflow（Codex 版）

## 触发时机

当用户提出以下任一诉求时启用：

- "帮我提交这次改动" / "生成 commit message"
- "推送分支并创建 PR"
- "整理当前分支状态" / "看看有哪些改动"
- "rebase / cherry-pick / 处理冲突"

## 强制原则

1. 先读状态，后做变更：先执行仓库快照，再给操作建议。
2. 危险操作必须确认：`git commit` / `git push` / `git rebase` / `git reset` 前必须得到用户明确授权。
3. 默认最小改动：优先 `add` 指定文件，不做无关文件提交。
4. 产出可追溯：提交说明包含目的、影响范围、验证方式。

## 标准流程

### Step 1）读取仓库快照

```bash
uv run python "skills/git-workflow/scripts/git_snapshot.py" --repo "."
```

需要补充时可再执行：

```bash
git status --short
git diff --stat
git log --oneline -10
```

### Step 2）给出提交计划（先说后做）

最少包含：

- 拟提交文件清单
- 提交类型（feat/fix/docs/chore/refactor/test/ci）
- 风险点（是否跨模块、是否有行为变化）
- 验证命令（测试/构建/smoke）

### Step 3）执行提交（需用户确认）

```bash
git add "<file1>" "<file2>"
git commit -m "<type>: <subject>"
```

### Step 4）推送与 PR（需用户确认）

```bash
git push -u origin "<branch>"
gh pr create --base "main" --head "<branch>" --title "<title>" --body "<body>"
```

## 提交信息规范

使用 Conventional Commits，详见：`references/commit-convention.md`

推荐模板：

- 标题：`<type>(<scope>): <subject>`
- 正文：
  - 变更内容（做了什么）
  - 影响范围（可能影响哪里）
  - 验证方式（如何确认）

## 常见场景模板

- "只想提交当前改动"：先 `git_snapshot` -> 生成提交计划 -> 等确认 -> `add + commit`
- "提交并发 PR"：先确认分支与远端 -> 提交 -> 推送 -> `gh pr create`
- "冲突后收敛"：先列冲突文件 -> 分文件修复 -> 重新测试 -> 再提交

## 禁止项

- 未确认就执行 `git commit` / `git push` / `git reset --hard`
- 自动把无关文件打包提交
- 不给验证步骤直接宣称“已完成”
