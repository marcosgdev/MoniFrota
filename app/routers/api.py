"""
Endpoints da API:
  GET /api/mapa            — pontos para o Leaflet
  GET /api/alertas         — apenas abastecimentos com anomalia
  GET /api/veiculo/{placa} — histórico de um veículo
  GET /api/tipo-veiculo    — histórico agregado por marca/modelo
  GET /api/modelos         — lista marcas/modelos disponíveis no período
  GET /api/comparativo     — compara métricas entre dois períodos
  GET /api/placas          — lista placas ativas no período
  GET /api/cnpj/{cnpj}     — consulta individual de CNPJ
  GET /api/sync            — força sincronização manual (somente modo real)
"""
import asyncio
import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse

import statistics
from app.config import settings
from app.models.schemas import (
    RespostaMapa, SituacaoCNPJ,
    HistoricoVeiculo, EventoVeiculo,
    HistoricoTipoVeiculo, ResumoVeiculoTipo,
    RespostaModelos, ModeloDisponivel,
    RespostaComparativo, MetricasPeriodo,
)
from app.services.cnpj_service import validar_cnpj
from app.services.alertas_service import classificar, montar_ponto
from app.services.alertas_service import _media_por_veiculo, _mediana_preco_combustivel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# ── Helpers de data ───────────────────────────────────────────────────────────

def _default_datas() -> tuple[str, str]:
    hoje   = date.today()
    inicio = hoje - timedelta(days=30)
    return inicio.strftime("%m-%d-%Y"), hoje.strftime("%m-%d-%Y")


def _api_para_date(s: str) -> date:
    """Converte 'MM-dd-yyyy' → date."""
    return datetime.strptime(s, "%m-%d-%Y").date()


async def _buscar(inicio: str, fim: str, unidades: str | None = None):
    """
    Fonte de dados unificada:
      - use_mock=True  → Sisatec mock (sem banco)
      - use_mock=False → banco local (PostgreSQL)
    """
    if settings.use_mock:
        from app.services.sisatec_service import buscar_abastecimentos
        return await buscar_abastecimentos(inicio, fim, unidades)

    from app.db.repository import buscar_por_periodo
    return await buscar_por_periodo(
        _api_para_date(inicio),
        _api_para_date(fim),
        unidades,
    )


# ── Lógica interna compartilhada ─────────────────────────────────────────────

async def _montar_resposta_mapa(inicio: str, fim: str, unidades: str | None, status: str):
    abastecimentos = await _buscar(inicio, fim, unidades)
    if not abastecimentos:
        return RespostaMapa(total=0, alertas=0, pontos=[])

    cnpjs_unicos = list({a.CNPJ for a in abastecimentos if a.CNPJ})
    resultados   = await asyncio.gather(*[validar_cnpj(c) for c in cnpjs_unicos], return_exceptions=True)

    mapa_cnpj: dict[str, SituacaoCNPJ] = {}
    for cnpj, resultado in zip(cnpjs_unicos, resultados):
        if isinstance(resultado, SituacaoCNPJ):
            mapa_cnpj[cnpj] = resultado
        else:
            logger.warning(f"Falha ao validar CNPJ {cnpj}: {resultado}")

    media_veiculo = _media_por_veiculo(abastecimentos)
    mediana_preco = _mediana_preco_combustivel(abastecimentos)

    pontos = []
    for ab in abastecimentos:
        ponto = montar_ponto(ab, mapa_cnpj.get(ab.CNPJ), media_veiculo, mediana_preco)
        if ponto:
            pontos.append(ponto)

    alertas = sum(1 for p in pontos if p.status_mapa != "ok")
    return RespostaMapa(total=len(pontos), alertas=alertas, pontos=pontos)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/mapa", response_model=RespostaMapa)
async def get_mapa(
    dataInicio: str | None = Query(default=None, description="MM-dd-yyyy"),
    dataFim:    str | None = Query(default=None, description="MM-dd-yyyy"),
    unidades:   str | None = Query(default=None, description="ex: 2,97"),
    status:     str        = Query(default="1",  description="0|1|2"),
):
    inicio, fim = dataInicio or "", dataFim or ""
    if not inicio or not fim:
        inicio, fim = _default_datas()
    return await _montar_resposta_mapa(inicio, fim, unidades, status)


@router.get("/alertas")
async def get_alertas(
    dataInicio: str | None = Query(default=None),
    dataFim:    str | None = Query(default=None),
    unidades:   str | None = Query(default=None),
):
    """Retorna apenas abastecimentos com alguma anomalia."""
    inicio, fim = dataInicio or "", dataFim or ""
    if not inicio or not fim:
        inicio, fim = _default_datas()
    resp = await _montar_resposta_mapa(inicio, fim, unidades, "1")
    alertas = [p for p in resp.pontos if p.status_mapa != "ok"]
    return {"total": len(alertas), "alertas": alertas}


