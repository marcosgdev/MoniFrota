"""
Serviço de validação de CNPJ.
- Produção: chama ReceitaWS (gratuito, limite 3 req/min)
- Cache Redis de 24h por CNPJ para não estourar o limite
- Mock: retorna dados simulados sem nenhuma chamada externa
"""
import re
import json
import logging
import httpx
import redis.asyncio as aioredis

from app.config import settings
from app.models.schemas import SituacaoCNPJ
from app.services.mock_data import MOCK_CNPJ

logger = logging.getLogger(__name__)

CACHE_TTL = 86_400        # 24 horas
RECEITAWS  = "https://receitaws.com.br/v1/cnpj/{cnpj}"
CNPJWS     = "https://publica.cnpj.ws/cnpj/{cnpj}"   # alternativa sem limite

_redis: aioredis.Redis | None = None

async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _limpar_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


async def validar_cnpj(cnpj_formatado: str) -> SituacaoCNPJ:
    """Retorna situação cadastral do CNPJ. Usa cache Redis de 24h."""

    cnpj_limpo = _limpar_cnpj(cnpj_formatado)

    # --- MODO MOCK ---
    if settings.use_mock:
        dados = MOCK_CNPJ.get(cnpj_formatado)
        if dados:
            return SituacaoCNPJ(cnpj=cnpj_formatado, **dados)
        return SituacaoCNPJ(
            cnpj=cnpj_formatado, ok=True, situacao="Ativa",
            atividade="Não identificada", municipio="Desconhecido", uf="--",
        )

    # --- CACHE ---
    try:
        r = await get_redis()
        cached = await r.get(f"cnpj:{cnpj_limpo}")
        if cached:
            return SituacaoCNPJ(**json.loads(cached))
    except Exception as e:
        logger.warning(f"Redis indisponível: {e}")

    # --- CHAMADA À API ---
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Tenta ReceitaWS primeiro; em caso de rate-limit, tenta cnpj.ws
            url = RECEITAWS.format(cnpj=cnpj_limpo)
            resp = await client.get(url)

            if resp.status_code == 429:
                url = CNPJWS.format(cnpj=cnpj_limpo)
                resp = await client.get(url)

            resp.raise_for_status()
            data = resp.json()

        situacao   = data.get("situacao", "Desconhecida")
        atividade  = ""
        if "atividade_principal" in data and data["atividade_principal"]:
            atividade = data["atividade_principal"][0].get("text", "")
        elif "cnae_fiscal_descricao" in data:
            atividade = data["cnae_fiscal_descricao"]

        municipio  = data.get("municipio", data.get("municipio", ""))
        uf         = data.get("uf", "")
        abertura   = data.get("abertura", data.get("data_inicio_atividade", ""))
        ok         = situacao.upper() == "ATIVA"

        resultado = SituacaoCNPJ(
            cnpj=cnpj_formatado, ok=ok, situacao=situacao,
            atividade=atividade, municipio=municipio, uf=uf, abertura=abertura,
        )

    except Exception as e:
        logger.error(f"Erro ao validar CNPJ {cnpj_formatado}: {e}")
        resultado = SituacaoCNPJ(
            cnpj=cnpj_formatado, ok=False, situacao="Erro",
            atividade="", municipio="", uf="", erro=str(e),
        )

    # --- GRAVAR CACHE ---
    try:
        r = await get_redis()
        await r.set(f"cnpj:{cnpj_limpo}", resultado.model_dump_json(), ex=CACHE_TTL)
    except Exception:
        pass

    return resultado
