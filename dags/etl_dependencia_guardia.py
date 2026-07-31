"""
dags/etl_dependencia_guardia.py — a rede de segurança da malha de dependências.

O CAMINHO PRINCIPAL NÃO PASSA POR AQUI. Quem libera um dependente é o próprio
predecessor, ao concluir (F3): latência de segundos, sem polling. Esta DAG existe
para as quatro coisas que o push, sozinho, não cobre:

  1. **Ordenar o dia.** Cria a linha AGUARDANDO_DEPENDENCIA da corrente. Sem
     ela não há como afirmar "este pipeline deveria ter rodado e não rodou" —
     é o New Day Procedure do Control-M em versão mínima.
  2. **Cobrir o push perdido.** Predecessor morto entre o fim e o trigger,
     worker reiniciado, banco fora por um instante: as condições estão
     satisfeitas e ninguém disparou.
  3. **Janela estourada.** Passou da hora-limite sem liberar → alerta, e o
     pipeline fica PENDENTE, não falha (decisão do usuário).
  4. **Data de referência divergente.** O predecessor concluiu, mas carimbado
     com outro dia — em vez de nunca liberar em silêncio, diz isso.

Sobre o item 1: a ordenação é PREGUIÇOSA — a linha nasce quando algum
predecessor já tem execução na data. Prever "quem deveria rodar hoje" exigiria
reimplementar as regras de agenda que já vivem no check_agenda da DAG gerada
(blackout, dias úteis, calendário, horários específicos), e duas cópias da mesma
regra divergem. O caso do predecessor PULADO continua coberto: pular também
grava execução (F2).
"""
from __future__ import annotations

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = "etl_dependencia_guardia"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ      = "America/Sao_Paulo"

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _var_int(nome, padrao):
    try:
        from airflow.models import Variable
        return int(Variable.get(nome, default_var=padrao))
    except Exception:
        return padrao


# ── Leitura ────────────────────────────────────────────────────────────────

def _carregar_dependentes(hook):
    """Pipelines ATIVOS que têm ao menos uma dependência, com a config da janela."""
    linhas = hook.get_records(
        "SELECT DISTINCT p.pipeline_name, "
        "       CONVERT(VARCHAR(8), p.hora_virada, 108), "
        "       CONVERT(VARCHAR(8), p.nao_iniciar_antes, 108), "
        "       CONVERT(VARCHAR(8), p.hora_limite_dependencia, 108) "
        "FROM dbo.etl_pipeline p "
        "JOIN dbo.etl_pipeline_dependencia d ON d.pipeline_name = p.pipeline_name "
        "WHERE p.active = 1 AND d.tipo = 'PIPELINE'")
    return [
        {"nome": str(r[0]), "hora_virada": r[1],
         "nao_iniciar_antes": r[2], "hora_limite": r[3]}
        for r in (linhas or [])
    ]


def _virada_global(hook):
    try:
        linha = hook.get_first(
            "SELECT config_value FROM dbo.etl_app_config "
            "WHERE config_key = 'dependencia_hora_virada'")
        return linha[0] if linha else None
    except Exception:
        return None


def _execucao_na_data(hook, pipeline_name, data_referencia):
    """Status da execução mais recente do pipeline naquela data (None se não há)."""
    linha = hook.get_first(
        "SELECT TOP 1 status FROM dbo.etl_pipeline_execucao "
        "WHERE pipeline_name = %s AND data_referencia = %s "
        "ORDER BY COALESCE(inicio, criado_em) DESC, id DESC",
        parameters=(pipeline_name, data_referencia))
    return str(linha[0]) if linha else None


def _datas_recentes_com_sucesso(hook, pipeline_name, data_referencia, dias=3):
    """Datas de referência PRÓXIMAS em que o predecessor concluiu bem.

    Alimenta o alerta de divergência: sem isto, "não liberou" e "liberou com
    outro carimbo de dia" seriam indistinguíveis para quem lê o painel.
    """
    linhas = hook.get_records(
        "SELECT DISTINCT CONVERT(VARCHAR(10), data_referencia, 23) "
        "FROM dbo.etl_pipeline_execucao "
        "WHERE pipeline_name = %s AND status = 'SUCESSO' "
        "  AND data_referencia <> %s "
        "  AND data_referencia BETWEEN DATEADD(day, -%s, %s) AND DATEADD(day, %s, %s)",
        parameters=(pipeline_name, data_referencia, dias, data_referencia,
                    dias, data_referencia))
    return [str(r[0]) for r in (linhas or [])]


