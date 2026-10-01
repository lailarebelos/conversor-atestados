"""Metadados dos arquivos: data em que a foto foi tirada e remoção da localização (GPS).

A remoção do GPS é feita no próprio arquivo, sem recomprimir: o bloco de GPS do EXIF
(e as coordenadas do XMP, se houver) é zerado byte a byte. Pixels, orientação, data
da foto e tamanho do arquivo não mudam.
"""
from __future__ import annotations

import io
import re
import zlib
from datetime import date, timedelta

from PIL import Image

from . import formatos

_TAG_GPS = 0x8825
_TAG_EXIF = 0x8769
_TAG_DATA_ORIGINAL = 0x9003
_TAG_DATA_DIGITALIZADA = 0x9004
_TAG_DATA = 0x0132
_TAGS_COORDENADAS = (2, 4)  # GPSLatitude, GPSLongitude
_TAMANHO_TIPO = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8, 13: 4}

_EXIF_ID = b"Exif\x00\x00"
_XMP_ID = b"http://ns.adobe.com/xap/1.0/\x00"
_XMP_EXT_ID = b"http://ns.adobe.com/xmp/extension/\x00"
_RE_XMP_GPS_ATRIBUTO = re.compile(rb'([\w-]+:gps\w*\s*=\s*["\'])([^"\']*)', re.IGNORECASE)
_RE_XMP_GPS_ELEMENTO = re.compile(rb"(<([\w-]+:gps\w*)>)([^<]*)(</\2>)", re.IGNORECASE)
_RE_EXIF_DATA = re.compile(rb"(\d{4}):(\d{2}):(\d{2})")
_RE_PDF_DATAS = (
    re.compile(rb"/CreationDate\s*\(\s*D:\s*(\d{4})(\d{2})(\d{2})"),
    re.compile(rb"<xmp:CreateDate>\s*(\d{4})-(\d{2})-(\d{2})"),
    re.compile(rb'xmp:CreateDate\s*=\s*"(\d{4})-(\d{2})-(\d{2})'),
)

GPS_REMOVIDO = "removido"
GPS_AUSENTE = "sem GPS"
GPS_FALHOU = "falhou"


# ---------------------------------------------------------------- TIFF (EXIF) ---
class _Tiff:
    """Acesso de baixo nível a um bloco TIFF (o formato interno do EXIF) dentro de um buffer."""

    def __init__(self, buf, base: int, fim: int):
        self.buf, self.base, self.tam = buf, base, fim - base
        self.ordem = {b"II": "little", b"MM": "big"}.get(bytes(buf[base:base + 2]))

    def valido(self) -> bool:
        return self.ordem is not None and self.tam >= 8

    def u16(self, o: int) -> int:
        return int.from_bytes(self.buf[self.base + o:self.base + o + 2], self.ordem)

    def u32(self, o: int) -> int:
        return int.from_bytes(self.buf[self.base + o:self.base + o + 4], self.ordem)

    def entradas(self, ifd: int):
        """(posição, tag, tipo, contagem) de cada entrada do IFD, sem sair do bloco."""
        if not (8 <= ifd <= self.tam - 2):
            return
        for k in range(self.u16(ifd)):
            pos = ifd + 2 + 12 * k
            if pos + 12 > self.tam:
                return
            yield pos, self.u16(pos), self.u16(pos + 2), self.u32(pos + 4)

    def valor(self, pos: int, tipo: int, contagem: int) -> tuple[int, int]:
        """(início, tamanho) dos bytes do valor de uma entrada."""
        tamanho = _TAMANHO_TIPO.get(tipo, 1) * contagem
        return (pos + 8, tamanho) if tamanho <= 4 else (self.u32(pos + 8), tamanho)

    def ponteiro(self, ifd: int, tag_procurada: int) -> int | None:
        for pos, tag, _, _ in self.entradas(ifd):
            if tag == tag_procurada:
                return self.u32(pos + 8)
        return None


def _zerar_gps_tiff(buf: bytearray, base: int, fim: int) -> tuple[bool, bool]:
    """Esvazia o IFD de GPS. Devolve (alterou, tinha_coordenadas)."""
    t = _Tiff(buf, base, fim)
    if not t.valido():
        return False, False
    gps = t.ponteiro(t.u32(4), _TAG_GPS)
    if gps is None or not (8 <= gps <= t.tam - 2):
        return False, False
    entradas = list(t.entradas(gps))
    tinha_coordenadas = False
    for pos, tag, tipo, contagem in entradas:
        inicio, tamanho = t.valor(pos, tipo, contagem)
        if 0 <= inicio and inicio + tamanho <= t.tam:
            if tag in _TAGS_COORDENADAS and tipo in (5, 10):
                if any(t.u32(inicio + 8 * j) for j in range(contagem) if inicio + 8 * j + 4 <= t.tam):
                    tinha_coordenadas = True
            if tamanho > 4:
                buf[base + inicio:base + inicio + tamanho] = bytes(tamanho)
        buf[base + pos:base + pos + 12] = bytes(12)
    buf[base + gps:base + gps + 2] = bytes(2)  # IFD vazio: 0 entradas, próximo IFD = 0
    fim_ifd = gps + 2 + 12 * len(entradas)
    if fim_ifd + 4 <= t.tam:
        buf[base + fim_ifd:base + fim_ifd + 4] = bytes(4)
    return bool(entradas), tinha_coordenadas


