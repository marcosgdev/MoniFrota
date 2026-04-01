from pydantic import BaseModel
from typing import Optional

class AbastecimentoRaw(BaseModel):
    """Espelho exato dos campos retornados pela API Sisatec."""
    codAbastecimento: str
    placa: str
    prefixo: Optional[str] = ""
    modelo: Optional[str] = ""
    marca: Optional[str]  = ""
    condutor: str
    cpfcondutor: Optional[str] = None   # removido antes de ir ao frontend
    cnhcondutor: Optional[str] = None   # removido antes de ir ao frontend
    matricula_condutor: Optional[str]  = ""
    centroDeCustoCondutor: Optional[str] = ""
    posto: str
    posto_razao: Optional[str] = ""
    endereco: Optional[str]   = ""
    estado: Optional[str]     = ""
    CNPJ: str
    latitude: Optional[str]   = "0"
    longitude: Optional[str]  = "0"
    data: str
    hora: str
    combustivel: str
    valor: str
    valorLitro: str
    quantidadeLitros: str
    kmAtual: Optional[str]    = "0"
    kmAnterior: Optional[str] = "0"
    status: str
    tipo_servico: Optional[str] = ""
    nomeServico: Optional[str]  = ""
    TipoFrota: Optional[str]    = ""
    centroDeCustoVeiculo: Optional[str] = ""


class PontoMapa(BaseModel):
    """Payload enviado ao frontend — sem dados pessoais sensíveis."""
    id: str
    lat: float
    lon: float
    placa: str
    condutor: str
    secretaria: str
    posto: str
    cnpj: str
    data: str
    hora: str
    combustivel: str
    litros: float
    valor: float
    valor_litro: float
    km_atual: int
    km_anterior: int
    km_rodados: int
    status_mapa: str          # "ok" | "warn" | "danger"
    tipo_posto: str           # "interno" | "externo"
    cnpj_ok: Optional[bool]  = None
    cnpj_situacao: Optional[str] = None
    cnpj_atividade: Optional[str] = None
    cnpj_municipio: Optional[str] = None
    alerta_motivo: Optional[str]  = None


class RespostaMapa(BaseModel):
    total: int
    alertas: int
    pontos: list[PontoMapa]


class SituacaoCNPJ(BaseModel):
    cnpj: str
    ok: bool
    situacao: str
    atividade: str
    municipio: str
    uf: str
    abertura: Optional[str] = None
    erro: Optional[str]     = None


class EventoVeiculo(BaseModel):
    id: str
    data: str
    hora: str
    posto: str
    combustivel: str
    litros: float
    valor: float
    valor_litro: float
    km_atual: int
    km_rodados: int
    status_mapa: str
    alerta_motivo: Optional[str] = None


class HistoricoVeiculo(BaseModel):
    placa: str
    modelo: str
    marca: str
    secretaria: str
    total_abastecimentos: int
    total_litros: float
    total_gasto: float
    km_total_rodado: int
    media_litros: float
    media_valor: float
    alertas: int
    eventos: list[EventoVeiculo]


class MetricasPeriodo(BaseModel):
    periodo: str
    data_inicio: str
    data_fim: str
    total_abastecimentos: int
    total_litros: float
    total_gasto: float
    media_valor_litro: float
    alertas: int
    cnpj_irregulares: int
    veiculos_distintos: int
    combustivel_mais_usado: str


class RespostaComparativo(BaseModel):
    periodo_a: MetricasPeriodo
    periodo_b: MetricasPeriodo
    variacao_gasto_pct: float
    variacao_litros_pct: float
    variacao_alertas_pct: float
    filtro_placas:   Optional[str] = None   # placas aplicadas, se houver
    filtro_unidades: Optional[str] = None   # unidades aplicadas, se houver