@router.get("/veiculo/{placa}", response_model=HistoricoVeiculo)
async def get_historico_veiculo(
    placa: str,
    dataInicio: str | None = Query(default=None),
    dataFim:    str | None = Query(default=None),
):
    """Histórico completo de abastecimentos de um veículo."""
    inicio, fim = dataInicio or "", dataFim or ""
    if not inicio or not fim:
        inicio, fim = _default_datas()

    todos        = await _buscar(inicio, fim)
    placa_upper  = placa.upper()
    abastecimentos = [a for a in todos if a.placa.upper() == placa_upper]

    if not abastecimentos:
        raise HTTPException(status_code=404, detail=f"Nenhum abastecimento encontrado para {placa}")

    cnpjs_unicos = list({a.CNPJ for a in abastecimentos if a.CNPJ})
    resultados   = await asyncio.gather(*[validar_cnpj(c) for c in cnpjs_unicos], return_exceptions=True)
    mapa_cnpj    = {c: r for c, r in zip(cnpjs_unicos, resultados) if isinstance(r, SituacaoCNPJ)}

    media_veiculo = _media_por_veiculo(todos)
    mediana_preco = _mediana_preco_combustivel(todos)

    eventos = []
    for ab in sorted(abastecimentos, key=lambda x: (x.data, x.hora)):
        cnpj_info = mapa_cnpj.get(ab.CNPJ)
        status_mapa, alerta_motivo = classificar(ab, cnpj_info, media_veiculo, mediana_preco)
        try:
            litros      = float(ab.quantidadeLitros)
            valor       = float(ab.valor)
            valor_litro = float(ab.valorLitro)
            km_atual    = int(ab.kmAtual or 0)
            km_anterior = int(ab.kmAnterior or 0)
        except ValueError:
            continue
        eventos.append(EventoVeiculo(
            id            = ab.codAbastecimento,
            data          = ab.data,
            hora          = ab.hora,
            posto         = ab.posto,
            combustivel   = ab.combustivel,
            litros        = litros,
            valor         = valor,
            valor_litro   = valor_litro,
            km_atual      = km_atual,
            km_rodados    = max(0, km_atual - km_anterior),
            status_mapa   = status_mapa,
            alerta_motivo = alerta_motivo,
        ))

    ref          = abastecimentos[0]
    total_litros = sum(e.litros for e in eventos)
    total_gasto  = sum(e.valor  for e in eventos)
    kms          = [e.km_rodados for e in eventos if e.km_rodados > 0]

    return HistoricoVeiculo(
        placa                = ref.placa,
        modelo               = ref.modelo or "",
        marca                = ref.marca  or "",
        secretaria           = ref.centroDeCustoVeiculo or ref.centroDeCustoCondutor or "",
        total_abastecimentos = len(eventos),
        total_litros         = total_litros,
        total_gasto          = total_gasto,
        km_total_rodado      = sum(kms),
        media_litros         = round(total_litros / len(eventos), 1) if eventos else 0,
        media_valor          = round(total_gasto  / len(eventos), 2) if eventos else 0,
        alertas              = sum(1 for e in eventos if e.status_mapa != "ok"),
        eventos              = eventos,
    )


def _calcular_metricas(pontos: list, label: str, inicio: str, fim: str) -> MetricasPeriodo:
    total_litros = sum(p.litros for p in pontos)
    total_gasto  = sum(p.valor  for p in pontos)
    precos       = [p.valor_litro for p in pontos if p.valor_litro > 0]
    alertas      = sum(1 for p in pontos if p.status_mapa != "ok")
    irreg        = len({p.cnpj for p in pontos if p.cnpj_ok is False})
    veiculos     = len({p.placa for p in pontos})
    comb_count: dict[str, int] = {}
    for p in pontos:
        comb_count[p.combustivel] = comb_count.get(p.combustivel, 0) + 1
    top_comb = max(comb_count, key=comb_count.get) if comb_count else "—"

    return MetricasPeriodo(
        periodo                = label,
        data_inicio            = inicio,
        data_fim               = fim,
        total_abastecimentos   = len(pontos),
        total_litros           = round(total_litros, 1),
        total_gasto            = round(total_gasto, 2),
        media_valor_litro      = round(statistics.mean(precos), 3) if precos else 0,
        alertas                = alertas,
        cnpj_irregulares       = irreg,
        veiculos_distintos     = veiculos,
        combustivel_mais_usado = top_comb,
    )


def _variacao(a: float, b: float) -> float:
    if a == 0:
        return 0.0
    return round((b - a) / a * 100, 1)


