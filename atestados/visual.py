"""Peças visuais da interface, na identidade Localiza&CO.

Segue as regras de marca de 24/09/2026: fonte Calibri, cores sólidas (sem transparência),
sem sombras (borda sólida no lugar) e Verde Cítrico só como acento. O Tkinter não desenha
cantos arredondados suaves nem tracejados, então as superfícies (cartões, botões, área de
arrastar, barra de progresso, selos) são desenhadas com o Pillow — cantos em 4x, reduzidos —
e ficam nítidas em qualquer zoom de tela. Os textos continuam sendo do próprio Tk (ClearType).
"""
from __future__ import annotations

import math
import sys
import tkinter as tk
from functools import lru_cache
from pathlib import Path
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageTk

# ------------------------------------------------------------------ cores ---
VERDE_BANDEIRA = "#018444"   # ação principal, links, números, foco
VERDE_ESCURO = "#003418"     # barra lateral e o botão principal sob o mouse
VERDE_CITRICO = "#78DE1F"    # só acento: nunca texto, nunca fundo de área com texto
VERDE_TINT = "#CEFDAF"
FUNDO = "#F2F2F2"
SUPERFICIE = "#FFFFFF"
SUPERFICIE_MEDIA = "#E8E8E8"
TEXTO_SOBRE_MEDIA = "#575757"
BORDA_BAIXA = "#E6E6E6"
BORDA = "#CCCCCC"
TEXTO = "#4A4A4A"
TEXTO_APOIO = "#6E6E6E"
TEXTO_MINIMO = "#767676"
SUCESSO_FUNDO, SUCESSO_TEXTO = "#D1F5DC", "#003827"
ALERTA_FUNDO, ALERTA_TEXTO = "#FBE437", "#003418"
ERRO_FUNDO, ERRO_BORDA, ERRO_TEXTO, ERRO_FORTE = "#FFE4E4", "#FFD1D1", "#720D0D", "#D92020"
INFO_FUNDO, INFO_BORDA, INFO_TEXTO = "#D8EFFD", "#C0E6FC", "#0B4260"


def _rgb(cor: str) -> tuple[int, int, int]:
    cor = cor.lstrip("#")
    return tuple(int(cor[i:i + 2], 16) for i in (0, 2, 4))


def solido(frente: str, alfa: float, fundo: str) -> str:
    """A cor sólida que 'frente a alfa%' daria sobre 'fundo' (a regra é não usar transparência)."""
    f, b = _rgb(frente), _rgb(fundo)
    return "#" + "".join(f"{round(alfa * x + (1 - alfa) * y):02X}" for x, y in zip(f, b))


# barra lateral: tons sólidos sobre o Verde Escuro (os mesmos do Triagem Trainee)
BARRA_LINHA = solido("#FFFFFF", 0.16, VERDE_ESCURO)        # #29543D
BARRA_REALCE = solido("#FFFFFF", 0.10, VERDE_ESCURO)       # item ativo
BARRA_CIRCULO = solido("#FFFFFF", 0.12, VERDE_ESCURO)      # #1F4C34
BARRA_TEXTO_PENDENTE = solido("#FFFFFF", 0.55, VERDE_ESCURO)  # #8CA497
BARRA_APOIO = solido("#FFFFFF", 0.72, VERDE_ESCURO)         # #B8C6BE
BARRA_TEXTO = solido("#FFFFFF", 0.92, VERDE_ESCURO)         # #EBEFED
# realces sobre o branco
REALCE = solido(VERDE_BANDEIRA, 0.08, SUPERFICIE)           # fundo da área de arrastar
REALCE_FORTE = solido(VERDE_BANDEIRA, 0.13, SUPERFICIE)     # mouse por cima
REALCE_BORDA = solido(VERDE_BANDEIRA, 0.22, SUPERFICIE)
ARRASTANDO = solido(VERDE_CITRICO, 0.18, SUPERFICIE)        # planilha sendo arrastada

SUPER = 4  # supersampling dos cantos e traços


# ------------------------------------------------------------------ fontes ---
class Fontes:
    """Calibri em tudo (regra de 24/09/2026), com Carlito e Segoe UI de reserva."""

    def __init__(self, raiz: tk.Misc):
        disponiveis = set(raiz.tk.call("font", "families"))
        familia = next((f for f in ("Calibri", "Carlito", "Segoe UI") if f in disponiveis), "TkDefaultFont")
        self.familia = familia

        def f(tamanho, peso="normal"):
            return tkfont.Font(raiz, family=familia, size=tamanho, weight=peso)

        self.titulo_app = f(15, "bold")
        self.titulo = f(13, "bold")
        self.micro = f(8, "bold")
        self.corpo = f(11)
        self.corpo_negrito = f(11, "bold")
        self.pequeno = f(10)
        self.pequeno_negrito = f(10, "bold")
        self.botao = f(12, "bold")
        self.botao_menor = f(10, "bold")
        self.campo = f(14)
        self.selo = f(9, "bold")
        self.produto = f(13, "bold")
        self.numero = f(18, "bold")


def micro(texto: str) -> str:
    """Rótulo curto em caixa-alta com espaçamento entre letras (o Tk não tem letter-spacing)."""
    return "\u200a".join(texto.upper())


# --------------------------------------------------------------- desenhos ---
@lru_cache(maxsize=256)
def _canto(raio: int, qual: int) -> Image.Image:
    """Máscara suavizada de um canto arredondado (0 sup-esq, 1 sup-dir, 2 inf-dir, 3 inf-esq)."""
    s = raio * SUPER
    grande = Image.new("L", (2 * s, 2 * s), 0)
    ImageDraw.Draw(grande).ellipse((0, 0, 2 * s - 1, 2 * s - 1), fill=255)
    caixas = [(0, 0, s, s), (s, 0, 2 * s, s), (s, s, 2 * s, 2 * s), (0, s, s, 2 * s)]
    return grande.crop(caixas[qual]).reduce(SUPER)


