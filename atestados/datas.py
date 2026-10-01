"""Datas: a do nome do arquivo, a de colunas da planilha e a digitada pelo usuário."""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

_SEP = r"[._ -]?"
_RE_DIA_MES_ANO = re.compile(rf"(?<!\d)(\d{{2}}){_SEP}(\d{{2}}){_SEP}(\d{{4}})(?!\d)")
_RE_ANO_MES_DIA = re.compile(rf"(?<!\d)(\d{{4}}){_SEP}(\d{{2}}){_SEP}(\d{{2}})(?!\d)")
_RE_DIA_MES_ANO2 = re.compile(r"(?<!\d)(\d{2})[._-](\d{2})[._-](\d{2})(?!\d)")  # 11-09-26
_RE_TEXTO_DMA = re.compile(r"\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?:[ T].*)?\s*")
_RE_TEXTO_AMD = re.compile(r"\s*(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?\s*")
_RE_DIGITADA = re.compile(r"\s*(\d{1,2})\s*[/.\- ]\s*(\d{1,2})\s*[/.\- ]\s*(\d{4})\s*|\s*(\d{2})(\d{2})(\d{4})\s*")
_SERIAL_EXCEL_MIN, _SERIAL_EXCEL_MAX = 36526, 73051  # 01/01/2000 a 01/01/2100
_EPOCA_EXCEL = date(1899, 12, 30)


def _criar(ano: int, mes: int, dia: int) -> date | None:
    try:
        d = date(ano, mes, dia)
    except ValueError:
        return None
    return d if 2000 <= ano <= 2100 else None


def data_do_nome(nome_arquivo: str) -> date | None:
    """Data no nome do arquivo: DDMMAAAA (padrão do servidor), DD_MM_AAAA, AAAAMMDD, DD-MM-AA..."""
    base = Path(nome_arquivo).stem
    for m in _RE_DIA_MES_ANO.finditer(base):
        d = _criar(int(m[3]), int(m[2]), int(m[1]))
        if d:
            return d
    for m in _RE_ANO_MES_DIA.finditer(base):
        d = _criar(int(m[1]), int(m[2]), int(m[3]))
        if d:
            return d
    for m in _RE_DIA_MES_ANO2.finditer(base):
        d = _criar(2000 + int(m[3]), int(m[2]), int(m[1]))
        if d:
            return d
    return None


def interpretar_valor(valor) -> date | None:
    """Data contida numa célula (data do Excel, texto DD/MM/AAAA ou AAAA-MM-DD, número serial)."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if _SERIAL_EXCEL_MIN <= valor < _SERIAL_EXCEL_MAX:
            return _EPOCA_EXCEL + timedelta(days=int(valor))
        return None
    if isinstance(valor, str):
        m = _RE_TEXTO_DMA.fullmatch(valor)
        if m:
            return _criar(int(m[3]), int(m[2]), int(m[1]))
        m = _RE_TEXTO_AMD.fullmatch(valor)
        if m:
            return _criar(int(m[1]), int(m[2]), int(m[3]))
    return None


def mais_frequente(datas: list[date]) -> tuple[date | None, int]:
    """(data mais frequente, quantas vezes apareceu). Empate: a mais recente."""
    if not datas:
        return None, 0
    contagem = Counter(datas)
    melhor = max(contagem, key=lambda d: (contagem[d], d))
    return melhor, contagem[melhor]


def ler_data_digitada(texto: str) -> date:
    """Data digitada pelo usuário (DD/MM/AAAA; aceita também - . espaço ou só os 8 dígitos)."""
    m = _RE_DIGITADA.fullmatch(texto or "")
    if m:
        dia, mes, ano = (m[1], m[2], m[3]) if m[1] else (m[4], m[5], m[6])
        d = _criar(int(ano), int(mes), int(dia))
        if d:
            return d
    raise ValueError("Data inválida. Use o formato DD/MM/AAAA, por exemplo 28/09/2026.")


def formatar(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def nome_pasta(d: date) -> str:
    """Atestados_DD_MM_AAAA, sempre com dia e mês de dois dígitos."""
    return f"Atestados_{d:%d_%m_%Y}"