@router.get("/comparativo", response_model=RespostaComparativo)
async def get_comparativo(
    inicioA:  str          = Query(..., description="MM-dd-yyyy"),
    fimA:     str          = Query(..., description="MM-dd-yyyy"),
    inicioB:  str          = Query(..., description="MM-dd-yyyy"),
    fimB:     str          = Query(..., description="MM-dd-yyyy"),
    unidades: str | None   = Query(default=None, description="Filtro por unidade/secretaria, ex: 2,97"),
    placas:   str | None   = Query(default=None, description="Filtro por placa(s), ex: ABC-1234,DEF-5678"),
):
    """
    Compara métricas entre dois períodos.
    Aceita filtros opcionais por unidade (centro de custo) e placa(s).
    """
    abs_a, abs_b = await asyncio.gather(
        _buscar(inicioA, fimA, unidades),
        _buscar(inicioB, fimB, unidades),
    )

    # Filtro por placa(s) aplicado após a busca
    if placas:
        filtro = {p.strip().upper() for p in placas.split(",")}
        abs_a = [a for a in abs_a if a.placa.upper() in filtro]
        abs_b = [a for a in abs_b if a.placa.upper() in filtro]

    async def pontos_de(abastecimentos):
        cnpjs      = list({a.CNPJ for a in abastecimentos if a.CNPJ})
        resultados = await asyncio.gather(*[validar_cnpj(c) for c in cnpjs], return_exceptions=True)
        mapa       = {c: r for c, r in zip(cnpjs, resultados) if isinstance(r, SituacaoCNPJ)}
        media      = _media_por_veiculo(abastecimentos)
        mediana    = _mediana_preco_combustivel(abastecimentos)
        return [p for ab in abastecimentos if (p := montar_ponto(ab, mapa.get(ab.CNPJ), media, mediana))]

    pontos_a, pontos_b = await asyncio.gather(pontos_de(abs_a), pontos_de(abs_b))

    ma = _calcular_metricas(pontos_a, "Período A", inicioA, fimA)
    mb = _calcular_metricas(pontos_b, "Período B", inicioB, fimB)

    return RespostaComparativo(
        periodo_a            = ma,
        periodo_b            = mb,
        variacao_gasto_pct   = _variacao(ma.total_gasto,  mb.total_gasto),
        variacao_litros_pct  = _variacao(ma.total_litros, mb.total_litros),
        variacao_alertas_pct = _variacao(ma.alertas,      mb.alertas),
        filtro_placas        = placas,
        filtro_unidades      = unidades,
    )


@router.get("/modelos", response_model=RespostaModelos)
async def get_modelos(
    dataInicio: str | None = Query(default=None),
    dataFim:    str | None = Query(default=None),
    marca:      str | None = Query(default=None, description="Filtra por marca, ex: Toyota"),
):
    """Lista todas as combinações marca/modelo disponíveis no período."""
    inicio, fim = dataInicio or "", dataFim or ""
    if not inicio or not fim:
        inicio, fim = _default_datas()

    todos = await _buscar(inicio, fim)

    agrupado: dict[tuple[str, str], set[str]] = {}
    for a in todos:
        m = (a.marca or "").strip()
        mo = (a.modelo or "").strip()
        if not m and not mo:
            continue
        if marca and m.lower() != marca.lower():
            continue
        agrupado.setdefault((m, mo), set()).add(a.placa)

    modelos = sorted(
        [ModeloDisponivel(marca=k[0], modelo=k[1], total_veiculos=len(v))
         for k, v in agrupado.items()],
        key=lambda x: (x.marca, x.modelo),
    )
    return RespostaModelos(total=len(modelos), modelos=modelos)


