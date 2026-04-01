"""
Serviço de integração com a API Sisatec WS Abastecimento.
- Modo mock (USE_MOCK=true): retorna dados simulados, zero chamadas externas
- Modo real (USE_MOCK=false): chama a API real com paginação automática
  e cache Redis de 5 minutos por período consultado
"""
import json
import logging
import httpx
import redis.asyncio as aioredis

from app.config import settings
from app.models.schemas import AbastecimentoRaw
from app.services.mock_data import MOCK_ABASTECIMENTOS

logger = logging.getLogger(__name__)

BASE_URL  = "https://ws.sisatec.com.br/api/abastecimento/novo/bydata"
CACHE_TTL = 300  # 5 minutos

_redis: aioredis.Redis | None = None

async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def buscar_abastecimentos(
    data_inicio: str,
    data_fim: str,
    unidades: str | None = None,
    status: str = "1",
) -> list[AbastecimentoRaw]:
    """
    Retorna todos os abastecimentos do período, percorrendo todas as páginas.

    Parâmetros:
        data_inicio: formato MM-dd-yyyy  ex: 03-01-2025
        data_fim:    formato MM-dd-yyyy  ex: 03-31-2025
        unidades:    ex: "2,97" (opcional)
        status:      "0" inativo | "1" ativo | "2" ambos
    """

    # --- MODO MOCK ---
    if settings.use_mock:
        return [AbastecimentoRaw(**a) for a in MOCK_ABASTECIMENTOS]

    # --- CACHE ---
    cache_key = f"sisatec:{data_inicio}:{data_fim}:{unidades}:{status}"
    try:
        r = await get_redis()
        cached = await r.get(cache_key)
        if cached:
            return [AbastecimentoRaw(**a) for a in json.loads(cached)]
    except Exception as e:
        logger.warning(f"Redis indisponível: {e}")

    # --- PAGINAÇÃO AUTOMÁTICA ---
    todos: list[dict] = []
    pagina = 1

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            params = {
                "codigo":     settings.sisatec_codigo,
                "key":        settings.sisatec_key,
                "dataInicio": data_inicio,
                "dataFim":    data_fim,
                "status":     status,
                "pagina":     pagina,
            }
            if unidades:
                params["unidades"] = unidades

            try:
                resp = await client.get(BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Sisatec HTTP {e.response.status_code}: {e}")
                break
            except Exception as e:
                logger.error(f"Erro ao chamar Sisatec: {e}")
                break

            # Verifica autorização
            if isinstance(data, dict) and data.get("Message") == "nao autorizado":
                logger.error("Sisatec: credenciais inválidas")
                break

            abastecimentos = data.get("abastecimentos", [])
            todos.extend(abastecimentos)

            pagina_atual  = data.get("pagina_atual", pagina)
            total_paginas = data.get("total_paginas", 1)

            logger.info(f"Sisatec: página {pagina_atual}/{total_paginas} — {len(abastecimentos)} registros")

            if pagina_atual >= total_paginas:
                break
            pagina += 1

    # --- GRAVAR CACHE ---
    try:
        r = await get_redis()
        await r.set(cache_key, json.dumps(todos), ex=CACHE_TTL)
    except Exception:
        pass

    return [AbastecimentoRaw(**a) for a in todos]
