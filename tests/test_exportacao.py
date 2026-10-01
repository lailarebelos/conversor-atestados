import csv
import threading
from datetime import date

import pytest

import sintetico as s
from atestados import exportacao, formatos, metadados
from atestados.exportacao import ErroExportacao, PastaJaExiste, analisar, exportar
from atestados.leitura import ErroLeitura

DIA = date(2026, 9, 28)


def relatorio(pasta) -> dict[str, dict]:
    with open(pasta / exportacao.NOME_RELATORIO, encoding="utf-8-sig", newline="") as f:
        return {ln["Linha da planilha"]: ln for ln in csv.DictReader(f, delimiter=";")}


def abre_normalmente(caminho) -> bool:
    dados = caminho.read_bytes()
    fmt = formatos.detectar_formato(dados)
    return fmt is not None and formatos.validar(dados, fmt) is None


@pytest.fixture(scope="module")
def imagens():
    grande = s.com_tamanho_exato(s.jpeg(1600, 1200, gps=False), 3_590_000)
    assert len(s.fatiar(s.b64(grande))) == 150
    pequena = s.jpeg(40, 30, gps=False)
    assert len(s.b64(pequena)) <= s.FATIA
    return {
        "pequena": pequena,
        "grande": grande,
        "maior_que_o_limite": s.com_tamanho_exato(s.jpeg(1600, 1200, semente=2), 5_000_000),
        "com_gps": s.jpeg(semente=3),
        "truncada": s.jpeg(800, 600, semente=4, gps=False),
        "com_quebras": s.jpeg(semente=5, gps=False),
        "url_safe": s.jpeg(semente=6, gps=False),
        "png": s.png(),
        "pdf": s.pdf(),
    }


@pytest.fixture
def planilha_variada(tmp_path, imagens):
    im = imagens
    linhas = [
        s.linha(100001, "000101", "FULANO UM FRAGMENTO", im["pequena"]),                      # linha 2
        s.linha(100002, "000102", "BELTRANO CENTO E CINQUENTA", im["grande"]),                # 3
        s.linha(100003, "000103", "SEM IMAGEM", None),                                        # 4
        s.linha(100004, "000104", "CORTADO PELO SERVIDOR", im["maior_que_o_limite"],          # 5
                fragmentos=s.fatiar(s.b64(im["maior_que_o_limite"]))[:150]),
        s.linha(100005, "000105", "COM PREFIXO DATA", im["com_gps"],                          # 6
                fragmentos=s.fatiar("data:image/jpeg;base64," + s.b64(im["com_gps"]))),
        s.linha(100006, "000106", "PNG NO LUGAR DE JPEG", im["png"]),                         # 7
        s.linha(100007, "000107", "ARQUIVO PDF", im["pdf"]),                                  # 8
        s.linha(100008, "000108", "BASE64 TRUNCADO", im["truncada"], declarar=False,          # 9
                fragmentos=[s.b64(im["truncada"])[:-3001]]),
        s.linha(100009, "000109", "ESPACOS E QUEBRAS", im["com_quebras"],                     # 10
                fragmentos=[f'"{f[:100]}\r\n {f[100:]}"' for f in s.fatiar(s.b64(im["com_quebras"]), 1000)]),
        s.linha(100010, "000110", "URL SAFE SEM PADDING", im["url_safe"],                     # 11
                fragmentos=s.fatiar(s.b64(im["url_safe"], urlsafe=True).rstrip("="))),
        s.linha(100011, "000111", "JOSÉ/ÇÃO: TESTE?", im["pequena"]),                         # 12
        s.linha(100011, "000111", "JOSÉ/ÇÃO: TESTE?", im["png"]),                             # 13 (mesmo nome)
    ]
    return s.planilha_padrao(tmp_path / "atestado28092026.xlsx", linhas)


