"""Fluxo completo: analisar a planilha → reconstruir → validar → salvar → relatório.

Uma linha com problema nunca interrompe o lote: o que for possível é salvo com o sufixo
_VERIFICAR, o motivo vai para o relatório e a exportação segue.
"""
from __future__ import annotations

import csv
import os
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from . import datas, formatos, metadados, nomes
from .colunas import EstatisticaColuna, MapaColunas, decidir_colunas_base64, identificar_metadados
from .formatos import Problema
from .leitura import Linha, Planilha, celula_vazia, valor_texto
from .reconstrucao import (TAMANHO_MINIMO_BASE64, decodificar, limpar_fragmento, no_alfabeto,
                           parece_base64, separar_arquivos)

NOME_RELATORIO = "relatorio_exportacao.csv"
COLUNAS_RELATORIO = ["Linha da planilha", "Chapa", "Nome", "ID do atestado", "Arquivo gerado",
                     "Formato", "Status", "Motivo", "Localização (GPS) removida"]
OK, VERIFICAR, SEM_ARQUIVO = "OK", "VERIFICAR", "SEM ARQUIVO"
ORIGEM_NOME = "do nome do arquivo"
ORIGEM_FOTOS = "da data das fotos"
ORIGEM_HOJE = "data de hoje"
_PREFIXO_PARA_DATA = 200_000  # caracteres de base64 suficientes para chegar ao EXIF da foto

# progresso(atual, total ou None se indeterminado, texto)
Progresso = Callable[[int, Optional[int], str], None]


class ErroExportacao(Exception):
    """Erro que impede a exportação. A mensagem é própria para mostrar ao usuário."""


class PastaJaExiste(ErroExportacao):
    def __init__(self, pasta: Path):
        self.pasta = pasta
        super().__init__(f"A pasta {pasta.name} já existe em {pasta.parent}.")


class Cancelado(Exception):
    """O usuário cancelou a análise."""


@dataclass
class Analise:
    caminho: Path
    colunas: MapaColunas
    total_linhas: int  # linhas de dados (sem o cabeçalho e sem linhas vazias)
    linhas_com_imagem: int
    incompletas: int  # menores que o tamanho informado nas colunas TAMANHO_*
    data: date
    origem_data: str
    avisos: list[str]
    tempo: float


@dataclass
class ItemRelatorio:
    linha: int
    chapa: str
    nome: str
    id_atestado: str
    arquivo: str = ""
    formato: str = ""
    status: str = OK
    problemas: list[Problema] = field(default_factory=list)
    gps: str = metadados.GPS_AUSENTE

    def para_csv(self) -> list[str]:
        gps = {metadados.GPS_REMOVIDO: "sim", metadados.GPS_FALHOU: "não foi possível"}.get(self.gps, "")
        return [str(self.linha), self.chapa, self.nome, self.id_atestado, self.arquivo, self.formato,
                self.status, "; ".join(p.detalhe for p in self.problemas), gps]


@dataclass
class Resultado:
    pasta: Path
    relatorio: Path
    linhas: int
    arquivos_ok: int
    arquivos_verificar: int
    linhas_sem_arquivo: int
    gps_removido: int
    problemas: Counter  # categoria → quantidade
    cancelado: bool
    tempo: float
    itens: list[ItemRelatorio]


