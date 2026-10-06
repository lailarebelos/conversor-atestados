# Conversor de Atestados

O sistema entrega os atestados do dia numa planilha, com as fotos "escondidas" em forma de texto.
Este programa transforma essa planilha, de uma vez só, em uma pasta com **um arquivo por
colaborador** (foto ou PDF), pronto para abrir no Windows.

---

## Como abrir

Dê dois cliques em **`ConversorAtestados.exe`**. Não é preciso instalar nada.

- Primeiro aparece a tela de abertura verde, com três folhinhas pulando enquanto o programa
  carrega. A janela do programa abre depois de **alguns segundos (de 5 a 15)**. É normal, **não
  precisa clicar de novo**.
- Se o Windows ou o antivírus bloquear o programa, fale com a TI para liberar.

## A janela

- **À esquerda**, a barra verde mostra as 4 etapas. A etapa da vez fica destacada e as concluídas
  ganham um ✓.
- **No topo**, um selo resume a situação: *Aguardando planilha*, *Pronto para exportar*,
  *Exportando*, *Concluído*…
- A janela cabe inteira na tela do notebook. Se quiser, maximize.

## Passo a passo (todo dia)

1. **Baixe a planilha do dia** no sistema (por exemplo, `atestado11092026.xlsx`).
2. **Abra o Conversor de Atestados.**
3. **Arraste a planilha para a área verde tracejada** (Etapa 1), ou clique nela e escolha o arquivo.
   O programa lê a planilha e mostra quantos atestados encontrou. Pode demorar alguns segundos
   (a planilha é grande). Se estiver tudo certo, aparece uma confirmação verde. Se houver algo a
   observar (por exemplo, um atestado que veio cortado do sistema), um aviso amarelo explica o que
   vai acontecer.
4. **Confira a data.** Ela dá nome à pasta (por exemplo, `Atestados_11_09_2026`) e vem preenchida:
   - pelo nome do arquivo (`atestado11092026` → 11/09/2026);
   - se o nome não tiver data, pela data das fotos;
   - se não houver nenhuma data, pela data de hoje.

   Ao lado aparece de onde a data veio. Se estiver errada, digite a certa no formato **DD/MM/AAAA**.
5. **Confira onde salvar.** Por padrão, é a mesma pasta da planilha. Para mudar, clique em **Trocar pasta…**.
6. Clique em **Exportar atestados** e acompanhe a barra ("45 de 97"). Você pode continuar usando o
   computador enquanto isso. Se precisar, clique em **Cancelar**.
7. No fim aparece o resumo. Clique em **Abrir pasta** para ver os arquivos ou em **Abrir relatório**
   para ver a lista no Excel. Para exportar outra vez (por exemplo, depois de corrigir a data), use
   **Exportar de novo**.

> Funciona mesmo com a planilha aberta no Excel.

## O que fica na pasta

| O que você vê | O que é |
|---|---|
| `012345_FULANO_DE_TAL_654321.jpg` | Atestado de um colaborador: **chapa_nome_ID do atestado**. A extensão (.jpg, .png, .pdf) é a do formato real do arquivo. |
| `..._VERIFICAR.jpg` | Arquivo com algum problema. Abra e confira; o motivo está no relatório. |
| `relatorio_exportacao.csv` | Lista de todas as linhas da planilha: linha, chapa, nome, ID, arquivo gerado, formato, **status** (OK, VERIFICAR ou SEM ARQUIVO), motivo e se a localização (GPS) foi removida. Abre no Excel. |

Uma linha com problema nunca interrompe as outras: o programa salva o que der, marca com
`_VERIFICAR` e segue.

## Se aparecer algum problema

| O que aparece | O que significa | O que fazer |
|---|---|---|
| Arquivo com `_VERIFICAR` e o motivo "a planilha traz só parte do arquivo: faltam X%" | O sistema de origem **cortou** o arquivo ao gerar a planilha. Isso acontece com fotos grandes, acima de cerca de 3,6 MB. | Abra esse atestado no sistema, como era feito antes. A foto cortada costuma mostrar só a parte de cima; o PDF cortado não abre. Avise a TI (veja abaixo). |
| `_VERIFICAR` com "imagem incompleta", "imagem corrompida" ou "PDF incompleto" | Os dados dessa linha estão com defeito. | Abra esse atestado no sistema. |
| Status **SEM ARQUIVO** com "a linha não tem imagem" | A linha veio sem foto. | Confira no sistema. |
| Arquivo `.bin` com "formato não reconhecido" | O conteúdo não é foto nem PDF. | Confira no sistema. |
| Arquivo `.heic` | Foto de iPhone. O Windows pode precisar da extensão gratuita "Extensões de Imagem HEIF" (Microsoft Store). | Peça à TI para instalar. |
| "A pasta … já existe" | Essa data já foi exportada antes. | **Sim**: troca os arquivos da exportação anterior pelos novos (o que você colocou na pasta por conta própria não é apagado). **Não**: cancela. |
| "Um arquivo da exportação anterior está aberto em outro programa" | O relatório antigo, ou uma foto, está aberto. | Feche o Excel ou o visualizador e tente de novo. |
| "Não foi possível ler a planilha" | O arquivo veio incompleto, está protegido por senha ou não é a planilha de atestados. | Baixe a planilha de novo no sistema. |
| "Este arquivo não é uma planilha do Excel (parece uma página HTML/XML)" | O sistema gerou outro tipo de arquivo. | Exporte de novo pelo sistema, em .xlsx ou .csv. |
| "O caminho da pasta de destino é longo demais" | A pasta escolhida fica "funda" demais para o Windows. | Escolha uma pasta mais curta, como Documentos. |
| "Data inválida" | A data não está no formato DD/MM/AAAA. | Corrija a data; o botão volta a funcionar. |

