from typing import Dict, List
from urllib.parse import urlparse


def _bullet_or_none(items: List[str], fallback: str = "未找到") -> str:
    if not items:
        return "- %s" % fallback
    return "\n".join("- %s" % item for item in items)


_GLOBAL_COMMUNITY_HOSTS = {
    "x.com",
    "twitter.com",
    "reddit.com",
    "news.ycombinator.com",
    "medium.com",
    "dev.to",
}
_CN_COMMUNITY_HOSTS = {
    "linux.do",
    "v2ex.com",
    "zhihu.com",
    "zhuanlan.zhihu.com",
    "juejin.cn",
    "mp.weixin.qq.com",
    "weixin.qq.com",
    "xiaohongshu.com",
    "bilibili.com",
    "csdn.net",
}
_NEGATIVE_HINTS = (
    "bug",
    "issue",
    "problem",
    "limitation",
    "risk",
    "failure",
    "broken",
    "unstable",
    "不稳定",
    "问题",
    "缺陷",
    "风险",
    "失败",
    "翻车",
)


def _host(url: str) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower()
    except Exception:
        return ""


def _is_host_in(host: str, candidates: set[str]) -> bool:
    if not host:
        return False
    return any(host == item or host.endswith("." + item) for item in candidates)


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
    lines.append("**📰 社区声量**")
    lines.append("")

    global_rows = []
    cn_rows = []
    for item in external:
        host = _host(item.get("url", ""))
        if _is_host_in(host, _CN_COMMUNITY_HOSTS):
            cn_rows.append(item)
        elif _is_host_in(host, _GLOBAL_COMMUNITY_HOSTS):
            global_rows.append(item)

    lines.append("**X / Reddit / 国际社区**")
    lines.append("")
    if not global_rows:
        lines.append("- 未找到（已尝试 X/Reddit/HN/Medium/Dev.to）")
        lines.append("- 未找到（可补充关键词后再检索）")
        lines.append("- 未找到（可放宽 freshness）")
    else:
        for item in global_rows[:3]:
            date = item.get("published_date") or "日期未知"
            lines.append("- [%s](%s)（%s）— %s" % (
                item.get("title", ""),
                item.get("url", ""),
                date,
                item.get("snippet", "") or "无摘要",
            ))
        for _ in range(max(0, 3 - len(global_rows[:3]))):
            lines.append("- 未找到（该类社区样本不足）")

    lines.append("")
    lines.append("**中文社区**")
    lines.append("")
    if not cn_rows:
        lines.append("- 未找到（已尝试 Linux.do/V2EX/知乎/掘金/公众号）")
        lines.append("- 未找到（可补充中文关键词再检索）")
        lines.append("- 未找到（可改用 content-extract 强化抓取）")
    else:
        for item in cn_rows[:3]:
            date = item.get("published_date") or "日期未知"
            lines.append("- [%s](%s)（%s）— %s" % (
                item.get("title", ""),
                item.get("url", ""),
                date,
                item.get("snippet", "") or "无摘要",
            ))
        for _ in range(max(0, 3 - len(cn_rows[:3]))):
            lines.append("- 未找到（该类社区样本不足）")
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
        lines.append("- 未找到")
        lines.append("- 未找到")
        lines.append("- 未找到")
    else:
        shown = 0
        for row in comparisons:
            lines.append("- [%s](%s) | source=%s | evidence=%s" % (
                row.get("repo", ""),
                row.get("url", ""),
                row.get("source", ""),
                row.get("evidence_title", ""),
            ))
            shown += 1
            if shown >= 4:
                break
        for _ in range(max(0, 4 - shown)):
            lines.append("- 未找到（竞品样本不足）")
    lines.append("")
    lines.append("**❎ 反对证据**")
    lines.append("")
    negatives: List[str] = []
    seen_negative = set()
    for issue in issues:
        risk_tags = ",".join(issue.get("risk_tags") or [])
        if risk_tags and risk_tags != "一般":
            key = issue.get("url", "")
            if key and key not in seen_negative:
                negatives.append(
                    "- [Issue #%s %s](%s) — risk=%s"
                    % (issue.get("number"), issue.get("title", ""), issue.get("url", ""), risk_tags)
                )
                seen_negative.add(key)
        if len(negatives) >= 2:
            break
    if len(negatives) < 2:
        for item in external:
            text = ("%s %s" % (item.get("title", ""), item.get("snippet", ""))).lower()
            if not any(hint in text for hint in _NEGATIVE_HINTS):
                continue
            key = item.get("url", "")
            if key and key not in seen_negative:
                negatives.append(
                    "- [%s](%s) — %s" % (item.get("title", ""), item.get("url", ""), item.get("snippet", "") or "negative signal")
                )
                seen_negative.add(key)
            if len(negatives) >= 2:
                break
    if not negatives:
        lines.append("- 未找到（已检索到的证据未形成明确反例）")
        lines.append("- 未找到（可扩展关键词：failure/risk/bug/limitation）")
    else:
        lines.extend(negatives[:2])
        for _ in range(max(0, 2 - len(negatives[:2]))):
            lines.append("- 未找到（反对证据样本不足）")
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
