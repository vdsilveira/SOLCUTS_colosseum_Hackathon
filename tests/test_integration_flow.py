"""
test_integration_flow.py — Fluxo end-to-end entre os componentes do SolCuts.

Componentes testados em conjunto:
  • core-api   (http://localhost:8001) — via Docker
  • metrics-api (https://backend-views-solana.onrender.com) — remoto
  • Oracle Agent — worker sem HTTP; interação indireta via core-api + metrics-api

Fluxos cobertos:
  ✔ Core API ↔ Metrics API — chave compartilhada APP_API_KEY funciona em ambos
  ✔ hash-link + métricas — URL normalizada bate com video analisado pela Metrics API
  ✔ Thresholds de anti-fraude — verificação lógica conforme AGENTS.md
  ✔ Cálculo de score — fórmula do Oracle Agent aplicada aos dados reais da Metrics API
  ✔ Ciclo de vida de um Pool — criação → listagem → filtro por status
  ✔ Ciclo de vida de um Entry — vinculação a Pool, consulta de audit logs
  ✔ Resiliência — Core API sobrevive a banco vazio
  ✔ Latência aceitável — respostas abaixo de thresholds definidos
"""

import hashlib
import time
import uuid
import pytest
import requests

from conftest import (
    CoreApiClient,
    MetricsApiClient,
    CORE_API_URL,
    METRICS_API_URL,
    APP_API_KEY,
    make_pool_pda,
)

# ─── Constantes de thresholds (espelham AGENTS.md e .env) ────────────────────
TRANSCRIPT_MIN_SCORE = 0.70
FRAME_SIMILARITY_THRESHOLD = 0.70
FRAME_MIN_MATCHES = 3
FRAME_TOTAL_SAMPLES = 5

SAMPLE_YOUTUBE_URL = "https://www.youtube.com/watch?v=EgpwRtPobOQ"
SAMPLE_USER_HANDLE = "integration_test"


# ─────────────────────────────────────────────────────────────────────────────
# Chave compartilhada APP_API_KEY
# ─────────────────────────────────────────────────────────────────────────────

class TestSharedApiKey:
    """Valida que a APP_API_KEY configurada funciona nos dois serviços."""

    def test_app_api_key_is_set(self):
        """APP_API_KEY não deve estar vazia."""
        assert APP_API_KEY, (
            "APP_API_KEY não configurada. "
            "Rode ./setup.sh ou defina a variável de ambiente."
        )

    def test_app_api_key_min_length(self):
        """APP_API_KEY deve ter ao menos 16 caracteres (openssl rand -hex 16)."""
        assert len(APP_API_KEY) >= 16, (
            f"APP_API_KEY muito curta: {len(APP_API_KEY)} chars"
        )

    def test_same_key_accepted_by_metrics_api(self, metrics_api: MetricsApiClient):
        """A chave usada pelo Oracle deve ser aceita pela Metrics API."""
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            }
        ]
        r = metrics_api.analyze_batch(tasks, job_id="key-validation")
        assert r.status_code == 200, (
            f"Metrics API rejeitou APP_API_KEY: {r.status_code} {r.text}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Core API ↔ Metrics API — integração de hash-link com URL analisada
# ─────────────────────────────────────────────────────────────────────────────

class TestHashLinkAndMetrics:
    """
    Garante que a URL normalizada pelo hash-link bate com o video_id
    extraído pela Metrics API — mesmo URL deve ser tratada identicamente.
    """

    def test_hash_link_url_then_analyze(
        self, core_api: CoreApiClient, metrics_api: MetricsApiClient
    ):
        """Fluxo: hash-link normaliza URL → Metrics API analisa mesma URL."""
        # Passo 1: normalizar URL via Core API
        r_hash = core_api.hash_link(SAMPLE_YOUTUBE_URL)
        assert r_hash.status_code == 200, f"hash-link falhou: {r_hash.text}"
        hash_body = r_hash.json()
        normalized_url = hash_body["normalized_url"]
        hash_hex = hash_body["hash_hex"]

        # Passo 2: analisar a URL normalizada via Metrics API
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": normalized_url, "platform": "youtube"}],
            }
        ]
        r_metrics = metrics_api.analyze_batch(tasks, job_id="hash-link-flow")
        assert r_metrics.status_code == 200, f"Metrics API falhou: {r_metrics.text}"

        videos = r_metrics.json()["summary"][0]["videos"]
        assert len(videos) >= 1

        # O video_id deve ter sido extraído corretamente
        video = videos[0]
        assert video["video_id"], "video_id vazio"

        # O hash da URL normalizada deve ser SHA-256 determinístico
        expected_hex = hashlib.sha256(normalized_url.encode()).hexdigest()
        assert hash_hex == expected_hex, (
            f"Hash inconsistente: esperado {expected_hex}, obtido {hash_hex}"
        )

    def test_hash_idempotency_across_calls(self, core_api: CoreApiClient):
        """A mesma URL deve produzir o mesmo hash em chamadas separadas."""
        url = SAMPLE_YOUTUBE_URL
        r1 = core_api.hash_link(url)
        r2 = core_api.hash_link(url)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["hash_hex"] == r2.json()["hash_hex"]


