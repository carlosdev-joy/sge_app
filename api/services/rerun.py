"""
api/services/rerun.py — o gesto de reexecutar a partir de uma etapa
(F4 da spec `docs/spec-operacao-nivel-etapa.md`, §4 Bloco B + decisão 1 do §7).

═══════════════════════════════════════════════════════════════════════════════
O QUE ESTA PEÇA RESOLVE
═══════════════════════════════════════════════════════════════════════════════
O rerun em si já existia: ``POST /execucoes/rerun`` faz ``clearTaskInstances``
com ``include_downstream`` sobre um dag_run concreto. O que faltava era o que a
decisão 1 do §7 exige — **a cascata como escolha explícita, com a lista de
pipelines afetados em cada opção**:

    "O modal oferece as duas opções — só este pipeline ou este e os
     dependentes (cascata) — mostrando quais pipelines seriam afetados em cada
     caso. Nunca decidir em silêncio, nos dois sentidos: nem reprocessar cadeia
     inteira sem aviso, nem deixar dependentes com dado velho achando que o
     rerun resolveu."

═══════════════════════════════════════════════════════════════════════════════
POR QUE HOJE NÃO CASCATEIA — E QUAL É O CAMINHO EXPLÍCITO
═══════════════════════════════════════════════════════════════════════════════
Quando o pai é reexecutado, o ``publish_dataset`` roda de novo no fim e chama
``_disparar_dependentes``, que para cada filho faz o **claim**
(``reservar_corrida``, dags/utils/dependencias.py). O claim é um INSERT
condicional::

    WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao
                      WHERE pipeline_name=? AND data_referencia=?
                        AND status <> 'PULADO')

Como o filho JÁ rodou naquele ODATE, existe linha e o claim devolve ``None``:
nada é disparado. **É a barreira D14 contra redisparo N×/ODATE fazendo o seu
trabalho** — e é por isso que o comportamento de hoje é "sem cascata" por
efeito colateral, não por escolha.

⚠️ **A tentação errada** seria disparar o filho por fora, direto no Airflow com
``trigger_dag``. Isso não "respeita o modelo": mata a barreira para todo mundo,
cria corrida sem claim (a classe de defeito D13/D14/D16 registrada no projeto)
e deixa a 067 contando uma história e o motor outra.

✅ **O caminho explícito escolhido** é o inverso — não furar o claim, e sim
**aposentar a corrida anterior**, deliberadamente e com dono:

  1. o gesto marca as corridas do ODATE dos dependentes com
     ``substituida_em``/``substituida_por`` (migration 078);
  2. o claim passa a ignorar corrida substituída — exatamente como já ignora
     ``'PULADO'`` (ver ``reservar_corrida``/``ordenar_corrida``);
  3. quando o ``publish_dataset`` do pai roda de novo, o push **normal** ganha
     o claim, gera um run_id NOVO e dispara o filho com o MESMO ODATE (o conf
     carrega ``data_referencia``).

O árbitro continua sendo o claim. Nenhum disparo acontece fora do motor. A
linha antiga **não é apagada nem reescrita**: mantém status, horários e
``disparado_por`` — o histórico que a fase existe para preservar. O que muda é
que ela foi explicitamente aposentada.

**Transitividade.** Cascata é o FECHO a jusante, não só os filhos diretos: se A
→ C → E, reabrir só C faria a corrida de C nova travar em E pelo mesmo claim, e
E ficaria com dado velho — o segundo erro que a decisão 1 proíbe. O fecho é
calculado com guarda de ciclo e **mostrado inteiro no modal antes de confirmar**
(§9 da spec: "o modal precisa dizer quantos pipelines e quais").

═══════════════════════════════════════════════════════════════════════════════
CONVENÇÕES
═══════════════════════════════════════════════════════════════════════════════
• Placeholder ``?`` (pyodbc — árvore api/); em dags/ é ``%s`` (pymssql).
• Todas as funções recebem ``cur`` (cursor aberto); o CHAMADOR é dono da
  transação e do commit.
• Nome de pipeline é canonizado por ``execucao_identidade.pipeline_oficial``
  antes de virar chave de dict — colação CI do banco × dict case-sensitive do
  Python é o incidente da PR #236.
"""
from __future__ import annotations

