"""
dags/utils/espera.py — o PORTÃO da etapa em espera
(F5 de docs/spec-operacao-nivel-etapa.md, §5 Bloco C; decisão 3 do §7: C2,
pausa em RUNTIME, em qualquer etapa que ainda não começou).

═══════════════════════════════════════════════════════════════════════════════
POR QUE ESTE MÓDULO EXISTE FORA DO FONTE GERADO
═══════════════════════════════════════════════════════════════════════════════
O §9 da spec chama a F5 de "a fase de risco real": o portão vive no
``log_start_<job>``, que existe em TODA etapa de TODO pipeline. A mitigação
declarada é "sem linha de pausa na tabela, o caminho é byte-idêntico ao atual,
com teste de não-regressão do fonte gerado".

Manter a lógica AQUI, e não emitida como texto pela factory, é o que torna essa
mitigação verificável e barata:

  • o delta no fonte gerado é MÍNIMO e fechado — um bloco de import guardado,
    duas constantes e **uma linha** dentro do ``log_start``. É o que o teste
    ``tests/test_dag_factory_espera.py`` prova removendo o delta e comparando o
    resultado, byte a byte, com o fonte que a factory de ``main`` gerava;
  • corrigir um defeito do portão NÃO exige regerar as DAGs — o mesmo motivo
    pelo qual o ``StoredProcOperator`` mora em ``utils/job_operators.py`` e não
    é emitido inline ("mudanças não exigem regenerar", comentário da factory).

═══════════════════════════════════════════════════════════════════════════════
O QUE O PORTÃO FAZ — E, SOBRETUDO, O QUE ELE NÃO FAZ
═══════════════════════════════════════════════════════════════════════════════
Ele responde a UMA pergunta: **existe pausa PENDENTE para (pipeline,
execução, etapa)?**

  • não existe (ou a tabela não está lá) → devolve None; o ``log_start`` segue
    exatamente o caminho de sempre;
  • existe → carimba a chegada e levanta ``AirflowRescheduleException``, o modo
    do Airflow que **devolve o worker** entre as verificações (a task fica
    ``up_for_reschedule``, nenhum slot de pool nem de worker fica preso);
  • existe e o **teto** estourou → marca a pausa EXPIRADA, grava o evento de
    alerta e levanta ``RuntimeError``: pausa esquecida vira falha VISÍVEL, nunca
    pipeline pendurado em silêncio.

**Uma pergunta só, de propósito.** O cancelamento NÃO é decidido aqui: quem
cancela é a API, que falha o DagRun no Airflow e só então marca a linha como
CANCELADA (se o Airflow recusar, a linha continua PENDENTE e a etapa segue
segura). Se o portão também tratasse CANCELADA, uma linha cancelada ontem
derrubaria o rerun de amanhã — o ``ts_nodash`` é o MESMO depois de um clear
(F4). Menos estado no caminho crítico é a mitigação do §9, não economia.

⚠️ **Isto não é o ``ExternalTaskSensor`` de volta (D01).** O sensor removido do
gerador esperava o *run de outra DAG*: dependência REMOTA, com timeout de 1h
que reprovava o filho, e ocupando slot enquanto esperava. Aqui a condição é
**local** (uma linha numa tabela deste mesmo banco, lida por seek num índice
filtrado), o modo ``reschedule`` não segura recurso, o teto é configurável e
estourá-lo produz **alerta + falha explicada**, não uma reprovação muda. E,
decisivo: o portão só muda de comportamento quando um HUMANO pediu a pausa —
sem linha, ele não existe.

═══════════════════════════════════════════════════════════════════════════════
DEGRADAÇÃO (a regra que não se negocia)
═══════════════════════════════════════════════════════════════════════════════
Sem a migration 079, com a tabela ilegível ou com qualquer erro inesperado, o
portão **abre**: loga alto e devolve None. Um pipeline de produção não pode
quebrar porque o recurso novo não está lá. O preço honesto disso está dito em
voz alta: nessa situação uma pausa pedida NÃO é honrada, e o log diz isso.

CONVENÇÕES
  • Placeholder ``%s`` (pymssql — árvore ``dags/``); em ``api/`` é ``?``.
  • A conexão vem do ``MsSqlHook`` que o ``log_start`` já tem na mão
    (``hook.get_conn()`` devolve pymssql) — o mesmo padrão da guardiã.
  • Variables do Airflow com default, nada derruba o import (D47):
      ESPERA_INTERVALO_SEGUNDOS (default 60; válido 15..600)
      ESPERA_TETO_MINUTOS       (default 240; válido 1..10080) — alavanca de
                                infra para pausas SEM teto na linha; o teto
                                normal viaja na própria pausa (migration 079).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta  # datetime: só para ler a data do ts_nodash

TABELA = "dbo.etl_etapa_pausa"

# Tipos de evento gravados em dbo.etl_dependencia_evento — a MESMA tabela da
# guardiã, lida pelo painel da malha e drenada para o Teams pela fila que já
# existe (`eventos_nao_notificados` → card). Nenhum canal novo foi inventado:
# a guardiã não precisou de UMA linha de mudança para alertar a espera.
EVENTO_ESPERA = "ESPERA_ETAPA"
EVENTO_ESTOUROU = "ESPERA_ESTOUROU"

INTERVALO_PADRAO = 60
INTERVALO_MIN, INTERVALO_MAX = 15, 600
TETO_PADRAO_MIN = 240
TETO_MIN, TETO_MAX = 1, 10080

# Memória de processo para não repetir o mesmo aviso a cada etapa quando a
# tabela não existe (deploy parcial). Só evita SPAM de log — a decisão de
# degradar é tomada de novo a cada chamada, nunca em cache.
_avisou_ausente = False


def _log():
    return logging.getLogger("airflow.task")


def _var_int(nome: str, padrao: int, minimo: int, maximo: int) -> int:
    """Variable do Airflow como inteiro com faixa — o padrão da guardiã
    (``DEPENDENCIA_GUARDIA_INTERVAL_MINUTES``). Valor ausente, vazio, não
    numérico ou fora da faixa cai no default COM aviso: configuração errada
    não pode virar espera infinita nem martelada de 1 em 1 segundo.

    Só é lida quando existe pausa — no caminho normal (sem pausa) o portão não
    toca no metastore do Airflow.
    """
    try:
        from airflow.models import Variable
        bruto = Variable.get(nome, default_var=None)
    except Exception as e:  # noqa: BLE001
        _log().warning("[ESPERA] Variable %s indisponivel (%s) — usando %s",
                       nome, e, padrao)
        return padrao
    if bruto is None or str(bruto).strip() == "":
        return padrao
    try:
        valor = int(str(bruto).strip())
    except (TypeError, ValueError):
        _log().warning("[ESPERA] Variable %s='%s' nao e inteiro — usando %s",
                       nome, bruto, padrao)
        return padrao
    if valor < minimo or valor > maximo:
        _log().warning("[ESPERA] Variable %s=%s fora da faixa %s..%s — usando %s",
                       nome, valor, minimo, maximo, padrao)
        return padrao
    return valor


def intervalo_segundos() -> int:
    return _var_int("ESPERA_INTERVALO_SEGUNDOS", INTERVALO_PADRAO,
                    INTERVALO_MIN, INTERVALO_MAX)


def teto_minutos(linha: dict) -> int:
    """O teto que vale para ESTA pausa.

    Precedência: o valor gravado na LINHA (o que a tela mostrou ao operador)
    > a Variable de infra > o padrão. Teto na linha é o que impede a tela de
    mentir: mudar a Variable no meio de uma espera não muda a promessa feita a
    quem pausou.
    """
    bruto = (linha or {}).get("teto_minutos")
    try:
        valor = int(bruto) if bruto is not None else 0
    except (TypeError, ValueError):
        valor = 0
    if TETO_MIN <= valor <= TETO_MAX:
        return valor
    return _var_int("ESPERA_TETO_MINUTOS", TETO_PADRAO_MIN, TETO_MIN, TETO_MAX)


def _ausente(erro: Exception) -> bool:
    """O erro é 'a tabela não existe' (migration 079 pendente)?

    Distinguir importa: tabela ausente é deploy parcial e merece UM aviso;
    erro transitório de banco merece aviso a cada vez, porque some sozinho e
    ninguém vai investigar um log que não repete.
    """
    txt = str(erro).lower()
    return "invalid object name" in txt or "nome de objeto" in txt


def pausa_pendente(conn, pipeline: str, execution_id: str, job_name: str):
    """A pausa PENDENTE de (pipeline, execução, etapa), ou None.

    Seek direto no índice único filtrado ``ux_etapa_pausa_pendente`` (079) —
    é a consulta que roda em todo ``log_start`` e por isso ela é UMA, sem
    subconsulta e sem OBJECT_ID de reconhecimento antes (a sonda dobraria o
    custo do caminho normal; a ausência da tabela é detectada pelo erro).

    ``TOP (1) ... ORDER BY id DESC`` é cinto de segurança: o índice filtrado já
    garante no máximo uma pendente, mas ler a mais recente nunca é errado.

    ⚠️ **O tempo parado (`parado_min`) é calculado PELO BANCO** —
    ``DATEDIFF(MINUTE, aguardando_desde, GETDATE())`` — e não em Python.

    **DEFEITO ENCONTRADO NA PROVA VIVA (dev, 2026-08-03):** a 1ª versão fazia
    ``datetime.now() - aguardando_desde``. Só que ``aguardando_desde`` é escrito
    com o ``GETDATE()`` do SQL Server e ``datetime.now()`` é o relógio do
    WORKER — e os dois divergem 3 horas neste ambiente. O log da execução real
    mostrou ``aguardando liberacao ha -179 min``: com o teto comparado contra um
    número NEGATIVO, a pausa **nunca expiraria** e o pipeline ficaria pendurado
    em silêncio — exatamente o que o §5 manda impedir. No sentido contrário
    (banco adiantado) o teto estouraria na chegada.

    É a MESMA armadilha que `execucaoEtapas.ts` já registrou para a tela
    ("as duas tabelas usam relógios diferentes... misturar as duas faria a tela
    mentir"). Aqui a regra fica: **quem escreve o carimbo é quem mede o
    intervalo**.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT TOP (1) id, estado, aguardando_desde, teto_minutos, "
        "data_referencia, motivo, solicitado_por, verificacoes, "
        "DATEDIFF(MINUTE, aguardando_desde, GETDATE()) "
        "FROM " + TABELA + " "
        "WHERE pipeline_name = %s AND execution_id = %s AND job_name = %s "
        "AND estado = 'PENDENTE' ORDER BY id DESC",
        (pipeline, execution_id, job_name))
    r = cur.fetchone()
    if not r:
        return None
    return {"id": r[0], "estado": r[1], "aguardando_desde": r[2],
            "teto_minutos": r[3], "data_referencia": r[4], "motivo": r[5],
            "solicitado_por": r[6], "verificacoes": r[7], "parado_min": r[8]}


