"""API ve WebSocket sözleşmesinin testleri.

Sözleşme testleri bilinçli olarak ayrıntılı: Kişi 1 ile Kişi 3 arasındaki
entegrasyon bu mesajlar üstünden yürüyor ve sessiz bir alan adı değişikliği
iki kişiyi birden bloke eder.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gaze_aac.main import create_app


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


class TestHealth:
    def test_health_reports_active_components(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200

        body = response.json()
        assert body["status"] == "ok"
        assert "gaze_source" in body
        assert "expander_provider" in body

    def test_schemes_lists_all_four(self, client: TestClient) -> None:
        response = client.get("/schemes")
        assert response.status_code == 200
        assert {s["id"] for s in response.json()} == {"S1", "S2", "S3", "S4"}


class TestExpandEndpoint:
    def test_expands_abbreviation(self, client: TestClient) -> None:
        response = client.post("/expand", json={"abbreviation": "s i", "scheme": "S1"})
        assert response.status_code == 200

        body = response.json()
        assert body["provider"] == "mock"
        assert any(c["text"] == "Su istiyorum." for c in body["candidates"])

    def test_rejects_unknown_scheme(self, client: TestClient) -> None:
        response = client.post("/expand", json={"abbreviation": "s i", "scheme": "S9"})
        assert response.status_code == 422

    def test_rejects_empty_abbreviation(self, client: TestClient) -> None:
        response = client.post("/expand", json={"abbreviation": "", "scheme": "S1"})
        assert response.status_code == 422


class TestWebSocket:
    def test_sends_ready_on_connect(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as socket:
            message = socket.receive_json()
            assert message["type"] == "ready"
            assert message["session_id"]
            assert message["dwell_ms"] > 0

    def test_gaze_sample_echoes_smoothed_position(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as socket:
            socket.receive_json()  # ready
            socket.send_json(
                {"type": "gaze", "point": {"x": 0.5, "y": 0.5, "t": 0.0, "confidence": 1.0}}
            )
            message = socket.receive_json()
            assert message["type"] == "gaze"
            assert 0.0 <= message["x"] <= 1.0

    def test_dwell_completes_and_reports_selection(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as socket:
            socket.receive_json()  # ready
            socket.send_json(
                {
                    "type": "targets",
                    "targets": [
                        {
                            "id": "k1",
                            "x": 0.0,
                            "y": 0.0,
                            "width": 1.0,
                            "height": 1.0,
                            "label": "A",
                            "kind": "key",
                        }
                    ],
                }
            )

            # İlk örnek yalnızca saati kurar: tek mesaj döner (gaze yankısı).
            # Sonrakiler iki mesaj döner: yankı + ilerleme ya da seçim.
            socket.send_json(
                {"type": "gaze", "point": {"x": 0.5, "y": 0.5, "t": 0.0, "confidence": 1.0}}
            )
            assert socket.receive_json()["type"] == "gaze"

            selected = False
            for step in range(1, 13):
                socket.send_json(
                    {
                        "type": "gaze",
                        "point": {"x": 0.5, "y": 0.5, "t": step * 0.1, "confidence": 1.0},
                    }
                )
                assert socket.receive_json()["type"] == "gaze"
                follow_up = socket.receive_json()
                if follow_up["type"] == "selection":
                    assert follow_up["target_id"] == "k1"
                    selected = True
                    break
                assert follow_up["type"] == "dwell_progress"

            assert selected, "1 saniyeden uzun bakışta seçim tetiklenmeliydi"

    def test_expand_returns_candidates(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as socket:
            socket.receive_json()  # ready
            socket.send_json({"type": "expand", "abbreviation": "s i", "scheme": "S1"})

            message = socket.receive_json()
            assert message["type"] == "candidates"
            assert message["abbreviation"] == "s i"
            assert message["latency_ms"] >= 0.0

    def test_invalid_message_does_not_close_connection(self, client: TestClient) -> None:
        """Tek bozuk mesaj oturumu düşürmemeli: kullanıcı kalibrasyonunu
        kaybederse baştan başlamak zorunda kalır."""
        with client.websocket_connect("/ws") as socket:
            socket.receive_json()  # ready
            socket.send_json({"type": "boyle_bir_mesaj_yok"})

            error = socket.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "invalid_message"

            socket.send_json({"type": "expand", "abbreviation": "s i", "scheme": "S1"})
            assert socket.receive_json()["type"] == "candidates"

    def test_calibration_with_too_few_samples_reports_failure(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as socket:
            socket.receive_json()  # ready
            socket.send_json(
                {
                    "type": "calibration_sample",
                    "target_x": 0.5,
                    "target_y": 0.5,
                    "features": [0.1] * 12,
                }
            )
            socket.send_json({"type": "calibration_fit"})

            result = socket.receive_json()
            assert result["type"] == "calibration_result"
            assert result["ok"] is False
            assert result["message"]
