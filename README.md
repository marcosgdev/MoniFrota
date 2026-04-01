# MoniFrota

> Plataforma de monitoramento inteligente de abastecimentos da frota pública estadual.

---

## Visão Geral

O **MoniFrota** é uma aplicação web desenvolvida para fiscalização em tempo real dos abastecimentos realizados pela frota pública do Estado do Pará. Integrada à API **Sisatec**, a plataforma coleta, persiste e analisa automaticamente cada abastecimento realizado — detectando anomalias, validando fornecedores e fornecendo histórico consolidado por veículo, secretaria e período.

O sistema foi projetado para operar em escala estadual, suportando **milhares de abastecimentos diários** distribuídos em múltiplas unidades gestoras, com rastreabilidade de no mínimo **3 anos de histórico**.

---

## Problema Resolvido

Antes do MoniFrota, a fiscalização de abastecimentos dependia de relatórios manuais e consultas avulsas à Sisatec — processo lento, sujeito a falhas humanas e sem visibilidade em tempo real. Irregularidades como abastecimentos em postos fantasmas, quilometragem regressiva ou volumes fora do padrão só eram identificadas dias depois, dificultando ações corretivas.

---

## Benefícios

- **Fiscalização em tempo real** — abastecimentos do dia visíveis no mapa minutos após ocorrerem
- **Detecção automática de fraudes** — 6 regras de alerta aplicadas a cada registro
- **Histórico de 3+ anos** — dados armazenados localmente em PostgreSQL, independente da disponibilidade da Sisatec
- **Zero dependência de planilhas** — todo o fluxo de coleta, análise e visualização é automatizado
- **Rastreabilidade completa** — cada abastecimento vinculado ao veículo, condutor, posto e secretaria
- **Baixo custo operacional** — stack open source, deploy em VPS único

---

## Gargalos Resolvidos

| Problema anterior | Solução implementada |
|---|---|
| Consulta à Sisatec em toda requisição — lenta e instável | Banco local PostgreSQL como fonte primária; Sisatec apenas para ingestão |
| Sem histórico além do que a Sisatec retornava | Persistência local com backfill de até 3 anos via `scripts/backfill.py` |
| Validação de CNPJ repetida a cada chamada | Cache Redis de 24h por CNPJ — chamada única por fornecedor por dia |
| Dados do dia atual sempre desatualizados | Scheduler intraday sincroniza com a Sisatec a cada 3 minutos |
| Registros tardios do dia anterior perdidos | Job diário à meia-noite reprocessa o dia anterior |
| Sem separação entre dados históricos e dados ao vivo | Dois fluxos distintos: histórico via DB, intraday via sync periódico |

---

## Arquitetura

```
Sisatec API
    │
    ▼
┌─────────────────────┐
│   Ingestion Service │  ← scheduler a cada 3 min (intraday)
│   + Backfill Script │  ← execução única para histórico
└────────┬────────────┘
         │  upsert (ON CONFLICT DO NOTHING)
         ▼
┌─────────────────────┐       ┌──────────────────────┐
│     PostgreSQL      │       │    Redis             │
│                     │       │                      │
│  tabela             │       │  CNPJ cache (24h)    │
│  abastecimentos     │       │  Sisatec page cache  │
│  (3+ anos)          │       │  (5 min)             │
└────────┬────────────┘       └──────────────────────┘
         │
         ▼
┌─────────────────────┐
│     FastAPI         │  ← endpoints consultam o banco
│     + Motor         │  ← alertas calculados on-the-fly
│       de Alertas    │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Dashboard Leaflet  │  ← mapa interativo, filtros, histórico
└─────────────────────┘
```

---

## Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| API | Python 3.12 + FastAPI 0.111 |
| Banco de dados | PostgreSQL 14+ via SQLAlchemy 2.x async + asyncpg |
| Cache | Redis 7 |
| Scheduler | APScheduler 3.10 (AsyncIOScheduler) |
| HTTP client | HTTPX (async) |
| Validação | Pydantic v2 |
| Frontend | Leaflet.js + HTML/CSS vanilla |
| Servidor | Uvicorn + Nginx (reverse proxy) |
| Deploy | Ubuntu 22.04 LTS + systemd |

---

## Estrutura do Projeto