# ── Escrita ────────────────────────────────────────────────────────────────

def _ordenar(hook, pipeline_name, data_referencia, log):
    """Cria a corrida do dia em AGUARDANDO_DEPENDENCIA."""
    conn = hook.get_conn(); cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO dbo.etl_pipeline_execucao "
            "(pipeline_name, data_referencia, status, disparado_por, motivo) "
            "VALUES (%s,%s,'AGUARDANDO_DEPENDENCIA','guardia','corrida ordenada pela guardia')",
            (pipeline_name, data_referencia))
        conn.commit()
        log.info("[GUARDIA] %s ordenado para %s", pipeline_name, data_referencia)
    except Exception as e:
        # Índice único: o push do predecessor pode ter criado a linha no mesmo
        # instante. Não é erro — é a corrida acontecendo.
        conn.rollback()
        log.info("[GUARDIA] %s ja ordenado em %s (%s)", pipeline_name, data_referencia, e)
    finally:
        cur.close(); conn.close()


def _disparar(hook, pipeline_name, data_referencia, log) -> bool:
    """Sobe o dependente. Mesma proteção de corrida do push (F3).

    Quem consegue virar a linha de AGUARDANDO_DEPENDENCIA para EXECUTANDO é
    quem dispara — se o predecessor tomou a linha primeiro, a guardiã não faz
    nada, e vice-versa.
    """
    conn = hook.get_conn(); cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE dbo.etl_pipeline_execucao SET status='EXECUTANDO', "
            "  disparado_por='guardia', atualizado_em=GETDATE() "
            "WHERE pipeline_name=%s AND data_referencia=%s "
            "  AND status='AGUARDANDO_DEPENDENCIA'",
            (pipeline_name, data_referencia))
        tomou = cur.rowcount
        conn.commit()
    finally:
        cur.close(); conn.close()
    if not tomou:
        return False
    try:
        from airflow.api.client.local_client import Client
        Client(None, None).trigger_dag(
            dag_id=pipeline_name,
            run_id=f"guardia__{data_referencia}",
            conf={"data_referencia": str(data_referencia), "disparado_por": "guardia"},
        )
        log.info("[GUARDIA] %s DISPARADO (data ref %s) — push do predecessor nao chegou",
                 pipeline_name, data_referencia)
        return True
    except Exception as e:
        log.warning("[GUARDIA] falha ao disparar %s: %s", pipeline_name, e)
        return False


def _gravar_evento(hook, pipeline_name, data_referencia, tipo, detalhe, log) -> int:
    """Evento idempotente por (pipeline, data, tipo).

    É o índice único que impede o ciclo de 5 min de reenviar o mesmo card a
    cada passagem — mesmo padrão da supervisão DataStage.
    """
    conn = hook.get_conn(); cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM dbo.etl_dependencia_evento "
            "WHERE pipeline_name=%s AND data_referencia=%s AND tipo=%s",
            (pipeline_name, data_referencia, tipo))
        if (cur.fetchone() or [0])[0]:
            return 0
        cur.execute(
            "INSERT INTO dbo.etl_dependencia_evento "
            "(pipeline_name, data_referencia, tipo, detalhe) VALUES (%s,%s,%s,%s)",
            (pipeline_name, data_referencia, tipo, (detalhe or "")[:1000]))
        conn.commit()
        log.info("[GUARDIA] evento %s: %s (%s)", tipo, pipeline_name, detalhe)
        return 1
    except Exception as e:
        conn.rollback()
        log.warning("[GUARDIA] evento nao gravado (%s): %s", tipo, e)
        return 0
    finally:
        cur.close(); conn.close()


# ── Notificação ────────────────────────────────────────────────────────────