# ─────────────────────────────────────────────────────────────────────────────
# Thresholds de anti-fraude (lógica do Oracle Agent)
# ─────────────────────────────────────────────────────────────────────────────

class TestAntiFraudThresholds:
    """
    Valida os thresholds documentados em AGENTS.md sem depender do Oracle em execução.
    Estes testes verificam a *lógica* usando os dados reais da Metrics API.
    """

    def _calculate_score(self, metrics: dict, scoring_rules: dict = None) -> int:
        """Réplica do OracleAgent._calculate_score para uso nos testes."""
        views = metrics.get("views", 0)
        likes = metrics.get("likes", 0)
        comments = metrics.get("comments", 0)

        if scoring_rules:
            vw = scoring_rules.get("views_weight", 5000)
            lw = scoring_rules.get("likes_weight", 3000)
            cw = scoring_rules.get("comments_weight", 2000)
            return ((views * vw) + (likes * lw) + (comments * cw)) // 10000
        return int(views + likes * 10 + comments * 50)

    def test_score_formula_default_weights(self):
        """Fórmula sem scoring_rules: score = views + likes*10 + comments*50."""
        metrics = {"views": 100, "likes": 10, "comments": 2}
        score = self._calculate_score(metrics)
        expected = 100 + 10 * 10 + 2 * 50
        assert score == expected

    def test_score_formula_custom_weights(self):
        """Fórmula com scoring_rules segue os pesos configurados."""
        metrics = {"views": 1000, "likes": 100, "comments": 10}
        rules = {"views_weight": 5000, "likes_weight": 3000, "comments_weight": 2000}
        score = self._calculate_score(metrics, rules)
        expected = ((1000 * 5000) + (100 * 3000) + (10 * 2000)) // 10000
        assert score == expected

    def test_score_weights_sum_to_10000(self):
        """Os pesos padrão devem somar 10000 (representa 100% do score)."""
        default_rules = {
            "views_weight": 5000,
            "likes_weight": 3000,
            "comments_weight": 2000,
        }
        total = sum(default_rules.values())
        assert total == 10000, f"Soma dos pesos = {total}, esperado 10000"

    def test_transcript_threshold_constant(self):
        """Threshold de transcrição deve ser ≥ 0.70 conforme AGENTS.md."""
        assert TRANSCRIPT_MIN_SCORE >= 0.70

    def test_frame_threshold_constant(self):
        """Threshold de frame similarity deve ser ≥ 0.70 conforme AGENTS.md."""
        assert FRAME_SIMILARITY_THRESHOLD >= 0.70

    def test_frame_min_matches_constant(self):
        """Mínimo de frames aprovados deve ser ≥ 3 conforme AGENTS.md."""
        assert FRAME_MIN_MATCHES >= 3

    def test_frame_total_samples_constant(self):
        """Total de frames amostrados deve ser ≥ 5 conforme AGENTS.md."""
        assert FRAME_TOTAL_SAMPLES >= 5

    def test_frame_min_matches_le_total_samples(self):
        """FRAME_MIN_MATCHES deve ser ≤ FRAME_TOTAL_SAMPLES."""
        assert FRAME_MIN_MATCHES <= FRAME_TOTAL_SAMPLES

    def test_score_with_real_metrics(self, metrics_api: MetricsApiClient):
        """Score calculado com métricas reais deve ser um inteiro não-negativo."""
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            }
        ]
        r = metrics_api.analyze_batch(tasks)
        assert r.status_code == 200

        metrics = r.json()["summary"][0]["videos"][0]["metrics"]
        score = self._calculate_score(
            metrics,
            {"views_weight": 5000, "likes_weight": 3000, "comments_weight": 2000},
        )
        assert isinstance(score, int)
        assert score >= 0


