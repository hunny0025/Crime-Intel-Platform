"""Config-driven ingestion adapter runner.

Given a source_format identifier and an input file, the runner:
1. Loads the matching YAML adapter config
2. Parses the input according to source_format
3. Applies field mappings and transforms
4. Returns a list of canonical records ready for the evidence write path
"""

import json
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.ingestion.transforms import get_transform
from app.ingestion.universal_parsers import (
    parse_cellebrite_xml,
    parse_cellebrite_json,
    parse_cellebrite_sqlite,
    parse_magnet_axiom_json,
    parse_magnet_axiom_sqlite,
    parse_ftk_csv,
    parse_xways_txt,
    parse_raw_sqlite,
    parse_raw_plist,
    parse_raw_xml,
    parse_raw_json,
)

logger = logging.getLogger(__name__)

# Directory containing adapter config YAML files
CONFIGS_DIR = Path(__file__).parent / "configs"


def load_adapter_config(source_format: str) -> dict:
    """Load a YAML adapter config by source_format name."""
    config_path = CONFIGS_DIR / f"{source_format}.yaml"
    if not config_path.exists():
        raise ValueError(f"No adapter config found for source_format: {source_format}")
    with open(config_path) as f:
        return yaml.safe_load(f)


def apply_mappings(row: dict, mappings: list[dict]) -> dict:
    """Apply field mappings and transforms to a single row."""
    result = {}
    for mapping in mappings:
        source_field = mapping["source_field"]
        canonical_field = mapping["canonical_field"]
        transform_name = mapping.get("transform")

        if source_field in row:
            value = row[source_field]
            transform_fn = get_transform(transform_name)
            try:
                result[canonical_field] = transform_fn(value)
            except Exception as e:
                logger.warning(
                    "Transform %s failed for field %s value %r: %s",
                    transform_name, source_field, value, e,
                )
                result[canonical_field] = value
    return result


def parse_autopsy_sqlite(file_bytes: bytes, config: dict) -> list[dict]:
    """
    Parse an Autopsy case SQLite file.
    Extracts tsk_files and blackboard_artifacts (TSK_WEB_HISTORY, TSK_MESSAGE).
    Returns a list of canonical records.
    """
    records = []

    # Write bytes to a temp file for sqlite3 to read
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        conn = sqlite3.connect(tmp_path)
        conn.row_factory = sqlite3.Row

        # Extract tsk_files
        try:
            cursor = conn.execute("SELECT * FROM tsk_files")
            file_mappings = config.get("file_mappings", [])
            for row in cursor:
                row_dict = dict(row)
                canonical = apply_mappings(row_dict, file_mappings)
                canonical["_source_table"] = "tsk_files"
                canonical["_canonical_output_type"] = config.get("output_types", {}).get(
                    "tsk_files", "generic_file"
                )
                canonical["_raw"] = {k: _serialize_value(v) for k, v in row_dict.items()}
                records.append(canonical)
        except sqlite3.OperationalError as e:
            logger.warning("Could not read tsk_files: %s", e)

        # Extract blackboard_artifacts with their attributes
        try:
            # Get artifacts of type TSK_WEB_HISTORY (4) and TSK_MESSAGE (12)
            cursor = conn.execute(
                """
                SELECT ba.artifact_id, ba.obj_id, ba.artifact_type_id,
                       CASE ba.artifact_type_id
                           WHEN 4 THEN 'TSK_WEB_HISTORY'
                           WHEN 12 THEN 'TSK_MESSAGE'
                       END as artifact_type_name
                FROM blackboard_artifacts ba
                WHERE ba.artifact_type_id IN (4, 12)
                """
            )
            artifact_rows = cursor.fetchall()

            artifact_mappings = config.get("artifact_mappings", [])

            for art_row in artifact_rows:
                art_dict = dict(art_row)
                # Get attributes for this artifact
                try:
                    attr_cursor = conn.execute(
                        "SELECT attribute_type_id, value_text, value_int32, value_int64 "
                        "FROM blackboard_attributes WHERE artifact_id = ?",
                        (art_dict["artifact_id"],),
                    )
                    attrs = {}
                    for attr in attr_cursor:
                        attr_dict = dict(attr)
                        # Use value_text if available, else int values
                        value = (
                            attr_dict.get("value_text")
                            or attr_dict.get("value_int64")
                            or attr_dict.get("value_int32")
                        )
                        attrs[str(attr_dict["attribute_type_id"])] = value
                    art_dict["value_text"] = json.dumps(attrs)
                except sqlite3.OperationalError:
                    art_dict["value_text"] = "{}"

                canonical = apply_mappings(art_dict, artifact_mappings)
                type_name = art_dict.get("artifact_type_name", "UNKNOWN")
                canonical["_source_table"] = "blackboard_artifacts"
                canonical["_canonical_output_type"] = config.get("output_types", {}).get(
                    type_name, "generic_file"
                )
                canonical["_raw"] = {k: _serialize_value(v) for k, v in art_dict.items()}
                records.append(canonical)

        except sqlite3.OperationalError as e:
            logger.warning("Could not read blackboard_artifacts: %s", e)

        conn.close()
    finally:
        os.unlink(tmp_path)

    return records


