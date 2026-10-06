# -*- mode: python ; coding: utf-8 -*-
# Receita do PyInstaller: um .exe único, sem janela de terminal, que roda sem Python instalado.
# Use o construir_exe.bat (ele roda os testes antes).
import os

import tkinterdnd2

RAIZ = SPECPATH  # noqa: F821 - definido pelo PyInstaller
TKDND = os.path.join(os.path.dirname(tkinterdnd2.__file__), "tkdnd", "win-x64")

a = Analysis(
    [os.path.join(RAIZ, "app.py")],
    pathex=[RAIZ],
    datas=[
        (os.path.join(RAIZ, "recursos", "icone.ico"), "recursos"),
        (os.path.join(RAIZ, "recursos", "ui"), os.path.join("recursos", "ui")),  # imagens da marca na tela
        (TKDND, os.path.join("tkinterdnd2", "tkdnd", "win-x64")),  # arrastar e soltar
    ],
    excludes=["openpyxl", "pytest", "_pytest", "numpy", "pandas"],  # só são usados nos testes
)
pyz = PYZ(a.pure)


class AberturaComFolhas(Splash):  # noqa: F821 - definido pelo PyInstaller
    """A tela de abertura do PyInstaller com as três folhas da marca pulando, para mostrar que o
    programa está carregando. O script Tcl das folhas é gerado por recursos/gerar_imagens.py."""

    def generate_script(self):
        with open(os.path.join(RAIZ, "recursos", "abertura_folhas.tcl"), encoding="utf-8") as f:
            script = super().generate_script() + "\n" + f.read()
        with open(self.script_name, "w", encoding="utf-8") as f:  # o script final fica na pasta do build
            f.write(script)
        return script


# tela de abertura: aparece na hora do clique, enquanto o .exe se descompacta (alguns segundos)
splash = AberturaComFolhas(
    os.path.join(RAIZ, "recursos", "abertura.png"),
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    max_img_size=(1120, 630),  # tamanho real da imagem (o padrão do PyInstaller a reduziria)
    always_on_top=False,
)
exe = EXE(
    pyz,
    a.scripts,
    splash,
    splash.binaries,
    a.binaries,
    a.datas,
    [],
    name="ConversorAtestados",
    icon=os.path.join(RAIZ, "recursos", "icone.ico"),
    version=os.path.join(RAIZ, "recursos", "versao_exe.txt"),
    # o manifesto padrão do PyInstaller + "dpiAware" (o mesmo modo que a janela já pede ao abrir):
    # sem ele, o Windows amplia a tela de abertura como bitmap e ela fica borrada em telas com zoom
    manifest=os.path.join(RAIZ, "recursos", "manifesto_exe.xml"),
    console=False,  # sem janela de terminal
    upx=False,
)