def mascara(largura: int, altura: int, raios: tuple[float, float, float, float]) -> Image.Image:
    m = Image.new("L", (max(largura, 1), max(altura, 1)), 255)
    for qual, raio in enumerate(raios):
        r = int(round(min(raio, largura / 2, altura / 2)))
        if r <= 0:
            continue
        x = 0 if qual in (0, 3) else largura - r
        y = 0 if qual in (0, 1) else altura - r
        m.paste(_canto(r, qual), (x, y))
    return m


def superficie(largura: int, altura: int, raios, cor: str, fundo: str,
               borda: str | None = None, espessuras=(0, 0, 0, 0)) -> Image.Image:
    """Retângulo com raio próprio em cada canto e borda sólida (espessura por lado:
    cima, direita, baixo, esquerda). Sai opaco, já sobre a cor do fundo — sem franjas."""
    largura, altura = max(int(largura), 2), max(int(altura), 2)
    img = Image.new("RGB", (largura, altura), fundo)
    externa = mascara(largura, altura, raios)
    if borda and any(espessuras):
        cima, direita, baixo, esquerda = espessuras
        img.paste(_rgb(borda), (0, 0, largura, altura), externa)
        li, ai = largura - esquerda - direita, altura - cima - baixo
        if li > 0 and ai > 0:
            internos = (max(raios[0] - max(cima, esquerda), 0), max(raios[1] - max(cima, direita), 0),
                        max(raios[2] - max(baixo, direita), 0), max(raios[3] - max(baixo, esquerda), 0))
            img.paste(_rgb(cor), (esquerda, cima, esquerda + li, cima + ai), mascara(li, ai, internos))
    else:
        img.paste(_rgb(cor), (0, 0, largura, altura), externa)
    return img


def canto_arredondado(raio: int, qual: int, cor: str, fundo: str) -> Image.Image:
    """Só o canto (raio x raio): a cor por dentro da curva, o fundo por fora."""
    img = Image.new("RGB", (max(raio, 1), max(raio, 1)), fundo)
    img.paste(_rgb(cor), (0, 0, img.width, img.height), _canto(max(raio, 1), qual))
    return img


def _contorno(x0, y0, x1, y1, raio, passos=28) -> list[tuple[float, float]]:
    """Pontos do perímetro de um retângulo arredondado, no sentido horário."""
    pts = []
    for cx, cy, a0 in ((x0 + raio, y0 + raio, 180), (x1 - raio, y0 + raio, 270),
                       (x1 - raio, y1 - raio, 0), (x0 + raio, y1 - raio, 90)):
        for i in range(passos + 1):
            a = math.radians(a0 + 90 * i / passos)
            pts.append((cx + raio * math.cos(a), cy + raio * math.sin(a)))
    pts.append(pts[0])
    return pts


def area_tracejada(largura: int, altura: int, raio: float, cor: str, fundo: str, cor_traco: str,
                   espessura: float, traco: float, vao: float, solida: bool = False) -> Image.Image:
    """A área de arrastar: fundo claro com borda tracejada (ou sólida, ao arrastar)."""
    s = SUPER
    largura, altura = max(int(largura), 4), max(int(altura), 4)
    grande = Image.new("RGB", (largura * s, altura * s), fundo)
    d = ImageDraw.Draw(grande)
    d.rounded_rectangle((0, 0, largura * s - 1, altura * s - 1), radius=raio * s, fill=cor)
    e = espessura * s
    if solida:
        d.rounded_rectangle((0, 0, largura * s - 1, altura * s - 1), radius=raio * s, outline=cor_traco,
                            width=round(e))
        return grande.reduce(s)
    pts = _contorno(e / 2, e / 2, largura * s - e / 2, altura * s - e / 2, max(raio * s - e / 2, 0))
    padrao, desenhando, resta, atual = (traco * s, vao * s), True, traco * s, [pts[0]]
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        seg = math.hypot(xb - xa, yb - ya)
        pos = 0.0
        while seg - pos > 1e-6:
            passo = min(resta, seg - pos)
            pos += passo
            ponto = (xa + (xb - xa) * pos / seg, ya + (yb - ya) * pos / seg)
            if desenhando:
                atual.append(ponto)
            resta -= passo
            if resta <= 1e-6:
                if desenhando and len(atual) > 1:
                    d.line(atual, fill=cor_traco, width=round(e), joint="curve")
                desenhando = not desenhando
                resta = padrao[0] if desenhando else padrao[1]
                atual = [ponto]
    if desenhando and len(atual) > 1:
        d.line(atual, fill=cor_traco, width=round(e), joint="curve")
    return grande.reduce(s)


def barra(largura: int, altura: int, fracao: float, fundo: str, trilho: str, cor: str,
          ponta: str | None = None) -> Image.Image:
    """Barra de progresso em pílula; a ponta cítrica é o acento da marca."""
    s = SUPER
    largura, altura = max(int(largura), 4), max(int(altura), 2)
    grande = Image.new("RGB", (largura * s, altura * s), fundo)
    d = ImageDraw.Draw(grande)
    a = altura * s
    d.rounded_rectangle((0, 0, largura * s - 1, a - 1), radius=a / 2, fill=trilho)
    if fracao > 0:
        w = max(a, min(1.0, fracao) * largura * s)
        d.rounded_rectangle((0, 0, w - 1, a - 1), radius=a / 2, fill=cor)
        if ponta:
            m = a * 0.22
            d.ellipse((w - a + m, m, w - 1 - m, a - 1 - m), fill=ponta)
    return grande.reduce(s)