# ------------------------------------------------------------------ análise ---
def analisar(caminho, progresso: Progresso | None = None, cancelar: threading.Event | None = None,
             hoje: date | None = None) -> Analise:
    """Lê a planilha uma vez: acha as colunas, conta as linhas e sugere a data."""
    inicio = time.perf_counter()
    planilha = Planilha(caminho)
    _avisar(progresso, 0, None, "Lendo a planilha…")
    data_nome = datas.data_do_nome(planilha.caminho.name)
    mapa: MapaColunas | None = None
    estatisticas: dict[int, EstatisticaColuna] = {}
    linhas_lidas: list[tuple[dict[int, int], int | None, int | None]] = []
    prefixos_linhas: list[dict[int, str]] = []
    datas_coluna: list[date] = []

    for linha in planilha.linhas():
        _checar(cancelar)
        valores = linha.valores
        if all(celula_vazia(v) for v in valores):
            continue
        if mapa is None:
            mapa = _mapa_pelo_cabecalho(linha)
            if mapa.linha_cabecalho:
                continue
        excluidas = mapa.metadados()
        tamanhos: dict[int, int] = {}
        prefixos: dict[int, str] = {}
        guardado = 0
        for j, v in enumerate(valores):
            if j in excluidas or celula_vazia(v):
                continue
            est = estatisticas.setdefault(j, EstatisticaColuna())
            if not isinstance(v, str):
                est.tem_nao_texto = True
                continue
            limpo = limpar_fragmento(v)
            if not no_alfabeto(limpo):
                est.tem_texto_invalido = True
                continue
            if len(limpo) >= TAMANHO_MINIMO_BASE64:
                est.tem_base64_longo = True
            tamanhos[j] = len(limpo)
            if data_nome is None and guardado < _PREFIXO_PARA_DATA:
                prefixos[j] = limpo[:_PREFIXO_PARA_DATA - guardado]
                guardado += len(prefixos[j])
        linhas_lidas.append((tamanhos, _inteiro(_campo(valores, mapa.tamanho_bytes)),
                             _inteiro(_campo(valores, mapa.tamanho_base64))))
        prefixos_linhas.append(prefixos)
        if mapa.data is not None and mapa.data < len(valores):
            d = datas.interpretar_valor(valores[mapa.data])
            if d:
                datas_coluna.append(d)

    if mapa is None or not linhas_lidas:
        raise ErroExportacao("A planilha não tem linhas com dados.")
    mapa.base64 = decidir_colunas_base64(mapa, estatisticas)
    if not mapa.base64:
        raise ErroExportacao("Não encontrei imagens em base64 nesta planilha. Confira se é a planilha de atestados.")

    com_imagem = incompletas = 0
    for tamanhos, declarado_bytes, declarado_b64 in linhas_lidas:
        total_b64 = sum(tamanhos.get(j, 0) for j in mapa.base64)
        if not total_b64:
            continue
        com_imagem += 1
        if declarado_bytes:
            incompletas += total_b64 * 3 // 4 < declarado_bytes
        elif declarado_b64:
            incompletas += total_b64 < declarado_b64 - 2  # tolera o '=' final omitido

    data, origem = _sugerir_data(data_nome, datas_coluna, prefixos_linhas, mapa, hoje or date.today())
    avisos = []
    if incompletas:
        avisos.append(f"{_plural(incompletas, 'atestado veio incompleto', 'atestados vieram incompletos')} "
                      "na própria planilha (o sistema de origem cortou o arquivo). "
                      f"{'Ele será salvo' if incompletas == 1 else 'Eles serão salvos'} com _VERIFICAR no nome.")
    if len(linhas_lidas) - com_imagem:
        avisos.append(f"{_plural(len(linhas_lidas) - com_imagem, 'linha não tem imagem', 'linhas não têm imagem')}.")
    if mapa.chapa is None and mapa.nome is None and mapa.id_atestado is None:
        avisos.append("Não encontrei colunas de chapa, nome ou ID: os arquivos serão numerados (001, 002…).")
    return Analise(Path(caminho), mapa, len(linhas_lidas), com_imagem, incompletas, data, origem, avisos,
                   time.perf_counter() - inicio)


def _mapa_pelo_cabecalho(linha: Linha) -> MapaColunas:
    """A 1ª linha com valores é o cabeçalho, a não ser que já traga base64 (planilha sem cabeçalho)."""
    if any(isinstance(v, str) and parece_base64(limpar_fragmento(v)) for v in linha.valores):
        return MapaColunas()
    mapa = identificar_metadados([valor_texto(v).strip() for v in linha.valores])
    mapa.linha_cabecalho = linha.numero
    return mapa


def _sugerir_data(data_nome, datas_coluna, prefixos_linhas, mapa, hoje) -> tuple[date, str]:
    """Nome do arquivo → coluna de data → data em que as fotos foram tiradas → hoje."""
    if data_nome:
        return data_nome, ORIGEM_NOME
    d, _ = datas.mais_frequente(datas_coluna)
    if d:
        return d, f"da coluna {mapa.nome_coluna(mapa.data)}"
    datas_fotos = []
    for prefixos in prefixos_linhas:
        texto = "".join(prefixos[j] for j in mapa.base64 if j in prefixos)
        if texto:
            dados, _ = decodificar(texto[: len(texto) - len(texto) % 4])
            d = metadados.data_do_arquivo(dados)
            if d:
                datas_fotos.append(d)
    d, _ = datas.mais_frequente(datas_fotos)
    if d:
        return d, ORIGEM_FOTOS
    return hoje, ORIGEM_HOJE