def test_planilha_do_dia_com_casos_de_borda(planilha_variada, tmp_path, imagens):
    analise = analisar(planilha_variada)
    assert analise.total_linhas == 12 and analise.linhas_com_imagem == 11 and analise.incompletas == 1
    assert (analise.data, analise.origem_data) == (DIA, exportacao.ORIGEM_NOME)
    assert len(analise.colunas.base64) == 150

    r = exportar(planilha_variada, tmp_path, analise.data, analise=analise)
    assert r.pasta == tmp_path / "Atestados_28_09_2026"
    rel = relatorio(r.pasta)
    assert len(rel) == 12

    def situacao(linha):
        return rel[str(linha)]["Status"], rel[str(linha)]["Arquivo gerado"]

    assert situacao(2) == ("OK", "000101_FULANO_UM_FRAGMENTO_100001.jpg")
    assert situacao(3) == ("OK", "000102_BELTRANO_CENTO_E_CINQUENTA_100002.jpg")
    assert situacao(4) == ("SEM ARQUIVO", "")
    assert situacao(5) == ("VERIFICAR", "000104_CORTADO_PELO_SERVIDOR_100004_VERIFICAR.jpg")
    assert "faltam 28%" in rel["5"]["Motivo"]
    assert situacao(6) == ("OK", "000105_COM_PREFIXO_DATA_100005.jpg")
    assert situacao(7) == ("OK", "000106_PNG_NO_LUGAR_DE_JPEG_100006.png")
    assert situacao(8) == ("OK", "000107_ARQUIVO_PDF_100007.pdf")
    assert situacao(9) == ("VERIFICAR", "000108_BASE64_TRUNCADO_100008_VERIFICAR.jpg")
    assert situacao(10)[0] == "OK" and situacao(11)[0] == "OK"
    assert situacao(12) == ("OK", "000111_JOSÉ_ÇÃO_TESTE_100011.jpg")
    assert situacao(13) == ("OK", "000111_JOSÉ_ÇÃO_TESTE_100011.png")  # extensão diferente: sem conflito

    # bytes originais, sem recomprimir (os sem GPS ficam idênticos)
    assert (r.pasta / situacao(2)[1]).read_bytes() == imagens["pequena"]
    assert (r.pasta / situacao(3)[1]).read_bytes() == imagens["grande"]
    assert (r.pasta / situacao(8)[1]).read_bytes() == imagens["pdf"]
    assert (r.pasta / situacao(11)[1]).read_bytes() == imagens["url_safe"]
    # GPS zerado e registrado no relatório
    com_gps = (r.pasta / situacao(6)[1]).read_bytes()
    assert not metadados.tem_coordenadas_gps(com_gps) and len(com_gps) == len(imagens["com_gps"])
    assert rel["6"]["Localização (GPS) removida"] == "sim"
    assert not any(metadados.tem_coordenadas_gps(p.read_bytes()) for p in r.pasta.glob("*.jpg"))

    for ln in rel.values():
        if ln["Status"] == "OK":
            assert abre_normalmente(r.pasta / ln["Arquivo gerado"])
    assert (r.arquivos_ok, r.arquivos_verificar, r.linhas_sem_arquivo) == (9, 2, 1)
    assert r.problemas["incompleto na planilha"] == 1
    assert not list(r.pasta.glob("*.parcial"))


def test_nome_repetido_ganha_sufixo(tmp_path):
    linhas = [s.linha(1, "000001", "MESMA PESSOA", s.jpeg(semente=i, gps=False)) for i in (1, 2)]
    r = exportar(s.planilha_padrao(tmp_path / "atestado28092026.xlsx", linhas), tmp_path, DIA)
    assert sorted(p.name for p in r.pasta.glob("*.jpg")) == ["000001_MESMA_PESSOA_1.jpg", "000001_MESMA_PESSOA_1_2.jpg"]


def test_ordem_fisica_das_colunas_e_nao_alfabetica(tmp_path):
    dados = s.jpeg(400, 300, gps=False)
    fragmentos = s.fatiar(s.b64(dados), 1000)
    assert len(fragmentos) > 10  # parte_10 viria antes de parte_2 na ordem alfabética
    cab = ["CHAPA", "NOME"] + [f"parte_{i}" for i in range(1, len(fragmentos) + 1)]
    planilha = s.salvar_xlsx(tmp_path / "atestados_01_10_2026.xlsx", cab, [["000001", "ORDEM"] + fragmentos])
    r = exportar(planilha, tmp_path, date(2026, 10, 1))
    assert (r.pasta / "000001_ORDEM.jpg").read_bytes() == dados


def test_ultimo_pedaco_curto_numa_coluna_que_so_ele_usa(tmp_path):
    dados = s.jpeg(gps=False)
    texto = s.b64(dados)
    fatia = (len(texto) - 30) // 2 // 4 * 4
    fragmentos = s.fatiar(texto, fatia)
    assert len(fragmentos) == 3 and len(fragmentos[2]) < 64
    outra = s.png()
    linhas = [s.linha(1, "000001", "TRES PEDACOS", dados, fragmentos=fragmentos),
              s.linha(2, "000002", "UM PEDACO", outra)]
    cab = s.cabecalho(3) + ["OBSERVACAO"]  # coluna de texto depois do base64 é ignorada
    linhas[1] += [None, None, "texto qualquer, com espaços"]
    r = exportar(s.salvar_xlsx(tmp_path / "atestado28092026.xlsx", cab, linhas), tmp_path, DIA)
    assert (r.pasta / "000001_TRES_PEDACOS_1.jpg").read_bytes() == dados
    assert (r.pasta / "000002_UM_PEDACO_2.png").read_bytes() == outra