def _webhook_da_supervisao(hook):
    """Canal do Teams da supervisão DataStage — decisão do usuário (spec §8).

    Reusa o grupo que a supervisão já usa em vez de criar um novo: um canal a
    menos para configurar, e quem acompanha a malha é a mesma equipe. Sem
    supervisão configurada, devolve (None, None) e o evento fica gravado sem
    card — o painel (F5) continua mostrando.
    """
    try:
        linha = hook.get_first(
            "SELECT TOP 1 g.webhook_url, g.nome FROM dbo.etl_msg_grupo g "
            "WHERE g.ativo = 1 AND g.webhook_url IS NOT NULL "
            "  AND LTRIM(RTRIM(g.webhook_url)) <> '' "
            "  AND EXISTS (SELECT 1 FROM dbo.etl_ds_supervisao_job s "
            "              WHERE s.grupo_id = g.id AND s.ativo = 1) "
            "ORDER BY g.id")
        return (linha[0], linha[1]) if linha else (None, None)
    except Exception:
        return (None, None)


ROTULO_EVENTO = {
    "JANELA_ESTOUROU": ("⏰ Dependência não liberou", "attention"),
    "DATA_DIVERGENTE": ("📅 Data de referência divergente", "warning"),
}


def montar_card(evento: dict) -> dict:
    """Adaptive Card do alerta de dependência. Função pura."""
    rotulo, cor = ROTULO_EVENTO.get(evento.get("tipo") or "", ("Dependência", "default"))
    corpo = [
        {"type": "TextBlock", "text": rotulo, "size": "Large", "weight": "Bolder",
         "wrap": True, "color": cor},
        {"type": "TextBlock", "text": evento.get("pipeline") or "?", "wrap": True,
         "spacing": "None", "isSubtle": True},
        {"type": "TextBlock", "text": evento.get("detalhe") or "", "wrap": True,
         "spacing": "Medium"},
        {"type": "FactSet", "spacing": "Medium", "facts": [
            {"title": "Pipeline", "value": str(evento.get("pipeline") or "—")},
            {"title": "Data de referência", "value": str(evento.get("data_ref") or "—")},
            {"title": "Detectado", "value": str(evento.get("detectado_em") or "—")},
        ]},
    ]
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.4", "body": corpo,
            },
        }],
    }


def _notificar_pendentes(hook, log, limite=50):
    """Envia os eventos ainda não notificados. `notificado_em` só após 2xx."""
    from utils.ds_teams import enviar_card

    webhook, canal = _webhook_da_supervisao(hook)
    linhas = hook.get_records(
        "SELECT TOP (%s) id, pipeline_name, CONVERT(VARCHAR(10), data_referencia, 23), "
        "       tipo, detalhe, CONVERT(VARCHAR(19), detectado_em, 120) "
        "FROM dbo.etl_dependencia_evento WHERE notificado_em IS NULL "
        "ORDER BY detectado_em",
        parameters=(limite,))
    if not linhas:
        return 0
    if not webhook:
        log.warning("[GUARDIA] %d evento(s) sem canal configurado — gravados, sem card.",
                    len(linhas))
        return 0

    enviados = 0
    conn = hook.get_conn(); cur = conn.cursor()
    try:
        for r in linhas:
            card = montar_card({
                "tipo": r[3], "pipeline": r[1], "data_ref": r[2],
                "detalhe": r[4], "detectado_em": r[5],
            })
            ok, motivo = enviar_card(webhook, card)
            if not ok:
                # A URL nunca entra no log — o canal é citado pelo NOME.
                log.warning("[GUARDIA] card nao enviado ao canal '%s': %s", canal, motivo)
                continue
            cur.execute(
                "UPDATE dbo.etl_dependencia_evento SET notificado_em = GETDATE() WHERE id = %s",
                (r[0],))
            enviados += 1
        conn.commit()
    finally:
        cur.close(); conn.close()
    return enviados


# ── Ciclo ──────────────────────────────────────────────────────────────────

