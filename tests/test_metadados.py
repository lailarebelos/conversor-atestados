import io
from datetime import date

from PIL import Image

import sintetico as s
from atestados import formatos, metadados


def test_remove_gps_sem_recomprimir_e_sem_mexer_no_resto():
    original = s.jpeg(gps=True)
    assert metadados.tem_coordenadas_gps(original)
    limpo, estado = metadados.remover_gps(original, formatos.JPEG)
    assert estado == metadados.GPS_REMOVIDO
    assert len(limpo) == len(original)
    assert not metadados.tem_coordenadas_gps(limpo)
    inicio_imagem = original.find(b"\xff\xda")  # dados comprimidos da imagem: idênticos
    assert limpo[inicio_imagem:] == original[inicio_imagem:]
    with Image.open(io.BytesIO(limpo)) as a, Image.open(io.BytesIO(original)) as b:
        assert a.tobytes() == b.tobytes()
        assert a.getexif().get(0x0112) == 6  # orientação preservada
    assert metadados.data_do_arquivo(limpo) == date(2026, 9, 10)  # data da foto preservada


def test_foto_sem_gps_fica_identica():
    original = s.jpeg(gps=False)
    assert metadados.remover_gps(original, formatos.JPEG) == (original, metadados.GPS_AUSENTE)


def test_gps_no_xmp_tambem_e_zerado():
    xmp = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description exif:GPSLatitude="23,32.175S" '
           b'exif:GPSLongitude="46,38.021W"><exif:GPSAltitude>760/1</exif:GPSAltitude>'
           b"</rdf:Description></rdf:RDF></x:xmpmeta>")
    segmento = b"\xff\xe1" + (len(metadados._XMP_ID) + len(xmp) + 2).to_bytes(2, "big") + metadados._XMP_ID + xmp
    base = s.jpeg(gps=False)
    dados = base[:2] + segmento + base[2:]
    limpo, estado = metadados.remover_gps(dados, formatos.JPEG)
    assert estado == metadados.GPS_REMOVIDO and len(limpo) == len(dados)
    assert b'GPSLatitude="00,00.000S"' in limpo and b"46,38" not in limpo and b">000/0<" in limpo
    assert formatos.validar(limpo, formatos.JPEG) is None


def test_png_com_gps_continua_valido_crc_recalculado():
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(buf, "PNG", exif=s.exif(gps=True))
    original = buf.getvalue()
    assert metadados.tem_coordenadas_gps(original)
    limpo, estado = metadados.remover_gps(original, formatos.PNG)
    assert estado == metadados.GPS_REMOVIDO
    assert formatos.validar(limpo, formatos.PNG) is None  # o Pillow confere o CRC
    assert not metadados.tem_coordenadas_gps(limpo)


def test_exif_malformado_nao_quebra_nada():
    lixo = b"\xff\xd8\xff\xe1\x00\x10Exif\x00\x00MM\x00*\xff\xff\xff\xff" + s.jpeg(gps=False)[2:]
    dados, estado = metadados.remover_gps(lixo, formatos.JPEG)
    assert dados == lixo and estado == metadados.GPS_AUSENTE


def test_data_da_foto_lida_so_do_comeco_do_arquivo():
    dados = s.com_tamanho_exato(s.jpeg(data="2026:09:11 07:00:00"), 900_000)
    assert metadados.data_do_arquivo(dados[:150_000]) == date(2026, 9, 11)


def test_data_ausente_ou_invalida():
    assert metadados.data_do_arquivo(s.jpeg(data="0000:00:00 00:00:00")) is None
    assert metadados.data_do_arquivo(s.jpeg(data=None)) is None
    assert metadados.data_do_arquivo(b"nada a ver") is None


def test_data_de_criacao_do_pdf():
    pdf = b"%PDF-1.4\n1 0 obj << /CreationDate (D:20260911101500-03'00') >> endobj\n%%EOF"
    assert metadados.data_do_arquivo(pdf) == date(2026, 9, 11)
