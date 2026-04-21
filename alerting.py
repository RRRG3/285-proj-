"""Simple persistent alerting engine based on operational telemetry."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AlertingEngine:
    """Evaluate and persist alert states from monitoring snapshots."""

    def __init__(self, path: str = "data/alerts.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"active": {}, "history": []}

        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
                if not isinstance(payload, dict):
                    return {"active": {}, "history": []}
                payload.setdefault("active", {})
                payload.setdefault("history", [])
                return payload
        except Exception:
            return {"active": {}, "history": []}

    def _save(self, payload: dict[str, Any]) -> None:
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _rules(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        counters = snapshot.get("counters", {}) if isinstance(snapshot, dict) else {}
        failure_rate = float(snapshot.get("failure_rate_pct", 0.0) or 0.0)

        triggered: list[dict[str, Any]] = []
        if failure_rate >= 7.0:
            triggered.append(
                {
                    "id": "HIGH_QUOTE_FAILURE_RATE",
                    "severity": "high",
                    "message": f"Quote failure rate is {failure_rate:.2f}% (threshold 7%).",
                }
            )

        fallback_quotes = int(counters.get("fallback_quotes", 0) or 0)
        if fallback_quotes >= 25:
            triggered.append(
                {
                    "id": "ELEVATED_FALLBACK_USAGE",
                    "severity": "medium",
                    "message": (
                        f"Fallback quotes reached {fallback_quotes} in this session "
                        "(threshold 25)."
                    ),
                }
            )

        stale_quotes = int(counters.get("stale_quotes", 0) or 0)
        if stale_quotes >= 10:
            triggered.append(
                {
                    "id": "STALE_QUOTE_PRESSURE",
                    "severity": "medium",
                    "message": f"Stale quote count is {stale_quotes} (threshold 10).",
                }
            )

        return triggered

    def evaluate(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Evaluate rules against a monitoring snapshot and persist alert state."""
        state = self._load()
        now_iso = self._iso_now()

        active_map: dict[str, Any] = state.get("active", {})
        history: list[dict[str, Any]] = state.get("history", [])

        triggered = self._rules(snapshot)
        triggered_ids = {item["id"] for item in triggered}

        # Resolve no-longer-triggered alerts.
        for alert_id in list(active_map.keys()):
            if alert_id in triggered_ids:
                continue
            resolved = active_map.pop(alert_id)
            resolved["status"] = "resolved"
            resolved["resolved_at"] = now_iso
            history.append(resolved)

        # Upsert triggered alerts.
        for item in triggered:
            alert_id = item["id"]
            existing = active_map.get(alert_id)
            if existing:
                existing["last_seen"] = now_iso
                existing["message"] = item["message"]
                existing["severity"] = item["severity"]
            else:
                active_map[alert_id] = {
                    "id": alert_id,
                    "severity": item["severity"],
                    "message": item["message"],
                    "status": "active",
                    "triggered_at": now_iso,
                    "last_seen": now_iso,
                }

        history = history[-200:]
        payload = {"active": active_map, "history": history}
        self._save(payload)

        active_list = sorted(active_map.values(), key=lambda entry: entry.get("severity", ""), reverse=True)
        return {
            "active": active_list,
            "history": history,
            "active_count": len(active_list),
        }

    def get_snapshot(self) -> dict[str, Any]:
        payload = self._load()
        active_map = payload.get("active", {})
        active_list = sorted(active_map.values(), key=lambda entry: entry.get("severity", ""), reverse=True)
        return {
            "active": active_list,
            "history": payload.get("history", []),
            "active_count": len(active_list),
        }
