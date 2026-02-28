"""Policy engine for Data Sheriff decisions."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from .models import AccessDecision, FileRiskLabel, PolicyRule
from .storage import JSONFileStore


def _normalize_path(path: str) -> str:
    if path == "*":
        return path
    return str(Path(path).expanduser().resolve())


def _subject_matches(subject: str, rule_subjects: List[str]) -> bool:
    return "*" in rule_subjects or subject in rule_subjects


def _path_matches(resource: str, path_scope: str) -> bool:
    if path_scope == "*":
        return True
    target = _normalize_path(resource)
    scope = _normalize_path(path_scope)
    return target == scope or target.startswith(scope.rstrip("/") + "/")


class PolicyEngine:
    """Persistent rule store + default deny-by-default behavior."""

    def __init__(self, store_path):
        self.store = JSONFileStore(Path(store_path))
        self._rules: List[PolicyRule] = []
        self._load()

    def _load(self) -> None:
        raw = self.store.load(default=[])
        parsed: List[PolicyRule] = []
        for item in raw:
            try:
                parsed.append(PolicyRule.model_validate(item))
            except Exception:
                continue
        self._rules = parsed

    def _flush(self) -> None:
        payload = [r.model_dump(mode="json") for r in self._rules]
        self.store.save(payload)

    def list_rules(self) -> List[PolicyRule]:
        """Return all rules, ordered by descending priority."""
        return sorted(self._rules, key=lambda r: r.priority, reverse=True)

    def add_rule(self, rule: PolicyRule) -> PolicyRule:
        """Add or replace rule."""
        self._rules = [r for r in self._rules if r.rule_id != rule.rule_id]
        self._rules.append(rule)
        self._flush()
        return rule

    def remove_rule(self, rule_id: str) -> bool:
        """Remove rule by id."""
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.rule_id != rule_id]
        changed = len(self._rules) != before
        if changed:
            self._flush()
        return changed

    def protect_paths(self, paths: List[str], label: FileRiskLabel = FileRiskLabel.CRITICAL) -> List[PolicyRule]:
        """Create path-scoped prompt rules for protected resources."""
        created: List[PolicyRule] = []
        for path in paths:
            rule = PolicyRule(
                path_scope=path,
                label_scope=[label],
                subject_scope=["*"],
                decision=AccessDecision.PROMPT,
                priority=200,
            )
            created.append(self.add_rule(rule))
        return created

    def evaluate(self, *, subject_app: str, resource: str, label: FileRiskLabel) -> Tuple[AccessDecision, str]:
        """Return decision and reason."""
        for rule in self.list_rules():
            if not rule.enabled:
                continue
            if label not in rule.label_scope:
                continue
            if not _subject_matches(subject_app, rule.subject_scope):
                continue
            if not _path_matches(resource, rule.path_scope):
                continue
            return rule.decision, f"Matched policy rule {rule.rule_id}"

        # Default deny-by-default posture for non-normal resources.
        if label == FileRiskLabel.CRITICAL:
            return AccessDecision.PROMPT, "Critical resource requires explicit consent"
        if label == FileRiskLabel.SENSITIVE:
            return AccessDecision.PROMPT, "Sensitive resource requires explicit consent"
        return AccessDecision.ALLOW, "Normal resource allowed by default policy"