def circulo(diametro: int, cor: str, fundo: str, marca: str | None = None, cor_marca: str = "#FFFFFF") -> Image.Image:
    """Círculo das etapas; marca="check" desenha o visto de etapa concluída."""
    s = SUPER
    t = max(int(diametro), 2) * s
    grande = Image.new("RGB", (t, t), fundo)
    d = ImageDraw.Draw(grande)
    d.ellipse((0, 0, t - 1, t - 1), fill=cor)
    if marca == "check":
        d.line([(t * 0.29, t * 0.52), (t * 0.44, t * 0.66), (t * 0.72, t * 0.37)], fill=cor_marca,
               width=round(t * 0.09), joint="curve")
    return grande.reduce(s)


def encurtar_meio(texto: str, fonte: tkfont.Font, largura: int) -> str:
    """Encurta no meio (C:\\Users\\…\\Downloads) para caber em 'largura' pixels."""
    if fonte.measure(texto) <= largura or len(texto) < 6:
        return texto
    esq, dir_ = len(texto) // 2, len(texto) // 2
    while esq > 1 and fonte.measure(texto[:esq] + "…" + texto[-dir_:]) > largura:
        if esq >= dir_:
            esq -= 1
        else:
            dir_ -= 1
    return texto[:esq] + "…" + texto[-dir_:]


def encurtar_fim(texto: str, fonte: tkfont.Font, largura: int) -> str:
    if fonte.measure(texto) <= largura:
        return texto
    while len(texto) > 1 and fonte.measure(texto + "…") > largura:
        texto = texto[:-1]
    return texto.rstrip() + "…"


# --------------------------------------------------------------- imagens ---
def pasta_recursos() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "recursos"


class Imagens:
    """Carrega os PNGs da marca (gerados em 4x) e reduz para o tamanho da tela, com cache."""

    def __init__(self, escala: float):
        self.escala = escala
        self._cache: dict = {}
        self._originais: dict = {}

    def original(self, nome: str) -> Image.Image:
        if nome not in self._originais:
            self._originais[nome] = Image.open(pasta_recursos() / "ui" / f"{nome}.png").convert("RGBA")
        return self._originais[nome]

    def __call__(self, nome: str, altura: float, fundo: str | None = None) -> ImageTk.PhotoImage:
        chave = (nome, altura, fundo)
        if chave not in self._cache:
            img = self.original(nome)
            a = max(1, round(altura * self.escala))
            l = max(1, round(img.width * a / img.height))
            img = img.resize((l, a), Image.LANCZOS)
            if fundo:  # já composto sobre a cor de fundo: sem franjas
                base = Image.new("RGBA", img.size, fundo)
                base.alpha_composite(img)
                img = base.convert("RGB")
            self._cache[chave] = ImageTk.PhotoImage(img)
        return self._cache[chave]


# --------------------------------------------------------------- componentes ---
class Tela(tk.Canvas):
    """Canvas sem borda, com escala de tela e guarda das imagens desenhadas."""

    def __init__(self, mestre, ui: "Kit", fundo: str, **kw):
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("bd", 0)
        super().__init__(mestre, bg=fundo, **kw)
        self.ui, self.fundo = ui, fundo
        self._guardadas: dict[str, ImageTk.PhotoImage] = {}

    def px(self, n: float) -> int:
        return self.ui.px(n)

    def guardar(self, chave: str, imagem: Image.Image | ImageTk.PhotoImage) -> ImageTk.PhotoImage:
        foto = imagem if isinstance(imagem, ImageTk.PhotoImage) else ImageTk.PhotoImage(imagem)
        self._guardadas[chave] = foto
        return foto


class Kit:
    """Escala da tela + fontes + imagens, compartilhados por todos os componentes."""

    def __init__(self, raiz: tk.Misc):
        self.escala = max(raiz.winfo_fpixels("1i") / 96, 1.0)
        self.fontes = Fontes(raiz)
        self.imagens = Imagens(self.escala)

    def px(self, n: float) -> int:
        return int(round(n * self.escala))


class Cartao(tk.Frame):
    """Cartão branco com o eco do "L" (canto superior direito de 4 px) e borda sólida.

    O conteúdo vai em `interior` (um Frame branco); o desenho arredondado fica numa camada
    atrás dele, e o tamanho do cartão vem do próprio conteúdo. carimbo=True troca a borda pelo
    carimbo cítrico da marca: fino em cima e à esquerda, grosso embaixo e à direita."""

    RAIOS = (16, 4, 16, 16)

    def __init__(self, mestre, ui: Kit, fundo: str = FUNDO, margem: float = 18):
        super().__init__(mestre, bg=fundo)
        self.ui, self.fundo, self.carimbo = ui, fundo, False
        self.tela = Tela(self, ui, fundo, width=1, height=1)
        self.tela.place(x=0, y=0, relwidth=1, relheight=1)
        self.interior = tk.Frame(self, bg=SUPERFICIE)
        self.interior.pack(fill="both", expand=True, padx=ui.px(margem), pady=ui.px(margem))
        self.tk.call("lower", self.tela._w)  # o desenho fica atrás do conteúdo
        self.tela.bind("<Configure>", lambda e: self._redesenhar())

    def definir_carimbo(self, ativo: bool) -> None:
        if ativo != self.carimbo:
            self.carimbo = ativo
            self._redesenhar()

    def _redesenhar(self):
        t, px = self.tela, self.ui.px
        l, a = t.winfo_width(), t.winfo_height()
        if l < 4 or a < 4:
            return
        raios = tuple(px(r) for r in self.RAIOS)
        if self.carimbo:
            imagem = superficie(l, a, raios, SUPERFICIE, self.fundo, VERDE_CITRICO, (px(1), px(4), px(4), px(1)))
        else:
            imagem = superficie(l, a, raios, SUPERFICIE, self.fundo, BORDA, (max(1, px(1)),) * 4)
        t.delete("all")
        t.create_image(0, 0, image=t.guardar("fundo", imagem), anchor="nw")


