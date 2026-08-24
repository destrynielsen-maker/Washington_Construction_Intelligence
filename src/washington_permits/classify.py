from __future__ import annotations
import re
from .models import Permit

EXCLUDE = re.compile(
    r"\b(re-?roof|roofing|mechanical|plumbing|electrical|solar|photovoltaic|sign|"
    r"fence|pool|spa|demolition|demo\b|water heater|tenant improvement|tenant finish|"
    r"addition|alteration|remodel|repair|deck|patio cover|revision|curb cut)\b", re.I
)
MULTI = re.compile(
    r"\b(multi[ -]?family|apartment|apartments|townhome|townhouse|duplex|triplex|"
    r"fourplex|condo|minium|\d+\s*[- ]?unit|\d+\s*[- ]?plex|middle housing)\b", re.I
)
SINGLE = re.compile(
    r"\b(single[- ]family|one family dwelling|one-family dwelling|new residence|"
    r"new home|detached dwelling|single family/duplex)\b", re.I
)
COMMERCIAL = re.compile(
    r"\b(commercial|non-residential|nonresidential|institutional|industrial|warehouse|"
    r"school|hospital|office|retail|hotel|mercantile|storage|factory|business)\b", re.I
)

def classify_permit(p: Permit) -> Permit:
    raw = p.raw or {}
    description = str(raw.get("description") or p.project_name or "")
    action = str(raw.get("permittypedesc") or "")
    permit_class = str(raw.get("permitclass") or p.building_use or "")
    text = " ".join([p.permit_type or "", permit_class, action, description])

    # Seattle's issued dataset has an explicit action field. Require "New"
    # when present so remodels/TIs do not leak into prospecting.
    is_new = action.strip().lower() == "new" if action.strip() else bool(re.search(r"\bnew\b|construct new|new construction", text, re.I))
    if EXCLUDE.search(text) or not is_new:
        p.classification = "OTHER"; p.qualifies = False; p.score = 0; p.new_construction_confidence = "LOW"; return p

    units = int(p.units or 0)
    if permit_class.lower().startswith("multifamily"):
        p.classification = "MULTIFAMILY"
    elif permit_class.lower().startswith("single family"):
        # Seattle groups single-family and duplex together. Use the narrative
        # to promote true duplex/townhome/multifamily work without treating the
        # class label itself as multifamily.
        if re.search(r"\bduplex|townhome|townhouse|triplex|fourplex|apartment\b", description, re.I):
            p.classification = "MULTIFAMILY"
        else:
            p.classification = "SINGLE_FAMILY"
    elif MULTI.search(text):
        p.classification = "MULTIFAMILY"
    elif SINGLE.search(text):
        p.classification = "SINGLE_FAMILY"
    elif permit_class.lower().startswith("commercial") or COMMERCIAL.search(text):
        p.classification = "COMMERCIAL"
    else:
        p.classification = "OTHER"; p.qualifies = False; p.score = 0; p.new_construction_confidence = "LOW"; return p

    p.qualifies = True
    p.new_construction_confidence = "HIGH"
    score = {"MULTIFAMILY": 40, "COMMERCIAL": 30, "SINGLE_FAMILY": 15}[p.classification]
    value = float(p.valuation or 0)
    if value >= 10_000_000: score += 20
    elif value >= 5_000_000: score += 15
    elif value >= 1_000_000: score += 10
    elif value >= 500_000: score += 5
    if units >= 100: score += 20
    elif units >= 50: score += 15
    elif units >= 20: score += 10
    elif units >= 5: score += 5
    if p.contractor: score += 5
    if p.owner: score += 3
    p.score = min(score, 100)
    return p
