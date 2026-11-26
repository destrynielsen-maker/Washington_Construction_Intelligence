"""Additive, source-attributed reporting; no influence on permit/RSS membership."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import Permit


def history_available(path: Path, existing: dict[str, Permit]) -> bool:
    if existing:
        return True
    # A valid empty saved ledger is evidence; the legacy loader also returns {}
    # on missing or unreadable files, but neither demonstrates a zero baseline.
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return payload == [] or (isinstance(payload, dict) and payload.get("permits") == [])


def source_row(status: dict, previous: dict | None, retained: dict[str, Permit],
               issued_new_keys: set[str], baseline_known: bool, today: date) -> dict:
    label = status["source"]
    items = [p for p in retained.values() if p.jurisdiction == label]
    failed = status["technical_status"] == "error"
    success_at = status.get("last_success_at")
    date_value = status.get("newest_permit_date")
    # On error/no-data, show the latest earlier issued permit still visible in
    # history. Within a successful non-empty run prefer that source's date.
    if failed or not date_value:
        dates = [p.issued_date for p in items] + [date_value]
    else:
        dates = [date_value]
    valid = []
    for raw in dates:
        if not raw:
            continue
        try:
            parsed = date.fromisoformat(raw)
        except (ValueError, TypeError):
            continue
        if parsed <= today:
            valid.append(parsed)
    latest = max(valid, default=None)
    prev_success = (previous or {}).get("last_success_at")
    availability = ("partial" if items else "unavailable") if failed else (
        "partial" if status["status"] in {"degraded", "warning"} or (status["status"] == "no_data" and items)
        else "reachable"
    )
    return {
        "id": label.lower().replace(" ", "-"),
        "label": label,
        "mode": "automatic",
        "coverage": "City of Seattle issued building permits only" if label == "Seattle" else label,
        "last_attempt_at": status.get("last_attempt_at"),
        "last_success_at": success_at,
        "latest_authoritative_date": latest.isoformat() if latest else None,
        "latest_date_kind": "issued" if latest else None,
        "source_age_days": (today-latest).days if latest else None,
        "new_since_previous_success": len(issued_new_keys) if not failed and prev_success and baseline_known else None,
        "retained_records": len(items) if items or baseline_known or not failed else None,
        "observed_records": None if failed else status.get("records_seen"),
        "availability": availability,
        "freshness_status": ("stale" if (today-latest).days > status.get("freshness_threshold_days",30) else "fresh") if latest else "unknown",
        "date_provenance": ("retained" if failed or not date_value else "current_report") if latest else None,
        "collection_outcome": "error" if failed else ("no_data" if status["status"] == "no_data" else "success"),
    }

def uncovered_rows() -> list[dict]:
    regions = [
        ("spokane-city", "Spokane City", "No published issued-permit collector"),
        ("spokane-county", "Spokane County", "No published coverage; manual-export preview only"),
        ("spokane-valley", "Spokane Valley", "No published issued-permit collector"),
        ("eastern-wa", "Other Eastern Washington", "No published issued-permit collector, including Tri-Cities"),
    ]
    return [{
        "id": key, "label": label, "mode": "uncovered", "coverage": coverage,
        "last_attempt_at": None, "last_success_at": None,
        "latest_authoritative_date": None, "latest_date_kind": None, "source_age_days": None,
        "new_since_previous_success": None, "retained_records": None, "observed_records": None,
        "availability": "not_attempted", "collection_outcome": "unknown", "freshness_status": "unknown",
        "date_provenance": None,
    } for key, label, coverage in regions]
