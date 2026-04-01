# FrotaGov — Monitoramento de Abastecimentos

## Estrutura do projeto

```
frotagov/
├── app/
│   ├── main.py                  # Entrada FastAPI
│   ├── config.py                # Settings via .env
│   ├── models/
│   │   └── schemas.py           # Modelos Pydantic
│   ├── routers/
│   │   └── api.py               # Endpoints GET /api/mapa, /alertas, /cnpj
│   └── services/
│       ├── sisatec_service.py   # Integração API Sisatec (mock + real)
│       ├── cnpj_service.py      # Validação CNPJ via ReceitaWS
│       ├── alertas_service.py   # Motor de detecção de anomalias
│       └── mock_data.py         # Dados simulados no formato Sisatec
├── tests/
│   └── test_alertas.py          # 17 testes automatizados
├── frontend/
│   └── index.html               # Dashboard Leaflet (copiar o arquivo gerado)
├── .env.example                 # Variáveis de ambiente (nunca commitar o .env)
├── requirements.txt
└── deploy.sh                    # Setup VPS Ubuntu 22.04
```

## Instalação local (desenvolvimento)

```bash
# 1. Criar virtualenv
python3.11 -m venv venv && source venv/bin/activate

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar variáveis
cp .env.example .env
# Edite .env — enquanto não tiver credenciais, mantenha USE_MOCK=true

# 4. Rodar testes
pytest tests/ -v

# 5. Iniciar servidor
uvicorn app.main:app --reload --port 8000
```

## Endpoints disponíveis

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/mapa` | Pontos para o Leaflet com status e CNPJ |
| GET | `/api/alertas` | Apenas abastecimentos com anomalia |
| GET | `/api/cnpj/{cnpj}` | Situação cadastral de um CNPJ |
| GET | `/api/health` | Health check |
| GET | `/docs` | Swagger UI (apenas em development) |

### Parâmetros do `/api/mapa`

| Parâmetro | Formato | Exemplo |
|-----------|---------|---------|
| `dataInicio` | MM-dd-yyyy | `03-01-2025` |
| `dataFim` | MM-dd-yyyy | `03-31-2025` |
| `unidades` | inteiros separados por vírgula | `2,97` |
| `status` | 0=inativo / 1=ativo / 2=ambos | `1` |

## Ativar dados reais (quando as credenciais chegarem)

Edite `/opt/frotagov/.env`:

```env
SISATEC_CODIGO=SEU_CODIGO_AQUI
SISATEC_KEY=SUA_KEY_AQUI
USE_MOCK=false
```

Reinicie o serviço:

```bash
systemctl restart frotagov
```

## Regras de alerta implementadas

| Prioridade | Regra | Status |
|-----------|-------|--------|
| DANGER | CNPJ inapto ou baixado na Receita Federal | Vermelho |
| DANGER | CNAE do posto não é de combustíveis | Vermelho |
| WARN | Abastecimento fora do horário (antes 06h / após 22h) | Laranja |
| WARN | Km atual menor que Km anterior | Laranja |
| WARN | Volume > 120% da média do veículo | Laranja |
| WARN | Preço/L > 120% da mediana do combustível | Laranja |

## Deploy no VPS

```bash
# Copiar projeto para o servidor
scp -r frotagov/ usuario@seu-vps:/opt/frotagov/

# Executar script de deploy
ssh usuario@seu-vps "bash /opt/frotagov/deploy.sh seu-dominio.com.br"
```
