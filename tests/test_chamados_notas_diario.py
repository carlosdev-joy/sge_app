"""As anotações do chamado: onde elas realmente estão, e como chegam à tela.

Pedido do dono do produto:

    "as anotações normalmente ficam vinculadas a task, porem não exibimos os
     detalhes da task no chamado no orquestra. vamos usar a parte de anotações
     para essa estrutura do chamado trazendo as anotações da sua task."

⚠️ **O DEFEITO ERA MAIOR QUE O PEDIDO.** Investigando, `dbo.etl_chamado_nota`
estava com **zero linhas** enquanto `etl_chamado_anexo` — preenchida pelo mesmo
laço, no mesmo DAG — tinha 89. O motor consultava `sys_journal_field`, e essa
tabela é **inacessível para a conta de integração**: o ServiceNow responde
**200 com lista vazia** em vez de 403. A DAG ficava verde, o ciclo gravava
`qtd_notas=0`, e a tela dizia "nenhuma anotação" — a mesma frase que diria um
chamado que de fato não tem notas. Ninguém tinha como distinguir.

Sondado contra a instância real em 2026-08-28:

    journal element=work_notes       HTTP 200  itens=0
    journal sem filtro de element    HTTP 200  itens=0
    work_notes/comments no registro  HTTP 200  itens=1   ← o conteúdo está aqui

O conteúdo vem no próprio registro, como diário concatenado. Estes testes
prendem o parser desse diário, o lote que o busca, e a junção pai+tarefa na API.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "dags"))

sync = importlib.import_module("utils.servicenow_sync")


# ── amostras REAIS, colhidas da instância cvpsnprod em 2026-08-28 ───────────

DIARIO_HUMANO = (
    "28/08/2026 11:59:04 - Cristiane Gomes de Moura (Anotações de trabalho)\n"
    "iniciativa\n"
    "visão 360"
)

DIARIO_COM_ECO = (
    "26/08/2026 15:08:31 - Usuário de Integração Interno (Comentários)\n"
    "Comentário adicionado na tarefa SCTASK0096263 - RITM0094363 - BUCC:\n"
    "\n"
    "26/08/2026 15:08:30 - Cristiane Gomes de Moura (Comentários)\n"
    "Será realizada reunião com Andre Ezio e Thauan para definição dos campos."
)


# ═══════════ 1. o parser do diário ══════════════════════════════════════════

def test_uma_entrada_vira_uma_nota_com_autor_data_e_tipo() -> None:
    notas = sync.parsear_diario(DIARIO_HUMANO, "work_notes", "abc")
    assert len(notas) == 1
    n = notas[0]
    assert n["autor"] == "Cristiane Gomes de Moura"
    assert str(n["criado_em"]) == "2026-08-28 11:59:04"
    assert n["tipo"] == "work_notes"
    assert n["sys_id_chamado"] == "abc"


def test_a_quebra_de_linha_do_texto_e_preservada() -> None:
    """As notas trazem lista de passos e saída de comando; juntar as linhas
    numa só destrói o sentido de quem escreveu."""
    assert sync.parsear_diario(DIARIO_HUMANO, "work_notes", "abc")[0]["texto"] \
        == "iniciativa\nvisão 360"


def test_o_rotulo_traduzido_vira_o_tipo_que_a_tela_conhece() -> None:
    """A instância decide o idioma do rótulo; a tela distingue nota interna de
    comentário que o solicitante lê, e essa distinção não pode se perder."""
    assert sync.parsear_diario(DIARIO_HUMANO, "comments", "x")[0]["tipo"] == "work_notes"
    assert sync.parsear_diario(DIARIO_COM_ECO, "work_notes", "x")[0]["tipo"] == "comments"


def test_rotulo_desconhecido_cai_no_campo_de_origem() -> None:
    """Melhor o campo de onde veio do que um tipo inventado — a tela tem mapa
    fechado e mostraria o valor cru."""
    diario = "01/01/2026 10:00:00 - Alguém (Rótulo Que Não Conhecemos)\ntexto"
    assert sync.parsear_diario(diario, "comments", "x")[0]["tipo"] == "comments"


def test_varias_entradas_no_mesmo_diario() -> None:
    duas = (DIARIO_HUMANO + "\n\n"
            + "27/08/2026 09:00:00 - Outra Pessoa (Comentários)\nsegunda nota")
    notas = sync.parsear_diario(duas, "work_notes", "x")
    assert [n["texto"] for n in notas] == ["iniciativa\nvisão 360", "segunda nota"]
    assert [n["tipo"] for n in notas] == ["work_notes", "comments"]


def test_a_ultima_entrada_do_diario_nao_se_perde() -> None:
    """Um parser que só fecha a entrada ao encontrar o PRÓXIMO cabeçalho
    engole a última — e a última é a mais antiga ou a mais nova, nunca uma
    qualquer."""
    notas = sync.parsear_diario(DIARIO_COM_ECO, "comments", "x")
    assert notas[-1]["texto"].startswith("Será realizada reunião")


# ═══════════ 2. o eco da integração ═════════════════════════════════════════

def test_o_anuncio_sem_conteudo_e_descartado() -> None:
    """"Comentário adicionado na tarefa X:" não é anotação — é aviso de que
    houve uma. A nota de verdade chega espelhada, com o autor humano. Mantê-lo
    faria o histórico ter o dobro de linhas e metade de conteúdo."""
    notas = sync.parsear_diario(DIARIO_COM_ECO, "comments", "x")
    assert len(notas) == 1
    assert "Usuário de Integração Interno" not in [n["autor"] for n in notas]


def test_o_anuncio_QUE_TRAZ_TEXTO_e_mantido() -> None:
    """Descartar por prefixo apagaria conteúdo quando a outra ponta não está
    espelhada no nosso banco — e nota perdida em silêncio é o pior resultado
    possível para uma tela de histórico."""
    com_texto = ("26/08/2026 15:08:31 - Usuário de Integração Interno (Comentários)\n"
                 "Comentário adicionado na tarefa SCTASK0096263: o cliente pediu "
                 "para adiar a entrega para a próxima sexta.")
    notas = sync.parsear_diario(com_texto, "comments", "x")
    assert len(notas) == 1
    assert "adiar a entrega" in notas[0]["texto"]


# ═══════════ 3. a identidade da nota ════════════════════════════════════════

def test_o_id_e_estavel_entre_execucoes() -> None:
    """A PK é `sys_id_nota` e o diário NÃO traz sys_id nenhum. Sem id
    determinístico, cada ciclo inseriria as mesmas notas outra vez — foi o que
    o teste de idempotência em dev conferiu (996 → 996)."""
    a = sync.parsear_diario(DIARIO_HUMANO, "work_notes", "abc")[0]["sys_id_nota"]
    b = sync.parsear_diario(DIARIO_HUMANO, "work_notes", "abc")[0]["sys_id_nota"]
    assert a == b


def test_a_mesma_nota_em_chamados_diferentes_tem_ids_diferentes() -> None:
    """A PK é global: o RITM e a task guardam a MESMA nota espelhada, e um id
    igual faria uma sobrescrever a outra."""
    a = sync.parsear_diario(DIARIO_HUMANO, "work_notes", "pai")[0]["sys_id_nota"]
    b = sync.parsear_diario(DIARIO_HUMANO, "work_notes", "task")[0]["sys_id_nota"]
    assert a != b


def test_o_id_cabe_na_coluna() -> None:
    """`sys_id_nota VARCHAR(32)` (migration 094). Estourar aqui trunca no banco
    e duas notas distintas viram a mesma linha."""
    assert len(sync.parsear_diario(DIARIO_HUMANO, "work_notes", "x")[0]["sys_id_nota"]) == 32


# ═══════════ 4. o que NÃO pode ser descartado ═══════════════════════════════

@pytest.mark.parametrize("vazio", ["", "   ", "\n\n", None])
def test_diario_vazio_nao_vira_nota(vazio) -> None:
    assert sync.parsear_diario(vazio, "comments", "x") == []


def test_texto_sem_cabecalho_nao_e_jogado_fora() -> None:
    """Formato que não conhecemos vira UMA nota sem autor nem data. Conteúdo
    perdido em silêncio é pior que conteúdo mal atribuído — o operador ainda
    consegue ler e julgar."""
    notas = sync.parsear_diario("anotação solta, sem formato", "comments", "x")
    assert len(notas) == 1
    assert notas[0]["texto"] == "anotação solta, sem formato"
    assert notas[0]["criado_em"] is None


# ═══════════ 5. a busca: a tabela CERTA, e em lote ══════════════════════════

class ClienteFalso:
    """Dublê de `httpx.Client` que guarda as URLs pedidas."""

    def __init__(self, resultado=None):
        self.urls = []
        self.resultado = resultado if resultado is not None else []

    def get(self, url):
        self.urls.append(url)
        cliente = self

        class Resposta:
            status_code = 200

            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"result": cliente.resultado}

        return Resposta()


def test_a_busca_nao_usa_mais_o_journal_inacessivel() -> None:
    """O DEFEITO. `sys_journal_field` responde 200 com lista vazia para esta
    conta: voltar a ela devolve o silêncio que escondeu as notas desde sempre."""
    cli = ClienteFalso()
    sync.buscar_notas_em_lote(cli, "https://sn", ["a", "b"])
    assert cli.urls, "a busca precisa consultar alguma coisa"
    for url in cli.urls:
        assert "sys_journal_field" not in url


def test_a_busca_le_a_tabela_mae_com_os_dois_campos() -> None:
    """`incident`, `sc_req_item` e `sc_task` herdam de `task`, e é nela que
    `work_notes` e `comments` moram: uma consulta serve os três tipos."""
    cli = ClienteFalso()
    sync.buscar_notas_em_lote(cli, "https://sn", ["a"])
    url = cli.urls[0]
    assert "/api/now/table/task?" in url
    assert "work_notes" in url and "comments" in url


def test_um_lote_e_uma_consulta_so() -> None:
    """Uma chamada por chamado, na carga cheia (milhares), é a diferença entre
    minutos e horas — e cada uma passa pelo proxy da Caixa."""
    cli = ClienteFalso()
    sync.buscar_notas_em_lote(cli, "https://sn", ["a", "b", "c"])
    assert len(cli.urls) == 1
    assert "sys_idINa,b,c" in cli.urls[0]


def test_lote_vazio_nao_bate_na_rede() -> None:
    """`sysparm_query=sys_idIN` sem nada casaria com o QUE HOUVESSE."""
    cli = ClienteFalso()
    assert sync.buscar_notas_em_lote(cli, "https://sn", []) == []
    assert sync.buscar_notas_em_lote(cli, "https://sn", ["", None]) == []
    assert cli.urls == []


def test_a_busca_parseia_os_dois_campos_do_registro() -> None:
    cli = ClienteFalso([{
        "sys_id": "abc", "work_notes": DIARIO_HUMANO,
        "comments": "27/08/2026 09:00:00 - Fulano (Comentários)\nvisível ao cliente",
    }])
    notas = sync.buscar_notas_em_lote(cli, "https://sn", ["abc"])
    assert {n["tipo"] for n in notas} == {"work_notes", "comments"}
    assert all(n["sys_id_chamado"] == "abc" for n in notas)


def test_registro_sem_sys_id_nao_gera_nota_orfa() -> None:
    """Nota com `sys_id_chamado` vazio viola a FK (migration 094) e derruba o
    ciclo inteiro por causa de um registro."""
    cli = ClienteFalso([{"sys_id": "", "work_notes": DIARIO_HUMANO}])
    assert sync.buscar_notas_em_lote(cli, "https://sn", ["abc"]) == []
