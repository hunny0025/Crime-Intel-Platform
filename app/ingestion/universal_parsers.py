"""Universal forensic evidence parsers.

Provides native parsing of the most common forensic tool export formats and
raw device file types, allowing the platform to ingest evidence without first
requiring a third-party extraction tool.

Supported source formats:
  cellebrite_xml     — UFED Analytics XML exports
  cellebrite_json    — UFED Touch JSON exports
  cellebrite_sqlite  — UFED physical SQLite databases
  magnet_axiom_json  — AXIOM JSON case exports
  magnet_axiom_sqlite — AXIOM SQLite artifact stores
  ftk_csv            — FTK Imager/Forensic Toolkit CSV reports
  xways_txt          — X-Ways Forensics report text files
  raw_sqlite         — Any raw SQLite database (app-level dumps)
  raw_plist          — Apple binary/XML property list files
  raw_xml            — Generic XML structured files
  raw_json           — Generic JSON structured files
"""

import csv
import io
import json
import logging
import os
import plistlib
import re
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────

def _serialize(v: Any) -> Any:
    """Make value JSON-serialisable."""
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8", errors="replace")
        except Exception:
            return v.hex()
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sqlite_to_records(tmp_path: str, table_filter: list[str] | None = None) -> list[dict]:
    """Dump rows from every table (or a filtered subset) into flat dicts."""
    records = []
    try:
        conn = sqlite3.connect(tmp_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        for tbl in tables:
            if table_filter and tbl not in table_filter:
                continue
            try:
                rows = conn.execute(f"SELECT * FROM \"{tbl}\"").fetchall()
                for row in rows:
                    record = {
                        "_source_table": tbl,
                        "_canonical_output_type": "generic_file",
                        "_raw": {k: _serialize(row[k]) for k in row.keys()},
                    }
                    records.append(record)
            except sqlite3.OperationalError as e:
                logger.warning("Could not read table %s: %s", tbl, e)
        conn.close()
    except Exception as e:
        logger.error("SQLite dump failed: %s", e)
    return records


def _write_tmp(file_bytes: bytes, suffix: str = ".tmp") -> str:
    """Write bytes to a temp file and return the path."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(file_bytes)
        return f.name


# ── Cellebrite XML Parser ─────────────────────────────────────────────────

def parse_cellebrite_xml(file_bytes: bytes, config: dict) -> list[dict]:
    """
    Parse a UFED Analytics XML export.
    Extracts <model>, <field>, and <multiField> elements into flat records.
    Each top-level <model> becomes one canonical record.
    """
    records = []
    try:
        root = ET.fromstring(file_bytes.decode("utf-8", errors="replace"))
    except ET.ParseError as e:
        logger.error("Cellebrite XML parse error: %s", e)
        return records

    # Walk all <model> elements regardless of namespace depth
    for model_el in root.iter("model"):
        model_type = model_el.get("type", "unknown")
        rec: dict = {
            "_source_table": model_type,
            "_canonical_output_type": _cellebrite_output_type(model_type),
        }
        raw: dict = {"model_type": model_type}

        for field in model_el.iter("field"):
            name = field.get("name", "")
            value = field.text or ""
            raw[name] = value
            # Map well-known Cellebrite field names
            if name in ("TimeStamp", "Timestamp", "Date"):
                rec["collection_timestamp_utc"] = _parse_ts(value)
            elif name in ("PhoneNumber", "FromIdentifier", "To"):
                rec["phone"] = value
            elif name == "Body":
                rec["content"] = value
            elif name == "Source":
                rec["source_app"] = value

        for mf in model_el.iter("multiField"):
            name = mf.get("name", "")
            values = [v.text or "" for v in mf.iter("value")]
            raw[name] = values

        rec["_raw"] = raw
        records.append(rec)

    logger.info("Cellebrite XML: extracted %d model records", len(records))
    return records


def _cellebrite_output_type(model_type: str) -> str:
    t = model_type.lower()
    if "sms" in t or "message" in t or "chat" in t or "call" in t:
        return "communication_record"
    if "location" in t or "gps" in t:
        return "location_record"
    return "generic_file"


# ── Cellebrite JSON Parser ────────────────────────────────────────────────

def parse_cellebrite_json(file_bytes: bytes, config: dict) -> list[dict]:
    """Parse a UFED Touch/PA JSON export — array of artifact objects."""
    records = []
    try:
        data = json.loads(file_bytes.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        logger.error("Cellebrite JSON parse error: %s", e)
        return records

    artifacts = data if isinstance(data, list) else data.get("artifacts", data.get("items", []))

    for item in artifacts:
        if not isinstance(item, dict):
            continue
        rec = {
            "_source_table": item.get("type", "cellebrite_artifact"),
            "_canonical_output_type": _cellebrite_output_type(item.get("type", "")),
            "_raw": {k: _serialize(v) for k, v in item.items()},
        }
        # Map common fields
        for ts_key in ("timestamp", "timeStamp", "dateTime", "date"):
            if ts_key in item:
                rec["collection_timestamp_utc"] = _parse_ts(str(item[ts_key]))
                break
        for body_key in ("body", "content", "text", "message"):
            if body_key in item:
                rec["content"] = str(item[body_key])
                break
        records.append(rec)

    logger.info("Cellebrite JSON: extracted %d records", len(records))
    return records


# ── Cellebrite SQLite Parser ──────────────────────────────────────────────

def parse_cellebrite_sqlite(file_bytes: bytes, config: dict) -> list[dict]:
    """
    Parse a Cellebrite physical SQLite database.
    Targets tables: Messages, Calls, Contacts, Locations.
    Falls back to a full dump if those tables are absent.
    """
    tmp = _write_tmp(file_bytes, ".db")
    try:
        target_tables = ["Messages", "Calls", "Contacts", "Locations",
                         "messages", "calls", "contacts", "locations"]
        records = _sqlite_to_records(tmp, table_filter=target_tables)
        if not records:
            records = _sqlite_to_records(tmp)  # full dump fallback
        # Annotate output types
        for rec in records:
            tbl = rec.get("_source_table", "").lower()
            if "message" in tbl or "call" in tbl:
                rec["_canonical_output_type"] = "communication_record"
            elif "location" in tbl:
                rec["_canonical_output_type"] = "location_record"
        logger.info("Cellebrite SQLite: extracted %d records", len(records))
        return records
    finally:
        os.unlink(tmp)


# ── Magnet AXIOM JSON Parser ──────────────────────────────────────────────

def parse_magnet_axiom_json(file_bytes: bytes, config: dict) -> list[dict]:
    """
    Parse a Magnet AXIOM case export (JSON).
    AXIOM exports wrap artifacts under a 'cases' → 'artifacts' hierarchy.
    """
    records = []
    try:
        data = json.loads(file_bytes.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        logger.error("AXIOM JSON parse error: %s", e)
        return records

    # Flatten regardless of nesting depth
    artifact_list = []
    if isinstance(data, list):
        artifact_list = data
    elif isinstance(data, dict):
        # Try common AXIOM keys
        for key in ("artifacts", "evidenceItems", "items", "results"):
            if key in data and isinstance(data[key], list):
                artifact_list = data[key]
                break
        if not artifact_list:
            artifact_list = [data]

    for item in artifact_list:
        if not isinstance(item, dict):
            continue
        category = item.get("category", item.get("artifactType", "axiom_artifact"))
        rec = {
            "_source_table": category,
            "_canonical_output_type": _axiom_output_type(category),
            "_raw": {k: _serialize(v) for k, v in item.items()},
        }
        for ts_key in ("timestamp", "dateCreated", "date", "modifiedTime"):
            if ts_key in item:
                rec["collection_timestamp_utc"] = _parse_ts(str(item[ts_key]))
                break
        for body_key in ("content", "body", "text", "detail"):
            if body_key in item:
                rec["content"] = str(item[body_key])
                break
        records.append(rec)

    logger.info("AXIOM JSON: extracted %d records", len(records))
    return records


def _axiom_output_type(category: str) -> str:
    c = category.lower()
    if any(k in c for k in ("chat", "message", "sms", "email", "call")):
        return "communication_record"
    if any(k in c for k in ("location", "gps", "wifi")):
        return "location_record"
    if "browser" in c or "history" in c:
        return "browser_record"
    return "generic_file"


# ── Magnet AXIOM SQLite Parser ────────────────────────────────────────────

def parse_magnet_axiom_sqlite(file_bytes: bytes, config: dict) -> list[dict]:
    """
    Parse a Magnet AXIOM artifact SQLite store.
    Targets: browserhistory, chats, artifacts, evidence.
    """
    tmp = _write_tmp(file_bytes, ".db")
    try:
        axiom_tables = ["browserhistory", "chats", "artifacts", "evidence",
                        "BrowserHistory", "Chats", "Artifacts", "Evidence"]
        records = _sqlite_to_records(tmp, table_filter=axiom_tables)
        if not records:
            records = _sqlite_to_records(tmp)
        for rec in records:
            tbl = rec.get("_source_table", "").lower()
            rec["_canonical_output_type"] = _axiom_output_type(tbl)
        logger.info("AXIOM SQLite: extracted %d records", len(records))
        return records
    finally:
        os.unlink(tmp)


# ── FTK CSV Parser ────────────────────────────────────────────────────────

def parse_ftk_csv(file_bytes: bytes, config: dict) -> list[dict]:
    """
    Parse a FTK Imager / Forensic Toolkit CSV file listing.
    Each row represents a file with metadata columns (Name, Path, Size, MD5, etc.)
    """
    records = []
    try:
        text = file_bytes.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        col_map = config.get("file_mappings", [])

        for row in reader:
            raw = {k: v for k, v in row.items()}
            rec: dict = {
                "_source_table": "ftk_file_listing",
                "_canonical_output_type": "generic_file",
                "_raw": raw,
            }
            # Apply config field mappings if present
            if col_map:
                from app.ingestion.runner import apply_mappings
                mapped = apply_mappings(raw, col_map)
                rec.update(mapped)
            else:
                # Heuristic field extraction
                for name_col in ("Name", "Filename", "File Name"):
                    if name_col in raw:
                        rec["file_name"] = raw[name_col].lower()
                        break
                for path_col in ("Path", "Full Path", "Location"):
                    if path_col in raw:
                        rec["file_path"] = raw[path_col]
                        break
                for size_col in ("Size", "File Size", "Logical Size"):
                    if size_col in raw:
                        rec["file_size"] = raw[size_col]
                        break
                for hash_col in ("MD5", "SHA1", "SHA256", "Hash"):
                    if hash_col in raw:
                        rec["file_hash"] = raw[hash_col]
                        break
                for ts_col in ("Created", "Modified", "Date Created", "Last Modified"):
                    if ts_col in raw and raw[ts_col]:
                        rec["collection_timestamp_utc"] = _parse_ts(raw[ts_col])
                        break
            records.append(rec)
    except Exception as e:
        logger.error("FTK CSV parse error: %s", e)

    logger.info("FTK CSV: extracted %d records", len(records))
    return records


# ── X-Ways TXT Parser ─────────────────────────────────────────────────────

def parse_xways_txt(file_bytes: bytes, config: dict) -> list[dict]:
    """
    Parse an X-Ways Forensics report text file.
    X-Ways exports one file per line in a tab-separated format with a
    header block followed by data lines.
    """
    records = []
    try:
        text = file_bytes.decode("utf-8", errors="replace")
        lines = text.splitlines()

        headers: list[str] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("#"):
                continue
            parts = stripped.split("\t")
            if not headers:
                headers = [h.strip() for h in parts]
                continue
            if len(parts) >= len(headers):
                row = {headers[j]: parts[j].strip() for j in range(len(headers))}
            else:
                row = {headers[j]: parts[j].strip() if j < len(parts) else "" for j in range(len(headers))}

            rec: dict = {
                "_source_table": "xways_file_listing",
                "_canonical_output_type": "generic_file",
                "_raw": row,
            }
            # Heuristic mapping
            for name_col in ("Name", "Filename", "Item"):
                if name_col in row:
                    rec["file_name"] = row[name_col].lower()
                    break
            for hash_col in ("MD5", "SHA-1", "SHA1", "Hash"):
                if hash_col in row and row[hash_col]:
                    rec["file_hash"] = row[hash_col]
                    break
            for ts_col in ("Created", "Modified", "Written", "Timestamp"):
                if ts_col in row and row[ts_col]:
                    rec["collection_timestamp_utc"] = _parse_ts(row[ts_col])
                    break
            records.append(rec)
    except Exception as e:
        logger.error("X-Ways TXT parse error: %s", e)

    logger.info("X-Ways TXT: extracted %d records", len(records))
    return records


# ── Raw SQLite Parser ─────────────────────────────────────────────────────

def parse_raw_sqlite(file_bytes: bytes, config: dict) -> list[dict]:
    """
    Parse any arbitrary SQLite database file (app DBs, WhatsApp, Signal, etc.).
    Dumps all tables unless config specifies a table_filter list.
    """
    tmp = _write_tmp(file_bytes, ".db")
    try:
        table_filter = config.get("table_filter")
        records = _sqlite_to_records(tmp, table_filter=table_filter)
        logger.info("Raw SQLite: extracted %d records from %d tables",
                    len(records), len(set(r["_source_table"] for r in records)))
        return records
    finally:
        os.unlink(tmp)


# ── Raw Plist Parser ──────────────────────────────────────────────────────

def parse_raw_plist(file_bytes: bytes, config: dict) -> list[dict]:
    """
    Parse an Apple binary or XML plist file.
    Flattens the property tree into a single canonical record (or a list
    of records if the root is an array).
    """
    records = []
    try:
        data = plistlib.loads(file_bytes)
    except Exception as e:
        logger.error("Plist parse error: %s", e)
        return records

    def _flatten(obj: Any, prefix: str = "") -> dict:
        result = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                result.update(_flatten(v, f"{prefix}{k}."))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                result.update(_flatten(v, f"{prefix}{i}."))
        else:
            result[prefix.rstrip(".")] = _serialize(obj)
        return result

    items = data if isinstance(data, list) else [data]
    for item in items:
        flat = _flatten(item)
        rec = {
            "_source_table": "plist_root",
            "_canonical_output_type": "generic_file",
            "_raw": flat,
        }
        records.append(rec)

    logger.info("Plist: extracted %d records", len(records))
    return records


# ── Raw XML Parser ────────────────────────────────────────────────────────

def parse_raw_xml(file_bytes: bytes, config: dict) -> list[dict]:
    """
    Parse a generic XML file. Each child element of the root becomes a record.
    Attributes and text content are captured in _raw.
    """
    records = []
    try:
        root = ET.fromstring(file_bytes.decode("utf-8", errors="replace"))
    except ET.ParseError as e:
        logger.error("Raw XML parse error: %s", e)
        return records

    child_tag = config.get("record_element")  # optional hint from YAML

    for child in root:
        if child_tag and child.tag != child_tag:
            continue
        raw: dict = dict(child.attrib)
        raw["_text"] = child.text or ""
        for sub in child:
            raw[sub.tag] = sub.text or ""
        rec = {
            "_source_table": child.tag,
            "_canonical_output_type": "generic_file",
            "_raw": raw,
        }
        records.append(rec)

    logger.info("Raw XML: extracted %d records", len(records))
    return records


# ── Raw JSON Parser ───────────────────────────────────────────────────────

def parse_raw_json(file_bytes: bytes, config: dict) -> list[dict]:
    """
    Parse a generic JSON file. Handles both array and object roots.
    Uses a config 'items_path' (dot-separated) to drill into nested objects.
    """
    records = []
    try:
        data = json.loads(file_bytes.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        logger.error("Raw JSON parse error: %s", e)
        return records

    # Navigate to the items list
    items_path: str | None = config.get("items_path")
    if items_path:
        for key in items_path.split("."):
            if isinstance(data, dict):
                data = data.get(key, [])
    items = data if isinstance(data, list) else [data]

    for item in items:
        if not isinstance(item, dict):
            item = {"value": _serialize(item)}
        rec = {
            "_source_table": "json_record",
            "_canonical_output_type": "generic_file",
            "_raw": {k: _serialize(v) for k, v in item.items()},
        }
        # Common timestamp auto-detection
        for ts_key in ("timestamp", "time", "date", "created_at", "updated_at"):
            if ts_key in item and item[ts_key]:
                rec["collection_timestamp_utc"] = _parse_ts(str(item[ts_key]))
                break
        records.append(rec)

    logger.info("Raw JSON: extracted %d records", len(records))
    return records


# ── Timestamp Parser ──────────────────────────────────────────────────────

_TS_FORMATS = [
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
]


def _parse_ts(value: str) -> str | None:
    """Try to parse a timestamp string into ISO UTC format. Returns None on failure."""
    if not value or value.strip() in ("", "None", "null"):
        return None
    value = value.strip()

    # Unix epoch (int)
    try:
        epoch = float(value)
        if 1_000_000_000 < epoch < 2_000_000_000:
            return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    except ValueError:
        pass

    # ISO with timezone
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass

    # Attempt known formats
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    return None
