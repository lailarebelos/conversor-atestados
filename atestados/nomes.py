"""Nomes dos arquivos gerados: CHAPA_NOME_ID.ext, seguros para o Windows e sem repetição."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

SUFIXO_VERIFICAR = "_VERIFICAR"
SUFIXO_TEMPORARIO = ".parcial"  # usado durante a gravação; some ao terminar
LIMITE_CAMINHO = 250  # o Windows recusa caminhos com 260+ caracteres
LIMITE_NOME = 120  # nome do arquivo, sem a pasta
_FOLGA = len(SUFIXO_VERIFICAR) + len("_99") + len(".webp") + len(SUFIXO_TEMPORARIO)

_RE_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_RE_ESPACOS = re.compile(r"\s+")
_RE_SUBLINHADOS = re.compile(r"_+")
_RESERVADOS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class CaminhoLongoDemais(Exception):
    """A pasta de destino é tão longa que os nomes dos arquivos não caberiam."""


def parte_segura(texto: str) -> str:
    """Troca o que o Windows não aceita por separador; espaços viram _; mantém acentos."""
    t = unicodedata.normalize("NFC", texto or "").strip()
    t = _RE_INVALIDOS.sub(" ", t)
    t = _RE_ESPACOS.sub("_", t)
    t = _RE_SUBLINHADOS.sub("_", t)
    return t.strip("._ ")


def espaco_para_nome(pasta: Path) -> int:
    """Quantos caracteres sobram para o nome base (sem sufixos/extensão) dentro de `pasta`."""
    return min(LIMITE_NOME, LIMITE_CAMINHO - len(str(pasta)) - 1) - _FOLGA


def verificar_comprimento(pasta: Path) -> None:
    if espaco_para_nome(pasta) < 20:
        raise CaminhoLongoDemais(
            "O caminho da pasta de destino é longo demais para o Windows. "
            "Escolha uma pasta mais curta (por exemplo, Documentos ou a Área de Trabalho)."
        )


class GeradorNomes:
    """Monta CHAPA_NOME_ID (ou o nº sequencial 001, 002… se faltar identificação),
    corta o NOME se o caminho ficar longo e acrescenta _2, _3… em nomes repetidos."""

    def __init__(self, pasta: Path, total_linhas: int):
        self.pasta = Path(pasta)
        self.espaco = espaco_para_nome(self.pasta)
        self.digitos = max(3, len(str(max(total_linhas, 1))))
        self._usados: set[str] = set()

    def base(self, chapa: str, nome: str, id_atestado: str, sequencial: int) -> str:
        chapa, nome, ident = parte_segura(chapa), parte_segura(nome), parte_segura(id_atestado)
        if not (chapa or nome or ident):
            return str(sequencial).zfill(self.digitos)
        fixas = [p for p in (chapa, ident) if p]
        sobra = self.espaco - sum(map(len, fixas)) - len(fixas)  # separadores
        if nome and sobra < len(nome):
            nome = nome[:max(sobra, 0)].rstrip("._ ")
        partes = [p for p in (chapa, nome, ident) if p]
        base = "_".join(partes)[: self.espaco].rstrip("._ ")
        if base.split(".")[0].upper() in _RESERVADOS:
            base += "_"
        return base or str(sequencial).zfill(self.digitos)

    def nome_arquivo(self, base: str, extensao: str, verificar: bool = False, parte: int | None = None) -> str:
        nucleo = base + (f"_{parte}" if parte else "")
        sufixo = (SUFIXO_VERIFICAR if verificar else "") + extensao
        candidato, n = nucleo + sufixo, 2
        while candidato.lower() in self._usados:
            candidato = f"{nucleo}_{n}{sufixo}"
            n += 1
        self._usados.add(candidato.lower())
        return candidato