class Botao(Tela):
    """Botão da marca. tipo: "primario" (Verde Bandeira), "secundario" (contorno verde).

    Aceita configure(state=...) e botao["state"] como um botão do Tk."""

    def __init__(self, mestre, ui: Kit, texto: str, comando, tipo: str = "primario", fundo: str = SUPERFICIE,
                 largura: float | None = None, altura: float = 46):
        self.tipo, self.texto, self.comando = tipo, texto, comando
        self.fonte = ui.fontes.botao if tipo == "primario" else ui.fontes.botao_menor
        self._altura_logica = altura
        self.anel = ui.px(3)  # espaço do contorno de foco
        l = ui.px(largura) if largura else self.fonte.measure(texto) + ui.px(48 if tipo == "primario" else 32)
        super().__init__(mestre, ui, fundo, width=l + 2 * self.anel, height=ui.px(altura) + 2 * self.anel,
                         takefocus=1, cursor="hand2")
        self._estado, self._sobre, self._pressionado, self._foco = "normal", False, False, False
        for ev, fn in (("<Enter>", lambda e: self._marcar(sobre=True)), ("<Leave>", lambda e: self._marcar(sobre=False)),
                       ("<ButtonPress-1>", lambda e: self._marcar(pressionado=True)), ("<ButtonRelease-1>", self._soltar),
                       ("<FocusIn>", lambda e: self._marcar(foco=True)), ("<FocusOut>", lambda e: self._marcar(foco=False)),
                       ("<KeyPress-space>", lambda e: self._acionar()), ("<KeyPress-Return>", lambda e: self._acionar()),
                       ("<Configure>", lambda e: self._desenhar())):
            self.bind(ev, fn)

    # interface de botão do Tk
    def configure(self, cnf=None, **kw):
        if "state" in kw:
            novo = str(kw.pop("state"))
            if novo != self._estado:
                self._estado = novo
                super().configure(cursor="hand2" if novo == "normal" else "arrow",
                                  takefocus=1 if novo == "normal" else 0)
                self._desenhar()
        if "text" in kw:
            novo = kw.pop("text")
            if novo != self.texto:
                self.texto = novo
                self._desenhar()
        if kw or cnf:
            return super().configure(cnf, **kw)
        return None

    config = configure

    def cget(self, chave):
        if chave == "state":
            return self._estado
        if chave == "text":
            return self.texto
        return super().cget(chave)

    def __getitem__(self, chave):
        return self.cget(chave)

    def _marcar(self, **mudancas):
        for k, v in mudancas.items():
            setattr(self, f"_{k}", v)
        self._desenhar()

    def _soltar(self, evento):
        dentro = 0 <= evento.x < self.winfo_width() and 0 <= evento.y < self.winfo_height()
        self._marcar(pressionado=False)
        if dentro:
            self._acionar()

    def _acionar(self):
        if self._estado == "normal" and self.comando:
            self.comando()

    def _cores(self):
        ativo = self._estado == "normal"
        if self.tipo == "primario":
            if not ativo:
                return SUPERFICIE_MEDIA, None, TEXTO_MINIMO
            return (VERDE_ESCURO if (self._sobre or self._pressionado) else VERDE_BANDEIRA), None, "#FFFFFF"
        if not ativo:
            return SUPERFICIE, BORDA, TEXTO_MINIMO
        return (REALCE_FORTE if self._pressionado else (REALCE if self._sobre else SUPERFICIE)), VERDE_BANDEIRA, VERDE_BANDEIRA

    def _desenhar(self):
        l, a = self.winfo_width(), self.winfo_height()
        if l < 4 or a < 4:
            l, a = int(self.cget("width")), int(self.cget("height"))
        g = self.anel
        cor, borda, cor_texto = self._cores()
        raio = self.px(8)
        imagem = Image.new("RGB", (l, a), self.fundo)
        if self._foco and self._estado == "normal":  # anel de foco: 2 px Verde Bandeira, afastado 1 px
            imagem.paste(superficie(l, a, (raio + g,) * 4, self.fundo, self.fundo, VERDE_BANDEIRA,
                                    (self.px(2),) * 4), (0, 0))
        imagem.paste(superficie(l - 2 * g, a - 2 * g, (raio,) * 4, cor, self.fundo, borda,
                                (max(1, self.px(1)),) * 4 if borda else (0, 0, 0, 0)), (g, g))
        self.delete("all")
        self.create_image(0, 0, image=self.guardar("fundo", imagem), anchor="nw")
        self.create_text(l / 2, a / 2, text=self.texto, font=self.fonte, fill=cor_texto)


class Selo(Tela):
    """Pílula de status (badge)."""

    CORES = {"aguardando": (VERDE_TINT, VERDE_ESCURO), "processando": (INFO_FUNDO, INFO_TEXTO),
             "pronto": (SUCESSO_FUNDO, SUCESSO_TEXTO), "atencao": (ALERTA_FUNDO, ALERTA_TEXTO),
             "erro": (ERRO_FUNDO, ERRO_TEXTO), "neutro": (SUPERFICIE_MEDIA, TEXTO_SOBRE_MEDIA)}

    def __init__(self, mestre, ui: Kit, fundo: str = SUPERFICIE):
        super().__init__(mestre, ui, fundo, width=1, height=ui.px(24))
        self.texto, self.tipo = "", "aguardando"

    def definir(self, texto: str, tipo: str) -> None:
        if (texto, tipo) == (self.texto, self.tipo) and self.find_all():
            return
        self.texto, self.tipo = texto, tipo
        fonte = self.ui.fontes.selo
        l, a = fonte.measure(texto) + self.px(22), self.px(24)
        cor, cor_texto = self.CORES[tipo]
        self.configure(width=l, height=a)
        self.delete("all")
        self.create_image(0, 0, image=self.guardar("fundo", superficie(l, a, (a / 2,) * 4, cor, self.fundo)),
                          anchor="nw")
        self.create_text(l / 2, a / 2, text=texto, font=fonte, fill=cor_texto)