Se algo diferente acontecer, anote a mensagem e avise a TI. **Não envie a planilha nem os
atestados** junto.

## Cuidados com os dados (LGPD)

Atestado médico é **dado pessoal sensível** (saúde).

- Salve as pastas só em locais com acesso restrito ao RH. Não deixe na Área de Trabalho nem em
  Downloads depois de usar.
- Não envie atestados por e-mail ou aplicativos de mensagem.
- Apague a planilha e as pastas quando não forem mais necessárias, conforme a política da empresa.
  A planilha original tem os mesmos dados e exige o mesmo cuidado.
- O programa **funciona sem internet** e não envia nada para fora do computador. Ele não grava
  registros (logs) com o conteúdo dos atestados e **remove a localização (GPS)** que algumas fotos
  de celular trazem, sem alterar a imagem.

---

## Para a equipe de TI

**Organização do código.** A lógica fica separada da interface:

- `atestados/`: núcleo, testável sozinho.
  - `leitura`: leitura de .xlsx/.xls/.ods com python-calamine e de .csv pelo módulo `csv`.
  - `colunas`: localiza as colunas de identificação pelo cabeçalho e as de base64 pelo conteúdo,
    sempre na ordem física.
  - `reconstrucao`: limpeza dos fragmentos, prefixo `data:`, url-safe, padding e detecção de mais
    de um arquivo por linha.
  - `formatos`: formato real pelos bytes e validação com `Image.load()` completo; PDF pelo
    `%PDF` no início e `%%EOF` no fim.
  - `metadados`: data das fotos (EXIF) e remoção do GPS sem recomprimir.
  - `nomes`, `datas` e `exportacao`: nomes de arquivo, datas e o fluxo completo com o relatório.
- `atestados/interface.py`: tela em Tkinter, na identidade visual Localiza&CO. O trabalho pesado
  roda numa thread separada.
- `atestados/visual.py`: peças visuais (cartões, botões, área de arrastar, barra de progresso,
  selos). São desenhadas com o Pillow para ficarem nítidas em qualquer zoom de tela.
- `recursos/`: em `marca/` ficam os SVGs originais da marca, tirados do acervo Designs Localiza.
  As imagens da tela (`ui/`), o ícone (`icone.ico`), a tela de abertura (`abertura.png`) e o
  script das folhas que pulam na abertura (`abertura_folhas.tcl`) são gerados a partir deles por
  `python recursos/gerar_imagens.py`. Esse passo só é necessário se a arte mudar.
- `app.py`: ponto de entrada do executável.

**Ambiente.** Python 3.13 64 bits. O executável não precisa de Python.

- Dependências de execução: `requirements.txt` (python-calamine, Pillow, tkinterdnd2).
- Para desenvolver: `requirements-dev.txt`. Inclui o resvg-py, usado só para gerar as imagens.

**Testes** (só dados sintéticos, gerados pelos próprios testes):

- `python -m pytest`: 100 testes.
- `python -m pytest -m lento -s`: desempenho com uma planilha de ~150 MB.

**Gerar o .exe.** Rode `construir_exe.bat`. Ele:

1. cria o ambiente em `%LOCALAPPDATA%\conversor-atestados\venv` (fora da pasta do projeto, porque
   alguns pacotes passam do limite de 260 caracteres do Windows);
2. roda os testes;
3. gera `dist\ConversorAtestados.exe`: arquivo único, sem janela de terminal, com tela de abertura,
   receita em `ConversorAtestados.spec`.

**Linha de comando** (mostra só contagens, nunca nomes):

```
python -m atestados PLANILHA.xlsx [--destino PASTA] [--data DD/MM/AAAA] [--substituir] [--so-analisar]
```

**Autoteste do .exe empacotado** (use uma planilha sintética):

```
set CONVERSOR_ATESTADOS_AUTOTESTE=C:\caminho\planilha.xlsx|C:\caminho\resumo.json
```

Depois execute o .exe. Ele exporta para uma pasta temporária e grava o resumo em JSON.

**Formato esperado da planilha.** Cabeçalho mais uma linha por atestado:

- colunas de identificação `ID_ATESTADO`, `COD_EMPRESA`, `CHAPA_SOLICITANTE`, `NOME`,
  `TAMANHO_ORIGINAL_BYTES` e `TAMANHO_BASE64_CHARS`;
- em seguida, o base64 fatiado em `IMG_PARTE001…IMG_PARTEnnn`.

O número de linhas e de colunas não é fixo. Também são aceitos:

- outros nomes de cabeçalho (Matrícula, Nome do colaborador, Data de envio…);
- planilha sem cabeçalho (arquivos numerados 001, 002…);
- CSV com `;` ou `,`;
- textos inline e dimensões declaradas erradas.

As colunas `TAMANHO_*` permitem detectar arquivos cortados.

**Limite do sistema de origem.** A exportação corta o base64 em **150 colunas × 32.000
caracteres ≈ 3,6 MB**. Arquivos maiores chegam cortados e saem com `_VERIFICAR`. Para que todos
cheguem inteiros, a exportação precisa permitir mais colunas; o Excel aceita até 16.384. O
programa não tem limite fixo e não precisa mudar.

**Privacidade.**

- Nenhum acesso à rede e nenhum log.
- Erros mostram só o tipo, sem o conteúdo.
- O `.gitignore` bloqueia planilhas (`*.xlsx`, `*.csv`…) e pastas `Atestados_*`.
- A remoção do GPS zera, no lugar, o bloco de GPS do EXIF e as coordenadas do XMP. O tamanho do
  arquivo e os dados da imagem ficam idênticos.
