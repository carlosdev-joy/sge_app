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

import ast
import json
import logging
import os
from datetime import date
from pathlib import Path

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
    não impede A→B→A, e um cascata em ciclo giraria para sempre. Teto
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


# ═════════════ o dags/ deployado entende o carimbo? (deploy parcial) ═════════
# ⚠️ **DEFEITO CORRIGIDO AQUI: "078 sim / dags não".**
# `tem_coluna_substituida()` responde sobre o BANCO. Se o operador aplicar as
# migrations e NÃO deployar `dags/`, a API oferecia a cascata, carimbava as
# corridas (rowcount > 0) e respondia "2 dependentes reabertos" — enquanto o
# push antigo ignorava o carimbo: **nenhum dependente rodava**, e as corridas
# ficavam aposentadas para sempre. A API afirmava o que não podia garantir.
#
# A pergunta certa tem duas metades — banco E motor — e esta é a segunda. O
# meio escolhido, entre os três avaliados:
#
#   (a) ✅ **ler a declaração de capacidade do módulo do motor.** O container
#       da API monta `${AIRFLOW_PROJ_DIR}/dags:/opt/airflow/dags:ro`
#       (docker-compose.yaml, serviço orquestra-api) — o MESMO bind mount que
#       o scheduler e o worker usam rw. Ler `utils/dependencias.py` de lá é
#       ler o código que o motor vai importar, não uma cópia nem um palpite.
#       Custo: um `os.stat` por chamada (o parse é cacheado por mtime+tamanho).
#   (b) ❌ o próprio `dags/` registrar a capacidade numa tabela na 1ª execução:
#       exigiria migration nova e um carimbo que SOBREVIVE ao rollback — o
#       banco continuaria dizendo "sei fazer" depois de voltar o dags/. Trocar
#       uma mentira por outra.
#   (c) ❌ perguntar ao Airflow: a REST não expõe o conteúdo de utils/, só o
#       código da DAG serializada — e `utils/` é importado em runtime.
#
# LIMITE HONESTO, registrado: isto prova o que está NO DISCO da árvore que o
# motor importa. Um worker que ficou com o módulo velho em memória (processo
# vivo desde antes do deploy) não é coberto — Airflow importa `utils/` por
# task, então a janela é a de uma task em voo. E se o arquivo não puder ser
# lido (mount ausente), a resposta é DESCONHECIDA e a cascata fica
# indisponível com mensagem acionável: é o inverso exato do defeito — na
# dúvida a API não promete.
CAPACIDADE_CASCATA = "rerun_cascata_078"
# F3 da spec-malha-execucao: "este `dags/` sabe abrir, vincular e FECHAR corrida
# de malha". A API pergunta antes de abrir corrida pelo disparo (§11.1) — a
# célula `api/` nova × `dags/` antigo é a mais provável da matriz de deploy,
# porque a etapa 7 é automática e a 5 é padrão-NÃO.
CAPACIDADE_CORRIDA = "malha_corrida_085"

CAP_OK = "ok"
CAP_AUSENTE = "dags_desatualizado"
CAP_DESCONHECIDA = "capacidade_dags_desconhecida"

_MODULO_MOTOR = ("utils", "dependencias.py")

# {caminho: ((mtime, tamanho), frozenset)} — invalida sozinho quando o deploy
# reescreve o arquivo. Sem cache, todo abrir de modal reparsaria ~1000 linhas.
# O que se guarda é o CONJUNTO declarado, e não o veredito de UMA capacidade:
# desde a F3 há dois consumidores com perguntas diferentes sobre o mesmo
# arquivo, e cachear o veredito faria a segunda pergunta responder a primeira.
_cache_capacidade: dict = {}


def caminho_modulo_motor() -> Path:
    """`<DAGS_FOLDER>/utils/dependencias.py` — o módulo do motor visto pela
    API. `DAGS_FOLDER` é a MESMA variável que admin/sync/lineage já usam."""
    base = os.environ.get("DAGS_FOLDER", "/opt/airflow/dags")
    return Path(base).joinpath(*_MODULO_MOTOR)


def _capacidades_declaradas(fonte: str) -> set:
    """Nomes em ``CAPACIDADES = (...)`` no nível do módulo, por AST.

    AST e não regex/`in`: um `grep` casaria com a palavra dentro de um
    comentário ou de uma docstring (inclusive a que EXPLICA a capacidade), e
    aí a sonda diria "sim" para um dags/ que só fala do assunto. E não import:
    importar o módulo do motor dentro da API acopla as duas árvores de deploy
    — exatamente o que o port de `services/dependencias.py` existe para
    evitar.
    """
    try:
        arvore = ast.parse(fonte)
    except SyntaxError as e:
        log.warning("[RERUN] modulo do motor ilegivel (%s)", e)
        return set()
    achadas: set = set()
    for no in arvore.body:
        if not isinstance(no, ast.Assign):
            continue
        alvos = [a.id for a in no.targets if isinstance(a, ast.Name)]
        if "CAPACIDADES" not in alvos:
            continue
        valor = no.value
        if isinstance(valor, (ast.Tuple, ast.List, ast.Set)):
            for elt in valor.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    achadas.add(elt.value)
    return achadas