class Folhas(Tela):
    """Indicador de carregamento da marca: três folhas cítricas do símbolo, pulando em sequência."""

    def __init__(self, mestre, ui: Kit, fundo: str):
        self.tam = 14
        super().__init__(mestre, ui, fundo, width=ui.px(3 * 14 + 2 * 8), height=ui.px(14 + 8))
        self._fotos = ui.imagens("folha", self.tam, fundo)
        self._itens = [self.create_image(ui.px(i * 22), ui.px(8), image=self._fotos, anchor="nw") for i in range(3)]
        self._rodando, self._t = False, 0.0

    def iniciar(self):
        if not self._rodando:
            self._rodando = True
            self._passo()

    def parar(self):
        self._rodando = False

    def _passo(self):
        if not self._rodando or not self.winfo_exists():
            return
        self._t += 0.033
        for i, item in enumerate(self._itens):
            fase = (self._t - i * 0.2) % 1.2 / 1.2
            salto = max(0.0, math.sin(fase * 2 * math.pi)) if fase < 0.5 else 0.0
            self.coords(item, self.px(i * 22), self.px(8) - self.px(7) * salto)
        self.after(33, self._passo)


class BarraProgresso(Tela):
    """Barra de progresso em pílula, com movimento suave até o valor novo."""

    def __init__(self, mestre, ui: Kit, fundo: str = SUPERFICIE, altura: float = 10):
        super().__init__(mestre, ui, fundo, height=ui.px(altura), width=1)
        self._alvo = self._atual = 0.0
        self._animando = False
        self.bind("<Configure>", lambda e: self._desenhar())

    def definir(self, fracao: float, imediato: bool = False) -> None:
        self._alvo = max(0.0, min(1.0, fracao))
        if imediato:
            self._atual = self._alvo
            self._desenhar()
        elif not self._animando:
            self._animando = True
            self._animar()

    def _animar(self):
        if not self.winfo_exists():
            return
        dif = self._alvo - self._atual
        if abs(dif) < 0.002:
            self._atual, self._animando = self._alvo, False
        else:
            self._atual += dif * 0.25
        self._desenhar()
        if self._animando:
            self.after(16, self._animar)

    def _desenhar(self):
        l, a = self.winfo_width(), self.winfo_height()
        if l < 8:
            return
        self.delete("all")
        imagem = barra(l, a, self._atual, self.fundo, SUPERFICIE_MEDIA, VERDE_BANDEIRA,
                       VERDE_CITRICO if self._atual > 0 else None)
        self.create_image(0, 0, image=self.guardar("barra", imagem), anchor="nw")


