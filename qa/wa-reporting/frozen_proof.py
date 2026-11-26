"""Offline, frozen proof comparing legacy and candidate output across identical run inputs."""
import hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from textwrap import dedent
here=Path(__file__).resolve().parent
base=Path(sys.argv[1]).resolve()
candidate=Path(sys.argv[2]).resolve()
shim=dedent("""
    from datetime import datetime
    from types import SimpleNamespace
    from pathlib import Path
    from unittest.mock import patch
    from washington_permits.pipeline import run
    from washington_permits.storage import load_permits
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls,tz=None): return cls.fromisoformat('2026-11-26T19:49:49+00:00')
    root=Path.cwd()
    observed=[p for p in load_permits(root/'data/permits.json').values() if p.last_seen_at=='2026-11-26T18:49:49+00:00']
    from json import loads
    previous=loads((root/'public/data/sources.json').read_bytes())['sources'][0]
    source=SimpleNamespace(name='Seattle',freshness_days=10,collect=lambda:SimpleNamespace(source='Seattle',permits=observed,source_url=previous['source_url'],note=previous['note']))
    with patch('washington_permits.pipeline.COLLECTORS',[source]),patch('washington_permits.pipeline.datetime',FrozenDatetime): run(root)
""")
with tempfile.TemporaryDirectory() as tmp:
    out={}
    for kind,code in (("baseline",base),("candidate",candidate)):
        d=Path(tmp,kind);(d/"data").mkdir(parents=True);(d/"public/data").mkdir(parents=True)
        for f in ("data/permits.json","public/data/sources.json"):
            (d/f).write_bytes((base/f).read_bytes())
        subprocess.run([sys.executable,"-c",shim],cwd=d,env={**os.environ,"PYTHONPATH":str(code/"src")},check=True)
        out[kind]=d
    before,after=out["baseline"],out["candidate"]
    protected=("data/permits.json","public/data/permits.json","public/data/builders.json")
    protected += tuple(str(p.relative_to(before)) for p in (before/"public/feeds").glob("*.xml"))
    for filename in protected:
        assert (before/filename).read_bytes()==(after/filename).read_bytes(), filename
    a=json.loads((before/"public/data/sources.json").read_bytes()); b=json.loads((after/"public/data/sources.json").read_bytes())
    manifest=b.pop("reporting_v1");assert a==b
    assert manifest["sources"][0]["retained_records"]==2463
    assert manifest["sources"][0]["new_since_previous_success"]==0
    print("PASS:",len(protected),"identical protected files; source status identical excluding additive manifest; Seattle",manifest["sources"][0])

