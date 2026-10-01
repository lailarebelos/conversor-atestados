"""Ponto de entrada do programa (é este arquivo que vira o ConversorAtestados.exe)."""
import os


def autoteste(planilha: str, saida: str) -> None:
    """Conferência do .exe já empacotado (uso da TI, com planilha sintética): abre a janela,
    analisa e exporta para uma pasta temporária e grava um resumo em JSON. Nada mais."""
    import json
    import shutil
    import tempfile

    from atestados import interface
    from atestados.exportacao import analisar, exportar

    resumo = {}
    try:
        root = interface.criar_janela()
        resumo["arrastar_e_soltar"] = interface.App(root).dnd
        root.destroy()
        destino = tempfile.mkdtemp(prefix="autoteste_")
        analise = analisar(planilha)
        r = exportar(planilha, destino, analise.data, analise=analise)
        resumo.update(linhas=analise.total_linhas, data=str(analise.data), ok=r.arquivos_ok,
                      verificar=r.arquivos_verificar, sem_arquivo=r.linhas_sem_arquivo, gps=r.gps_removido)
        shutil.rmtree(destino, ignore_errors=True)
    except Exception as e:  # noqa: BLE001
        resumo["erro"] = type(e).__name__
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False)


if __name__ == "__main__":
    pedido = os.environ.get("CONVERSOR_ATESTADOS_AUTOTESTE")  # "planilha|resumo.json"
    if pedido and "|" in pedido:
        autoteste(*pedido.split("|", 1))
    else:
        from atestados.interface import main
        main()
