"""Desempenho com uma planilha sintética do porte da real (~160 MB, 97 linhas, até 150 colunas).

Rode com:  pytest -m lento -s
"""
import ctypes
import io
import random
import time
from ctypes import wintypes

import pytest
from PIL import Image

import sintetico as s
from atestados import exportacao

pytestmark = pytest.mark.lento


def pico_de_memoria_mb() -> float:
    class Contadores(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    c = Contadores()
    c.cb = ctypes.sizeof(c)
    atual = ctypes.windll.kernel32.GetCurrentProcess
    atual.restype = wintypes.HANDLE
    info = ctypes.windll.psapi.GetProcessMemoryInfo
    info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Contadores), wintypes.DWORD]
    info(atual(), ctypes.byref(c), c.cb)
    return c.PeakWorkingSetSize / 1e6


def foto(largura, altura, semente):
    """Foto sintética com o número de pixels de uma foto de celular (custo real de decodificação)."""
    random.seed(semente)
    fundo = Image.linear_gradient("L").resize((largura, altura))
    ruido = Image.effect_noise((largura, altura), 8)
    buf = io.BytesIO()
    Image.merge("RGB", (fundo, ruido, fundo.transpose(Image.Transpose.FLIP_LEFT_RIGHT))).save(
        buf, "JPEG", quality=80, exif=s.exif(gps=semente % 5 == 0))
    return buf.getvalue()


@pytest.fixture(scope="module")
def planilha_grande(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("grande")
    bases = sorted((foto(*dim, semente=i) for i, dim in enumerate([(200, 150), (800, 600), (2000, 1500), (4000, 3000)])),
                   key=len)
    random.seed(42)
    # distribuição parecida com a real: fragmentos por linha de 2 a 150
    fragmentos = ([random.randint(2, 10) for _ in range(26)] + [random.randint(11, 50) for _ in range(15)]
                  + [random.randint(51, 100) for _ in range(20)] + [random.randint(101, 150) for _ in range(28)])
    random.shuffle(fragmentos)
    linhas, n = [], 0
    for i, nfr in enumerate(fragmentos):
        n += 1
        alvo = nfr * 24_000 - random.randint(100, 20_000)
        if i < 11:  # PDFs
            buf = io.BytesIO()
            Image.effect_noise((300 + 40 * i, 400 + 40 * i), 30).convert("RGB").save(buf, "PDF")
            dados = buf.getvalue()
        elif i < 15:  # PNGs
            buf = io.BytesIO()
            Image.effect_noise((500, 400), 30).convert("RGB").save(buf, "PNG")
            dados = buf.getvalue()
        else:
            base = max((b for b in bases if len(b) + 8 <= alvo), key=len, default=bases[0])
            dados = s.com_tamanho_exato(base, max(alvo, len(base)))
        linhas.append(s.linha(200000 + n, f"{n:06d}", f"PESSOA SINTETICA {n}", dados))
    for k in range(8):  # 8 arquivos maiores que o limite de 150 colunas (3,7 a 6,0 MB), cortados
        n += 1
        dados = s.com_tamanho_exato(bases[-1], 3_700_000 + k * 330_000)
        linhas.append(s.linha(200000 + n, f"{n:06d}", f"PESSOA CORTADA {n}", dados,
                              fragmentos=s.fatiar(s.b64(dados))[:150]))
    random.shuffle(linhas)
    t = time.perf_counter()
    caminho = s.planilha_padrao(pasta / "atestado11092026.xlsx", linhas)
    print(f"\n[planilha sintética] {caminho.stat().st_size / 1e6:.0f} MB, {len(linhas)} linhas, "
          f"gerada em {time.perf_counter() - t:.0f} s")
    return caminho


def test_planilha_do_porte_da_real(planilha_grande, tmp_path):
    t0 = time.perf_counter()
    analise = exportacao.analisar(planilha_grande)
    t1 = time.perf_counter()
    r = exportacao.exportar(planilha_grande, tmp_path, analise.data, analise=analise)
    t2 = time.perf_counter()
    print(f"[análise] {t1 - t0:.1f} s  |  [exportação] {t2 - t1:.1f} s  |  total {t2 - t0:.1f} s  |  "
          f"pico de memória do processo {pico_de_memoria_mb():.0f} MB")
    print(f"[resultado] OK {r.arquivos_ok}, VERIFICAR {r.arquivos_verificar}, sem arquivo {r.linhas_sem_arquivo}, "
          f"GPS removido {r.gps_removido}, motivos {dict(r.problemas)}")
    assert (analise.total_linhas, analise.incompletas) == (97, 8)
    assert (r.arquivos_ok, r.arquivos_verificar, r.linhas_sem_arquivo) == (89, 8, 0)
    assert r.problemas["incompleto na planilha"] == 8
    assert t2 - t0 < 300
