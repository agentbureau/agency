"""Infrastructure reference integrity tests (Issue 16, v1.2.4).

Prevents dead URLs, wrong repos, placeholder values in shipped code.
"""
import ast
import re
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent / "src" / "agency"
CANONICAL_ORG = "agentbureau"
PLACEHOLDER_PATTERNS = re.compile(r"https?://[^\s\"']*\[[^\]]+\]")


def _collect_python_files():
    return list(SRC_DIR.rglob("*.py"))


def _extract_string_literals(filepath: Path) -> list[str]:
    source = filepath.read_text()
    tree = ast.parse(source)
    strings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.append(node.value)
    return strings


def test_no_placeholders_in_urls():
    """No URL string contains [placeholder] patterns."""
    violations = []
    for pyfile in _collect_python_files():
        for s in _extract_string_literals(pyfile):
            if PLACEHOLDER_PATTERNS.search(s):
                violations.append(f"{pyfile.relative_to(SRC_DIR.parent.parent)}: {s[:80]}")
    assert not violations, f"Placeholder values in URLs:\n" + "\n".join(violations)


def test_github_refs_use_org():
    """All GitHub references must use the canonical org."""
    github_pattern = re.compile(r"github(?:usercontent)?\.com/(\w+)/agency")
    violations = []
    for pyfile in _collect_python_files():
        for s in _extract_string_literals(pyfile):
            match = github_pattern.search(s)
            if match and match.group(1) != CANONICAL_ORG:
                violations.append(
                    f"{pyfile.relative_to(SRC_DIR.parent.parent)}: "
                    f"found '{match.group(1)}', expected '{CANONICAL_ORG}'"
                )
    assert not violations, f"Non-canonical GitHub org refs:\n" + "\n".join(violations)


def test_urls_are_wellformed():
    """All hardcoded URLs are syntactically valid."""
    from urllib.parse import urlparse
    url_pattern = re.compile(r"https?://[^\s\"']+")
    violations = []
    for pyfile in _collect_python_files():
        for s in _extract_string_literals(pyfile):
            for match in url_pattern.finditer(s):
                url = match.group(0).rstrip(".,;)")
                parsed = urlparse(url)
                if not parsed.scheme or not parsed.netloc:
                    violations.append(
                        f"{pyfile.relative_to(SRC_DIR.parent.parent)}: {url}"
                    )
    assert not violations, f"Malformed URLs:\n" + "\n".join(violations)
