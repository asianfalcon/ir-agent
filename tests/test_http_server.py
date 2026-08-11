from starlette.testclient import TestClient

from alphasonar.interfaces.mcp.http_server import create_http_app


def test_http_transport_requires_token():
    try:
        create_http_app(token="")
        assert False, "empty token must be rejected"
    except RuntimeError:
        pass


def test_health_is_public_and_mcp_requires_bearer_token():
    with TestClient(create_http_app(token="test-secret")) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.post("/mcp/", json={})
        assert response.status_code == 401
        assert response.json() == {"error": "unauthorized"}
        authorized = client.post("/mcp/", json={}, headers={"Authorization": "Bearer test-secret"})
        assert authorized.status_code != 401


def test_http_transport_reads_token_file(tmp_path, monkeypatch):
    token_file = tmp_path / "alphasonar_mcp_token"
    token_file.write_text("file-secret\n")
    monkeypatch.delenv("ALPHASONAR_MCP_TOKEN", raising=False)
    monkeypatch.setenv("ALPHASONAR_MCP_TOKEN_FILE", str(token_file))
    with TestClient(create_http_app()) as client:
        response = client.post("/mcp/", json={})
        assert response.status_code == 401


def test_http_transport_accepts_former_token_variable(monkeypatch):
    monkeypatch.delenv("ALPHASONAR_MCP_TOKEN", raising=False)
    monkeypatch.delenv("ALPHASONAR_MCP_TOKEN_FILE", raising=False)
    monkeypatch.setenv("IRA_MCP_TOKEN", "former-token")
    with TestClient(create_http_app()) as client:
        response = client.post("/mcp/", json={})
        assert response.status_code == 401
