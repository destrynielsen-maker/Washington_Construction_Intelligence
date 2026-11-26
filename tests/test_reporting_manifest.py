from __future__ import annotations
import json, tempfile, unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from washington_permits.models import Permit
from washington_permits.pipeline import run


class FixedDatetime(datetime):
    current = "2026-11-26T18:49:49+00:00"

    @classmethod
    def now(cls, tz=None):
        return datetime.fromisoformat(cls.current)


def permit(number):
    return Permit(state="WA", jurisdiction="Seattle", permit_number=number,
                  issued_date="2026-11-24", permit_type="Construction",
                  project_name="Construct new single family residence",
                  status="Issued", source_name="Seattle", source_url="https://example.com/permit")


class ManifestTest(unittest.TestCase):
    def test_pipeline_cold_success_zero_fail_recovery(self):
        raw = [permit("A")]
        def collect():
            if raw and isinstance(raw[0], Exception):
                raise raw[0]
            return SimpleNamespace(permits=[Permit.from_dict(p.to_dict()) for p in raw],
                                   source_url="https://example.com", source="Seattle", note="fixture")
        collector = SimpleNamespace(name="Seattle", freshness_days=10, collect=collect)
        with tempfile.TemporaryDirectory() as tmp, patch("washington_permits.pipeline.COLLECTORS", [collector]), patch("washington_permits.pipeline.datetime", FixedDatetime):
            root = Path(tmp)
            def read():
                payload=json.loads((root/"public/data/sources.json").read_bytes())
                self.assertEqual(payload["reporting_v1"]["generated_at"], payload["generated_at"])
                self.assertEqual(len(payload["sources"]),1)
                self.assertEqual(payload["reporting_v1"]["schema_version"],1)
                gaps=payload["reporting_v1"]["sources"][1:]
                self.assertEqual(len(gaps),4)
                self.assertTrue(all(r["retained_records"] is None and r["observed_records"] is None for r in gaps))
                self.assertEqual([(r["mode"],r["collection_outcome"]) for r in gaps], [
                    ("uncovered","unknown"),("manual","manual_only"),("uncovered","unknown"),("uncovered","unknown")])
                return payload["reporting_v1"]["sources"][0]
            raw[:] = [RuntimeError("fixture failure")]
            run(root)
            cold_failed=read()
            self.assertEqual(cold_failed["availability"],"unavailable")
            self.assertIsNone(cold_failed["observed_records"])
            self.assertIsNone(cold_failed["retained_records"])
            raw[:] = [permit("A")]
            run(root)
            initial=read()
            self.assertIsNone(initial["new_since_previous_success"])
            self.assertEqual((initial["observed_records"],initial["retained_records"]), (1,1))
            self.assertEqual((initial["latest_authoritative_date"], initial["source_age_days"]),("2026-11-24",2))
            first=(json.loads((root/"data/permits.json").read_bytes())["permits"][0])["first_seen_at"]
            FixedDatetime.current = "2026-11-27T18:49:49+00:00"
            raw[:] = [permit("A"),permit("B"),permit("B")]
            run(root)
            second=read()
            self.assertEqual((second["new_since_previous_success"],second["retained_records"],second["observed_records"]), (1,2,3))
            raw[:] = [RuntimeError("fixture error")]
            FixedDatetime.current = "2026-11-28T18:49:49+00:00"
            run(root)
            failed=read()
            self.assertEqual(failed["last_success_at"], second["last_success_at"])
            self.assertNotEqual(failed["last_attempt_at"],second["last_attempt_at"])
            self.assertEqual((failed["availability"],failed["collection_outcome"]),("unavailable","error"))
            self.assertEqual(failed["retained_records"],2)
            self.assertIsNone(failed["new_since_previous_success"])
            self.assertIsNone(failed["observed_records"])
            FixedDatetime.current = "2026-11-29T18:49:49+00:00"
            raw[:] = [permit("A"),permit("B"),permit("C")]
            run(root)
            recovered=read()
            self.assertEqual((recovered["new_since_previous_success"],recovered["retained_records"]), (1,3))
            raw[:] = []
            run(root)
            empty=read()
            self.assertEqual((empty["collection_outcome"],empty["observed_records"],empty["retained_records"],empty["new_since_previous_success"]),("no_data",0,3,None))
            self.assertEqual(empty["date_provenance"],"retained")
            self.assertEqual(next(p for p in json.loads((root/"data/permits.json").read_bytes())["permits"] if p["permit_number"]=="A")["first_seen_at"],first)
