"""
Testes da lógica de negócio — rodam sem credenciais, sem Redis, sem rede.
Execute com:  pytest tests/ -v
"""
import pytest
from app.models.schemas import AbastecimentoRaw, SituacaoCNPJ
from app.services.alertas_service import (
    classificar, montar_ponto,
    _media_por_veiculo, _mediana_preco_combustivel,
)

# --- Fixtures ---

def ab_base(**kwargs) -> AbastecimentoRaw:
    defaults = {
        "codAbastecimento": "T001",
        "placa": "TST-0001",
        "condutor": "Teste Silva",
        "cpfcondutor": None,
        "cnhcondutor": None,
        "posto": "Posto Teste",
        "CNPJ": "00.000.000/0001-00",
        "latitude": "-3.72",
        "longitude": "-38.54",
        "data": "31/03/2025",
        "hora": "10:00:00",
        "combustivel": "Diesel",
        "valor": "350.00",
        "valorLitro": "7.00",
        "quantidadeLitros": "50",
        "kmAtual": "10000",
        "kmAnterior": "9500",
        "status": "1",
        "tipo_servico": "1",
    }
    defaults.update(kwargs)
    return AbastecimentoRaw(**defaults)

def cnpj_ok() -> SituacaoCNPJ:
    return SituacaoCNPJ(
        cnpj="00.000.000/0001-00", ok=True, situacao="Ativa",
        atividade="comércio varejista de combustíveis",
        municipio="Fortaleza", uf="CE",
    )

def cnpj_inapto() -> SituacaoCNPJ:
    return SituacaoCNPJ(
        cnpj="00.000.000/0001-00", ok=False, situacao="Inapta",
        atividade="comércio varejista de combustíveis",
        municipio="Fortaleza", uf="CE",
    )

# --- Testes de alertas ---

class TestClassificar:

    def test_abastecimento_normal(self):
        ab = ab_base()
        status, motivo = classificar(ab, cnpj_ok(), {}, {})
        assert status == "ok"
        assert motivo is None

    def test_cnpj_inapto_gera_danger(self):
        ab = ab_base()
        status, motivo = classificar(ab, cnpj_inapto(), {}, {})
        assert status == "danger"
        assert "inapta" in motivo.lower()

    def test_horario_noturno_gera_warn(self):
        ab = ab_base(hora="23:15:00")
        status, motivo = classificar(ab, cnpj_ok(), {}, {})
        assert status == "warn"
        assert "horário" in motivo.lower()

    def test_horario_madrugada_gera_warn(self):
        ab = ab_base(hora="03:00:00")
        status, motivo = classificar(ab, cnpj_ok(), {}, {})
        assert status == "warn"

    def test_km_regressivo_gera_warn(self):
        ab = ab_base(kmAtual="9000", kmAnterior="9500")
        status, motivo = classificar(ab, cnpj_ok(), {}, {})
        assert status == "warn"
        assert "regressivo" in motivo.lower()

    def test_volume_alto_gera_warn(self):
        ab = ab_base(quantidadeLitros="80")
        media = {"TST-0001": 50.0}  # 80 > 50 * 1.2 = 60
        status, motivo = classificar(ab, cnpj_ok(), media, {})
        assert status == "warn"
        assert "média" in motivo.lower()

    def test_preco_alto_gera_warn(self):
        ab = ab_base(valorLitro="9.50")
        mediana = {"Diesel": 7.00}  # 9.50 > 7.00 * 1.2 = 8.40
        status, motivo = classificar(ab, cnpj_ok(), {}, mediana)
        assert status == "warn"
        assert "mediana" in motivo.lower()

    def test_cnpj_danger_prevalece_sobre_warn_horario(self):
        ab = ab_base(hora="23:00:00")
        status, motivo = classificar(ab, cnpj_inapto(), {}, {})
        assert status == "danger"

    def test_cnae_errado_gera_danger(self):
        cnpj_errado = SituacaoCNPJ(
            cnpj="00.000.000/0001-00", ok=True, situacao="Ativa",
            atividade="restaurante e lanchonete",
            municipio="Fortaleza", uf="CE",
        )
        ab = ab_base()
        status, motivo = classificar(ab, cnpj_errado, {}, {})
        assert status == "danger"
        assert "cnae" in motivo.lower()

    def test_multiplos_motivos_concatenados(self):
        ab = ab_base(hora="23:00:00", kmAtual="9000", kmAnterior="9500")
        status, motivo = classificar(ab, cnpj_ok(), {}, {})
        assert "|" in motivo
        assert status == "warn"


# --- Testes de montagem do ponto ---

class TestMontarPonto:

    def test_ponto_normal(self):
        ab = ab_base()
        ponto = montar_ponto(ab, cnpj_ok(), {}, {})
        assert ponto is not None
        assert ponto.lat == -3.72
        assert ponto.km_rodados == 500
        assert ponto.tipo_posto == "externo"

    def test_sem_gps_retorna_none(self):
        ab = ab_base(latitude="0", longitude="0")
        ponto = montar_ponto(ab, cnpj_ok(), {}, {})
        assert ponto is None

    def test_gps_ausente_retorna_none(self):
        ab = ab_base(latitude=None, longitude=None)
        ponto = montar_ponto(ab, cnpj_ok(), {}, {})
        assert ponto is None

    def test_posto_interno_detectado(self):
        ab = ab_base(tipo_servico="0")
        ponto = montar_ponto(ab, cnpj_ok(), {}, {})
        assert ponto.tipo_posto == "interno"

    def test_cpf_nao_exposto(self):
        ab = ab_base(cpfcondutor="123.456.789-00")
        ponto = montar_ponto(ab, cnpj_ok(), {}, {})
        assert not hasattr(ponto, "cpfcondutor")


# --- Testes de estatísticas ---

class TestEstatisticas:

    def test_media_por_veiculo(self):
        abs_ = [ab_base(quantidadeLitros="60"), ab_base(quantidadeLitros="40")]
        media = _media_por_veiculo(abs_)
        assert media["TST-0001"] == 50.0

    def test_mediana_preco(self):
        abs_ = [
            ab_base(valorLitro="7.00"),
            ab_base(valorLitro="8.00"),
            ab_base(valorLitro="9.00"),
        ]
        mediana = _mediana_preco_combustivel(abs_)
        assert mediana["Diesel"] == 8.00
