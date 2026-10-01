import base64

import pytest

import sintetico as s
from atestados.reconstrucao import (comeca_com_assinatura, decodificar, limpar_fragmento, reconstruir,
                                    separar_arquivos)


@pytest.mark.parametrize("valor", [None, float("nan"), "", "   ", "\r\n"])
def test_celula_vazia_vira_texto_vazio(valor):
    assert limpar_fragmento(valor) == ""


def test_celulas_vazias_nunca_viram_none_ou_nan():
    partes = [None, "QUJD", float("nan"), "", "REVG"]
    assert "".join(limpar_fragmento(p) for p in partes) == "QUJDREVG"


def test_limpeza_remove_espacos_quebras_aspas_e_prefixo_data():
    assert limpar_fragmento(' "data:image/png;base64,iVBO\r\nRw0 KGgo" ') == "iVBORw0KGgo"
    assert limpar_fragmento("DATA:IMAGE/JPEG;BASE64,/9j/") == "/9j/"


def test_decodifica_url_safe_sem_padding():
    dados = bytes(range(256)) * 3 + b"x"
    texto = base64.urlsafe_b64encode(dados).decode().rstrip("=")
    assert "-" in texto or "_" in texto
    saida, problemas = decodificar(texto)
    assert saida == dados and problemas == []


def test_base64_que_termina_no_meio_de_um_bloco():
    texto = base64.b64encode(b"abcdefghij").decode().rstrip("=")
    saida, problemas = decodificar(texto[:13])  # sobra 1 caractere
    assert saida == b"abcdefghi"
    assert [p.categoria for p in problemas] == ["base64 com defeito"]


def test_caracteres_invalidos_sao_descartados_e_registrados():
    saida, problemas = decodificar("QUJD*REVG")
    assert saida == b"ABCDEF" and problemas


def test_concatena_na_ordem_fisica():
    dados = s.jpeg()
    assert reconstruir(s.fatiar(s.b64(dados), 1000)).dados == dados


def test_pedacos_codificados_separadamente_com_padding_no_meio():
    partes = [b"primeiro pedaco!", b"segundo", b"terceiro."]
    fragmentos = [base64.b64encode(p).decode() for p in partes]
    assert any("=" in f for f in fragmentos[:-1])
    assert reconstruir(fragmentos).dados == b"".join(partes)


def test_assinatura_so_no_primeiro_pedaco_e_um_arquivo_so():
    fragmentos = s.fatiar(s.b64(s.jpeg()), 4000)
    assert comeca_com_assinatura(fragmentos[0])
    assert not any(comeca_com_assinatura(f) for f in fragmentos[1:])
    assert len(separar_arquivos(fragmentos)) == 1


def test_duas_imagens_na_mesma_linha_sao_separadas():
    a, b = s.jpeg(semente=1), s.png()
    arquivos = separar_arquivos(s.fatiar(s.b64(a), 4000) + s.fatiar(s.b64(b), 4000))
    assert [r.dados for r in arquivos] == [a, b]


def test_assinatura_por_acaso_no_meio_nao_divide_o_arquivo():
    fragmentos = s.fatiar(s.b64(s.jpeg()), 4000)
    fragmentos.insert(1, "/9j/" + "A" * 3996)  # parece JPEG, mas o trecho anterior não termina com FFD9
    assert len(separar_arquivos(fragmentos)) == 1