def capacidade_dags(caminho=None, capacidade: str = CAPACIDADE_CASCATA) -> str:
    """O `dags/` deployado declara `capacidade`?

    Devolve ``CAP_OK`` | ``CAP_AUSENTE`` (arquivo lido, sem a declaração:
    dags/ antigo) | ``CAP_DESCONHECIDA`` (não deu para ler: mount ausente,
    permissão, I/O). As três respostas são distintas de propósito — cada uma
    tem uma frase diferente para o operador, e nenhuma delas é "pode ir".

    `capacidade` é parâmetro desde a F3 da spec-malha-execucao, e o default é o
    da cascata para que todo call site anterior siga idêntico. A sonda é a mesma
    porque a pergunta é a mesma ("o que está NO DISCO da árvore que o motor
    importa"): duplicá-la para a corrida faria nascer uma segunda régua de
    deploy parcial, com um cache próprio e um bug próprio.
    """
    p = Path(caminho) if caminho else caminho_modulo_motor()
    try:
        st = p.stat()
        chave = (str(p), st.st_mtime_ns, st.st_size)
        anterior = _cache_capacidade.get(str(p))
        if anterior and anterior[0] == chave:
            declaradas = anterior[1]
        else:
            declaradas = frozenset(_capacidades_declaradas(
                p.read_text(encoding="utf-8", errors="replace")))
            _cache_capacidade[str(p)] = (chave, declaradas)
    except Exception as e:  # noqa: BLE001 — não saber é uma resposta, e ela recusa
        log.warning("[RERUN] capacidade do dags/ desconhecida (%s em %s)", e, p)
        return CAP_DESCONHECIDA
    resultado = CAP_OK if capacidade in declaradas else CAP_AUSENTE
    if resultado != CAP_OK:
        log.warning("[RERUN] dags/ deployado NAO declara '%s' — recurso "
                    "indisponivel (deploy parcial: migrations sem dags/)",
                    capacidade)
    return resultado


def razao_cascata_indisponivel(cur) -> str | None:
    """A razão pela qual a cascata NÃO pode acontecer, ou None se pode.

    As duas metades na ordem em que o operador as conserta: primeiro o banco
    (migration 078), depois o motor (deploy de dags/). Uma razão por vez —
    o modal mostra uma frase, não uma lista de tudo que falta.
    """
    if not tem_coluna_substituida(cur):
        return "migration_078_pendente"
    cap = capacidade_dags()
    return None if cap == CAP_OK else cap


def corridas_do_dia(cur, pipelines: list, data_ref: date) -> dict:
    """``{casefold(pipeline): [corrida, ...]}`` das corridas VIVAS de cada
    pipeline no ODATE — as que o claim ainda considera existentes.

    "Viva" = não substituída. Uma corrida já aposentada por um rerun anterior
    não deve aparecer no modal como "ciclo que será substituída": ela já foi.
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
         "cascata_indisponivel": False,
         "razao_indisponivel": None}          # banco OU dags/ (deploy parcial)

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
    razao = razao_cascata_indisponivel(cur)
    return {
        "dependentes": deps,
        "truncado": truncado,
        "corridas": corridas,
        "com_corrida": com,
        "sem_corrida": sem,
        "cascata_indisponivel": razao is not None,
        "razao_indisponivel": razao,
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

    ⚠️ **Não toca na corrida REEXECUTADA do pipeline.** Ela NÃO é redisparada:
    o ``clearTaskInstances`` reaproveita o MESMO dag_run e, portanto, a MESMA
    corrida na 067 (mesmo run_id). Aposentá-la faria o pai aparecer sem corrida
    viva no dia enquanto ele está rodando. As OUTRAS corridas do pai no ODATE
    são caso à parte — ver ``aposentar_irmas``.

    ⚠️ Carimbar exige as DUAS metades (banco e motor): sem a 078 não há coluna;
    com a 078 e um ``dags/`` antigo o carimbo não seria lido por ninguém e as
    corridas ficariam aposentadas para sempre, sem nada rodar de novo.
    """
    if not pipelines or razao_cascata_indisponivel(cur) is not None:
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


