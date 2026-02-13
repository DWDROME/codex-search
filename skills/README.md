# skills

本目录存放可直接挂载到 Codex 的 Skill 单元（建议作为主调用入口）：

- `search-layer`
- `content-extract`
- `mineru-extract`
- `github-explorer`

建议从仓库根目录执行脚本：

```bash
uv run python "skills/search-layer/scripts/search.py" "多源搜索示例" --mode deep --intent exploratory --num 5
uv run python "skills/content-extract/scripts/content_extract.py" --url "https://zhuanlan.zhihu.com/p/619438846" --max-chars 3000
uv run python "skills/mineru-extract/scripts/mineru_parse_documents.py" --file-sources "https://zhuanlan.zhihu.com/p/619438846" --model-version MinerU-HTML --emit-markdown --max-chars 20000
uv run python "skills/github-explorer/scripts/explore.py" "openai/codex" --format markdown
```
