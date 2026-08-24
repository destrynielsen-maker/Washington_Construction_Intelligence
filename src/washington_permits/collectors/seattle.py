from __future__ import annotations
from datetime import datetime
from urllib.parse import urlparse
import requests
from .base import CollectionResult, new_session
from ..models import Permit

class SeattleCollector:
    name = "Seattle"
    freshness_days = 10
    dataset_id = "8tqq-u7ib"
    api_url = f"https://data.seattle.gov/resource/{dataset_id}.json"
    source_url = "https://data.seattle.gov/Permitting/Issued-Building-Permits/8tqq-u7ib"

    def collect(self, session: requests.Session | None = None) -> CollectionResult:
        session = session or new_session()
        params = {
            "$limit": 50000,
            "$order": "issueddate DESC",
            "$where": "issueddate IS NOT NULL",
        }
        response = session.get(self.api_url, params=params, timeout=90)
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("Seattle issued-building-permit API returned no rows")
        self._validate_source_identity(rows)

        permits: list[Permit] = []
        for row in rows:
            number = str(row.get("permitnum") or "").strip()
            issued = self._date(row.get("issueddate"))
            if not number or not issued:
                continue
            units = self._int(row.get("housingunitsadded"))
            if units is None:
                units = self._int(row.get("housingunits"))
            description = str(row.get("description") or "").strip()
            permit_class = str(row.get("permitclass") or "").strip()
            action = str(row.get("permittypedesc") or "").strip()
            mapped = str(row.get("permitclassmapped") or "").strip()
            link = self._link(row.get("link")) or self.source_url
            permits.append(Permit(
                state="WA",
                jurisdiction="Seattle",
                permit_number=number,
                issued_date=issued,
                permit_type=" / ".join(x for x in [permit_class, action] if x),
                building_use=mapped or permit_class or None,
                project_name=description or None,
                address=str(row.get("originaladdress1") or "").strip(),
                units=units,
                valuation=self._float(row.get("estprojectcost")),
                contractor=str(row.get("contractorcompanyname") or "").strip() or None,
                status=str(row.get("statuscurrent") or "").strip() or None,
                source_name="City of Seattle SDCI Issued Building Permits",
                source_url=link,
                raw={
                    **row,
                    "description": description,
                    "permitclass": permit_class,
                    "permittypedesc": action,
                    "permitclassmapped": mapped,
                },
            ))
        if not permits:
            raise RuntimeError("Seattle API parsed with zero usable permit rows")
        return CollectionResult(
            self.name, permits, self.source_url,
            "Official City of Seattle SDCI Issued Building Permits open-data feed"
        )

    @classmethod
    def _validate_source_identity(cls, rows: list[dict]) -> None:
        checked = rows[:250]
        wrong_state = []
        wrong_city = []
        foreign_links = []
        for row in checked:
            state = str(row.get("originalstate") or "").strip().upper()
            city = str(row.get("originalcity") or "").strip().upper()
            link = cls._link(row.get("link"))
            if state and state not in {"WA", "WASHINGTON"}:
                wrong_state.append(state)
            if city and city != "SEATTLE":
                wrong_city.append(city)
            if link:
                host = (urlparse(link).hostname or "").lower()
                if host not in {"services.seattle.gov", "www.seattle.gov", "seattle.gov"}:
                    foreign_links.append(host)
        if wrong_state or wrong_city or foreign_links:
            raise RuntimeError(
                f"Seattle source identity check failed: wrong_state={wrong_state[:3]}, "
                f"wrong_city={wrong_city[:3]}, foreign_links={foreign_links[:3]}"
            )

    @staticmethod
    def _link(value) -> str | None:
        if isinstance(value, dict):
            value = value.get("url")
        value = str(value or "").strip()
        return value or None

    @staticmethod
    def _date(value) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        text = text[:10]
        try:
            return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None

    @staticmethod
    def _int(value) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _float(value) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace("$","").replace(",",""))
        except (TypeError, ValueError):
            return None