def marcar_chegada(conn, pausa_id, primeira: bool) -> None:
    """Carimba a passagem da etapa pelo portão.

    ``aguardando_desde`` só é gravado na PRIMEIRA chegada (``COALESCE``) — é a
    partir dele que o teto conta. Contar do ``solicitado_em`` seria injusto e
    errado: a pausa pode ter sido pedida horas antes de a etapa chegar ali, e o
    teto existe para medir quanto tempo o PROCESSO ficou parado, não quanto
    tempo o pedido ficou na gaveta.
    """
    cur = conn.cursor()
    cur.execute(
        "UPDATE " + TABELA + " SET "
        "aguardando_desde = COALESCE(aguardando_desde, GETDATE()), "
        "ultima_verificacao = GETDATE(), "
        "verificacoes = verificacoes + 1 "
        "WHERE id = %s", (pausa_id,))
    conn.commit()
    if primeira:
        _log().info("[ESPERA] primeira chegada da etapa ao portao (pausa id=%s)",
                    pausa_id)


def expirar(conn, pausa_id) -> bool:
    """PENDENTE → EXPIRADA, uma vez só.

    O ``AND estado = 'PENDENTE'`` faz a transição ser atômica contra a corrida
    real desta fase: o operador clicando "Liberar" no mesmo segundo em que o
    teto estoura. Quem chegar primeiro vence, e o outro lado não reescreve o
    carimbo do vencedor. ``rowcount == 1`` significa "fui EU quem expirou" — é
    o que autoriza gravar o evento e falhar.
    """
    cur = conn.cursor()
    cur.execute(
        "UPDATE " + TABELA + " SET estado = 'EXPIRADA', "
        "resolvido_em = GETDATE(), resolvido_por = 'portao', "
        "alertado_em = GETDATE() "
        "WHERE id = %s AND estado = 'PENDENTE'", (pausa_id,))
    n = cur.rowcount
    conn.commit()
    return n == 1