def _zerar_gps_xmp(buf: bytearray, inicio: int, fim: int) -> tuple[bool, bool]:
    """Troca por zeros os dígitos das propriedades GPS do XMP (mesmo tamanho, nada se desloca)."""
    trecho = bytes(buf[inicio:fim])
    alterou = tinha = False

    def zerar(valor: bytes) -> bytes:
        return re.sub(rb"[1-9]", b"0", valor)

    for m in list(_RE_XMP_GPS_ATRIBUTO.finditer(trecho)) + list(_RE_XMP_GPS_ELEMENTO.finditer(trecho)):
        grupo = 2 if m.re is _RE_XMP_GPS_ATRIBUTO else 3
        valor = m.group(grupo)
        novo = zerar(valor)
        if novo != valor:
            alterou = True
            if re.search(rb"(latitude|longitude)", m.group(1), re.IGNORECASE):
                tinha = True
            a, b = m.span(grupo)
            buf[inicio + a:inicio + b] = novo
    return alterou, tinha


# ---------------------------------------------------------------- contêineres ---
def _segmentos_jpeg(buf):
    """(marcador, início_dados, fim_dados) dos segmentos antes da imagem em si (SOS)."""
    i, n = 2, len(buf)
    while i + 4 <= n:
        if buf[i] != 0xFF:
            return
        marcador = buf[i + 1]
        if marcador == 0xFF:  # byte de preenchimento
            i += 1
            continue
        if marcador in (0xD8, 0x01) or 0xD0 <= marcador <= 0xD7:
            i += 2
            continue
        if marcador in (0xDA, 0xD9):  # início da imagem / fim: acabaram os metadados
            return
        tamanho = int.from_bytes(buf[i + 2:i + 4], "big")
        if tamanho < 2:
            return
        yield marcador, i + 4, min(i + 2 + tamanho, n)
        i += 2 + tamanho


def _gps_jpeg(buf: bytearray) -> tuple[bool, bool]:
    alterou = tinha = False
    for marcador, ini, fim in list(_segmentos_jpeg(buf)):
        if marcador != 0xE1:
            continue
        if buf[ini:ini + 6] == _EXIF_ID:
            a, t = _zerar_gps_tiff(buf, ini + 6, fim)
        elif buf[ini:ini + len(_XMP_ID)] == _XMP_ID or buf[ini:ini + len(_XMP_EXT_ID)] == _XMP_EXT_ID:
            a, t = _zerar_gps_xmp(buf, ini, fim)
        else:
            continue
        alterou, tinha = alterou or a, tinha or t
    return alterou, tinha


def _gps_png(buf: bytearray) -> tuple[bool, bool]:
    alterou = tinha = False
    i = 8
    while i + 12 <= len(buf):
        tamanho = int.from_bytes(buf[i:i + 4], "big")
        tipo = bytes(buf[i + 4:i + 8])
        ini, fim = i + 8, i + 8 + tamanho
        if fim + 4 > len(buf):
            break
        a = t = False
        if tipo == b"eXIf":
            base = ini + 6 if buf[ini:ini + 6] == _EXIF_ID else ini
            a, t = _zerar_gps_tiff(buf, base, fim)
        elif tipo == b"iTXt" and buf[ini:ini + 18] == b"XML:com.adobe.xmp\x00" and buf[ini + 18] == 0:
            a, t = _zerar_gps_xmp(buf, ini, fim)  # só iTXt não comprimido
        if a:  # PNG tem CRC por bloco: recalcular
            buf[fim:fim + 4] = (zlib.crc32(bytes(buf[i + 4:fim])) & 0xFFFFFFFF).to_bytes(4, "big")
        alterou, tinha = alterou or a, tinha or t
        if tipo == b"IEND":
            break
        i = fim + 4
    return alterou, tinha


def _gps_webp(buf: bytearray) -> tuple[bool, bool]:
    alterou = tinha = False
    i = 12
    while i + 8 <= len(buf):
        tipo = bytes(buf[i:i + 4])
        tamanho = int.from_bytes(buf[i + 4:i + 8], "little")
        ini, fim = i + 8, min(i + 8 + tamanho, len(buf))
        a = t = False
        if tipo == b"EXIF":
            base = ini + 6 if buf[ini:ini + 6] == _EXIF_ID else ini
            a, t = _zerar_gps_tiff(buf, base, fim)
        elif tipo == b"XMP ":
            a, t = _zerar_gps_xmp(buf, ini, fim)
        alterou, tinha = alterou or a, tinha or t
        i = ini + tamanho + (tamanho & 1)
    return alterou, tinha


