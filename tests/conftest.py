"""
conftest.py — Fixtures e helpers compartilhados para todos os testes de integração.

Os testes pressupõem que os serviços estão em execução via docker compose:
  docker compose up -d
"""

import os
import time
import uuid
from typing import Optional

import pytest
import requests

# ---------------------------------------------------------------------------
# URLs base (lidas de env vars, com defaults para execução local)
# ---------------------------------------------------------------------------
CORE_API_URL = os.getenv("CORE_API_URL", "http://localhost:8001")
METRICS_API_URL = os.getenv(
    "METRICS_API_URL", "https://backend-views-solana.onrender.com"
)
APP_API_KEY = os.getenv("APP_API_KEY", "")
# A Metrics API pode exigir uma chave separada (METRICS_API_KEY).
# Se não definida, usa APP_API_KEY como fallback (igual ao Oracle Agent).
METRICS_API_KEY = os.getenv("METRICS_API_KEY", "") or APP_API_KEY

# Timeout padrão para requisições HTTP (segundos)
REQUEST_TIMEOUT = int(os.getenv("TEST_TIMEOUT", "30"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class CoreApiClient:
    """Cliente HTTP simplificado para a Core API."""

    def __init__(self, base_url: str = CORE_API_URL, timeout: int = REQUEST_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.session.get(
            f"{self.base_url}{path}", timeout=self.timeout, **kwargs
        )

    def post(self, path: str, **kwargs) -> requests.Response:
        return self.session.post(
            f"{self.base_url}{path}", timeout=self.timeout, **kwargs
        )

    # --- endpoints de conveniência ---

    def health(self) -> requests.Response:
        return self.get("/health")

    def list_pools(self, **params) -> requests.Response:
        return self.get("/api/v1/pools", params=params)

    def get_pool(self, pool_pda: str) -> requests.Response:
        return self.get(f"/api/v1/pools/{pool_pda}")

    def get_pool_entries(self, pool_pda: str, **params) -> requests.Response:
        return self.get(f"/api/v1/pools/{pool_pda}/entries", params=params)

    def list_entries(self, **params) -> requests.Response:
        return self.get("/api/v1/entries", params=params)

    def get_entry(self, entry_pda: str) -> requests.Response:
        return self.get(f"/api/v1/entries/{entry_pda}")

    def get_entry_audit_logs(self, entry_pda: str) -> requests.Response:
        return self.get(f"/api/v1/entries/{entry_pda}/audit-logs")

    def hash_link(self, url: str) -> requests.Response:
        return self.post("/api/v1/utils/hash-link", json={"url": url})


class MetricsApiClient:
    """Cliente HTTP simplificado para a Metrics API remota."""

    def __init__(
        self,
        base_url: str = METRICS_API_URL,
        api_key: str = METRICS_API_KEY,
        timeout: int = REQUEST_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-API-Key": self.api_key,
            }
        )

    def analyze_batch(self, tasks: list[dict], job_id: Optional[str] = None) -> requests.Response:
        payload = {
            "job_id": job_id or f"test-{uuid.uuid4().hex[:8]}",
            "deep_analysis": False,
            "tasks": tasks,
        }
        return self.session.post(
            f"{self.base_url}/api/v1/analyze", json=payload, timeout=self.timeout
        )


def wait_for_service(url: str, retries: int = 10, delay: float = 2.0) -> bool:
    """Aguarda até que um serviço HTTP esteja disponível."""
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=5)
            if r.status_code < 500:
                return True
        except requests.exceptions.ConnectionError:
            pass
        if attempt < retries - 1:
            time.sleep(delay)
    return False


def make_pool_pda() -> str:
    """Gera um PDA fictício de 44 caracteres (base58-like) para testes."""
    chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    import random
    return "".join(random.choices(chars, k=44))


# ---------------------------------------------------------------------------
# Fixtures pytest
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def core_api() -> CoreApiClient:
    """Retorna um cliente para a Core API, aguardando o serviço ficar disponível."""
    client = CoreApiClient()
    available = wait_for_service(f"{CORE_API_URL}/health")
    if not available:
        pytest.skip(
            f"Core API não disponível em {CORE_API_URL}. "
            "Certifique-se de executar 'docker compose up -d' antes dos testes."
        )
    return client


@pytest.fixture(scope="session")
def metrics_api() -> MetricsApiClient:
    """Retorna um cliente para a Metrics API remota."""
    key = METRICS_API_KEY
    if not key:
        pytest.skip(
            "Chave da Metrics API não encontrada. "
            "Defina METRICS_API_KEY ou APP_API_KEY no .env antes de rodar os testes da Metrics API."
        )
    return MetricsApiClient(api_key=key)


@pytest.fixture
def sample_pool_payload() -> dict:
    """Payload de pool de referência para inserções de teste."""
    import datetime

    expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
    return {
        "pda_address": make_pool_pda(),
        "creator_wallet": "CreatorWallet" + make_pool_pda()[:20],
        "original_video_id": "dQw4w9WgXcQ",
        "prize_amount": 1_000_000_000,  # lamports
        "scoring_rules": {
            "views_weight": 5000,
            "likes_weight": 3000,
            "comments_weight": 2000,
        },
        "participant_count": 0,
        "total_score": 0,
        "status": "OPEN",
        "expiry_timestamp": expiry.isoformat(),
    }
