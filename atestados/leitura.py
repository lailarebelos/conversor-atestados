"""Leitura das planilhas recebidas do servidor.

Aceita .xlsx/.xlsm/.xls/.ods (via python-calamine, rápido mesmo com centenas de MB)
e .csv. O tipo é decidido pelos bytes do arquivo, não pela extensão. As linhas são
entregues uma a uma, com os valores na ordem física das colunas.
"""
from __future__ import annotations

import codecs
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from python_calamine import CalamineWorkbook, PasswordError, SheetTypeEnum, SheetVisibleEnum

ASSINATURA_ZIP = b"PK\x03\x04"  # .xlsx, .xlsm, .ods
ASSINATURA_XLS = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # .xls antigo
LIMITE_CAMPO_CSV = 2**31 - 1  # sys.maxsize estoura no Windows


class ErroLeitura(Exception):
    """A planilha não pôde ser lida. A mensagem já é própria para mostrar ao usuário."""


@dataclass
class Linha:
    numero: int  # número da linha como o Excel mostra (1 = primeira)
    valores: list  # valores na ordem física das colunas


def valor_texto(valor) -> str:
    """Texto de uma célula, sem nunca virar 'None' ou 'nan' (erro clássico com pandas)."""
    if valor is None:
        return ""
    if isinstance(valor, str):
        return valor
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, float):
        if math.isnan(valor) or math.isinf(valor):
            return ""
        return str(int(valor)) if valor.is_integer() else repr(valor)
    return str(valor)


def celula_vazia(valor) -> bool:
    if valor is None:
        return True
    if isinstance(valor, str):
        return not valor.strip()
    if isinstance(valor, float):
        return math.isnan(valor)
    return False


def tipo_do_arquivo(caminho: Path) -> str:
    """'planilha' (xlsx/xls/ods) ou 'csv'."""
    with open(caminho, "rb") as f:
        inicio = f.read(512)
    if inicio.startswith(ASSINATURA_ZIP) or inicio.startswith(ASSINATURA_XLS):
        return "planilha"
    texto = inicio.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if texto.startswith((b"<html", b"<!doctype", b"<table", b"<?xml")):
        raise ErroLeitura(
            "Este arquivo não é uma planilha do Excel (parece uma página HTML/XML). "
            "Exporte de novo pelo sistema, em .xlsx ou .csv."
        )
    if not inicio:
        raise ErroLeitura("O arquivo está vazio.")
    return "csv"


class Planilha:
    """Uma planilha no disco. `linhas()` pode ser chamado mais de uma vez (relê o arquivo)."""

    def __init__(self, caminho):
        self.caminho = Path(caminho)
        if not self.caminho.is_file():
            raise ErroLeitura("Arquivo não encontrado.")
        try:
            self.tipo = tipo_do_arquivo(self.caminho)
        except OSError as e:
            raise ErroLeitura(f"Não foi possível abrir o arquivo ({type(e).__name__}).") from None

    def linhas(self) -> Iterator[Linha]:
        if self.tipo == "planilha":
            yield from self._linhas_planilha()
        else:
            yield from self._linhas_csv()

    # ---------- xlsx / xls / ods ----------
    def _linhas_planilha(self) -> Iterator[Linha]:
        try:
            livro = CalamineWorkbook.from_path(str(self.caminho))
        except PasswordError:
            raise ErroLeitura(
                "A planilha está protegida por senha. Salve uma cópia sem senha e tente de novo."
            ) from None
        except Exception as e:  # noqa: BLE001 - mensagem genérica, sem conteúdo do arquivo
            raise ErroLeitura(
                f"Não foi possível ler a planilha ({type(e).__name__}). "
                "Ela pode estar corrompida ou ter sido baixada pela metade."
            ) from None
        try:
            aba = self._escolher_aba(livro)
            # iter_rows() começa na linha 1 do Excel: as linhas vazias do topo vêm vazias.
            for i, valores in enumerate(aba.iter_rows()):
                yield Linha(i + 1, valores)
        except ErroLeitura:
            raise
        except Exception as e:  # noqa: BLE001
            raise ErroLeitura(f"Erro ao ler as linhas da planilha ({type(e).__name__}).") from None
        finally:
            livro.close()

    @staticmethod
    def _escolher_aba(livro):
        """A aba visível com mais células (a das fotos é, de longe, a maior)."""
        metas = list(livro.sheets_metadata)
        candidatas = [i for i, m in enumerate(metas)
                      if m.typ == SheetTypeEnum.WorkSheet and m.visible == SheetVisibleEnum.Visible]
        if not candidatas:
            candidatas = [i for i, m in enumerate(metas) if m.typ == SheetTypeEnum.WorkSheet]
        melhor, maior_area = None, -1
        for i in candidatas:
            aba = livro.get_sheet_by_index(i)
            area = aba.height * aba.width
            if area > maior_area:
                melhor, maior_area = aba, area
        if melhor is None or maior_area <= 0:
            raise ErroLeitura("A planilha não tem nenhuma aba com dados.")
        return melhor

    # ---------- csv ----------
    def _linhas_csv(self) -> Iterator[Linha]:
        csv.field_size_limit(LIMITE_CAMPO_CSV)
        codificacao = self._codificacao_csv()
        numero = 0
        try:
            with open(self.caminho, "r", encoding=codificacao, errors="replace", newline="") as f:
                primeira = f.readline()
                delimitador = max(";,\t|", key=primeira.count)
                if primeira.count(delimitador) == 0:
                    delimitador = ";"  # uma coluna só
                f.seek(0)
                for numero, valores in enumerate(csv.reader(f, delimiter=delimitador), start=1):
                    yield Linha(numero, valores)
        except csv.Error:
            raise ErroLeitura(f"O arquivo CSV está mal formado perto da linha {numero + 1}.") from None

    def _codificacao_csv(self) -> str:
        with open(self.caminho, "rb") as f:
            inicio = f.read(4)
            if inicio.startswith(codecs.BOM_UTF8):
                return "utf-8-sig"
            if inicio.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
                return "utf-16"
            f.seek(0)
            decodificador = codecs.getincrementaldecoder("utf-8")()
            try:
                while bloco := f.read(4 * 1024 * 1024):
                    decodificador.decode(bloco)
                decodificador.decode(b"", final=True)
            except UnicodeDecodeError:
                return "cp1252"  # padrão do Excel/Windows em português
        return "utf-8"
