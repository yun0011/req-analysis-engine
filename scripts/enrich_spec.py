#!/usr/bin/env python3
"""
Enrich 6_structured_spec.json with request_schema and response_schema
by mapping FR evidence_refs → Rule Record schemas.
"""

import json
import re

BASE = "/Users/sds/Documents/Personal_Github/req-analysis-engine"
REQ_ANALYSIS = f"{BASE}/.req-analysis"


# ──────────────────────────────────────────────────────────────
# Load rule records — build lookup: rule_id → schema
# ──────────────────────────────────────────────────────────────

with open(f"{REQ_ANALYSIS}/3_rule_records.json") as f:
    rr_data = json.load(f)

# Also load entry points for route lookup
with open(f"{REQ_ANALYSIS}/1_entry_points.json") as f:
    ep_data = json.load(f)
ep_map = {ep["ep_id"]: ep for ep in ep_data["entry_points"]}

rr_map = {}  # rule_id → rule_record
ep_rr_map = {}  # ep_id → list of rule_records
for rr in rr_data["rule_records"]:
    rr_map[rr["rule_id"]] = rr
    ep_id = rr["entrypoint_id"]
    ep_rr_map.setdefault(ep_id, []).append(rr)


# ──────────────────────────────────────────────────────────────
# Load structured spec
# ──────────────────────────────────────────────────────────────

with open(f"{REQ_ANALYSIS}/6_structured_spec.json") as f:
    spec = json.load(f)


# ──────────────────────────────────────────────────────────────
# Enrich each FR
# ──────────────────────────────────────────────────────────────

def find_schema_for_fr(evidence_refs: list) -> tuple:
    """
    Given evidence_refs like ['DG-USER-C-001', 'EP-001-R-001'],
    find the matching Rule Record and return (request_schema, response_schema).
    """
    for ref in evidence_refs:
        # Direct rule record reference: EP-NNN-R-NNN
        if re.match(r"EP-\d+-R-\d+", ref):
            rr = rr_map.get(ref)
            if rr:
                return rr.get("request_schema"), rr.get("response_schema")

    # Fallback: try EP-NNN prefix
    for ref in evidence_refs:
        m = re.match(r"(EP-\d+)", ref)
        if m:
            ep_id = m.group(1)
            rrs = ep_rr_map.get(ep_id, [])
            if rrs:
                return rrs[0].get("request_schema"), rrs[0].get("response_schema")

    return None, None


enriched_count = 0
total_fr = 0

for domain in spec["structured_spec"]["domains"]:
    for fr in domain["features"]:
        total_fr += 1
        evidence_refs = fr.get("evidence_refs", [])
        req_schema, resp_schema = find_schema_for_fr(evidence_refs)
        fr["request_schema"] = req_schema
        fr["response_schema"] = resp_schema
        if req_schema:
            enriched_count += 1

# Also enrich XC items (no schema needed, but note coverage)
for xc in spec["structured_spec"].get("cross_cutting", []):
    xc["request_schema"] = None
    xc["response_schema"] = None

print(f"Enriched {enriched_count}/{total_fr} FRs with request_schema")


# ──────────────────────────────────────────────────────────────
# Write enriched spec
# ──────────────────────────────────────────────────────────────

with open(f"{REQ_ANALYSIS}/6_structured_spec.json", "w") as f:
    json.dump(spec, f, ensure_ascii=False, indent=2)

print(f"Written to {REQ_ANALYSIS}/6_structured_spec.json")
