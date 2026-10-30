import os
import sqlite3
import json
from typing import List, Dict, Any, Optional
from config import DB_PATH, AUDIO_DIR, SCREENSHOTS_DIR


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lessons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        status TEXT DEFAULT 'idle',
        started_at TIMESTAMP,
        ended_at TIMESTAMP,
        duration_seconds REAL DEFAULT 0,
        audio_filename TEXT,
        ai_summary TEXT,
        vocabulary_json TEXT,
        grammar_notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transcripts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lesson_id INTEGER NOT NULL,
        start_seconds REAL,
        end_seconds REAL,
        start_str TEXT,
        end_str TEXT,
        speaker TEXT DEFAULT 'Class',
        text TEXT NOT NULL,
        FOREIGN KEY (lesson_id) REFERENCES lessons (id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS screenshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lesson_id INTEGER NOT NULL,
        timestamp_seconds REAL,
        timestamp_str TEXT,
        filename TEXT NOT NULL,
        is_manual INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (lesson_id) REFERENCES lessons (id) ON DELETE CASCADE
    );
    """)

    # Migração: coluna de tradução PT-BR por linha de transcrição
    existing_cols = [row[1] for row in cursor.execute("PRAGMA table_info(transcripts)").fetchall()]
    if "translation" not in existing_cols:
        cursor.execute("ALTER TABLE transcripts ADD COLUMN translation TEXT")

    conn.commit()
    conn.close()


def update_transcript_translations(translations: List[tuple]):
    """Salva traduções. `translations` é uma lista de (transcript_id, texto_traduzido)."""
    conn = get_connection()
    conn.executemany(
        "UPDATE transcripts SET translation = ? WHERE id = ?",
        [(text, tid) for tid, text in translations if text],
    )
    conn.commit()
    conn.close()


def create_lesson(title: Optional[str] = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO lessons (title, status, started_at)
        VALUES (?, 'recording', CURRENT_TIMESTAMP)
    """, (title or "Aula de Inglês",))
    lesson_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return lesson_id


def update_lesson_status(
    lesson_id: int,
    status: str,
    duration_seconds: Optional[float] = None,
    audio_filename: Optional[str] = None
):
    conn = get_connection()
    cursor = conn.cursor()
    query = "UPDATE lessons SET status = ?"
    params = [status]

    if duration_seconds is not None:
        query += ", duration_seconds = ?, ended_at = CURRENT_TIMESTAMP"
        params.append(duration_seconds)
    if audio_filename is not None:
        query += ", audio_filename = ?"
        params.append(audio_filename)

    query += " WHERE id = ?"
    params.append(lesson_id)

    cursor.execute(query, tuple(params))
    conn.commit()
    conn.close()


def save_lesson_ai_analysis(
    lesson_id: int,
    summary: str,
    vocabulary_json: str,
    grammar_notes: str
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE lessons
        SET ai_summary = ?, vocabulary_json = ?, grammar_notes = ?, status = 'ready'
        WHERE id = ?
    """, (summary, vocabulary_json, grammar_notes, lesson_id))
    conn.commit()
    conn.close()


def save_transcripts(lesson_id: int, segments: List[Dict[str, Any]]):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transcripts WHERE lesson_id = ?", (lesson_id,))

    rows = []
    for seg in segments:
        rows.append((
            lesson_id,
            seg.get("start_seconds", 0.0),
            seg.get("end_seconds", 0.0),
            seg.get("start_str", "00:00:00"),
            seg.get("end_str", "00:00:00"),
            seg.get("speaker", "Class"),
            seg.get("text", "").strip()
        ))

    cursor.executemany("""
        INSERT INTO transcripts (
            lesson_id, start_seconds, end_seconds, start_str, end_str, speaker, text
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, rows)

    conn.commit()
    conn.close()


def save_screenshot_record(
    lesson_id: int,
    timestamp_seconds: float,
    timestamp_str: str,
    filename: str,
    is_manual: int = 0
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO screenshots (lesson_id, timestamp_seconds, timestamp_str, filename, is_manual)
        VALUES (?, ?, ?, ?, ?)
    """, (lesson_id, timestamp_seconds, timestamp_str, filename, is_manual))
    conn.commit()
    conn.close()


def get_all_lessons() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.*,
               (SELECT COUNT(*) FROM screenshots s WHERE s.lesson_id = l.id) AS screenshot_count,
               (SELECT COUNT(*) FROM transcripts t WHERE t.lesson_id = l.id) AS transcript_count
        FROM lessons l
        ORDER BY l.id DESC
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_lesson(lesson_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_lesson_transcripts(lesson_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM transcripts
        WHERE lesson_id = ?
        ORDER BY start_seconds ASC
    """, (lesson_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_lesson_screenshots(lesson_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM screenshots
        WHERE lesson_id = ?
        ORDER BY timestamp_seconds ASC
    """, (lesson_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def delete_lesson(lesson_id: int) -> bool:
    lesson = get_lesson(lesson_id)
    if not lesson:
        return False

    # Apaga arquivos de áudio
    if lesson.get("audio_filename"):
        audio_file = os.path.join(AUDIO_DIR, lesson["audio_filename"])
        if os.path.exists(audio_file):
            try:
                os.remove(audio_file)
            except Exception:
                pass

    # Apaga screenshots
    screenshots = get_lesson_screenshots(lesson_id)
    for s in screenshots:
        s_file = os.path.join(SCREENSHOTS_DIR, s["filename"])
        if os.path.exists(s_file):
            try:
                os.remove(s_file)
            except Exception:
                pass

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM screenshots WHERE lesson_id = ?", (lesson_id,))
    cursor.execute("DELETE FROM transcripts WHERE lesson_id = ?", (lesson_id,))
    cursor.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
    conn.commit()
    conn.close()
    return True
