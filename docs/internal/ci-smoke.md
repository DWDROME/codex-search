# CI/Smoke 组件说明

## 组件定位

`ci/smoke` 负责回归校验与自动化执行。

主入口：

- 本地 smoke：`scripts/smoke_phase6.sh`
- CI hook：`scripts/ci_smoke_hook.sh`
- 脱敏快照：`scripts/masked_env_snapshot.py`
- 工作流：`.github/workflows/ci-smoke.yml`

---

## 本地命令

完整 smoke：

```bash
./scripts/smoke_phase6.sh
```

CI hook 本地模拟：

```bash
./scripts/ci_smoke_hook.sh
```

强制模式：

```bash
CI_SMOKE_MODE=offline ./scripts/ci_smoke_hook.sh
CI_SMOKE_MODE=online ./scripts/ci_smoke_hook.sh
```

---

## 关键环境变量

- `CI_SMOKE_MODE=auto|offline|online`
- `CI_REPORT_DIR`（可选，覆盖报告输出目录）
- `CONFIDENCE_PROFILE`（影响 explore 校验默认 profile）
- `CODEX_SEARCH_CONFIG`（可选，指定 YAML 配置路径）

---

## 自动决策逻辑（auto）

`ci_smoke_hook.sh` 会判断：

1. 调用 `check_api_config.py --json` 读取“有效配置”
2. 判断 `search_ready` 与 `extract_ready`

两者都满足则 `online`，否则降级 `offline`。

---

## 产物文件

默认目录：`.runtime/ci-reports`

- `masked_env_snapshot.json`：脱敏环境快照
- `config_check.json`：配置体检结果（含 `search_ready` / `extract_ready`）
- `ci_smoke_decision.json`：本次模式决策
- `ci_smoke.log`：执行日志

---

## 参考

- 详细阶段说明：`docs/internal/phase8-ci-smoke-hook.md`
