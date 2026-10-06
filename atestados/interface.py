"""Interface gráfica (Tkinter): uma tela só, em português, na identidade Localiza&CO.

O trabalho pesado (ler a planilha, decodificar, validar, gravar) roda numa thread separada;
a janela só recebe mensagens por uma fila, então nunca congela. A aparência segue o acervo
"Designs Localiza" e as regras de marca de 24/09/2026 (Calibri, cores sólidas, sem sombras,
cítrico só como acento): barra lateral verde-escura com as etapas, cartões brancos com o eco
do "L" e botões em Verde Bandeira. O comportamento é o mesmo da versão anterior.
"""
from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from . import NOME_APP, __version__, datas
from . import visual as v
from .exportacao import (Analise, Cancelado, ErroExportacao, PastaJaExiste, Resultado, analisar,
                         exportar)
from .leitura import ErroLeitura
from .visual import (Aviso, BarraProgresso, Botao, CaixaCaminho, Campo, Cartao, Etapas, Folhas, Kit,
                     Selo, Tela, ZonaArrastar, micro, superficie)

try:  # arrastar e soltar; sem ele, a área continua funcionando com clique
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # noqa: BLE001
    TkinterDnD = None

TIPOS_PLANILHA = [("Planilhas", "*.xlsx *.xlsm *.xls *.ods *.csv"), ("Todos os arquivos", "*.*")]
LARGURA_BARRA = 232
LARGURA_MAXIMA = 1080  # janela maximizada num monitor grande: os cartões não esticam além disso
ETAPAS = ["Planilha do dia", "Data da planilha", "Onde salvar", "Exportar"]
CREDITO = ("Desenvolvido por ", "Laila Rebelo")  # rodapé da barra lateral (e a tela de abertura)
LEITURA_SEM_AVISOS = "Leitura concluída sem avisos. Cada arquivo ainda é conferido na exportação."


def caminho_recurso(nome: str) -> Path:
    """Arquivo da pasta recursos/, tanto rodando o código quanto dentro do .exe."""
    return v.pasta_recursos() / nome