class ZonaArrastar(Tela):
    """Área para arrastar ou clicar e escolher a planilha (borda tracejada Verde Bandeira).

    estado: "vazio" | "analisando" | "carregado" | "erro"."""

    def __init__(self, mestre, ui: Kit, comando, fundo: str = SUPERFICIE, altura: float = 132,
                 altura_compacta: float = 64):
        self.anel = ui.px(3)
        self.altura_cheia = ui.px(altura) + 2 * self.anel
        self.altura_compacta = ui.px(altura_compacta) + 2 * self.anel
        super().__init__(mestre, ui, fundo, width=1, height=self.altura_cheia, takefocus=1, cursor="hand2")
        self.comando = comando
        self.estado, self.titulo, self.subtitulo = "vazio", "", ""
        self._sobre = self._arrastando = self._foco = self._bloqueada = False
        self.folhas = Folhas(self, ui, REALCE)
        self._janela_folhas = None
        self._fundos: dict = {}  # desenhos já feitos (o tracejado custa caro): por tamanho e estado
        for ev, fn in (("<Enter>", lambda e: self._marcar(sobre=True)), ("<Leave>", lambda e: self._marcar(sobre=False)),
                       ("<FocusIn>", lambda e: self._marcar(foco=True)), ("<FocusOut>", lambda e: self._marcar(foco=False)),
                       ("<ButtonRelease-1>", lambda e: self._acionar()), ("<KeyPress-space>", lambda e: self._acionar()),
                       ("<KeyPress-Return>", lambda e: self._acionar()), ("<Configure>", lambda e: self._desenhar())):
            self.bind(ev, fn)

    def definir(self, estado: str, titulo: str = "", subtitulo: str = "") -> None:
        """'carregado' vira um chip compacto do arquivo (como no Refinador); os outros usam a área cheia."""
        self.estado, self.titulo, self.subtitulo = estado, titulo, subtitulo
        if estado == "analisando":
            self.folhas.iniciar()
        else:
            self.folhas.parar()
        altura = self.altura_compacta if estado == "carregado" else self.altura_cheia
        if int(self.cget("height")) != altura:
            self.configure(height=altura)
        self._desenhar()

    def bloquear(self, sim: bool) -> None:
        if sim == self._bloqueada:
            return
        self._bloqueada = sim
        self.configure(cursor="arrow" if sim else "hand2", takefocus=0 if sim else 1)
        self._desenhar()

    def arrastando(self, sim: bool) -> None:
        self._marcar(arrastando=sim and not self._bloqueada)

    def _marcar(self, **mudancas):
        for k, v in mudancas.items():
            setattr(self, f"_{k}", v)
        self._desenhar()

    def _acionar(self):
        if not self._bloqueada and self.comando:
            self.comando()

    def _desenhar(self):
        l, a = self.winfo_width(), self.winfo_height()
        if l < 20 or a < 20:
            return
        g, f, ui = self.anel, self.ui.fontes, self.ui
        li, ai = l - 2 * g, a - 2 * g
        chip = self.estado == "carregado" and not self._arrastando
        mais_forte = self._sobre and not self._bloqueada and self.estado != "analisando"
        if self._arrastando:
            fundo_area, traco, solida = ARRASTANDO, VERDE_BANDEIRA, True
        elif self.estado == "erro":
            fundo_area, traco, solida = ERRO_FUNDO, ERRO_FORTE, False
        elif chip:  # chip do arquivo: borda sólida fina, raio 12
            fundo_area, traco, solida = (REALCE_FORTE if mais_forte else REALCE), REALCE_BORDA, True
        else:
            fundo_area, traco, solida = (REALCE_FORTE if mais_forte else REALCE), VERDE_BANDEIRA, False
        foco = self._foco and not self._bloqueada
        chave = (l, a, fundo_area, traco, solida, foco, chip)
        if chave not in self._fundos:
            raio = self.px(12 if chip else 16)
            imagem = Image.new("RGB", (l, a), self.fundo)
            if foco:
                imagem.paste(superficie(l, a, (raio + g,) * 4, self.fundo, self.fundo, VERDE_BANDEIRA,
                                        (self.px(2),) * 4), (0, 0))
            espessura = max(1.0, ui.escala * (1 if chip else 2))
            imagem.paste(area_tracejada(li, ai, raio, fundo_area, self.fundo, traco, espessura,
                                        ui.px(7), ui.px(5), solida), (g, g))
            if len(self._fundos) > 12:
                self._fundos.clear()
            self._fundos[chave] = ImageTk.PhotoImage(imagem)
        self.delete("all")  # apaga também a janela das folhas, que é recriada abaixo se preciso
        self._janela_folhas = None
        self.create_image(0, 0, image=self._fundos[chave], anchor="nw")
        cx, largura_texto = l / 2, li - self.px(40)
        espaco_corpo, espaco_pequeno = f.corpo.metrics("linespace"), f.pequeno.metrics("linespace")
        if chip:
            self._sem_folhas()
            x = g + self.px(16)
            self.create_image(x, a / 2, image=ui.imagens("checklist", 30, fundo_area), anchor="w")
            x += self.px(30) + self.px(14)
            trocar = "Trocar"
            largura_trocar = f.pequeno_negrito.measure(trocar)
            self.create_text(l - g - self.px(18), a / 2, text=trocar, font=f.pequeno_negrito,
                             fill=VERDE_BANDEIRA, anchor="e")
            livre = l - g - self.px(18) - largura_trocar - self.px(16) - x
            topo = (a - espaco_corpo - espaco_pequeno) / 2
            self.create_text(x, topo, text=encurtar_fim(self.titulo, f.corpo_negrito, livre), anchor="nw",
                             font=f.corpo_negrito, fill=TEXTO)
            self.create_text(x, topo + espaco_corpo, text=encurtar_fim(self.subtitulo, f.pequeno, livre),
                             anchor="nw", font=f.pequeno, fill=TEXTO_APOIO)
            return
        if self.estado == "vazio":
            self._sem_folhas()
            topo = (a - (self.px(44) + self.px(10) + espaco_corpo + self.px(4) + espaco_pequeno)) / 2
            self.create_image(cx, topo, image=ui.imagens("nuvem", 44, fundo_area), anchor="n")
            y = topo + self.px(44) + self.px(10)
            parte1, parte2 = "Arraste a planilha do dia", " ou clique para escolher"
            w1, w2 = f.corpo_negrito.measure(parte1), f.corpo.measure(parte2)
            x0 = cx - (w1 + w2) / 2
            self.create_text(x0, y, text=parte1, font=f.corpo_negrito, fill=TEXTO, anchor="nw")
            self.create_text(x0 + w1, y, text=parte2, font=f.corpo, fill=TEXTO, anchor="nw")
            self.create_text(cx, y + espaco_corpo + self.px(4), anchor="n", fill=TEXTO_MINIMO,
                             text="Arquivo .xlsx ou .csv exportado do sistema", font=f.pequeno)
            return
        if self.estado == "analisando":
            topo = (a - (self.px(22) + self.px(12) + espaco_corpo + self.px(2) + espaco_pequeno)) / 2
            self.folhas.configure(bg=fundo_area)
            self._janela_folhas = self.create_window(cx, topo, window=self.folhas, anchor="n")
            y = topo + self.px(22) + self.px(12)
        else:
            self._sem_folhas()
            nome_icone, alt = ("checklist", 40) if self.estado == "carregado" else ("balao_alerta", 34)
            topo = (a - (self.px(alt) + self.px(10) + espaco_corpo + self.px(2) + espaco_pequeno)) / 2
            self.create_image(cx, topo, image=ui.imagens(nome_icone, alt, fundo_area), anchor="n")
            y = topo + self.px(alt) + self.px(10)
        erro = self.estado == "erro"
        self.create_text(cx, y, text=encurtar_fim(self.titulo, f.corpo_negrito, largura_texto), anchor="n",
                         font=f.corpo_negrito, fill=ERRO_TEXTO if erro else TEXTO)
        self.create_text(cx, y + espaco_corpo + self.px(2), anchor="n", font=f.pequeno,
                         text=encurtar_fim(self.subtitulo, f.pequeno, largura_texto),
                         fill=ERRO_TEXTO if erro else TEXTO_APOIO)

    def _sem_folhas(self):
        if self._janela_folhas is not None:
            self.delete(self._janela_folhas)
            self._janela_folhas = None


