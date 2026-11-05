from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from wechat_rule_assistant.domain.models import ActionJob, InboundEvent, MatchRule


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS rules (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, enabled INTEGER NOT NULL,
 source_binding_id TEXT NOT NULL, sender_binding_id TEXT NOT NULL,
 target_binding_id TEXT NOT NULL, keywords_json TEXT NOT NULL,
 keyword_mode TEXT NOT NULL CHECK(keyword_mode IN ('ALL','ANY')),
 exclude_keywords_json TEXT NOT NULL, case_sensitive INTEGER NOT NULL,
 reply_text TEXT NOT NULL, mode TEXT NOT NULL CHECK(mode IN ('dry_run','notify_confirm','auto')),
 cooldown_sec INTEGER NOT NULL, event_ttl_sec INTEGER NOT NULL,
 max_actions_per_day INTEGER NOT NULL, priority INTEGER NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event_records (
 id TEXT PRIMARY KEY, source_binding_id TEXT NOT NULL, dedup_key TEXT NOT NULL,
 observed_at TEXT NOT NULL, content_sha256 TEXT NOT NULL, decision TEXT NOT NULL,
 decision_reason TEXT, UNIQUE(source_binding_id, dedup_key)
);
CREATE TABLE IF NOT EXISTS action_jobs (
 id TEXT PRIMARY KEY, rule_id TEXT NOT NULL REFERENCES rules(id),
 event_id TEXT NOT NULL REFERENCES event_records(id), target_binding_id TEXT NOT NULL,
 reply_text TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL, approved_at TEXT, finished_at TEXT, failure_reason TEXT,
 UNIQUE(rule_id, event_id)
);
CREATE TABLE IF NOT EXISTS action_attempts (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES action_jobs(id), attempted_at TEXT NOT NULL,
 target_verified INTEGER NOT NULL, ui_result TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_jobs_status_expiry ON action_jobs(status, expires_at);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    def save_rule(self, rule: MatchRule) -> None:
        with self.transaction():
            self.connection.execute("""INSERT INTO rules VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,enabled=excluded.enabled,
                source_binding_id=excluded.source_binding_id,sender_binding_id=excluded.sender_binding_id,
                target_binding_id=excluded.target_binding_id,keywords_json=excluded.keywords_json,
                keyword_mode=excluded.keyword_mode,exclude_keywords_json=excluded.exclude_keywords_json,
                case_sensitive=excluded.case_sensitive,reply_text=excluded.reply_text,mode=excluded.mode,
                cooldown_sec=excluded.cooldown_sec,event_ttl_sec=excluded.event_ttl_sec,
                max_actions_per_day=excluded.max_actions_per_day,priority=excluded.priority,updated_at=excluded.updated_at""",
                (rule.id, rule.name, int(rule.enabled), rule.source_binding_id, rule.sender_binding_id,
                 rule.target_binding_id, json.dumps(rule.keywords, ensure_ascii=False), rule.keyword_mode,
                 json.dumps(rule.exclude_keywords, ensure_ascii=False), int(rule.case_sensitive), rule.reply_text,
                 rule.mode, rule.cooldown_sec, rule.event_ttl_sec, rule.max_actions_per_day, rule.priority, _iso(_now())))

    def list_rules(self) -> list[MatchRule]:
        return [self._row_to_rule(row) for row in self.connection.execute("SELECT * FROM rules ORDER BY priority, name")]

    def _row_to_rule(self, row: sqlite3.Row) -> MatchRule:
        return MatchRule(row["id"], row["name"], bool(row["enabled"]), row["source_binding_id"],
            row["sender_binding_id"], row["target_binding_id"], tuple(json.loads(row["keywords_json"])),
            row["reply_text"], row["keyword_mode"], tuple(json.loads(row["exclude_keywords_json"])),
            bool(row["case_sensitive"]), row["mode"], row["cooldown_sec"], row["event_ttl_sec"],
            row["max_actions_per_day"], row["priority"])

    def delete_rule(self, rule_id: str) -> None:
        with self.transaction():
            self.connection.execute("DELETE FROM rules WHERE id=?", (rule_id,))

    def record_decision(self, event: InboundEvent, rule: MatchRule, decision: str, reason: str) -> ActionJob | None:
        content_hash = hashlib.sha256(event.content.encode("utf-8")).hexdigest()
        # A source adapter key wins; the fallback deliberately contains observation time to avoid merging distinct repeats.
        dedup_key = event.adapter_event_key or f"{event.sender_binding_id}|{content_hash}|{_iso(event.observed_at)}"
        event_id = event.event_id
        now = _now()
        with self.transaction():
            try:
                self.connection.execute("INSERT INTO event_records VALUES(?,?,?,?,?,?,?)",
                    (event_id, event.source_binding_id, dedup_key, _iso(event.observed_at), content_hash, decision, reason))
            except sqlite3.IntegrityError:
                return None
            if decision != "matched":
                return None
            since = _iso(now - timedelta(seconds=rule.cooldown_sec))
            if self.connection.execute("SELECT 1 FROM action_jobs WHERE rule_id=? AND created_at>=? LIMIT 1", (rule.id, since)).fetchone():
                self.connection.execute("UPDATE event_records SET decision=?, decision_reason=? WHERE id=?", ("filtered", "cooldown", event_id))
                return None
            day_start = _iso(now.replace(hour=0, minute=0, second=0, microsecond=0))
            count = self.connection.execute("SELECT COUNT(*) FROM action_jobs WHERE rule_id=? AND created_at>=?", (rule.id, day_start)).fetchone()[0]
            if count >= rule.max_actions_per_day:
                self.connection.execute("UPDATE event_records SET decision=?, decision_reason=? WHERE id=?", ("filtered", "daily_limit", event_id))
                return None
            job_id, expiry = str(uuid4()), now + timedelta(seconds=rule.event_ttl_sec)
            status = "awaiting_approval" if rule.mode == "notify_confirm" else "approved"
            self.connection.execute("INSERT INTO action_jobs(id,rule_id,event_id,target_binding_id,reply_text,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)",
                (job_id, rule.id, event_id, rule.target_binding_id, rule.reply_text, status, _iso(now), _iso(expiry)))
            return ActionJob(job_id, rule.id, event_id, rule.target_binding_id, rule.reply_text, status, now, expiry)

    def record_event_and_jobs(self, event: InboundEvent, evaluations: list[tuple[MatchRule, bool, str]]) -> list[ActionJob]:
        """Persist one observed message and zero or more rule-specific jobs atomically."""
        content_hash = hashlib.sha256(event.content.encode("utf-8")).hexdigest()
        dedup_key = event.adapter_event_key or f"{event.sender_binding_id}|{content_hash}|{_iso(event.observed_at)}"
        matched = [(rule, reason) for rule, is_match, reason in evaluations if is_match]
        now, created = _now(), []
        with self.transaction():
            try:
                self.connection.execute("INSERT INTO event_records VALUES(?,?,?,?,?,?,?)", (
                    event.event_id, event.source_binding_id, dedup_key, _iso(event.observed_at), content_hash,
                    "matched" if matched else "filtered", "matched" if matched else ";".join(reason for _, _, reason in evaluations)))
            except sqlite3.IntegrityError:
                return []
            for rule, _ in matched:
                since = _iso(now - timedelta(seconds=rule.cooldown_sec))
                cooled_down = self.connection.execute("SELECT 1 FROM action_jobs WHERE rule_id=? AND created_at>=? LIMIT 1", (rule.id, since)).fetchone()
                day_start = _iso(now.replace(hour=0, minute=0, second=0, microsecond=0))
                daily_count = self.connection.execute("SELECT COUNT(*) FROM action_jobs WHERE rule_id=? AND created_at>=?", (rule.id, day_start)).fetchone()[0]
                if cooled_down or daily_count >= rule.max_actions_per_day:
                    continue
                job_id, expiry = str(uuid4()), now + timedelta(seconds=rule.event_ttl_sec)
                status = "awaiting_approval" if rule.mode == "notify_confirm" else "approved"
                self.connection.execute("INSERT INTO action_jobs(id,rule_id,event_id,target_binding_id,reply_text,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)", (
                    job_id, rule.id, event.event_id, rule.target_binding_id, rule.reply_text, status, _iso(now), _iso(expiry)))
                created.append(ActionJob(job_id, rule.id, event.event_id, rule.target_binding_id, rule.reply_text, status, now, expiry))
        return created

    def get_job(self, job_id: str) -> ActionJob | None:
        row = self.connection.execute("SELECT * FROM action_jobs WHERE id=?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(self, statuses: tuple[str, ...] = ()) -> list[ActionJob]:
        sql, params = "SELECT * FROM action_jobs", []
        if statuses:
            sql += " WHERE status IN (" + ",".join("?" for _ in statuses) + ")"
            params.extend(statuses)
        sql += " ORDER BY created_at DESC"
        return [self._row_to_job(row) for row in self.connection.execute(sql, params)]

    def _row_to_job(self, row: sqlite3.Row) -> ActionJob:
        return ActionJob(row["id"], row["rule_id"], row["event_id"], row["target_binding_id"], row["reply_text"], row["status"], datetime.fromisoformat(row["created_at"]), datetime.fromisoformat(row["expires_at"]))

    def set_job_status(self, job_id: str, status: str, reason: str | None = None) -> None:
        now = _iso(_now())
        with self.transaction():
            self.connection.execute("UPDATE action_jobs SET status=?, approved_at=CASE WHEN ?='approved' THEN ? ELSE approved_at END, finished_at=CASE WHEN ? IN ('sent_ui','failed','blocked','uncertain','cancelled') THEN ? ELSE finished_at END, failure_reason=? WHERE id=?",
                (status, status, now, status, now, reason, job_id))

    def add_attempt(self, job_id: str, target_verified: bool, result: str, details: str) -> None:
        with self.transaction():
            self.connection.execute("INSERT INTO action_attempts VALUES(?,?,?,?,?,?)", (str(uuid4()), job_id, _iso(_now()), int(target_verified), result, json.dumps({"details": details}, ensure_ascii=False)))