def criar_janela() -> tk.Tk:
    """Janela principal nítida em telas com zoom (DPI) e com arrastar e soltar, se disponível."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 - fora do Windows ou já configurado
        pass
    if TkinterDnD is not None:
        try:
            return TkinterDnD.Tk()
        except Exception:  # noqa: BLE001
            pass
    return tk.Tk()


def _duracao(segundos: float) -> str:
    if segundos < 1:
        return "menos de 1 s"
    segundos = round(segundos)
    return f"{segundos} s" if segundos < 60 else f"{segundos // 60} min {segundos % 60:02d} s"


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.dnd = TkinterDnD is not None and hasattr(root, "drop_target_register")
        self.fila: queue.Queue = queue.Queue()
        self.caminho: Path | None = None
        self.analise: Analise | None = None
        self.resultado: Resultado | None = None
        self.exportando = False
        self.analisando = False
        self.falha_analise = False
        self.geracao = 0  # descarta resultados de análises antigas
        self.cancelar_analise = threading.Event()
        self.cancelar_exportacao = threading.Event()
        self.thread_exportacao: threading.Thread | None = None
        self.destino_escolhido = False
        self.data_editada = False
        self._definindo_data = False
        self.recuo = 0  # margem extra de cada lado quando a janela passa da largura máxima

        self.var_status = tk.StringVar(value="Nenhuma planilha selecionada.")
        self.var_avisos = tk.StringVar()
        self.var_data = tk.StringVar()
        self.var_origem_data = tk.StringVar()
        self.var_pasta = tk.StringVar()
        self.var_destino = tk.StringVar()
        self.var_progresso = tk.StringVar()
        self.var_resumo = tk.StringVar()
        self.var_resumo_ok = tk.StringVar()
        self.var_resumo_aviso = tk.StringVar()
        self.var_resumo_gps = tk.StringVar()

        self._montar()
        self.var_data.trace_add("write", self._data_mudou)
        self.var_destino.trace_add("write", lambda *_: self._atualizar_estado())
        root.protocol("WM_DELETE_WINDOW", self._fechar)
        root.report_callback_exception = self._erro_inesperado
        root.after(100, self._ler_fila)
        self._atualizar_estado()

    # ------------------------------------------------------------ montagem ---
    def _montar(self) -> None:
        r = self.root
        r.title(NOME_APP)
        r.configure(bg=v.FUNDO)
        self.ui = ui = Kit(r)
        self.escala = ui.escala
        try:
            r.iconbitmap(default=str(caminho_recurso("icone.ico")))
        except tk.TclError:
            pass
        r.columnconfigure(1, weight=1)
        r.rowconfigure(1, weight=1)

        # barra lateral verde-escura: logo, produto, etapas
        self.barra = Tela(r, ui, v.VERDE_ESCURO, width=ui.px(LARGURA_BARRA))
        self.barra.grid(row=0, column=0, rowspan=2, sticky="ns")
        self.etapas = Etapas(self.barra, ui, ETAPAS, largura=LARGURA_BARRA - 16)
        self.barra.bind("<Configure>", lambda e: self._desenhar_barra())

        # topo branco: nome, selo de status e o monograma L&CO
        self.topo = Tela(r, ui, v.SUPERFICIE, height=ui.px(56), width=1)
        self.topo.grid(row=0, column=1, sticky="ew")
        self.selo = Selo(self.topo, ui)
        self.topo.bind("<Configure>", lambda e: self._desenhar_topo())

        self.conteudo = conteudo = tk.Frame(r, bg=v.FUNDO)
        conteudo.grid(row=1, column=1, sticky="nsew", padx=ui.px(24), pady=ui.px(18))
        # larguras de partida pensadas para caber num notebook; crescem juntas se a janela crescer
        conteudo.columnconfigure(0, weight=5, minsize=ui.px(408))
        conteudo.columnconfigure(1, weight=4, minsize=ui.px(328))
        self._montar_planilha(conteudo)
        self._montar_data_destino(conteudo)
        self._montar_exportacao(conteudo)
        r.bind("<Configure>", self._limitar_largura, add="+")

    def _limitar_largura(self, evento) -> None:
        if evento.widget is not self.root:
            return
        ui = self.ui
        livre = evento.width - ui.px(LARGURA_BARRA) - 2 * ui.px(24)
        recuo = max(0, livre - ui.px(LARGURA_MAXIMA)) // 2
        if recuo != self.recuo:
            self.recuo = recuo
            self.conteudo.grid_configure(padx=ui.px(24) + recuo)
            self._desenhar_topo()

    def _cabecalho(self, mestre, etapa: str, titulo: str) -> tk.Frame:
        f = self.ui.fontes
        quadro = tk.Frame(mestre, bg=v.SUPERFICIE)
        tk.Label(quadro, text=micro(etapa), font=f.micro, fg=v.TEXTO_APOIO, bg=v.SUPERFICIE).pack(anchor="w")
        tk.Label(quadro, text=titulo, font=f.titulo, fg=v.TEXTO, bg=v.SUPERFICIE).pack(anchor="w")
        return quadro

    def _montar_planilha(self, conteudo) -> None:
        ui = self.ui
        cartao = Cartao(conteudo, ui)
        cartao.grid(row=0, column=0, sticky="nsew", padx=(0, ui.px(8)))
        self._cabecalho(cartao.interior, "Etapa 1", "Planilha do dia").pack(fill="x")
        self.zona = ZonaArrastar(cartao.interior, ui, self.escolher_planilha)
        self.zona.pack(fill="x", pady=(ui.px(10), 0))
        if self.dnd:
            self.zona.drop_target_register(DND_FILES)
            self.zona.dnd_bind("<<Drop>>", self._ao_soltar)
            self.zona.dnd_bind("<<DropEnter>>", lambda e: (self.zona.arrastando(True), e.action)[1])
            self.zona.dnd_bind("<<DropLeave>>", lambda e: (self.zona.arrastando(False), e.action)[1])
        self.aviso_planilha = Aviso(cartao.interior, ui)

    def _montar_data_destino(self, conteudo) -> None:
        ui, f = self.ui, self.ui.fontes
        cartao = Cartao(conteudo, ui)
        cartao.grid(row=0, column=1, sticky="nsew", padx=(ui.px(8), 0))
        i = cartao.interior
        self._cabecalho(i, "Etapa 2", "Data da planilha").pack(fill="x")
        linha = tk.Frame(i, bg=v.SUPERFICIE)
        linha.pack(fill="x", pady=(ui.px(10), 0))
        self.campo_data = Campo(linha, ui, self.var_data, caracteres=10)
        self.campo_data.pack(side="left")
        self.entrada_data = self.campo_data.entrada
        self.selo_origem = Selo(linha, ui)
        self.selo_origem.pack(side="left", padx=(ui.px(10), 0))
        self.linha_pasta = Tela(i, ui, v.SUPERFICIE, height=f.pequeno.metrics("linespace") + ui.px(4), width=1)
        self.linha_pasta.pack(fill="x", pady=(ui.px(8), 0))
        self.linha_pasta.bind("<Configure>", lambda e: self._desenhar_linha_pasta())
        tk.Frame(i, bg=v.BORDA_BAIXA, height=max(1, ui.px(1))).pack(fill="x", pady=ui.px(14))
        self._cabecalho(i, "Etapa 3", "Onde salvar").pack(fill="x")
        linha2 = tk.Frame(i, bg=v.SUPERFICIE)
        linha2.pack(fill="x", pady=(ui.px(10), 0))
        self.botao_destino = Botao(linha2, ui, "Trocar pasta…", self.escolher_destino, "secundario", altura=40)
        self.botao_destino.pack(side="right", padx=(ui.px(8), 0))
        self.caixa_destino = CaixaCaminho(linha2, ui, self.var_destino)
        self.caixa_destino.pack(side="left", fill="x", expand=True, pady=self.botao_destino.anel)

    def _montar_exportacao(self, conteudo) -> None:
        ui, f = self.ui, self.ui.fontes
        self.cartao_exportar = cartao = Cartao(conteudo, ui)
        cartao.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(ui.px(16), 0))
        i = cartao.interior
        i.columnconfigure(0, weight=1)
        tk.Label(i, text=micro("Etapa 4 — Exportar"), font=f.micro, fg=v.TEXTO_APOIO,
                 bg=v.SUPERFICIE).grid(row=0, column=0, sticky="w")
        # "Exportar de novo": só aparece no cartão de sucesso
        self.link_exportar = v.Link(i, ui, "Exportar de novo", self.exportar)
        i.rowconfigure(0, minsize=self.link_exportar.winfo_reqheight())  # com ou sem o link, mesma altura
        altura = ui.px(84)  # a mesma altura em todos os estados: a tela não "pula"

        # linha de ação: botão principal + área de status (dica, lendo ou progresso)
        self.linha_acao = tk.Frame(i, bg=v.SUPERFICIE, height=altura)
        self.linha_acao.pack_propagate(False)
        self.botao_exportar = Botao(self.linha_acao, ui, "Exportar atestados", self.exportar, "primario", largura=212)
        self.botao_exportar.pack(side="left")
        self.area_status = tk.Frame(self.linha_acao, bg=v.SUPERFICIE)
        self.area_status.pack(side="left", fill="both", expand=True, padx=(ui.px(18), 0))
        self.status_dica = tk.Label(self.area_status, font=f.corpo, fg=v.TEXTO_APOIO, bg=v.SUPERFICIE,
                                    anchor="w", justify="left")
        self.status_lendo = tk.Frame(self.area_status, bg=v.SUPERFICIE)
        self.folhas_status = Folhas(self.status_lendo, ui, v.SUPERFICIE)
        self.folhas_status.pack(side="left")
        tk.Label(self.status_lendo, textvariable=self.var_progresso, font=f.corpo, fg=v.TEXTO_APOIO,
                 bg=v.SUPERFICIE).pack(side="left", padx=(ui.px(12), 0))
        self.status_progresso = tk.Frame(self.area_status, bg=v.SUPERFICIE)
        self.botao_cancelar = Botao(self.status_progresso, ui, "Cancelar", self.cancelar, "secundario", altura=36)
        self.botao_cancelar.pack(side="right", padx=(ui.px(14), 0))
        self.rotulo_progresso = tk.Label(self.status_progresso, textvariable=self.var_progresso,
                                         font=f.corpo_negrito, fg=v.TEXTO, bg=v.SUPERFICIE, width=12, anchor="e")
        self.rotulo_progresso.pack(side="right", padx=(ui.px(12), 0))
        self.barra_progresso = BarraProgresso(self.status_progresso, ui)
        self.barra_progresso.pack(side="left", fill="x", expand=True)

        # cartão de sucesso: balão, resumo em duas linhas e as ações empilhadas à direita
        self.status_resultado = tk.Frame(i, bg=v.SUPERFICIE, height=altura)
        self.status_resultado.pack_propagate(False)
        acoes = tk.Frame(self.status_resultado, bg=v.SUPERFICIE)
        acoes.pack(side="right", anchor="center")
        Botao(acoes, ui, "Abrir pasta", self.abrir_pasta, "primario", largura=150, altura=36).pack()
        Botao(acoes, ui, "Abrir relatório", self.abrir_relatorio, "secundario", largura=150, altura=36).pack(
            pady=(ui.px(2), 0))
        self.icone_resultado = tk.Label(self.status_resultado, bg=v.SUPERFICIE)
        self.icone_resultado.pack(side="left", anchor="center", padx=(0, ui.px(14)))
        textos = tk.Frame(self.status_resultado, bg=v.SUPERFICIE)
        textos.pack(side="left", fill="x", expand=True, anchor="center")
        tk.Label(textos, textvariable=self.var_resumo, font=f.corpo_negrito, fg=v.TEXTO, bg=v.SUPERFICIE,
                 anchor="w").pack(anchor="w")
        linha = tk.Frame(textos, bg=v.SUPERFICIE)
        linha.pack(anchor="w", pady=(ui.px(4), 0))
        tk.Label(linha, textvariable=self.var_resumo_ok, font=f.pequeno_negrito, fg=v.VERDE_BANDEIRA,
                 bg=v.SUPERFICIE).pack(side="left")
        self.selo_resultado = Selo(linha, ui)
        self.rotulo_gps = tk.Label(linha, textvariable=self.var_resumo_gps, font=f.pequeno, fg=v.TEXTO_APOIO,
                                   bg=v.SUPERFICIE)
        self.rotulo_gps.pack(side="left", padx=(ui.px(10), 0))
        self._mostrar_status("dica")

    def _mostrar_status(self, qual: str) -> None:
        resultado = qual == "resultado"
        if resultado:
            self.linha_acao.grid_remove()
            self.status_resultado.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(self.ui.px(6), 0))
            self.link_exportar.grid(row=0, column=1, sticky="e")
        else:
            self.status_resultado.grid_remove()
            self.link_exportar.grid_remove()
            self.linha_acao.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(self.ui.px(6), 0))
            for nome, quadro in (("dica", self.status_dica), ("lendo", self.status_lendo),
                                 ("progresso", self.status_progresso)):
                if nome == qual:
                    quadro.pack(fill="x", expand=True)
                else:
                    quadro.pack_forget()
        if qual == "lendo":
            self.folhas_status.iniciar()
        else:
            self.folhas_status.parar()

    # ------------------------------------------------------------ desenho ---
    def _desenhar_barra(self) -> None:
        b, ui, f = self.barra, self.ui, self.ui.fontes
        l, a = b.winfo_width(), b.winfo_height()
        if l < 10 or a < 10:
            return
        b.delete("desenho")
        # o "&" da marca, em contorno discreto, sangrando o canto de baixo à direita (atrás do rodapé)
        b.create_image(ui.px(104), a - ui.px(150), image=ui.imagens("grafismo_barra", 230, v.VERDE_ESCURO),
                       anchor="nw", tags="desenho")
        # canto superior direito arredondado (24 px), apoiado no branco do topo
        canto = v.canto_arredondado(ui.px(24), 1, v.VERDE_ESCURO, v.SUPERFICIE)
        b.create_image(l, 0, image=b.guardar("canto", canto), anchor="ne", tags="desenho")
        x, y = ui.px(20), ui.px(24)
        b.create_image(x, y, image=ui.imagens("logo_barra", 24, v.VERDE_ESCURO), anchor="nw", tags="desenho")
        y += ui.px(24 + 22)
        b.create_text(x, y, text=NOME_APP, font=f.produto, fill="#FFFFFF", anchor="nw", tags="desenho")
        y += f.produto.metrics("linespace") + ui.px(2)
        sub = b.create_text(x, y, text="Da planilha do sistema a um arquivo por colaborador", font=f.pequeno,
                            fill=v.BARRA_APOIO, anchor="nw", width=l - 2 * x, tags="desenho")
        y = b.bbox(sub)[3] + ui.px(16)
        b.create_rectangle(ui.px(16), y, l - ui.px(16), y + max(1, ui.px(1)), fill=v.BARRA_LINHA, width=0,
                           tags="desenho")
        y += ui.px(16)
        b.create_text(x, y, text=micro("Progresso"), font=f.micro, fill=v.BARRA_TEXTO_PENDENTE, anchor="nw",
                      tags="desenho")
        y += f.micro.metrics("linespace") + ui.px(8)
        b.create_window(ui.px(8), y, window=self.etapas, anchor="nw", tags="desenho")
        # rodapé: privacidade, versão e crédito (o nome um tom mais claro, como na tela de abertura)
        base = a - ui.px(20)
        inicio, nome = CREDITO
        b.create_text(x, base, text=inicio, font=f.pequeno, fill=v.BARRA_TEXTO_PENDENTE, anchor="sw", tags="desenho")
        b.create_text(x + f.pequeno.measure(inicio), base, text=nome, font=f.pequeno, fill=v.BARRA_TEXTO,
                      anchor="sw", tags=("desenho", "credito"))
        base -= f.pequeno.metrics("linespace") + ui.px(2)
        b.create_text(x, base, text=f"versão {__version__}", font=f.pequeno, fill=v.BARRA_TEXTO_PENDENTE,
                      anchor="sw", tags="desenho")
        rotulo = "Funciona sem internet"
        alto = ui.px(26)
        largura = f.selo.measure(rotulo) + ui.px(34)
        topo = base - f.pequeno.metrics("linespace") - ui.px(8) - alto
        pilula = superficie(largura, alto, (alto / 2,) * 4, v.BARRA_CIRCULO, v.VERDE_ESCURO)
        b.create_image(x, topo, image=b.guardar("pilula", pilula), anchor="nw", tags="desenho")
        ponto = superficie(ui.px(8), ui.px(8), (ui.px(4),) * 4, v.VERDE_CITRICO, v.BARRA_CIRCULO)
        b.create_image(x + ui.px(12), topo + alto / 2, image=b.guardar("ponto", ponto), anchor="w", tags="desenho")
        b.create_text(x + ui.px(26), topo + alto / 2, text=rotulo, font=f.selo, fill=v.BARRA_TEXTO, anchor="w",
                      tags="desenho")

    def _desenhar_topo(self) -> None:
        t, ui, f = self.topo, self.ui, self.ui.fontes
        l, a = t.winfo_width(), t.winfo_height()
        if l < 10:
            return
        t.delete("desenho")
        x = ui.px(28) + self.recuo  # alinhado com a coluna dos cartões
        t.create_text(x, a / 2, text=NOME_APP, font=f.titulo_app, fill=v.TEXTO, anchor="w", tags="desenho")
        t.create_window(x + f.titulo_app.measure(NOME_APP) + ui.px(14), a / 2, window=self.selo, anchor="w",
                        tags="desenho")
        t.create_image(l - ui.px(24) - self.recuo, a / 2, image=ui.imagens("selo_topo", 30, v.SUPERFICIE),
                       anchor="e", tags="desenho")
        t.create_rectangle(0, a - max(1, ui.px(1)), l, a, fill=v.BORDA_BAIXA, width=0, tags="desenho")

    def _desenhar_linha_pasta(self) -> None:
        c, f = self.linha_pasta, self.ui.fontes
        c.delete("all")
        data = self._data_valida()
        if data:
            inicio = "Será criada a pasta "
            c.create_text(0, 0, text=inicio, font=f.pequeno, fill=v.TEXTO_APOIO, anchor="nw")
            c.create_text(f.pequeno.measure(inicio), 0, text=datas.nome_pasta(data), font=f.pequeno_negrito,
                          fill=v.VERDE_BANDEIRA, anchor="nw")
        elif self.var_data.get().strip():
            c.create_text(0, 0, text="Data inválida. Use o formato DD/MM/AAAA.", font=f.pequeno,
                          fill=v.ERRO_TEXTO, anchor="nw")
        else:
            c.create_text(0, 0, text="Formato DD/MM/AAAA", font=f.pequeno, fill=v.TEXTO_MINIMO, anchor="nw")

    # ------------------------------------------------------------- planilha ---
    def escolher_planilha(self) -> None:
        if self.exportando:
            return
        inicial = str(self.caminho.parent) if self.caminho else str(Path.home() / "Downloads")
        caminho = filedialog.askopenfilename(title="Escolha a planilha do dia", filetypes=TIPOS_PLANILHA,
                                             initialdir=inicial)
        if caminho:
            self.carregar_planilha(caminho)

    def _ao_soltar(self, evento):
        self.zona.arrastando(False)
        caminhos = self.root.tk.splitlist(evento.data)
        if caminhos and not self.exportando:
            self.carregar_planilha(caminhos[0])
        return evento.action

    def carregar_planilha(self, caminho) -> None:
        caminho = Path(caminho)
        if self.exportando or not caminho.is_file():
            return
        self.cancelar_analise.set()  # interrompe a análise de uma planilha anterior
        self.cancelar_analise = threading.Event()
        self.geracao += 1
        self.caminho, self.analise, self.resultado = caminho, None, None
        self.analisando, self.falha_analise, self.data_editada = True, False, False
        self.cartao_exportar.definir_carimbo(False)
        self.var_status.set("Analisando a planilha…")
        self.var_avisos.set("")
        self._mostrar_avisos()
        self.zona.definir("analisando", "Lendo a planilha…", caminho.name)
        if not self.destino_escolhido:
            self.var_destino.set(str(caminho.parent))
        data_nome = datas.data_do_nome(caminho.name)
        if data_nome:
            self._definir_data(data_nome, "do nome do arquivo")
        else:
            self._definir_data(None, "procurando a data…")
        self.var_progresso.set("Lendo a planilha… (pode levar alguns segundos)")
        self._mostrar_status("lendo")
        self._atualizar_estado()
        threading.Thread(target=self._trabalho_analise, args=(caminho, self.geracao, self.cancelar_analise),
                         daemon=True).start()

    def _trabalho_analise(self, caminho: Path, geracao: int, cancelar: threading.Event) -> None:
        try:
            self.fila.put(("analise", geracao, analisar(caminho, cancelar=cancelar)))
        except Cancelado:
            pass
        except (ErroLeitura, ErroExportacao) as e:
            self.fila.put(("analise_erro", geracao, str(e)))
        except Exception as e:  # noqa: BLE001
            self.fila.put(("analise_erro", geracao, f"Erro inesperado ao analisar a planilha ({type(e).__name__})."))

    def _analise_pronta(self, analise: Analise) -> None:
        self.analise, self.analisando = analise, False
        encontrados = _plural(analise.total_linhas, "atestado encontrado", "atestados encontrados")
        self.var_status.set(f"{encontrados} nesta planilha.")
        self.var_avisos.set("\n".join(analise.avisos))
        self.zona.definir("carregado", self.caminho.name if self.caminho else "", encontrados)
        self._mostrar_avisos()
        if not self.data_editada:
            self._definir_data(analise.data, analise.origem_data)
        self.var_progresso.set("")
        self._mostrar_status("dica")
        self._atualizar_estado()

    def _analise_falhou(self, mensagem: str) -> None:
        self.analisando, self.falha_analise = False, True
        self.var_status.set("Não foi possível usar esta planilha.")
        self.zona.definir("erro", "Não foi possível usar esta planilha", "Clique ou arraste outra planilha")
        if not self.data_editada:
            self._definir_data(None, "")
        self.var_progresso.set("")
        self._mostrar_status("dica")
        self._atualizar_estado()
        messagebox.showerror(NOME_APP, mensagem, parent=self.root)

    def _mostrar_avisos(self) -> None:
        texto = self.var_avisos.get()
        if texto:
            self.aviso_planilha.definir(texto, "atencao")
        elif self.analise is not None:  # sem avisos: a confirmação também equilibra o cartão
            self.aviso_planilha.definir(LEITURA_SEM_AVISOS, "ok")
        else:
            self.aviso_planilha.pack_forget()
            return
        # recuado como o chip da planilha (que reserva o espaço do contorno de foco): bordas alinhadas
        self.aviso_planilha.pack(fill="x", padx=self.zona.anel, pady=(self.ui.px(10), 0))

    # ------------------------------------------------------------ data/destino ---
    def _definir_data(self, data, origem: str) -> None:
        self._definindo_data = True
        self.var_data.set(datas.formatar(data) if data else "")
        self._definindo_data = False
        self.var_origem_data.set(f"({origem})" if origem else "")
        self._atualizar_estado()

    def _data_mudou(self, *_):
        if not self._definindo_data:
            self.data_editada = True
            self.var_origem_data.set("(digitada por você)")
        self._atualizar_estado()

    def _data_valida(self):
        try:
            return datas.ler_data_digitada(self.var_data.get())
        except ValueError:
            return None

    def escolher_destino(self) -> None:
        pasta = filedialog.askdirectory(title="Onde criar a pasta dos atestados?",
                                        initialdir=self.var_destino.get() or str(Path.home()))
        if pasta:
            self.definir_destino(pasta)

    def definir_destino(self, pasta) -> None:
        self.destino_escolhido = True
        self.var_destino.set(str(Path(pasta)))

    def _atualizar_estado(self) -> None:
        data = self._data_valida()
        texto_data = self.var_data.get().strip()
        if data:
            self.var_pasta.set(f"Será criada a pasta:  {datas.nome_pasta(data)}")
        elif texto_data:
            self.var_pasta.set("Data inválida. Use o formato DD/MM/AAAA, por exemplo 28/09/2026.")
        else:
            self.var_pasta.set("")
        self.campo_data.definir_erro(bool(texto_data) and not data)
        self._desenhar_linha_pasta()
        origem = self.var_origem_data.get().strip("()")
        if origem:
            tipo = "neutro" if origem == "digitada por você" or origem.startswith("procurando") else "aguardando"
            self.selo_origem.definir(origem, tipo)
            self.selo_origem.pack(side="left", padx=(self.ui.px(10), 0))
        else:
            self.selo_origem.pack_forget()

        destino = self.var_destino.get()
        destino_ok = bool(destino) and Path(destino).is_dir()
        pode = bool(self.analise and data and destino_ok and not self.exportando)
        self.botao_exportar.configure(state="normal" if pode else "disabled")
        self.link_exportar.habilitar(pode)
        estado = "disabled" if self.exportando else "normal"
        self.entrada_data.configure(state=estado)
        self.botao_destino.configure(state=estado)
        self.zona.bloquear(self.exportando)

        # selo de status do topo
        r = self.resultado
        if self.exportando:
            selo = ("Exportando", "processando")
        elif r is not None:
            selo = ("Cancelado", "neutro") if r.cancelado else (
                ("Concluído · verificar", "atencao") if (r.arquivos_verificar or r.linhas_sem_arquivo)
                else ("Concluído", "pronto"))
        elif self.analisando:
            selo = ("Lendo a planilha", "processando")
        elif self.falha_analise:
            selo = ("Planilha com problema", "erro")
        elif self.analise is None:
            selo = ("Aguardando planilha", "aguardando")
        elif not data:
            selo = ("Revise a data", "atencao")
        elif not destino_ok:
            selo = ("Escolha a pasta", "atencao")
        else:
            selo = ("Pronto para exportar", "pronto")
        self.selo.definir(*selo)
        self._desenhar_topo()

        # etapas da barra lateral
        feitas = [self.analise is not None, bool(self.analise and data), bool(self.analise and destino_ok),
                  r is not None and not r.cancelado]
        estados, ativa = [], False
        for feita in feitas:
            if feita:
                estados.append("feita")
            elif not ativa:
                estados.append("ativa")
                ativa = True
            else:
                estados.append("pendente")
        if self.exportando:
            estados = ["feita", "feita", "feita", "ativa"]
        self.etapas.definir(estados)

        # dica da etapa 4
        if self.analise is None:
            dica = "Escolha a planilha do dia para começar." if not self.analisando else ""
        elif not data:
            dica = "Corrija a data da planilha para continuar."
        elif not destino_ok:
            dica = "Escolha uma pasta que exista para salvar os arquivos."
        else:
            dica = "Um arquivo por colaborador e o relatório vão para a pasta indicada acima."
        self.status_dica.configure(text=dica)

    # ------------------------------------------------------------ exportação ---
    def exportar(self) -> None:
        data = self._data_valida()
        if not (self.analise and data) or self.exportando:
            return
        destino = Path(self.var_destino.get())
        pasta = destino / datas.nome_pasta(data)
        substituir = False
        if pasta.exists():
            substituir = messagebox.askyesno(
                "A pasta já existe",
                f"A pasta “{pasta.name}” já existe em:\n{destino}\n\n"
                "Deseja substituir a exportação anterior?\n\n"
                "Os arquivos gerados antes serão trocados pelos novos. Outros arquivos que você "
                "tenha colocado nessa pasta não serão apagados.",
                icon="warning", parent=self.root)
            if not substituir:
                return
        self.exportando, self.resultado = True, None
        self.cancelar_exportacao = threading.Event()
        self.cartao_exportar.definir_carimbo(False)
        self.botao_cancelar.configure(text="Cancelar", state="normal")
        self.barra_progresso.definir(0, imediato=True)
        self.var_progresso.set("Lendo a planilha…")
        self._mostrar_status("progresso")
        self._atualizar_estado()
        self.thread_exportacao = threading.Thread(
            target=self._trabalho_exportacao,
            args=(self.analise.caminho, destino, data, self.analise, substituir, self.cancelar_exportacao),
            daemon=True)
        self.thread_exportacao.start()

    def _trabalho_exportacao(self, caminho, destino, data, analise, substituir, cancelar) -> None:
        def progresso(atual, total, texto):
            self.fila.put(("progresso", atual, total, texto))
        try:
            r = exportar(caminho, destino, data, analise=analise, progresso=progresso, cancelar=cancelar,
                         substituir=substituir)
            self.fila.put(("exportacao", r))
        except (ErroLeitura, ErroExportacao, PastaJaExiste) as e:
            self.fila.put(("exportacao_erro", str(e)))
        except Exception as e:  # noqa: BLE001
            self.fila.put(("exportacao_erro", f"Erro inesperado durante a exportação ({type(e).__name__})."))

    def cancelar(self) -> None:
        self.cancelar_exportacao.set()
        self.botao_cancelar.configure(text="Cancelando…", state="disabled")

    def _exportacao_pronta(self, r: Resultado) -> None:
        self.resultado, self.exportando = r, False
        total = self.analise.total_linhas if self.analise else r.linhas
        if r.cancelado:
            self.var_resumo.set(f"Exportação cancelada: {r.linhas} de {total} linhas processadas.")
        else:
            self.var_resumo.set(f"Pronto! {_plural(r.linhas, 'linha processada', 'linhas processadas')} "
                                f"em {_duracao(r.tempo)}.")
        self.var_resumo_ok.set(_plural(r.arquivos_ok, "atestado exportado", "atestados exportados"))
        avisos = []
        if r.arquivos_verificar:
            avisos.append(f"{r.arquivos_verificar} para verificar")
        if r.linhas_sem_arquivo:
            avisos.append(_plural(r.linhas_sem_arquivo, "linha sem arquivo", "linhas sem arquivo"))
        self.var_resumo_aviso.set(" · ".join(avisos))
        self.selo_resultado.pack_forget()
        if avisos:  # o selo amarelo vem logo depois do total exportado
            self.selo_resultado.definir(self.var_resumo_aviso.get(), "atencao")
            self.selo_resultado.pack(side="left", padx=(self.ui.px(10), 0), before=self.rotulo_gps)
        self.var_resumo_gps.set(f"· GPS removido de {_plural(r.gps_removido, 'foto', 'fotos')}"
                                if r.gps_removido else "")
        problemas = r.arquivos_verificar or r.linhas_sem_arquivo or r.cancelado
        self.icone_resultado.configure(image=self.ui.imagens("balao_alerta" if problemas else "balao_check", 34,
                                                             v.SUPERFICIE))
        self.var_progresso.set(f"Arquivos salvos em: {r.pasta}")
        self.barra_progresso.definir(1.0 if not r.cancelado else self.barra_progresso._alvo)
        self.cartao_exportar.definir_carimbo(not r.cancelado)
        self._mostrar_status("resultado")
        self._atualizar_estado()

    def _exportacao_falhou(self, mensagem: str) -> None:
        self.exportando = False
        self.barra_progresso.definir(0, imediato=True)
        self.var_progresso.set("")
        self._mostrar_status("dica")
        self._atualizar_estado()
        messagebox.showerror(NOME_APP, mensagem, parent=self.root)

    def abrir_pasta(self) -> None:
        if self.resultado:
            os.startfile(str(self.resultado.pasta))  # noqa: S606 - abre no Explorador do Windows

    def abrir_relatorio(self) -> None:
        if self.resultado and self.resultado.relatorio.is_file():
            os.startfile(str(self.resultado.relatorio))  # noqa: S606

    # ------------------------------------------------------------ infraestrutura ---
    def _ler_fila(self) -> None:
        try:
            while True:
                msg = self.fila.get_nowait()
                tipo = msg[0]
                if tipo == "analise" and msg[1] == self.geracao:
                    self._analise_pronta(msg[2])
                elif tipo == "analise_erro" and msg[1] == self.geracao:
                    self._analise_falhou(msg[2])
                elif tipo == "progresso":
                    _, atual, total, texto = msg
                    if total:
                        self.barra_progresso.definir(atual / total)
                    self.var_progresso.set(texto)
                elif tipo == "exportacao":
                    self._exportacao_pronta(msg[1])
                elif tipo == "exportacao_erro":
                    self._exportacao_falhou(msg[1])
        except queue.Empty:
            pass
        self.root.after(100, self._ler_fila)

    def _fechar(self) -> None:
        if self.exportando:
            if not messagebox.askyesno(NOME_APP, "Uma exportação está em andamento.\n\n"
                                                 "Deseja cancelar e sair?", parent=self.root):
                return
            self.cancelar_exportacao.set()
            if self.thread_exportacao is not None:
                self.thread_exportacao.join(timeout=20)
        self.cancelar_analise.set()
        self.root.destroy()

    def _erro_inesperado(self, tipo, valor, rastro) -> None:  # noqa: ARG002 - nada vai para log
        messagebox.showerror(NOME_APP, f"Ocorreu um erro inesperado ({tipo.__name__}).\n"
                                       "Feche o programa e abra de novo. Se repetir, avise a TI.",
                             parent=self.root)


def posicionar(app: App) -> None:
    """Tamanho inicial pelo conteúdo (cabe numa tela de notebook), centralizado."""
    root = app.root
    root.update_idletasks()
    largura = min(root.winfo_reqwidth(), root.winfo_screenwidth() - app.ui.px(40))
    altura = min(root.winfo_reqheight(), root.winfo_screenheight() - app.ui.px(80))
    root.minsize(largura, altura)
    x = (root.winfo_screenwidth() - largura) // 2
    y = max((root.winfo_screenheight() - app.ui.px(48) - altura) // 2, 0)
    root.geometry(f"{largura}x{altura}+{x}+{y}")


def _fechar_tela_de_abertura() -> None:
    """Fecha a tela de abertura do .exe (só existe no executável empacotado)."""
    try:
        import pyi_splash  # noqa: PLC0415
        pyi_splash.close()
    except Exception:  # noqa: BLE001 - rodando pelo código-fonte: não há tela de abertura
        pass


def main() -> None:
    root = criar_janela()
    posicionar(App(root))
    root.after(150, _fechar_tela_de_abertura)
    root.mainloop()
