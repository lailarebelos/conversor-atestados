import time
from types import SimpleNamespace

import pytest

import sintetico as s

tk = pytest.importorskip("tkinter")
from atestados import interface  # noqa: E402


@pytest.fixture
def app():
    try:
        root = interface.criar_janela()
    except tk.TclError:
        pytest.skip("sem ambiente gráfico")
    root.withdraw()
    aplicativo = interface.App(root)
    yield aplicativo
    try:
        root.destroy()
    except tk.TclError:
        pass


def esperar(app, condicao, limite=60.0) -> bool:
    """Roda o laço de eventos da janela até a condição valer (a janela segue respondendo)."""
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        app.root.update()
        if condicao():
            return True
        time.sleep(0.02)
    return False


def test_fluxo_completo_pela_interface(app, tmp_path, monkeypatch):
    planilha = s.planilha_padrao(tmp_path / "atestado28092026.xlsx",
                                 [s.linha(1, "000001", "PESSOA UM", s.jpeg()),
                                  s.linha(2, "000002", "PESSOA DOIS", s.png())])
    app.carregar_planilha(planilha)
    assert app.var_data.get() == "28/09/2026"  # preenchida na hora, pelo nome do arquivo
    assert app.var_destino.get() == str(tmp_path)  # padrão: a pasta da planilha
    assert app.selo.texto == "Lendo a planilha" and app.zona.estado == "analisando"
    assert esperar(app, lambda: app.analise is not None)
    assert "2 atestados encontrados" in app.var_status.get()
    assert str(app.botao_exportar["state"]) == "normal"
    assert app.zona.estado == "carregado"  # vira o chip compacto do arquivo
    assert app.aviso_planilha.tipo == "ok" and app.aviso_planilha.winfo_manager() == "pack"  # sem avisos
    assert app.etapas.estados == ["feita", "feita", "feita", "ativa"]
    assert app.selo.texto == "Pronto para exportar"

    destino = tmp_path / "saida"
    destino.mkdir()
    app.definir_destino(destino)
    app.exportar()
    assert str(app.botao_exportar["state"]) == "disabled"  # bloqueado durante a exportação
    assert esperar(app, lambda: app.resultado is not None)
    assert (app.resultado.arquivos_ok, app.resultado.arquivos_verificar) == (2, 0)
    assert "2 linhas processadas" in app.var_resumo.get()
    assert "2 atestados exportados" in app.var_resumo_ok.get() and app.var_resumo_aviso.get() == ""
    assert app.cartao_exportar.carimbo and app.link_exportar.winfo_manager() == "grid"  # cartão de sucesso
    assert app.status_resultado.winfo_manager() == "grid" and not app.linha_acao.winfo_manager()
    assert app.selo.texto == "Concluído" and app.etapas.estados == ["feita"] * 4
    assert (destino / "Atestados_28_09_2026" / "000001_PESSOA_UM_1.jpg").is_file()
    app.var_data.set("31/02/2026")
    assert not app.link_exportar.ativo  # data inválida: "Exportar de novo" fica cinza, como o botão
    app.var_data.set("28/09/2026")
    assert app.link_exportar.ativo

    perguntas = []
    monkeypatch.setattr(interface.messagebox, "askyesno", lambda *a, **k: perguntas.append(a) or False)
    app.exportar()  # a pasta já existe: pergunta e, sem confirmação, não faz nada
    assert perguntas and not app.exportando


def test_data_invalida_bloqueia_a_exportacao(app, tmp_path):
    app.carregar_planilha(s.planilha_padrao(tmp_path / "atestado28092026.xlsx", [s.linha(1, "000001", "X", s.png())]))
    assert esperar(app, lambda: app.analise is not None)
    app.var_data.set("31/02/2026")
    assert str(app.botao_exportar["state"]) == "disabled" and "inválida" in app.var_pasta.get()
    app.var_data.set("30/09/2026")
    assert "Atestados_30_09_2026" in app.var_pasta.get()
    assert app.var_origem_data.get() == "(digitada por você)"
    assert str(app.botao_exportar["state"]) == "normal"


def test_data_sugerida_mostra_a_origem(app, tmp_path):
    app.carregar_planilha(s.planilha_padrao(tmp_path / "atestados.xlsx",
                                            [s.linha(1, "000001", "X", s.com_tamanho_exato(s.jpeg(), 100_000))]))
    assert app.var_data.get() == ""  # o nome não tem data: espera a análise
    assert esperar(app, lambda: app.analise is not None)
    assert (app.var_data.get(), app.var_origem_data.get()) == ("10/09/2026", "(da data das fotos)")


def test_janela_muito_larga_nao_estica_os_cartoes(app):
    px, larga = app.ui.px, SimpleNamespace(widget=app.root)
    larga.width = px(interface.LARGURA_BARRA) + 2 * px(24) + px(interface.LARGURA_MAXIMA) + 400
    app._limitar_largura(larga)
    assert app.recuo == 200  # sobra dividida dos dois lados
    app._limitar_largura(SimpleNamespace(widget=app.root, width=px(1016)))
    assert app.recuo == 0


def test_planilha_corrompida_mostra_erro_e_nao_libera_exportar(app, tmp_path, monkeypatch):
    erros = []
    monkeypatch.setattr(interface.messagebox, "showerror", lambda *a, **k: erros.append(a))
    ruim = tmp_path / "atestado28092026.xlsx"
    ruim.write_bytes(b"PK\x03\x04 baixado pela metade")
    app.carregar_planilha(ruim)
    assert esperar(app, lambda: bool(erros))
    assert app.analise is None and str(app.botao_exportar["state"]) == "disabled"