# ---------------------------------------------------------------- exportação ---
def exportar(caminho, pasta_destino, data_planilha: date, analise: Analise | None = None,
             progresso: Progresso | None = None, cancelar: threading.Event | None = None,
             substituir: bool = False) -> Resultado:
    """Cria <pasta_destino>/Atestados_DD_MM_AAAA com um arquivo por linha e o relatório."""
    inicio = time.perf_counter()
    if analise is None:
        analise = analisar(caminho, progresso, cancelar)
    destino = Path(pasta_destino)
    if not destino.is_dir():
        raise ErroExportacao("A pasta de destino não existe. Escolha outra pasta.")
    pasta = destino / datas.nome_pasta(data_planilha)
    try:
        nomes.verificar_comprimento(pasta)
    except nomes.CaminhoLongoDemais as e:
        raise ErroExportacao(str(e)) from None
    if pasta.exists():
        if not substituir:
            raise PastaJaExiste(pasta)
        _limpar_exportacao_anterior(pasta)
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        relatorio = open(pasta / NOME_RELATORIO, "w", encoding="utf-8-sig", newline="")
    except OSError as e:
        raise ErroExportacao(f"Não foi possível gravar em {destino} ({type(e).__name__}). "
                             "Confira se a pasta existe e se você tem permissão.") from None

    mapa, total = analise.colunas, analise.total_linhas
    gerador = nomes.GeradorNomes(pasta, total)
    itens: list[ItemRelatorio] = []
    cancelado = False
    _avisar(progresso, 0, total, "Lendo a planilha…")
    with relatorio:
        escritor = csv.writer(relatorio, delimiter=";")
        escritor.writerow(COLUNAS_RELATORIO)
        sequencial = 0
        for linha in Planilha(caminho).linhas():
            if linha.numero <= mapa.linha_cabecalho or all(celula_vazia(v) for v in linha.valores):
                continue
            if cancelar is not None and cancelar.is_set():
                cancelado = True
                break
            sequencial += 1
            for item in _processar_linha(linha, sequencial, mapa, gerador, pasta):
                escritor.writerow(item.para_csv())
                itens.append(item)
            relatorio.flush()
            _avisar(progresso, sequencial, total, f"{sequencial} de {total}")
    return _resultado(pasta, itens, cancelado, time.perf_counter() - inicio)


def _processar_linha(linha: Linha, sequencial: int, mapa: MapaColunas,
                     gerador: nomes.GeradorNomes, pasta: Path) -> list[ItemRelatorio]:
    valores = linha.valores
    chapa, nome, ident = (_campo(valores, j) for j in (mapa.chapa, mapa.nome, mapa.id_atestado))

    def novo_item(status=OK, problema: Problema | None = None) -> ItemRelatorio:
        item = ItemRelatorio(linha.numero, chapa, nome, ident, status=status)
        if problema:
            item.problemas.append(problema)
        return item

    try:
        base = gerador.base(chapa, nome, ident, sequencial)
        fragmentos = [f for j in mapa.base64 if j < len(valores) for f in (limpar_fragmento(valores[j]),) if f]
        if not fragmentos:
            return [novo_item(SEM_ARQUIVO, Problema("linha sem imagem", "a linha não tem imagem (nenhum base64)"))]
        arquivos = separar_arquivos(fragmentos)
    except Exception as e:  # noqa: BLE001 - uma linha ruim não pode parar o lote
        return [novo_item(SEM_ARQUIVO, Problema("erro inesperado", f"erro inesperado ao ler a linha ({type(e).__name__})"))]

    declarado_bytes = _inteiro(_campo(valores, mapa.tamanho_bytes))
    declarado_b64 = _inteiro(_campo(valores, mapa.tamanho_base64))
    itens = []
    for parte, rec in enumerate(arquivos, start=1):
        item = novo_item()
        try:
            item.problemas.extend(rec.problemas)
            if len(arquivos) > 1:
                item.problemas.insert(0, Problema("mais de um arquivo na linha",
                                                  f"a linha tinha {len(arquivos)} arquivos; este é o {parte}º"))
            else:
                p = formatos.conferir_tamanho(len(rec.dados), rec.tamanho_base64, declarado_bytes, declarado_b64)
                if p:
                    item.problemas.append(p)
            dados = rec.dados
            formato = formatos.detectar_formato(dados)
            if formato is None:
                item.formato, extensao = "desconhecido", ".bin"
                item.problemas.append(Problema("formato não reconhecido", "formato de arquivo não reconhecido"))
            else:
                item.formato, extensao = formato.nome, formato.extensao
                dados = _sem_gps_e_validado(dados, formato, item)
            item.status = VERIFICAR if item.problemas else OK
            item.arquivo = gerador.nome_arquivo(base, extensao, verificar=bool(item.problemas),
                                                parte=parte if len(arquivos) > 1 else None)
            _gravar(pasta / item.arquivo, dados)
        except OSError as e:
            item.arquivo, item.status = "", SEM_ARQUIVO
            item.problemas.append(Problema("erro ao gravar", f"não foi possível gravar o arquivo ({type(e).__name__}); "
                                                             "confira o espaço em disco e as permissões da pasta"))
        except Exception as e:  # noqa: BLE001
            item.arquivo, item.status = "", SEM_ARQUIVO
            item.problemas.append(Problema("erro inesperado", f"erro inesperado ao processar o arquivo ({type(e).__name__})"))
        itens.append(item)
    return itens


