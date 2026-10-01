from datetime import date, datetime

import pytest

from atestados import datas, nomes


@pytest.mark.parametrize("nome, esperado", [
    ("atestado11092026 (1).XLSX", date(2026, 9, 11)),
    ("atestado28092026.xlsx", date(2026, 9, 28)),
    ("atestados_28_09_2026.csv", date(2026, 9, 28)),
    ("export-2026-09-28.xlsx", date(2026, 9, 28)),
    ("20260928_atestados.xlsx", date(2026, 9, 28)),
    ("atestados 28.09.26.xlsx", date(2026, 9, 28)),
    ("atestados.xlsx", None),
    ("planilha (3).xlsx", None),
    ("atestado99992026.xlsx", None),
])
def test_data_no_nome_do_arquivo(nome, esperado):
    assert datas.data_do_nome(nome) == esperado


@pytest.mark.parametrize("texto", ["28/09/2026", "28-09-2026", "28.09.2026", "28092026", " 28 / 9 / 2026 "])
def test_data_digitada_valida(texto):
    assert datas.ler_data_digitada(texto) == date(2026, 9, 28)


@pytest.mark.parametrize("texto", ["", "31/02/2026", "2026-09-28", "28/09/26", "abc"])
def test_data_digitada_invalida(texto):
    with pytest.raises(ValueError):
        datas.ler_data_digitada(texto)


def test_nome_da_pasta_sempre_com_dois_digitos():
    assert datas.nome_pasta(date(2026, 1, 5)) == "Atestados_05_01_2026"


def test_data_mais_frequente_e_desempate_pela_mais_recente():
    d1, d2 = date(2026, 9, 10), date(2026, 9, 11)
    assert datas.mais_frequente([d1, d1, d2]) == (d1, 2)
    assert datas.mais_frequente([d1, d2]) == (d2, 1)
    assert datas.mais_frequente([]) == (None, 0)


def test_data_em_celula():
    serial = (date(2026, 9, 11) - date(1899, 12, 30)).days
    assert datas.interpretar_valor("11/09/2026") == date(2026, 9, 11)
    assert datas.interpretar_valor("2026-09-11 10:00:00") == date(2026, 9, 11)
    assert datas.interpretar_valor(datetime(2026, 9, 11, 8, 0)) == date(2026, 9, 11)
    assert datas.interpretar_valor(float(serial)) == date(2026, 9, 11)
    assert datas.interpretar_valor("FULANO") is None
    assert datas.interpretar_valor(123456.0) is None


def test_parte_segura_remove_o_que_o_windows_nao_aceita_e_mantem_acentos():
    assert nomes.parte_segura('  JOSÉ  DA/SILVA: "TESTE"?* ') == "JOSÉ_DA_SILVA_TESTE"
    assert nomes.parte_segura("...") == ""


def test_nome_chapa_nome_id_e_repetidos(tmp_path):
    g = nomes.GeradorNomes(tmp_path, 97)
    base = g.base("012345", "FULANO DE TAL", "654321", 1)
    assert g.nome_arquivo(base, ".jpg") == "012345_FULANO_DE_TAL_654321.jpg"
    assert g.nome_arquivo(base, ".jpg") == "012345_FULANO_DE_TAL_654321_2.jpg"
    assert g.nome_arquivo(base, ".JPG".lower()) == "012345_FULANO_DE_TAL_654321_3.jpg"
    assert g.nome_arquivo(base, ".jpg", verificar=True) == "012345_FULANO_DE_TAL_654321_VERIFICAR.jpg"


def test_sem_identificacao_usa_o_numero_da_linha(tmp_path):
    assert nomes.GeradorNomes(tmp_path, 97).base("", "", "", 7) == "007"
    assert nomes.GeradorNomes(tmp_path, 1500).base("", "", "", 7) == "0007"


def test_nome_reservado_do_windows(tmp_path):
    assert nomes.GeradorNomes(tmp_path, 1).base("", "CON", "", 1) == "CON_"


def test_caminho_longo_encurta_so_o_nome_da_pessoa(tmp_path):
    pasta = tmp_path / ("x" * (200 - len(str(tmp_path))))
    g = nomes.GeradorNomes(pasta, 97)
    base = g.base("012345", "MARIA " * 30, "654321", 1)
    nome = g.nome_arquivo(base, ".jpg", verificar=True)
    assert base.startswith("012345_MARIA") and base.endswith("_654321")
    assert len(str(pasta / nome)) + len(nomes.SUFIXO_TEMPORARIO) <= nomes.LIMITE_CAMINHO


def test_pasta_de_destino_longa_demais(tmp_path):
    with pytest.raises(nomes.CaminhoLongoDemais):
        nomes.verificar_comprimento(tmp_path / ("x" * 240))
