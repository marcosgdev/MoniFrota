"""
Operações de persistência para a tabela abastecimentos.
"""
import logging
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.database import get_session_factory
from app.db.models import Abastecimento
from app.models.schemas import AbastecimentoRaw

logger = logging.getLogger(__name__)


def _parse_data(data_str: str) -> date:
    """Converte 'dd/MM/yyyy' → date. Retorna hoje em caso de formato inválido."""
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(data_str, fmt).date()
        except ValueError:
            continue
    logger.warning(f"Formato de data não reconhecido: {data_str!r} — usando hoje")
    return date.today()


def _to_row(ab: AbastecimentoRaw) -> dict:
    return {
        "cod_abastecimento":     ab.codAbastecimento,
        "placa":                 ab.placa,
        "prefixo":               ab.prefixo or "",
        "modelo":                ab.modelo or "",
        "marca":                 ab.marca or "",
        "condutor":              ab.condutor,
        "matricula_condutor":    ab.matricula_condutor or "",
        "centro_custo_condutor": ab.centroDeCustoCondutor or "",
        "posto":                 ab.posto,
        "posto_razao":           ab.posto_razao or "",
        "endereco":              ab.endereco or "",
        "estado":                ab.estado or "",
        "cnpj":                  ab.CNPJ,
        "latitude":              ab.latitude or "0",
        "longitude":             ab.longitude or "0",
        "data_str":              ab.data,
        "data_date":             _parse_data(ab.data),
        "hora":                  ab.hora,
        "combustivel":           ab.combustivel,
        "valor":                 ab.valor,
        "valor_litro":           ab.valorLitro,
        "quantidade_litros":     ab.quantidadeLitros,
        "km_atual":              ab.kmAtual or "0",
        "km_anterior":           ab.kmAnterior or "0",
        "status":                ab.status,
        "tipo_servico":          ab.tipo_servico or "",
        "nome_servico":          ab.nomeServico or "",
        "tipo_frota":            ab.TipoFrota or "",
        "centro_custo_veiculo":  ab.centroDeCustoVeiculo or "",
    }


def _from_row(row: Abastecimento) -> AbastecimentoRaw:
    return AbastecimentoRaw(
        codAbastecimento     = row.cod_abastecimento,
        placa                = row.placa,
        prefixo              = row.prefixo,
        modelo               = row.modelo,
        marca                = row.marca,
        condutor             = row.condutor,
        matricula_condutor   = row.matricula_condutor,
        centroDeCustoCondutor= row.centro_custo_condutor,
        posto                = row.posto,
        posto_razao          = row.posto_razao,
        endereco             = row.endereco,
        estado               = row.estado,
        CNPJ                 = row.cnpj,
        latitude             = row.latitude,
        longitude            = row.longitude,
        data                 = row.data_str,
        hora                 = row.hora,
        combustivel          = row.combustivel,
        valor                = row.valor,
        valorLitro           = row.valor_litro,
        quantidadeLitros     = row.quantidade_litros,
        kmAtual              = row.km_atual,
        kmAnterior           = row.km_anterior,
        status               = row.status,
        tipo_servico         = row.tipo_servico,
        nomeServico          = row.nome_servico,
        TipoFrota            = row.tipo_frota,
        centroDeCustoVeiculo = row.centro_custo_veiculo,
    )


async def upsert_abastecimentos(records: list[AbastecimentoRaw]) -> int:
    """
    Insere novos registros ignorando duplicatas (ON CONFLICT DO NOTHING).
    Retorna o número de linhas efetivamente inseridas.
    """
    if not records:
        return 0

    rows = [_to_row(ab) for ab in records]
    factory = await get_session_factory()
    async with factory() as session:
        stmt = (
            pg_insert(Abastecimento)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["cod_abastecimento"])
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount


async def buscar_por_periodo(
    data_inicio: date,
    data_fim: date,
    unidades: str | None = None,
) -> list[AbastecimentoRaw]:
    """
    Retorna todos os abastecimentos do período a partir do banco local.
    O parâmetro unidades (ex: '2,97') filtra por centro_custo_veiculo quando fornecido.
    """
    factory = await get_session_factory()
    async with factory() as session:
        stmt = (
            select(Abastecimento)
            .where(Abastecimento.data_date >= data_inicio)
            .where(Abastecimento.data_date <= data_fim)
            .order_by(Abastecimento.data_date, Abastecimento.hora)
        )
        if unidades:
            codigos = [u.strip() for u in unidades.split(",")]
            stmt = stmt.where(Abastecimento.centro_custo_veiculo.in_(codigos))

        result = await session.execute(stmt)
        return [_from_row(r) for r in result.scalars().all()]
