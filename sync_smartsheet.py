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
 
def api_get(path, params=None):
    url = f"https://api.smartsheet.com/2.0/{path}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"
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
        data = api_get(f"sheets/{SHEET_ID}", {"pageSize": 1000, "include": "rowPermalink"})
    except urllib.error.HTTPError as e:
        print(f"ERROR: Smartsheet API returned {e.code}: {e.read().decode()}")
        sys.exit(1)
 
    # ── Column mapping ────────────────────────────────────────────────────────
    col_lookup = {}
    print("  Columns found in sheet:")
    for col in data.get("columns", []):
        title = col.get("title", "").strip()
        mapped = COL_MAP.get(title)
        print(f"    [{col['id']}] '{title}' → {mapped if mapped else '(not mapped)'}")
        if mapped:
            col_lookup[col["id"]] = mapped
 
    # ── Row count check ───────────────────────────────────────────────────────
    total_row_count = data.get("totalRowCount", "?")
    rows = data.get("rows", [])
    print(f"  API reports {total_row_count} total rows, returned {len(rows)} in this response")
 
    if isinstance(total_row_count, int) and len(rows) < total_row_count:
        print(f"  WARNING: Only got {len(rows)} of {total_row_count} rows — pagination may be needed!")
 
    records = []
    skipped = []
    now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
 
    for row in rows:
        row_num = row.get("rowNumber", "?")
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
 
        # ── Skip only truly empty rows (no action AND no country) ─────────────
        if not rec["action"] and not rec["country"]:
            reason = "both 'action' and 'country' are empty"
            print(f"  SKIP row {row_num} (Smartsheet rowNumber): {reason}")
            skipped.append({"rowNumber": row_num, "reason": reason, "mapped": {k: rec[k] for k in ("action", "country", "topic")}})
            continue
 
        if rec["id"] is None:
            rec["id"] = row.get("rowNumber", 0)
 
        records.append(rec)
 
    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n  ── Summary ──")
    print(f"  Rows from API : {len(rows)}")
    print(f"  Rows written  : {len(records)}")
    print(f"  Rows skipped  : {len(skipped)}")
    if skipped:
        print("  Skipped rows detail:")
        for s in skipped:
            print(f"    Row {s['rowNumber']}: {s['reason']} | mapped values: {s['mapped']}")
 
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
 
    print(f"\n  Written {len(records)} records → {OUTPUT}")
 
if __name__ == "__main__":
    main()
