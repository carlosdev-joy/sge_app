"""
api/services/espera.py — o gesto de PAUSAR uma etapa, liberar e cancelar
(F5 da spec `docs/spec-operacao-nivel-etapa.md`, §5 Bloco C + decisão 3 do §7:
"Pausa: RUNTIME primeiro" — C2; a pausa declarada no desenho, C1, é backlog).

═══════════════════════════════════════════════════════════════════════════════
O QUE ESTA PEÇA RESOLVE
═══════════════════════════════════════════════════════════════════════════════
"Não há como segurar o processo num ponto para conferir um número antes de
deixar seguir: hoje a alternativa é despausar/pausar DAG na mão ou deixar
quebrar de propósito" (§1 da spec).

O portão físico já existe e vive na DAG (`dags/utils/espera.py`, chamado pelo
`log_start_<job>` de toda etapa). Esta camada é a outra metade: **quem pede,
quem libera, quem cancela — e o registro de tudo isso.**

═══════════════════════════════════════════════════════════════════════════════
AS TRÊS REGRAS QUE GOVERNAM ESTE ARQUIVO
═══════════════════════════════════════════════════════════════════════════════

1. **Só pausa etapa que AINDA NÃO INICIOU.** É o limite honesto do §5 e ele é
   verificado aqui, não só explicado na tela: etapa com linha em
   `etl_job_execution` para esta execução já começou (ou já terminou), e o
   portão dela ficou para trás. Recusa 409 com a lista do que dá para pausar.

2. **Cancelar é falhar o DagRun, não marcar uma linha.** "Cancelar a execução"
   (§5) significa que o operador desistiu da corrida — então quem cancela é o
   Airflow, e a linha só vira CANCELADA **depois** de o Airflow confirmar. Se
   o Airflow recusar, a pausa continua PENDENTE e a etapa continua segura: um
   cancelamento que não pegou não pode virar "portão aberto". Essa ordem é o
   que permite ao portão fazer UMA pergunta só (existe pausa pendente?) — a
   mitigação de risco do §9 aplicada ao caminho crítico.

3. **Transição de estado é atômica.** Liberar, cancelar e expirar são todos
   `UPDATE ... WHERE estado = 'PENDENTE'` com `rowcount == 1` como resposta.
   A corrida real desta fase é o operador clicando "Liberar" no mesmo segundo
   em que o teto estoura no worker — quem chegar primeiro vence, e o outro
   recebe 409 explicando o que aconteceu, nunca um sucesso mentiroso.

CONVENÇÕES
• Placeholder `?` (pyodbc — árvore api/); em dags/ é `%s` (pymssql).
• Todas as funções recebem `cur` (cursor aberto); o CHAMADOR é dono da
  transação e do commit — o mesmo contrato de `services/rerun.py`.
• Nome de pipeline canonizado por `execucao_identidade.pipeline_oficial` antes
  de virar chave (colação CI do banco × dict case-sensitive do Python, PR #236).
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

log = logging.getLogger("orquestra-api")

TABELA = "dbo.etl_etapa_pausa"

# Campo usado em dbo.etl_pipeline_audit — o padrão da casa é uma linha por
# gesto com (field_name, old_value, new_value). Igual ao `rerun_etapa` da F4.
CAMPO_AUDIT = "pausa_etapa"

# Tipos de evento em dbo.etl_dependencia_evento — a MESMA tabela da guardiã.
EVENTO_LIBERADA = "ESPERA_LIBERADA"
EVENTO_CANCELADA = "ESPERA_CANCELADA"

ESTADOS_FINAIS = ("LIBERADA", "CANCELADA", "EXPIRADA")

TETO_PADRAO_MIN = 240
TETO_MIN, TETO_MAX = 1, 10080


# ═════════════════════════════ guardas de deploy ══════════════════════════════

def tem_tabela(cur) -> bool:
    """`dbo.etl_etapa_pausa` (migration 079) existe?

    Mesma disciplina dos guards 073/074/075/078: deploy parcial DEGRADA — a
    tela diz que o recurso está indisponível — em vez de estourar
    'Invalid object name'. Qualquer falha conta como ausente.
    """
    try:
        cur.execute("SELECT OBJECT_ID('dbo.etl_etapa_pausa', 'U')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:  # noqa: BLE001
        log.warning("[ESPERA] checagem da migration 079 falhou: %s", e)
        return False


def teto_padrao(cur) -> int:
    """Teto de espera padrão, em minutos, de `etl_app_config` (079).

    Fica no banco — e não numa Variable do Airflow — porque a TELA precisa
    mostrá-lo ao operador antes de ele pausar. O valor é copiado para a linha
    da pausa no momento da criação: o que a tela prometeu é o que o portão
    obedece, mesmo que a configuração mude depois.
    """
    try:
        cur.execute("SELECT config_value FROM dbo.etl_app_config "
                    "WHERE config_key = 'espera_teto_minutos'")
        row = cur.fetchone()
        valor = int(str(row[0]).strip()) if row and row[0] is not None else 0
    except Exception as e:  # noqa: BLE001
        log.warning("[ESPERA] leitura de espera_teto_minutos falhou: %s", e)
        return TETO_PADRAO_MIN
    return valor if TETO_MIN <= valor <= TETO_MAX else TETO_PADRAO_MIN


def normaliza_teto(bruto, padrao: int) -> int:
    """Teto pedido pelo operador, dentro da faixa; fora dela usa o padrão."""
    try:
        valor = int(bruto)
    except (TypeError, ValueError):
        return padrao
    return valor if TETO_MIN <= valor <= TETO_MAX else padrao


# ═══════════════ a DAG PUBLICADA tem portão? (o outro deploy parcial) ═════════
#
# ⚠️ **DEFEITO CORRIGIDO AQUI: pausa criada em pipeline sem portão.**
# `tem_tabela()` responde sobre o BANCO. Mas o portão que OBEDECE a pausa não
# está no banco nem no módulo `utils/espera.py`: ele é uma linha **emitida
# dentro do fonte gerado de cada DAG** (`etl_dag_factory`, no `log_start`):
#
#     if _espera is not None:
#         _espera.portao(hook, PIPELINE_NAME, job_name, execution_id)
#
# Ou seja: **DAG publicada antes da F5 não tem portão**, e só volta a ter
# depois de uma regeração (`force_all` — passo 6 do deploy). Sem esta sonda o
# operador clicava "Pausar aqui", recebia `200 {"ok": true}`, a tela pintava
# "pausa marcada" e **o pipeline passava direto**. Medido no dev em 2026-08-03:
# banco com a 079 aplicada e ZERO das 5 DAGs geradas contendo `_espera.portao`.
#
# A técnica é a MESMA que a PR #268 criou para o outro lado
# (`services/rerun.capacidade_dags`): a API monta `${AIRFLOW_PROJ_DIR}/dags`
# como `:ro` (docker-compose.yaml, serviço orquestra-api) — o MESMO bind mount
# que o scheduler e o worker usam rw. Ler o `.py` de lá é ler o código que o
# Airflow vai importar, não uma cópia nem um palpite. A diferença é o alcance:
# lá a pergunta é sobre o MOTOR (um arquivo para todos); aqui é por PIPELINE
# (cada DAG tem o seu fonte, e o `force_all` pode ter regenerado umas e não
# outras).
#
# Por que não perguntar ao Airflow: a REST expõe a DAG serializada (grafo,
# tasks), não o corpo do `log_start` — o portão é uma chamada DENTRO de uma
# PythonOperator callable, invisível ali.
#
# Por que texto e não AST (o inverso da escolha de `rerun`): lá a declaração é
# um `CAPACIDADES = (...)` no nível do módulo, que um `in` casaria dentro da
# própria docstring que explica a capacidade. Aqui o alvo é uma CHAMADA no
# corpo de uma função aninhada, e o fonte é gerado por concatenação de strings
# pela factory — a marca `_espera.portao(` só aparece no arquivo gerado se a
# factory a emitiu. (Amarração nos testes: se a factory mudar a marca, o teste
# de paridade quebra.)
#
# LIMITE HONESTO: isto prova o que está NO DISCO. Um scheduler que ainda não
# reparseou o arquivo novo não é coberto — a janela é a de um ciclo de parse.

MARCA_PORTAO = "_espera.portao("

PORTAO_OK = "ok"
PORTAO_AUSENTE = "dag_sem_portao"
PORTAO_DESCONHECIDO = "portao_desconhecido"

# ── A MESMA sonda, para a F5 da spec-malha-execucao (§12.2) ──────────────────
# `_corrida.odate(` é a marca que a factory emite quando o fonte gerado carimba
# o ODATE pela corrida da malha. A pergunta é a mesma de cima ("a DAG PUBLICADA
# já tem isto?"), a técnica é a mesma, e por isso mora aqui em vez de virar um
# segundo leitor de `generated/` com regras próprias de caminho e de cache.
#
# Por que ela é NECESSÁRIA e não decorativa: a F5 é a única fase da spec que
# exige `force_all`, e o gesto NÃO está no `deploy.sh` — é um trigger manual de
# `etl_dag_factory` com `conf={"force_all": true}`. Entre o deploy e a
# regeração, metade das DAGs carimba pela corrida e metade calcula sozinha: a
# doença com aparência de cura. Esta sonda responde POR PIPELINE quem ficou
# para trás, para o operador republicar só aquele.
#
# ⚠️ Não se usa `grep -rl "malha_execucao_id" generated/ | wc -l` contra o
# COUNT de pipelines ativos: `generated/` guarda fonte de pipeline INATIVO
# também (o deploy nunca limpa a pasta), então o total do grep é legitimamente
# ≥ o COUNT e a conferência deixa de conferir. A marca é sintática, emitida por
# concatenação pela factory, e não casa em comentário nem em código morto.
MARCA_CORRIDA = "_corrida.odate("

CORRIDA_OK = "ok"
CORRIDA_AUSENTE = "dag_sem_carimbo_de_corrida"
CORRIDA_DESCONHECIDO = "carimbo_desconhecido"

# Nome de projeto/domínio/pipeline que pode virar caminho. Vem do BANCO, mas
# concatenar em caminho o que veio de um cadastro editável sem filtrar é como
# se abre travessia de diretório — a mesma disciplina do `_DAG_ID_RE` do router.
_SEGMENTO_RE = re.compile(r"^[A-Za-z0-9_.\- ]+$")

# {caminho: ((mtime, tamanho), resultado)} — invalida sozinho quando o
# force_all reescreve o arquivo. Sem cache, todo abrir de canvas em modo
# Execução releria o fonte da DAG (que tem milhares de linhas).
_cache_portao: dict = {}


def raiz_dags() -> Path:
    """`DAGS_FOLDER` — a MESMA variável que admin/sync/lineage/rerun já usam."""
    return Path(os.environ.get("DAGS_FOLDER", "/opt/airflow/dags"))


def caminho_dag_gerada(project, domain, pipeline):
    """`<DAGS_FOLDER>/generated/<project>/<domain>/<pipeline>.py`, ou `None`.

    É EXATAMENTE como `etl_dag_factory` monta o destino::

        dest_dir  = os.path.join(output_root, "generated", project, domain)
        dest_file = os.path.join(dest_dir, f"{pname}.py")

    `None` quando algum segmento está vazio ou tem caractere que não cabe num
    nome de arquivo — e aí a resposta da sonda é DESCONHECIDA, nunca "sem
    portão": não saber montar o caminho não é prova de nada.
    """
    partes = [str(project or "").strip(), str(domain or "").strip(),
              str(pipeline or "").strip()]
    if not all(partes) or not all(_SEGMENTO_RE.match(p) for p in partes):
        return None
    proj, dom, pipe = partes
    return raiz_dags() / "generated" / proj / dom / f"{pipe}.py"


def _cadastro_do_pipeline(cur, pipeline: str):
    """`(project_name, domain)` do cadastro, ou `(None, None)`."""
    try:
        cur.execute("SELECT project_name, domain FROM dbo.etl_pipeline "
                    "WHERE pipeline_name = ?", (pipeline,))
        row = cur.fetchone()
        return (row[0], row[1]) if row else (None, None)
    except Exception as e:  # noqa: BLE001
        log.warning("[ESPERA] cadastro de '%s' indisponivel: %s", pipeline, e)
        return (None, None)


def _marca_no_arquivo(caminho, marca: str, rotulo: str,
                      valores: tuple) -> str:
    """`ok` | `ausente` | `desconhecido` para UMA marca em UM arquivo.

    As três respostas são distintas de propósito: "tem", "li o arquivo e ele
    NÃO tem" e "não deu para ler". Só a segunda é uma acusação; a terceira é
    uma dúvida, e elas têm frases e consequências diferentes.

    O cache é por `(arquivo, marca)`: duas marcas no mesmo fonte respondem
    coisas diferentes, e uma chave só faria a segunda pergunta herdar a
    resposta da primeira.
    """
    ok, ausente, desconhecido = valores
    if caminho is None:
        return desconhecido
    p = Path(caminho)
    try:
        st = p.stat()
        chave = (st.st_mtime_ns, st.st_size)
        anterior = _cache_portao.get((str(p), marca))
        if anterior and anterior[0] == chave:
            return anterior[1]
        fonte = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001 — não saber é uma resposta própria
        log.warning("[ESPERA] fonte da DAG ilegivel (%s em %s)", e, p)
        return desconhecido
    resultado = ok if marca in fonte else ausente
    _cache_portao[(str(p), marca)] = (chave, resultado)
    if resultado != ok:
        log.warning("[ESPERA] DAG publicada em %s NAO tem %s — pipeline precisa "
                    "ser republicado (force_all)", p, rotulo)
    return resultado


def portao_no_arquivo(caminho) -> str:
    """`PORTAO_OK` | `PORTAO_AUSENTE` | `PORTAO_DESCONHECIDO` para UM arquivo."""
    return _marca_no_arquivo(caminho, MARCA_PORTAO, "portao de espera",
                             (PORTAO_OK, PORTAO_AUSENTE, PORTAO_DESCONHECIDO))


def carimbo_corrida_no_arquivo(caminho) -> str:
    """`CORRIDA_OK` | `CORRIDA_AUSENTE` | `CORRIDA_DESCONHECIDO` (§12.2).

    ⚠️ O terceiro valor NÃO é ausência: "não consegui montar o caminho" e "não
    consegui ler o arquivo" não provam nada sobre o fonte publicado, e tratá-los
    como AUSENTE mandaria o operador republicar 40 pipelines por causa de um
    cadastro com espaço no nome do domínio.
    """
    return _marca_no_arquivo(caminho, MARCA_CORRIDA,
                             "o carimbo de ODATE pela corrida",
                             (CORRIDA_OK, CORRIDA_AUSENTE, CORRIDA_DESCONHECIDO))


def estado_portao(cur, pipeline: str) -> str:
    """A DAG PUBLICADA deste pipeline obedece a pausa?

    Junta as duas metades: o cadastro (projeto/domínio, que dão o caminho) e o
    fonte gerado. Cadastro incompleto → DESCONHECIDO, jamais AUSENTE.
    """
    project, domain = _cadastro_do_pipeline(cur, pipeline)
    return portao_no_arquivo(caminho_dag_gerada(project, domain, pipeline))


def estado_carimbo_corrida(cur, pipeline: str) -> str:
    """A DAG PUBLICADA deste pipeline já carimba o ODATE pela corrida? (§12.2)

    `dag_config_pendente_em` **não** serve para esta pergunta: ele responde "a
    configuração mudou desde a publicação", e não "o fonte publicado tem o
    carimbo" — uma DAG que ninguém editou tem `pendente` nulo e pode estar anos
    atrás do gerador.
    """
    project, domain = _cadastro_do_pipeline(cur, pipeline)
    return carimbo_corrida_no_arquivo(
        caminho_dag_gerada(project, domain, pipeline))


def carimbo_corrida_dos_pipelines(cur, pipelines) -> list:
    """As duas colunas do §12.2: `[{"pipeline", "sonda"}]`, na ordem recebida.

    Existe para o operador ver QUEM ficou para trás e republicar só aquele — a
    conferência agregada ("N de M") esconde exatamente a informação que resolve
    o problema.
    """
    return [{"pipeline": p, "sonda": estado_carimbo_corrida(cur, p)}
            for p in pipelines]


# Uma frase por estado, no idioma do operador — o que aconteceu e o que
# consertar. Espelha o `AVISO_CASCATA_INDISPONIVEL` da F4.
MENSAGEM_PORTAO = {
    PORTAO_AUSENTE: (
        "A DAG publicada deste pipeline NÃO tem o portão de espera: ela foi "
        "gerada antes desta funcionalidade. Uma pausa marcada aqui não "
        "seguraria nada — a execução passaria direto. Republique o pipeline "
        "(gerar DAG novamente) e a pausa volta a ser aceita."),
    PORTAO_DESCONHECIDO: (
        "não foi possível confirmar se a DAG publicada deste pipeline tem o "
        "portão de espera (o fonte gerado não pôde ser lido). Se ela tiver "
        "sido publicada antes desta funcionalidade, a pausa NÃO vai segurar a "
        "execução — republique o pipeline para ter certeza"),
}


# ═══════════════════════ "a etapa já começou?" — o limite ═════════════════════

def etapas_iniciadas(cur, pipeline: str, execution_id: str) -> set:
    """`{job_name.casefold()}` das etapas que JÁ têm linha de execução nesta
    corrida — as que não dá mais para pausar.

    Ter linha em `etl_job_execution` significa que o `log_start` da etapa
    RODOU: o portão dela já ficou para trás. Vale para RUNNING, SUCCESS e
    FAILED — em nenhum dos três a pausa teria efeito, e prometer que teria
    seria a mentira mais fácil desta fase.
    """
    cur.execute(
        "SELECT job_name FROM dbo.etl_job_execution "
        "WHERE execution_id = ? AND pipeline = ?", (execution_id, pipeline))
    return {str(r[0] or "").strip().casefold() for r in cur.fetchall() if r[0]}


# ══════════════════════════════ leitura da tela ═══════════════════════════════

def listar(cur, pipeline: str, execution_id: str) -> list:
    """Todas as pausas da execução — inclusive as resolvidas.

    O histórico faz parte da resposta de propósito: "quem liberou e quando" é
    metade do valor do gesto (§5), e uma tela que só mostra o pendente esconde
    justamente a prova de auditoria.
    """
    if not tem_tabela(cur):
        return []
    try:
        # `data_referencia` e `parado_min` entram porque a TELA os mostra —
        # a primeira versão omitia a data e o JSON saía com `data_referencia:
        # null` numa linha que tinha a data no banco (visto na prova viva). Um
        # campo prometido no contrato e sempre nulo é pior que campo ausente.
        # O minuto parado vem do BANCO (mesmo motivo do portão: o carimbo é
        # escrito com GETDATE() e misturar relógios dá tempo negativo).
        cur.execute(
            "SELECT id, job_name, task_id, estado, motivo, observacao, "
            "       teto_minutos, solicitado_por, solicitado_em, "
            "       aguardando_desde, ultima_verificacao, verificacoes, "
            "       resolvido_por, resolvido_em, alertado_em, data_referencia, "
            "       DATEDIFF(MINUTE, aguardando_desde, GETDATE()) "
            "FROM " + TABELA + " "
            "WHERE pipeline_name = ? AND execution_id = ? "
            "ORDER BY id", (pipeline, execution_id))
        return [
            {"id": r[0], "job_name": r[1], "task_id": r[2], "estado": r[3],
             "motivo": r[4], "observacao": r[5], "teto_minutos": r[6],
             "solicitado_por": r[7], "solicitado_em": r[8],
             "aguardando_desde": r[9], "ultima_verificacao": r[10],
             "verificacoes": r[11], "resolvido_por": r[12],
             "resolvido_em": r[13], "alertado_em": r[14],
             "data_referencia": r[15], "parado_min": r[16]}
            for r in cur.fetchall()
        ]
    except Exception as e:  # noqa: BLE001 — a tela nunca quebra por causa disto
        log.warning("[ESPERA] listagem de pausas de '%s/%s' falhou: %s",
                    pipeline, execution_id, e)
        return []


def por_id(cur, pausa_id: int):
    """Uma pausa pelo id — com o contexto que os gestos de liberar/cancelar
    precisam (pipeline, corrida e etapa)."""
    cur.execute(
        "SELECT id, pipeline_name, execution_id, job_name, task_id, run_id, "
        "       data_referencia, estado, motivo, teto_minutos, "
        "       solicitado_por, aguardando_desde, resolvido_por, resolvido_em "
        "FROM " + TABELA + " WHERE id = ?", (pausa_id,))
    r = cur.fetchone()
    if not r:
        return None
    return {"id": r[0], "pipeline_name": r[1], "execution_id": r[2],
            "job_name": r[3], "task_id": r[4], "run_id": r[5],
            "data_referencia": r[6], "estado": r[7], "motivo": r[8],
            "teto_minutos": r[9], "solicitado_por": r[10],
            "aguardando_desde": r[11], "resolvido_por": r[12],
            "resolvido_em": r[13]}


# ═══════════════════════════════ os três gestos ═══════════════════════════════

def criar(cur, *, pipeline: str, execution_id: str, job_name: str,
          task_id: str | None, run_id: str | None, data_ref,
          motivo: str | None, teto: int, usuario: str) -> int:
    """Cria a pausa PENDENTE e devolve o id.

    O INSERT é condicional (`WHERE NOT EXISTS ... estado='PENDENTE'`) para não
    depender do erro do índice único filtrado da 079 como fluxo de controle:
    duas abas do operador clicando "Pausar" ao mesmo tempo devem produzir UMA
    pausa e nenhum 500. `rowcount == 0` significa "já havia uma pendente" e o
    chamador devolve a existente.
    """
    cur.execute(
        "INSERT INTO " + TABELA + " "
        "(pipeline_name, execution_id, job_name, task_id, run_id, "
        " data_referencia, estado, motivo, teto_minutos, solicitado_por) "
        "SELECT ?, ?, ?, ?, ?, ?, 'PENDENTE', ?, ?, ? "
        "WHERE NOT EXISTS (SELECT 1 FROM " + TABELA + " "
        "WHERE pipeline_name = ? AND execution_id = ? AND job_name = ? "
        "AND estado = 'PENDENTE')",
        (pipeline, execution_id, job_name, task_id, run_id, data_ref,
         (motivo or None), int(teto), (usuario or "?")[:200],
         pipeline, execution_id, job_name))
    if cur.rowcount == 0:
        return 0
    cur.execute(
        "SELECT TOP (1) id FROM " + TABELA + " "
        "WHERE pipeline_name = ? AND execution_id = ? AND job_name = ? "
        "AND estado = 'PENDENTE' ORDER BY id DESC",
        (pipeline, execution_id, job_name))
    row = cur.fetchone()
    return int(row[0]) if row else 0


def resolver(cur, pausa_id: int, estado: str, usuario: str,
             observacao: str | None) -> bool:
    """PENDENTE → LIBERADA/CANCELADA, atomicamente. True = fui eu quem mudou.

    `AND estado = 'PENDENTE'` é a trava contra a corrida com o portão (que
    pode estar expirando a mesma linha neste instante) e contra o duplo clique.
    False não é erro do sistema: é "alguém chegou antes", e o chamador lê o
    estado atual para contar a história certa.
    """
    cur.execute(
        "UPDATE " + TABELA + " SET estado = ?, resolvido_por = ?, "
        "resolvido_em = GETDATE(), observacao = ? "
        "WHERE id = ? AND estado = 'PENDENTE'",
        (estado, (usuario or "?")[:200],
         (observacao or None), int(pausa_id)))
    return cur.rowcount == 1


# ═══════════════════════════ evento e auditoria ═══════════════════════════════

def data_do_execution_id(ts):
    """A data embutida no ``ts_nodash`` (``YYYYMMDDTHHMMSS``), ou None.

    ⚠️ **DEFEITO ENCONTRADO NA PROVA VIVA (dev, 2026-08-03).** Pausar poucos
    segundos depois de disparar a corrida cria a pausa com
    ``data_referencia = NULL``: o ``check_agenda`` ainda não gravou a linha em
    ``etl_pipeline_execucao``, então a identidade resolve o run mas não o ODATE.
    A consequência apareceu no cancelamento — "evento ESPERA_CANCELADA sem data
    — nao gravado" — ou seja, o gesto acontecia e o painel não ficava sabendo.

    O ``ts_nodash`` É a data lógica da corrida, então ele é a fonte de
    recuperação óbvia — e é a MESMA que o portão usa do lado da DAG
    (``dags/utils/espera.data_do_evento``). Regra: o ODATE pode faltar na hora
    do pedido, nunca no registro.
    """
    try:
        return datetime.strptime(str(ts)[:8], "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def fechar_corrida_cancelada(cur, pipeline: str, run_id: str, usuario: str) -> bool:
    """Fecha a corrida como FALHA quando o operador CANCELA a execução.

    ⚠️ **DEFEITO ENCONTRADO NA PROVA VIVA (dev, 2026-08-03).** Cancelar pelo
    Airflow (``PATCH state=failed``) marca as tasks não terminadas como
    SKIPPED — inclusive o ``registrar_falha``, que tem ``trigger_rule=
    ONE_FAILED`` e é quem grava FALHA em ``etl_pipeline_execucao``. Medido: o
    DagRun ficou `failed` e a corrida ficou **EXECUTANDO para sempre**.

    É a classe de defeito que este projeto já pagou (o `factory_log` órfão em
    RUNNING): para o operador, um processo eternamente "executando" é um
    timeout mudo. Quem cancela é quem fecha.

    ``AND status NOT IN ('SUCESSO','FALHA')`` preserva estado terminal: se a
    corrida já tinha fechado por conta própria, o cancelamento não a reescreve.
    Nunca levanta — o DagRun já foi falhado e o gesto não pode ser desfeito.
    """
    try:
        cur.execute(
            "UPDATE dbo.etl_pipeline_execucao "
            "SET status = 'FALHA', motivo = ?, fim = GETDATE(), "
            "    atualizado_em = GETDATE() "
            "WHERE pipeline_name = ? AND execution_id = ? "
            "AND status NOT IN ('SUCESSO', 'FALHA')",
            (f"execucao cancelada na etapa em espera por {usuario or '?'}"[:500],
             pipeline, run_id))
        return cur.rowcount == 1
    except Exception as e:  # noqa: BLE001
        log.warning("[ESPERA] corrida '%s/%s' nao fechada apos cancelamento: %s",
                    pipeline, run_id, e)
        return False


def gravar_evento(cur, pipeline: str, data_ref, tipo: str, detalhe: str) -> bool:
    """Evento em `dbo.etl_dependencia_evento` — a tabela da guardiã.

    ⚠️ **Port do `dependencias.gravar_evento` de dags/**, com `?` no lugar de
    `%s`. A casa prefere paridade por IDENTIDADE (o mesmo objeto), e é o que o
    portão faz do lado da DAG; aqui a árvore muda o placeholder e a cópia é
    inevitável — o mesmo caso já registrado em `rerun.dependentes_diretos`.
    A chave de idempotência (`ux_dep_evento_corrida`: pipeline, data, tipo,
    corrida — era `ux_dep_evento`, com três colunas, até a migration 085) é a
    mesma, então os dois lados nunca duplicam um ao outro.

    Reusar esta tabela é o que faz o alerta chegar ao Teams **sem uma linha de
    mudança na guardiã**: ela já drena todo evento sem `notificado_em`.

    Nunca levanta: registrar o evento não pode derrubar o gesto que já
    aconteceu.
    """
    if data_ref is None:
        log.warning("[ESPERA] evento %s de '%s' sem data — nao gravado",
                    tipo, pipeline)
        return False
    try:
        cur.execute(
            "INSERT INTO dbo.etl_dependencia_evento "
            "(pipeline_name, data_referencia, tipo, detalhe) "
            "SELECT ?, ?, ?, ? "
            "WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_dependencia_evento "
            "WHERE pipeline_name = ? AND data_referencia = ? AND tipo = ?)",
            (pipeline, data_ref, tipo, (detalhe or "")[:1000],
             pipeline, data_ref, tipo))
        return cur.rowcount == 1
    except Exception as e:  # noqa: BLE001
        log.warning("[ESPERA] evento %s de '%s' nao gravado: %s",
                    tipo, pipeline, e)
        return False


def registrar_auditoria(cur, pipeline: str, usuario: str, gesto: str,
                        detalhe: dict) -> bool:
    """Uma linha em `dbo.etl_pipeline_audit` por gesto — pausar, liberar,
    cancelar. `field_name` é `pausa_etapa`, `old_value` guarda a corrida e a
    etapa, `new_value` o JSON do gesto.

    É AQUI que mora a auditoria completa (uma linha por gesto, sem dedupe),
    e não na tabela de eventos: a de eventos é única por (pipeline, dia, tipo)
    e serve ao painel e ao card, não ao histórico.

    **Nunca levanta** — falhar em auditar não pode desfazer um gesto que já
    aconteceu (o mesmo contrato do `rerun.registrar_auditoria`).
    """
    try:
        antes = json.dumps({
            "execution_id": detalhe.get("execution_id"),
            "run_id": detalhe.get("run_id"),
            "data_referencia": detalhe.get("data_referencia"),
            "job_name": detalhe.get("job_name"),
        }, ensure_ascii=False)
        depois = json.dumps({
            "gesto": gesto,
            "pausa_id": detalhe.get("pausa_id"),
            "motivo": detalhe.get("motivo"),
            "observacao": detalhe.get("observacao"),
            "teto_minutos": detalhe.get("teto_minutos"),
            "dagrun_falhado": detalhe.get("dagrun_falhado"),
        }, ensure_ascii=False)
        cur.execute(
            "INSERT INTO dbo.etl_pipeline_audit "
            "(pipeline_name, changed_by, field_name, old_value, new_value) "
            "VALUES (?, ?, ?, ?, ?)",
            (pipeline, (usuario or "?")[:100], CAMPO_AUDIT,
             antes[:4000], depois[:4000]))
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("[ESPERA] auditoria de '%s' nao gravada: %s", pipeline, e)
        return False


# ══════════════════════════ material para a tela ══════════════════════════════

def avisos_da_pausa(cur, pipeline: str, teto: int) -> list:
    """Avisos honestos que o operador precisa ver ANTES de pausar.

    Hoje há um só, e ele é real: pipeline com SLA configurado gera DAG com
    `dagrun_timeout` (etl_dag_factory), e o Airflow mata a corrida inteira
    quando o tempo estoura — inclusive uma corrida parada de propósito no
    portão. Uma pausa maior que o SLA não fica esperando: ela vira falha por
    timeout do DagRun, e por outro motivo que não o teto. Melhor dizer isso
    antes do que explicar depois.
    """
    avisos: list = []
    try:
        cur.execute("SELECT sla_minutos FROM dbo.etl_pipeline "
                    "WHERE pipeline_name = ?", (pipeline,))
        row = cur.fetchone()
        sla = int(row[0]) if row and row[0] is not None else 0
    except Exception as e:  # noqa: BLE001
        log.warning("[ESPERA] leitura de sla_minutos de '%s' falhou: %s",
                    pipeline, e)
        return avisos
    if sla > 0 and sla <= teto:
        avisos.append(
            f"O pipeline tem SLA de {sla} min e a DAG roda com "
            f"dagrun_timeout — uma espera até o teto de {teto} min pode ser "
            "interrompida pelo Airflow antes disso, com a corrida marcada "
            "como falha por timeout.")
    return avisos
