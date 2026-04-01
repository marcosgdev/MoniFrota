"""
Serviço de ingestão: busca abastecimentos na Sisatec e persiste no banco local.

Funções principais:
  sync_periodo(inicio, fim)  — janela arbitrária (usada pelo backfill e pelo scheduler)
  sync_hoje()                — abastecimentos de hoje (chamado a cada N minutos)
  sync_ontem()               — garante completude do dia anterior (chamado à meia-noite)
"""
import logging
from datetime import date, timedelta

from app.services.sisatec_service import buscar_abastecimentos
from app.db.repository import upsert_abastecimentos

logger = logging.getLogger(__name__)


async def sync_periodo(data_inicio: str, data_fim: str) -> int:
    """
    Busca todos os abastecimentos do período na Sisatec e faz upsert no banco.
    Retorna o número de novos registros inseridos.

    Parâmetros no formato MM-dd-yyyy (padrão Sisatec).
    """
    logger.info(f"Ingestion: sincronizando {data_inicio} → {data_fim}")
    registros = await buscar_abastecimentos(data_inicio, data_fim)
    novos = await upsert_abastecimentos(registros)
    logger.info(f"Ingestion: {len(registros)} registros recebidos, {novos} novos inseridos")
    return novos


async def sync_hoje() -> int:
    """Sincroniza abastecimentos de hoje. Chamado periodicamente pelo scheduler."""
    hoje = date.today().strftime("%m-%d-%Y")
    return await sync_periodo(hoje, hoje)


async def sync_ontem() -> int:
    """
    Sincroniza abastecimentos de ontem.
    Garante que registros com atraso de processamento na Sisatec sejam capturados.
    """
    ontem = (date.today() - timedelta(days=1)).strftime("%m-%d-%Y")
    return await sync_periodo(ontem, ontem)