import json
import logging
from datetime import date

log = logging.getLogger("orquestra-api")

# Teto do fecho a jusante. Não é limite de negócio: é cinto de segurança contra
# grafo patológico/ciclo que a guarda de visitados não pegue. Estourar o teto
# NÃO vira silêncio — o chamador recebe `truncado=True` e a tela avisa.
MAX_FECHO = 200

# Campo usado em dbo.etl_pipeline_audit. O padrão da casa é uma linha por
# alteração com (field_name, old_value, new_value); aqui o "campo" é o gesto.
CAMPO_AUDIT = "rerun_etapa"


# ═════════════════════════════ o grafo a jusante ═════════════════════════════

def dependentes_diretos(cur, pai: str) -> list:
    """Quem depende DIRETAMENTE de ``pai`` (só PIPELINE, só dependente ativo).

    Port EXATO de ``dags/utils/dependencias.dependentes_de`` — mesmo SELECT,
    mesmo JOIN com ``etl_pipeline`` por ``active = 1``, só o placeholder muda
    (``%s`` → ``?``). O canônico continua sendo o de dags/: a cascata não pode
    prometer disparar um pipeline que o motor não dispararia.
    """
    cur.execute(
        "SELECT d.pipeline_name FROM dbo.etl_pipeline_dependencia d "
        "JOIN dbo.etl_pipeline p ON p.pipeline_name = d.pipeline_name "
        "WHERE d.depende_de = ? AND d.tipo = 'PIPELINE' AND p.active = 1",
        (pai,))
    return [str(r[0] or "").strip() for r in cur.fetchall() if r[0]]


def fecho_dependentes(cur, raiz: str) -> tuple:
    """Fecho transitivo a jusante de ``raiz`` — devolve ``(lista, truncado)``.

    Largura (BFS), para a lista sair na ordem em que a cascata realmente
    acontece: filhos diretos primeiro, netos depois. É a ordem que o operador
    lê no modal, e ela conta a história certa ("A dispara C e D; C dispara E").

    **A raiz NÃO entra na lista** — ela é o pipeline reexecutado, não um
    afetado pela cascata.

    Guarda de ciclo por ``visitados`` (casefold): o cadastro de dependências
    não impede A→B→A, e uma cascata em ciclo giraria para sempre. Teto
    ``MAX_FECHO`` como segunda barreira; estourar devolve ``truncado=True`` em
    vez de mentir que a lista está completa.
    """
    raiz_k = str(raiz or "").strip().casefold()
    visitados = {raiz_k}
    fila = [raiz]
    saida: list = []
    truncado = False
    while fila:
        atual = fila.pop(0)
        try:
            filhos = dependentes_diretos(cur, atual)
        except Exception as e:  # noqa: BLE001 — grafo indisponível não vira "sem dependentes"
            log.warning("[RERUN] dependentes de '%s' indisponiveis: %s", atual, e)
            raise
        for f in filhos:
            k = f.strip().casefold()
            if k in visitados:
                continue
            visitados.add(k)
            if len(saida) >= MAX_FECHO:
                truncado = True
                return saida, truncado
            saida.append(f)
            fila.append(f)
    return saida, truncado


# ══════════════════════════ as corridas de cada afetado ══════════════════════