def remover_gps(dados: bytes, formato: formatos.Formato | None) -> tuple[bytes, str]:
    """Devolve (bytes, estado), estado = 'removido' (havia coordenadas), 'sem GPS' ou 'falhou'."""
    if formato not in (formatos.JPEG, formatos.PNG, formatos.WEBP, formatos.TIFF):
        return dados, GPS_AUSENTE
    buf = bytearray(dados)
    try:
        if formato is formatos.JPEG:
            alterou, tinha = _gps_jpeg(buf)
        elif formato is formatos.PNG:
            alterou, tinha = _gps_png(buf)
        elif formato is formatos.WEBP:
            alterou, tinha = _gps_webp(buf)
        else:
            alterou, tinha = _zerar_gps_tiff(buf, 0, len(buf))
    except Exception:  # noqa: BLE001 - metadado malformado: mantém o original
        return dados, GPS_FALHOU
    if not alterou:
        return dados, GPS_AUSENTE
    return bytes(buf), (GPS_REMOVIDO if tinha else GPS_AUSENTE)


def tem_coordenadas_gps(dados: bytes) -> bool:
    """Verificação independente (pelo Pillow) de que ainda há latitude/longitude no EXIF."""
    try:
        with Image.open(io.BytesIO(dados)) as imagem:
            gps = imagem.getexif().get_ifd(_TAG_GPS)
    except Exception:  # noqa: BLE001
        return False
    for tag in _TAGS_COORDENADAS:
        valor = gps.get(tag)
        if valor and any(float(x) for x in valor):
            return True
    return False


# ---------------------------------------------------------------- datas ---
def _data_plausivel(ano: int, mes: int, dia: int, hoje: date | None = None) -> date | None:
    try:
        d = date(ano, mes, dia)
    except ValueError:
        return None
    hoje = hoje or date.today()
    return d if date(2000, 1, 1) <= d <= hoje + timedelta(days=1) else None


def _data_exif(valor) -> date | None:
    if isinstance(valor, str):
        valor = valor.encode("ascii", "ignore")
    if not isinstance(valor, (bytes, bytearray)):
        return None
    m = _RE_EXIF_DATA.search(bytes(valor))
    return _data_plausivel(int(m[1]), int(m[2]), int(m[3])) if m else None


def _data_no_tiff(buf, base: int, fim: int) -> date | None:
    t = _Tiff(buf, base, fim)
    if not t.valido():
        return None

    def ler(ifd, tag_procurada):
        for pos, tag, tipo, contagem in t.entradas(ifd):
            if tag == tag_procurada and tipo == 2:
                inicio, tamanho = t.valor(pos, tipo, contagem)
                if 0 <= inicio and inicio + tamanho <= t.tam:
                    return _data_exif(bytes(buf[base + inicio:base + inicio + tamanho]))
        return None

    ifd0 = t.u32(4)
    exif = t.ponteiro(ifd0, _TAG_EXIF)
    for ifd, tag in ((exif, _TAG_DATA_ORIGINAL), (exif, _TAG_DATA_DIGITALIZADA), (ifd0, _TAG_DATA)):
        if ifd is not None:
            d = ler(ifd, tag)
            if d:
                return d
    return None


def data_do_arquivo(dados: bytes) -> date | None:
    """Data em que a foto foi tirada (EXIF) ou em que o PDF foi criado.

    Para JPEG basta o começo do arquivo (o EXIF fica nos primeiros 64 KB)."""
    formato = formatos.detectar_formato(dados, parcial=True)
    if formato is formatos.JPEG:
        for marcador, ini, fim in _segmentos_jpeg(dados):
            if marcador == 0xE1 and dados[ini:ini + 6] == _EXIF_ID:
                return _data_no_tiff(dados, ini + 6, fim)
        return None
    if formato is formatos.PDF:
        for regex in _RE_PDF_DATAS:
            m = regex.search(dados)
            if m:
                d = _data_plausivel(int(m[1]), int(m[2]), int(m[3]))
                if d:
                    return d
        return None
    if formato in (formatos.PNG, formatos.WEBP, formatos.TIFF):
        try:
            with Image.open(io.BytesIO(dados)) as imagem:
                exif = imagem.getexif()
                interno = exif.get_ifd(_TAG_EXIF)
                for valor in (interno.get(_TAG_DATA_ORIGINAL), interno.get(_TAG_DATA_DIGITALIZADA),
                              exif.get(_TAG_DATA)):
                    d = _data_exif(valor)
                    if d:
                        return d
        except Exception:  # noqa: BLE001
            return None
    return None