def _serialize_value(v: Any) -> Any:
    """Make a value JSON-serializable."""
    if isinstance(v, bytes):
        return v.hex()
    if isinstance(v, datetime):
        return v.isoformat()
    return v


# Registry of format parsers — all supported source_format identifiers
FORMAT_PARSERS = {
    # Existing Autopsy adapter
    "autopsy_sqlite": parse_autopsy_sqlite,
    # Cellebrite UFED formats
    "cellebrite_xml": parse_cellebrite_xml,
    "cellebrite_json": parse_cellebrite_json,
    "cellebrite_sqlite": parse_cellebrite_sqlite,
    # Magnet AXIOM formats
    "magnet_axiom_json": parse_magnet_axiom_json,
    "magnet_axiom_sqlite": parse_magnet_axiom_sqlite,
    # FTK and X-Ways reports
    "ftk_csv": parse_ftk_csv,
    "xways_txt": parse_xways_txt,
    # Raw device file formats (no third-party tool required)
    "raw_sqlite": parse_raw_sqlite,
    "raw_plist": parse_raw_plist,
    "raw_xml": parse_raw_xml,
    "raw_json": parse_raw_json,
}

# Formats that don't require a dedicated YAML config (they use heuristic extraction)
_CONFIG_OPTIONAL_FORMATS = {
    "cellebrite_xml", "cellebrite_json", "cellebrite_sqlite",
    "magnet_axiom_json", "magnet_axiom_sqlite",
    "ftk_csv", "xways_txt",
    "raw_sqlite", "raw_plist", "raw_xml", "raw_json",
}


def run_adapter(source_format: str, file_bytes: bytes) -> list[dict]:
    """
    Main entry point: load config (if available), parse input, return canonical records.
    Each record is a dict with canonical fields + _canonical_output_type metadata.
    Formats in _CONFIG_OPTIONAL_FORMATS work without a YAML config file.
    """
    if source_format in _CONFIG_OPTIONAL_FORMATS:
        try:
            config = load_adapter_config(source_format)
        except ValueError:
            config = {}  # use heuristic extraction — no YAML required
    else:
        config = load_adapter_config(source_format)

    parser = FORMAT_PARSERS.get(source_format)
    if parser is None:
        raise ValueError(
            f"No parser implemented for source_format: '{source_format}'. "
            f"Supported formats: {sorted(FORMAT_PARSERS.keys())}"
        )

    records = parser(file_bytes, config)
    logger.info(
        "Adapter %s produced %d canonical records", source_format, len(records)
    )
    return records
