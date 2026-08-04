"""
dags/utils/malha_ciclo.py — a malha começa do ZERO (docs/spec-malha-data-unica).

Porte, para a árvore das DAGs, das duas perguntas que a API já faz antes de
disparar uma malha pela tela (F1):

  1. algum membro tem corrida VIVA? (a malha não recomeça por cima de si mesma)
  2. algum membro executou NESTE ciclo carimbando outra data de referência?

A F5 leva essas perguntas para o gatilho AUTOMÁTICO: sem elas, a proteção valia
só para quem clicava na tela, e o cron continuava partindo malha suja — que foi
como a Carga_Vida acabou com metade dos membros no dia 3 e metade no dia 4.

Placeholder `%s` (pymssql) — árvore `dags/`. O par desta lógica em `api/` usa
`?` (pyodbc); são cópias conscientes, como data_referencia/dependencias.

Nenhuma função abre conexão, commita ou faz rollback: quem chama é dono da
transação (mesma regra de utils/dependencias.py). Toda leitura degrada para
"nada a dizer" quando a tabela/coluna não existe — num deploy parcial, o
comportamento tem de ser o de antes desta fase.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

# Corrida que ainda pode andar. PULADO/FALHA/SUCESSO são terminais: não seguram
# a malha (o que segura é a FALHA pelo predicado de liberação, não por aqui).
STATUS_VIVO = ("EXECUTANDO", "AGUARDANDO_DEPENDENCIA")


def malha_do_pipeline(conn, pipeline: str):
    """Nome da malha ATIVA de que o pipeline participa, ou None.

    Pipeline em mais de uma malha devolve a primeira por nome — determinístico
    entre ciclos. É uma limitação assumida: a régua de data é da malha, e um
    membro compartilhado entre duas malhas com réguas diferentes é uma
    contradição de cadastro que a tela precisa impedir, não algo para o motor
    adivinhar em runtime."""
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 1 m.malha_name FROM dbo.etl_malha_pipeline mp "
            "JOIN dbo.etl_malha m ON m.malha_name = mp.malha_name "
            "WHERE mp.pipeline_name = %s AND m.ativo = 1 "
            "ORDER BY m.malha_name",
            (pipeline,))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception as e:  # noqa: BLE001 — sem as tabelas da 070 não há malha
        print(f"[MALHA] malha de {pipeline} indisponivel ({e}) — seguindo")
        return None


def equalizar_ligado(conn, malha: str) -> bool:
    """A malha está marcada para equalizar a data sozinha (F3, migration 081)?"""
    try:
        cur = conn.cursor()
        cur.execute("SELECT CAST(equalizar_data AS INT) FROM dbo.etl_malha "
                    "WHERE malha_name = %s", (malha,))
        row = cur.fetchone()
        return bool(row and int(row[0] or 0))
    except Exception as e:  # noqa: BLE001 — sem a 081, o default é bloquear
        print(f"[MALHA] equalizar_data de {malha} indisponivel ({e})")
        return False


def virada_da_malha(conn, malha: str):
    """A hora de virada da MALHA (081), ou None quando ela segue a global."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT hora_virada FROM dbo.etl_malha WHERE malha_name = %s",
                    (malha,))
        row = cur.fetchone()
        bruto = row[0] if row else None
        if bruto is None:
            return None
        if isinstance(bruto, time):
            return bruto
        if isinstance(bruto, datetime):
            return bruto.time()
        partes = str(bruto).split(":")
        return time(int(partes[0]), int(partes[1]))
    except Exception as e:  # noqa: BLE001
        print(f"[MALHA] hora_virada de {malha} indisponivel ({e})")
        return None


def inicio_do_ciclo(agora: datetime, virada) -> datetime:
    """Instante da virada mais recente — o começo do ciclo corrente.

    É o recorte que separa "a corrida de ontem, encerrada" (histórico legítimo)
    de "esta mesma madrugada com dois ODATEs". Sem ele, malha com histórico
    ficaria barrada para sempre."""
    v = virada if isinstance(virada, time) else time(0, 0)
    base = agora.date() if agora.time() >= v else agora.date() - timedelta(days=1)
    return datetime.combine(base, v)