@router.get("/tipo-veiculo", response_model=HistoricoTipoVeiculo)
async def get_historico_tipo_veiculo(
    modelo:     str | None = Query(default=None, description="ex: Corolla"),
    marca:      str | None = Query(default=None, description="ex: Toyota"),
    dataInicio: str | None = Query(default=None),
    dataFim:    str | None = Query(default=None),
):
    """
    Histórico agregado de abastecimentos para todos os veículos de um tipo.
    Filtra por marca, modelo ou ambos (case-insensitive).
    Ao menos um dos parâmetros marca ou modelo deve ser informado.
    """
    if not marca and not modelo:
        raise HTTPException(status_code=400, detail="Informe ao menos 'marca' ou 'modelo'")

    inicio, fim = dataInicio or "", dataFim or ""
    if not inicio or not fim:
        inicio, fim = _default_datas()

    todos = await _buscar(inicio, fim)

    # Filtra pelo tipo solicitado (case-insensitive)
    def _match(a) -> bool:
        if marca and (a.marca or "").strip().lower() != marca.lower():
            return False
        if modelo and (a.modelo or "").strip().lower() != modelo.lower():
            return False
        return True

    filtrados = [a for a in todos if _match(a)]
    if not filtrados:
        marca_str  = marca  or ""
        modelo_str = modelo or ""
        raise HTTPException(
            status_code=404,
            detail=f"Nenhum abastecimento encontrado para {marca_str} {modelo_str}".strip(),
        )

    # Calcula estatísticas de alertas por placa
    cnpjs_unicos = list({a.CNPJ for a in filtrados if a.CNPJ})
    resultados   = await asyncio.gather(*[validar_cnpj(c) for c in cnpjs_unicos], return_exceptions=True)
    mapa_cnpj    = {c: r for c, r in zip(cnpjs_unicos, resultados) if isinstance(r, SituacaoCNPJ)}
    media_veiculo = _media_por_veiculo(todos)
    mediana_preco = _mediana_preco_combustivel(todos)

    # Agrupa por placa
    por_placa: dict[str, list] = {}
    for a in filtrados:
        por_placa.setdefault(a.placa, []).append(a)

    resumos: list[ResumoVeiculoTipo] = []
    for placa, abs_placa in sorted(por_placa.items()):
        litros_total = 0.0
        valor_total  = 0.0
        kms          = []
        alertas_cnt  = 0

        for a in abs_placa:
            try:
                litros_total += float(a.quantidadeLitros)
                valor_total  += float(a.valor)
                km_a = int(a.kmAtual or 0)
                km_p = int(a.kmAnterior or 0)
                if km_a > 0 and km_p > 0:
                    kms.append(max(0, km_a - km_p))
            except ValueError:
                pass
            _, motivo = classificar(a, mapa_cnpj.get(a.CNPJ), media_veiculo, mediana_preco)
            if motivo:
                alertas_cnt += 1

        ref = abs_placa[0]
        resumos.append(ResumoVeiculoTipo(
            placa                = placa,
            secretaria           = ref.centroDeCustoVeiculo or ref.centroDeCustoCondutor or "",
            total_abastecimentos = len(abs_placa),
            total_litros         = round(litros_total, 1),
            total_gasto          = round(valor_total, 2),
            km_total_rodado      = sum(kms),
            alertas              = alertas_cnt,
        ))

    total_ab     = sum(r.total_abastecimentos for r in resumos)
    total_litros = sum(r.total_litros for r in resumos)
    total_gasto  = sum(r.total_gasto  for r in resumos)
    total_km     = sum(r.km_total_rodado for r in resumos)
    total_alertas = sum(r.alertas for r in resumos)

    ref0 = filtrados[0]
    return HistoricoTipoVeiculo(
        marca                        = ref0.marca  or marca  or "",
        modelo                       = ref0.modelo or modelo or "",
        total_veiculos               = len(resumos),
        total_abastecimentos         = total_ab,
        total_litros                 = round(total_litros, 1),
        total_gasto                  = round(total_gasto, 2),
        km_total_rodado              = total_km,
        media_litros_por_abastecimento = round(total_litros / total_ab, 1) if total_ab else 0,
        media_valor_por_abastecimento  = round(total_gasto  / total_ab, 2) if total_ab else 0,
        alertas                      = total_alertas,
        veiculos                     = resumos,
    )


@router.get("/placas")
async def get_placas(
    dataInicio: str | None = Query(default=None),
    dataFim:    str | None = Query(default=None),
):
    """Lista todas as placas com abastecimentos no período."""
    inicio, fim = dataInicio or "", dataFim or ""
    if not inicio or not fim:
        inicio, fim = _default_datas()
    todos  = await _buscar(inicio, fim)
    placas = sorted({a.placa for a in todos})
    return {"placas": placas}


@router.get("/cnpj/{cnpj}", response_model=SituacaoCNPJ)
async def get_cnpj(cnpj: str):
    """Consulta situação cadastral de um CNPJ individual."""
    try:
        return await validar_cnpj(cnpj)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def forcar_sync(
    dataInicio: str | None = Query(default=None, description="MM-dd-yyyy"),
    dataFim:    str | None = Query(default=None, description="MM-dd-yyyy"),
):
    """
    Força sincronização manual com a Sisatec.
    Disponível apenas em modo real (USE_MOCK=false).
    """
    if settings.use_mock:
        raise HTTPException(status_code=400, detail="Sync não disponível em modo mock")

    from app.services.ingestion_service import sync_periodo, sync_hoje
    if dataInicio and dataFim:
        novos = await sync_periodo(dataInicio, dataFim)
    else:
        novos = await sync_hoje()
    return {"status": "ok", "novos_registros": novos}


@router.get("/health")
async def health():
    info: dict = {"status": "ok", "mode": "mock" if settings.use_mock else "real"}
    if not settings.use_mock:
        from app.db.database import get_engine
        try:
            engine = await get_engine()
            async with engine.connect() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            info["db"] = "ok"
        except Exception as e:
            info["db"] = f"erro: {e}"
    return info
