"""Interface gráfica (Tkinter): uma tela só, em português, para o uso diário do RH.

O trabalho pesado (ler a planilha, decodificar, validar, gravar) roda numa thread
separada; a janela só recebe mensagens por uma fila, então nunca congela.
"""
from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from . import NOME_APP, __version__, datas
from .exportacao import (Analise, Cancelado, ErroExportacao, PastaJaExiste, Resultado, analisar,
                         exportar)
from .leitura import ErroLeitura

try:  # arrastar e soltar; sem ele, a área continua funcionando com clique
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # noqa: BLE001
    TkinterDnD = None

TIPOS_PLANILHA = [("Planilhas", "*.xlsx *.xlsm *.xls *.ods *.csv"), ("Todos os arquivos", "*.*")]
AZUL, AZUL_ESCURO, CINZA = "#1F6FB2", "#185A91", "#9AA5B1"
ZONA, ZONA_ATIVA, BORDA, BORDA_ATIVA = "#EEF4FB", "#DCEBFA", "#B7C6D8", "#1F6FB2"
TEXTO_SUAVE, LARANJA, VERMELHO, VERDE = "#5B6B7C", "#B45309", "#B91C1C", "#15803D"


def caminho_recurso(nome: str) -> Path:
    """Arquivo da pasta recursos/, tanto rodando o código quanto dentro do .exe."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "recursos" / nome


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
        self.geracao = 0  # descarta resultados de análises antigas
        self.cancelar_analise = threading.Event()
        self.cancelar_exportacao = threading.Event()
        self.thread_exportacao: threading.Thread | None = None
        self.destino_escolhido = False
        self.data_editada = False
        self._definindo_data = False

        self.var_status = tk.StringVar(value="Nenhuma planilha selecionada.")
        self.var_avisos = tk.StringVar()
        self.var_data = tk.StringVar()
        self.var_origem_data = tk.StringVar()
        self.var_pasta = tk.StringVar()
        self.var_destino = tk.StringVar()
        self.var_progresso = tk.StringVar()
        self.var_resumo = tk.StringVar()

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
        self.escala = max(r.winfo_fpixels("1i") / 96, 1.0)  # 1,5 numa tela com zoom de 150%
        r.minsize(int(600 * self.escala), int(560 * self.escala))
        try:
            r.iconbitmap(default=str(caminho_recurso("icone.ico")))
        except tk.TclError:
            pass
        for nome in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            tkfont.nametofont(nome).configure(family="Segoe UI", size=10)
        estilo = ttk.Style(r)
        estilo.configure("Titulo.TLabel", font=("Segoe UI", 17, "bold"))
        estilo.configure("Suave.TLabel", foreground=TEXTO_SUAVE)
        estilo.configure("Aviso.TLabel", foreground=LARANJA)
        estilo.configure("Secao.TLabelframe.Label", font=("Segoe UI", 10, "bold"))

        base = ttk.Frame(r, padding=(22, 12, 22, 10))
        base.pack(fill="both", expand=True)
        base.columnconfigure(0, weight=1)
        ttk.Label(base, text=NOME_APP, style="Titulo.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(base, text="Transforma a planilha diária de atestados em arquivos, um por colaborador.",
                  style="Suave.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 8))

        # 1. Planilha do dia: área de arrastar e soltar / clicar
        sec1 = ttk.LabelFrame(base, text=" 1. Planilha do dia ", style="Secao.TLabelframe", padding=(12, 8, 12, 10))
        sec1.grid(row=2, column=0, sticky="ew")
        sec1.columnconfigure(0, weight=1)
        self.zona = tk.Frame(sec1, bg=ZONA, highlightthickness=2, highlightbackground=BORDA,
                             highlightcolor=BORDA, cursor="hand2")
        self.zona.grid(row=0, column=0, sticky="ew")
        self.zona_titulo = tk.Label(self.zona, bg=ZONA, fg=AZUL, font=("Segoe UI", 12, "bold"), cursor="hand2")
        self.zona_titulo.pack(padx=16, pady=(14, 2))
        self.zona_sub = tk.Label(self.zona, bg=ZONA, fg=TEXTO_SUAVE, cursor="hand2")
        self.zona_sub.pack(padx=16, pady=(0, 14))
        self._textos_zona()
        for w in (self.zona, self.zona_titulo, self.zona_sub):
            w.bind("<Button-1>", lambda e: self.escolher_planilha())
            w.bind("<Enter>", lambda e: self._realcar_zona(True))
            w.bind("<Leave>", lambda e: self._realcar_zona(False))
        if self.dnd:
            self.zona.drop_target_register(DND_FILES)
            self.zona.dnd_bind("<<Drop>>", self._ao_soltar)
            self.zona.dnd_bind("<<DropEnter>>", lambda e: (self._realcar_zona(True), e.action)[1])
            self.zona.dnd_bind("<<DropLeave>>", lambda e: (self._realcar_zona(False), e.action)[1])
        self.rotulo_status = ttk.Label(sec1, textvariable=self.var_status)
        self.rotulo_status.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.rotulo_avisos = ttk.Label(sec1, textvariable=self.var_avisos, style="Aviso.TLabel", justify="left")
        self.rotulo_avisos.grid(row=2, column=0, sticky="w")

        # 2. Data
        sec2 = ttk.LabelFrame(base, text=" 2. Data da planilha ", style="Secao.TLabelframe", padding=(12, 8, 12, 10))
        sec2.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        sec2.columnconfigure(2, weight=1)
        self.entrada_data = ttk.Entry(sec2, textvariable=self.var_data, width=12, font=("Segoe UI", 11),
                                      justify="center")
        self.entrada_data.grid(row=0, column=0, sticky="w")
        ttk.Label(sec2, text="DD/MM/AAAA", style="Suave.TLabel").grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(sec2, textvariable=self.var_origem_data, style="Suave.TLabel").grid(row=0, column=2, sticky="w",
                                                                                      padx=(12, 0))
        self.rotulo_pasta = ttk.Label(sec2, textvariable=self.var_pasta)
        self.rotulo_pasta.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))

        # 3. Onde salvar
        sec3 = ttk.LabelFrame(base, text=" 3. Onde salvar ", style="Secao.TLabelframe", padding=(12, 8, 12, 10))
        sec3.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        sec3.columnconfigure(0, weight=1)
        ttk.Entry(sec3, textvariable=self.var_destino, state="readonly").grid(row=0, column=0, sticky="ew")
        self.botao_destino = ttk.Button(sec3, text="Trocar pasta…", command=self.escolher_destino)
        self.botao_destino.grid(row=0, column=1, padx=(8, 0))

        # Exportar
        acao = ttk.Frame(base)
        acao.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        acao.columnconfigure(0, weight=1)
        self.botao_exportar = tk.Button(acao, text="Exportar atestados", command=self.exportar,
                                        font=("Segoe UI", 12, "bold"), fg="white", bg=AZUL,
                                        activebackground=AZUL_ESCURO, activeforeground="white",
                                        disabledforeground="#EEF1F4", relief="flat", bd=0, padx=20, pady=8)
        self.botao_exportar.grid(row=0, column=0, sticky="ew")
        self.botao_cancelar = ttk.Button(acao, text="Cancelar", command=self.cancelar)
        self.botao_cancelar.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self.botao_cancelar.grid_remove()
        self.barra = ttk.Progressbar(base, mode="determinate")
        self.barra.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        self.rotulo_progresso = ttk.Label(base, textvariable=self.var_progresso, style="Suave.TLabel")
        self.rotulo_progresso.grid(row=7, column=0, sticky="w")

        # Resultado: título, linha verde (exportados), linhas laranja (verificar), GPS
        self.quadro_resultado = ttk.Frame(base)
        self.quadro_resultado.grid(row=8, column=0, sticky="ew", pady=(6, 0))
        self.var_resumo_ok, self.var_resumo_aviso, self.var_resumo_gps = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.rotulos_resumo = []
        for i, (var, cor, fonte) in enumerate(((self.var_resumo, "", ("Segoe UI", 10, "bold")),
                                               (self.var_resumo_ok, VERDE, None),
                                               (self.var_resumo_aviso, LARANJA, None),
                                               (self.var_resumo_gps, TEXTO_SUAVE, None))):
            rotulo = ttk.Label(self.quadro_resultado, textvariable=var, justify="left", foreground=cor,
                               **({"font": fonte} if fonte else {}))
            rotulo.grid(row=i, column=0, sticky="w")
            self.rotulos_resumo.append(rotulo)
        botoes = ttk.Frame(self.quadro_resultado)
        botoes.grid(row=4, column=0, sticky="w", pady=(6, 0))
        ttk.Button(botoes, text="Abrir pasta", command=self.abrir_pasta).pack(side="left")
        ttk.Button(botoes, text="Abrir relatório", command=self.abrir_relatorio).pack(side="left", padx=(8, 0))
        self.quadro_resultado.grid_remove()

        base.rowconfigure(9, weight=1)
        ttk.Label(base, text=f"Funciona sem internet: nenhum dado sai deste computador.   •   versão {__version__}",
                  style="Suave.TLabel", font=("Segoe UI", 8)).grid(row=10, column=0, sticky="w", pady=(6, 0))
        # textos longos quebram conforme a largura da janela
        base.bind("<Configure>", lambda e: [
            w.configure(wraplength=max(e.width - int(70 * self.escala), 200))
            for w in (self.rotulo_avisos, self.rotulo_progresso, *self.rotulos_resumo)])

    def _textos_zona(self) -> None:
        if self.caminho is None:
            titulo = "Arraste a planilha do dia para cá" if self.dnd else "Clique para escolher a planilha do dia"
            sub = "ou clique para escolher o arquivo (.xlsx ou .csv)" if self.dnd else "(.xlsx ou .csv)"
        else:
            titulo = self.caminho.name
            sub = "Para trocar, clique aqui ou arraste outra planilha" if self.dnd else "Clique aqui para trocar"
        self.zona_titulo.configure(text=titulo)
        self.zona_sub.configure(text=sub)

    def _realcar_zona(self, ativo: bool) -> None:
        cor = ZONA_ATIVA if ativo and not self.exportando else ZONA
        self.zona.configure(bg=cor, highlightbackground=BORDA_ATIVA if ativo else BORDA)
        self.zona_titulo.configure(bg=cor)
        self.zona_sub.configure(bg=cor)

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
        self._realcar_zona(False)
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
        self.data_editada = False
        self._textos_zona()
        self.quadro_resultado.grid_remove()
        self.rotulo_status.configure(foreground="")
        self.var_status.set("Analisando a planilha…")
        self.var_avisos.set("")
        if not self.destino_escolhido:
            self.var_destino.set(str(caminho.parent))
        data_nome = datas.data_do_nome(caminho.name)
        if data_nome:
            self._definir_data(data_nome, "do nome do arquivo")
        else:
            self._definir_data(None, "procurando a data…")
        self.barra.configure(mode="indeterminate")
        self.barra.start(12)
        self.var_progresso.set("Lendo a planilha… (pode levar alguns segundos)")
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
        self.analise = analise
        self._parar_barra()
        self.var_status.set(f"{_plural(analise.total_linhas, 'atestado encontrado', 'atestados encontrados')}"
                            f" nesta planilha.")
        self.var_avisos.set("\n".join(f"⚠  {a}" for a in analise.avisos))
        if not self.data_editada:
            self._definir_data(analise.data, analise.origem_data)
        self._atualizar_estado()

    def _analise_falhou(self, mensagem: str) -> None:
        self._parar_barra()
        self.var_status.set("Não foi possível usar esta planilha.")
        self.rotulo_status.configure(foreground=VERMELHO)
        if not self.data_editada:
            self._definir_data(None, "")
        self._atualizar_estado()
        messagebox.showerror(NOME_APP, mensagem, parent=self.root)

    # ------------------------------------------------------------ data/destino ---
    def _definir_data(self, data, origem: str) -> None:
        self._definindo_data = True
        self.var_data.set(datas.formatar(data) if data else "")
        self._definindo_data = False
        self.var_origem_data.set(f"({origem})" if origem else "")

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
        if data:
            self.var_pasta.set(f"Será criada a pasta:  {datas.nome_pasta(data)}")
            self.rotulo_pasta.configure(foreground="")
        elif self.var_data.get().strip():
            self.var_pasta.set("Data inválida. Use o formato DD/MM/AAAA, por exemplo 28/09/2026.")
            self.rotulo_pasta.configure(foreground=VERMELHO)
        else:
            self.var_pasta.set("")
        destino = self.var_destino.get()
        pode = bool(self.analise and data and destino and Path(destino).is_dir() and not self.exportando)
        self.botao_exportar.configure(state="normal" if pode else "disabled", bg=AZUL if pode else CINZA,
                                      cursor="hand2" if pode else "arrow")
        estado = "disabled" if self.exportando else "normal"
        self.entrada_data.configure(state=estado)
        self.botao_destino.configure(state=estado)

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
        self.quadro_resultado.grid_remove()
        self.botao_cancelar.configure(text="Cancelar", state="normal")
        self.botao_cancelar.grid()
        self.barra.configure(mode="determinate", maximum=max(self.analise.total_linhas, 1), value=0)
        self.var_progresso.set("Lendo a planilha…")
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
        self.botao_cancelar.grid_remove()
        total = self.analise.total_linhas if self.analise else r.linhas
        if r.cancelado:
            self.var_resumo.set(f"Exportação cancelada: {r.linhas} de {total} linhas processadas. "
                                "O relatório lista o que foi salvo.")
        else:
            self.var_resumo.set(f"Pronto! {_plural(r.linhas, 'linha processada', 'linhas processadas')} "
                                f"em {_duracao(r.tempo)}.")
        self.var_resumo_ok.set(f"✔  {_plural(r.arquivos_ok, 'atestado exportado', 'atestados exportados')}")
        avisos = []
        if r.arquivos_verificar:
            avisos.append(f"⚠  {r.arquivos_verificar} para verificar: arquivos com _VERIFICAR no nome "
                          "(o motivo está no relatório)")
        if r.linhas_sem_arquivo:
            avisos.append(f"⚠  {_plural(r.linhas_sem_arquivo, 'linha ficou', 'linhas ficaram')} sem arquivo "
                          "(veja o relatório)")
        self.var_resumo_aviso.set("\n".join(avisos))
        self.var_resumo_gps.set(f"Localização (GPS) removida de {_plural(r.gps_removido, 'foto', 'fotos')}."
                                if r.gps_removido else "")
        self.var_progresso.set(f"Arquivos salvos em: {r.pasta}")
        self.quadro_resultado.grid()
        self._atualizar_estado()
        self._caber_na_janela()

    def _caber_na_janela(self) -> None:
        """Cresce a janela, se preciso, para o resumo e o rodapé aparecerem inteiros."""
        self.root.update_idletasks()
        falta = self.root.winfo_reqheight() - self.root.winfo_height()
        if falta > 0 and self.root.state() == "normal":
            altura = min(self.root.winfo_height() + falta, self.root.winfo_screenheight() - 80)
            self.root.geometry(f"{self.root.winfo_width()}x{altura}")

    def _exportacao_falhou(self, mensagem: str) -> None:
        self.exportando = False
        self.botao_cancelar.grid_remove()
        self.barra.configure(value=0)
        self.var_progresso.set("")
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
                        self.barra.configure(maximum=total, value=atual)
                    self.var_progresso.set(texto)
                elif tipo == "exportacao":
                    self._exportacao_pronta(msg[1])
                elif tipo == "exportacao_erro":
                    self._exportacao_falhou(msg[1])
        except queue.Empty:
            pass
        self.root.after(100, self._ler_fila)

    def _parar_barra(self) -> None:
        self.barra.stop()
        self.barra.configure(mode="determinate", value=0)
        self.var_progresso.set("")

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
    """Tamanho inicial pela escala da tela (com folga para o resumo final), centralizado."""
    root = app.root
    root.update_idletasks()
    largura = min(max(root.winfo_reqwidth(), int(660 * app.escala)), root.winfo_screenwidth() - 40)
    altura = min(max(root.winfo_reqheight() + int(150 * app.escala), int(700 * app.escala)),
                 root.winfo_screenheight() - 80)
    x = (root.winfo_screenwidth() - largura) // 2
    y = max((root.winfo_screenheight() - altura) // 3, 0)
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