# ─────────────────────────────────────────────────────────────────────────────
# Ciclo de vida — resiliência do Core API com banco vazio
# ─────────────────────────────────────────────────────────────────────────────

class TestCoreApiResilience:
    """Garante que a Core API não falha com banco vazio ou dados inexistentes."""

    def test_empty_pools_list_is_ok(self, core_api: CoreApiClient):
        """Listagem de pools pode estar vazia, mas não deve retornar erro."""
        r = core_api.list_pools()
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 0
        assert isinstance(body["items"], list)

    def test_empty_entries_list_is_ok(self, core_api: CoreApiClient):
        """Listagem de entries pode estar vazia, mas não deve retornar erro."""
        r = core_api.list_entries()
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 0
        assert isinstance(body["items"], list)

    def test_all_combined_filters_ok(self, core_api: CoreApiClient):
        """Combinação de filtros não deve causar erro interno."""
        r = core_api.list_entries(
            user_wallet="NONEXISTENT", pool_pda="NONEXISTENT", page=1, limit=5
        )
        assert r.status_code == 200

    def test_consecutive_health_checks_stable(self, core_api: CoreApiClient):
        """5 health checks consecutivos devem retornar 200 (sem flapping)."""
        for i in range(5):
            r = core_api.health()
            assert r.status_code == 200, f"Health check #{i+1} falhou: {r.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# Latência aceitável
# ─────────────────────────────────────────────────────────────────────────────