def _sem_gps_e_validado(dados: bytes, formato: formatos.Formato, item: ItemRelatorio) -> bytes:
    """Zera o GPS e valida o resultado. Se a remoção estragar algo, mantém o original."""
    sem_gps, item.gps = metadados.remover_gps(dados, formato)
    problema = formatos.validar(sem_gps, formato)
    if problema and sem_gps is not dados and formatos.validar(dados, formato) is None:
        item.gps = metadados.GPS_FALHOU
        return dados
    if problema:
        item.problemas.append(problema)
    return sem_gps


def _gravar(destino: Path, dados: bytes) -> None:
    """Grava num arquivo temporário e renomeia: nunca fica um arquivo pela metade."""
    temporario = destino.with_name(destino.name + nomes.SUFIXO_TEMPORARIO)
    try:
        with open(temporario, "wb") as f:
            f.write(dados)
        os.replace(temporario, destino)
    except BaseException:
        try:
            temporario.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _limpar_exportacao_anterior(pasta: Path) -> None:
    """Apaga só o que a exportação anterior gerou (os arquivos listados no relatório antigo)."""
    relatorio = pasta / NOME_RELATORIO
    try:
        if relatorio.is_file():
            with open(relatorio, encoding="utf-8-sig", newline="") as f:
                leitor = csv.reader(f, delimiter=";")
                cabecalho = next(leitor, [])
                coluna = cabecalho.index("Arquivo gerado") if "Arquivo gerado" in cabecalho else None
                gerados = [r[coluna] for r in leitor if coluna is not None and coluna < len(r)]
            for nome in gerados:
                if nome and Path(nome).name == nome and nome not in (".", ".."):
                    alvo = pasta / nome
                    if alvo.is_file():
                        alvo.unlink()
            relatorio.unlink()
        for temporario in pasta.glob("*" + nomes.SUFIXO_TEMPORARIO):
            temporario.unlink()
    except PermissionError:
        raise ErroExportacao("Um arquivo da exportação anterior está aberto em outro programa "
                             "(por exemplo, o relatório no Excel). Feche-o e tente de novo.") from None
    except OSError as e:
        raise ErroExportacao(f"Não foi possível substituir a exportação anterior ({type(e).__name__}).") from None


def _resultado(pasta: Path, itens: list[ItemRelatorio], cancelado: bool, tempo: float) -> Resultado:
    com_arquivo = [i for i in itens if i.arquivo]
    return Resultado(
        pasta=pasta,
        relatorio=pasta / NOME_RELATORIO,
        linhas=len({i.linha for i in itens}),
        arquivos_ok=sum(1 for i in com_arquivo if i.status == OK),
        arquivos_verificar=sum(1 for i in com_arquivo if i.status == VERIFICAR),
        linhas_sem_arquivo=sum(1 for i in itens if i.status == SEM_ARQUIVO),
        gps_removido=sum(1 for i in itens if i.gps == metadados.GPS_REMOVIDO),
        problemas=Counter(p.categoria for i in itens for p in i.problemas),
        cancelado=cancelado,
        tempo=tempo,
        itens=itens,
    )


# ------------------------------------------------------------------ apoio ---
def _campo(valores: list, j: int | None) -> str:
    return valor_texto(valores[j]).strip() if j is not None and j < len(valores) else ""


def _inteiro(texto: str) -> int | None:
    t = texto.strip()
    if t.isdigit():
        return int(t)
    m = re.fullmatch(r"(\d+)[.,]0*", t)
    return int(m.group(1)) if m else None


def _avisar(progresso: Progresso | None, atual: int, total: int | None, texto: str) -> None:
    if progresso is not None:
        progresso(atual, total, texto)


def _checar(cancelar: threading.Event | None) -> None:
    if cancelar is not None and cancelar.is_set():
        raise Cancelado()


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"