def guardar(**context):
    import logging

    from utils.data_referencia import calcular, parse_virada
    from utils.dependencias import (avaliar_liberacao, dentro_da_janela,
                                    detectar_divergencia, precisa_alertar_janela,
                                    status_dos_predecessores)

    log = logging.getLogger("airflow.task")
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    try:
        dependentes = _carregar_dependentes(hook)
    except Exception as e:
        log.warning("[GUARDIA] cadastro indisponivel (migration 067 aplicada?): %s", e)
        return {"pipelines": 0}

    if not dependentes:
        log.info("[GUARDIA] nenhum pipeline com dependencia ativa.")
        return {"pipelines": 0}

    virada_padrao = _virada_global(hook)
    agora = pendulum.now(LOCAL_TZ)
    momento = __import__("datetime").datetime(
        agora.year, agora.month, agora.day, agora.hour, agora.minute, agora.second)

    ordenados = disparados = eventos = 0
    for p in dependentes:
        try:
            virada = parse_virada(p["hora_virada"] or virada_padrao)
            data_ref = calcular(momento, virada)
            status_preds = status_dos_predecessores(hook, p["nome"], data_ref)
            if not status_preds:
                continue

            atual = _execucao_na_data(hook, p["nome"], data_ref)

            # 1. Ordenar (preguiçoso): a corrida do dia começou em algum
            #    predecessor e este ainda não tem linha.
            if atual is None and any(s is not None for s in status_preds.values()):
                _ordenar(hook, p["nome"], data_ref, log)
                atual = "AGUARDANDO_DEPENDENCIA"
                ordenados += 1

            # 2. Rede de segurança do push.
            if atual == "AGUARDANDO_DEPENDENCIA":
                liberado, pendentes = avaliar_liberacao(status_preds)
                if liberado and dentro_da_janela(p["nao_iniciar_antes"], agora):
                    if _disparar(hook, p["nome"], data_ref, log):
                        disparados += 1
                        continue

            # 3. Janela estourada — alerta, e o pipeline segue PENDENTE.
            if precisa_alertar_janela(p["hora_limite"], agora, atual):
                _, pendentes = avaliar_liberacao(status_preds)
                detalhe = (
                    f"Não liberou até {p['hora_limite']}: "
                    f"{', '.join(pendentes) if pendentes else 'nenhum predecessor executou'} "
                    f"(data de referência {data_ref})."
                )
                eventos += _gravar_evento(hook, p["nome"], data_ref,
                                          "JANELA_ESTOUROU", detalhe, log)

            # 4. Data de referência divergente.
            if atual in ("AGUARDANDO_DEPENDENCIA", None):
                datas = {}
                for nome, status in status_preds.items():
                    if status == "SUCESSO":
                        continue
                    outras = _datas_recentes_com_sucesso(hook, nome, data_ref)
                    if outras:
                        datas[nome] = ", ".join(sorted(outras))
                divergentes = detectar_divergencia(status_preds, datas)
                if divergentes:
                    detalhe = "; ".join(
                        f"{nome} concluiu em {quando}, não em {data_ref}"
                        for nome, quando in divergentes)
                    eventos += _gravar_evento(hook, p["nome"], data_ref,
                                              "DATA_DIVERGENTE", detalhe, log)
        except Exception as e:
            # Um pipeline problemático não pode parar a varredura dos outros.
            log.warning("[GUARDIA] %s: erro no ciclo (%s)", p["nome"], e)

    notificados = _notificar_pendentes(
        hook, log, limite=_var_int("DEPENDENCIA_LOTE_NOTIFICACAO", 50))

    log.info("[GUARDIA] ciclo: %d pipeline(s), %d ordenado(s), %d disparado(s), "
             "%d evento(s), %d notificado(s).",
             len(dependentes), ordenados, disparados, eventos, notificados)
    return {"pipelines": len(dependentes), "ordenados": ordenados,
            "disparados": disparados, "eventos": eventos, "notificados": notificados}


_INTERVALO = _var_int("DEPENDENCIA_GUARDIA_INTERVAL_MINUTES", 5)

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Rede de segurança da malha de dependências: ordena o dia, cobre push perdido, alerta janela e data divergente",
    schedule=f"*/{_INTERVALO} * * * *",
    start_date=pendulum.datetime(2026, 7, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,          # ciclos não podem se atropelar no mesmo disparo
    tags=["dependencias", "monitoramento", "infraestrutura"],
) as dag:
    PythonOperator(task_id="guardar", python_callable=guardar)