class Campo(Tela):
    """Campo de texto arredondado; o contorno vira Verde Bandeira (2 px) no foco e vermelho no erro."""

    def __init__(self, mestre, ui: Kit, variavel: tk.StringVar, caracteres: int = 10, fundo: str = SUPERFICIE,
                 altura: float = 42):
        super().__init__(mestre, ui, fundo, height=ui.px(altura), cursor="xterm")
        self.entrada = tk.Entry(self, textvariable=variavel, font=ui.fontes.campo, width=caracteres, relief="flat",
                                bd=0, bg=SUPERFICIE, fg=TEXTO, insertbackground=VERDE_BANDEIRA, highlightthickness=0,
                                disabledbackground=SUPERFICIE, disabledforeground=TEXTO_MINIMO,
                                selectbackground=VERDE_TINT, selectforeground=VERDE_ESCURO)
        self.configure(width=self.entrada.winfo_reqwidth() + ui.px(28))
        self.create_window(ui.px(14), ui.px(altura) / 2, window=self.entrada, anchor="w")
        self.erro = self._foco = False
        self.entrada.bind("<FocusIn>", lambda e: self._marcar(True), add="+")
        self.entrada.bind("<FocusOut>", lambda e: self._marcar(False), add="+")
        self.bind("<Button-1>", lambda e: self.entrada.focus_set())
        self.bind("<Configure>", lambda e: self._desenhar())

    def definir_erro(self, sim: bool) -> None:
        if sim != self.erro:
            self.erro = sim
            self._desenhar()

    def _marcar(self, foco: bool):
        self._foco = foco
        self._desenhar()

    def _desenhar(self):
        l, a = self.winfo_width(), self.winfo_height()
        if l < 8:
            return
        cor = ERRO_FORTE if self.erro else (VERDE_BANDEIRA if self._foco else BORDA)
        esp = (self.px(2) if (self.erro or self._foco) else max(1, self.px(1)),) * 4
        self.delete("fundo")
        imagem = superficie(l, a, (self.px(8),) * 4, SUPERFICIE, self.fundo, cor, esp)
        self.create_image(0, 0, image=self.guardar("fundo", imagem), anchor="nw", tags="fundo")
        self.tag_lower("fundo")


class Dica:
    """Balão de dica que aparece ao parar o mouse sobre um componente."""

    def __init__(self, alvo: tk.Misc, ui: Kit, texto_atual):
        self.alvo, self.ui, self.texto_atual = alvo, ui, texto_atual
        self._janela: tk.Toplevel | None = None
        self._agendada = None
        alvo.bind("<Enter>", self._agendar, add="+")
        alvo.bind("<Leave>", self._esconder, add="+")
        alvo.bind("<ButtonPress>", self._esconder, add="+")

    def _agendar(self, _evento=None):
        self._esconder()
        self._agendada = self.alvo.after(450, self._mostrar)

    def _mostrar(self):
        texto = self.texto_atual()
        if not texto:
            return
        x = self.alvo.winfo_rootx()
        y = self.alvo.winfo_rooty() + self.alvo.winfo_height() + self.ui.px(6)
        self._janela = janela = tk.Toplevel(self.alvo)
        janela.wm_overrideredirect(True)
        janela.configure(bg=BORDA)
        tk.Label(janela, text=texto, font=self.ui.fontes.pequeno, fg="#FFFFFF", bg=VERDE_ESCURO,
                 padx=self.ui.px(10), pady=self.ui.px(6), justify="left",
                 wraplength=self.ui.px(420)).pack()
        janela.wm_geometry(f"+{x}+{y}")

    def _esconder(self, _evento=None):
        if self._agendada:
            self.alvo.after_cancel(self._agendada)
            self._agendada = None
        if self._janela is not None:
            self._janela.destroy()
            self._janela = None


class CaixaCaminho(Tela):
    """Mostra a pasta de destino, encurtada no meio se for longa (o caminho inteiro aparece na dica)."""

    def __init__(self, mestre, ui: Kit, variavel: tk.StringVar, fundo: str = SUPERFICIE, altura: float = 40):
        super().__init__(mestre, ui, fundo, height=ui.px(altura), width=1)
        self.variavel = variavel
        self.encurtado = False
        variavel.trace_add("write", lambda *_: self._desenhar())
        self.bind("<Configure>", lambda e: self._desenhar())
        self.dica = Dica(self, ui, lambda: self.variavel.get() if self.encurtado else "")

    def _desenhar(self):
        l, a = self.winfo_width(), self.winfo_height()
        if l < 8:
            return
        f, valor = self.ui.fontes.pequeno, self.variavel.get()
        self.delete("all")
        imagem = superficie(l, a, (self.px(8),) * 4, FUNDO, self.fundo, BORDA_BAIXA, (max(1, self.px(1)),) * 4)
        self.create_image(0, 0, image=self.guardar("fundo", imagem), anchor="nw")
        texto = valor or "Pasta da planilha"
        exibido = encurtar_meio(texto, f, l - self.px(24))
        self.encurtado = bool(valor) and exibido != texto
        self.create_text(self.px(12), a / 2, anchor="w", font=f, fill=TEXTO if valor else TEXTO_MINIMO,
                         text=exibido)


class Link(tk.Label):
    """Texto clicável em Verde Bandeira, sublinhado sob o mouse; também responde ao teclado."""

    def __init__(self, mestre, ui: Kit, texto: str, comando, fundo: str = SUPERFICIE):
        self.fonte = tkfont.Font(mestre, font=ui.fontes.pequeno_negrito)
        self.fonte_sublinhada = tkfont.Font(mestre, font=ui.fontes.pequeno_negrito)
        self.fonte_sublinhada.configure(underline=True)
        anel = max(2, ui.px(1.5))  # contorno + folga = o mesmo recuo dos botões: o texto alinha com eles
        super().__init__(mestre, text=texto, font=self.fonte, fg=VERDE_BANDEIRA, bg=fundo, cursor="hand2",
                         takefocus=1, padx=max(0, ui.px(3) - anel), highlightthickness=anel,
                         highlightbackground=fundo, highlightcolor=VERDE_BANDEIRA)
        self.fundo, self.comando, self.ativo = fundo, comando, True
        self.bind("<Enter>", lambda e: self.ativo and self.configure(font=self.fonte_sublinhada))
        self.bind("<Leave>", lambda e: self.configure(font=self.fonte))
        # contorno de foco (teclado) desenhado à mão: no Windows o Tk não o desenha em rótulos
        self.bind("<FocusIn>", lambda e: self.configure(highlightbackground=VERDE_BANDEIRA))
        self.bind("<FocusOut>", lambda e: self.configure(highlightbackground=self.fundo))
        for evento in ("<Button-1>", "<Return>", "<space>"):
            self.bind(evento, lambda e: self.ativo and self.comando())

    def habilitar(self, sim: bool) -> None:
        """Desabilitado fica cinza e sem a mãozinha (como o botão que ele substitui)."""
        if sim != self.ativo:
            self.ativo = sim
            self.configure(fg=VERDE_BANDEIRA if sim else TEXTO_MINIMO, cursor="hand2" if sim else "arrow",
                           font=self.fonte, takefocus=1 if sim else 0)


