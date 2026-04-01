"""
Backfill histórico: busca abastecimentos de um período na Sisatec e persiste
no banco local. Execute uma única vez após o deploy em produção.

Uso:
    # Últimos 3 anos (padrão)
    python -m scripts.backfill

    # Últimos N anos
    python -m scripts.backfill --anos 3

    # Período específico
    python -m scripts.backfill --inicio 01-01-2022 --fim 12-31-2024
"""
import asyncio
import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# Garante que o pacote raiz está no path quando executado como script
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _ultimo_dia_do_mes(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1) - timedelta(days=1)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


async def run(data_inicio: date, data_fim: date):
    from app.db.database import init_db
    from app.services.ingestion_service import sync_periodo

    logger.info(f"Backfill: {data_inicio} → {data_fim}")
    await init_db()

    total_recebidos = 0
    total_inseridos = 0
    cursor = data_inicio

    while cursor <= data_fim:
        fim_janela = min(_ultimo_dia_do_mes(cursor), data_fim)

        ini_str = cursor.strftime("%m-%d-%Y")
        fim_str = fim_janela.strftime("%m-%d-%Y")

        logger.info(f"  Janela: {ini_str} → {fim_str}")
        inseridos = await sync_periodo(ini_str, fim_str)
        total_inseridos += inseridos

        cursor = fim_janela + timedelta(days=1)

    logger.info(f"Backfill concluído. Novos registros inseridos: {total_inseridos}")


def _parse_data(s: str) -> date:
    try:
        return datetime.strptime(s, "%m-%d-%Y").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"Data inválida '{s}' — use MM-dd-yyyy")


def main():
    from datetime import datetime  # noqa

    parser = argparse.ArgumentParser(description="Backfill histórico de abastecimentos")
    parser.add_argument("--anos",   type=int, default=3,   help="Quantos anos retroativos (padrão: 3)")
    parser.add_argument("--inicio", type=str, default=None, help="Data início MM-dd-yyyy")
    parser.add_argument("--fim",    type=str, default=None, help="Data fim   MM-dd-yyyy")
    args = parser.parse_args()

    hoje = date.today()

    if args.inicio and args.fim:
        try:
            data_inicio = datetime.strptime(args.inicio, "%m-%d-%Y").date()
            data_fim    = datetime.strptime(args.fim,    "%m-%d-%Y").date()
        except ValueError as e:
            logger.error(f"Formato de data inválido: {e}. Use MM-dd-yyyy.")
            sys.exit(1)
    else:
        data_inicio = date(hoje.year - args.anos, hoje.month, hoje.day)
        data_fim    = hoje

    if data_inicio > data_fim:
        logger.error("Data início deve ser anterior à data fim.")
        sys.exit(1)

    asyncio.run(run(data_inicio, data_fim))


if __name__ == "__main__":
    main()
