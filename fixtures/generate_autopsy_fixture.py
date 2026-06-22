"""Generate a synthetic Autopsy-format SQLite database for testing.

Creates a minimal SQLite file with:
- tsk_files: 5 fake file metadata rows
- blackboard_artifacts: 3 rows (2 TSK_WEB_HISTORY, 1 TSK_MESSAGE)
- blackboard_attributes: corresponding attribute values
"""

import sqlite3
import os


def generate_autopsy_fixture(output_path: str = None) -> str:
    """Create the synthetic Autopsy test fixture and return its path."""
    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), "autopsy_test.db")

    # Remove existing file
    if os.path.exists(output_path):
        os.unlink(output_path)

    conn = sqlite3.connect(output_path)
    cursor = conn.cursor()

    # ── tsk_files table ──────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE tsk_files (
            obj_id INTEGER PRIMARY KEY,
            fs_obj_id INTEGER,
            name TEXT,
            parent_path TEXT,
            size INTEGER,
            crtime INTEGER,
            ctime INTEGER,
            atime INTEGER,
            mtime INTEGER,
            md5 TEXT,
            known INTEGER DEFAULT 0,
            type INTEGER DEFAULT 0
        )
    """)

    files = [
        (1, 1, "photo_001.jpg", "/DCIM/Camera/", 2048576, 1700000000, 1700000000, 1700001000, 1700001000, "a" * 32, 0, 0),
        (2, 1, "document.pdf", "/Documents/", 102400, 1700100000, 1700100000, 1700101000, 1700101000, "b" * 32, 0, 0),
        (3, 1, "chat_backup.db", "/WhatsApp/Databases/", 5242880, 1700200000, 1700200000, 1700201000, 1700201000, "c" * 32, 0, 0),
        (4, 1, "contacts.vcf", "/Contacts/", 8192, 1700300000, 1700300000, 1700301000, 1700301000, "d" * 32, 0, 0),
        (5, 1, "call_log.xml", "/Logs/", 4096, 1700400000, 1700400000, 1700401000, 1700401000, "e" * 32, 0, 0),
    ]
    cursor.executemany(
        "INSERT INTO tsk_files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        files,
    )

    # ── blackboard_artifacts table ───────────────────────────────────
    cursor.execute("""
        CREATE TABLE blackboard_artifacts (
            artifact_id INTEGER PRIMARY KEY,
            obj_id INTEGER,
            artifact_type_id INTEGER,
            review_status_id INTEGER DEFAULT 0
        )
    """)

    artifacts = [
        (1, 1, 4, 0),   # TSK_WEB_HISTORY
        (2, 2, 4, 0),   # TSK_WEB_HISTORY
        (3, 3, 12, 0),  # TSK_MESSAGE
    ]
    cursor.executemany(
        "INSERT INTO blackboard_artifacts VALUES (?, ?, ?, ?)",
        artifacts,
    )

    # ── blackboard_attributes table ──────────────────────────────────
    cursor.execute("""
        CREATE TABLE blackboard_attributes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artifact_id INTEGER,
            attribute_type_id INTEGER,
            value_text TEXT,
            value_int32 INTEGER,
            value_int64 INTEGER,
            FOREIGN KEY (artifact_id) REFERENCES blackboard_artifacts(artifact_id)
        )
    """)

    # Attribute type IDs (simplified from Sleuth Kit):
    # 1 = TSK_URL, 2 = TSK_DATETIME_ACCESSED, 3 = TSK_TITLE
    # 32 = TSK_TEXT (message body), 33 = TSK_PHONE_NUMBER
    attributes = [
        # Web history 1
        (1, 1, "https://example.com/search?q=evidence", None, None),
        (1, 2, None, None, 1700050000),
        (1, 3, "Example Search Results", None, None),
        # Web history 2
        (2, 1, "https://suspicious-site.org/page", None, None),
        (2, 2, None, None, 1700060000),
        (2, 3, "Suspicious Page Title", None, None),
        # Message
        (3, 32, "Meet me at the warehouse at 9pm", None, None),
        (3, 33, "+1-555-0142", None, None),
        (3, 2, None, None, 1700070000),
    ]
    cursor.executemany(
        "INSERT INTO blackboard_attributes (artifact_id, attribute_type_id, value_text, value_int32, value_int64) VALUES (?, ?, ?, ?, ?)",
        attributes,
    )

    conn.commit()
    conn.close()

    print(f"Generated Autopsy test fixture at: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_autopsy_fixture()
