"""Formato real do arquivo (pelos bytes, nunca pela extensão) e validação completa."""
from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

# Fotos de celular passam de 50 MP; acima de 2x este valor o Pillow recusa (proteção
# contra "bombas de descompressão").
Image.MAX_IMAGE_PIXELS = 200_000_000


@dataclass(frozen=True)
class Formato:
    nome: str
    extensao: str
    imagem: bool  # True = validar decodificando com o Pillow


JPEG = Formato("JPEG", ".jpg", True)
PNG = Formato("PNG", ".png", True)
GIF = Formato("GIF", ".gif", True)
WEBP = Formato("WEBP", ".webp", True)
BMP = Formato("BMP", ".bmp", True)
TIFF = Formato("TIFF", ".tif", True)
PDF = Formato("PDF", ".pdf", False)
HEIC = Formato("HEIC", ".heic", False)
AVIF = Formato("AVIF", ".avif", False)

_MARCAS_HEIC = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}
_MARCAS_AVIF = {b"avif", b"avis"}
_FIM_PNG = b"IEND\xaeB`\x82"


def detectar_formato(dados: bytes, parcial: bool = False) -> Formato | None:
    """Formato pelos primeiros bytes. `parcial=True` quando só o começo do arquivo está disponível."""
    if dados[:3] == b"\xff\xd8\xff":
        return JPEG
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return PNG
    if dados[:5] == b"%PDF-":
        return PDF
    if dados[:6] in (b"GIF87a", b"GIF89a"):
        return GIF
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return WEBP
    if dados[:4] in (b"II*\x00", b"MM\x00*"):
        return TIFF
    if dados[4:8] == b"ftyp":
        if dados[8:12] in _MARCAS_AVIF:
            return AVIF
        if dados[8:12] in _MARCAS_HEIC:
            return HEIC
    if not parcial:
        # BMP só tem 2 bytes de assinatura: exige também o tamanho gravado no cabeçalho.
        if dados[:2] == b"BM" and len(dados) > 26 and int.from_bytes(dados[2:6], "little") == len(dados):
            return BMP
        # PDF pode ter alguns bytes antes do %PDF (permitido até 1 KB).
        if b"%PDF-" in dados[:1024]:
            return PDF
    return None


def termina_corretamente(dados: bytes) -> bool:
    """O arquivo tem o marcador de fim do seu formato? (usado para separar 2 arquivos numa linha)."""
    fmt = detectar_formato(dados)
    fim = dados.rstrip(b"\x00")
    if fmt is JPEG:
        return fim.endswith(b"\xff\xd9")
    if fmt is PNG:
        return fim.endswith(_FIM_PNG)
    if fmt is PDF:
        return b"%%EOF" in dados.rstrip(b"\x00\t\n\r\f ")[-1024:]
    if fmt is GIF:
        return fim.endswith(b";")
    if fmt is WEBP:
        return int.from_bytes(dados[4:8], "little") + 8 == len(dados)
    return False


@dataclass
class Problema:
    categoria: str  # rótulo curto, para o resumo
    detalhe: str  # texto completo, para o relatório


def validar(dados: bytes, formato: Formato) -> Problema | None:
    """Validação completa. None = arquivo íntegro."""
    if formato.imagem:
        return _validar_imagem(dados)
    if formato is PDF:
        return _validar_pdf(dados)
    return Problema(
        "formato sem validação",
        f"formato {formato.nome}: não foi possível validar; o Windows pode precisar de uma "
        "extensão gratuita da Microsoft Store para abrir",
    )


def _validar_imagem(dados: bytes) -> Problema | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(dados)) as imagem:
                imagem.load()  # decodifica por inteiro (verify() sozinho não pega truncamento)
    except Image.DecompressionBombError:
        return Problema("imagem não validada", "imagem grande demais para validar")
    except UnidentifiedImageError:
        return Problema("imagem corrompida", "os dados não formam uma imagem reconhecível")
    except (OSError, SyntaxError, ValueError, EOFError, IndexError) as e:
        texto = str(e).lower()
        if "truncated" in texto or "broken data stream" in texto or isinstance(e, EOFError):
            return Problema("imagem incompleta", "imagem incompleta: os dados terminam antes do fim da imagem")
        return Problema("imagem corrompida", f"imagem corrompida ({type(e).__name__})")
    return None


def _validar_pdf(dados: bytes) -> Problema | None:
    if dados.find(b"%PDF-", 0, 1024) < 0:
        return Problema("PDF corrompido", "PDF sem o cabeçalho %PDF")
    if b"%%EOF" not in dados.rstrip(b"\x00\t\n\r\f ")[-1024:]:
        return Problema("PDF incompleto", "PDF incompleto: falta o marcador %%EOF no fim")
    return None


def conferir_tamanho(tam_bytes: int, tam_base64: int,
                     declarado_bytes: int | None, declarado_base64: int | None) -> Problema | None:
    """Compara com as colunas TAMANHO_* da planilha, quando existem."""
    if declarado_bytes:
        esperado, incompleto = declarado_bytes, tam_bytes < declarado_bytes
    elif declarado_base64:  # o '=' do fim (até 2) pode ter sido omitido sem perda
        esperado, incompleto = declarado_base64 * 3 // 4, tam_base64 < declarado_base64 - 2
    else:
        return None
    if incompleto:
        falta = max(0.0, 1 - tam_bytes / esperado)
        return Problema(
            "incompleto na planilha",
            f"a planilha traz só parte do arquivo: faltam {falta:.0%} ({tamanho_legivel(esperado - tam_bytes)} "
            f"de {tamanho_legivel(esperado)}); o sistema de origem cortou o arquivo",
        )
    if declarado_bytes and tam_bytes > declarado_bytes:
        return Problema("tamanho diferente do informado",
                        "o arquivo ficou maior do que o tamanho informado na planilha")
    return None


def tamanho_legivel(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB".replace(".", ",")
    return f"{max(1, round(n / 1024))} KB"
