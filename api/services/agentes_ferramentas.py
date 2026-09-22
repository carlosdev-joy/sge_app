"""api/services/agentes_ferramentas.py — as ferramentas do agente DataStage e
a allowlist que as guarda (F2 + F2b da spec docs/spec-agentes-datastage.md).

Cinco ferramentas, e só cinco (ferramenta nova entra por PR, nunca por
aprendizado do modelo):

  • `resolver_projeto` — decide o PROJETO DataStage da conversa (§3,
    "resolução do projeto"). Não toca o servidor: valida contra a BASE
    (`etl_pipeline`/`etl_ds_job_isx`) e a lista de arquivos `.dsx`
    (`DSX_BASE_DIR`, só os NOMES — ler o conteúdo é `dsx_consulta`). Sem
    projeto resolvido, `base`/`dsjob`/`dsx_consulta`/`isx_extrair` se
    recusam a rodar — é a guarda central contra "consultas às cegas"
    (risco 28 da spec).
  • `base` — o que o Orquestra já sabe do job (`etl_ds_job_isx` +
    `etl_job_lineage` `isx_auto`; `etl_agente_fato` só a partir da F5).
    Sempre tentada ANTES de `dsjob`/`dsx_consulta` — é o "base primeiro".
  • `dsjob` — leitura ao vivo no servidor DataStage, só os 5 subcomandos
    read-only que não expõem valor de dado (`ljobs`, `lstages`, `lparams`,
    `jobinfo`, `report`; **nunca** `logsum`/`logdetail`), atrás de um
    semáforo de sessões SSH (`agentes_ssh_max`) e sempre `redigir()`ada
    antes de qualquer gravação ou de ir ao modelo.
  • `dsx_consulta` (F2b) — **somente leitura** dos `.dsx` que já existem em
    `DSX_BASE_DIR` (nunca toca o servidor DataStage), pelo `DSXEngine`
    existente — as MESMAS funções que `api/routers/lineage.py` já usa.
    Toda resposta traz nome+data do arquivo (é um retrato); `redigir()`
    sempre; roda num executor com teto (um `.dsx` grande não pode travar
    a rodada).
  • `isx_extrair` (F2b) — export via `istool` + parse + gravação, com a
    MESMA régua do botão `POST /lineage/isx/extrair` da Governança: as
    MESMAS funções (`lineage_isx.localizar/extrair/gravar`) e o MESMO
    executor dedicado (`routers.lineage_isx._EXECUTOR_ISX`, 2 por
    processo) — nenhum pool novo. Exige `acao_editar` do usuário (o mesmo
    do botão); sem ela, devolve o link da Governança em vez de extrair.
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import datetime

from fastapi import HTTPException

from routers.lineage_isx import _EXECUTOR_ISX as ISX_EXECUTOR  # noqa: F401 — reexportado (testes)
from routers.lineage_isx import _no_executor as isx_no_executor
from routers.lineage_isx import _TETO_EXTRAIR_S as ISX_TETO_EXTRAIR_S
from services import lineage_isx
from services.ssh_datastage import DsConsoleError, run_dsjob, ssh_configured

# ── Redação de segredos ──────────────────────────────────────────────────────
#
# O que sai do `dsjob` (em especial `-lparams` e `-report`) pode trazer valor
# de parâmetro `Encrypted` e trechos de configuração com senha — nada disso
# pode chegar ao modelo nem ser gravado (mensagem, fato ou aprendizado).
# Conservador de propósito (D-07 ainda não fechada — não sabemos o formato
# exato): mascara qualquer coisa que PAREÇA um valor de campo sensível, e o
# nome do parâmetro/campo continua visível (é o que o operador precisa ler).
#
# O nome do campo (e o separador) pode vir entre aspas — formato JSON, como
# `-report`/`-lparams` às vezes devolvem (`"password": "abc123"`). Sem os
# `["\']?` ao redor do nome/separador, a aspas que fecha o NOME quebrava o
# casamento logo antes do `:` e a linha inteira passava incólume (achado real
# da revisão adversarial da F2: miss silencioso em `{"password":"abc123"}`).
# O VALOR também pode vir entre aspas — capturado como grupo próprio
# (`"..."`/`'...'`/sem aspas) em vez de um `\S+` genérico, que antes casava
# só a pontuação logo após o nome (ex.: a aspas de abertura do valor) e
# deixava o segredo de verdade visível atrás da máscara.
#
# O valor NÃO tenta reconhecer onde "termina" (nem por aspas, nem por
# delimitador estrutural tipo `,`/`}`/`]`) — mascara tudo da posição atual
# até o FIM DA LINHA, sempre. Duas tentativas mais "espertas" já se
# provaram erradas nesta mesma função:
#   1ª tentativa (régua de escape estilo JSON, `\\.` antes de `[^"\\\n]`):
#      um texto ARBITRÁRIO (a saída crua do `dsjob`, formato não confirmado
#      — D-07) pode ter uma barra invertida comum bem antes de uma aspa
#      REAL de fechamento (ex.: path Windows `"C:\Temp\"`), indistinguível
#      de uma aspa escapada — o regex tratava a aspa real como escapada e
#      seguia procurando a PRÓXIMA aspa, que podia abrir o valor de um
#      CAMPO SEGUINTE inteiro — esse segundo segredo saía sem máscara
#      nenhuma (achado real da 3ª rodada da revisão adversarial da F2).
#   2ª tentativa (parar em `,`/`}`/`]`/quebra de linha, sem olhar aspas):
#      o valor real de um parâmetro `Encrypted` do DataStage tem a FORMA
#      `{iisenc}<base64>` — a chave `}` faz parte do CONTEÚDO, não é um
#      delimitador de nada. Parar nela cortava o valor no meio e deixava o
#      resto (o segredo de verdade) exposto sem máscara.
# "Até o fim da linha" nunca tem essa ambiguidade: não existe combinação de
# aspas/chaves/vírgulas dentro do valor que engane onde ele "termina" — o
# preço é mascarar informação não sensível que porventura esteja DEPOIS, na
# MESMA linha (nunca um segredo de um campo diferente escapa). É
# exatamente o design pré-F2 desta função, restaurado com o motivo
# documentado desta vez.
_VALOR = r"[^\n]*"
_RE_SEGREDO = re.compile(
    r"(?im)([\"']?\b(?:senha|password|pwd|secret|token|api[_-]?key)\b[\"']?\s*[:=]\s*)"
    r"(" + _VALOR + r")")
_RE_ENCRYPTED = re.compile(
    r"(?im)([\"']?\bEncrypted\b[\"']?\s*[:=]?\s*)"
    r"(" + _VALOR + r")")
_MASCARA = "••••"


def redigir(texto: str) -> str:
    """Mascara o VALOR de qualquer linha que pareça um campo sensível — o
    NOME do campo/parâmetro fica visível. Nunca levanta: texto vazio/None
    volta como veio."""
    if not texto:
        return texto or ""
    saida = _RE_SEGREDO.sub(lambda m: m.group(1) + _MASCARA, texto)
    saida = _RE_ENCRYPTED.sub(lambda m: m.group(1) + _MASCARA, saida)
    return saida


def redigir_estrutura(valor):
    """Aplica `redigir()` a cada STRING FOLHA de um dict/list, recursivamente
    — NUNCA ao JSON serializado inteiro de uma vez. `redigir()` mascara até
    o fim da LINHA que contém a keyword sensível (decisão de design das
    rodadas anteriores da F2, pensada para a saída MULTI-LINHA do `dsjob`);
    um `json.dumps(..., default=str)` compacto (sem `indent`, como
    `isx_extrair`/`base`/`dsx_consulta` produzem) é UMA linha lógica só —
    mascarar o texto serializado inteiro apagava a resposta INTEIRA sempre
    que qualquer parte dela (ex.: `job_description` em prosa mencionando
    "senha", ou o VALOR de um campo `type` sendo literalmente "Encrypted")
    continha a keyword — over-masking severo, destruindo o lineage útil
    (achado real da revisão adversarial da F2b). Aplicar por STRING isola
    o dano a cada campo individualmente, sem perder segurança (a defesa
    multi-linha original de `redigir()` continua valendo DENTRO de uma
    string que, por si só, tenha várias linhas — ex.: um `job_description`
    grande, ou o stdout redigido de um `dsjob`)."""
    if isinstance(valor, dict):
        return {k: redigir_estrutura(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [redigir_estrutura(v) for v in valor]
    if isinstance(valor, str):
        return redigir(valor)
    return valor


# ── Truncagem ────────────────────────────────────────────────────────────────
#
# `run_dsjob` já trunca o stdout em 200 000 caracteres (o teto do Console) —
# isso ainda é grande demais para ir ao modelo (custo, e o `-report` de um
# job com muitos stages pode ter dezenas de milhares de linhas). O agente
# trunca de novo, bem mais curto, e avisa que truncou.
MAX_SAIDA_MODELO = 6000


def _truncar(texto: str, limite: int = MAX_SAIDA_MODELO) -> str:
    texto = texto or ""
    if len(texto) <= limite:
        return texto
    return texto[:limite] + f"\n… [saída truncada em {limite} caracteres — {len(texto) - limite} a mais]"


# ── Semáforo de sessões SSH (D-09: teto configurável, padrão 10) ────────────

class ServidorOcupado(Exception):
    """A espera pelo semáforo de SSH estourou o prazo — nomeado, não um
    timeout genérico (spec, critério 5 da F2)."""


class SemaforoSsh:
    """Um `asyncio.Semaphore` reconstruído quando o teto muda (o admin edita
    `agentes_ssh_max` em runtime — trocar o `Semaphore` no meio de um
    `acquire()` alheio não afeta quem já entrou, só os próximos)."""

    def __init__(self) -> None:
        self._teto = 0
        self._sem: asyncio.Semaphore | None = None

    def _para(self, teto: int) -> asyncio.Semaphore:
        if self._sem is None or teto != self._teto:
            self._teto = teto
            self._sem = asyncio.Semaphore(teto)
        return self._sem

    async def __call__(self, teto: int, espera_max_s: float):
        """Async context manager: `async with semaforo(teto, espera_s):`."""
        sem = self._para(teto)
        try:
            await asyncio.wait_for(sem.acquire(), timeout=max(0.1, espera_max_s))
        except asyncio.TimeoutError:
            raise ServidorOcupado(
                "Servidor DataStage ocupado (todas as sessões SSH em uso) — tente de novo em instantes.")
        return _SoltarAoSair(sem)


class _SoltarAoSair:
    def __init__(self, sem: asyncio.Semaphore) -> None:
        self._sem = sem

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        self._sem.release()
        return False


SEMAFORO_SSH = SemaforoSsh()


# ── resolver_projeto ─────────────────────────────────────────────────────────

def _projetos_da_base(cur) -> list[str]:
    """Nomes de projeto DataStage que a base já conhece — `etl_pipeline` (todo
    pipeline cadastrado) ∪ `etl_ds_job_isx` (todo job com ISX gravado)."""
    vistos: set[str] = set()
    try:
        cur.execute("SELECT DISTINCT project_name FROM dbo.etl_pipeline WHERE project_name <> ''")
        vistos |= {str(r[0]).strip() for r in cur.fetchall() if r[0]}
    except Exception:
        pass
    try:
        cur.execute("SELECT DISTINCT ds_project FROM dbo.etl_ds_job_isx")
        vistos |= {str(r[0]).strip() for r in cur.fetchall() if r[0]}
    except Exception:
        pass
    return sorted(vistos)


def _dsx_engine_cls():
    """Importa o `DSXEngine` do pacote das DAGs — mesmo padrão de
    `api/routers/lineage.py::_import_dsx_engine` (o container da API monta
    `dags/`, e o `orquestra-api` monta `DSX_BASE_DIR` `:ro`)."""
    import sys
    dags_folder = os.environ.get("DAGS_FOLDER", "/opt/airflow/dags")
    if dags_folder not in sys.path:
        sys.path.insert(0, dags_folder)
    from utils.dsx_engine import DSXEngine  # type: ignore
    return DSXEngine


def _projetos_com_dsx() -> list[str]:
    """Nomes de projeto com arquivo `.dsx` em `DSX_BASE_DIR` — só a LISTA
    (`listar_dsx`); ler o conteúdo de um `.dsx` é a ferramenta `dsx_consulta`."""
    try:
        return list(_dsx_engine_cls()().listar_dsx())
    except Exception:
        return []


def projeto_tem_dsx(nome: str) -> bool:
    """Se `nome` (já resolvido) tem arquivo `.dsx` — usado por `dsx_consulta`
    para recusar sem tocar o disco de novo além da listagem (critério 11 da
    F2b: só roda com projeto **com** `.dsx`)."""
    dsx = _projetos_com_dsx()
    return nome in dsx or _casa_ignorando_caixa(nome, dsx) is not None


def nome_dsx_valido(nome: str) -> str | None:
    """Réplica de `api/routers/lineage.py::_safe_project_name`, sem
    `HTTPException` — devolve `None` (não levanta) quando o nome está vazio
    ou tem sinal de path traversal (critério 7 da F2b)."""
    n = (nome or "").strip()
    if n.lower().endswith(".dsx"):
        n = n[:-4]
    if not n or "/" in n or "\\" in n or ".." in n:
        return None
    return n


def _casa_exato(nome: str, candidatos: list[str]) -> str | None:
    return nome if nome in candidatos else None


def _casa_ignorando_caixa(nome: str, candidatos: list[str]) -> str | None:
    """DataStage é sensível a caixa (nomes de job/projeto). Casa ignorando
    e devolve a grafia CANÔNICA (a que está cadastrada) — mas quem chama
    (`resolver_projeto`) só usa isso para SUGERIR: o critério 11 da F2 pede
    confirmação antes de assumir, nunca corrigir sozinho."""
    alvo = nome.strip().lower()
    for c in candidatos:
        if c.strip().lower() == alvo:
            return c
    return None


def projeto_do_pipeline_job(cur, pipeline_name: str, job_name: str) -> str | None:
    """Se o usuário citou um pipeline/job do Orquestra, o projeto sai daí —
    sem perguntar (spec, critério 10 da F2). Nome vindo de `etl_pipeline_job`
    já é a grafia cadastrada — não precisa de confirmação de caixa."""
    info = lineage_isx.job_do_pipeline(cur, pipeline_name, job_name)
    return info["ds_project"] if info else None


def resolver_projeto(cur, nome_informado: str | None = None,
                     pipeline_name: str | None = None, job_name: str | None = None) -> dict:
    """Valida um nome de projeto DataStage contra o que o Orquestra já
    conhece — a base e a lista de `.dsx`. NÃO toca o servidor DataStage.

    Duas portas de entrada (critério 10 da F2): `pipeline_name`+`job_name`
    (o usuário citou algo do Orquestra — resolve sem perguntar) OU
    `nome_informado` (um nome de projeto DataStage cru, que pode vir com a
    caixa errada — DataStage é sensível a ela).

    Devolve `{"estado": "resolvido"|"quase"|"desconhecido", "projeto": str|None,
    "sugerido": str|None, "tem_dsx": bool, "sugestoes": [str]}`.
    `"quase"` (crítério 11) é SÓ sugestão — nunca resolve sozinho por essa
    via; confirmar é chamar de novo com a grafia exata (`sugerido`)."""
    conhecidos = _projetos_da_base(cur)
    dsx = _projetos_com_dsx()
    todos = sorted(set(conhecidos) | set(dsx))

    if pipeline_name and job_name:
        projeto = projeto_do_pipeline_job(cur, pipeline_name, job_name)
        if projeto:
            return {"estado": "resolvido", "projeto": projeto, "sugerido": None,
                    "tem_dsx": projeto in dsx or _casa_ignorando_caixa(projeto, dsx) is not None,
                    "sugestoes": []}
        # Pipeline/job não achado na base — cai para tentar como nome cru,
        # se também veio; senão desconhecido (sem inventar).

    nome = (nome_informado or "").strip()
    if not nome:
        return {"estado": "desconhecido", "projeto": None, "sugerido": None,
                "tem_dsx": False, "sugestoes": todos[:10]}

    exato = _casa_exato(nome, conhecidos) or _casa_exato(nome, dsx)
    if exato:
        return {"estado": "resolvido", "projeto": exato, "sugerido": None,
                "tem_dsx": exato in dsx, "sugestoes": []}

    quase = _casa_ignorando_caixa(nome, conhecidos) or _casa_ignorando_caixa(nome, dsx)
    if quase:
        return {"estado": "quase", "projeto": None, "sugerido": quase,
                "tem_dsx": quase in dsx, "sugestoes": []}

    return {"estado": "desconhecido", "projeto": None, "sugerido": None,
            "tem_dsx": False, "sugestoes": todos[:10]}


# ── base (o que o Orquestra já sabe) ────────────────────────────────────────

def _idade_dias(data_iso: str | None) -> int | None:
    """Dias desde `data_iso` (o `ds_last_modified` do ISX — "texto ISO da
    API REST", formato exato não confirmado — D-08 da spec). Nunca levanta:
    formato inesperado devolve None, e a resposta diz "idade desconhecida"
    em vez de inventar um número."""
    if not data_iso:
        return None
    import datetime as _dt
    texto = str(data_iso).strip()
    quando = None
    try:
        quando = _dt.datetime.fromisoformat(texto.replace("Z", "+00:00"))
        if quando.tzinfo is not None:
            quando = quando.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                quando = _dt.datetime.strptime(texto, fmt)
                break
            except ValueError:
                continue
    if quando is None:
        return None
    return max(0, (_dt.datetime.now() - quando).days)


def ferramenta_base(cur, ds_project: str, job_name: str) -> dict:
    """Lê `etl_ds_job_isx`/`etl_job_lineage` (isx_auto) para (projeto, job).
    Sem FK direta por projeto — busca por `ds_project` + `job_name`, que é
    único por job dentro de um projeto na prática do DataStage.

    Inclui `idade_dias` do `ds_last_modified` — a RESPOSTA já traz a idade
    computada (critério 3 da F2: "a resposta informa a idade do dado"), sem
    depender do modelo calcular a partir de uma data crua."""
    cur.execute(
        "SELECT pipeline_name, job_name, ds_folder_path, ds_job_type, ds_last_modified, "
        "       job_description, parameters_json, flow_json, status, erro, extracted_at "
        "FROM dbo.etl_ds_job_isx WHERE ds_project = ? AND job_name = ?", [ds_project, job_name])
    row = cur.fetchone()
    if not row:
        return {"encontrado": False}
    cur.execute(
        "SELECT COUNT(*) FROM dbo.etl_job_lineage "
        "WHERE pipeline_name = ? AND job_name = ? AND extraction_method = 'isx_auto'",
        [row[0], job_name])
    n_stages = cur.fetchone()
    return {
        "encontrado": True, "origem": "isx", "pipeline_name": row[0], "job_name": row[1],
        "ds_folder_path": row[2], "job_type": row[3], "ds_last_modified": row[4],
        "idade_dias": _idade_dias(row[4]),
        "job_description": row[5], "parameters_json": row[6], "flow_json": row[7],
        "status": row[8], "erro": row[9], "extracted_at": str(row[10]) if row[10] else None,
        "stages": int(n_stages[0]) if n_stages else 0,
    }


# ── dsjob (leitura ao vivo) ──────────────────────────────────────────────────

ALLOWLIST_DSJOB = ("ljobs", "lstages", "lparams", "jobinfo", "report")


async def ferramenta_dsjob(comando: str, ds_project: str, job_name: str | None,
                           *, teto_sessoes: int, espera_max_s: float) -> dict:
    """`dsjob` de leitura, atrás do semáforo. Levanta `DsConsoleError`
    (comando/nome inválido, SSH não configurado) ou `ServidorOcupado`
    (semáforo estourou a espera) — o chamador (a orquestração) as traduz em
    mensagem nomeada; nunca deixa o modelo escolher um comando fora da
    allowlist, mesmo que o pedido venha bem formado.

    Duas fases com segurança de cancelamento DIFERENTE (achado real da 3ª
    rodada da revisão adversarial da F2): enquanto só está NA FILA do
    semáforo, cancelar de fora (ex.: o orçamento da rodada estourando) é
    seguro e desejável — larga a vaga na hora, sem custo. Mas depois de
    OBTIDA a vaga, a sessão real (paramiko, via `asyncio.to_thread`) não é
    interrompível — abandonar o `async with` no meio liberaria o semáforo
    "mentindo": o teto contaria a vaga como livre enquanto a sessão de
    verdade ainda roda no servidor DataStage. Por isso só ESSA fase
    (adquirido → trabalho → libera) é protegida com `asyncio.shield`: um
    cancelamento externo durante ela não a interrompe, só deixa de esperar
    por ela — ela termina sozinha, no seu tempo, e libera o semáforo no
    momento certo."""
    if comando not in ALLOWLIST_DSJOB:
        raise DsConsoleError(f"Comando '{comando}' não é permitido — só {', '.join(ALLOWLIST_DSJOB)}.")
    if not ssh_configured():
        raise DsConsoleError("SSH do DataStage não configurado no servidor.")
    t0 = time.monotonic()
    gerenciador = await SEMAFORO_SSH(teto_sessoes, espera_max_s)  # cancelável — só fila, nada obtido ainda

    async def _com_a_vaga_obtida():
        async with gerenciador:
            # run_dsjob é síncrono/bloqueante (paramiko) — roda num thread
            # para não travar o loop async, mesmo padrão de
            # routers/lineage_isx.py.
            return await asyncio.to_thread(run_dsjob, comando, ds_project, job_name)

    tarefa = asyncio.ensure_future(_com_a_vaga_obtida())
    try:
        resultado = await asyncio.shield(tarefa)
    except asyncio.CancelledError:
        if not tarefa.cancelled():
            # Abandonada, não cancelada — segue rodando sozinha (é ela quem
            # libera o semáforo, no fim). Consome uma eventual exceção só
            # para não virar warning de "exception never retrieved".
            tarefa.add_done_callback(lambda t: None if t.cancelled() else t.exception())
        raise
    resultado["saida_redigida"] = _truncar(redigir(resultado.get("stdout") or ""))
    resultado["espera_ms"] = int((time.monotonic() - t0) * 1000) - resultado.get("duration_ms", 0)
    return resultado


# ── isx_extrair (F2b: export via istool + parse + gravação, mesma régua) ────
#
# Reaproveita 100% de `services.lineage_isx` (localizar/extrair/gravar/
# cabecalho/conta_linhas/mapa_tipos/config/montar) e o MESMO executor
# dedicado do router (`ISX_EXECUTOR`/`isx_no_executor`/`ISX_TETO_EXTRAIR_S`,
# importados de `routers.lineage_isx` acima) — "nenhum segundo pool"
# (spec F2b, item 1). Nunca reimplementa o export/parse/gravação.

_DS_JOB_TYPES = ("datastage", "")  # mesmo conjunto de routers/lineage_isx.py::_DS_JOB_TYPES
ORIGEM_AGENTE = "agente:datastage"  # sufixo em extracted_by — rastreia extrações feitas pelo agente
MAX_EXTRACOES_ISX = 2  # no máx. 2 extrações ISX por pergunta (spec F2b, item 5)


def isx_info_do_job(cur, pipeline_name: str, job_name: str) -> dict | None:
    """Mesma checagem de `routers.lineage_isx._info_do_job`, sem levantar
    `HTTPException` — devolve `None` quando o job não está mapeado no
    pipeline, o pipeline não tem projeto DataStage, ou o nó não é um job
    DataStage. Devolve os nomes na GRAFIA DO BANCO (case-insensitive na
    colação, mas o DataStage distingue caixa)."""
    info = lineage_isx.job_do_pipeline(cur, pipeline_name, job_name)
    if info is None or not info["ds_project"]:
        return None
    if str(info.get("job_type") or "").strip().lower() not in _DS_JOB_TYPES:
        return None
    return info


def mensagem_erro_lineage(e: Exception) -> str:
    """Traduz uma falha do `lineage_isx` (`ISXError`, `HTTPException`,
    genérica) numa mensagem nomeada para o chat — nunca vaza detalhe
    interno (`.interno`/traceback ficam só no log, como o router já faz
    em `_http()`)."""
    if isinstance(e, HTTPException):
        detalhe = e.detail
        return detalhe if isinstance(detalhe, str) else str(detalhe)
    status = getattr(e, "status", None)
    detail = getattr(e, "detail", None)
    if status is not None and detail is not None:
        return str(detail)
    return f"Falha inesperada na extração ISX ({type(e).__name__}) — tente de novo."


# ── dsx_consulta (F2b: só leitura dos .dsx já existentes) ───────────────────

DSX_TETO_S = 20  # parse de um .dsx grande num executor com prazo (critério 10 da F2b)
DSX_OPERACOES = ("listar_jobs", "listar_pastas", "buscar_campo", "extrair")


def _dsx_data_arquivo(diretorio_base: str, projeto: str) -> str | None:
    """Data de modificação do `.dsx` — toda resposta de `dsx_consulta` traz
    nome+data do arquivo (é um RETRATO, não o estado agora — critério 8)."""
    try:
        mtime = os.path.getmtime(os.path.join(diretorio_base, f"{projeto}.dsx"))
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return None


async def ferramenta_dsx_consulta(projeto: str, operacao: str, args: dict) -> dict:
    """Só leitura dos `.dsx` já existentes em `DSX_BASE_DIR` — NUNCA toca o
    servidor DataStage (critério 7 da F2b: sem SSH, sem `dsjob`, sem criar
    nem alterar arquivo). `projeto` já validado contra path traversal e
    contra "tem .dsx" por quem chama (`nome_dsx_valido`/`projeto_tem_dsx`).

    Roda num executor com teto — um `.dsx` grande não pode travar a rodada
    (critério 10). Como é só LEITURA de arquivo local (sem semáforo, sem
    sessão remota a proteger), `asyncio.wait_for` simples é seguro aqui:
    diferente do `dsjob`, não há recurso compartilhado que "vazaria" se a
    espera for abandonada — a thread órfã só termina de ler um arquivo."""
    if operacao not in DSX_OPERACOES:
        raise ValueError(f"Operação '{operacao}' não existe em dsx_consulta — "
                         f"use uma de: {', '.join(DSX_OPERACOES)}.")
    DSXEngine = _dsx_engine_cls()
    motor = DSXEngine()

    def _rodar():
        if operacao == "listar_jobs":
            return motor.listar_jobs(projeto)
        if operacao == "listar_pastas":
            return motor.listar_pastas(projeto)
        if operacao == "buscar_campo":
            termo = str(args.get("termo") or "").strip()
            tipos = args.get("tipos") if isinstance(args.get("tipos"), list) else None
            return motor.buscar_campo(
                projeto, termo, exato=bool(args.get("exato")), tipos=tipos,
                excluir=bool(args.get("excluir")), pasta=str(args.get("pasta") or ""))
        job_name = str(args.get("job_name") or "").strip()
        return motor.extrair(projeto, job_name)

    resultado = await asyncio.wait_for(asyncio.to_thread(_rodar), timeout=DSX_TETO_S)
    resultado = dict(resultado or {})
    resultado["dsx_arquivo"] = f"{projeto}.dsx"
    resultado["dsx_data"] = _dsx_data_arquivo(motor.diretorio_base, projeto)
    return resultado
