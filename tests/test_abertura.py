"""Tela de abertura do .exe: imagem de fundo + as três folhas animadas (recursos/abertura_folhas.tcl)."""
import base64
import io
import math
import re
from pathlib import Path

import pytest
from PIL import Image

RECURSOS = Path(__file__).resolve().parent.parent / "recursos"
ESCURO = (0x00, 0x34, 0x18)


@pytest.fixture(scope="module")
def folhas():
    script = (RECURSOS / "abertura_folhas.tcl").read_text(encoding="utf-8")
    dados = re.search(r"-data \{([A-Za-z0-9+/=]+)\}", script).group(1)
    xs = [int(x) for x in re.search(r"set folhas_x \{([\d ]+)\}", script).group(1).split()]
    y = int(re.search(r"create image \$x (\d+) ", script).group(1))
    salto = float(re.search(r"round\(\d+ - ([\d.]+) \* \$salto\)", script).group(1))
    return script, Image.open(io.BytesIO(base64.b64decode(dados))).convert("RGB"), xs, y, salto


def test_imagem_de_fundo_no_tamanho_real():
    assert Image.open(RECURSOS / "abertura.png").size == (1120, 630)


def test_folhas_so_passam_por_verde_escuro_liso(folhas):
    # a folha é opaca (sem transparência): o retângulo dela só pode andar sobre o fundo liso,
    # senão apagaria parte do desenho ou deixaria rastro
    _, folha, xs, y, salto = folhas
    fundo = Image.open(RECURSOS / "abertura.png").convert("RGB")
    l, a = folha.size
    assert all(folha.getpixel(p) == ESCURO for p in ((0, 0), (l - 1, 0), (0, a - 1), (l - 1, a - 1)))
    assert len(xs) == 3 and all(xs[i] + l < xs[i + 1] for i in range(2))  # não se sobrepõem
    regiao = fundo.crop((xs[0], y - math.ceil(salto), xs[-1] + l, y + a))
    assert regiao.getextrema() == tuple((c, c) for c in ESCURO)  # sem folhas paradas embaixo nem outro desenho
    assert folha.getextrema()[1][1] > 150  # e a folha cítrica está lá


def test_script_usa_o_canvas_da_abertura_do_pyinstaller(folhas):
    templates = pytest.importorskip("PyInstaller.building.splash_templates")
    assert ".root.canvas" in templates.splash_canvas_setup and ".root.canvas" in folhas[0]
    assert "catch {pular_folhas" in folhas[0]  # se algo falhar, as folhas só ficam paradas
