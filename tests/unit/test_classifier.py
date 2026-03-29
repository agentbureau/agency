"""Test task-type keyword classifier (Issue 8, v1.2.4)."""
from agency.engine.classifier import classify_task_type, estimate_method_absence


LABELLED_DESCRIPTIONS = [
    ("Review the PRD for implementation blockers", "review"),
    ("Build a REST API for user authentication", "build"),
    ("Investigate what Singapore statutes apply to youth programme data collection under PDPA", "research"),
    ("Write an executive summary of the workshop findings", "write"),
    ("Design a three-tier architecture for the notification service", "design"),
    ("Debug why the webhook endpoint returns 502 on POST requests", "debug"),
    ("Evaluate three vendor proposals against the scoring rubric", "evaluate"),
    ("Plan the implementation sequence for the v2.0 migration", "plan"),
    ("Audit the codebase for PII exposure in log statements", "audit"),
    ("Advise on whether to proceed with the acquisition given the due diligence findings", "advise"),
    ("Analyse the gap between the current org structure and the target operating model", "analyse"),
    ("Research the latest findings on transformer attention mechanisms", "research"),
    ("Create a CLI tool for primitive CSV validation", "build"),
    ("Check this consulting proposal for overstatements and unsupported claims", "review"),
    ("Draft a blog post about the distinction between risk and uncertainty", "write"),
    ("Troubleshoot the failing CI pipeline — tests pass locally but fail in GitHub Actions", "debug"),
    ("Score each candidate response on a 1-5 scale using the rubric dimensions", "evaluate"),
    ("Recommend a pricing strategy for the pilot programme", "advise"),
    ("Validate that all API endpoints return the documented error schemas", "audit"),
    ("Propose a data model for the multi-tenant primitive store", "design"),
    ("Synthesise the findings from the three research agents into a unified report", "synthesise"),
    ("Bring together the user interview themes and the quantitative survey data", "synthesise"),
    ("Consolidate the gap analysis, stakeholder feedback, and market research into a single brief", "synthesise"),
    ("Integrate the technical audit results with the business case analysis", "synthesise"),
]


def test_classifier_agreement():
    """At least 80% agreement with human labels (>=19 of 24)."""
    correct = sum(
        1 for desc, expected in LABELLED_DESCRIPTIONS
        if classify_task_type(desc) == expected
    )
    assert correct >= 19, f"Only {correct}/24 correct (need >=19)"


def test_classifier_fallback():
    """No keywords match -> falls back to 'analyse'."""
    assert classify_task_type("do something vague") == "analyse"


def test_method_absence_fully_absent():
    """No method indicators -> 1.0."""
    assert estimate_method_absence("Review this document for clarity") == 1.0


def test_method_absence_fully_prescribed():
    """3+ method indicators -> 0.0."""
    desc = "Distinguish fact from opinion, evaluate by criteria A/B/C, rank by importance"
    assert estimate_method_absence(desc) == 0.0
