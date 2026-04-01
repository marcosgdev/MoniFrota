"""
Modelo ORM da tabela de abastecimentos.

Campos numéricos (valor, litros, km) são armazenados como TEXT para manter
compatibilidade perfeita com AbastecimentoRaw e evitar erros de conversão
em registros com dados faltantes da Sisatec.
O campo data_date (DATE) é o único campo tipado para permitir queries eficientes
por período.
"""
from datetime import date, datetime
from sqlalchemy import String, Date, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class Abastecimento(Base):
    __tablename__ = "abastecimentos"

    cod_abastecimento:      Mapped[str]      = mapped_column(String, primary_key=True)
    placa:                  Mapped[str]      = mapped_column(String, index=True)
    prefixo:                Mapped[str]      = mapped_column(String, default="")
    modelo:                 Mapped[str]      = mapped_column(String, default="")
    marca:                  Mapped[str]      = mapped_column(String, default="")
    condutor:               Mapped[str]      = mapped_column(String, default="")
    matricula_condutor:     Mapped[str]      = mapped_column(String, default="")
    centro_custo_condutor:  Mapped[str]      = mapped_column(String, default="", index=True)
    posto:                  Mapped[str]      = mapped_column(String, default="")
    posto_razao:            Mapped[str]      = mapped_column(String, default="")
    endereco:               Mapped[str]      = mapped_column(String, default="")
    estado:                 Mapped[str]      = mapped_column(String, default="")
    cnpj:                   Mapped[str]      = mapped_column(String, default="", index=True)
    latitude:               Mapped[str]      = mapped_column(String, default="0")
    longitude:              Mapped[str]      = mapped_column(String, default="0")
    data_str:               Mapped[str]      = mapped_column(String)           # "dd/MM/yyyy" original
    data_date:              Mapped[date]     = mapped_column(Date, index=True)  # para range queries
    hora:                   Mapped[str]      = mapped_column(String, default="")
    combustivel:            Mapped[str]      = mapped_column(String, default="")
    valor:                  Mapped[str]      = mapped_column(String, default="0")
    valor_litro:            Mapped[str]      = mapped_column(String, default="0")
    quantidade_litros:      Mapped[str]      = mapped_column(String, default="0")
    km_atual:               Mapped[str]      = mapped_column(String, default="0")
    km_anterior:            Mapped[str]      = mapped_column(String, default="0")
    status:                 Mapped[str]      = mapped_column(String, default="")
    tipo_servico:           Mapped[str]      = mapped_column(String, default="")
    nome_servico:           Mapped[str]      = mapped_column(String, default="")
    tipo_frota:             Mapped[str]      = mapped_column(String, default="")
    centro_custo_veiculo:   Mapped[str]      = mapped_column(String, default="", index=True)
    ingerido_em:            Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
