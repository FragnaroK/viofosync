"""healthz, clip ZIP endpoint and places search."""
from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient


def _client(tmp_config_dir, tmp_recordings_dir):
    from web import app as app_mod
    from web import settings as settings_mod
    settings_mod.reset_for_tests()
    app = app_mod.create_app()
    return app, TestClient(app)


def _setup(c):
    r = c.post("/setup", data={
        "address": "192.168.1.230",
        "password": "twelve-chars-min!",
        "confirm": "twelve-chars-min!",
    }, follow_redirects=False)
    assert r.status_code == 303


def test_healthz_is_unauthenticated(tmp_config_dir: Path, tmp_recordings_dir: Path):
    app, c = _client(tmp_config_dir, tmp_recordings_dir)
    with c:
        # Reachable even before setup/login.
        r = c.get("/healthz", follow_redirects=False)
        assert r.status_code == 200
        assert r.json() == {"ok": True}


def test_zip_endpoint_streams_selected_clips(
    tmp_config_dir: Path, tmp_recordings_dir: Path,
):
    app, c = _client(tmp_config_dir, tmp_recordings_dir)
    with c:
        _setup(c)
        paths = []
        for i, name in enumerate(("2026_0901_100000_0001F.MP4", "2026_0901_100000_0002R.MP4")):
            p = tmp_recordings_dir / name
            p.write_bytes(bytes([65 + i]) * 1000)
            paths.append(p)
        ids = []
        with app.state.db.write() as conn:
            for i, p in enumerate(paths):
                cur = conn.execute(
                    "INSERT INTO clip_index (path, basename, timestamp, camera, "
                    "sequence, size_bytes, scanned_at) VALUES (?,?,?,?,?,?,?)",
                    (str(p), p.name, 1000 + i, "FR"[i], i, 1000, int(time.time())),
                )
                ids.append(cur.lastrowid)

        r = c.get("/api/archive/zip", params={"ids": ",".join(map(str, ids))})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        assert "attachment" in r.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            assert sorted(zf.namelist()) == sorted(p.name for p in paths)
            assert zf.read(paths[0].name) == b"A" * 1000

        assert c.get("/api/archive/zip", params={"ids": "abc"}).status_code == 400
        assert c.get("/api/archive/zip", params={"ids": "99999"}).status_code == 404


def test_places_search_with_no_gps_returns_empty(
    tmp_config_dir: Path, tmp_recordings_dir: Path,
):
    app, c = _client(tmp_config_dir, tmp_recordings_dir)
    with c:
        _setup(c)
        r = c.get("/api/archive/places/search",
                  params={"lat": 51.5, "lon": -0.1, "radius_m": 300})
        assert r.status_code == 200
        body = r.json()
        assert body["hits"] == []
        assert body["partial"] is False

        assert c.get("/api/archive/places/search",
                     params={"lat": 999, "lon": 0}).status_code == 422
