"""Uso em linha de comando (para a TI e para testes): python -m atestados PLANILHA [opções]

Mostra só o resumo (contagens, motivos e tempo). Nunca mostra nomes, chapas nem conteúdo.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import NOME_APP, __version__, datas
from .exportacao import ErroExportacao, PastaJaExiste, analisar, exportar
from .leitura import ErroLeitura


def _progresso(atual, total, texto):
    if total:
        print(f"\r  {texto}   ", end="", file=sys.stderr, flush=True)


def main(argv=None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if fluxo is not None and hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(errors="replace")
    p = argparse.ArgumentParser(prog="python -m atestados",
                                description=f"{NOME_APP} {__version__}: planilha de atestados em base64 → arquivos.")
    p.add_argument("planilha", help="arquivo .xlsx ou .csv do dia")
    p.add_argument("--destino", help="onde criar a pasta Atestados_DD_MM_AAAA (padrão: a pasta da planilha)")
    p.add_argument("--data", help="data da planilha, DD/MM/AAAA (padrão: detectada automaticamente)")
    p.add_argument("--substituir", action="store_true", help="substitui uma exportação anterior da mesma data")
    p.add_argument("--so-analisar", action="store_true", help="só analisa, sem gravar nada")
    args = p.parse_args(argv)

    try:
        analise = analisar(args.planilha)
        print(f"Planilha: {analise.total_linhas} linhas de dados, {analise.linhas_com_imagem} com imagem, "
              f"{analise.incompletas} incompletas na origem ({analise.tempo:.1f} s)")
        print(f"Data: {datas.formatar(analise.data)} ({analise.origem_data})")
        for aviso in analise.avisos:
            print(f"Aviso: {aviso}")
        if args.so_analisar:
            return 0
        data = datas.ler_data_digitada(args.data) if args.data else analise.data
        destino = Path(args.destino) if args.destino else Path(args.planilha).resolve().parent
        r = exportar(args.planilha, destino, data, analise=analise, progresso=_progresso, substituir=args.substituir)
    except PastaJaExiste as e:
        print(f"\n{e} Use --substituir para trocar a exportação anterior.")
        return 2
    except (ErroLeitura, ErroExportacao, ValueError) as e:
        print(f"\nErro: {e}")
        return 1
    print(file=sys.stderr)
    print(f"{'CANCELADO' if r.cancelado else 'Concluído'} em {r.tempo:.1f} s → {r.pasta}")
    print(f"  arquivos OK:        {r.arquivos_ok}")
    print(f"  arquivos VERIFICAR: {r.arquivos_verificar}")
    print(f"  linhas sem arquivo: {r.linhas_sem_arquivo}")
    print(f"  GPS removido de:    {r.gps_removido}")
    for categoria, n in r.problemas.most_common():
        print(f"  motivo — {categoria}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
