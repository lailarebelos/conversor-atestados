import pytest

from atestados import visual as v

FUNDO, BRANCO, BORDA = (242, 242, 242), (255, 255, 255), (204, 204, 204)


def test_cores_solidas_equivalem_as_transparencias_da_marca():
    # os mesmos valores calculados no Triagem Trainee (regra: nada de transparência)
    assert v.solido("#FFFFFF", 0.16, "#003418") == "#29543D"
    assert v.solido("#FFFFFF", 0.72, "#003418") == "#B8C6BE"
    assert v.solido("#78DE1F", 0.30, "#F2F2F2") == "#CDECB3"
    assert v.BARRA_CIRCULO == "#1F4C34"


def test_cartao_opaco_com_eco_do_l_e_borda_solida():
    img = v.superficie(200, 100, (16, 4, 16, 16), "#FFFFFF", "#F2F2F2", "#CCCCCC", (1, 1, 1, 1))
    assert img.mode == "RGB" and img.size == (200, 100)  # opaco: sem franjas escuras na tela
    assert img.getpixel((0, 0)) == FUNDO  # canto de 16 px: o fundo aparece
    assert img.getpixel((100, 50)) == BRANCO
    assert img.getpixel((100, 0)) == BORDA
    assert img.getpixel((198, 1)) != FUNDO  # canto de 4 px (o eco do "L"): quase reto


def test_carimbo_citrico_fino_em_cima_e_grosso_embaixo():
    citrico = (0x78, 0xDE, 0x1F)
    img = v.superficie(200, 100, (16, 4, 16, 16), "#FFFFFF", "#F2F2F2", v.VERDE_CITRICO, (1, 4, 4, 1))
    assert img.getpixel((100, 97)) == citrico and img.getpixel((197, 50)) == citrico
    assert img.getpixel((100, 2)) == BRANCO and img.getpixel((2, 50)) == BRANCO


def test_area_de_arrastar_tem_traco_e_vao():
    img = v.area_tracejada(300, 120, 16, v.REALCE, "#FFFFFF", v.VERDE_BANDEIRA, 2, 7, 5)
    linha = [img.getpixel((x, 1)) for x in range(40, 260)]
    proporcao = sum(1 for p in linha if p[1] < 200) / len(linha)
    assert 0.4 < proporcao < 0.8
    solida = v.area_tracejada(300, 120, 16, v.REALCE, "#FFFFFF", v.VERDE_BANDEIRA, 2, 7, 5, solida=True)
    assert all(solida.getpixel((x, 1))[1] < 200 for x in range(40, 260))


def test_barra_de_progresso_com_ponta_citrica():
    vazia = v.barra(200, 10, 0, "#FFFFFF", v.SUPERFICIE_MEDIA, v.VERDE_BANDEIRA)
    meia = v.barra(200, 10, 0.5, "#FFFFFF", v.SUPERFICIE_MEDIA, v.VERDE_BANDEIRA, v.VERDE_CITRICO)
    assert vazia.getpixel((50, 5)) == (232, 232, 232)
    assert meia.getpixel((50, 5)) == (1, 132, 68)
    assert meia.getpixel((150, 5)) == (232, 232, 232)
    assert meia.getpixel((95, 5)) == (0x78, 0xDE, 0x1F)


def test_canto_da_barra_lateral():
    canto = v.canto_arredondado(24, 1, v.VERDE_ESCURO, "#FFFFFF")
    assert canto.size == (24, 24)
    assert canto.getpixel((23, 0)) == BRANCO  # fora da curva: o branco do topo
    assert canto.getpixel((0, 23)) == (0, 52, 24)  # dentro: o Verde Escuro


@pytest.fixture(scope="module")
def fontes():
    tk = pytest.importorskip("tkinter")
    try:
        raiz = tk.Tk()
    except tk.TclError:
        pytest.skip("sem ambiente gráfico")
    raiz.withdraw()
    yield v.Fontes(raiz)
    raiz.destroy()


@pytest.fixture
def fonte(fontes):
    return fontes.pequeno


def test_caminho_longo_encurtado_no_meio(fonte):
    caminho = r"C:\Users\fulano\OneDrive - Empresa\Área de Trabalho\RH\Atestados\2026\Setembro"
    curto = v.encurtar_meio(caminho, fonte, 200)
    assert "…" in curto and fonte.measure(curto) <= 200
    assert curto.startswith("C:\\") and curto.endswith("o")
    assert v.encurtar_meio("C:\\RH", fonte, 200) == "C:\\RH"


def test_texto_encurtado_no_fim(fonte):
    assert v.encurtar_fim("atestado28092026 (2).XLSX", fonte, 60).endswith("…")
    assert v.encurtar_fim("curto", fonte, 200) == "curto"


def test_calibri_e_a_fonte(fontes):
    assert fontes.familia in ("Calibri", "Carlito", "Segoe UI")  # regra de 24/09/2026: Calibri
