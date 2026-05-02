"""
test_core_api.py — Testes de integração da Core API (container solcuts-core-api).

Serviço testado: http://localhost:8001
Pré-condição  : docker compose up -d

Cobertura:
  ✔ Health check
  ✔ GET /api/v1/pools  — listagem e paginação
  ✔ GET /api/v1/pools/{pda}  — pool inexistente → 404
  ✔ GET /api/v1/pools/{pda}/entries
  ✔ GET /api/v1/entries  — listagem e filtros
  ✔ GET /api/v1/entries/{pda}  — entry inexistente → 404
  ✔ GET /api/v1/entries/{pda}/audit-logs
  ✔ POST /api/v1/utils/hash-link  — happy path
  ✔ POST /api/v1/utils/hash-link  — URL inválida → erro
  ✔ Validação de schema das respostas paginadas
"""

import pytest
import requests

from conftest import CoreApiClient, make_pool_pda


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthCheck:
    """Valida que o serviço está saudável e respondendo."""

    def test_health_returns_200(self, core_api: CoreApiClient):
        """GET /health → 200 OK com status 'ok'."""
        r = core_api.health()
        assert r.status_code == 200, f"Esperado 200, obtido {r.status_code}: {r.text}"

    def test_health_body_structure(self, core_api: CoreApiClient):
        """Corpo do health check deve conter {'status': 'ok'}."""
        r = core_api.health()
        body = r.json()
        assert "status" in body
        assert body["status"] == "ok"

    def test_health_content_type_json(self, core_api: CoreApiClient):
        """Resposta deve ser JSON."""
        r = core_api.health()
        assert "application/json" in r.headers.get("Content-Type", "")


# ─────────────────────────────────────────────────────────────────────────────
# Pools
# ─────────────────────────────────────────────────────────────────────────────

class TestPools:
    """Testes dos endpoints de Pools."""

    def test_list_pools_returns_200(self, core_api: CoreApiClient):
        """GET /api/v1/pools → 200."""
        r = core_api.list_pools()
        assert r.status_code == 200, r.text

    def test_list_pools_paginated_schema(self, core_api: CoreApiClient):
        """Resposta de listagem deve seguir o schema PaginatedResponse."""
        r = core_api.list_pools(page=1, limit=5)
        assert r.status_code == 200
        body = r.json()

        # Campos obrigatórios do schema PaginatedResponse
        assert "items" in body, "Campo 'items' ausente"
        assert "total" in body, "Campo 'total' ausente"
        assert "page" in body, "Campo 'page' ausente"
        assert "limit" in body, "Campo 'limit' ausente"

        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["page"] == 1
        assert body["limit"] == 5

    def test_list_pools_default_pagination(self, core_api: CoreApiClient):
        """Sem parâmetros, page=1 e limit=20 devem ser os padrões."""
        r = core_api.list_pools()
        body = r.json()
        assert body["page"] == 1
        assert body["limit"] == 20

    def test_list_pools_filter_by_status_open(self, core_api: CoreApiClient):
        """Filtro ?status=OPEN deve retornar apenas pools com status OPEN."""
        r = core_api.list_pools(status="OPEN")
        assert r.status_code == 200
        body = r.json()
        for pool in body["items"]:
            assert pool["status"] == "OPEN", (
                f"Pool com status inesperado: {pool['status']}"
            )

    def test_list_pools_filter_by_status_closed(self, core_api: CoreApiClient):
        """Filtro ?status=CLOSED não deve retornar pools OPEN."""
        r = core_api.list_pools(status="CLOSED")
        assert r.status_code == 200
        body = r.json()
        for pool in body["items"]:
            assert pool["status"] == "CLOSED"

    def test_list_pools_filter_by_nonexistent_creator(self, core_api: CoreApiClient):
        """Filtro por creator_wallet inexistente → lista vazia, total = 0."""
        r = core_api.list_pools(creator_wallet="NONEXISTENT_WALLET_XYZ_9999")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_get_pool_not_found(self, core_api: CoreApiClient):
        """GET /api/v1/pools/{pda_inexistente} → 404."""
        fake_pda = make_pool_pda()
        r = core_api.get_pool(fake_pda)
        assert r.status_code == 404, (
            f"Esperado 404 para PDA inexistente, obtido {r.status_code}"
        )

    def test_get_pool_not_found_detail(self, core_api: CoreApiClient):
        """404 deve conter campo 'detail' informativo."""
        r = core_api.get_pool(make_pool_pda())
        assert r.status_code == 404
        body = r.json()
        assert "detail" in body

    def test_pool_schema_fields(self, core_api: CoreApiClient):
        """Se houver pools, cada item deve conter os campos do PoolResponse."""
        r = core_api.list_pools(limit=1)
        body = r.json()
        if not body["items"]:
            pytest.skip("Nenhum pool cadastrado — pule para testar schema.")

        pool = body["items"][0]
        required_fields = [
            "pda_address",
            "creator_wallet",
            "original_video_id",
            "prize_amount",
            "scoring_rules",
            "participant_count",
            "total_score",
            "status",
            "expiry_timestamp",
            "indexed_at",
        ]
        for field in required_fields:
            assert field in pool, f"Campo obrigatório ausente: '{field}'"

    def test_get_existing_pool(self, core_api: CoreApiClient):
        """Se existir ao menos 1 pool, o GET por PDA deve retornar 200."""
        r = core_api.list_pools(limit=1)
        body = r.json()
        if not body["items"]:
            pytest.skip("Nenhum pool cadastrado.")

        pda = body["items"][0]["pda_address"]
        r2 = core_api.get_pool(pda)
        assert r2.status_code == 200
        pool = r2.json()
        assert pool["pda_address"] == pda

    def test_get_pool_entries_not_found(self, core_api: CoreApiClient):
        """GET /api/v1/pools/{pda_inexistente}/entries → 404."""
        r = core_api.get_pool_entries(make_pool_pda())
        assert r.status_code == 404

    def test_get_pool_entries_for_existing_pool(self, core_api: CoreApiClient):
        """Se pool existir, /entries deve retornar schema paginado."""
        r = core_api.list_pools(limit=1)
        body = r.json()
        if not body["items"]:
            pytest.skip("Nenhum pool cadastrado.")

        pda = body["items"][0]["pda_address"]
        r2 = core_api.get_pool_entries(pda, page=1, limit=10)
        assert r2.status_code == 200
        entries_body = r2.json()
        assert "items" in entries_body
        assert "total" in entries_body


