"""
Motor de alertas — detecta anomalias nos abastecimentos.

Regras implementadas:
  1. CNPJ inapto ou baixado na Receita Federal
  2. Abastecimento fora do horário comercial (antes 06h ou após 22h)
  3. Quilometragem regressiva (km atual < km anterior)
  4. Volume acima de 120% da média histórica do veículo
  5. Valor por litro acima de 20% da mediana do combustível no período
  6. CNAE do posto não é de combustíveis (possível posto fantasma)
"""
import logging
import statistics
from app.models.schemas import AbastecimentoRaw, SituacaoCNPJ, PontoMapa

logger = logging.getLogger(__name__)

HORA_INICIO_COMERCIAL = 6
HORA_FIM_COMERCIAL    = 22
FATOR_VOLUME_ALERTA   = 1.20   # 20% acima da média do veículo
FATOR_PRECO_ALERTA    = 1.20   # 20% acima da mediana do combustível
CNAE_COMBUSTIVEL      = "comércio varejista de combustíveis"


def _hora_int(hora_str: str) -> int:
    """Extrai hora inteira de 'HH:MM:SS' ou 'HH:MM'."""
    try:
        return int(hora_str.split(":")[0])
    except Exception:
        return 12


def _media_por_veiculo(abastecimentos: list[AbastecimentoRaw]) -> dict[str, float]:
    """Calcula média de litros por placa."""
    grupos: dict[str, list[float]] = {}
    for a in abastecimentos:
        try:
            litros = float(a.quantidadeLitros)
            grupos.setdefault(a.placa, []).append(litros)
        except ValueError:
            pass
    return {placa: statistics.mean(vals) for placa, vals in grupos.items()}


def _mediana_preco_combustivel(abastecimentos: list[AbastecimentoRaw]) -> dict[str, float]:
    """Calcula mediana de preço por litro por tipo de combustível."""
    grupos: dict[str, list[float]] = {}
    for a in abastecimentos:
        try:
            preco = float(a.valorLitro)
            grupos.setdefault(a.combustivel, []).append(preco)
        except ValueError:
            pass
    return {comb: statistics.median(vals) for comb, vals in grupos.items() if vals}


def classificar(
    ab: AbastecimentoRaw,
    cnpj_info: SituacaoCNPJ | None,
    media_veiculo: dict[str, float],
    mediana_preco: dict[str, float],
) -> tuple[str, str | None]:
    """
    Retorna (status_mapa, alerta_motivo).
    status_mapa: "ok" | "warn" | "danger"
    """
    motivos: list[str] = []
    status = "ok"

    # --- Regra 1: CNPJ irregular ---
    if cnpj_info and not cnpj_info.ok:
        motivos.append(f"CNPJ {cnpj_info.situacao.lower()} na Receita Federal")
        status = "danger"

    # --- Regra 2: Horário fora do comercial ---
    hora = _hora_int(ab.hora)
    if hora < HORA_INICIO_COMERCIAL or hora >= HORA_FIM_COMERCIAL:
        motivos.append(f"Abastecimento fora do horário comercial ({ab.hora})")
        if status != "danger":
            status = "warn"

    # --- Regra 3: Quilometragem regressiva ---
    try:
        km_atual     = int(ab.kmAtual or 0)
        km_anterior  = int(ab.kmAnterior or 0)
        if km_atual > 0 and km_anterior > 0 and km_atual < km_anterior:
            motivos.append(f"Km regressivo: atual {km_atual} < anterior {km_anterior}")
            if status != "danger":
                status = "warn"
    except ValueError:
        pass

    # --- Regra 4: Volume acima da média do veículo ---
    try:
        litros = float(ab.quantidadeLitros)
        media  = media_veiculo.get(ab.placa)
        if media and litros > media * FATOR_VOLUME_ALERTA:
            pct = round((litros / media - 1) * 100)
            motivos.append(f"Volume {pct}% acima da média do veículo ({media:.0f}L)")
            if status == "ok":
                status = "warn"
    except ValueError:
        pass

    # --- Regra 5: Preço acima da mediana ---
    try:
        preco   = float(ab.valorLitro)
        mediana = mediana_preco.get(ab.combustivel)
        if mediana and preco > mediana * FATOR_PRECO_ALERTA:
            pct = round((preco / mediana - 1) * 100)
            motivos.append(f"Preço {pct}% acima da mediana ({ab.combustivel}: R${mediana:.2f}/L)")
            if status == "ok":
                status = "warn"
    except ValueError:
        pass

    # --- Regra 6: CNAE não é de combustíveis ---
    if cnpj_info and cnpj_info.atividade:
        if CNAE_COMBUSTIVEL not in cnpj_info.atividade.lower():
            motivos.append(f"CNAE do posto não é de combustíveis: {cnpj_info.atividade}")
            status = "danger"

    motivo_str = " | ".join(motivos) if motivos else None
    return status, motivo_str


def montar_ponto(
    ab: AbastecimentoRaw,
    cnpj_info: SituacaoCNPJ | None,
    media_veiculo: dict[str, float],
    mediana_preco: dict[str, float],
) -> PontoMapa | None:
    """Converte AbastecimentoRaw → PontoMapa, retorna None se sem GPS."""
    try:
        lat = float(ab.latitude or "0")
        lon = float(ab.longitude or "0")
    except ValueError:
        return None

    if lat == 0.0 and lon == 0.0:
        return None

    try:
        litros     = float(ab.quantidadeLitros)
        valor      = float(ab.valor)
        valor_litro = float(ab.valorLitro)
        km_atual   = int(ab.kmAtual or 0)
        km_anterior = int(ab.kmAnterior or 0)
    except ValueError:
        return None

    tipo_posto = "interno" if ab.tipo_servico == "0" else "externo"
    status_mapa, alerta_motivo = classificar(ab, cnpj_info, media_veiculo, mediana_preco)

    return PontoMapa(
        id             = ab.codAbastecimento,
        lat            = lat,
        lon            = lon,
        placa          = ab.placa,
        condutor       = ab.condutor,
        secretaria     = ab.centroDeCustoCondutor or ab.centroDeCustoVeiculo or "",
        posto          = ab.posto,
        cnpj           = ab.CNPJ,
        data           = ab.data,
        hora           = ab.hora,
        combustivel    = ab.combustivel,
        litros         = litros,
        valor          = valor,
        valor_litro    = valor_litro,
        km_atual       = km_atual,
        km_anterior    = km_anterior,
        km_rodados     = max(0, km_atual - km_anterior),
        status_mapa    = status_mapa,
        tipo_posto     = tipo_posto,
        cnpj_ok        = cnpj_info.ok        if cnpj_info else None,
        cnpj_situacao  = cnpj_info.situacao  if cnpj_info else None,
        cnpj_atividade = cnpj_info.atividade if cnpj_info else None,
        cnpj_municipio = cnpj_info.municipio if cnpj_info else None,
        alerta_motivo  = alerta_motivo,
    )
