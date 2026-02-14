# skills

本目录对外统一为 4 个能力 Skill：

- `search-layer`
- `content-extract`
- `mineru-extract`
- `github-explorer`

> 说明：`git-workflow`、`api-availability`、research 回路、decision trace 等属于内部工程支撑，不计入对外能力数。

建议从仓库根目录执行：

```bash
uv run python "skills/search-layer/scripts/search.py" "多源搜索示例" --mode deep --intent exploratory --num 5
uv run python "skills/content-extract/scripts/content_extract.py" --url "https://zhuanlan.zhihu.com/p/619438846" --max-chars 3000
uv run python "skills/mineru-extract/scripts/mineru_parse_documents.py" --file-sources "https://zhuanlan.zhihu.com/p/619438846" --model-version MinerU-HTML --emit-markdown --max-chars 20000
uv run python "skills/github-explorer/scripts/explore.py" "openai/codex" --format markdown
uv run python "skills/api-availability/scripts/api_availability.py" --json
```

如果需要 search-layer 的多轮补证能力：

```bash
uv run python "skills/search-layer/scripts/research.py" "多轮研究示例" --protocol codex_research_v1 --extract-per-round 2
```
