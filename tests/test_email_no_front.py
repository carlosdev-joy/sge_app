"""Bancada do front para o nó `email` no canvas (F2 da spec de notificação por
e-mail): `components/etapas/fluxoTypes.ts`.

A régua daqui ESPELHA `_validate_email` do backend (api/routers/jobs.py). Ela
existe para o operador ver o problema junto do nó, antes do save; a fonte da
verdade continua sendo o servidor. Se as duas divergirem, a tela passa a
prometer o que o save recusa — por isso os mesmos casos aparecem nos dois
arquivos de teste.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests/js/ds_params_harness.cjs"


@pytest.fixture(scope="module")
def e():
    node = shutil.which("node")
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, cwd=str(RAIZ), timeout=180)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)["emailNo"]


def test_no_novo_nasce_util(e):
    """Arrastar o nó e ligar já produz um aviso que faz sentido: herda a lista
    do fluxo e traz assunto e corpo prontos."""
    p = e["padrao"]
    assert p["incluir_pipeline"] is True and p["destinatarios"] == []
    assert "{pipeline}" in p["assunto"] and p["corpo"].strip()
    assert p["anexo"] is None and p["html"] is False


def test_round_trip_com_a_api(e):
    vazio, completo, sujo, incluirAusente = e["doApi"]
    assert vazio["incluir_pipeline"] is True                  # null → default útil
    assert completo["anexo"] == {"raiz": "/dados/saida", "nome": "relatorio_{odate}.xlsx"}
    assert completo["incluir_pipeline"] is False              # escolha explícita sobrevive
    assert sujo["destinatarios"] == ["a@x.com"]               # espaços e vazios somem
    assert sujo["anexo"] == {"raiz": "/dados/saida", "nome": "r.csv"}
    # Ausente = ligado, como no backend: um round-trip não pode desligar a
    # herança sozinho (o e-mail sairia para menos gente, em silêncio).
    assert incluirAusente is True


def test_rotulo_do_card_diz_quem_recebe(e):
    assert e["rotulos"] == ["destinatários do fluxo", "ana@cvp.com.br",
                            "2 destinatários + fluxo", "sem destinatário"]


def test_regua_local_espelha_a_do_backend(e):
    r = e["erros"]
    assert r["padraoHerdando"] == [] and r["completo"] == []
    assert r["padraoSemDestinatario"] and "destinatário" in r["padraoSemDestinatario"][0]
    assert r["semAssunto"] == ["Informe o assunto"]
    assert r["semCorpo"] == ["Informe o corpo da mensagem"]
    assert "quebra de linha" in r["assuntoComQuebra"][0]
    assert r["destinatarioRuim"] == ["Destinatário inválido: sem-arroba"]


def test_anexo_so_dentro_das_pastas_liberadas(e):
    r = e["erros"]
    assert "não está entre as permitidas" in r["anexoForaDaRaiz"][0]
    assert "barra" in r["anexoComBarra"][0]


def test_anexo_incompleto_e_cobrado_em_vez_de_sumir(e):
    """A serialização descarta um anexo sem nome (vira null): sem esta régua o
    operador marcaria 'Anexar', salvaria, e o anexo não existiria — sem aviso."""
    r = e["erros"]
    assert any("nome do arquivo do anexo" in x for x in r["anexoSemNome"])
    assert any("Escolha a pasta do anexo" in x for x in r["anexoSemPasta"])


def test_lista_de_pastas_vazia_nao_trava_o_save(e):
    """Lista vazia pode ser 'Admin sem pasta liberada' OU falha ao consultar o
    status. Cobrar a pasta aqui travaria o fluxo inteiro por um erro de rede,
    sem caminho de saída — o backend continua sendo a palavra final."""
    assert e["erros"]["semRaizLiberada"] == []


# ── catálogo de modelos (F2 da spec de modelos e navegação) ─────────────────

@pytest.fixture(scope="module")
def modelos():
    import shutil as _sh
    node = _sh.which("node")
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, cwd=str(RAIZ), timeout=180)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)["emailModelos"]


def test_modelo_novo_nasce_em_html_e_ativo(modelos):
    f = modelos["formVazio"]
    assert f["html"] is True and f["ativo"] is True and f["padrao"] is False


def test_regua_do_modelo_espelha_a_do_backend(modelos):
    e = modelos["erros"]
    assert e["cheio"] == []
    assert e["vazio"] == ["Informe o nome do modelo", "Informe o corpo do modelo"]
    assert e["semNome"] == ["Informe o nome do modelo"]
    assert "quebra de linha" in e["nomeComQuebra"][0]
    assert e["semCorpo"] == ["Informe o corpo do modelo"]
    assert "20.000" in e["corpoLongo"][0]
    assert "quebra de linha" in e["assuntoComQuebra"][0]


def test_ancora_com_modelo_o_corpo_do_no_nao_e_exigido(modelos):
    """⛔ Âncora do catálogo: o corpo vem de lá no envio. Se a régua da tela
    continuasse cobrando o corpo do nó, cada fluxo teria de duplicar o HTML —
    exatamente o que o catálogo existe para evitar."""
    assert modelos["noComModelo"] == []
    assert modelos["noSemModelo"] == ["Informe o corpo da mensagem"]


def test_ancora_no_anterior_ao_catalogo_vira_corpo_livre(modelos):
    """⛔ Âncora da compatibilidade: nó gravado antes da F2 não tem a chave.
    Ele entra como Corpo livre e segue enviando o que sempre enviou — a
    mudança não pode alterar nenhum e-mail já configurado."""
    assert modelos["doApiSemModelo"] is None
    assert modelos["doApiComModelo"] == 5


def test_no_novo_nasce_no_modelo_padrao(modelos):
    """O layout institucional tem de ser o caminho de MENOR esforço: nó novo
    já nasce nele. Sem catálogo (ou sem padrão marcado), nasce em Corpo livre
    — igual a antes da F2."""
    assert modelos["novoComPadrao"] == 4
    assert modelos["novoSemPadrao"] is None
    assert modelos["novoPreservaOResto"] is True      # o resto do default fica de pé


# A MESMA lista da bancada (tests/js/ds_params_harness.cjs, CASOS_PASTA), na
# mesma ordem: é o par que faz o teste cruzado valer.
CASOS_PASTA = [
    ("/dados/saida", ["/dados/saida"]),
    ("/dados/saida/2026/09", ["/dados/saida"]),
    ("/dados/saida/", ["/dados/saida"]),
    ("/dados//saida/x", ["/dados/saida"]),
    ("/dados/./saida", ["/dados/saida"]),
    ("/dados/saidaX", ["/dados/saida"]),
    ("/dados/saida/../../etc", ["/dados/saida"]),
    ("dados/saida", ["/dados/saida"]),
    ("/dados/saida", []),
    ("//dados/saida", ["/dados/saida"]),
    ("/dados/saida", ["//dados/saida"]),
    ("/etc/shadow", [""]),
    ("/etc/shadow", ["/"]),
    ("/dados/saida\n/etc", ["/dados/saida"]),
    ("/dados/saida\\etc", ["/dados/saida"]),
    ("/x" * 200, ["/x"]),
    ("/dados/saida/" + "a" * 320, ["/dados/saida"]),
    ("", ["/dados/saida"]),
    ("/dados/saida/sub", ["/outra", "/dados/saida"]),
    ("/DADOS/SAIDA", ["/dados/saida"]),
]


def test_ancora_regua_da_pasta_bate_com_a_da_api(modelos):
    """⛔ Âncora do espelho front × backend.

    O par api/ × dags/ tem o anti-drift por `inspect.getsource`; entre TS e
    Python não dá para comparar fonte, então compara-se o VEREDITO nos mesmos
    casos. Sem isto, a tela promete o que o save recusa (ou pior: aceita na
    tela o que o save aceitaria por outro motivo) e a divergência só aparece
    para quem estiver montando o fluxo."""
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "..", "api"))
    from services import email_mime as em

    da_api = [em.pasta_do_anexo(pasta, raizes) is not None for pasta, raizes in CASOS_PASTA]
    do_front = modelos["pastaCruzada"]
    assert len(do_front) == len(CASOS_PASTA), "a bancada e o teste saíram de sincronia"
    divergentes = [(c, a, f) for c, a, f in zip(CASOS_PASTA, da_api, do_front) if a != f]
    assert not divergentes, f"régua do front diverge da API em: {divergentes}"
    # e o conjunto prova alguma coisa: tem caso aceito E caso recusado
    assert any(da_api) and not all(da_api)


def test_pasta_do_anexo_aceita_subpasta_e_so_dentro_da_raiz(modelos):
    """O seletor de arquivo desce da raiz até onde o arquivo está — então a
    pasta do anexo é a raiz **ou uma pasta abaixo dela**. Espelha
    `pasta_do_anexo` da API; o envio sempre mediu o caminho final contra as
    raízes, era o cadastro que recusava a subpasta."""
    raiz, subpasta, comBarra, prefixo, pontoPonto, relativo, semRaiz = modelos["pastaDentro"]
    assert raiz and subpasta and comBarra
    # `/dados/saidaX` NÃO está dentro de `/dados/saida`: prefixo de texto não basta
    assert not prefixo
    assert not pontoPonto and not relativo and not semRaiz


def test_regua_local_aceita_o_anexo_em_subpasta(modelos):
    assert modelos["anexoEmSubpasta"] == []
    assert modelos["anexoForaDaRaizAgora"] == [
        'A pasta do anexo não está entre as permitidas no Admin › E-mail']


def test_sugestao_do_marcador_de_data(modelos):
    """Escolher pelo navegador traz o arquivo DE HOJE; amanhã a corrida
    procuraria o mesmo nome. A troca é oferecida, nunca feita sozinha — nome
    com data fixa é caso legítimo."""
    o = modelos["odate"]
    assert o["comData"] == {"sugestao": "relatorio_{odate}.xlsx", "data": "20260911"}
    assert o["semData"] is None and o["jaTemMarca"] is None
    # intervalo: a tela não sabe QUAL das duas datas é a da corrida
    assert o["duasDatas"] is None
    # a mesma data repetida vira marcador nas duas posições
    assert o["datasIguais"]["sugestao"] == "lote_{odate}_parte_{odate}.csv"
    # 13º mês não é data; sequência de 10 dígitos não é AAAAMMDD
    assert o["dataInvalida"] is None and o["numeroLongo"] is None
    assert o["legivel"] == "11/09/2026"


def test_guarda_do_save_so_cobra_modelo_com_o_catalogo_em_maos(modelos):
    """A guarda local do save existe para o erro aparecer junto do nome do nó,
    em vez de um 422 com a lista crua. Ela só cobra o modelo quando recebeu a
    resposta do catálogo: sem ela (rede fora), cobrar travaria o save do fluxo
    inteiro por um erro que a tela não sabe explicar."""
    assert modelos["guardaSemCatalogo"] == []
    assert modelos["guardaNovoExigindo"] == [
        'Escolha um modelo do catálogo (Admin › E-mail exige modelo)']
    assert modelos["guardaAntigoExigindo"] == []


def test_corpo_livre_some_com_a_padronizacao_menos_para_quem_ja_esta_nele(modelos):
    """A regra que o painel aplica na lista de modelos.

    Nó NOVO com a padronização ligada abre em "Selecione um modelo…", não em
    Corpo livre — oferecer Corpo livre ali só produziria o 422 do backend. Nó
    que JÁ está em Corpo livre continua vendo a opção: escondê-la faria o
    select mostrar um modelo que a config não tem, e o nó trocaria de corpo
    sozinho no primeiro save."""
    o = modelos["opcoes"]
    assert o["livreDesligado"] == {"podeCorpoLivre": True, "faltaEscolherModelo": False}
    assert o["novoExigindo"] == {"podeCorpoLivre": False, "faltaEscolherModelo": True}
    assert o["novoExigindoComModelo"] == {"podeCorpoLivre": False, "faltaEscolherModelo": False}
    assert o["antigoEmCorpoLivre"] == {"podeCorpoLivre": True, "faltaEscolherModelo": False}
    assert o["antigoComModelo"] == {"podeCorpoLivre": False, "faltaEscolherModelo": False}


# ── Campo de destinatários (F1 da spec de tabela do SQL) ────────────────────
# O defeito que estes testes prendem: o campo guardava o ARRAY e redesenhava o
# texto com `destinatarios.join('\n')` a cada tecla. Como a separação descarta o
# pedaço vazio, o Enter (e a vírgula) sumia no mesmo instante em que era
# digitado e o 2º endereço colava no 1º — dava para cadastrar UM destinatário,
# ou colar a lista pronta, que chega inteira num `onChange` só.


def test_separa_por_linha_virgula_e_ponto_e_virgula(e):
    dois = ["ana@cvp.com.br", "bruno@cvp.com.br"]
    d = e["destinatarios"]
    assert d["umPorLinha"] == dois
    assert d["porVirgula"] == dois
    assert d["porPontoEVirgula"] == dois
    assert d["comEspacoSobrando"] == dois


def test_separador_sozinho_nao_vira_destinatario_vazio(e):
    d = e["destinatarios"]
    assert d["soSeparadores"] == [] and d["vazio"] == []
    # o que sobra na tela depois do blur é o que o nó guarda: a vírgula do fim some
    assert d["textoDeVolta"] == "ana@cvp.com.br\nbruno@cvp.com.br"


def test_repetido_some_sem_olhar_a_caixa(e):
    """Espelha `validar_destinatarios` (dags/utils/email_envio.py), que descarta
    o repetido comparando em minúsculas — endereço repetido no campo não pode
    virar dois envios para a mesma pessoa."""
    assert e["destinatarios"]["repetido"] == ["ana@cvp.com.br", "bruno@cvp.com.br"]


def test_digitar_dois_enderecos_no_painel_de_verdade(e):
    """O `PainelEmail` REAL, montado na bancada, digitado tecla a tecla.

    Este é o teste que prende o defeito: exercitar só `separarDestinatarios`
    não diria nada, porque a separação sempre funcionou — o defeito morava na
    LIGAÇÃO entre o texto que a tela mostra e a lista que o nó guarda. O palco
    da bancada faz o que o FluxoEditor faz (recebe o patch, devolve o nó novo).

    Falsificação feita à mão antes de fechar a fase: com o `value` derivado de
    `cfg.destinatarios.join('\\n')` de volta, este mesmo roteiro termina em
    `["ana@cvp.com.brbruno@cvp.com.br"]` e o teste falha."""
    p = e["painel"]
    assert p["textoNaTela"] == "ana@cvp.com.br\nbruno@cvp.com.br"
    assert p["listaDoNo"] == ["ana@cvp.com.br", "bruno@cvp.com.br"]
    assert p["rotuloDoCard"] == "2 destinatários + fluxo"


def test_painel_acompanha_mudanca_vinda_de_fora_do_campo(e):
    """Salvar o fluxo invalida a query e o editor reconstrói os nós com a
    resposta do servidor — que normaliza o domínio para minúsculas e pode não
    ter o que se digitou durante o POST. O campo precisa passar a contar a
    verdade, em vez de seguir mostrando o texto antigo.

    É por isso que a sincronização compara TEXTO com o que o campo emitiu por
    último, e não pode ser um `useEffect([cfg.destinatarios])`: a lista é um
    array novo a cada tecla, e o efeito redesenharia o campo enquanto se digita
    — exatamente o defeito que esta fase corrige."""
    v = e["painel"]["vindoDeFora"]
    assert v["antes"] == "Ana@CVP.COM.BR"
    assert v["depois"] == "Ana@cvp.com.br"


def test_campo_de_destinatarios_nao_redesenha_o_texto_a_cada_tecla():
    """Trava ESTRUTURAL, complementar aos testes de comportamento acima.

    O comportamento já é provado pela bancada, que monta o painel de verdade —
    mas o minireact NÃO roda efeitos, e o caminho mais natural para o defeito
    voltar é justamente um `useEffect([cfg.destinatarios])` "para sincronizar o
    texto", que redesenharia o campo a cada tecla sem a bancada perceber. Esta
    trava cobre esse ponto cego: o texto do campo só pode ser reescrito pelo
    próprio campo (onChange/onBlur) e pela sincronização de fora, que é feita no
    render, comparando texto."""
    fonte = (RAIZ / "ui-react/src/components/etapas/paineis/PainelEmail.tsx").read_text(encoding="utf-8")
    trecho = fonte[fonte.index('label="Destinatários"'):]
    trecho = trecho[:trecho.index("</div>")]
    assert "value={textoDest}" in trecho, "o campo voltou a derivar o texto da lista"
    assert "separarDestinatarios(e.target.value)" in trecho, "o nó precisa receber a lista separada"
    # O padrão exato do defeito, procurado só na região do campo: o comentário
    # que explica o bug corrigido cita `destinatarios.join` de propósito, e
    # varrer o arquivo inteiro faria este teste falhar por causa da explicação.
    assert "destinatarios.join" not in trecho, "o texto do campo não pode ser remontado a cada tecla"

    # Ponto cego da bancada: efeito não roda no minireact. `setTextoDest` pode
    # aparecer em três lugares e só neles — onChange, onBlur e a sincronização
    # do render. Um quarto (tipicamente dentro de um useEffect) traz o defeito
    # de volta sem que nenhum outro teste perceba.
    sem_comentarios = "\n".join(l for l in fonte.splitlines() if not l.strip().startswith("//"))
    assert sem_comentarios.count("setTextoDest(") == 3, (
        "o texto do campo passou a ser reescrito em outro lugar — se for um efeito "
        "sobre cfg.destinatarios, o campo volta a apagar o separador a cada tecla")
    assert "useEffect" not in sem_comentarios, (
        "efeito novo neste painel: confira se ele não reescreve o campo de destinatários")