def test_duas_imagens_na_mesma_linha(tmp_path):
    a, b = s.jpeg(gps=False), s.png()
    linha = s.linha(7, "000007", "DUAS FOTOS", None, fragmentos=s.fatiar(s.b64(a), 4000) + s.fatiar(s.b64(b), 4000))
    r = exportar(s.planilha_padrao(tmp_path / "atestado28092026.xlsx", [linha]), tmp_path, DIA)
    assert sorted(p.name for p in r.pasta.iterdir() if p.suffix != ".csv") == [
        "000007_DUAS_FOTOS_7_1_VERIFICAR.jpg", "000007_DUAS_FOTOS_7_2_VERIFICAR.png"]
    assert r.problemas["mais de um arquivo na linha"] == 2


def test_formatos_desconhecido_e_heic(tmp_path):
    heic = b"\0\0\0\x18ftypheic\0\0\0\0" + bytes(500)
    linhas = [s.linha(1, "000001", "HEIC", heic), s.linha(2, "000002", "LIXO", b"isto nao e imagem" * 10)]
    r = exportar(s.planilha_padrao(tmp_path / "atestado28092026.xlsx", linhas), tmp_path, DIA)
    nomes = sorted(p.name for p in r.pasta.iterdir() if p.suffix != ".csv")
    assert nomes == ["000001_HEIC_1_VERIFICAR.heic", "000002_LIXO_2_VERIFICAR.bin"]


def test_csv_com_campo_gigante_e_celula_vazia_no_meio(tmp_path):
    dados = s.com_tamanho_exato(s.jpeg(gps=False), 400_000)  # 533 mil caracteres num campo só
    outro = s.jpeg(semente=9, gps=False)
    texto = s.b64(outro)
    meio = len(texto) // 2 // 4 * 4
    linhas = [s.linha(1, "000001", "CAMPO GIGANTE", dados, fragmentos=[s.b64(dados)]),
              s.linha(2, "000002", "VAZIO NO MEIO", outro, fragmentos=[texto[:meio], "", texto[meio:]])]
    planilha = s.salvar_csv(tmp_path / "atestado28092026.csv", s.cabecalho(3), linhas)
    r = exportar(planilha, tmp_path, DIA)
    assert (r.pasta / "000001_CAMPO_GIGANTE_1.jpg").read_bytes() == dados
    assert (r.pasta / "000002_VAZIO_NO_MEIO_2.jpg").read_bytes() == outro


def test_csv_com_virgula_e_acentos_em_cp1252(tmp_path):
    dados = s.jpeg(gps=False)
    planilha = s.salvar_csv(tmp_path / "atestado28092026.csv", s.cabecalho(1),
                            [s.linha(1, "000001", "JOÃO ÇÉ", dados, fragmentos=[s.b64(dados)])],
                            delimitador=",", codificacao="cp1252")
    r = exportar(planilha, tmp_path, DIA)
    assert (r.pasta / "000001_JOÃO_ÇÉ_1.jpg").read_bytes() == dados


