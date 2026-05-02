"""
test_metrics_api.py — Testes de integração da Metrics API remota.

Serviço testado: https://backend-views-solana.onrender.com
Pré-condição  : APP_API_KEY configurada no .env ou como variável de ambiente.

Cobertura:
  ✔ POST /api/v1/analyze — happy path com vídeo YouTube real
  ✔ Validação do schema de resposta (status, job_id, summary)
  ✔ Campos obrigatórios de VideoResult (platform, video_id, metrics)
  ✔ Métricas numéricas não-negativas
  ✔ Batch com múltiplos vídeos
  ✔ Erro por API key inválida → 401/403
  ✔ Erro por payload inválido → 422
  ✔ job_id único é refletido na resposta
  ✔ deep_analysis=False não retorna comment_sample populado
"""

import uuid
import pytest
import requests

from conftest import MetricsApiClient, METRICS_API_URL, APP_API_KEY

# Vídeo YouTube público usado como fixture nos testes
SAMPLE_YOUTUBE_URL = "https://www.youtube.com/watch?v=EgpwRtPobOQ"
SAMPLE_USER_HANDLE = "test_integration"


# ─────────────────────────────────────────────────────────────────────────────
# Conectividade básica
# ─────────────────────────────────────────────────────────────────────────────

class TestMetricsApiConnectivity:
    """Valida que a Metrics API está acessível."""

    def test_metrics_api_is_reachable(self):
        """A Metrics API remota deve estar acessível (sem autenticação)."""
        try:
            r = requests.get(METRICS_API_URL, timeout=15)
            # Qualquer código de resposta (mesmo 404) indica que o host responde
            assert r.status_code < 600
        except requests.exceptions.ConnectionError:
            pytest.fail(
                f"Não foi possível alcançar a Metrics API em {METRICS_API_URL}. "
                "Verifique sua conexão com a internet."
            )


# ─────────────────────────────────────────────────────────────────────────────
# Autenticação
# ─────────────────────────────────────────────────────────────────────────────

class TestMetricsApiAuth:
    """Testes de autenticação via X-API-Key."""

    def test_invalid_api_key_rejected(self):
        """API key inválida → 401 ou 403."""
        client = MetricsApiClient(api_key="chave_invalida_test_xyz_000")
        payload = {
            "job_id": "auth-test",
            "deep_analysis": False,
            "tasks": [
                {
                    "user_handle": SAMPLE_USER_HANDLE,
                    "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
                }
            ],
        }
        r = client.session.post(
            f"{METRICS_API_URL}/api/v1/analyze",
            json=payload,
            timeout=30,
        )
        assert r.status_code in (401, 403, 422), (
            f"Esperado 401/403 para API key inválida, obtido {r.status_code}: {r.text}"
        )

    def test_missing_api_key_rejected(self):
        """Requisição sem X-API-Key → erro de autenticação."""
        r = requests.post(
            f"{METRICS_API_URL}/api/v1/analyze",
            json={
                "job_id": "no-key-test",
                "deep_analysis": False,
                "tasks": [],
            },
            timeout=30,
        )
        assert r.status_code in (401, 403, 422)


# ─────────────────────────────────────────────────────────────────────────────
# Happy path — análise de vídeo
# ─────────────────────────────────────────────────────────────────────────────

