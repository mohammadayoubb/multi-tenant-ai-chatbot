# Owner: Amer
"""Tests for API + widget frontend composition."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def test_create_app_serves_widget_frontend_when_dist_exists(tmp_path: Path) -> None:
    """The API host serves the built widget shell and loader from one origin."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<!doctype html><div id='root'>widget</div>")
    (dist_dir / "widget.js").write_text("console.log('widget');")

    client = TestClient(create_app(widget_dist_dir=dist_dir))

    index = client.get("/")
    widget_loader = client.get("/widget.js")

    assert index.status_code == 200
    assert "widget" in index.text
    assert widget_loader.status_code == 200
    assert "console.log('widget');" in widget_loader.text


def test_create_app_keeps_api_routes_ahead_of_static_mount(tmp_path: Path) -> None:
    """Static hosting must not shadow API endpoints."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<!doctype html><div id='root'>widget</div>")

    client = TestClient(create_app(widget_dist_dir=dist_dir))
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Week 8 Concierge API"