def data_do_evento(linha: dict, execution_id: str):
    """A data de referência do evento: a da pausa; na falta, a data embutida no
    ``ts_nodash`` (``YYYYMMDDTHHMMSS``). Evento sem data não entra na chave de
    idempotência da tabela de eventos, então adivinhar mal é melhor que não
    gravar — e o detalhe do evento nomeia a etapa de qualquer forma."""
    d = (linha or {}).get("data_referencia")
    if d is not None:
        return d
    try:
        return datetime.strptime(str(execution_id)[:8], "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def gravar_evento(conn, pipeline: str, data_ref, tipo: str, detalhe: str) -> bool:
    """Evento no caminho da casa — ``dbo.etl_dependencia_evento``, via o MESMO
    ``dependencias.gravar_evento`` da guardiã (paridade por IDENTIDADE, não por
    cópia: é a regra que a F4 estabeleceu para ``liberado()``).

    Consequência de reusar a tabela: a fila do Teams da guardiã
    (``eventos_nao_notificados`` → card) drena estes eventos **sem uma linha de
    mudança na guardiã**, e o painel da malha já os lê pela data. Inventar um
    canal novo aqui seria criar um segundo lugar onde procurar alerta.

    Limite herdado e aceito: ``ux_dep_evento_corrida`` (``ux_dep_evento`` até a
    migration 085) é único por (pipeline, data, tipo, corrida) — duas etapas do
    MESMO pipeline no MESMO dia e na MESMA corrida geram UM evento. O detalhe nomeia a primeira; a tela de execução mostra todas as
    pausas. É a mesma dedupe que JANELA_ESTOUROU usa desde a 067.

    Nunca levanta: alerta que falha não pode mudar a decisão do portão.
    """
    if data_ref is None:
        _log().warning("[ESPERA] evento %s de '%s' sem data de referencia — "
                       "nao gravado", tipo, pipeline)
        return False
    try:
        from utils import dependencias as dep
        novo = dep.gravar_evento(conn, pipeline, data_ref, tipo, detalhe)
        conn.commit()
        return bool(novo)
    except Exception as e:  # noqa: BLE001
        _log().warning("[ESPERA] evento %s de '%s' nao gravado: %s",
                       tipo, pipeline, e)
        return False


def portao(hook, pipeline: str, job_name: str, execution_id: str):
    """O portão. Chamado pelo ``log_start_<job>`` de toda etapa.

    Devolve ``None`` para SEGUIR (o caso normal e o de degradação) ou levanta:
      • ``AirflowRescheduleException`` — aguardando liberação;
      • ``RuntimeError`` — teto estourado (com evento e alerta já gravados).

    Assinatura com ``hook`` (e não com uma conexão) porque é o que o
    ``log_start`` tem na mão; a conexão é aberta e FECHADA aqui.
    """
    global _avisou_ausente
    log = _log()
    conn = None
    try:
        try:
            conn = hook.get_conn()
            linha = pausa_pendente(conn, pipeline, execution_id, job_name)
        except Exception as e:  # noqa: BLE001 — degradação: o portão ABRE
            if _ausente(e):
                if not _avisou_ausente:
                    _avisou_ausente = True
                    log.warning("[ESPERA] %s ausente (migration 079 pendente) — "
                                "portao DESLIGADO; pausas pedidas NAO serao "
                                "honradas ate a migration subir", TABELA)
            else:
                log.warning("[ESPERA] consulta de pausa de '%s/%s' falhou (%s) — "
                            "portao ABERTO nesta passagem", pipeline, job_name, e)
            return None

        if linha is None:
            return None

        # ── daqui para baixo SÓ roda quando um humano pediu a pausa ──────────
        primeira = linha.get("aguardando_desde") is None
        marcar_chegada(conn, linha["id"], primeira)
        if primeira:
            gravar_evento(
                conn, pipeline, data_do_evento(linha, execution_id),
                EVENTO_ESPERA,
                f"Etapa '{job_name}' em espera, aguardando liberacao "
                f"(pedida por {linha.get('solicitado_por') or '?'}"
                + (f": {linha['motivo']}" if linha.get("motivo") else "") + ")")

        teto = teto_minutos(linha)
        # Na primeira chegada o relógio começa AGORA (aguardando_desde acabou
        # de ser gravado): nenhuma pausa estoura o teto na própria chegada.
        # Nas demais, o minuto vem do BANCO (ver `pausa_pendente`) — nunca de
        # subtração entre relógios diferentes.
        parado = 0 if primeira else int(linha.get("parado_min") or 0)
        if parado >= teto:
            if expirar(conn, linha["id"]):
                gravar_evento(
                    conn, pipeline, data_do_evento(linha, execution_id),
                    EVENTO_ESTOUROU,
                    f"Etapa '{job_name}' esperou {int(parado)} min (teto de "
                    f"{teto} min) sem liberacao — execucao interrompida")
            log.error("[ESPERA] teto de %s min estourado na etapa '%s' "
                      "(%d min parada) — execucao interrompida",
                      teto, job_name, int(parado))
            raise _falha_sem_retry(
                f"Etapa '{job_name}' ficou {int(parado)} min em espera sem "
                f"liberacao (teto de {teto} min). A execucao foi interrompida "
                "para nao ficar pendurada em silencio — libere a pausa e "
                "reexecute a partir desta etapa.")

        espera = intervalo_segundos()
        log.info("[ESPERA] etapa '%s' aguardando liberacao ha %d min "
                 "(teto %s min) — nova verificacao em %ss",
                 job_name, int(parado), teto, espera)
        _reagendar(espera)
    finally:
        if conn is not None:
            _fechar(conn)


def _fechar(conn) -> None:
    try:
        conn.close()
    except Exception:  # noqa: BLE001
        pass


def _falha_sem_retry(mensagem: str) -> BaseException:
    """A exceção do teto estourado — ``AirflowFailException``, que **não é
    retentada**.

    ⚠️ **DEFEITO ENCONTRADO NA PROVA VIVA (dev, 2026-08-03), antes de existir.**
    A primeira versão levantava ``RuntimeError``. Só que a factory emite
    ``retries`` no ``default_args`` (``int(retries_count or 1)`` — ou seja,
    **quase todo pipeline tem retry**), e o teto já marcou a pausa como
    EXPIRADA antes de falhar. Resultado: o Airflow retentaria o
    ``log_start``, o portão não acharia mais pausa PENDENTE e **deixaria a
    etapa rodar** — o alerta sairia e a execução seguiria assim mesmo, que é
    exatamente o contrário do que o §5 promete.

    ``AirflowFailException`` é tratada pelo ``taskinstance`` com
    ``force_fail=True``: falha na hora, sem consumir nem repetir tentativa.
    Sem o Airflow importável (teste), degrada para ``RuntimeError`` — a
    mensagem é a mesma e o efeito local (levantar) também.
    """
    try:
        from airflow.exceptions import AirflowFailException
        return AirflowFailException(mensagem)
    except Exception:  # noqa: BLE001
        return RuntimeError(mensagem)


def _reagendar(segundos: int) -> None:
    """Levanta ``AirflowRescheduleException`` para daqui a ``segundos``.

    Import LAZY e dentro da função: o módulo precisa ser importável em teste
    sem Airflow de verdade, e — mais importante — a exceção só existe no
    caminho em que há pausa. O Airflow 2.11 trata essa exceção para QUALQUER
    operador (``taskinstance._execute_task``, não só sensores): a task vai para
    ``up_for_reschedule``, o worker é devolvido, o ``try_number`` é preservado
    e o scheduler a traz de volta na data pedida.
    """
    from airflow.exceptions import AirflowRescheduleException
    from airflow.utils import timezone
    raise AirflowRescheduleException(
        timezone.utcnow() + timedelta(seconds=int(segundos)))