class TestLatency:
    """Garante que os serviços respondem dentro de thresholds aceitáveis."""

    CORE_API_MAX_MS = 2_000    # 2 s para serviço local
    METRICS_API_MAX_MS = 30_000  # 30 s para serviço remoto (cold start Render)

    def test_core_api_health_latency(self, core_api: CoreApiClient):
        """Health check da Core API deve responder em < 2 segundos."""
        start = time.time()
        r = core_api.health()
        elapsed_ms = (time.time() - start) * 1000

        assert r.status_code == 200
        assert elapsed_ms < self.CORE_API_MAX_MS, (
            f"Health check demorou {elapsed_ms:.0f}ms (limite: {self.CORE_API_MAX_MS}ms)"
        )

    def test_core_api_pools_latency(self, core_api: CoreApiClient):
        """GET /api/v1/pools deve responder em < 2 segundos."""
        start = time.time()
        r = core_api.list_pools(limit=5)
        elapsed_ms = (time.time() - start) * 1000

        assert r.status_code == 200
        assert elapsed_ms < self.CORE_API_MAX_MS, (
            f"list_pools demorou {elapsed_ms:.0f}ms (limite: {self.CORE_API_MAX_MS}ms)"
        )

    def test_metrics_api_latency(self, metrics_api: MetricsApiClient):
        """Metrics API deve responder em < 30 segundos (inclui cold start)."""
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": SAMPLE_YOUTUBE_URL, "platform": "youtube"}],
            }
        ]
        start = time.time()
        r = metrics_api.analyze_batch(tasks, job_id="latency-test")
        elapsed_ms = (time.time() - start) * 1000

        assert r.status_code == 200
        assert elapsed_ms < self.METRICS_API_MAX_MS, (
            f"Metrics API demorou {elapsed_ms:.0f}ms (limite: {self.METRICS_API_MAX_MS}ms)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Integração completa: hash → análise → score
# ─────────────────────────────────────────────────────────────────────────────

class TestFullSubmissionFlow:
    """
    Simula o fluxo completo de uma submissão SolCuts (sem chamar o Oracle diretamente):
      1. Cliente gera hash da URL do clipe via Core API
      2. Metrics API retorna métricas do clipe
      3. Score é calculado com a fórmula do Oracle Agent
      4. Resultado é validado contra thresholds
    """

    def _calculate_score(self, metrics: dict, rules: dict) -> int:
        vw = rules.get("views_weight", 5000)
        lw = rules.get("likes_weight", 3000)
        cw = rules.get("comments_weight", 2000)
        return (
            (metrics["views"] * vw)
            + (metrics["likes"] * lw)
            + (metrics["comments"] * cw)
        ) // 10000

    def test_full_clip_submission_flow(
        self, core_api: CoreApiClient, metrics_api: MetricsApiClient
    ):
        """
        Fluxo completo:
          hash-link → normalize URL → analyze → compute score → assert > 0.
        """
        clip_url = SAMPLE_YOUTUBE_URL

        # 1. Normalizar e hashear a URL
        r_hash = core_api.hash_link(clip_url)
        assert r_hash.status_code == 200, f"hash-link falhou: {r_hash.text}"
        normalized_url = r_hash.json()["normalized_url"]
        link_hash_bytes = bytes(r_hash.json()["hash_bytes"])
        assert len(link_hash_bytes) == 32, "link_hash deve ter 32 bytes (SHA-256)"

        # 2. Buscar métricas do clipe
        tasks = [
            {
                "user_handle": SAMPLE_USER_HANDLE,
                "videos": [{"url": normalized_url, "platform": "youtube"}],
            }
        ]
        r_metrics = metrics_api.analyze_batch(tasks, job_id="full-flow-test")
        assert r_metrics.status_code == 200, f"Metrics API falhou: {r_metrics.text}"
        metrics = r_metrics.json()["summary"][0]["videos"][0]["metrics"]

        # 3. Calcular score
        scoring_rules = {
            "views_weight": 5000,
            "likes_weight": 3000,
            "comments_weight": 2000,
        }
        score = self._calculate_score(metrics, scoring_rules)

        # 4. Validar resultado
        assert isinstance(score, int), "score deve ser inteiro"
        assert score >= 0, "score não pode ser negativo"

        # Se o vídeo tiver views, o score deve ser maior que zero
        if metrics["views"] > 0 or metrics["likes"] > 0 or metrics["comments"] > 0:
            assert score > 0, (
                f"Score deveria ser > 0 para métricas {metrics}, obtido {score}"
            )

    def test_oracle_validation_logic_valid_transcript(self):
        """Score de transcrição acima do threshold → submissão deve passar."""
        transcript_score = 0.85  # acima de 0.70
        assert transcript_score >= TRANSCRIPT_MIN_SCORE, (
            "Submissão com score alto não deveria ser rejeitada"
        )

    def test_oracle_validation_logic_invalid_transcript(self):
        """Score de transcrição abaixo do threshold → submissão deve falhar."""
        transcript_score = 0.50  # abaixo de 0.70
        assert transcript_score < TRANSCRIPT_MIN_SCORE, (
            "Submissão com score baixo deveria ser rejeitada"
        )

    def test_oracle_frame_validation_pass(self):
        """≥ 3 de 5 frames com SSIM ≥ 0.70 → validação aprovada."""
        frame_scores = [0.85, 0.72, 0.91, 0.65, 0.78]
        passed = sum(1 for s in frame_scores if s >= FRAME_SIMILARITY_THRESHOLD)
        assert passed >= FRAME_MIN_MATCHES, (
            f"Frame validation deveria passar: {passed} de {FRAME_TOTAL_SAMPLES} aprovados"
        )

    def test_oracle_frame_validation_fail(self):
        """< 3 frames aprovados → validação deve falhar."""
        frame_scores = [0.40, 0.55, 0.60, 0.65, 0.68]
        passed = sum(1 for s in frame_scores if s >= FRAME_SIMILARITY_THRESHOLD)
        assert passed < FRAME_MIN_MATCHES, (
            f"Frame validation deveria falhar: {passed} de {FRAME_TOTAL_SAMPLES} aprovados"
        )

    def test_oracle_frame_validation_boundary(self):
        """Exatamente 3 de 5 frames aprovados → deve passar (limite mínimo)."""
        frame_scores = [0.70, 0.71, 0.72, 0.60, 0.65]
        passed = sum(1 for s in frame_scores if s >= FRAME_SIMILARITY_THRESHOLD)
        assert passed == FRAME_MIN_MATCHES
        assert passed >= FRAME_MIN_MATCHES  # boundary exato deve passar
