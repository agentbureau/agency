from dataclasses import dataclass, field
import httpx
import logging

log = logging.getLogger(__name__)


@dataclass
class StatusEntry:
    id: str
    severity: str
    message: str
    url: str | None = None
    affects_versions: list[str] = field(default_factory=list)
    fixed_in_version: str | None = None


@dataclass
class SystemStatus:
    homepool_enabled: bool = False
    homepool_endpoint: str | None = None
    notices: list[StatusEntry] = field(default_factory=list)


@dataclass
class StatusFile:
    latest_version: str | None = None
    min_supported_version: str | None = None
    updates: list[StatusEntry] = field(default_factory=list)
    bugs_reported: list[StatusEntry] = field(default_factory=list)
    bugs_fixed: list[StatusEntry] = field(default_factory=list)
    primitives: list[StatusEntry] = field(default_factory=list)
    research: list[StatusEntry] = field(default_factory=list)
    system: SystemStatus = field(default_factory=SystemStatus)


def _parse_entries(raw: list | None) -> list[StatusEntry]:
    if not isinstance(raw, list):
        return []
    entries = []
    for item in raw:
        if not isinstance(item, dict) or "id" not in item or "message" not in item:
            continue  # skip silently
        entries.append(StatusEntry(
            id=item["id"],
            severity=item.get("severity", "info"),
            message=item["message"],
            url=item.get("url"),
            affects_versions=item.get("affects_versions", []),
            fixed_in_version=item.get("fixed_in_version"),
        ))
    return entries


def _parse_system(raw: dict | None) -> SystemStatus:
    if not isinstance(raw, dict):
        return SystemStatus()
    return SystemStatus(
        homepool_enabled=bool(raw.get("homepool_enabled", False)),
        homepool_endpoint=raw.get("homepool_endpoint"),
        notices=_parse_entries(raw.get("notices")),
    )


def parse_status_file(data) -> "StatusFile | None":
    if not isinstance(data, dict):
        return None
    try:
        return StatusFile(
            latest_version=data.get("latest_version"),
            min_supported_version=data.get("min_supported_version"),
            updates=_parse_entries(data.get("updates")),
            bugs_reported=_parse_entries(data.get("bugs_reported")),
            bugs_fixed=_parse_entries(data.get("bugs_fixed")),
            primitives=_parse_entries(data.get("primitives")),
            research=_parse_entries(data.get("research")),
            system=_parse_system(data.get("system")),
        )
    except Exception:
        log.warning("Status file parse failed; skipping.")
        return None


def fetch_status(url: str) -> "StatusFile | None":
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        return parse_status_file(resp.json())
    except Exception:
        log.debug("Status file fetch failed; continuing without it.")
        return None