# ─────────────────────────────────────────────────────────────────────────────
# Entries
# ─────────────────────────────────────────────────────────────────────────────

class TestEntries:
    """Testes dos endpoints de Entries."""

    def test_list_entries_returns_200(self, core_api: CoreApiClient):
        """GET /api/v1/entries → 200."""
        r = core_api.list_entries()
        assert r.status_code == 200, r.text

    def test_list_entries_paginated_schema(self, core_api: CoreApiClient):
        """Resposta deve seguir schema PaginatedResponse."""
        r = core_api.list_entries(page=1, limit=10)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "limit" in body

    def test_list_entries_filter_by_nonexistent_wallet(self, core_api: CoreApiClient):
        """Filtro por user_wallet inexistente → lista vazia."""
        r = core_api.list_entries(user_wallet="WALLET_INEXISTENTE_TEST_9999")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_get_entry_not_found(self, core_api: CoreApiClient):
        """GET /api/v1/entries/{pda_inexistente} → 404."""
        r = core_api.get_entry(make_pool_pda())
        assert r.status_code == 404

    def test_entry_schema_fields(self, core_api: CoreApiClient):
        """Se houver entries, cada item deve conter os campos do EntryResponse."""
        r = core_api.list_entries(limit=1)
        body = r.json()
        if not body["items"]:
            pytest.skip("Nenhuma entry cadastrada.")

        entry = body["items"][0]
        required_fields = [
            "pda_address",
            "pool_pda",
            "user_wallet",
            "channel_id",
            "clip_link",
            "views",
            "likes",
            "comments",
            "score",
            "claimed",
            "indexed_at",
        ]
        for field in required_fields:
            assert field in entry, f"Campo obrigatório ausente: '{field}'"

    def test_get_existing_entry(self, core_api: CoreApiClient):
        """Se existir ao menos 1 entry, GET por PDA deve retornar 200."""
        r = core_api.list_entries(limit=1)
        body = r.json()
        if not body["items"]:
            pytest.skip("Nenhuma entry cadastrada.")

        pda = body["items"][0]["pda_address"]
        r2 = core_api.get_entry(pda)
        assert r2.status_code == 200
        entry = r2.json()
        assert entry["pda_address"] == pda

    def test_get_entry_audit_logs_not_found(self, core_api: CoreApiClient):
        """GET /api/v1/entries/{pda_inexistente}/audit-logs → 404."""
        r = core_api.get_entry_audit_logs(make_pool_pda())
        assert r.status_code == 404

    def test_get_entry_audit_logs_returns_list(self, core_api: CoreApiClient):
        """Se entry existir, /audit-logs deve retornar uma lista."""
        r = core_api.list_entries(limit=1)
        body = r.json()
        if not body["items"]:
            pytest.skip("Nenhuma entry cadastrada.")

        pda = body["items"][0]["pda_address"]
        r2 = core_api.get_entry_audit_logs(pda)
        assert r2.status_code == 200
        logs = r2.json()
        assert isinstance(logs, list)

    def test_audit_log_schema_fields(self, core_api: CoreApiClient):
        """Se houver audit logs, devem conter os campos do AuditLogResponse."""
        r = core_api.list_entries(limit=5)
        body = r.json()
        if not body["items"]:
            pytest.skip("Nenhuma entry cadastrada.")

        for entry in body["items"]:
            pda = entry["pda_address"]
            r2 = core_api.get_entry_audit_logs(pda)
            logs = r2.json()
            if logs:
                log = logs[0]
                for field in ["id", "entry_pda", "validation_type", "status", "created_at"]:
                    assert field in log, f"Campo ausente no audit log: '{field}'"
                return  # basta encontrar um log para validar

        pytest.skip("Nenhum audit log encontrado nas entries existentes.")


