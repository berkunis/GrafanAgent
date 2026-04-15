from fastapi.testclient import TestClient

from agents.router.app import create_app
from agents.router.fallback import FallbackChain, FallbackConfig
from tests.conftest import FakeAnthropic, tool_use_response
from agents._llm import LLMClient


def _build_client(confidence: float = 0.95) -> TestClient:
    fake = FakeAnthropic(
        [
            tool_use_response(
                tool_name="record_decision",
                tool_input={
                    "skill": "lifecycle",
                    "confidence": confidence,
                    "rationale": "aha-moment threshold crossed",
                    "payload": {},
                },
            )
        ]
    )
    llm = LLMClient(client=fake, agent="router")  # type: ignore[arg-type]
    chain = FallbackChain(llm, FallbackConfig())
    app = create_app(chain=chain)
    return TestClient(app)


def test_healthz():
    client = _build_client()
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "router"}


def test_post_signal_happy_path():
    client = _build_client(confidence=0.95)
    body = {
        "id": "sig-1",
        "type": "aha_moment_threshold",
        "source": "cli",
        "user_id": "user-aha-001",
    }
    resp = client.post("/signal", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["signal_id"] == "sig-1"
    assert data["decision"]["skill"] == "lifecycle"
    assert data["rung_used"] == "haiku"
    assert data["models_consulted"] == ["claude-haiku-4-5"]
    assert data["latency_ms"] >= 0


def test_post_signal_validation_error():
    client = _build_client()
    # Missing required fields.
    resp = client.post("/signal", json={"id": "sig-1"})
    assert resp.status_code == 422