def test_xlsx_gerado_por_sistema_inline_fora_de_a1_e_dimensao_errada(tmp_path):
    dados = s.jpeg(gps=False)
    linhas = [s.cabecalho(4)[:6] + ["IMG_PARTE001", "IMG_PARTE002"],
              s.linha(5, "000005", "INLINE", dados, fragmentos=s.fatiar(s.b64(dados), len(s.b64(dados)) // 2 // 4 * 4 + 4))]
    planilha = s.salvar_xlsx_manual(tmp_path / "atestado28092026.xlsx", linhas, linha_inicial=3, coluna_inicial=2)
    analise = analisar(planilha)
    r = exportar(planilha, tmp_path, DIA, analise=analise)
    assert relatorio(r.pasta)["4"]["Arquivo gerado"] == "000005_INLINE_5.jpg"  # linha 4 do Excel
    assert (r.pasta / "000005_INLINE_5.jpg").read_bytes() == dados


def test_planilha_sem_cabecalho_numera_os_arquivos(tmp_path):
    a, b = s.jpeg(gps=False), s.png()
    planilha = s.salvar_xlsx(tmp_path / "atestado28092026.xlsx", s.fatiar(s.b64(a), 5000), [s.fatiar(s.b64(b), 5000)])
    analise = analisar(planilha)
    assert analise.colunas.linha_cabecalho == 0 and analise.avisos
    r = exportar(planilha, tmp_path, DIA, analise=analise)
    assert sorted(p.name for p in r.pasta.iterdir() if p.suffix != ".csv") == ["001.jpg", "002.png"]


def test_pasta_existente_so_substitui_o_que_o_programa_gerou(tmp_path):
    p1 = s.planilha_padrao(tmp_path / "atestado28092026.xlsx", [s.linha(1, "000001", "A", s.jpeg())])
    r1 = exportar(p1, tmp_path, DIA)
    (r1.pasta / "anotacao_do_rh.txt").write_text("não apagar", encoding="utf-8")
    with pytest.raises(PastaJaExiste):
        exportar(p1, tmp_path, DIA)
    p2 = s.planilha_padrao(tmp_path / "atestado28092026_v2.xlsx", [s.linha(2, "000002", "B", s.jpeg())])
    r2 = exportar(p2, tmp_path, DIA, substituir=True)
    assert sorted(p.name for p in r2.pasta.iterdir()) == [
        "000002_B_2.jpg", "anotacao_do_rh.txt", "relatorio_exportacao.csv"]


def test_cancelar_para_e_deixa_relatorio_parcial(tmp_path):
    linhas = [s.linha(i, f"{i:06d}", f"PESSOA {i}", s.jpeg(semente=i)) for i in range(1, 6)]
    planilha = s.planilha_padrao(tmp_path / "atestado28092026.xlsx", linhas)
    cancelar = threading.Event()

    def progresso(atual, total, texto):
        if atual == 2:
            cancelar.set()

    r = exportar(planilha, tmp_path, DIA, progresso=progresso, cancelar=cancelar)
    assert r.cancelado and r.linhas == 2 and len(relatorio(r.pasta)) == 2


def test_progresso_conta_as_linhas(tmp_path):
    linhas = [s.linha(i, f"{i:06d}", "X", s.png()) for i in range(1, 4)]
    vistos = []
    exportar(s.planilha_padrao(tmp_path / "atestado28092026.xlsx", linhas), tmp_path, DIA,
             progresso=lambda a, t, txt: vistos.append(txt))
    assert vistos[-3:] == ["1 de 3", "2 de 3", "3 de 3"]


def test_data_vem_da_coluna_quando_o_nome_do_arquivo_nao_tem(tmp_path):
    cab = ["CHAPA", "NOME", "DATA_ENVIO", "IMG_PARTE001"]
    linhas = [["000001", "A", "27/09/2026", s.b64(s.png())], ["000002", "B", "27/09/2026", s.b64(s.png())]]
    analise = analisar(s.salvar_xlsx(tmp_path / "atestados.xlsx", cab, linhas))
    assert analise.data == date(2026, 9, 27) and "DATA_ENVIO" in analise.origem_data


def test_data_vem_das_fotos_quando_nao_ha_nome_nem_coluna(tmp_path):
    datas_fotos = ["2026:09:10 10:00:00", "2026:09:11 10:00:00", "2026:09:11 18:00:00"]
    linhas = [s.linha(i, f"{i:06d}", "X", s.com_tamanho_exato(s.jpeg(data=d), 300_000))
              for i, d in enumerate(datas_fotos, 1)]
    analise = analisar(s.planilha_padrao(tmp_path / "atestados.xlsx", linhas))
    assert (analise.data, analise.origem_data) == (date(2026, 9, 11), exportacao.ORIGEM_FOTOS)


def test_data_de_hoje_quando_nada_mais_informa(tmp_path):
    analise = analisar(s.planilha_padrao(tmp_path / "atestados.xlsx", [s.linha(1, "000001", "X", s.png())]),
                       hoje=date(2026, 10, 1))
    assert (analise.data, analise.origem_data) == (date(2026, 10, 1), exportacao.ORIGEM_HOJE)


def test_planilha_sem_base64_da_mensagem_clara(tmp_path):
    with pytest.raises(ErroExportacao, match="base64"):
        analisar(s.salvar_xlsx(tmp_path / "x.xlsx", ["CHAPA", "NOME"], [["000001", "FULANO"]]))


def test_arquivo_que_nao_e_planilha(tmp_path):
    pagina = tmp_path / "pagina.xls"
    pagina.write_text("<html><table><tr><td>x</td></tr></table></html>", encoding="utf-8")
    with pytest.raises(ErroLeitura, match="HTML"):
        analisar(pagina)


def test_destino_inexistente(tmp_path):
    planilha = s.planilha_padrao(tmp_path / "atestado28092026.xlsx", [s.linha(1, "000001", "A", s.png())])
    with pytest.raises(ErroExportacao, match="não existe"):
        exportar(planilha, tmp_path / "nao_existe", DIA)
