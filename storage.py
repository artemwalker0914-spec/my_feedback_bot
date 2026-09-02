"""
Слой хранения данных бота «ЮНИВЁРСУМ» на SQLite.
"""

import sqlite3
import time
from contextlib import closing
from typing import Optional, List, Tuple

ROLE_STUDENT = "student"
ROLE_PARENT = "parent"
ROLE_TEACHER = "teacher"

ROLE_LABELS_RU = {
    ROLE_STUDENT: "Ученика",
    ROLE_PARENT: "Родителя",
    ROLE_TEACHER: "Преподавателя",
}

ROLE_NAMES_RU = {
    ROLE_STUDENT: "ученик",
    ROLE_PARENT: "родитель",
    ROLE_TEACHER: "преподаватель",
}


class Storage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with closing(self._conn.cursor()) as cur:
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS rooms (
                    room_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id   INTEGER UNIQUE,
                    name        TEXT,
                    created_by  INTEGER,
                    created_at  REAL
                );

                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER PRIMARY KEY,
                    username    TEXT,
                    full_name   TEXT,
                    role        TEXT,
                    room_id     INTEGER
                );

                CREATE TABLE IF NOT EXISTS pending_invites (
                    invite_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id         INTEGER,
                    role            TEXT,
                    target_user_id  INTEGER,
                    target_username TEXT,
                    invited_by      INTEGER,
                    created_at      REAL
                );

                CREATE TABLE IF NOT EXISTS message_map (
                    group_message_id INTEGER,
                    thread_id         INTEGER,
                    user_id           INTEGER,
                    PRIMARY KEY (group_message_id, thread_id)
                );
                """
            )
            self._conn.commit()

    # ---------------- rooms ----------------

    def create_room(self, thread_id: int, name: str, created_by: int) -> int:
        with closing(self._conn.cursor()) as cur:
            cur.execute(
                "INSERT INTO rooms (thread_id, name, created_by, created_at) VALUES (?, ?, ?, ?)",
                (thread_id, name, created_by, time.time()),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_room_by_thread(self, thread_id: int) -> Optional[sqlite3.Row]:
        with closing(self._conn.cursor()) as cur:
            cur.execute("SELECT * FROM rooms WHERE thread_id = ?", (thread_id,))
            return cur.fetchone()

    def get_room(self, room_id: int) -> Optional[sqlite3.Row]:
        with closing(self._conn.cursor()) as cur:
            cur.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,))
            return cur.fetchone()

    def get_room_members(self, room_id: int) -> List[sqlite3.Row]:
        with closing(self._conn.cursor()) as cur:
            cur.execute("SELECT * FROM users WHERE room_id = ?", (room_id,))
            return cur.fetchall()

    def update_thread_id(self, room_id: int, new_thread_id: int):
        with closing(self._conn.cursor()) as cur:
            cur.execute("UPDATE rooms SET thread_id = ? WHERE room_id = ?", (new_thread_id, room_id))
            self._conn.commit()

    def clear_user_room(self, user_id: int):
        with closing(self._conn.cursor()) as cur:
            cur.execute("UPDATE users SET room_id = NULL WHERE user_id = ?", (user_id,))
            self._conn.commit()

    def clear_pending_invite(self, invite_id: int):
        with closing(self._conn.cursor()) as cur:
            cur.execute("DELETE FROM pending_invites WHERE invite_id = ?", (invite_id,))
            self._conn.commit()

    # ---------------- users ----------------

    def get_user(self, user_id: int) -> Optional[sqlite3.Row]:
        with closing(self._conn.cursor()) as cur:
            cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            return cur.fetchone()

    def find_user_by_username(self, username: str) -> Optional[sqlite3.Row]:
        with closing(self._conn.cursor()) as cur:
            cur.execute(
                "SELECT * FROM users WHERE lower(username) = lower(?)", (username,)
            )
            return cur.fetchone()

    def upsert_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        full_name: Optional[str] = None,
        role: Optional[str] = None,
        room_id: Optional[int] = None,
    ):
        existing = self.get_user(user_id)
        with closing(self._conn.cursor()) as cur:
            if existing is None:
                cur.execute(
                    "INSERT INTO users (user_id, username, full_name, role, room_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, username, full_name, role, room_id),
                )
            else:
                new_username = username if username is not None else existing["username"]
                new_full_name = full_name if full_name is not None else existing["full_name"]
                new_role = role if role is not None else existing["role"]
                new_room_id = room_id if room_id is not None else existing["room_id"]
                cur.execute(
                    "UPDATE users SET username=?, full_name=?, role=?, room_id=? WHERE user_id=?",
                    (new_username, new_full_name, new_role, new_room_id, user_id),
                )
            self._conn.commit()

    def set_role(self, user_id: int, role: str):
        with closing(self._conn.cursor()) as cur:
            cur.execute("UPDATE users SET role=? WHERE user_id=?", (role, user_id))
            self._conn.commit()

    # ---------------- pending invites ----------------

    def add_pending_invite(
        self,
        room_id: int,
        role: str,
        invited_by: int,
        target_user_id: Optional[int] = None,
        target_username: Optional[str] = None,
    ):
        with closing(self._conn.cursor()) as cur:
            cur.execute(
                "INSERT INTO pending_invites (room_id, role, target_user_id, target_username, invited_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (room_id, role, target_user_id, target_username, invited_by, time.time()),
            )
            self._conn.commit()

    def pop_pending_invite_for(self, user_id: int, username: Optional[str]) -> Optional[sqlite3.Row]:
        with closing(self._conn.cursor()) as cur:
            cur.execute("SELECT * FROM pending_invites WHERE target_user_id = ?", (user_id,))
            row = cur.fetchone()
            if row is None and username:
                cur.execute(
                    "SELECT * FROM pending_invites WHERE lower(target_username) = lower(?)",
                    (username,),
                )
                row = cur.fetchone()
            if row is not None:
                cur.execute("DELETE FROM pending_invites WHERE invite_id = ?", (row["invite_id"],))
                self._conn.commit()
            return row

    # ---------------- message routing map ----------------

    def save_message_map(self, group_message_id: int, thread_id: int, user_id: int):
        with closing(self._conn.cursor()) as cur:
            cur.execute(
                "INSERT OR REPLACE INTO message_map (group_message_id, thread_id, user_id) VALUES (?, ?, ?)",
                (group_message_id, thread_id, user_id),
            )
            self._conn.commit()

    def get_message_author(self, group_message_id: int, thread_id: int) -> Optional[int]:
        with closing(self._conn.cursor()) as cur:
            cur.execute(
                "SELECT user_id FROM message_map WHERE group_message_id = ? AND thread_id = ?",
                (group_message_id, thread_id),
            )
            row = cur.fetchone()
            return row["user_id"] if row else None