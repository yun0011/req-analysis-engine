#!/usr/bin/env python3
"""
Schema extraction script.
Adds request_schema and response_schema to each Rule Record in 3_rule_records.json
by reading struct definitions from analysis_output/ AST files.
"""

import json
import os
import re

BASE = "/Users/sds/Documents/Personal_Github/req-analysis-engine"
AST_BASE = f"{BASE}/analysis_output/pati-server"
REQ_ANALYSIS = f"{BASE}/.req-analysis"

# ──────────────────────────────────────────────────────────────
# Step 1: Build struct registry from all AST JSON files
# ──────────────────────────────────────────────────────────────

struct_registry = {}   # name → {fields: [...], body: str}

for root, dirs, files in os.walk(AST_BASE):
    for fn in files:
        if fn.endswith(".json"):
            with open(os.path.join(root, fn)) as fh:
                data = json.load(fh)
            for s in data.get("structs", []):
                name = s["name"]
                # Prefer types/ package over others for disambiguation
                rel_path = os.path.relpath(os.path.join(root, fn), AST_BASE)
                if name not in struct_registry or rel_path.startswith("types/"):
                    struct_registry[name] = {
                        "fields": s.get("fields", []),
                        "body": s.get("body", ""),
                        "file": rel_path,
                    }

print(f"Loaded {len(struct_registry)} structs into registry")


# ──────────────────────────────────────────────────────────────
# Step 2: Helpers
# ──────────────────────────────────────────────────────────────

def parse_json_key(tag: str | None, field_name: str) -> str:
    """Extract JSON key from struct tag, or convert FieldName → field_name."""
    if tag:
        m = re.search(r'json:"([^,"\\]+)', tag)
        if m:
            return m.group(1)
    # CamelCase → snake_case fallback
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", field_name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()


def is_optional(field: dict) -> bool:
    """A field is optional if it's a pointer type or has omitempty tag."""
    t = field.get("type", "")
    tag = field.get("tag", "") or ""
    return t.startswith("*") or t.startswith("[]*") or "omitempty" in tag


def base_type(type_str: str) -> str:
    """Strip pointer/slice wrappers to get the base type name."""
    t = type_str.lstrip("[]*")
    # Remove package prefix: types.User → User
    if "." in t:
        t = t.split(".")[-1]
    # Apply type name aliases (e.g. lowercase api-local aliases)
    t = TYPE_NAME_ALIASES.get(t, t)
    return t


PRIMITIVE_TYPES = {
    "string", "bool", "int", "int8", "int16", "int32", "int64",
    "uint", "uint8", "uint16", "uint32", "uint64",
    "float32", "float64", "byte", "rune", "[]byte",
}

# Custom domain scalar types we know about
SCALAR_ALIASES = {
    "sessionID": {"json_type": "string", "description": "세션 ID (64자 hex)"},
    "Permission": {"json_type": "string", "description": "사용자 권한 타입 (Admin|Employee|Professor|Student)"},
    "TermStatus": {"json_type": "string", "description": "학기 상태 (READY|APPLYING|PROCEEDING|GRADUATED)"},
    "Semester": {"json_type": "string", "description": "학기 구분 (SPRING|FALL)"},
    "Grade": {"json_type": "string", "description": "학년 등급"},
    "Status": {"json_type": "string", "description": "상태 값"},
    "RegistrationStatus": {"json_type": "string", "description": "수강 신청 상태 (REQUESTED|ENROLLED|CANCELED 등)"},
}

# Type name aliases: lowercase api-local aliases → canonical struct name
TYPE_NAME_ALIASES = {
    "term": "Term",  # api package local type alias for types.Term
}


def is_primitive(type_str: str) -> bool:
    bt = base_type(type_str)
    raw = type_str.lstrip("[]*")
    return bt in PRIMITIVE_TYPES or raw in PRIMITIVE_TYPES or raw.endswith("int") or raw.endswith("float")


