import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from ..contracts import ExtractionArtifacts, ExtractionResponse


def _default_mineru_wrapper(project_root: Path) -> Path:
    return project_root / "skills" / "mineru-extract" / "scripts" / "mineru_parse_documents.py"


def run_mineru_wrapper(
    url: str,
    wrapper_path: Optional[str],
    token: Optional[str],
    api_base: Optional[str],
    workspace: Optional[str],
    max_chars: int = 20000,
    language: str = "ch",
    model_version: str = "MinerU-HTML",
) -> ExtractionResponse:
    project_root = Path(__file__).resolve().parents[3]
    target = Path(wrapper_path) if wrapper_path else _default_mineru_wrapper(project_root)

    if not target.exists():
        return ExtractionResponse(
            ok=False,
            source_url=url,
            engine="mineru",
            notes=["mineru_wrapper_not_found:%s" % target],
            sources=[url],
        )

    cmd = [
        sys.executable,
        str(target),
        "--file-sources",
        url,
        "--model-version",
        model_version,
        "--language",
        language,
        "--emit-markdown",
        "--max-chars",
        str(max_chars),
    ]

    env = os.environ.copy()
    if token:
        env["MINERU_TOKEN"] = token
    if api_base:
        env["MINERU_API_BASE"] = api_base
    if workspace:
        env["CODEX_WORKSPACE"] = workspace
        env["MINERU_WORKSPACE"] = workspace
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)

    try:
        payload = json.loads(proc.stdout)
    except Exception:
        return ExtractionResponse(
            ok=False,
            source_url=url,
            engine="mineru",
            notes=["mineru_non_json_output", "returncode:%s" % proc.returncode, (proc.stdout or "")[:500]],
            sources=[url],
        )

    items = payload.get("items") or []
    if not items:
        return ExtractionResponse(
            ok=False,
            source_url=url,
            engine="mineru",
            notes=[
                "mineru_empty_items",
                "returncode:%s" % proc.returncode,
                json.dumps(payload.get("errors") or [], ensure_ascii=False)[:500],
            ],
            sources=[url],
        )

    first = items[0]
    sources = [url]
    if first.get("full_zip_url"):
        sources.append(first["full_zip_url"])
    if first.get("markdown_path"):
        sources.append(first["markdown_path"])

    return ExtractionResponse(
        ok=True,
        source_url=url,
        engine="mineru",
        markdown=first.get("markdown"),
        artifacts=ExtractionArtifacts(
            out_dir=first.get("out_dir"),
            markdown_path=first.get("markdown_path"),
            zip_path=first.get("zip_path"),
            task_id=first.get("task_id"),
            cache_key=first.get("cache_key"),
        ),
        sources=sources,
        notes=["fallback:mineru_parse_documents"],
    )
