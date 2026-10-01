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
        (TKDND, os.path.join("tkinterdnd2", "tkdnd", "win-x64")),  # arrastar e soltar
    ],
    excludes=["openpyxl", "pytest", "_pytest", "numpy", "pandas"],  # só são usados nos testes
)
pyz = PYZ(a.pure)
# tela de abertura: aparece na hora do clique, enquanto o .exe se descompacta (alguns segundos)
splash = Splash(
    os.path.join(RAIZ, "recursos", "abertura.png"),
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
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
    console=False,  # sem janela de terminal
    upx=False,
)
