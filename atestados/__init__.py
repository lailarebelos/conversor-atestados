"""Conversor de Atestados: transforma a planilha diária (fotos em base64) em arquivos.

A lógica (ler → reconstruir → validar → salvar) fica neste pacote, separada da
interface gráfica (`atestados.interface`), para poder ser testada sozinha.
Tudo roda offline: nada é enviado para a internet e nada do conteúdo é registrado em log.
"""

__version__ = "1.0.0"
NOME_APP = "Conversor de Atestados"
