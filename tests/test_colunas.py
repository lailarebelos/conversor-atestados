from atestados.colunas import identificar_metadados, normalizar, prefixo_numerado


def test_layout_do_servidor():
    m = identificar_metadados(["ID_ATESTADO", "COD_EMPRESA", "CHAPA_SOLICITANTE", "NOME",
                               "TAMANHO_ORIGINAL_BYTES", "TAMANHO_BASE64_CHARS", "IMG_PARTE001"])
    assert (m.id_atestado, m.empresa, m.chapa, m.nome, m.tamanho_bytes, m.tamanho_base64, m.data) == \
        (0, 1, 2, 3, 4, 5, None)


def test_variacoes_de_cabecalho():
    m = identificar_metadados(["Matrícula", "Nome do Médico", "Nome do Colaborador", "Data de Nascimento",
                               "Data de Envio", "Foto"])
    assert (m.chapa, m.nome, m.data, m.id_atestado) == (0, 2, 4, None)


def test_normalizar_e_prefixo_numerado():
    assert normalizar("Matrícula do colaborador") == "MATRICULA_DO_COLABORADOR"
    assert prefixo_numerado("IMG_PARTE001") == "IMG_PARTE"
    assert prefixo_numerado("PARTE_10") == "PARTE"
    assert prefixo_numerado("NOME") is None
    assert prefixo_numerado("10") is None
