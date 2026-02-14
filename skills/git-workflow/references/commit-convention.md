# Commit Convention（简版）

## 类型（type）

- `feat`: 新功能
- `fix`: 缺陷修复
- `docs`: 文档改动
- `chore`: 维护性改动（不影响业务逻辑）
- `refactor`: 重构（不改变外部行为）
- `test`: 测试相关
- `ci`: CI/CD 或脚本流程调整

## 标题格式

```text
<type>(<scope>): <subject>
```

示例：

- `feat(search): add request-level model routing`
- `fix(extract): handle mineru timeout fallback`
- `docs(readme): clarify skills-first workflow`

## 编写建议

- 标题使用现在时，长度建议 <= 72 字符。
- 只描述一件核心事，不把多个主题塞进同一个提交。
- 如有破坏性变化，在正文明确写出兼容风险与迁移步骤。