def reviver_corrida(cur, pipeline: str, data_ref: date, run_id: str) -> int:
    """Marca a corrida REEXECUTADA como EXECUTANDO — e a traz de volta à VIDA.

    Devolve o `rowcount` do UPDATE (0 = nenhuma linha casou; o chamador avisa).

    ⚠️ **DEFEITO CORRIGIDO AQUI: reexecutar corrida já APOSENTADA criava um
    SUCESSO invisível para sempre.** `aposentar_irmas` carimba
    `substituida_em` nas OUTRAS corridas do ODATE, e **nenhum caminho do
    projeto limpava esse carimbo** (`grep -rn "substituida_em" api/ dags/ sql/`
    não tinha um `= NULL` sequer). Num pipeline que roda 2×/dia:

      1. reexecutar a corrida das 18:00 aposenta a das 06:00;
      2. reexecutar depois a das 06:00 — ela era marcada EXECUTANDO
         **mantendo o carimbo**, e ao concluir gravava SUCESSO ainda
         carimbada;
      3. a partir daí `liberado()` e `pipelines_todos_sucesso()` não enxergam
         nenhum SUCESSO VIVO no dia (as três portas ignoram corrida
         substituída, por desenho): **todo dependente fica bloqueado**,
         `MALHA_CONCLUIDA` nunca sai, e só um UPDATE manual desfaz.

    A regra que fecha o buraco é a mesma que o modelo já usa em toda parte: a
    corrida que está sendo reexecutada **é a corrida viva do momento**. Limpar
    o carimbo no MESMO UPDATE que marca EXECUTANDO é o que impede a janela
    entre "voltou a rodar" e "voltou a contar" — se fossem dois UPDATEs, uma
    falha no meio deixaria exatamente o estado que este defeito descreve.

    `substituida_por` também é limpo: um carimbo de quem aposentou uma corrida
    que não está mais aposentada é história errada, não auditoria (a auditoria
    do gesto vive em `etl_pipeline_audit`, que nunca é reescrita).

    Sem a migration 078 o UPDATE é o de antes, byte a byte (deploy parcial
    degrada — as duas colunas não existem e não há carimbo a limpar).
    """
    revive = ", substituida_em = NULL, substituida_por = NULL" \
        if tem_coluna_substituida(cur) else ""
    cur.execute(
        "UPDATE dbo.etl_pipeline_execucao "
        "SET status='EXECUTANDO', fim=NULL" + revive + ", "
        "    atualizado_em=GETDATE() "
        "WHERE pipeline_name=? AND data_referencia=? AND execution_id=?",
        (pipeline, data_ref, run_id))
    n = cur.rowcount
    return n if n and n > 0 else 0


def aposentar_irmas(cur, pipeline: str, data_ref: date, run_id: str,
                    usuario: str) -> int:
    """Aposenta as OUTRAS corridas vivas do pipeline reexecutado no ODATE —
    todas menos a escolhida. Devolve quantas.

    ⚠️ **A variante das duas corridas.** Com dois runs do mesmo pipeline no
    mesmo ODATE, o operador escolhe UM (a F2 recusa o gesto com 409 até que
    ele escolha). O carimbo de EXECUTANDO só toca o escolhido — e o outro
    continua dizendo ``SUCESSO`` na data. Como liberação é EXISTS, **um único
    SUCESSO sobrevivente basta**: o filho direto é liberado e roda com o dado
    velho antes de o reprocesso terminar, o mesmo estrago da cascata do neto.

    Por que APOSENTAR e não marcar EXECUTANDO junto: EXECUTANDO em corrida que
    ninguém está executando é órfão em RUNNING — o ``publish_dataset`` do
    reprocesso só reescreve o run_id DELE, e a irmã ficaria pendurada
    bloqueando todo dependente para sempre (a classe de defeito já registrada
    no projeto). Aposentadoria é o gesto que já existe, é o que o modelo lê nas
    três portas e é reversível na leitura: a linha mantém status, horários e
    ``disparado_por`` — some só da pergunta "existe SUCESSO vivo hoje?".

    Vale COM e SEM cascata: a marca de EXECUTANDO no pipeline reexecutado já é
    incondicional (protege o dependente que ainda não rodou de partir com dado
    velho), e isto aqui é a metade que faltava dessa mesma proteção. "Sem
    cascata" quer dizer *não reabro quem já rodou*, nunca *deixo uma corrida
    velha liberando quem ainda não rodou*.
    """
    if not run_id or razao_cascata_indisponivel(cur) is not None:
        return 0
    marca = f"rerun:{usuario or '?'}"[:200]
    cur.execute(
        "UPDATE dbo.etl_pipeline_execucao "
        "SET substituida_em = GETDATE(), substituida_por = ?, "
        "    atualizado_em = GETDATE() "
        "WHERE pipeline_name = ? AND data_referencia = ? "
        "AND execution_id <> ? "
        "AND substituida_em IS NULL "
        "AND status <> 'AGUARDANDO_DEPENDENCIA'",
        (marca, pipeline, data_ref, run_id))
    n = cur.rowcount
    return n if n and n > 0 else 0


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
