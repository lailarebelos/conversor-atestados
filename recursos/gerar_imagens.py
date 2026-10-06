"""Gera as imagens do programa a partir dos vetores oficiais da marca (recursos/marca/*.svg).

Roda só no desenvolvimento (precisa do resvg-py, listado em requirements-dev.txt):
    python recursos/gerar_imagens.py
Saídas: recursos/icone.ico, recursos/abertura.png, recursos/abertura_folhas.tcl e
recursos/ui/*.png. O executável só carrega os arquivos prontos. Os SVGs da marca nunca são
alterados: quando um desenho precisa de um tom mais discreto, a cor é trocada só na cópia em
memória (regra de 24/09/2026: cores sólidas, sem transparência).
"""
from __future__ import annotations

import base64
import io
import math
import re
from pathlib import Path

import resvg_py
from PIL import Image

AQUI = Path(__file__).resolve().parent
MARCA = AQUI / "marca"
UI = AQUI / "ui"

BANDEIRA, ESCURO, CITRICO, TINT = "#018444", "#003418", "#78DE1F", "#CEFDAF"
BRANCO, BORDA, APOIO_BARRA, TEXTO_BARRA = "#FFFFFF", "#CCCCCC", "#B8C6BE", "#EBEFED"
ESCALA_MAX = 4  # PNGs em 4x: nítidos até 400% de zoom de tela


def ler(nome: str) -> str:
    return (MARCA / f"{nome}.svg").read_text(encoding="utf-8")


def trocar_cores(svg: str, cores: dict[str, str]) -> str:
    for de, para in cores.items():
        svg = re.sub(re.escape(de), para, svg, flags=re.IGNORECASE)
    return svg


def _viewbox(svg: str) -> str:
    return re.search(r'viewBox="([^"]+)"', svg).group(1)


def _miolo(svg: str) -> str:
    return svg[svg.index(">", svg.index("<svg")) + 1:svg.rindex("</svg>")]


def embutir(svg: str, x: float, y: float, largura: float, altura: float) -> str:
    """Um SVG dentro de outro (logo, folha, grafismo), sem redesenhar nada. Os atributos de
    pintura da tag externa (ex.: fill="none" dos grafismos de contorno) vão junto."""
    raiz = svg[svg.index("<svg"):svg.index(">", svg.index("<svg"))]
    pintura = " ".join(re.findall(r'\b(?:fill|stroke)="[^"]*"', raiz))
    return (f'<svg x="{x}" y="{y}" width="{largura}" height="{altura}" viewBox="{_viewbox(svg)}">'
            f"<g {pintura}>{_miolo(svg)}</g></svg>")


def rasterizar(svg: str, largura: int | None = None, altura: int | None = None) -> Image.Image:
    dados = resvg_py.svg_to_bytes(svg_string=svg, width=largura, height=altura)
    return Image.open(io.BytesIO(bytes(dados))).convert("RGBA")


def recortar(imagem: Image.Image) -> Image.Image:
    return imagem.crop(imagem.getbbox())


def svg_folha(cor: str = CITRICO) -> str:
    """A folha do símbolo Localiza, sozinha (o "pixel de marca")."""
    d = re.search(r'<path d="([^"]+)" fill="#78DE1F"', ler("simbolo-localiza-principal")).group(1)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="22.6 0.2 13.9 19.1">'
            f'<path d="{d}" fill="{cor}"/></svg>')


# ------------------------------------------------------------------ ícone ---
def _retangulo(x, y, w, h, se, sd, id_, ie):
    """Retângulo com raio diferente em cada canto (sup-esq, sup-dir, inf-dir, inf-esq)."""
    return (f"M{x + se},{y} H{x + w - sd} A{sd},{sd} 0 0 1 {x + w},{y + sd} V{y + h - id_} "
            f"A{id_},{id_} 0 0 1 {x + w - id_},{y + h} H{x + ie} A{ie},{ie} 0 0 1 {x},{y + h - ie} "
            f"V{y + se} A{se},{se} 0 0 1 {x + se},{y} Z")