def estado_do_ciclo(conn, malha: str, data_ref, desde: datetime) -> dict:
    """{'em_aberto': [...], 'divergentes': [...]} — o que segura a malha.

    Cada item é (pipeline, data_referencia, status). Falha de consulta devolve
    vazio COM log: barrar a produção inteira por um erro transitório de banco
    seria pior que o problema que esta trava existe para evitar."""
    resultado = {"em_aberto": [], "divergentes": []}
    try:
        cur = conn.cursor()
        marcadores = ",".join("%s" for _ in STATUS_VIVO)
        cur.execute(
            "SELECT e.pipeline_name, e.data_referencia, e.status "
            "FROM dbo.etl_pipeline_execucao e "
            "JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name "
            f"WHERE mp.malha_name = %s AND e.status IN ({marcadores})",
            (malha, *STATUS_VIVO))
        resultado["em_aberto"] = [(r[0], r[1], r[2]) for r in cur.fetchall()]
        cur.execute(
            "SELECT e.pipeline_name, e.data_referencia, e.status "
            "FROM dbo.etl_pipeline_execucao e "
            "JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name "
            "WHERE mp.malha_name = %s AND e.data_referencia <> %s "
            "  AND e.inicio >= %s",
            (malha, data_ref, desde))
        resultado["divergentes"] = [(r[0], r[1], r[2]) for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        print(f"[MALHA] estado do ciclo de {malha} indisponivel ({e}) — seguindo")
    return resultado


def equalizar(conn, malha: str, data_ref, divergentes: list, quem: str) -> list:
    """Recarimba as execuções divergentes para `data_ref` (F3, no automático).

    As MESMAS guardas da porta da tela: pipeline que já tem linha na data-alvo
    é PULADO (duas corridas do mesmo pipeline no mesmo ODATE seria um estado
    inexplicável), e cada mudança deixa rastro no `motivo` da linha. Devolve os
    (pipeline, de, para) efetivamente mudados — o chamador commita."""
    feitos = []
    cur = conn.cursor()
    for pipeline, origem, status in divergentes:
        try:
            cur.execute(
                "SELECT COUNT(*) FROM dbo.etl_pipeline_execucao "
                "WHERE pipeline_name = %s AND data_referencia = %s",
                (pipeline, data_ref))
            row = cur.fetchone()
            if row and int(row[0] or 0) > 0:
                print(f"[MALHA] {pipeline} nao equalizado — ja tem corrida em {data_ref}")
                continue
            cur.execute(
                "UPDATE dbo.etl_pipeline_execucao "
                "SET data_referencia = %s, atualizado_em = GETDATE(), "
                "    motivo = LEFT(ISNULL(motivo + ' | ', '') + %s, 500) "
                "WHERE pipeline_name = %s AND data_referencia = %s AND status = %s",
                (data_ref,
                 f"data de referencia equalizada de {origem} para {data_ref} "
                 f"pela malha {malha} ({quem})",
                 pipeline, origem, status))
            feitos.append((pipeline, origem, data_ref))
        except Exception as e:  # noqa: BLE001 — um pipeline não derruba os outros
            print(f"[MALHA] equalizacao de {pipeline} falhou ({e}) — seguindo")
    return feitos


def resumo(estado: dict) -> str:
    """Texto curto do que está segurando — vai para o motivo do PULADO."""
    partes = []
    if estado["em_aberto"]:
        partes.append("corrida em andamento: " + ", ".join(
            f"{p} ({s.lower()})" for p, _d, s in estado["em_aberto"][:3]))
    if estado["divergentes"]:
        partes.append("data de referencia divergente: " + ", ".join(
            f"{p} em {d}" for p, d, _s in estado["divergentes"][:3]))
    return "; ".join(partes)