```
MoniFrota/
├── app/
│   ├── main.py                      # Lifespan: init DB + scheduler
│   ├── config.py                    # Settings via .env (pydantic-settings)
│   ├── db/
│   │   ├── database.py              # Engine async, init_db(), close_db()
│   │   ├── models.py                # ORM: tabela abastecimentos
│   │   └── repository.py           # upsert_abastecimentos(), buscar_por_periodo()
│   ├── models/
│   │   └── schemas.py               # Schemas Pydantic (request/response)
│   ├── routers/
│   │   └── api.py                   # Endpoints REST
│   └── services/
│       ├── sisatec_service.py       # Integração Sisatec (paginação + cache)
│       ├── ingestion_service.py     # sync_hoje(), sync_ontem(), sync_periodo()
│       ├── alertas_service.py       # Motor de detecção de anomalias
│       ├── cnpj_service.py          # Validação CNPJ via ReceitaWS
│       └── mock_data.py             # Dados simulados para desenvolvimento
├── scripts/
│   └── backfill.py                  # Backfill histórico em janelas mensais
├── tests/
│   └── test_alertas.py              # Testes automatizados do motor de alertas
├── frontend/
│   └── index.html                   # Dashboard Leaflet
├── .env.example                     # Template de configuração
├── requirements.txt
└── deploy.sh                        # Setup automatizado Ubuntu 22.04
```

---

## Regras de Alerta

Cada abastecimento é classificado automaticamente em `ok`, `warn` ou `danger`:

| Severidade | Regra |
|---|---|
| `danger` | CNPJ inapto ou baixado na Receita Federal |
| `danger` | CNAE do posto não corresponde a comércio de combustíveis |
| `warn` | Abastecimento fora do horário comercial (antes 06h ou após 22h) |
| `warn` | Quilometragem atual menor que a anterior (km regressivo) |
| `warn` | Volume abastecido acima de 120% da média histórica do veículo |
| `warn` | Preço por litro acima de 120% da mediana do combustível no período |

---

## Endpoints da API

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/mapa` | Pontos georreferenciados para o mapa |
| `GET` | `/api/alertas` | Somente abastecimentos com anomalia |
| `GET` | `/api/veiculo/{placa}` | Histórico completo de um veículo |
| `GET` | `/api/comparativo` | Comparativo de métricas entre dois períodos |
| `GET` | `/api/placas` | Lista de placas ativas no período |
| `GET` | `/api/cnpj/{cnpj}` | Situação cadastral de um CNPJ |
| `POST` | `/api/sync` | Força sincronização manual com a Sisatec |
| `GET` | `/api/health` | Health check (status do banco e modo) |
| `GET` | `/docs` | Swagger UI (somente em `ENV=development`) |

### Parâmetros de data

Todos os endpoints de período aceitam `dataInicio` e `dataFim` no formato `MM-dd-yyyy`.

---

## Instalação e Execução Local

```bash
# 1. Clonar o repositório
git clone https://github.com/marcosgdev/MoniFrota.git
cd MoniFrota

# 2. Criar e ativar virtualenv
python3.11 -m venv venv
source venv/bin/activate       # Linux/macOS
venv\Scripts\activate          # Windows

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Configurar variáveis de ambiente
cp .env.example .env
# USE_MOCK=true por padrão — não requer banco nem credenciais Sisatec

# 5. Executar testes
pytest tests/ -v

# 6. Iniciar servidor
uvicorn app.main:app --reload --port 8000
```

Acesse `http://localhost:8000` com usuário `admin` / senha `admin`.

---

## Deploy em Produção (Ubuntu 22.04)

```bash
# 1. Copiar projeto para o servidor
scp -r MoniFrota/ usuario@seu-vps:/opt/frotagov/

# 2. Executar script de setup (instala PostgreSQL, Redis, Nginx, systemd)
ssh usuario@seu-vps "bash /opt/frotagov/deploy.sh seu-dominio.com.br"

# 3. Configurar credenciais reais
nano /opt/frotagov/.env
# SISATEC_CODIGO, SISATEC_KEY, USE_MOCK=false, DASHBOARD_PASS

# 4. Iniciar serviço
systemctl start frotagov

# 5. Executar backfill histórico (uma única vez)
cd /opt/frotagov && venv/bin/python -m scripts.backfill --anos 3

# 6. Ativar HTTPS
certbot --nginx -d seu-dominio.com.br
```

---

## Variáveis de Ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `SISATEC_CODIGO` | `0000` | Código de acesso à API Sisatec |
| `SISATEC_KEY` | `MOCK` | Chave de autenticação Sisatec |
| `USE_MOCK` | `true` | `true` = sem banco/Sisatec (desenvolvimento) |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Connection string PostgreSQL |
| `REDIS_URL` | `redis://localhost:6379` | Connection string Redis |
| `DASHBOARD_USER` | `admin` | Usuário do dashboard |
| `DASHBOARD_PASS` | `admin` | Senha do dashboard |
| `ENV` | `development` | `development` habilita `/docs` e CORS aberto |
| `SYNC_INTERVAL_MIN` | `3` | Intervalo do scheduler intraday (minutos) |

---

## Licença

Uso restrito — Governo do Estado do Pará.
