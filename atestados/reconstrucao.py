"""Reconstrução do arquivo a partir dos pedaços de base64 de uma linha.

O servidor fatia o base64 em várias células (limite de 32.767 caracteres por célula do
Excel). Para reconstruir: limpar cada pedaço e concatenar na ordem física das colunas.
"""
from __future__ import annotations

import binascii
import re
from dataclasses import dataclass, field

from .formatos import Problema, detectar_formato, termina_corretamente
from .leitura import valor_texto

TAMANHO_MINIMO_BASE64 = 64  # textos menores não são considerados início de imagem

_RE_ESPACOS_ASPAS = re.compile(r"[\s\"']+")
_RE_PREFIXO_DATA = re.compile(r"data:[^,]{0,200},", re.IGNORECASE)  # data:image/jpeg;base64,
_RE_ALFABETO = re.compile(r"[A-Za-z0-9+/=_-]*")  # padrão + url-safe
_RE_ALFABETO_PADRAO = re.compile(r"[A-Za-z0-9+/]*")
_RE_FORA_DO_ALFABETO = re.compile(r"[^A-Za-z0-9+/]")


def limpar_fragmento(valor) -> str:
    """Texto do pedaço sem espaços, quebras de linha, aspas nem prefixo data:...;base64,"""
    texto = valor_texto(valor)
    if not texto:
        return ""
    texto = _RE_ESPACOS_ASPAS.sub("", texto)
    prefixo = _RE_PREFIXO_DATA.match(texto)
    if prefixo:
        texto = texto[prefixo.end():]
    return texto


def no_alfabeto(texto: str) -> bool:
    return _RE_ALFABETO.fullmatch(texto) is not None


def parece_base64(texto_limpo: str) -> bool:
    return len(texto_limpo) >= TAMANHO_MINIMO_BASE64 and no_alfabeto(texto_limpo)


@dataclass
class Reconstrucao:
    dados: bytes
    tamanho_base64: int  # caracteres de base64 usados (já limpos)
    problemas: list[Problema] = field(default_factory=list)


def decodificar(texto: str) -> tuple[bytes, list[Problema]]:
    """Decodifica base64 padrão ou url-safe, corrigindo o padding. Nunca levanta exceção."""
    problemas: list[Problema] = []
    if "-" in texto or "_" in texto:
        texto = texto.replace("-", "+").replace("_", "/")
    corpo = texto.rstrip("=")
    if _RE_ALFABETO_PADRAO.fullmatch(corpo) is None:
        corpo = _RE_FORA_DO_ALFABETO.sub("", corpo)
        problemas.append(Problema("base64 com defeito",
                                  "o base64 tinha caracteres inválidos, que foram descartados"))
    if len(corpo) % 4 == 1:  # sobra 1 caractere: não forma nenhum byte
        corpo = corpo[:-1]
        problemas.append(Problema("base64 com defeito", "o base64 termina no meio de um bloco"))
    dados = binascii.a2b_base64(corpo + "=" * (-len(corpo) % 4), strict_mode=True)
    return dados, problemas


def reconstruir(fragmentos: list[str]) -> Reconstrucao:
    """`fragmentos`: pedaços já limpos, na ordem física, sem vazios."""
    tamanho = sum(map(len, fragmentos))
    if any("=" in f for f in fragmentos[:-1]):
        # '=' antes do último pedaço: cada pedaço foi codificado separadamente.
        partes, problemas = [], []
        for f in fragmentos:
            dados, p = decodificar(f)
            partes.append(dados)
            problemas.extend(p)
        return Reconstrucao(b"".join(partes), tamanho, _sem_repetir(problemas))
    dados, problemas = decodificar("".join(fragmentos))
    return Reconstrucao(dados, tamanho, problemas)


def comeca_com_assinatura(fragmento: str) -> bool:
    """O pedaço começa com a assinatura de algum formato conhecido (JPEG, PNG, PDF...)?"""
    cabeca = fragmento[:16].replace("-", "+").replace("_", "/")
    cabeca = cabeca[: len(cabeca) - len(cabeca) % 4]
    if not cabeca:
        return False
    try:
        inicio = binascii.a2b_base64(cabeca)
    except binascii.Error:
        return False
    return detectar_formato(inicio, parcial=True) is not None


def separar_arquivos(fragmentos: list[str]) -> list[Reconstrucao]:
    """Normalmente 1 arquivo por linha. Se um pedaço do meio começa com assinatura E o
    trecho anterior termina com o marcador de fim do seu formato, a linha tem 2+ arquivos."""
    candidatos = [i for i in range(1, len(fragmentos)) if comeca_com_assinatura(fragmentos[i])]
    if not candidatos:
        return [reconstruir(fragmentos)]
    arquivos, inicio = [], 0
    for i in candidatos:
        anterior = reconstruir(fragmentos[inicio:i])
        if termina_corretamente(anterior.dados):
            arquivos.append(anterior)
            inicio = i
    arquivos.append(reconstruir(fragmentos[inicio:]))
    return arquivos


def _sem_repetir(problemas: list[Problema]) -> list[Problema]:
    vistos, saida = set(), []
    for p in problemas:
        if p.detalhe not in vistos:
            vistos.add(p.detalhe)
            saida.append(p)
    return saida
