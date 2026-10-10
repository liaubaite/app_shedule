"""Tiesioginės Supabase užklausos nereikalingos – testuojama su imitacijomis."""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import saugykla as s


class FakeResponse:
    def __init__(self, body):
        self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self.body


class SupabaseTests(unittest.TestCase):
    def setUp(self):
        self.e = patch.dict(os.environ, {
            "SUPABASE_URL": "https://example.supabase.co/rest/v1/",
            "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_SAMPLE_NOT_REAL",
        })
        self.e.start()
        self.addCleanup(self.e.stop)

    def test_url_strips_rest_path(self):
        self.assertEqual(s.remote_url(), "https://example.supabase.co")

    def test_alias_key_fallback(self):
        with patch.dict(os.environ, {
            "SUPABASE_SERVICE_ROLE_KEY": "", "SUPABASE_SECRET_KEY": "alias_key"
        }):
            self.assertEqual(s.supabase_key(), "alias_key")

    def test_secret_only_apikey_header(self):
        def verify(req, timeout):
            self.assertEqual(req.full_url, "https://example.supabase.co/rest/v1/app_state?id=eq.main&select=payload")
            self.assertEqual(req.get_header("Apikey"), "sb_secret_SAMPLE_NOT_REAL")
            self.assertIsNone(req.get_header("Authorization"))
            return FakeResponse(b"[]")
        with patch.object(s.urllib.request, "urlopen", side_effect=verify):
            self.assertEqual(s._call("GET"), [])

    def test_401_includes_no_sensitive_response(self):
        error = urllib.error.HTTPError("https://example.supabase.co", 401, "Unauth", {},
                                      io.BytesIO(json.dumps({"code": "PGRST301", "message": "secret in message"}).encode()))
        with patch.object(s.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(s.SupabaseConnectionError) as captured:
                s._call("GET")
        self.assertIn("HTTP 401", str(captured.exception))
        self.assertIn("PGRST301", str(captured.exception))
        self.assertNotIn("secret in message", str(captured.exception))

    def test_404_clear_status(self):
        error = urllib.error.HTTPError("https://example.supabase.co", 404, "Not Found", {},
                                      io.BytesIO(b'{"code":"PGRST205"}'))
        with patch.object(s.urllib.request, "urlopen", side_effect=error):
            with self.assertRaisesRegex(s.SupabaseConnectionError, "app_state"):
                s._call("GET")

    def test_no_http_secrets_in_exception(self):
        error = urllib.error.HTTPError("https://example.supabase.co", 403, "Forbidden", {},
                                      io.BytesIO(b'{"message":"sb_secret_sensitive"}'))
        with patch.object(s.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(s.SupabaseConnectionError) as captured:
                s._call("GET")
        self.assertNotIn("sb_secret_sensitive", str(captured.exception))

    def test_invalid_url_fails_early(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co/rest/v1/app_state"}):
            with self.assertRaisesRegex(s.SupabaseConnectionError, "papildomo kelio"):
                s.remote_url()

    def test_no_restore_when_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"data.sqlite3"
            with patch.object(s, "_call", return_value=[]):
                self.assertFalse(s.restore_remote(db))
            self.assertFalse(db.exists())

    def test_post_payload(self):
        def verify(req, timeout):
            self.assertEqual(req.method, "POST")
            self.assertIn("resolution=merge-duplicates", req.get_header("Prefer"))
            self.assertEqual(json.loads(req.data)["id"], "main")
            return FakeResponse(b"")
        with patch.object(s.urllib.request, "urlopen", side_effect=verify):
            self.assertIsNone(s._call("POST", {"id":"main", "payload":"abc"}))


if __name__ == "__main__":
    unittest.main()
