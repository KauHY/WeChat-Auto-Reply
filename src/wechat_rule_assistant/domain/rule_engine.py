from __future__ import annotations

import unicodedata

from .models import InboundEvent, MatchRule


def normalize_text(text: str, case_sensitive: bool) -> str:
    normalized = unicodedata.normalize("NFKC", text).strip()
    return normalized if case_sensitive else normalized.casefold()


def evaluate(event: InboundEvent, rule: MatchRule) -> tuple[bool, str]:
    if not rule.enabled:
        return False, "rule_disabled"
    if not event.is_after_startup_baseline:
        return False, "historical_or_unverified_newness"
    if event.source_kind != "group":
        return False, "wrong_conversation_type"
    if event.direction != "incoming" or event.message_type != "text":
        return False, "unsupported_direction_or_type"
    if event.source_binding_id != rule.source_binding_id:
        return False, "wrong_source_group"
    if not event.sender_identity_verified:
        return False, "sender_ambiguous"
    if event.sender_binding_id != rule.sender_binding_id:
        return False, "wrong_sender"
    if not rule.keywords or any(not key.strip() for key in rule.keywords):
        return False, "invalid_keywords"

    body = normalize_text(event.content, rule.case_sensitive)
    exclusions = [normalize_text(key, rule.case_sensitive) for key in rule.exclude_keywords if key.strip()]
    if any(key in body for key in exclusions):
        return False, "excluded_keyword"
    hits = [normalize_text(key, rule.case_sensitive) in body for key in rule.keywords]
    matched = all(hits) if rule.keyword_mode == "ALL" else any(hits)
    return matched, "matched" if matched else "keywords_not_satisfied"