def svg_icone(detalhe: str) -> str:
    """Atestado que vira imagem: uma folha com uma foto, cujo sol é a folha da Localiza.

    detalhe: "minimo" (16-24 px), "medio" (30-48 px) ou "completo" (60 px ou mais)."""
    folha = svg_folha()
    if detalhe == "16":  # alinhado à grade de 16 px (1 px = 16 unidades): bordas nítidas
        pagina = (48, 32, 160, 192)
        moldura = (64, 48, 128, 112, 8)
        montes = "64,160 104,112 128,136 152,104 192,152 192,160"
        sol = (144, 52, 32, 44)
        linhas = []
    elif detalhe == "24":  # alinhado à grade de 24 px (1 px = 10,67 unidades)
        pagina = (53.33, 32, 149.33, 192)
        moldura = (74.67, 53.33, 106.67, 96, 10.67)
        montes = "74.67,149.33 106.67,106.67 128,128 149.33,98 181.33,138.67 181.33,149.33"
        sol = (149.33, 58, 26, 36)
        linhas = [(74.67, 170.67, 106.67, 10.67)]
    elif detalhe == "20":  # alinhado à grade de 20 px (1 px = 12,8 unidades)
        pagina = (38.4, 25.6, 179.2, 204.8)
        moldura = (51.2, 38.4, 153.6, 115.2, 12.8)
        montes = "51.2,153.6 96,102.4 121.6,128 147.2,96 204.8,147.2 204.8,153.6"
        sol = (150, 44, 32, 44)
        linhas = []
    else:  # 30 px ou mais: medidas em múltiplos de 16 (pixels inteiros em 32, 48, 64 e 256)
        pagina = (48, 32, 160, 192)
        moldura = (64, 48, 128, 96, 12)
        montes = "64,144 104,100 126,122 152,92 192,136 192,144"
        sol = (152, 56, 24, 33)
        linhas = [(64, 164, 128, 12), (64, 188, 80, 12)] if detalhe == "completo" else [(64, 168, 128, 16)]
    px, py, pw, ph = pagina
    mx, my, mw, mh, mr = moldura
    partes = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">',
        "<defs>",
        f'<linearGradient id="fundo" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{ESCURO}"/>'
        f'<stop offset="1" stop-color="{BANDEIRA}"/></linearGradient>',
        f'<clipPath id="foto"><rect x="{mx}" y="{my}" width="{mw}" height="{mh}" rx="{mr}"/></clipPath>',
        "</defs>",
        '<rect x="8" y="8" width="240" height="240" rx="58" fill="url(#fundo)"/>',
        # folha de papel com o eco do "L": canto superior esquerdo quase reto
        f'<path d="{_retangulo(px, py, pw, ph, 6, 24, 24, 24)}" fill="{BRANCO}"/>',
        f'<rect x="{mx}" y="{my}" width="{mw}" height="{mh}" rx="{mr}" fill="{TINT}"/>',
        f'<g clip-path="url(#foto)"><polygon points="{montes}" fill="{BANDEIRA}"/></g>',
        embutir(folha, *sol),
    ]
    for x, y, w, h in linhas:
        partes.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" fill="{BORDA}"/>')
    partes.append("</svg>")
    return "".join(partes)


TAMANHOS_ICONE = [16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 128, 256]


def gerar_icone() -> list[Image.Image]:
    imagens = []
    for t in TAMANHOS_ICONE:
        detalhe = {16: "16", 20: "20", 24: "24"}.get(t) or ("medio" if t <= 48 else "completo")
        imagens.append(rasterizar(svg_icone(detalhe), t, t))
    grande = imagens[-1]
    grande.save(AQUI / "icone.ico", format="ICO", sizes=[(t, t) for t in TAMANHOS_ICONE],
                append_images=imagens[:-1])
    return imagens


# --------------------------------------------------------- tela de abertura ---
# As três folhas ao lado de "Abrindo…" (medidas no desenho de 880x495). Elas não entram na
# imagem: o .exe as desenha por cima e as faz pular (veja TCL_FOLHAS, mais abaixo).
FOLHAS_X, FOLHAS_Y, FOLHA_LARGURA, FOLHA_ALTURA = (64, 88, 112), 404, 15, 21


def svg_abertura(largura: int = 880, altura: int = 495) -> str:
    """Tela que aparece enquanto o .exe se prepara (cores sólidas, sem transparência)."""
    logo = ler("localiza-co-horizontal-branco-e-citrico")
    eco = ler("grafismo-ampersand-contorno-citrico")
    fonte = "Calibri, Carlito, 'Segoe UI', sans-serif"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{largura}" height="{altura}" '
        f'viewBox="0 0 {largura} {altura}">'
        f'<rect width="{largura}" height="{altura}" fill="{ESCURO}"/>'
        # um só "&" da marca, em contorno cítrico, sangrando o canto de baixo à direita
        + embutir(eco, 548, 124, 400, 407)
        + embutir(logo, 64, 58, 196, 32)
        + f'<text x="62" y="212" font-family="{fonte}" font-size="58" font-weight="700" fill="{BRANCO}">'
          "Conversor de Atestados</text>"
        f'<text x="64" y="256" font-family="{fonte}" font-size="24" fill="{APOIO_BARRA}">'
        "Da planilha do sistema a um arquivo por colaborador</text>"
        f'<rect x="64" y="292" width="72" height="4" rx="2" fill="{CITRICO}"/>'
        f'<text x="146" y="421" font-family="{fonte}" font-size="21" fill="{TEXTO_BARRA}">'
          "Abrindo… isso leva alguns segundos</text>"
        "</svg>"
    )


# Pixels reais da tela de abertura (o .exe é "dpiAware": o Windows não a amplia). 16:9 como o
# desenho; 1120 px é cerca de 58% da largura de uma tela Full HD e ainda cabe numa de 1366x768.
TAMANHO_ABERTURA = (1120, 630)


