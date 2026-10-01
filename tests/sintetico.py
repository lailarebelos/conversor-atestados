"""Geradores de dados 100% sintéticos para os testes. Nenhum dado real é usado."""
from __future__ import annotations

import base64
import csv
import io
import random
from pathlib import Path

import openpyxl
from PIL import Image

CABECALHO_FIXO = ["ID_ATESTADO", "COD_EMPRESA", "CHAPA_SOLICITANTE", "NOME",
                  "TAMANHO_ORIGINAL_BYTES", "TAMANHO_BASE64_CHARS"]
FATIA = 32000
LAT, LON = (23.0, 32.0, 10.5), (46.0, 38.0, 1.25)  # coordenadas fictícias


def exif(data: str | None = "2026:09:10 08:30:00", orientacao: int | None = 6, gps: bool = True) -> bytes:
    e = Image.Exif()
    if orientacao is not None:
        e[0x0112] = orientacao
    if data:
        e.get_ifd(0x8769)[0x9003] = data
    if gps:
        g = e.get_ifd(0x8825)
        g[1], g[2], g[3], g[4] = "S", LAT, "W", LON
    return e.tobytes()


def jpeg(largura: int = 320, altura: int = 240, gps: bool = True, data: str | None = "2026:09:10 08:30:00",
         orientacao: int | None = 6, qualidade: int = 88, semente: int = 1) -> bytes:
    random.seed(semente)
    ruido = Image.effect_noise((largura, altura), 20 + semente % 20)
    fundo = Image.linear_gradient("L").resize((largura, altura))
    imagem = Image.merge("RGB", (fundo, ruido, Image.eval(fundo, lambda v: 255 - v)))
    buf = io.BytesIO()
    imagem.save(buf, "JPEG", quality=qualidade, exif=exif(data, orientacao, gps))
    return buf.getvalue()


def com_tamanho_exato(dados_jpeg: bytes, alvo: int) -> bytes:
    """JPEG válido com exatamente `alvo` bytes: acrescenta segmentos de comentário (COM)
    logo antes do início da imagem (SOS), depois do EXIF, como numa foto real."""
    falta = alvo - len(dados_jpeg)
    if falta == 0:
        return dados_jpeg
    if falta < 4:
        raise ValueError("alvo pequeno demais")
    segmentos = []
    sorteio = random.Random(alvo)  # bytes aleatórios: não comprimem, como os de uma foto real
    while falta:
        carga = min(65533, falta - 4)
        if 0 < falta - (carga + 4) < 4:  # não deixar uma sobra impossível de preencher
            carga -= 4
        segmentos.append(b"\xff\xfe" + (carga + 2).to_bytes(2, "big") + sorteio.randbytes(carga))
        falta -= carga + 4
    i = 2
    while dados_jpeg[i + 1] != 0xDA:  # pula os segmentos até o SOS
        i += 2 + int.from_bytes(dados_jpeg[i + 2:i + 4], "big")
    return dados_jpeg[:i] + b"".join(segmentos) + dados_jpeg[i:]


def png(largura: int = 200, altura: int = 150) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (largura, altura), (10, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


def pdf(largura: int = 200, altura: int = 280) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (largura, altura), "white").save(buf, "PDF")
    return buf.getvalue()


def b64(dados: bytes, urlsafe: bool = False) -> str:
    return (base64.urlsafe_b64encode if urlsafe else base64.b64encode)(dados).decode("ascii")


def fatiar(texto: str, tamanho: int = FATIA) -> list[str]:
    return [texto[i:i + tamanho] for i in range(0, len(texto), tamanho)]


def linha(ident, chapa, nome, dados: bytes | None, fragmentos: list[str] | None = None,
          empresa=1, declarar: bool = True) -> list:
    """Uma linha no layout do servidor: ID, empresa, chapa, nome, tamanhos e os pedaços."""
    if fragmentos is None:
        fragmentos = fatiar(b64(dados)) if dados else []
    tam = len(dados) if (dados and declarar) else None
    tam_b64 = len(b64(dados)) if (dados and declarar) else None
    return [ident, empresa, chapa, nome, tam, tam_b64] + fragmentos


def cabecalho(n_partes: int, nome_parte=lambda i: f"IMG_PARTE{i:03d}") -> list[str]:
    return CABECALHO_FIXO + [nome_parte(i) for i in range(1, n_partes + 1)]


def salvar_xlsx(caminho: Path, cab: list, linhas: list[list]) -> Path:
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("Sheet")
    ws.append(cab)
    for ln in linhas:
        ws.append(ln)
    wb.save(caminho)
    return caminho


def salvar_csv(caminho: Path, cab: list, linhas: list[list], delimitador: str = ";",
               codificacao: str = "utf-8-sig") -> Path:
    with open(caminho, "w", encoding=codificacao, newline="") as f:
        w = csv.writer(f, delimiter=delimitador)
        w.writerow(cab)
        for ln in linhas:
            w.writerow(["" if v is None else v for v in ln])
    return caminho


def planilha_padrao(caminho: Path, linhas: list[list]) -> Path:
    n = max([len(ln) - len(CABECALHO_FIXO) for ln in linhas] + [1])
    return salvar_xlsx(caminho, cabecalho(n), linhas)


def _letra(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def salvar_xlsx_manual(caminho: Path, linhas: list[list], linha_inicial: int = 1, coluna_inicial: int = 1,
                       dimensao: str | None = "A1") -> Path:
    """XLSX mínimo feito à mão, como alguns sistemas geram: textos inline (t="inlineStr"),
    tabela começando fora de A1 e, por padrão, <dimension> errada (A1)."""
    import zipfile
    from xml.sax.saxutils import escape
    xml_linhas = []
    for i, ln in enumerate(linhas):
        r = linha_inicial + i
        celulas = []
        for j, v in enumerate(ln):
            ref = f"{_letra(coluna_inicial + j)}{r}"
            if v is None or v == "":
                continue
            if isinstance(v, (int, float)):
                celulas.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                celulas.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>')
        xml_linhas.append(f'<row r="{r}">{"".join(celulas)}</row>')
    dim = f'<dimension ref="{dimensao}"/>' if dimensao else ""
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    partes = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{pkg}"><Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8"?><workbook {ns} xmlns:r="{rel}"><sheets><sheet name="Dados" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{pkg}"><Relationship Id="rId1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": f'<?xml version="1.0" encoding="UTF-8"?><worksheet {ns}>{dim}<sheetData>{"".join(xml_linhas)}</sheetData></worksheet>',
    }
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, conteudo in partes.items():
            z.writestr(nome, conteudo)
    return caminho
