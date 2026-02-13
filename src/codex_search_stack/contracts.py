from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class SearchBudget:
    max_calls: int = 6
    max_tokens: int = 12000
    max_latency_ms: int = 30000


@dataclass
class SearchRequest:
    query: str
    mode: str = "deep"
    intent: Optional[str] = None
    freshness: Optional[str] = None
    limit: int = 5
    boost_domains: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=lambda: ["auto"])
    model: Optional[str] = None
    model_profile: str = "balanced"
    risk_level: str = "medium"
    budget: SearchBudget = field(default_factory=SearchBudget)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    source: str = ""
    published_date: str = ""
    score: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SearchResponse:
    mode: str
    query: str
    intent: Optional[str] = None
    freshness: Optional[str] = None
    count: int = 0
    results: List[SearchResult] = field(default_factory=list)
    answer: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    decision_trace: Optional["DecisionTrace"] = None

    def to_dict(self) -> Dict:
        data = asdict(self)
        data["results"] = [item.to_dict() for item in self.results]
        if self.decision_trace is not None:
            data["decision_trace"] = self.decision_trace.to_dict()
        return data


@dataclass
class ExtractionArtifacts:
    out_dir: Optional[str] = None
    markdown_path: Optional[str] = None
    zip_path: Optional[str] = None
    task_id: Optional[str] = None
    cache_key: Optional[str] = None


@dataclass
class ExtractionResponse:
    ok: bool
    source_url: str
    engine: str
    markdown: Optional[str] = None
    artifacts: ExtractionArtifacts = field(default_factory=ExtractionArtifacts)
    sources: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    decision_trace: Optional["DecisionTrace"] = None

    def to_dict(self) -> Dict:
        data = asdict(self)
        data["artifacts"] = asdict(self.artifacts)
        if self.decision_trace is not None:
            data["decision_trace"] = self.decision_trace.to_dict()
        return data


@dataclass
class ExtractRequest:
    url: str
    force_mineru: bool = False
    max_chars: int = 20000
    strategy: str = "auto"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExploreRequest:
    target: str
    issues_limit: int = 5
    commits_limit: int = 5
    external_limit: int = 8
    extract_top: int = 2
    with_extract: bool = True
    confidence_profile: str = "deep"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionEvent:
    stage: str
    decision: str
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionTrace:
    request_id: str = field(default_factory=lambda: uuid4().hex[:12])
    policy_version: str = "policy.v1"
    events: List[DecisionEvent] = field(default_factory=list)

    def add_event(self, stage: str, decision: str, reason: str = "", metadata: Optional[Dict[str, Any]] = None) -> None:
        self.events.append(
            DecisionEvent(
                stage=stage,
                decision=decision,
                reason=reason,
                metadata=metadata or {},
            )
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "policy_version": self.policy_version,
            "events": [event.to_dict() for event in self.events],
        }