def gerar_abertura() -> Image.Image:
    imagem = rasterizar(svg_abertura(), *TAMANHO_ABERTURA).convert("RGB")
    imagem.save(AQUI / "abertura.png", optimize=True)
    return imagem


# Script Tcl somado ao da tela de abertura do PyInstaller (ConversorAtestados.spec). Ele roda
# no próprio .exe enquanto o programa se descompacta: o mesmo pulinho do indicador da janela
# (ciclo de 1,2 s, uma folha 0,2 s depois da outra, meia senoide para cima e pausa). O tempo
# vem do relógio, então o ritmo não depende da taxa de quadros; se algo falhar, as folhas
# ficam paradas no lugar e a abertura continua normal.
TCL_FOLHAS = """
# Folhas da marca pulando enquanto o programa abre (gerado por recursos/gerar_imagens.py)
image create photo folha_abertura -data {@DADOS@}
set folhas_x {@XS@}
set folhas {}
foreach x $folhas_x {
    lappend folhas [.root.canvas create image $x @Y@ -image folha_abertura -anchor nw]
}
proc pular_folhas {inicio} {
    global folhas folhas_x
    set t [expr {([clock milliseconds] - $inicio) / 1000.0}]
    foreach item $folhas x $folhas_x atraso {0.0 0.2 0.4} {
        set fase [expr {fmod($t - $atraso + 12.0, 1.2) / 1.2}]
        set salto [expr {$fase < 0.5 ? sin($fase * 6.283185307179586) : 0.0}]
        .root.canvas coords $item $x [expr {round(@Y@ - @ALTURA_SALTO@ * $salto)}]
    }
    after 16 [list pular_folhas $inicio]
}
catch {pular_folhas [clock milliseconds]}
"""


def gerar_folhas_abertura() -> str:
    """A folha (sobre o Verde Escuro, opaca) e o script que a desenha e anima na abertura."""
    k = TAMANHO_ABERTURA[0] / 880
    lf, af = FOLHA_LARGURA * k, FOLHA_ALTURA * k
    tw, th = math.ceil(lf) + 2, math.ceil(af) + 2  # 1 px de folga em volta: bordas suaves inteiras
    ox, oy = (tw - lf) / 2, (th - af) / 2
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}" viewBox="0 0 {tw} {th}">'
           f'<rect width="{tw}" height="{th}" fill="{ESCURO}"/>' + embutir(svg_folha(), ox, oy, lf, af) + "</svg>")
    png = io.BytesIO()
    rasterizar(svg, tw, th).convert("RGB").save(png, format="PNG", optimize=True)
    script = (TCL_FOLHAS.replace("@DADOS@", base64.b64encode(png.getvalue()).decode("ascii"))
              .replace("@XS@", " ".join(str(round(x * k - ox)) for x in FOLHAS_X))
              .replace("@Y@", str(round(FOLHAS_Y * k - oy)))
              .replace("@ALTURA_SALTO@", f"{af / 2:.1f}"))  # metade da folha, como na janela
    (AQUI / "abertura_folhas.tcl").write_text(script, encoding="utf-8", newline="\n")
    return script


# ------------------------------------------------------- imagens da interface ---
def gerar_ui() -> list[str]:
    """PNGs em 4x do tamanho de uso; a interface reduz para o zoom da tela na hora."""
    UI.mkdir(exist_ok=True)
    itens = {
        "logo_barra": (ler("localiza-co-horizontal-branco-e-citrico"), 24),
        "selo_topo": (ler("lco-compacto-principal"), 30),
        "nuvem": (ler("passo1-enviar-nuvem-v3"), 44),
        "checklist": (ler("passo2-revisar-checklist-v2"), 44),
        "exportar": (ler("passo4-baixar-exportar-v2"), 24),
        "balao_check": (ler("balao-check"), 40),
        "balao_alerta": (ler("balao-alerta"), 40),
        "balao_info": (ler("balao-info"), 40),
        "folha": (svg_folha(), 16),
        # grafismo da barra lateral: o "&" num tom sólido discreto sobre o Verde Escuro
        "grafismo_barra": (trocar_cores(ler("grafismo-ampersand-contorno-citrico"), {CITRICO: "#2E6B3C"}), 300),
    }
    feitos = []
    for nome, (svg, altura) in itens.items():
        recortar(rasterizar(svg, altura=altura * ESCALA_MAX)).save(UI / f"{nome}.png", optimize=True)
        feitos.append(nome)
    return feitos


if __name__ == "__main__":
    print("interface:", ", ".join(gerar_ui()))
    print("ícone:", len(gerar_icone()), "tamanhos")
    gerar_abertura()
    gerar_folhas_abertura()
    print("abertura: %dx%d, com as folhas animadas" % TAMANHO_ABERTURA)
