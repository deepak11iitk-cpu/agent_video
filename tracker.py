"""
FlowTribes Scout - Event Tracker Module
SQLite-based tracker to manage discovered events and application status.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path


DB_PATH = "flowtribes_scout.db"


class EventTracker:
    """Manages events in a local SQLite database."""

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    date TEXT,
                    location TEXT,
                    city TEXT,
                    country TEXT,
                    event_type TEXT,
                    url TEXT,
                    source TEXT,
                    description TEXT DEFAULT '',
                    organizer TEXT DEFAULT '',
                    contact_email TEXT DEFAULT '',
                    application_url TEXT DEFAULT '',
                    deadline TEXT DEFAULT '',
                    status TEXT DEFAULT 'discovered',
                    notes TEXT DEFAULT '',
                    discovered_at TEXT,
                    updated_at TEXT,
                    UNIQUE(name, date, location)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    workshop_type TEXT,
                    proposal_text TEXT,
                    sent_at TEXT,
                    response TEXT DEFAULT '',
                    response_at TEXT,
                    status TEXT DEFAULT 'draft',
                    FOREIGN KEY (event_id) REFERENCES events(id)
                )
            """)
            conn.commit()

    def add_event(self, event_dict):
        """Add a new event to the tracker. Skips duplicates."""
        now = datetime.now().isoformat()
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO events
                    (name, date, location, city, country, event_type, url, source,
                     description, organizer, contact_email, application_url, deadline,
                     status, notes, discovered_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event_dict.get("name", ""),
                    event_dict.get("date", ""),
                    event_dict.get("location", ""),
                    event_dict.get("city", ""),
                    event_dict.get("country", ""),
                    event_dict.get("event_type", ""),
                    event_dict.get("url", ""),
                    event_dict.get("source", ""),
                    event_dict.get("description", ""),
                    event_dict.get("organizer", ""),
                    event_dict.get("contact_email", ""),
                    event_dict.get("application_url", ""),
                    event_dict.get("deadline", ""),
                    event_dict.get("status", "discovered"),
                    event_dict.get("notes", ""),
                    event_dict.get("discovered_at", now),
                    now,
                ))
                conn.commit()
                return True
        except sqlite3.Error:
            return False

    def bulk_add_events(self, events):
        """Add multiple events at once. Returns count of newly added."""
        added = 0
        for event in events:
            if isinstance(event, dict):
                event_dict = event
            else:
                event_dict = event.to_dict()
            if self.add_event(event_dict):
                added += 1
        return added

    def get_all_events(self, status=None):
        """Get all events, optionally filtered by status."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    "SELECT * FROM events WHERE status = ? ORDER BY date", (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events ORDER BY date"
                ).fetchall()
            return [dict(row) for row in rows]

    def get_event(self, event_id):
        """Get a single event by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
            return dict(row) if row else None

    def update_status(self, event_id, status, notes=""):
        """Update event status (discovered/interested/applied/accepted/rejected)."""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE events SET status = ?, notes = ?, updated_at = ? WHERE id = ?",
                (status, notes, now, event_id),
            )
            conn.commit()

    def search_events(self, keyword):
        """Search events by keyword in name, description, or location."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM events
                WHERE name LIKE ? OR description LIKE ? OR location LIKE ? OR event_type LIKE ?
                ORDER BY date
            """, (f"%{keyword}%",) * 4).fetchall()
            return [dict(row) for row in rows]

    def get_stats(self):
        """Get summary statistics."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            by_status = {}
            for row in conn.execute("SELECT status, COUNT(*) FROM events GROUP BY status"):
                by_status[row[0]] = row[1]
            by_country = {}
            for row in conn.execute("SELECT country, COUNT(*) FROM events GROUP BY country ORDER BY COUNT(*) DESC LIMIT 10"):
                by_country[row[0]] = row[1]
            by_type = {}
            for row in conn.execute("SELECT event_type, COUNT(*) FROM events GROUP BY event_type ORDER BY COUNT(*) DESC LIMIT 10"):
                by_type[row[0]] = row[1]
            return {
                "total": total,
                "by_status": by_status,
                "by_country": by_country,
                "by_type": by_type,
            }

    def save_application(self, event_id, workshop_type, proposal_text):
        """Save a workshop application/proposal."""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO applications (event_id, workshop_type, proposal_text, sent_at, status)
                VALUES (?, ?, ?, ?, 'draft')
            """, (event_id, workshop_type, proposal_text, now))
            conn.commit()

    def get_applications(self, event_id=None):
        """Get all applications, optionally for a specific event."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if event_id:
                rows = conn.execute(
                    "SELECT * FROM applications WHERE event_id = ?", (event_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM applications").fetchall()
            return [dict(row) for row in rows]

    def delete_event(self, event_id):
        """Delete an event by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM applications WHERE event_id = ?", (event_id,))
            conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
            conn.commit()
