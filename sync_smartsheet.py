#!/usr/bin/env python3
"""
sync_smartsheet.py
Fetches rows from the ENGIE Action Tracking Smartsheet and writes actions.json
that index.html loads on startup.
"""

import os
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
SHEET_ID   = "jPQ7vwCcv6QcPggMpMWc3vCQrPcgw9qM48mR5J31"
API_TOKEN  = os.environ["SMARTSHEET_API_TOKEN"]
OUTPUT     = "actions.json"

# Smartsheet column name → internal JS field name
COL_MAP = {
    "ID":                          "id",
    "Country":                     "country",
    "Topic":                       "topic",
    "Priority":                    "priority",
    "Source":                      "source",
    "Actions raised":              "raised",
    "Actions required":            "action",
    "TargetDueDate":               "targetDate",
    "CBRE":                        "ownerCBRE",
    "Engie":                       "ownerEngie",
    "Lead":                        "lead",
    "Last update":                 "lastUpdate",
    "Comments":                    "commentsRaw",
    "Status":                      "status",
    "Blocking point (yes or not)": "blocking",
    "Revised Target Date":         "revisedTargetDate",
    "Created By":                  "createdBy",
}

PRIORITY_MAP = {
    "P1": 1, "P1 – Critical": 1, "1": 1, "Critical": 1,
    "P2": 2, "P2 – High": 2,     "2": 2, "High": 2,
    "P3": 3, "P3 – Medium": 3,   "3": 3, "Medium": 3,
}

def api_get(path):
    url = f"https://api.smartsheet.com/2.0/{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {API_TOKEN}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def fmt_date(raw):
    if not raw:
        return ""
    raw = str(raw).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return raw

def parse_priority(raw):
    if not raw:
        return 0
    s = str(raw).strip()
    return PRIORITY_MAP.get(s, 0)

def parse_blocking(raw):
    if not raw:
        return ""
    s = str(raw).strip().upper()
    return "YES" if s in ("YES", "Y", "OUI", "TRUE", "1") else ""

def main():
    print(f"Fetching sheet {SHEET_ID} …")
    try:
        data = api_get(f"sheets/{SHEET_ID}")
    except urllib.error.HTTPError as e:
        print(f"ERROR: Smartsheet API returned {e.code}: {e.read().decode()}")
        sys.exit(1)

    col_lookup = {}
    for col in data.get("columns", []):
        title = col.get("title", "").strip()
        if title in COL_MAP:
            col_lookup[col["id"]] = COL_MAP[title]

    rows = data.get("rows", [])
    print(f"  Found {len(rows)} rows")

    records = []
    now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    for row in rows:
        rec = {
            "id":               None,
            "country":          "",
            "topic":            "",
            "priority":         0,
            "source":           "Smartsheet",
            "raised":           "",
            "action":           "",
            "targetDate":       "",
            "revisedTargetDate":"",
            "ownerCBRE":        "",
            "ownerEngie":       "",
            "lead":             "",
            "lastUpdate":       "",
            "status":           "Not Started",
            "blocking":         "",
            "createdBy":        "",
            "comments":         [],
            "createdAt":        now_str,
            "updatedAt":        now_str,
        }

        for cell in row.get("cells", []):
            field = col_lookup.get(cell.get("columnId"))
            if not field:
                continue
            val = cell.get("displayValue") or cell.get("value") or ""
            val = str(val).strip() if val else ""

            if field == "id":
                try:
                    rec["id"] = int(val)
                except (ValueError, TypeError):
                    rec["id"] = val
            elif field == "priority":
                rec["priority"] = parse_priority(val)
            elif field in ("targetDate", "revisedTargetDate"):
                rec[field] = fmt_date(val)
            elif field == "blocking":
                rec["blocking"] = parse_blocking(val)
            elif field == "commentsRaw":
                pass
            else:
                rec[field] = val

        if not rec["action"] and not rec["country"]:
            continue

        if rec["id"] is None:
            rec["id"] = row.get("rowNumber", 0)

        records.append(rec)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"  Written {len(records)} records → {OUTPUT}")

if __name__ == "__main__":
    main()
