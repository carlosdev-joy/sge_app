"""087 — o canal e a mensagem da notificação da malha, configuráveis.

Três coisas mudaram, e as três reusam cadastro que já existia (`etl_msg_grupo`
e `etl_msg_template`, migration 049/050 — o mesmo catálogo do nó de Notificação
das ETAPAS):

  1. a MALHA aponta para um canal (`etl_malha.grupo_id`), e os avisos dela vão
     para lá em vez do canal global da supervisão;
  2. o NÓ Notificação aponta para canal e modelo, e tem texto próprio;
  3. a PRÉVIA renderiza pela MESMA função do envio.

O item 3 é o que mais merece teste. Prévia é uma promessa sobre o que vai
chegar no celular de quem está de plantão — se ela renderizar por outro
caminho, a divergência só aparece às 3h, com o card errado já entregue.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_RAIZ = Path(__file__).parent.parent

for _mod in ("airflow", "airflow.models", "airflow.operators",
             "airflow.operators.python", "airflow.datasets", "airflow.utils",
             "airflow.utils.trigger_rule", "pendulum", "requests"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules.setdefault("pyodbc", MagicMock())

from services import msg_texto as API  # noqa: E402


@pytest.fixture(scope="module")
def dags():
    """O gêmeo de `dags/` — carregado do arquivo, como os outros testes de
    paridade fazem."""
    spec = importlib.util.spec_from_file_location(
        "ds_teams_087", _RAIZ / "dags/utils/ds_teams.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ═══════════════ 1. paridade: as duas árvores dizem o MESMO ═════════════════

def test_as_duas_arvores_interpolam_igual(dags):
    """`api/services/msg_texto.py` é port de `dags/utils/ds_teams.py`.

    Aqui a paridade é mais exigente que a dos outros gêmeos do repo: como
    nenhuma destas funções toca o banco, não há nem a diferença de placeholder
    (`%s` × `?`) para justificar divergência — o resultado tem de ser idêntico
    caractere a caractere.
    """
    casos = [
        ("A malha {malha} terminou em {data}.",
         {"malha": "Carga_Vida", "data": "2026-08-04"}),
        # placeholder desconhecido sobrevive nos dois
        ("Faltou {jobs} de {malha}", {"malha": "M1"}),
        # `None` vira vazio nos dois (o valor existe e está vazio)
        ("[{pipelines}]", {"pipelines": None}),
        # texto sem placeholder nenhum
        ("aviso fixo", {"malha": "M1"}),
        ("", {"malha": "M1"}),
    ]
    for texto, mapa in casos:
        assert API.interpolar(texto, mapa) == dags.interpolar(texto, mapa), texto


def test_as_duas_arvores_resolvem_a_precedencia_igual(dags):
    """Mensagem escrita no NÓ vence o corpo do modelo — nas duas árvores.

    Divergir aqui seria pior que divergir na interpolação: a prévia mostraria o
    texto do nó e o Teams entregaria o do modelo, ou o contrário.
    """
    cfg = {"titulo": "Do nó", "mensagem": "corpo do nó"}
    tpl = {"titulo": "Do modelo", "corpo": "corpo do modelo"}
    mapa = {"malha": "M1"}
    for c, t in [(cfg, tpl), (cfg, None), ({}, tpl), ({}, None),
                 ({"mensagem": "só o corpo"}, tpl)]:
        assert API.texto_da_notificacao(c, t, mapa) == \
            dags.texto_da_notificacao(c, t, mapa), (c, t)


def test_os_dois_oferecem_os_MESMOS_placeholders(dags):
    """O editor oferece o que o servidor sabe substituir.

    Um token oferecido na tela e desconhecido na emissão chegaria CRU ao
    celular — e o operador teria clicado num botão para pôr ele lá."""
    assert tuple(API.PLACEHOLDERS_MALHA) == tuple(dags.PLACEHOLDERS_MALHA)


# ═══════════════ 2. a precedência, e o que ela protege ══════════════════════

def test_a_mensagem_do_no_vence_o_modelo():
    """O modelo é ponto de partida, não camisa de força.

    Quem ajustou o texto para uma malha específica não pode ver o ajuste sumir
    porque outra pessoa editou o modelo compartilhado — que é justamente o
    risco de um catálogo com vários consumidores."""
    titulo, corpo = API.texto_da_notificacao(
        {"titulo": "Meu título", "mensagem": "Meu texto"},
        {"titulo": "Do catálogo", "corpo": "Texto do catálogo"},
        {})
    assert (titulo, corpo) == ("Meu título", "Meu texto")


def test_sem_texto_no_no_o_modelo_responde():
    """O caminho comum: escolher um modelo e não escrever nada."""
    titulo, corpo = API.texto_da_notificacao(
        {}, {"titulo": "Carga concluída", "corpo": "A malha {malha} terminou."},
        {"malha": "Carga_Vida"})
    assert (titulo, corpo) == ("Carga concluída", "A malha Carga_Vida terminou.")


def test_sem_no_sem_modelo_e_sem_texto_devolve_NADA():
    """`(None, None)` — e o chamador mantém a frase automática de sempre.

    Teste de AUSÊNCIA: configurar é opcional, e malha nenhuma pode ficar muda
    por não ter sido configurada. Se isto devolvesse string vazia, o detalhe do
    evento sairia com um travessão solto no fim."""
    assert API.texto_da_notificacao({}, None, {"malha": "M1"}) == (None, None)
    assert API.texto_da_notificacao(None, None, {}) == (None, None)


# ═══════════════ 3. o placeholder errado NÃO some ═══════════════════════════

def test_placeholder_desconhecido_fica_no_texto():
    """Quem escreveu `{jobs}` achando que existe precisa VER `{jobs}`.

    Apagá-lo em silêncio entregaria uma frase com um buraco onde deveria haver
    informação — e ninguém descobriria o engano. A prévia é quem avisa; a
    interpolação só não esconde."""
    assert API.interpolar("tem {malha} e {jobs}", {"malha": "M1"}) == \
        "tem M1 e {jobs}"


def test_valor_nulo_vira_vazio_e_nao_a_palavra_None():
    """`None` é "existe e está vazio". Sem isto o card diria "Pipelines: None",
    que é jargão de Python no celular de quem está de plantão."""
    assert API.interpolar("[{pipelines}]", {"pipelines": None}) == "[]"


# ═══════════════ 4. o exemplo da prévia é da MALHA de verdade ═══════════════

def test_a_previa_usa_os_membros_REAIS_da_malha():
    """Nomes inventados esconderiam o caso que quebra."""
    mapa = API.contexto_exemplo("Carga_Vida", ["CARGA_A", "CARGA_B"])
    assert mapa["malha"] == "Carga_Vida"
    assert mapa["pipelines"] == "CARGA_A, CARGA_B"
    assert mapa["quantidade"] == 2


def test_a_previa_corta_a_lista_no_MESMO_ponto_que_a_emissao(dags):
    """10 nomes, e o resto vira `(+N)` — nas duas pontas.

    A malha de 40 membros é justamente a que estoura o limite da coluna de
    detalhe. Se a prévia cortasse noutro ponto, ela mostraria uma frase que o
    Teams não recebe — e o operador ajustaria o texto com base numa mentira."""
    membros = [f"P{i:02d}" for i in range(40)]
    previa = API.contexto_exemplo("M1", membros)["pipelines"]
    # a guardiã monta o mesmo resumo na emissão
    resumo = ", ".join(membros[:10]) + f" (+{len(membros) - 10})"
    assert previa == resumo
    assert previa.endswith("(+30)")


def test_a_previa_sem_membros_nao_inventa_nada():
    """Malha recém-criada: o exemplo mostra vazio, não um nome fictício."""
    mapa = API.contexto_exemplo("NOVA", [])
    assert mapa["pipelines"] == "" and mapa["quantidade"] == 0


# ═══════════════ 5. o campo só existe se o banco souber guardar ═════════════

def test_a_tela_do_canal_da_malha_esta_ligada_ao_editor():
    """O buraco que esta correção fecha: a coluna, a API e a guardiã existiam,
    e NENHUMA tela tinha o campo.

    É o mesmo defeito que a spec inteira combate — a API aceita e ninguém
    preenche —, e ele passou porque o backend estava completo e verde. O teste
    é sobre a FIAÇÃO: o editor lê `grupo_id` do detalhe e passa ao painel de
    configuração da malha, e o painel o oferece.
    """
    editor = (_RAIZ / "ui-react/src/components/malhas/MalhaEditor.tsx").read_text()
    assert "grupoId={data?.grupo_id ?? null}" in editor
    # A CHAVE presente (e não um flag) é o que diz que a 087 passou — mesmo
    # esquema do teto: sem a coluna o campo não aparece, em vez de aparecer e
    # não gravar.
    assert "temGrupo={data ? 'grupo_id' in data : false}" in editor

    painel = (_RAIZ / "ui-react/src/components/malhas/AgendamentoInicioModal.tsx").read_text()
    assert "Canal do Teams para os avisos desta malha" in painel
    assert "canal geral (o de hoje)" in painel
    # E ele só vai ao servidor quando MUDOU: mandar a chave em todo save faria
    # um deploy sem a 087 responder `migration_087_pendente` para quem nem
    # tocou no campo.
    assert "...(grupoMudou ? { grupo_id: grupoNovo } : {})" in painel


def test_o_no_notificacao_tem_porta_no_canvas():
    """Duplo clique no nó — a MESMA porta que o Início já usava (Decisão 8).

    Sem isto o modal existiria no código e não teria como ser aberto, que é
    exatamente o estado em que o nó ficou desde a F14."""
    editor = (_RAIZ / "ui-react/src/components/malhas/MalhaEditor.tsx").read_text()
    assert "} else if (tipo === 'notificacao') {" in editor
    assert "setNotifAberta(idNo)" in editor
    assert "<NotificacaoMalhaModal" in editor
