"""Quais colunas identificam o colaborador e quais trazem os pedaços do base64.

Nada é fixo: o número de linhas e de colunas muda todo dia. As colunas de identificação
são achadas pelo nome do cabeçalho; as de base64, pelo conteúdo, e sempre usadas na
ordem física (da esquerda para a direita), nunca pela ordem alfabética do cabeçalho.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from .leitura import valor_texto

_RE_NAO_ALFANUM = re.compile(r"[^A-Za-z0-9]+")
_RE_PREFIXO_NUMERADO = re.compile(r"(.*?)_?(\d+)")

_IDENTIFICADORES_ATESTADO = {"ID", "COD", "CODIGO", "NUM", "NUMERO", "NR", "NRO", "PROTOCOLO"}
_NOMES_ID_SOLTOS = {"ID", "PROTOCOLO", "ID_DOCUMENTO", "ID_ANEXO", "ID_REGISTRO"}
_NAO_E_NOME_DA_PESSOA = {"ARQUIVO", "MEDICO", "EMPRESA", "MAE", "PAI", "CLINICA", "HOSPITAL", "UNIDADE",
                         "GESTOR", "LIDER", "SUPERIOR", "CENTRO", "SOCIAL", "CID", "DOENCA",
                         "PROFISSIONAL", "CRM", "SETOR", "CARGO", "FILIAL", "DEPARTAMENTO", "DOCUMENTO"}
_NOME_PREFERIDO = {"COLABORADOR", "FUNCIONARIO", "EMPREGADO", "SOLICITANTE", "PACIENTE"}
_DATA = {"DATA", "DT", "DATE"}
_DATA_NAO_SERVE = {"NASCIMENTO", "NASC", "ADMISSAO", "ADMIS", "DEMISSAO", "DEMIS", "VALIDADE",
                   "INICIO", "FIM", "RETORNO", "AFASTAMENTO", "TERMINO"}
_DATA_PREFERIDA = {"ENVIO", "RECEBIMENTO", "RECEB", "INCLUSAO", "CADASTRO", "UPLOAD", "REGISTRO",
                   "SOLICITACAO", "ENTRADA", "CRIACAO", "ANEXO", "EMISSAO"}


def normalizar(texto) -> str:
    """'Matrícula do colaborador' → 'MATRICULA_DO_COLABORADOR'."""
    t = unicodedata.normalize("NFKD", valor_texto(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return _RE_NAO_ALFANUM.sub("_", t).strip("_").upper()


def prefixo_numerado(cabecalho_normalizado: str) -> str | None:
    """'IMG_PARTE001' → 'IMG_PARTE'; sem número no fim → None."""
    m = _RE_PREFIXO_NUMERADO.fullmatch(cabecalho_normalizado)
    return m.group(1) if m and m.group(1) else None


@dataclass
class MapaColunas:
    cabecalho: list[str] = field(default_factory=list)  # textos originais do cabeçalho
    linha_cabecalho: int = 0  # nº da linha do cabeçalho no Excel (0 = sem cabeçalho)
    id_atestado: int | None = None
    chapa: int | None = None
    nome: int | None = None
    empresa: int | None = None
    data: int | None = None
    tamanho_bytes: int | None = None
    tamanho_base64: int | None = None
    base64: list[int] = field(default_factory=list)  # índices, na ordem física

    def metadados(self) -> set[int]:
        return {j for j in (self.id_atestado, self.chapa, self.nome, self.empresa, self.data,
                            self.tamanho_bytes, self.tamanho_base64) if j is not None}

    def nome_coluna(self, j: int | None) -> str:
        if j is None:
            return ""
        return self.cabecalho[j] if j < len(self.cabecalho) and self.cabecalho[j] else f"coluna {j + 1}"


def _achar(normalizados, condicao, preferencias=()):
    candidatos = [j for j, n in enumerate(normalizados) if n and condicao(n, set(n.split("_")))]
    for pref in preferencias:
        for j in candidatos:
            n = normalizados[j]
            if pref(n, set(n.split("_"))):
                return j
    return candidatos[0] if candidatos else None


def identificar_metadados(cabecalho: list[str]) -> MapaColunas:
    """Acha as colunas de identificação, data e tamanhos pelo nome do cabeçalho."""
    n = [normalizar(c) for c in cabecalho]
    mapa = MapaColunas(cabecalho=list(cabecalho))
    mapa.id_atestado = _achar(n, lambda s, t: "ATESTADO" in t and bool(t & _IDENTIFICADORES_ATESTADO))
    if mapa.id_atestado is None:
        mapa.id_atestado = _achar(n, lambda s, t: s in _NOMES_ID_SOLTOS)
    mapa.chapa = _achar(n, lambda s, t: bool(t & {"CHAPA", "MATRICULA", "MATR"}))
    mapa.nome = _achar(
        n, lambda s, t: "NOME" in t and not t & _NAO_E_NOME_DA_PESSOA,
        preferencias=(lambda s, t: s == "NOME", lambda s, t: bool(t & _NOME_PREFERIDO)))
    mapa.empresa = _achar(n, lambda s, t: bool(t & {"EMPRESA", "COLIGADA"}) and "NOME" not in t)
    tamanho = lambda t: bool(t & {"TAMANHO", "TAM", "SIZE"})  # noqa: E731
    mapa.tamanho_base64 = _achar(n, lambda s, t: tamanho(t) and ("BASE64" in s or bool(t & {"CHARS", "CARACTERES"})))
    mapa.tamanho_bytes = _achar(n, lambda s, t: tamanho(t) and "BASE64" not in s and bool(t & {"BYTES", "ORIGINAL"}))
    mapa.data = _achar(n, lambda s, t: bool(t & _DATA) and not t & _DATA_NAO_SERVE,
                       preferencias=(lambda s, t: bool(t & _DATA_PREFERIDA),))
    return mapa


@dataclass
class EstatisticaColuna:
    tem_base64_longo: bool = False  # algum valor com cara de base64 (>= 64 caracteres)
    tem_texto_invalido: bool = False  # algum texto fora do alfabeto do base64
    tem_nao_texto: bool = False  # algum número/data (pedaço de base64 é sempre texto)


def decidir_colunas_base64(mapa: MapaColunas, estatisticas: dict[int, EstatisticaColuna]) -> list[int]:
    excluidas = mapa.metadados()
    longas = sorted(j for j, e in estatisticas.items() if e.tem_base64_longo and j not in excluidas)
    if not longas:
        return []
    # 1) Cabeçalho numerado (ex.: IMG_PARTE001…IMG_PARTE150): todas as colunas do padrão,
    #    inclusive as que hoje só têm o último pedaço, curto, ou estão vazias.
    normalizados = [normalizar(c) for c in mapa.cabecalho]
    prefixos = Counter(prefixo_numerado(normalizados[j]) for j in longas if j < len(normalizados))
    prefixos.pop(None, None)
    if prefixos:
        prefixo, quantas = prefixos.most_common(1)[0]
        if quantas >= 0.8 * len(longas):
            do_padrao = {j for j, c in enumerate(normalizados)
                         if j not in excluidas and prefixo_numerado(c) == prefixo}
            return sorted(do_padrao | set(longas))
    # 2) Sem padrão no cabeçalho: da 1ª coluna com base64 em diante, as colunas que só têm texto
    #    no alfabeto do base64.
    ultima = max(estatisticas)
    return [j for j in range(longas[0], ultima + 1) if j not in excluidas
            and not estatisticas.get(j, EstatisticaColuna()).tem_texto_invalido
            and not estatisticas.get(j, EstatisticaColuna()).tem_nao_texto]
