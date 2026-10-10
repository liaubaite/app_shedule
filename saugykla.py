"""Supabase PostgREST – patvari, suspausta SQLite duomenų bazės kopija.

Skirta vienam redaktoriui ir dviem skaitytojams viename Streamlit procese.
Pagal nutylėjimą vietinė SQLite; debesyje būtina SUPABASE_URL ir
SUPABASE_SERVICE_ROLE_KEY iš Streamlit Secrets.
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
import tempfile
import urllib.error
import urllib.request
import zlib
from pathlib import Path


def read_setting(name: str) -> str:
    env = os.getenv(name, "")
    if env:
        return env
    try:
        import streamlit as st
        return str(st.secrets.get(name, "") or "")
    except (FileNotFoundError, RuntimeError, AttributeError):
        return ""


def remote_configured() -> bool:
    return bool(read_setting("SUPABASE_URL") and read_setting("SUPABASE_SERVICE_ROLE_KEY"))


def _call(method: str, payload: dict | None = None) -> list | None:
    url = read_setting("SUPABASE_URL").rstrip("/")
    key = read_setting("SUPABASE_SERVICE_ROLE_KEY")
    if not url.startswith("https://") or not key:
        raise ValueError("Supabase saugyklai reikalingas HTTPS URL ir paslaptis.")
    resource = url + "/rest/v1/app_state"
    if method == "GET":
        resource += "?id=eq.main&select=payload"
    else:
        resource += "?on_conflict=id"
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key.count(".") >= 2:  # legacy JWT service_role; naujo tipo secret keys nėra JWT
        headers["Authorization"] = "Bearer " + key
    if method != "GET":
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(resource, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            body = response.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"Nuotolinė saugykla nepasiekiama (HTTP {err.code}). Patikrinkite Supabase lentelę ir Secrets.") from err
    except urllib.error.URLError as err:
        raise RuntimeError("Nepavyko susisiekti su nuotoline saugykla; patikrinkite ryšį.") from err


def restore_remote(db_path: Path) -> bool:
    """Grąžina True jei nuotolinė kopija buvo rasta ir atkurta."""
    records = _call("GET")
    if not records:
        return False
    dump = zlib.decompress(base64.b64decode(records[0]["payload"])).decode("utf-8")
    fd, temp_path = tempfile.mkstemp(prefix="grafiko_atkurta_", suffix=".sqlite3", dir=db_path.parent)
    os.close(fd)
    try:
        con = sqlite3.connect(temp_path)
        try:
            con.executescript(dump)
            count = con.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
            if count != 3:
                raise ValueError("Nuotolinėje bazėje turi būti trys darbuotojai.")
            con.commit()
        finally:
            con.close()
        os.replace(temp_path, db_path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return True


def save_remote(db_path: Path) -> None:
    """Po SQLite transakcijos išsaugo vieną pilną atominę nuotolinę kopiją."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        dump = "\n".join(con.iterdump())
    finally:
        con.close()
    payload = base64.b64encode(zlib.compress(dump.encode("utf-8"), level=8)).decode("ascii")
    _call("POST", {"id": "main", "payload": payload})
