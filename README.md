# Conversor de Atestados

Programa para Windows que transforma a planilha diária de atestados, com as fotos em base64,
em uma pasta com **um arquivo por colaborador** (foto ou PDF).

## Baixar

**[⬇ Baixar ConversorAtestados.exe](https://github.com/lailarebelos/conversor-atestados/releases/latest/download/ConversorAtestados.exe)**

É um arquivo único: não precisa instalar nem ter Python. Funciona no Windows 10 e 11 (64 bits).

## Como usar

1. Salve o `ConversorAtestados.exe` numa pasta fixa, por exemplo `Documentos\Conversor de Atestados`,
   e abra com dois cliques. A janela leva alguns segundos para abrir.
2. Arraste a planilha do dia para a área azul.
3. Confira a data e a pasta de destino e clique em **Exportar atestados**.

O passo a passo completo, o que fazer em cada mensagem de problema e os cuidados com os dados
estão no **[LEIA-ME](LEIA-ME.md)**.

> Na primeira vez, o Windows pode mostrar "O Windows protegeu o computador", porque o programa
> não tem assinatura digital. Se a política da empresa não permitir abrir assim mesmo, peça à TI
> para liberar.

## Privacidade

O programa funciona **sem internet**: nada do que ele lê ou gera sai do computador, e ele não grava
logs com o conteúdo dos atestados. Este repositório tem só o código e testes com dados
**sintéticos**. Planilhas e atestados nunca devem ser enviados para cá.