class Aviso(Tela):
    """Caixa de aviso da casa, com o balão de fala da marca. tipo: atencao | erro | info | ok."""

    TIPOS = {"atencao": (ALERTA_FUNDO, ALERTA_FUNDO, ALERTA_TEXTO, "balao_alerta"),
             "erro": (ERRO_FUNDO, ERRO_BORDA, ERRO_TEXTO, "balao_alerta"),
             "info": (INFO_FUNDO, INFO_BORDA, INFO_TEXTO, "balao_info"),
             "ok": (SUCESSO_FUNDO, SUCESSO_FUNDO, SUCESSO_TEXTO, "balao_check")}

    def __init__(self, mestre, ui: Kit, fundo: str = SUPERFICIE):
        super().__init__(mestre, ui, fundo, height=1, width=1)
        self.texto, self.tipo = "", "atencao"
        self.bind("<Configure>", lambda e: self._desenhar())

    def definir(self, texto: str, tipo: str = "atencao") -> None:
        self.texto, self.tipo = texto, tipo
        self._desenhar()

    def _desenhar(self):
        l = self.winfo_width()
        if l < 40 or not self.texto:
            return
        cor, borda, cor_texto, icone = self.TIPOS[self.tipo]
        f, pad, tam = self.ui.fontes.pequeno, self.px(12), 22
        self.delete("all")
        x_texto = pad + self.px(tam) + self.px(10)
        texto = self.create_text(x_texto, pad, anchor="nw", font=f, fill=cor_texto, text=self.texto,
                                 width=l - x_texto - pad)
        _, y0, _, y1 = self.bbox(texto)
        a = max(y1 - y0, self.px(tam)) + 2 * pad
        if abs(int(self.cget("height")) - a) > 1:
            self.configure(height=a)
        fundo = superficie(l, a, (self.px(4), self.px(12), self.px(12), self.px(12)), cor, self.fundo, borda,
                           (max(1, self.px(1)),) * 4)
        self.create_image(0, 0, image=self.guardar("fundo", fundo), anchor="nw", tags="fundo")
        self.create_image(pad, pad, image=self.ui.imagens(icone, tam, cor), anchor="nw")
        self.tag_lower("fundo")


class Etapas(Tela):
    """As etapas na barra lateral: número em círculo e marcador cítrico na etapa ativa."""

    LINHA, CONECTOR = 40, 12

    def __init__(self, mestre, ui: Kit, rotulos: list[str], fundo: str = VERDE_ESCURO, largura: float = 216):
        n = len(rotulos)
        super().__init__(mestre, ui, fundo, width=ui.px(largura),
                         height=ui.px(n * self.LINHA + (n - 1) * self.CONECTOR))
        self.rotulos = rotulos
        self.estados = ["ativa"] + ["pendente"] * (n - 1)
        self._desenhar()

    def definir(self, estados: list[str]) -> None:
        if estados != self.estados:
            self.estados = estados
            self._desenhar()

    def _desenhar(self):
        self.delete("all")
        ui, f = self.ui, self.ui.fontes
        l = int(self.cget("width"))
        for i, (rotulo, estado) in enumerate(zip(self.rotulos, self.estados)):
            y = ui.px(i * (self.LINHA + self.CONECTOR))
            meio = y + ui.px(self.LINHA) / 2
            fundo_circulo = self.fundo
            if estado == "ativa":
                fundo_circulo = BARRA_REALCE
                linha = superficie(l, ui.px(self.LINHA), (ui.px(10),) * 4, BARRA_REALCE, self.fundo)
                self.create_image(0, y, image=self.guardar(f"linha{i}", linha), anchor="nw")
                marca = superficie(ui.px(3), ui.px(22), (0, ui.px(1.5), ui.px(1.5), 0), VERDE_CITRICO, BARRA_REALCE)
                self.create_image(0, meio, image=self.guardar(f"marca{i}", marca), anchor="w")
            cor = {"ativa": VERDE_CITRICO, "feita": VERDE_BANDEIRA}.get(estado, BARRA_CIRCULO)
            img = circulo(ui.px(28), cor, fundo_circulo, "check" if estado == "feita" else None)
            self.create_image(ui.px(10), meio, image=self.guardar(f"circ{i}", img), anchor="w")
            if estado != "feita":
                self.create_text(ui.px(10 + 14), meio, text=str(i + 1), font=f.selo,
                                 fill=VERDE_ESCURO if estado == "ativa" else BARRA_TEXTO_PENDENTE)
            cor_rotulo = {"ativa": "#FFFFFF", "feita": BARRA_TEXTO}.get(estado, BARRA_TEXTO_PENDENTE)
            self.create_text(ui.px(10 + 28 + 12), meio, text=rotulo, anchor="w", fill=cor_rotulo,
                             font=f.pequeno_negrito if estado == "ativa" else f.pequeno)
            if i < len(self.rotulos) - 1:
                x = ui.px(10 + 14) - ui.px(1)
                self.create_rectangle(x, y + ui.px(self.LINHA) + ui.px(2), x + max(2, ui.px(2)),
                                      y + ui.px(self.LINHA + self.CONECTOR) - ui.px(2), width=0,
                                      fill=VERDE_CITRICO if estado == "feita" else BARRA_LINHA)
