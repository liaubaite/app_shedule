"""Patvari darbografikių SQLite kopija Supabase duomenų bazėje.

Prisijungimas vyksta tik iš Streamlit serverio; API raktas niekada
neperduodamas į naršyklę. Jei Supabase sukonfigūruota, bet nepasiekiama,
neleidžiame tyliai pakeisti patvarios saugyklos laikina SQLite.
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
from urllib.parse import urlsplit, urlunsplit


class SupabaseConnectionError(RuntimeError):
    """Aiški diagnostika be raktų, SQL duomenų ar jautrių atsakymų."""


def read_setting(name: str) -> str:
    env = os.getenv(name, "")
    if env:
        return env.strip()
    try:
        import streamlit as st
        return str(st.secrets.get(name, "") or "").strip()
    except (ImportError, FileNotFoundError, RuntimeError, AttributeError):
        return ""


def supabase_key() -> str:
    # Senas nustatymų vardas išlieka suderinamas, bet rekomenduojame naują.
    return (read_setting("SUPABASE_SERVICE_ROLE_KEY")
            or read_setting("SUPABASE_SECRET_KEY")
            or read_setting("SUPABASE_KEY"))


def remote_configured() -> bool:
    return bool(read_setting("SUPABASE_URL") and supabase_key())


def remote_url() -> str:
    """Priima projekto URL arba netyčia įklijuotą /rest/v1/ adresą."""
    entered = read_setting("SUPABASE_URL").strip().rstrip("/")
    parsed = urlsplit(entered)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SupabaseConnectionError("Neteisingas SUPABASE_URL: reikia https://<projektas>.supabase.co")
    path = parsed.path.rstrip("/")
    if path == "/rest/v1":
        path = ""
    if path:
        raise SupabaseConnectionError("SUPABASE_URL turi būti projekto adresas be papildomo kelio.")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _safe_http_detail(err: urllib.error.HTTPError) -> str:
    """Iš nuotolinio atsakymo skaitome tik techninį klaidos KODĄ, ne tekstą."""
    try:
        blob = err.read(8192)
        parsed = json.loads(blob)
        if isinstance(parsed, dict):
            code = parsed.get("code", "")
            if isinstance(code, str) and code and len(code) < 48 and all(
                c.isupper() or c.isdigit() or c in "_-" for c in code
            ):
                return f" (Supabase kodas: {code})"
    except (ValueError, TypeError, OSError):
        pass
    return ""


def _http_hint(status: int) -> str:
    if status == 401:
        return "Patikrinkite naują Secret API key, projekto atitikimą ir jo galiojimą."
    if status == 403:
        return "Patikrinkite, ar naudojamas slaptasis serverio raktas ir suteiktos teisės lentelei."
    if status == 404:
        return "Patikrinkite app_state lentelę (public schema), projekto URL ir įjungtą Data API."
    if status == 400:
        return "Patikrinkite app_state lentelės id/payload stulpelius ir Data API nustatymus."
    if status == 429:
        return "Supabase viršytas užklausų limitas; palaukite ir bandykite dar kartą."
    return "Patikrinkite Supabase API būseną ir projekto nustatymus."


def _call(method: str, payload: dict | None = None) -> list | None:
    key = supabase_key()
    if not key:
        raise SupabaseConnectionError("Nerastas SUPABASE_SERVICE_ROLE_KEY (ar SUPABASE_SECRET_KEY).")
    url = remote_url()
    resource = url + "/rest/v1/app_state"
    if method == "GET":
        resource += "?id=eq.main&select=payload"
    elif method == "POST":
        resource += "?on_conflict=id"
    else:
        raise ValueError("Nepalaikomas metodas")

    # Supabase naujieji sb_secret_* raktai perduodami tik 'apikey' antraštėje.
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key.startswith("eyJ") and key.count(".") == 2:  # senas service_role JWT
        headers["Authorization"] = "Bearer " + key
    if method == "POST":
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(resource, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            body = response.read()
            result = json.loads(body) if body else None
            if method == "GET" and not isinstance(result, list):
                raise SupabaseConnectionError("Supabase grąžino netikėtą duomenų formatą.")
            return result
    except urllib.error.HTTPError as err:
        code = int(err.code)
        detail = _safe_http_detail(err)
        raise SupabaseConnectionError(
            f"Supabase HTTP {code}{detail}. {_http_hint(code)}"
        ) from None
    except (urllib.error.URLError, TimeoutError) as err:
        raise SupabaseConnectionError(
            "Nepavyko pasiekti Supabase serverio. Patikrinkite interneto ryšį arba bandykite vėliau."
        ) from None


def restore_remote(db_path: Path) -> bool:
    """Grąžina True jei nuotolinė kopija buvo rasta ir atkurta."""
    records = _call("GET")
    if not records:
        return False
    try:
        dump = zlib.decompress(base64.b64decode(records[0]["payload"])).decode("utf-8")
    except (KeyError, IndexError, TypeError, ValueError, zlib.error) as err:
        raise SupabaseConnectionError(
            "Supabase app_state/main duomenų kopija neteisinga."
            " Nieko netrinkite, prieš taisydami pasidarykite atsarginę kopiją."
        ) from None
    fd, temp_path = tempfile.mkstemp(prefix="grafiko_atkurta_", suffix=".sqlite3", dir=db_path.parent)
    os.close(fd)
    try:
        con = sqlite3.connect(temp_path)
        try:
            con.executescript(dump)
            count = con.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
            if count != 3:
                raise ValueError("Turi būti trys darbuotojos")
            con.commit()
        finally:
            con.close()
        os.replace(temp_path, db_path)
    except (sqlite3.Error, ValueError) as err:
        raise SupabaseConnectionError(
            "Supabase išsaugota kopija neatitinka grafikų struktūros."
            " Netrinkite jos; reikia patikrinti prieš atkuriant."
        ) from None
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return True


def save_remote(db_path: Path) -> None:
    """Po SQLite transakcijos išsaugo pilną nuotolinę kopiją."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        dump = "\n".join(con.iterdump())
    finally:
        con.close()
    payload = base64.b64encode(zlib.compress(dump.encode("utf-8"), level=8)).decode("ascii")
    _call("POST", {"id": "main", "payload": payload})