def expand_struct(struct_name: str, depth: int = 0, visited: set = None) -> list:
    """
    Recursively expand a struct into a flat list of field dicts:
    {json_key, go_type, required, description}
    """
    if visited is None:
        visited = set()
    if struct_name in visited or depth > 4:
        return [{"json_key": f"<{struct_name}>", "go_type": struct_name, "required": False,
                 "description": "recursive/deep reference"}]
    visited = visited | {struct_name}

    s = struct_registry.get(struct_name)
    if not s:
        return [{"json_key": struct_name.lower(), "go_type": struct_name, "required": False,
                 "description": f"unknown type {struct_name}"}]

    result = []
    for field in s["fields"]:
        fname = field["name"]
        ftype = field.get("type", "")
        ftag = field.get("tag")
        json_key = parse_json_key(ftag, fname)
        optional = is_optional(field)
        bt = base_type(ftype)

        # Skip session_id in sub-expansions (it's already handled at top level)
        if ftype == "sessionID" and depth > 0:
            continue

        if ftype == "sessionID":
            result.append({
                "json_key": json_key,
                "go_type": "string",
                "required": True,
                "description": "세션 ID",
            })
        elif bt in SCALAR_ALIASES:
            info = SCALAR_ALIASES[bt]
            result.append({
                "json_key": json_key,
                "go_type": info["json_type"],
                "required": not optional,
                "description": info["description"],
            })
        elif is_primitive(ftype) or bt in PRIMITIVE_TYPES:
            result.append({
                "json_key": json_key,
                "go_type": ftype.lstrip("[]*"),
                "required": not optional,
                "array": ftype.startswith("[]"),
            })
        elif bt in struct_registry:
            # Expandable struct
            is_array = "[]" in ftype
            sub_fields = expand_struct(bt, depth + 1, visited)
            result.append({
                "json_key": json_key,
                "go_type": bt,
                "required": not optional,
                "array": is_array,
                "fields": sub_fields,
            })
        else:
            result.append({
                "json_key": json_key,
                "go_type": ftype,
                "required": not optional,
            })

    # Detect anonymous embedded structs from body
    body = s.get("body", "")
    known_field_names = {f["name"] for f in s["fields"]}
    for line in body.splitlines():
        stripped = line.strip()
        # Anonymous embedding: line has no spaces (just a type name)
        if stripped and " " not in stripped and stripped not in known_field_names:
            # Could be an embedded type name like "pagination" or "types.X"
            embed_type = stripped.split(".")[-1]
            # Capitalize first letter for lookup (pagination → Pagination)
            embed_lookup = embed_type[0].upper() + embed_type[1:] if embed_type else ""
            if embed_lookup in struct_registry or embed_type in struct_registry:
                lookup = embed_lookup if embed_lookup in struct_registry else embed_type
                sub_fields = expand_struct(lookup, depth + 1, visited)
                result.extend(sub_fields)

    return result


def make_schema(struct_name: str) -> dict | None:
    """Build a schema dict for a given struct name."""
    if struct_name not in struct_registry:
        return None
    fields = expand_struct(struct_name)
    return {
        "struct": struct_name,
        "fields": fields,
    }


# ──────────────────────────────────────────────────────────────
# Step 3: Load entry points and rule records
# ──────────────────────────────────────────────────────────────

with open(f"{REQ_ANALYSIS}/1_entry_points.json") as f:
    ep_data = json.load(f)

ep_map = {ep["ep_id"]: ep for ep in ep_data["entry_points"]}

with open(f"{REQ_ANALYSIS}/3_rule_records.json") as f:
    rr_data = json.load(f)

# Manual handler → struct name overrides
HANDLER_PARAM_OVERRIDES = {
    "addSpringRegistration": "addRegistrationParam",   # Spring variant reuses same param
    "updateLectureAttachment": "updateLectureAttachParam",
    "updateBoardAttachment": "updateBoardAttachParam",
    "HandleRequest": None,  # Background HTTP handler, no Param struct
}

# ──────────────────────────────────────────────────────────────
# Step 4: Add request_schema / response_schema to each Rule Record
# ──────────────────────────────────────────────────────────────

updated = 0
no_param = 0
no_resp = 0

for rr in rr_data["rule_records"]:
    ep_id = rr["entrypoint_id"]
    ep = ep_map.get(ep_id)
    if not ep:
        continue

    handler = ep.get("handler_symbol", "")
    if not handler:
        continue

    # Check manual overrides first
    if handler in HANDLER_PARAM_OVERRIDES:
        param_struct = HANDLER_PARAM_OVERRIDES[handler]
    else:
        # Param struct: {handler}Param (capitalize first letter)
        param_name = handler[0].upper() + handler[1:] + "Param" if handler else None
        # Also try lowercase first letter (most Go handler names start lowercase)
        param_name_lower = handler + "Param"

        # Try both capitalizations
        param_struct = None
        for candidate in [param_name_lower, param_name]:
            if candidate and candidate in struct_registry:
                param_struct = candidate
                break

    resp_name_lower = handler + "Resp"
    resp_name = handler[0].upper() + handler[1:] + "Resp" if handler else None
    resp_struct = None
    for candidate in [resp_name_lower, resp_name]:
        if candidate and candidate in struct_registry:
            resp_struct = candidate
            break

    if param_struct:
        rr["request_schema"] = make_schema(param_struct)
        updated += 1
    else:
        rr["request_schema"] = None
        no_param += 1
        print(f"  [WARN] No Param struct found for handler '{handler}' (EP: {ep_id})")

    if resp_struct:
        rr["response_schema"] = make_schema(resp_struct)
    else:
        rr["response_schema"] = None
        if ep.get("method") not in ["DELETE"] and "export" not in handler.lower():
            no_resp += 1

# ──────────────────────────────────────────────────────────────
# Step 5: Write updated rule records
# ──────────────────────────────────────────────────────────────

with open(f"{REQ_ANALYSIS}/3_rule_records.json", "w") as f:
    json.dump(rr_data, f, ensure_ascii=False, indent=2)

print(f"\nDone.")
print(f"  Updated with request_schema: {updated} rule records")
print(f"  No Param struct found: {no_param}")
print(f"  No Resp struct found: {no_resp}")
print(f"  Written to {REQ_ANALYSIS}/3_rule_records.json")