# ─────────────────────────────────────────────────────────────────────────────
# Utils / hash-link
# ─────────────────────────────────────────────────────────────────────────────

class TestHashLink:
    """Testes do endpoint utilitário POST /api/v1/utils/hash-link."""

    VALID_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_hash_link_valid_url_200(self, core_api: CoreApiClient):
        """URL válida e acessível → 200 com hash."""
        r = core_api.hash_link(self.VALID_URL)
        assert r.status_code == 200, f"Obtido {r.status_code}: {r.text}"

    def test_hash_link_response_schema(self, core_api: CoreApiClient):
        """Resposta deve conter original_url, normalized_url, hash_bytes, hash_hex."""
        r = core_api.hash_link(self.VALID_URL)
        assert r.status_code == 200
        body = r.json()
        assert "original_url" in body
        assert "normalized_url" in body
        assert "hash_bytes" in body
        assert "hash_hex" in body

    def test_hash_link_hash_bytes_length(self, core_api: CoreApiClient):
        """SHA-256 deve produzir exatamente 32 bytes."""
        r = core_api.hash_link(self.VALID_URL)
        assert r.status_code == 200
        body = r.json()
        assert len(body["hash_bytes"]) == 32

    def test_hash_link_hex_consistency(self, core_api: CoreApiClient):
        """hash_hex deve ser codificação hex dos hash_bytes."""
        r = core_api.hash_link(self.VALID_URL)
        assert r.status_code == 200
        body = r.json()
        expected_hex = bytes(body["hash_bytes"]).hex()
        assert body["hash_hex"] == expected_hex

    def test_hash_link_idempotent(self, core_api: CoreApiClient):
        """Mesma URL deve produzir o mesmo hash em chamadas consecutivas."""
        r1 = core_api.hash_link(self.VALID_URL)
        r2 = core_api.hash_link(self.VALID_URL)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["hash_hex"] == r2.json()["hash_hex"]

    def test_hash_link_invalid_url_returns_error(self, core_api: CoreApiClient):
        """URL completamente inválida → 422 (Unprocessable Entity)."""
        r = core_api.hash_link("nao-eh-uma-url-valida")
        assert r.status_code in (422, 400), (
            f"Esperado 422 ou 400 para URL inválida, obtido {r.status_code}"
        )

    def test_hash_link_unreachable_url(self, core_api: CoreApiClient):
        """URL bem-formada mas inacessível → erro (422)."""
        r = core_api.hash_link("https://host.inexistente.solcuts.invalid/video")
        assert r.status_code in (422, 400)

    def test_hash_link_missing_body(self, core_api: CoreApiClient):
        """Requisição sem corpo → 422."""
        r = core_api.session.post(
            f"{core_api.base_url}/api/v1/utils/hash-link",
            json={},
            timeout=core_api.timeout,
        )
        assert r.status_code == 422

    def test_hash_link_url_normalization(self, core_api: CoreApiClient):
        """URL com maiúsculas no scheme/host deve ser normalizada."""
        r = core_api.hash_link("HTTPS://WWW.YOUTUBE.COM/watch?v=dQw4w9WgXcQ")
        assert r.status_code == 200
        body = r.json()
        assert body["normalized_url"].startswith("https://www.youtube.com")


# ─────────────────────────────────────────────────────────────────────────────
# Paginação e bordas
# ─────────────────────────────────────────────────────────────────────────────

class TestPagination:
    """Testes de paginação e casos de borda nos endpoints de listagem."""

    def test_pools_limit_1(self, core_api: CoreApiClient):
        """limit=1 deve retornar no máximo 1 item."""
        r = core_api.list_pools(limit=1)
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 1

    def test_pools_limit_100(self, core_api: CoreApiClient):
        """limit=100 (máximo permitido) deve retornar 200."""
        r = core_api.list_pools(limit=100)
        assert r.status_code == 200

    def test_pools_limit_above_max(self, core_api: CoreApiClient):
        """limit=101 deve retornar erro de validação (422)."""
        r = core_api.list_pools(limit=101)
        assert r.status_code == 422

    def test_pools_page_0_invalid(self, core_api: CoreApiClient):
        """page=0 é inválido (ge=1) → 422."""
        r = core_api.list_pools(page=0)
        assert r.status_code == 422

    def test_pools_large_page_returns_empty_items(self, core_api: CoreApiClient):
        """Página muito alta → itens vazios, mas total correto."""
        r = core_api.list_pools(page=999999, limit=10)
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []
        assert body["total"] >= 0

    def test_entries_limit_1(self, core_api: CoreApiClient):
        """limit=1 para entries deve retornar no máximo 1 item."""
        r = core_api.list_entries(limit=1)
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 1
