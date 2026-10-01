import pytest

import sintetico as s
from atestados import formatos


def test_formato_pelos_bytes_e_nao_pela_extensao():
    assert formatos.detectar_formato(s.jpeg()) is formatos.JPEG
    assert formatos.detectar_formato(s.png()) is formatos.PNG
    assert formatos.detectar_formato(s.pdf()) is formatos.PDF
    assert formatos.detectar_formato(b"GIF89a" + bytes(10)) is formatos.GIF
    assert formatos.detectar_formato(b"RIFF\0\0\0\0WEBPVP8 ") is formatos.WEBP
    assert formatos.detectar_formato(b"\0\0\0\x18ftypheic\0\0\0\0") is formatos.HEIC
    assert formatos.detectar_formato(b"II*\x00" + bytes(8)) is formatos.TIFF
    assert formatos.detectar_formato(b"\r\n%PDF-1.4 ...") is formatos.PDF  # lixo antes do %PDF
    assert formatos.detectar_formato(b"qualquer coisa") is None


@pytest.mark.parametrize("gerar", [s.jpeg, s.png, s.pdf])
def test_arquivo_integro_passa_na_validacao(gerar):
    dados = gerar()
    assert formatos.validar(dados, formatos.detectar_formato(dados)) is None


@pytest.mark.parametrize("gerar", [s.jpeg, s.png])
def test_imagem_truncada_e_detectada_decodificando_por_inteiro(gerar):
    dados = gerar()
    problema = formatos.validar(dados[: len(dados) * 2 // 3], formatos.detectar_formato(dados))
    assert problema is not None
    assert problema.categoria in ("imagem incompleta", "imagem corrompida")


def test_pdf_sem_eof_e_detectado():
    assert formatos.validar(s.pdf()[:-200], formatos.PDF).categoria == "PDF incompleto"


def test_jpeg_com_bytes_extras_depois_do_fim_continua_valido():
    # alguns celulares gravam dados depois do marcador de fim (FFD9)
    assert formatos.validar(s.jpeg() + bytes(50) + b"TRAILER" * 40, formatos.JPEG) is None


def test_heic_vai_para_verificar():
    assert formatos.validar(b"\0\0\0\x18ftypheic", formatos.HEIC).categoria == "formato sem validação"


def test_conferir_tamanho_com_as_colunas_da_planilha():
    assert formatos.conferir_tamanho(100, 136, 100, 136) is None
    assert formatos.conferir_tamanho(100, 136, None, None) is None
    p = formatos.conferir_tamanho(3_600_000, 4_800_000, 6_000_000, 8_000_000)
    assert p.categoria == "incompleto na planilha" and "faltam 40%" in p.detalhe
