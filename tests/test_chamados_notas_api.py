"""O detalhe do chamado junta as anotações das suas tarefas.

No ServiceNow a anotação costuma ser escrita na SCTASK, e o Orquestra não
mostra a task como card — ela é uma linha dentro do card do pedido. Ler só o
RITM é ler o chamado sem o histórico de quem o executou.

⚠️ **MEDIDO EM DEV, E O RESULTADO CONTRARIA A EXPECTATIVA.** Depois de o
coletor voltar a funcionar (ver `test_chamados_notas_diario.py`), a junção foi
medida sobre os 182 pedidos que têm nota em alguma tarefa: **nenhum ganhou uma
nota sequer**. O ServiceNow ESPELHA cada anotação nos dois lados, então o diário
do pedido já contém tudo o que está na tarefa. O que estava faltando na tela não
era a junção — era a coleta.

A junção fica, e estes testes a prendem, por duas razões concretas: ela é o que
garante o resultado quando o espelhamento não acontece (categoria com regra
própria, tarefa de outro grupo), e é ela que impede a DUPLICAÇÃO do histórico
agora que as notas existem dos dois lados no nosso banco.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "api"))

mod = importlib.import_module("routers.chamados")

PAI = "sys_pai"
TASK = "sys_task"


def nota(sys_id_nota, criado_em, texto, dono, numero, tipo="comments", autor="Fulano"):
    """Uma linha como a consulta devolve: (…, sys_id_chamado, numero)."""
    return (sys_id_nota, autor, "", criado_em, texto, tipo, dono, numero)


class CursorFalso:
    def __init__(self, linhas, falhar_com_parentesco=False):
        self.linhas = linhas
        self.falhar_com_parentesco = falhar_com_parentesco
        self.sqls = []
        self.fechado = False

    def execute(self, sql, params=None):
        self.sqls.append(sql)
        if self.falhar_com_parentesco and "pai_sys_id" in sql:
            raise RuntimeError("Invalid column name 'pai_sys_id'")

    def fetchall(self):
        # A consulta pede ORDER BY criado_em DESC; o dublê honra isso, senão
        # estaria testando uma ordenação que o banco não entregaria.
        if self.falhar_com_parentesco:
            proprias = [l for l in self.linhas if l[6] == PAI]
            return sorted(proprias, key=lambda l: l[3] or "", reverse=True)
        return sorted(self.linhas, key=lambda l: l[3] or "", reverse=True)

    def close(self):
        self.fechado = True


class ConexaoFalsa:
    def __init__(self, linhas, falhar_com_parentesco=False):
        self.linhas = linhas
        self.falhar_com_parentesco = falhar_com_parentesco
        self.cursores = []

    def cursor(self):
        c = CursorFalso(self.linhas, self.falhar_com_parentesco)
        self.cursores.append(c)
        return c


# ═══════════ 1. a junção ════════════════════════════════════════════════════

def test_a_nota_da_tarefa_aparece_no_chamado() -> None:
    conn = ConexaoFalsa([
        nota("n1", "2026-08-28 10:00:00", "só na task", TASK, "SCTASK0001"),
    ])
    notas = mod._notas_do_chamado(conn, PAI)
    assert [n["texto"] for n in notas] == ["só na task"]


def test_a_nota_da_tarefa_diz_de_onde_veio() -> None:
    """Trazer a nota sem dizer isso faria parecer que o PEDIDO foi anotado, e
    é a tarefa que o foi — atribuição errada num histórico é pior que ausência."""
    conn = ConexaoFalsa([
        nota("n1", "2026-08-28 10:00:00", "só na task", TASK, "SCTASK0001"),
    ])
    n = mod._notas_do_chamado(conn, PAI)[0]
    assert n["origem_propria"] is False
    assert n["origem_numero"] == "SCTASK0001"


def test_a_nota_do_proprio_chamado_nao_ganha_marca_de_origem() -> None:
    """"via RITM…" no histórico do próprio RITM seria ruído que confunde."""
    conn = ConexaoFalsa([
        nota("n1", "2026-08-28 10:00:00", "do pedido", PAI, "RITM0001"),
    ])
    n = mod._notas_do_chamado(conn, PAI)[0]
    assert n["origem_propria"] is True
    assert n["origem_numero"] is None


# ═══════════ 2. o dedupe ════════════════════════════════════════════════════

def test_a_mesma_nota_dos_dois_lados_aparece_uma_vez() -> None:
    """O ServiceNow espelha: medido em dev, TODA nota de tarefa tem gêmea no
    pedido. Sem dedupe, o histórico teria o dobro de linhas — e o operador
    leria duas vezes a mesma frase achando que houve duas anotações."""
    conn = ConexaoFalsa([
        nota("n1", "2026-08-28 10:00:00", "mesma frase", PAI, "RITM0001"),
        nota("n2", "2026-08-28 10:00:00", "mesma frase", TASK, "SCTASK0001"),
    ])
    notas = mod._notas_do_chamado(conn, PAI)
    assert len(notas) == 1


def test_no_empate_a_copia_do_proprio_chamado_ganha() -> None:
    """A cópia do pedido não é "via SCTASK": dizer isso de uma nota que também
    está no pedido é afirmar uma origem que o dado não sustenta."""
    conn = ConexaoFalsa([
        nota("n1", "2026-08-28 10:00:00", "mesma frase", PAI, "RITM0001"),
        nota("n2", "2026-08-28 10:00:00", "mesma frase", TASK, "SCTASK0001"),
    ])
    n = mod._notas_do_chamado(conn, PAI)[0]
    assert n["origem_propria"] is True


def test_notas_diferentes_no_mesmo_instante_nao_se_engolem() -> None:
    """Dedupe por data apenas apagaria duas anotações simultâneas — e elas
    acontecem: a integração escreve no mesmo segundo em que a pessoa anota."""
    conn = ConexaoFalsa([
        nota("n1", "2026-08-28 10:00:00", "primeira", PAI, "RITM0001"),
        nota("n2", "2026-08-28 10:00:00", "segunda", TASK, "SCTASK0001"),
    ])
    assert len(mod._notas_do_chamado(conn, PAI)) == 2


def test_o_tipo_separa_notas_de_mesmo_texto() -> None:
    """Nota interna e comentário ao solicitante com o mesmo texto são fatos
    DIFERENTES: um a equipe leu, o outro o cliente leu."""
    conn = ConexaoFalsa([
        nota("n1", "2026-08-28 10:00:00", "ok", PAI, "RITM0001", tipo="work_notes"),
        nota("n2", "2026-08-28 10:00:00", "ok", PAI, "RITM0001", tipo="comments"),
    ])
    assert len(mod._notas_do_chamado(conn, PAI)) == 2


# ═══════════ 3. a ordem ═════════════════════════════════════════════════════

def test_mais_recente_primeiro() -> None:
    """Ao abrir um chamado, o que se quer ler é o que acabou de acontecer."""
    conn = ConexaoFalsa([
        nota("n1", "2026-08-20 08:00:00", "antiga", PAI, "RITM0001"),
        nota("n2", "2026-08-28 10:00:00", "recente", TASK, "SCTASK0001"),
        nota("n3", "2026-08-24 09:00:00", "meio", PAI, "RITM0001"),
    ])
    assert [n["texto"] for n in mod._notas_do_chamado(conn, PAI)] == [
        "recente", "meio", "antiga"]


def test_a_ordem_sobrevive_a_juncao_dos_dois_lados() -> None:
    """As notas chegam em dois grupos (próprias e das tarefas) por causa do
    dedupe. Sem reordenar depois, a tela mostraria todas as do pedido e só
    então as das tarefas — uma cronologia falsa."""
    conn = ConexaoFalsa([
        nota("n1", "2026-08-20 08:00:00", "pedido antiga", PAI, "RITM0001"),
        nota("n2", "2026-08-28 10:00:00", "task recente", TASK, "SCTASK0001"),
    ])
    assert [n["texto"] for n in mod._notas_do_chamado(conn, PAI)] == [
        "task recente", "pedido antiga"]


def test_nota_sem_data_vai_para_o_fim() -> None:
    """No topo, ela empurraria para baixo justamente a que acabou de ser
    escrita — e nota sem data é a exceção, não o que se quer ler primeiro."""
    conn = ConexaoFalsa([
        nota("n1", None, "sem data", PAI, "RITM0001"),
        nota("n2", "2026-08-28 10:00:00", "com data", PAI, "RITM0001"),
    ])
    assert [n["texto"] for n in mod._notas_do_chamado(conn, PAI)] == [
        "com data", "sem data"]


# ═══════════ 4. a degradação ════════════════════════════════════════════════

def test_sem_a_migration_do_parentesco_o_chamado_mantem_as_proprias_notas() -> None:
    """`pai_sys_id` chegou na migration 090. Onde ela não passou, o chamado não
    pode perder as PRÓPRIAS notas por causa de uma coluna que só serve para
    trazer as das filhas — seria trocar um histórico incompleto por nenhum."""
    conn = ConexaoFalsa([
        nota("n1", "2026-08-28 10:00:00", "do pedido", PAI, "RITM0001"),
        nota("n2", "2026-08-28 11:00:00", "da task", TASK, "SCTASK0001"),
    ], falhar_com_parentesco=True)
    notas = mod._notas_do_chamado(conn, PAI)
    assert [n["texto"] for n in notas] == ["do pedido"]
    assert len(conn.cursores) == 2, "a segunda consulta usa um cursor NOVO"
    assert conn.cursores[0].fechado is True


def test_chamado_sem_nota_nenhuma_devolve_lista_vazia() -> None:
    """Lista vazia é resposta, não falha: quem distingue "sem notas" de "não
    consegui ler" é o `migration_ausente` da rota."""
    assert mod._notas_do_chamado(ConexaoFalsa([]), PAI) == []


@pytest.mark.parametrize("campo", ["sys_id_nota", "autor", "criado_em",
                                   "texto", "tipo", "origem_propria",
                                   "origem_numero"])
def test_a_nota_chega_a_tela_com_todos_os_campos(campo: str) -> None:
    """A tela lê estes nomes; um deles faltando vira `undefined` silencioso no
    JavaScript — que renderiza vazio em vez de erro."""
    conn = ConexaoFalsa([nota("n1", "2026-08-28 10:00:00", "t", PAI, "RITM0001")])
    assert campo in mod._notas_do_chamado(conn, PAI)[0]


def test_a_consulta_nao_traz_a_task_como_pai_de_si_mesma() -> None:
    """No espelho, `pai_sys_id` pode vir igual ao `sys_id` (auto-referência) —
    é o caso que a fila já trata em `separarFila`. Aqui isso duplicaria as
    notas do próprio chamado."""
    conn = ConexaoFalsa([])
    mod._notas_do_chamado(conn, PAI)
    sql = conn.cursores[0].sqls[0]
    assert "f.sys_id <> f.pai_sys_id" in sql
