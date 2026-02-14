from typing import Dict, List


def _bullet_or_none(items: List[str], fallback: str = "未找到") -> str:
    if not items:
        return "- %s" % fallback
    return "\n".join("- %s" % item for item in items)


def render_markdown(report: Dict) -> str:
    if not report.get("ok"):
        lines = [
            "# GitHub Explorer",
            "",
            "**❌ 解析失败**",
            "",
            "- %s" % report.get("error", "未知错误"),
        ]
        for note in report.get("notes") or []:
            lines.append("- note: %s" % note)
        return "\n".join(lines)

    repo = report.get("repo") or {}
    issues = report.get("issues") or []
    commits = report.get("commits") or []
    external = report.get("external") or []
    comparisons = report.get("comparisons") or []
    index_coverage = report.get("index_coverage") or {}
    book = report.get("book") or {}
    confidence = report.get("confidence") or {}

    topics = ", ".join(repo.get("topics") or []) or "未标注"
    license_value = repo.get("license") or "未声明"

    lines: List[str] = []
    lines.append("# [%s](%s)" % (repo.get("full_name", ""), repo.get("url", "")))
    lines.append("")
    lines.append("**🎯 一句话定位**")
    lines.append("")
    lines.append(repo.get("description") or "未提供描述")
    if repo.get("readme_excerpt"):
        lines.append("")
        lines.append("- README 摘要: %s" % repo.get("readme_excerpt"))
    lines.append("")
    lines.append("**⚙️ 核心机制**")
    lines.append("")
    lines.append("- 主要语言: %s" % (repo.get("language") or "未知"))
    lines.append("- 主题标签: %s" % topics)
    lines.append("")
    lines.append("**📊 项目健康度**")
    lines.append("")
    lines.append(
        "- Stars: %s | Forks: %s | Open Issues: %s | License: %s"
        % (repo.get("stars", 0), repo.get("forks", 0), repo.get("open_issues", 0), license_value)
    )
    lines.append("- 最近推送: %s" % (repo.get("pushed_at") or "未知"))
    lines.append("- 阶段判断: %s" % (repo.get("project_stage") or "未知"))
    lines.append("")
    lines.append("**✅ 结果置信度**")
    lines.append("")
    if not confidence:
        lines.append("- 未提供")
    else:
        lines.append(
            "- 综合评分: %s/100 | level=%s | profile=%s"
            % (confidence.get("score", 0), confidence.get("level", "未知"), confidence.get("profile", "deep"))
        )
        if confidence.get("profile_desc"):
            lines.append("- profile说明: %s" % confidence.get("profile_desc"))
        for factor in confidence.get("factors") or []:
            lines.append(
                "- %s: %s/%s [raw=%s/%s] (%s)"
                % (
                    factor.get("name", ""),
                    factor.get("score", 0),
                    factor.get("max_score", 0),
                    factor.get("raw_score", 0),
                    factor.get("raw_max_score", 0),
                    factor.get("detail", ""),
                )
            )
    lines.append("")
    lines.append("**🔥 精选 Issue**")
    lines.append("")
    if not issues:
        lines.append("- 未找到")
    else:
        for issue in issues:
            maintainer_text = "yes" if issue.get("maintainer_participated") else "no"
            maintainer_count = issue.get("maintainer_comment_count", 0)
            risk_tags = ",".join(issue.get("risk_tags") or []) or "一般"
            lines.append(
                "- [#%s %s](%s) | q=%s | comments=%s | maintainer=%s(%s) | risk=%s | state=%s"
                % (
                    issue.get("number"),
                    issue.get("title", "").strip(),
                    issue.get("url", ""),
                    issue.get("quality_score", 0),
                    issue.get("comments", 0),
                    maintainer_text,
                    maintainer_count,
                    risk_tags,
                    issue.get("state", ""),
                )
            )
    lines.append("")
    lines.append("**🛠 最近提交**")
    lines.append("")
    if not commits:
        lines.append("- 未找到")
    else:
        for commit in commits:
            lines.append(
                "- [`%s`](%s) %s (%s)"
                % (commit.get("sha", ""), commit.get("url", ""), commit.get("message", ""), commit.get("date", ""))
            )
    lines.append("")
    lines.append("**📰 外部信号**")
    lines.append("")
    if not external:
        lines.append("- 未找到")
    else:
        for item in external:
            lines.append("- [%s](%s) | source=%s" % (item.get("title", ""), item.get("url", ""), item.get("source", "")))
            if item.get("snippet"):
                lines.append("  - 摘要: %s" % item.get("snippet"))
            extract = item.get("extract") or {}
            if extract:
                lines.append("  - 抓取: ok=%s, engine=%s" % (extract.get("ok"), extract.get("engine", "")))
                if extract.get("summary"):
                    lines.append("  - 提取片段: %s" % extract.get("summary"))
    lines.append("")
    lines.append("**🧭 收录与索引**")
    lines.append("")
    if not index_coverage:
        lines.append("- 未找到")
    else:
        for key, label in [("deepwiki", "DeepWiki"), ("arxiv", "arXiv"), ("zread", "zread")]:
            item = index_coverage.get(key) or {}
            status = item.get("status", "not_found")
            if status == "found":
                lines.append("- %s: found -> %s" % (label, item.get("url", "")))
            else:
                lines.append("- %s: %s" % (label, status))
    lines.append("")
    lines.append("**📚 Book 资料包**")
    lines.append("")
    if not book:
        lines.append("- 未找到")
    else:
        papers = book.get("papers") or []
        if papers:
            for item in papers:
                lines.append(
                    "- [论文] [%s](%s) | source=%s"
                    % (item.get("title", ""), item.get("url", ""), item.get("source", ""))
                )
                if item.get("pdf_url"):
                    lines.append("  - pdf: %s" % item.get("pdf_url", ""))
        else:
            lines.append("- 论文: 未找到")

        deep = book.get("deepwiki") or []
        if deep:
            for item in deep:
                lines.append("- [DeepWiki] [%s](%s)" % (item.get("title", ""), item.get("url", "")))
        else:
            lines.append("- DeepWiki: 未找到")

        zread = book.get("zread") or []
        if zread:
            for item in zread:
                lines.append("- [zread] [%s](%s)" % (item.get("title", ""), item.get("url", "")))
        else:
            lines.append("- zread: 未找到")
    lines.append("")
    lines.append("**🆚 竞品对比**")
    lines.append("")
    if not comparisons:
        lines.append("- 未找到")
    else:
        for row in comparisons:
            lines.append("- [%s](%s) | source=%s | evidence=%s" % (
                row.get("repo", ""),
                row.get("url", ""),
                row.get("source", ""),
                row.get("evidence_title", ""),
            ))
    lines.append("")
    lines.append("**💬 我的判断**")
    lines.append("")
    stage = repo.get("project_stage") or ""
    if stage in {"快速迭代", "稳定活跃"}:
        lines.append("- 项目处于活跃阶段，适合持续跟踪并投入验证。")
    elif stage == "维护模式":
        lines.append("- 项目进入维护阶段，适合稳定场景，不建议押注激进特性。")
    else:
        lines.append("- 活跃度一般，建议先做小范围 PoC 再决定是否深度投入。")
    lines.append("- 建议结合精选 Issue 与外部信号判断真实落地成本。")

    notes = report.get("notes") or []
    if notes:
        lines.append("")
        lines.append("**🧾 执行注记**")
        lines.append("")
        lines.append(_bullet_or_none(["note: %s" % note for note in notes], fallback="无"))

    return "\n".join(lines)