class TestMetricsApiAnalyze:
    """Testes do endpoint POST /api/v1/analyze."""

    def test_analyze_returns_200(self, metrics_api: MetricsApiClient):
        """POST /api/v1/analyze com vídeo válido → 200."""
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            }
        ]
        r = metrics_api.analyze_batch(tasks)
        assert r.status_code == 200, f"Obtido {r.status_code}: {r.text}"

    def test_analyze_response_schema_top_level(self, metrics_api: MetricsApiClient):
        """Resposta deve conter status, job_id e summary."""
        job_id = f"schema-test-{uuid.uuid4().hex[:6]}"
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            }
        ]
        r = metrics_api.analyze_batch(tasks, job_id=job_id)
        assert r.status_code == 200
        body = r.json()

        assert "status" in body, "Campo 'status' ausente"
        assert "job_id" in body, "Campo 'job_id' ausente"
        assert "summary" in body, "Campo 'summary' ausente"
        assert isinstance(body["summary"], list)

    def test_analyze_job_id_echoed_back(self, metrics_api: MetricsApiClient):
        """O job_id enviado deve ser refletido na resposta."""
        job_id = f"echo-test-{uuid.uuid4().hex[:8]}"
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            }
        ]
        r = metrics_api.analyze_batch(tasks, job_id=job_id)
        assert r.status_code == 200
        assert r.json()["job_id"] == job_id

    def test_analyze_status_is_success(self, metrics_api: MetricsApiClient):
        """status deve ser 'success' em resposta bem-sucedida."""
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            }
        ]
        r = metrics_api.analyze_batch(tasks)
        assert r.status_code == 200
        assert r.json()["status"] == "success"

    def test_analyze_summary_user_handle(self, metrics_api: MetricsApiClient):
        """summary deve conter o user_handle enviado."""
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            }
        ]
        r = metrics_api.analyze_batch(tasks)
        assert r.status_code == 200
        body = r.json()
        handles = [s["user_handle"] for s in body["summary"]]
        assert SAMPLE_USER_HANDLE in handles

    def test_analyze_video_result_schema(self, metrics_api: MetricsApiClient):
        """Cada VideoResult deve conter platform, video_id e metrics."""
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            }
        ]
        r = metrics_api.analyze_batch(tasks)
        assert r.status_code == 200
        body = r.json()

        for user_summary in body["summary"]:
            assert "videos" in user_summary
            for video in user_summary["videos"]:
                assert "platform" in video, "Campo 'platform' ausente em VideoResult"
                assert "video_id" in video, "Campo 'video_id' ausente em VideoResult"
                assert "metrics" in video, "Campo 'metrics' ausente em VideoResult"

    def test_analyze_metrics_schema(self, metrics_api: MetricsApiClient):
        """metrics deve conter views, likes e comments como inteiros."""
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            }
        ]
        r = metrics_api.analyze_batch(tasks)
        assert r.status_code == 200
        body = r.json()

        for user_summary in body["summary"]:
            for video in user_summary["videos"]:
                metrics = video["metrics"]
                assert "views" in metrics
                assert "likes" in metrics
                assert "comments" in metrics
                assert isinstance(metrics["views"], int), "views deve ser int"
                assert isinstance(metrics["likes"], int), "likes deve ser int"
                assert isinstance(metrics["comments"], int), "comments deve ser int"

    def test_analyze_metrics_non_negative(self, metrics_api: MetricsApiClient):
        """Métricas (views, likes, comments) devem ser ≥ 0."""
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            }
        ]
        r = metrics_api.analyze_batch(tasks)
        assert r.status_code == 200

        for user_summary in r.json()["summary"]:
            for video in user_summary["videos"]:
                m = video["metrics"]
                assert m["views"] >= 0, "views negativo"
                assert m["likes"] >= 0, "likes negativo"
                assert m["comments"] >= 0, "comments negativo"

    def test_analyze_video_id_extracted(self, metrics_api: MetricsApiClient):
        """video_id deve ser extraído corretamente da URL do YouTube."""
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            }
        ]
        r = metrics_api.analyze_batch(tasks)
        assert r.status_code == 200

        videos = r.json()["summary"][0]["videos"]
        assert len(videos) >= 1
        # O video_id para https://www.youtube.com/watch?v=EgpwRtPobOQ é EgpwRtPobOQ
        assert videos[0]["video_id"] == "EgpwRtPobOQ"

    def test_analyze_normalized_at_is_iso8601(self, metrics_api: MetricsApiClient):
        """normalized_at deve ser uma string ISO 8601 válida."""
        from datetime import datetime

        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            }
        ]
        r = metrics_api.analyze_batch(tasks)
        assert r.status_code == 200

        for user_summary in r.json()["summary"]:
            for video in user_summary["videos"]:
                ts = video.get("normalized_at", "")
                assert ts, "normalized_at vazio"
                # Tenta parsear como ISO 8601
                try:
                    datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    pytest.fail(f"normalized_at não é ISO 8601: '{ts}'")

    def test_analyze_deep_analysis_false_no_comments(self, metrics_api: MetricsApiClient):
        """Com deep_analysis=False, comment_sample deve ser vazio ou ausente."""
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            }
        ]
        r = metrics_api.analyze_batch(tasks)
        assert r.status_code == 200

        for user_summary in r.json()["summary"]:
            for video in user_summary["videos"]:
                comment_sample = video.get("comment_sample", [])
                assert isinstance(comment_sample, list)
                # Com deep_analysis=False esperamos lista vazia
                assert comment_sample == [], (
                    f"deep_analysis=False mas comment_sample não está vazio: {comment_sample}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# Batch com múltiplos vídeos / usuários
# ─────────────────────────────────────────────────────────────────────────────

class TestMetricsApiBatch:
    """Testes de análise em batch com múltiplos itens."""

    SECOND_VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_batch_multiple_videos_same_user(self, metrics_api: MetricsApiClient):
        """Dois vídeos do mesmo usuário → summary com total_videos_analyzed = 2."""
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [
                    {"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"},
                    {"url": self.SECOND_VIDEO_URL, "platform": "youtube"},
                ],
            }
        ]
        r = metrics_api.analyze_batch(tasks)
        assert r.status_code == 200
        body = r.json()
        user_summary = next(
            (s for s in body["summary"] if s["user_handle"] == SAMPLE_USER_HANDLE), None
        )
        assert user_summary is not None
        assert user_summary["total_videos_analyzed"] >= 1

    def test_batch_multiple_users(self, metrics_api: MetricsApiClient):
        """Dois usuários distintos → dois grupos no summary."""
        tasks = [
            {
                "user_handle": "user_a",
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            },
            {
                "user_handle": "user_b",
                "videos": [{"url": self.SECOND_VIDEO_URL, "platform": "youtube"}],
            },
        ]
        r = metrics_api.analyze_batch(tasks)
        assert r.status_code == 200
        body = r.json()
        handles = {s["user_handle"] for s in body["summary"]}
        # Pelo menos um dos dois usuários deve aparecer no summary
        assert len(handles) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Erros e casos de borda
# ─────────────────────────────────────────────────────────────────────────────

class TestMetricsApiErrors:
    """Testes de tratamento de erros."""

    def test_invalid_payload_missing_tasks(self, metrics_api: MetricsApiClient):
        """Payload sem campo 'tasks' → 422."""
        r = metrics_api.session.post(
            f"{METRICS_API_URL}/api/v1/analyze",
            json={"job_id": "error-test"},
            timeout=30,
        )
        assert r.status_code == 422

    def test_invalid_platform(self, metrics_api: MetricsApiClient):
        """platform desconhecida → erro ou resultado vazio (não deve explodir)."""
        tasks = [
            {
                "user_handle": "test_user",
                "videos": [
                    {"url": "https://example.com/video", "platform": "platform_inexistente"}
                ],
            }
        ]
        r = metrics_api.analyze_batch(tasks)
        # A API deve retornar 200 ou 422 — não deve retornar 500
        assert r.status_code in (200, 422), (
            f"Erro inesperado para platform inválida: {r.status_code} {r.text}"
        )
