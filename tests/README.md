# SolCuts — Testes de Integração

Scripts de teste para validar a integração entre os componentes do projeto em execução via `docker compose`.

## Pré-requisitos

```bash
# Instalar dependências (usa apenas stdlib + requests + pytest)
pip install pytest requests pytest-timeout
```

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `CORE_API_URL` | `http://localhost:8001` | URL da Core API (Docker local) |
| `METRICS_API_URL` | `https://backend-views-solana.onrender.com` | URL da Metrics API remota |
| `APP_API_KEY` | *(do .env)* | Chave compartilhada gerada pelo `setup.sh` |
| `METRICS_API_KEY` | *(fallback para APP_API_KEY)* | Chave específica da Metrics API se diferente |
| `TEST_TIMEOUT` | `30` | Timeout em segundos por requisição HTTP |

> **Atenção:** Os testes da Metrics API exigem uma chave válida para `backend-views-solana.onrender.com`.
> Se a sua `APP_API_KEY` local não for aceita, defina `METRICS_API_KEY` com a chave correta:
> ```bash
> export METRICS_API_KEY=sua_chave_da_metrics_api
> pytest tests/test_metrics_api.py -v
> ```

## Subir os serviços

```bash
cd ..
docker compose up -d
```

## Executar todos os testes

```bash
# Da raiz do projeto
pytest tests/ -v

# Ou do diretório tests/
cd tests
pytest -v
```

## Executar suítes individuais

```bash
# Apenas Core API
pytest tests/test_core_api.py -v

# Apenas Metrics API remota
pytest tests/test_metrics_api.py -v

# Fluxo completo de integração
pytest tests/test_integration_flow.py -v
```

## Estrutura dos testes

| Arquivo | Componentes testados |
|---------|---------------------|
| `conftest.py` | Fixtures e helpers compartilhados |
| `test_core_api.py` | `core-api` (http://localhost:8001) — endpoints REST |
| `test_metrics_api.py` | `metrics-api` remota (https://backend-views-solana.onrender.com) |
| `test_integration_flow.py` | Fluxo end-to-end: Core API → Oracle → Metrics API |

## Arquitetura dos serviços testados

```
┌─────────────────┐     ┌─────────────────────────┐
│   core-api      │     │  metrics-api (remota)   │
│ localhost:8001  │     │  backend-views-solana   │
│  (Docker local) │     │     .onrender.com       │
└─────────────────┘     └─────────────────────────┘
         │                          ▲
         └─────── Oracle Agent ─────┘
              (worker, sem porta HTTP)
```