def tem_coluna_substituida(cur) -> bool:
    """``etl_pipeline_execucao.substituida_em`` (migration 078) existe?

    Mesma disciplina dos guards 073/074/075: deploy parcial DEGRADA (a cascata
    fica indisponível e o gesto diz isso) em vez de estourar 'Invalid column
    name'. Qualquer falha conta como ausente.
    """
    try:
        cur.execute("SELECT COL_LENGTH('dbo.etl_pipeline_execucao', 'substituida_em')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:  # noqa: BLE001
        log.warning("[RERUN] checagem da coluna substituida_em (078) falhou: %s", e)
        return False


def corridas_do_dia(cur, pipelines: list, data_ref: date) -> dict:
    """``{casefold(pipeline): [corrida, ...]}`` das corridas VIVAS de cada
    pipeline no ODATE — as que o claim ainda considera existentes.

    "Viva" = não substituída. Uma corrida já aposentada por um rerun anterior
    não deve aparecer no modal como "corrida que será substituída": ela já foi.
    Sem a coluna da 078 (deploy parcial) todas contam como vivas — é o
    comportamento de antes desta fase.

    Consulta uma vez por pipeline (a lista é curta por construção e o índice
    ``ux_pipe_exec`` faz seek por (pipeline_name, data_referencia)); um IN
    dinâmico economizaria pouco e abriria montagem de SQL por concatenação.
    """
    tem_col = tem_coluna_substituida(cur)
    col = ", substituida_em" if tem_col else ", NULL"
    filtro = " AND substituida_em IS NULL" if tem_col else ""
    saida: dict = {}
    for p in pipelines:
        cur.execute(
            "SELECT execution_id, status, inicio, fim, disparado_por" + col + " "
            "FROM dbo.etl_pipeline_execucao "
            "WHERE pipeline_name = ? AND data_referencia = ?" + filtro,
            (p, data_ref))
        saida[p.strip().casefold()] = [
            {"run_id": str(r[0] or "") or None, "status": r[1], "inicio": r[2],
             "fim": r[3], "disparado_por": r[4], "substituida_em": r[5]}
            for r in cur.fetchall()
        ]
    return saida


def afetados(cur, raiz: str, data_ref: date) -> dict:
    """O material do modal: o que cada opção faz, com nome e número.

    Devolve::

        {"dependentes": ["C", "D", "E"],      # fecho a jusante, ordem BFS
         "truncado": False,
         "corridas": {"c": [...], ...},       # corridas VIVAS no ODATE
         "com_corrida": ["C", "D"],           # rodaram no ODATE → serão reabertos
         "sem_corrida": ["E"],                # não rodaram → nada a reabrir
         "cascata_indisponivel": False}

    A distinção ``com_corrida`` × ``sem_corrida`` é o que impede o modal de
    prometer o que não vai acontecer: reabrir um pipeline que **não rodou** no
    ODATE não faz nada (não há corrida a aposentar) — e ele pode rodar sozinho
    quando o pai concluir, pelo push normal. Dizer isso é diferente de listar
    todo mundo junto.
    """
    deps, truncado = fecho_dependentes(cur, raiz)
    corridas = corridas_do_dia(cur, deps, data_ref) if deps else {}
    com, sem = [], []
    for p in deps:
        # "Tem corrida a reabrir" usa o MESMO predicado de `marcar_substituidas`
        # — corrida só ORDENADA (AGUARDANDO_DEPENDENCIA) não é reaberta, porque
        # ela ainda vai rodar. Se o modal contasse uma e o gesto aposentasse
        # outra, a promessa da tela e o efeito divergiriam.
        vivas = [c for c in corridas.get(p.strip().casefold(), [])
                 if str(c.get("status") or "") != "AGUARDANDO_DEPENDENCIA"]
        (com if vivas else sem).append(p)
    return {
        "dependentes": deps,
        "truncado": truncado,
        "corridas": corridas,
        "com_corrida": com,
        "sem_corrida": sem,
        "cascata_indisponivel": not tem_coluna_substituida(cur),
    }


# ═══════════════════════════ a reabertura, de fato ═══════════════════════════

def marcar_substituidas(cur, pipelines: list, data_ref: date, usuario: str) -> int:
    """Aposenta as corridas VIVAS de ``pipelines`` no ODATE. Devolve quantas.

    É o **único** efeito da opção "com dependentes" sobre o modelo de corrida —
    e ele é aditivo: nenhum status é reescrito, nenhuma linha é apagada. A
    corrida antiga continua contando o que aconteceu (SUCESSO/FALHA, horários,
    quem disparou); ``substituida_em`` só diz que ela foi aposentada por um
    reprocesso deliberado, e ``substituida_por`` diz por quem.

    ``WHERE substituida_em IS NULL`` torna a operação idempotente: repetir o
    gesto não re-carimba corrida já aposentada (e não estraga o carimbo
    original, que é prova de auditoria).

    ⚠️ **Não toca no pipeline reexecutado.** Ele NÃO é redisparado: o
    ``clearTaskInstances`` reaproveita o MESMO dag_run e, portanto, a MESMA
    corrida na 067 (mesmo run_id). Aposentá-la faria o pai aparecer sem corrida
    viva no dia enquanto ele está rodando.
    """
    if not pipelines or not tem_coluna_substituida(cur):
        return 0
    total = 0
    # Proveniência no mesmo idioma de `disparado_por` ('malha:X (ADMIN)',
    # 'guardia', 'agenda'): quem lê a linha sabe de onde veio a aposentadoria.
    marca = f"rerun:{usuario or '?'}"[:200]
    for p in pipelines:
        # `status <> 'AGUARDANDO_DEPENDENCIA'`: corrida ORDENADA e ainda não
        # rodada não é reaberta — ela ainda vai rodar. Aposentá-la só criaria
        # uma linha morta e uma segunda ao lado, sem nada acontecer de
        # diferente.
        cur.execute(
            "UPDATE dbo.etl_pipeline_execucao "
            "SET substituida_em = GETDATE(), substituida_por = ?, "
            "    atualizado_em = GETDATE() "
            "WHERE pipeline_name = ? AND data_referencia = ? "
            "AND substituida_em IS NULL "
            "AND status <> 'AGUARDANDO_DEPENDENCIA'",
            (marca, p, data_ref))
        n = cur.rowcount
        total += n if n and n > 0 else 0
    return total


# ═════════════════════════════════ auditoria ═════════════════════════════════

def registrar_auditoria(cur, pipeline: str, usuario: str, detalhe: dict) -> bool:
    """Uma linha em ``dbo.etl_pipeline_audit`` — o padrão da casa (migration
    002): ``(pipeline_name, changed_by, field_name, old_value, new_value)``.

    ``field_name`` é o GESTO (``rerun_etapa``), ``old_value`` guarda a corrida
    de onde se partiu (dag_run + ODATE) e ``new_value`` o JSON do que foi
    pedido: de qual etapa, com ou sem cascata, e quais pipelines foram
    reabertos. Fica tudo numa linha só porque a pergunta que a auditoria
    responde é uma só — "quem mandou reexecutar o quê, quando, e com que
    alcance".

    **Nunca levanta**: falhar em auditar não pode derrubar um rerun que o
    Airflow já aceitou (seria pior — o efeito aconteceu e o registro sumiu).
    Devolve False e loga em nível de alerta.
    """
    try:
        antes = json.dumps({
            "dag_run_id": detalhe.get("dag_run_id"),
            "data_referencia": detalhe.get("data_referencia"),
            "execution_id": detalhe.get("execution_id"),
        }, ensure_ascii=False)
        depois = json.dumps({
            "task_id": detalhe.get("task_id"),
            "cascata": bool(detalhe.get("cascata")),
            "dependentes_reabertos": detalhe.get("dependentes_reabertos") or [],
            "corridas_substituidas": detalhe.get("corridas_substituidas"),
            "tasks_limpas": detalhe.get("tasks_limpas"),
        }, ensure_ascii=False)
        cur.execute(
            "INSERT INTO dbo.etl_pipeline_audit "
            "(pipeline_name, changed_by, field_name, old_value, new_value) "
            "VALUES (?, ?, ?, ?, ?)",
            (pipeline, (usuario or "?")[:100], CAMPO_AUDIT, antes[:4000], depois[:4000]))
        return True
    except Exception as e:  # noqa: BLE001 — auditoria nunca derruba o gesto
        log.warning("[RERUN] auditoria de '%s' nao gravada: %s", pipeline, e)
        return False


# ════════════════════════ o corpo do clear (uma autoridade) ══════════════════

def marcador_inicio(task_id: str) -> str:
    """Nome da task que MARCA o início da etapa — a convenção da factory
    (``dags/etl_dag_factory.py``): ``log_start_<job_name>``, e no grafo gerado
    ``task_id == job_name`` para toda etapa."""
    return f"log_start_{str(task_id or '').strip()}"


def task_ids_do_clear(task_id: str, tasks_da_dag) -> list:
    """As tasks a limpar para reexecutar a etapa ``task_id`` DE VERDADE.

    ⚠️ **DEFEITO ENCONTRADO NA PROVA VIVA (dev, 2026-08-03) — e ele é ANTIGO.**
    O clear com ``include_downstream`` a partir da task da etapa **não inclui o
    ``log_start_<etapa>``**, porque ele é UPSTREAM dela
    (``log_start_x >> x >> log_end_x``). Consequência medida numa execução
    real: reexecutando a partir de ``proc_meio``, o ``log_start_proc_meio``
    ficou com ``try_number=1`` (não rodou) e a linha da telemetria manteve o
    ``start_time`` da tentativa ANTERIOR, ganhando só o ``end_time`` novo —
    duração reportada de 89s para uma execução de ~10s.

    Isso vale para o rerun que JÁ existia (modal de Logs / Dashboard): é um bug
    de produção que estava escondido porque ninguém comparava as duas pontas.
    A migration 058 chegou a tratar o sintoma na SP ("reprocesso reinicia o
    relógio"), mas o ramo dela nunca era alcançado — o ``log_start`` não
    rodava.

    E é também o que faz ou não faz a contagem de tentativas funcionar: quem
    decide que houve tentativa nova é o ``log_start``. Sem ele, a reexecução
    volta a SOBRESCREVER em silêncio, que é exatamente o que a decisão 2 manda
    acabar.

    Por isso o marcador entra na lista quando ele EXISTE na DAG. Quando não
    existe (task que não é etapa, DAG de shape antigo, lista indisponível), a
    lista é ``[task_id]`` — o comportamento de antes, byte a byte.

    Mandar os dois é deliberado: o downstream de ``log_start_x`` já contém
    ``x``, mas nomear a etapa explicitamente mantém o corpo legível e imune a
    uma mudança de fiação do gerador.
    """
    tid = str(task_id or "").strip()
    nomes = {str(t).strip() for t in (tasks_da_dag or [])}
    marcador = marcador_inicio(tid)
    return [marcador, tid] if marcador in nomes else [tid]


def corpo_clear(dag_run_id: str, task_id: str, *, dry_run: bool = False,
                task_ids=None) -> dict:
    """O corpo do ``POST /api/v1/dags/{dag}/clearTaskInstances``.

    Existe como função para que a **prévia** e a **execução** usem exatamente o
    mesmo corpo, mudando só ``dry_run``. Um modal que promete N etapas e um
    clear que limpa M seria a mentira mais fácil de cometer nesta fase — e a
    mais difícil de perceber.

    Os campos, e por que cada um:
      • ``dag_run_id`` SEMPRE presente — sem ele o Airflow limpa a task em
        TODOS os dag_runs da DAG e ``reset_dag_runs`` re-enfileira todos
        (reprocessamento em massa). É a guarda já registrada no rerun de
        produção; ela não se afrouxa aqui.
      • ``task_ids`` — por padrão só a etapa (o comportamento histórico);
        ``task_ids_do_clear`` acrescenta o ``log_start_<etapa>`` quando ele
        existe, pelo motivo documentado lá.
      • ``include_downstream`` — é o sentido do gesto: retomar DAQUI para
        frente.
      • ``include_upstream``/``include_past``/``include_future`` False — o
        gesto é sobre esta corrida e deste ponto adiante, nada mais.
      • ``reset_dag_runs`` — sem ele as tasks ficam limpas e o dag_run
        terminado; nada roda.
      • ``only_failed: False`` — ver abaixo. **É o campo mais importante do
        corpo e o que estava faltando.**

    ⚠️ **DEFEITO ANTIGO ENCONTRADO NA PROVA VIVA (dev, 2026-08-03).**
    ``only_failed`` do ``clearTaskInstances`` tem default **True** no Airflow —
    e o rerun nunca o enviou. Consequência medida no dev, com dry_run real:

        task_ids=[http_saude]  (estado SUCCESS)  →  http_saude NÃO entra na
        lista de limpeza; só as tasks FALHAS a jusante entram.

    Ou seja: **o rerun "a partir de uma etapa" silenciosamente NÃO reexecutava
    a etapa escolhida** sempre que ela não estivesse falha. O defeito ficou
    invisível todo esse tempo porque o botão só aparecia com status FAILED —
    e a F4 é exatamente a fase que tira essa restrição (§4: "não depender de
    FAILED — retomar a partir de uma etapa SUCCESS é legítimo"). Sem este
    campo, o requisito (b) do §4 seria impossível de cumprir.

    Dois efeitos colaterais, ambos corretos e desejados:
      • o ``log_start_<etapa>`` (sempre SUCCESS) passa a ser limpo de fato —
        é o que reinicia o relógio da etapa e o que faz a tentativa ser
        contada (ver ``task_ids_do_clear``);
      • um ramo PARALELO que concluiu com o dado velho também é refeito.
        Antes ele ficava intacto a jusante de uma etapa reprocessada,
        guardando resultado calculado sobre dado que acabou de mudar —
        a mesma classe de problema que esta spec existe para acabar.
    """
    return {
        "dry_run": bool(dry_run),
        "dag_run_id": dag_run_id,
        "task_ids": list(task_ids) if task_ids else [task_id],
        "include_downstream": True,
        "include_future": False,
        "include_past": False,
        "include_upstream": False,
        "only_failed": False,
        "reset_dag_runs": True,
    }


def etapas_do_clear(task_instances: list, desenho: list) -> dict:
    """Traduz a resposta do ``dry_run`` do Airflow para a linguagem da tela.

    O Airflow devolve TASKS (``log_start_x``, ``x``, ``log_end_x``,
    ``publish_dataset``, cards do Teams…). O operador raciocina em ETAPAS. A
    tradução casa o ``task_id`` com o ``job_name`` do desenho (casefold) e
    separa o resto em ``tasks_de_apoio`` — que **não some**: some seria
    esconder que o publish_dataset e os cards também vão rodar de novo, e é
    justamente o publish_dataset que faz o push da cascata.

    Devolve ``{"etapas": [...], "tasks_de_apoio": N, "total_tasks": N}``.
    """
    nomes = {}
    for no in desenho or []:
        jn = str(no.get("job_name") or "").strip()
        if jn:
            nomes[jn.casefold()] = jn
    etapas, apoio = [], 0
    vistos = set()
    for ti in task_instances or []:
        tid = str((ti or {}).get("task_id") or "").strip()
        if not tid:
            continue
        oficial = nomes.get(tid.casefold())
        if oficial and oficial.casefold() not in vistos:
            vistos.add(oficial.casefold())
            etapas.append(oficial)
        elif not oficial:
            apoio += 1
    return {"etapas": etapas, "tasks_de_apoio": apoio,
            "total_tasks": len(task_instances or [])}
