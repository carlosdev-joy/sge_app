"""api/routers/malhas.py — CRUD da entidade Malha (F7, spec §4b de dependências).

Malha = agrupadora de pipelines: o análogo da sequence mestre do DataStage e da
malha/SMART Folder do Control-M. NÃO é um executor — quem roda continua sendo o
modelo da spec (ODATE + push + guardiã), e as dependências continuam GLOBAIS em
etl_pipeline_dependencia (migration 067). A malha agrupa e exibe; o diagrama de
montagem é a F8.

Endpoints:
  GET    /malhas                                   — lista com agregados por malha
  POST   /malhas                                   — cria malha
  GET    /malhas/{malha_name}                      — detalhe + membros + arestas (F8) + nós (F10)
  GET    /malhas/{malha_name}/execucao             — status + eventos por data (F9)
                                                     + eventos de nó #no:* e
                                                     malha_concluida (F14)
                                                     + lente ?corrida={id} e o
                                                     bloco `corrida` (F4)
  POST   /malhas/{malha_name}/disparo              — disparo MANUAL da malha (F15;
                                                     dry_run no body): raízes do
                                                     Início via trigger REST
  POST   /malhas/{malha_name}/republicar           — republica as DAGs de TODOS os
                                                     pipelines membros (dry_run no
                                                     body): o gesto "Publicar nova
                                                     versão" repetido por membro
  PATCH  /malhas/{malha_name}                      — descricao / ativo / renomear / orientacao
  POST   /malhas/{malha_name}/pipelines            — adiciona membro (idempotente)
  DELETE /malhas/{malha_name}/pipelines/{pipeline_name} — remove membro
  PUT    /malhas/{malha_name}/layout               — persiste posições dos nós (F8/F10)
  POST   /malhas/{malha_name}/agendamento          — agendamento da malha + compilação
                                                     nas raízes (F13; dry_run no body)
  POST   /malhas/{malha_name}/nos                  — cria nó especial do desenho (F10)
  PATCH  /malhas/{malha_name}/nos/{no_id}          — config/layout do nó (F10)
  DELETE /malhas/{malha_name}/nos/{no_id}          — exclui nó + DESCOMPILA (F11; ?dry_run)
  POST   /malhas/{malha_name}/arestas              — aresta de nó + COMPILA (F11; dry_run no body)
  DELETE /malhas/{malha_name}/arestas/{aresta_id}  — remove aresta + RECOMPILA (F11; ?dry_run)
  POST   /dependencias                             — cria dependência REAL (F8)
  DELETE /dependencias                             — remove dependência REAL (F8;
                                                     linha assinada → 422, F11/Decisão 4)

F8: desenhar uma aresta no MalhaEditor É cadastrar a dependência GLOBAL em
etl_pipeline_dependencia (migration 067) — a mesma tabela da F1, com as MESMAS
validações (existência + ciclo BFS, importadas de routers.pipelines, nunca
reimplementadas). A aresta não tem escopo por malha: se dois pipelines aparecem
em duas malhas, a dependência aparece nas duas, porque é real nas duas.

F10 (docs/malha-componentes-desenho.md): nós especiais do desenho — Início,
Aguarde, Notificação e Fim (etl_malha_no/etl_malha_aresta, migration 075).
A gramática das arestas de nó (§2.1) e os avisos de desenho (§2.2) valem
desde a F10; a aresta pipeline→pipeline continua sendo o F8 acima (o CHECK
CK_malha_ar_tem_no da 075 declara isso no modelo).

F11 (desenho §3/§7): o Aguarde ganha EFEITO — cada gesto que o envolve
compila a expansão N×M (dags/utils/malha_nos.py via o port em services) para
linhas NORMAIS da 067, ASSINADAS com origem_no, com espelho CSV depends_on e
carimbo dag_config_pendente_em na MESMA transação (Decisão 7: incremental por
gesto, o desenho É o compilado). dry_run devolve o efeito §7.2 sem gravar; o
write RECOMPUTA (a autoridade é o estado corrente). Descompilar remove SÓ o
que a expansão perdeu — linha manual coincidente nunca é adotada nem removida
(Decisão 5) e linha que a expansão de OUTRA malha também produz é TRANSFERIDA
(re-assinada, §7.3), nunca derrubada em silêncio. O ciclo passa a ser validado
sobre o conjunto PÓS-expansão com o BFS canônico da F1 e a mensagem literal
compartilhada (Decisão 15); o ciclo topológico do desenho segue de retaguarda
para o ciclo só-de-nós, que não compila nada.

F13 (desenho §4): o Início ganha EFEITO — o agendamento mora na MALHA
(etl_malha.agendamento_json, Decisão 8) e compilar é COPIAR os campos para as
colunas reais de cada raiz ligada ao Início + assinar agenda_no + carimbar,
na mesma transação (POST /malhas/{name}/agendamento, dry_run no body).
Todas as raízes com o MESMO cron e a MESMA virada (Decisão 9) disparam no
mesmo tick do scheduler, cada uma na própria DAG — nenhum disparador novo.
Raiz com dependência na 067 não pode ser ligada ao Início (422, §2.2); raiz
assinada por Início de OUTRA malha idem (422, Decisão 11); desligar a raiz
(aresta/nó excluído) vira on_demand + carimbo — nunca cron restaurado
(Decisão 10). Os observadores (Notificação/Fim) são avaliados pela GUARDIÃ
(F14 — dags/etl_dependencia_guardia.py): aqui só nasce o desenho, a validação
do config por tipo (_validar_config_no) e a leitura dos eventos #no:* no
endpoint de execução.

Degradação em deploy parcial (API nova + migration 070 ainda não aplicada):
cada endpoint checa UMA vez se as tabelas existem; leitura da lista degrada
para vazio com log, e escrita devolve 503 com instrução clara em pt-BR —
nunca um 500 cru com stack trace na tela. Mesma regra para a migration 067
nos endpoints de dependência: leitura degrada ("arestas": []), escrita dá 503.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import PERM_EDITAR, PERM_EXECUTAR, get_current_user, require_perm
# F15 (disparo manual da malha): o disparo reusa o MESMO caminho do trigger
# manual de pipeline (proxy REST do Airflow) — nenhum executor novo; o client
# e a validação de dag_id vêm do proxy para não nascer uma segunda cópia.
from routers.airflow import _DAG_ID_RE, get_airflow_client
# Port do ODATE para a árvore da API (o canônico é dags/utils/data_referencia.py;
# paridade garantida por teste — ver o docstring do módulo).
from services import data_referencia as dref
# Port da expansão dos nós de malha (F10 — canônico em dags/utils/malha_nos.py;
# paridade por teste). O upstream por nó que o GET devolve sai DAQUI: o front
# nunca reimplementa a expansão (uma autoridade só, a regra do ciclo da F8).
from services import malha_nos as malha_nos_svc
# Port do predicado de liberação (F5/D29 — canônico em dags/utils/dependencias.py;
# paridade por teste). virada_global/tabela_067 moraram aqui inline até a F5 e
# foram extraídos para o service, reusados também por routers/pipelines.
from services import dependencias as deps_svc
# Ponte de identidade / canonização de pipeline (F2 — spec de operação no nível
# de etapa). Aqui entra só `pipeline_oficial`, que morava inline neste módulo.
from services import execucao_identidade as ident_svc
# F3 da spec-malha-execucao: o REGISTRO da corrida de malha. Port `?`/pyodbc do
# canônico dags/utils/malha_corrida.py, com paridade garantida por teste. Toda
# TRANSIÇÃO do ciclo (abrir, congelar snapshot, expirar, fechar) passa por ele —
# a mesma disciplina de "zero SQL de corrida" que a guardiã segue do outro lado,
# e a razão de a API e o motor não poderem discordar sobre o que é uma corrida.
from services import malha_corrida as mc
# F5 da spec-malha-execucao (§12.2): a sonda do fonte GERADO. `rerun_svc`
# pergunta o que o `dags/` deployado sabe fazer (um arquivo para todos);
# `espera_svc` pergunta o que a DAG PUBLICADA de CADA pipeline tem dentro — e é
# essa a pergunta do `force_all`, porque a regeração pode ter alcançado uns
# pipelines e não outros.
from services import espera as espera_svc
# `capacidade_dags` responde o que o `dags/` DEPLOYADO declara saber fazer — é
# metade do portão da §11.1 (a outra metade é o heartbeat da guardiã).
from services import rerun as rerun_svc
# Helpers da F1 — fonte ÚNICA das validações de dependência (não reimplementar:
# a mensagem de ciclo do servidor é ESPELHADA no cliente pelo MalhaEditor, e
# duas implementações divergiriam). Sem ciclo de import: pipelines.py não
# importa malhas — mesmo padrão de admin.py/copias.py importando de routers.X.
# _check_circular_grafo (F11): o NÚCLEO do BFS com adjacência injetada — o
# ciclo pós-expansão do compilador (Decisão 15) roda o MESMO algoritmo e emite
# a MESMA mensagem literal do cadastro da F1.
# F13 (Decisão 8): o agendamento da malha é validado pelas MESMAS funções do
# register — _build_cron para o domínio, _validate_dias_horarios_mes,
# _parse_horarios_especificos e _parse_hora_opcional (D35) — nunca uma
# reimplementação (a regra que salvou o texto do ciclo na F8).
# FACTORY_DAG_ID: a republicação da malha (abaixo) dispara a MESMA factory do
# botão "Publicar nova versão" da tela Pipelines — a constante vem de lá para
# não nascer uma segunda grafia do dag_id.
from routers.pipelines import (FACTORY_DAG_ID, _build_cron, _check_circular,
                               _check_circular_grafo, _parse_hora_opcional,
                               _parse_horarios_especificos,
                               _validar_existencia,
                               _validate_dias_horarios_mes, deduplicar)
# Fila da ativação/notificação da DAG recém-publicada (padrão do repo: a
# intenção mora no banco e um loop do lifespan reconcilia) — é ela que também
# apaga o carimbo dag_config_pendente_em quando a DAG é confirmada no Airflow.
from services.dag_reconcile import enqueue as enqueue_dag_pendente

log = logging.getLogger("orquestra-api")

router = APIRouter()

_MSG_SEM_MIGRATION = (
    "Recurso de malhas indisponível: a migration 070 (etl_malha/"
    "etl_malha_pipeline) ainda não foi aplicada neste banco."
)

_MSG_SEM_067 = (
    "Cadastro de dependências indisponível: a migration 067 "
    "(etl_pipeline_dependencia) ainda não foi aplicada neste banco."
)

_MSG_SEM_075 = (
    "Componentes de malha indisponíveis: a migration 075 "
    "(etl_malha_no/etl_malha_aresta) ainda não foi aplicada neste banco."
)

# Domínio dos nós especiais (F10). A coluna tipo não tem CHECK (padrão da
# casa): a API valida na escrita; a unicidade de Início/Fim tem o índice
# filtrado da 075 por baixo (o 2º chega a 422 aqui ANTES de estourar lá).
_TIPOS_NO = ("inicio", "aguarde", "notificacao", "fim")
_ROTULO_NO = {"inicio": "Início", "aguarde": "Aguarde",
              "notificacao": "Notificação", "fim": "Fim",
              "pipeline": "pipeline"}

# Domínio da orientação do diagrama de montagem (migration 074). A coluna não
# tem CHECK (padrão da casa): a API é quem valida na escrita e normaliza na
# leitura — valor estranho no banco vira 'horizontal', nunca tela quebrada.
_ORIENTACOES = ("horizontal", "vertical")

# Ordem de severidade da criticidade (mesmo domínio do CritBadge da tela Malha;
# comparação em caixa alta porque o valor em etl_pipeline é texto livre).
_CRIT_ORDEM = {"CRITICA": 3, "ALTA": 2, "MEDIA": 1, "BAIXA": 0}


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def _fmt_dia(v):
    """DATE → 'YYYY-MM-DD' (o formato que a tela e o contrato usam para a data
    de referência). None continua None."""
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return str(v)


def _fechar_silencioso(conn):
    """Desfaz a transação e fecha, sem mascarar o erro original."""
    if conn is None:
        return
    try:
        conn.rollback()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass


def _tabelas_070(cur) -> bool:
    """True se as tabelas da migration 070 existem. Checagem ÚNICA por request:
    é o que permite degradar num deploy parcial (API nova + banco antigo) em vez
    de estourar 'Invalid object name' na primeira query."""
    try:
        cur.execute(
            "SELECT OBJECT_ID('dbo.etl_malha', 'U'), OBJECT_ID('dbo.etl_malha_pipeline', 'U')"
        )
        row = cur.fetchone()
        return bool(row and row[0] is not None and row[1] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem das tabelas da migration 070 falhou: %s", e)
        return False


def _exigir_tabelas(cur, conn):
    """Escritas e detalhe não têm degradação útil: sem as tabelas, o erro tem
    de ser claro (503 + instrução), não um 500 cru de 'Invalid object name'."""
    if not _tabelas_070(cur):
        _fechar_silencioso(conn)
        raise HTTPException(status_code=503, detail=_MSG_SEM_MIGRATION)


def _tabela_067(cur) -> bool:
    """True se etl_pipeline_dependencia (migration 067) existe. Implementação
    extraída para services.dependencias na F5 (reuso pelos dois routers) — o
    alias local preserva os call sites."""
    return deps_svc.tabela_067(cur)


def _exigir_tabela_067(cur, conn):
    if not _tabela_067(cur):
        _fechar_silencioso(conn)
        raise HTTPException(status_code=503, detail=_MSG_SEM_067)


def _coluna_074(cur) -> bool:
    """True se etl_malha.orientacao (migration 074) existe. Guard de COLUNA no
    padrão de _has_card_cols (routers/mensagens.py): COL_LENGTH, best-effort —
    qualquer falha conta como ausente e a API degrada para o default."""
    try:
        cur.execute("SELECT COL_LENGTH('dbo.etl_malha', 'orientacao')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem da coluna da migration 074 falhou: %s", e)
        return False


def _compilar_virada(cur, malha: str, hora_virada) -> list:
    """Copia a virada da MALHA para todos os membros e carimba publicação
    pendente em quem mudou. Devolve os nomes alinhados.

    É o mesmo movimento do agendamento do Início (F13), que já copia
    `hora_virada` para as RAÍZES — aqui ele vale para a malha inteira, porque
    quem calcula data não é só a raiz: qualquer membro que ainda dispare por
    agenda calcula a dele (e foi assim que a corrida saiu partida).

    Só toca em quem DIVERGE: um UPDATE cego carimbaria publicação pendente em
    toda a malha a cada salvamento, e o operador aprenderia a ignorar o aviso.
    Sem a coluna em etl_pipeline (067 pendente), não há o que compilar."""
    if not _coluna_hora_virada(cur):
        return []
    cur.execute(
        "SELECT p.pipeline_name FROM dbo.etl_malha_pipeline mp "
        "JOIN dbo.etl_pipeline p ON p.pipeline_name = mp.pipeline_name "
        "WHERE mp.malha_name = ? AND ("
        "  (p.hora_virada IS NULL AND ? IS NOT NULL) OR "
        "  (p.hora_virada IS NOT NULL AND ? IS NULL) OR "
        "  (p.hora_virada <> ?))",
        (malha, hora_virada, hora_virada, hora_virada))
    fora = [r[0] for r in cur.fetchall()]
    for nome in fora:
        cur.execute(
            "UPDATE dbo.etl_pipeline SET hora_virada = ?, updated_at = GETDATE() "
            "WHERE pipeline_name = ?", (hora_virada, nome))
        # A DAG publicada ainda carrega a virada ANTIGA no _data_referencia
        # gerado: sem republicar, a régua nova só vale no papel.
        _ligar_dag_config_pendente(cur, nome)
    return sorted(fora)


def _coluna_hora_virada(cur) -> bool:
    """True se etl_pipeline.hora_virada (migration 067) existe."""
    try:
        cur.execute("SELECT COL_LENGTH('dbo.etl_pipeline', 'hora_virada')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem de etl_pipeline.hora_virada falhou: %s", e)
        return False


def _colunas_081(cur) -> bool:
    """True se as colunas da migration 081 (hora_virada + equalizar_data da
    MALHA) existem. Mesmo padrão dos demais guards: falha conta como ausente e
    a malha se comporta como antes da fase — a virada continua vindo do
    pipeline/global e a equalização não é oferecida."""
    try:
        cur.execute("SELECT COL_LENGTH('dbo.etl_malha', 'hora_virada'), "
                    "COL_LENGTH('dbo.etl_malha', 'equalizar_data')")
        row = cur.fetchone()
        return bool(row and row[0] is not None and row[1] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem das colunas da migration 081 falhou: %s", e)
        return False


def _coluna_teto_horas(cur) -> bool:
    """True se `etl_malha.teto_horas` (migration 085) existe.

    Guard PRÓPRIO, e não `tabela_085_presente`: a 085 cria a tabela da corrida e
    esta coluna em blocos separados, e um deploy parcial pode ter um sem o
    outro. Perguntar pela tabela e ler a coluna é como um `SELECT` inválido
    chega ao banco no meio de uma request que só queria mostrar a malha."""
    try:
        cur.execute("SELECT COL_LENGTH('dbo.etl_malha', 'teto_horas')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem de etl_malha.teto_horas falhou: %s", e)
        return False


def _hhmm(valor):
    """TIME/str → 'HH:MM' (o formato que a tela usa), ou None."""
    if valor is None:
        return None
    if hasattr(valor, "strftime"):
        return valor.strftime("%H:%M")
    texto = str(valor).strip()
    return texto[:5] if texto else None


def _orientacao_norm(valor) -> str:
    """Normaliza o valor lido do banco para o domínio da API: fora de
    'horizontal'|'vertical' (coluna sem CHECK) devolve o default."""
    v = (str(valor).strip().lower() if valor else "")
    return v if v in _ORIENTACOES else "horizontal"


# ── helpers dos nós especiais (F10 — migration 075) ──────────────────────────

def _tabelas_075(cur) -> bool:
    """True se as tabelas da migration 075 existem. Mesma regra das outras
    checagens (070/067): uma consulta por request, para o deploy parcial
    degradar (leitura com flag, escrita 503) em vez de estourar
    'Invalid object name' — princípio 6 do desenho de componentes."""
    try:
        cur.execute(
            "SELECT OBJECT_ID('dbo.etl_malha_no', 'U'), "
            "OBJECT_ID('dbo.etl_malha_aresta', 'U')"
        )
        row = cur.fetchone()
        return bool(row and row[0] is not None and row[1] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem das tabelas da migration 075 falhou: %s", e)
        return False


def _exigir_tabelas_075(cur, conn):
    """Escrita de nó/aresta sem a 075 não tem degradação útil: 503 com
    instrução clara, nunca 500 cru — padrão literal das guardas 070/067."""
    if not _tabelas_075(cur):
        _fechar_silencioso(conn)
        raise HTTPException(status_code=503, detail=_MSG_SEM_075)


def _coluna_origem_no(cur) -> bool:
    """True se etl_pipeline_dependencia.origem_no (assinatura da 075) existe.
    Implementação extraída para services.dependencias na F11 (as TRÊS portas
    da Decisão 4 precisam do mesmo guard) — o alias local preserva os call
    sites, como _tabela_067."""
    return deps_svc.coluna_origem_no(cur)


def _colunas_082(cur) -> bool:
    """True se as colunas da retenção do Aguarde (migration 082) existem."""
    try:
        cur.execute("SELECT COL_LENGTH('dbo.etl_malha_no', 'retido_em'), "
                    "COL_LENGTH('dbo.etl_malha_no', 'retido_por')")
        row = cur.fetchone()
        return bool(row and row[0] is not None and row[1] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem das colunas da migration 082 falhou: %s", e)
        return False


def _nos_da_malha(cur, malha) -> list:
    """Nós do desenho da malha, ordenados por id (determinístico).

    `retido_em` (082) é ADITIVO: sem a migration, o nó vem sem as chaves de
    retenção e a tela não oferece o gesto — nunca um botão que não segura."""
    tem_082 = _colunas_082(cur)
    cur.execute(
        "SELECT id, tipo, config_json, layout_x, layout_y"
        + (", retido_em, retido_por" if tem_082 else "") +
        " FROM dbo.etl_malha_no WHERE malha_name = ? ORDER BY id",
        (malha,))
    nos = []
    for r in cur.fetchall():
        n = {"id": int(r[0]), "tipo": (r[1] or "").strip().lower(),
             "config_json": r[2], "layout_x": r[3], "layout_y": r[4]}
        if tem_082:
            n["retido_em"] = _fmt_dt(r[5])
            n["retido_por"] = r[6]
        nos.append(n)
    return nos


def _arestas_da_malha(cur, malha) -> list:
    """Arestas de nó do desenho da malha, ordenadas por id."""
    cur.execute(
        "SELECT id, origem_no, origem_pipeline, destino_no, destino_pipeline "
        "FROM dbo.etl_malha_aresta WHERE malha_name = ? ORDER BY id",
        (malha,))
    return [{"id": int(r[0]),
             "origem_no": int(r[1]) if r[1] is not None else None,
             "origem_pipeline": r[2],
             "destino_no": int(r[3]) if r[3] is not None else None,
             "destino_pipeline": r[4]}
            for r in cur.fetchall()]


def _no_config(raw):
    """config_json do nó → objeto para o front. A API só grava JSON válido;
    valor quebrado por SQL direto degrada para None com log — nunca tela
    quebrada (mesmo espírito do _orientacao_norm)."""
    if raw is None or str(raw).strip() == "":
        return None
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else None
    except Exception:
        log.warning("[MALHA] config_json ilegível em etl_malha_no — degradado para None")
        return None


def _validar_config_no(tipo, config):
    """Validação rica do config por tipo (F14 — a pendência declarada da F13;
    desenho §5/§6). Levanta 422 com instrução; config None passa (limpar é
    gesto legítimo).

    • notificacao: {"titulo"?: str, "mensagem"?: str} — vira o corpo do
      evento MALHA_NOTIFICACAO e do card (a guardiã renderiza na detecção);
    • fim: {"notificar_teams"?: bool} — o card do Teams é OPT-IN (Decisão
      14, default False); o evento e o painel são sempre;
    • inicio/aguarde: sem schema AQUI de propósito — o agendamento do Início
      mora na MALHA (Decisão 8, POST /malhas/{name}/agendamento) e o Aguarde
      não tem configuração; a validação estrutural (objeto JSON) já foi
      feita pelo chamador.

    Chave desconhecida é 422, não silêncio: config que o motor ignora é a
    tela contando uma história e a guardiã outra (princípio 5)."""
    if config is None or tipo not in ("notificacao", "fim"):
        return
    if tipo == "notificacao":
        extras = sorted(set(config) - {"titulo", "mensagem"})
        if extras:
            raise HTTPException(
                status_code=422,
                detail="config da Notificação aceita apenas 'titulo' e "
                       f"'mensagem' — chave(s) desconhecida(s): {', '.join(extras)}")
        for chave in ("titulo", "mensagem"):
            v = config.get(chave)
            if v is not None and not isinstance(v, str):
                raise HTTPException(
                    status_code=422,
                    detail=f"'{chave}' da Notificação deve ser texto")
        return
    extras = sorted(set(config) - {"notificar_teams"})
    if extras:
        raise HTTPException(
            status_code=422,
            detail="config do Fim aceita apenas 'notificar_teams' — "
                   f"chave(s) desconhecida(s): {', '.join(extras)}")
    v = config.get("notificar_teams")
    if v is not None and not isinstance(v, bool):
        raise HTTPException(
            status_code=422,
            detail="'notificar_teams' do Fim deve ser booleano "
                   "(o card do Teams é opt-in — Decisão 14)")


def _erro_gramatica(origem_tipo, destino_tipo):
    """Gramática do desenho — célula a célula da tabela §2.1: devolve a
    mensagem do 422 para célula proibida, ou None para aresta permitida.

    Permitidas: inicio→pipeline · pipeline→aguarde · aguarde→pipeline ·
    aguarde→aguarde · pipeline/aguarde→notificacao · pipeline/aguarde→fim.
    pipeline→pipeline é recusada AQUI com a instrução da porta certa (F8):
    aresta direta é dependência REAL na 067, nunca desenho de nó (Decisão 2)."""
    if origem_tipo in ("notificacao", "fim"):
        return (f"Aresta inválida: {_ROTULO_NO[origem_tipo]} não tem saída — "
                "Notificação e Fim são observadores terminais do desenho "
                "(se tivessem saída, precisariam de um primitivo de runtime "
                "que não existe).")
    if destino_tipo == "inicio":
        return ("Aresta inválida: nada liga NO Início — ele é o ponto de "
                "partida do desenho, não um destino.")
    if origem_tipo == "inicio" and destino_tipo != "pipeline":
        return (f"Aresta inválida: Início → {_ROTULO_NO[destino_tipo]}. "
                "O Início só liga em pipeline — ele planta o agendamento da "
                "malha nas raízes, nada mais.")
    if origem_tipo == "pipeline" and destino_tipo == "pipeline":
        return ("Aresta pipeline → pipeline não entra no desenho de nós: use "
                "a aresta direta do diagrama (F8) — ela grava a dependência "
                "REAL na tabela global de dependências.")
    return None


def _avisos_desenho(nos, arestas) -> list:
    """Avisos de desenho do §2.2 — os ESTRUTURAIS desta fase (F10).

    A lição do nó Aguarde das Etapas (§5.5): ponta solta avisada no momento de
    consequência — cada gesto devolve a lista (toast) e o GET a repete (o
    banner persistente do editor, F12). Aviso NUNCA bloqueia: onde a tabela
    §2.2 diz aviso, o gesto é aceito e o efeito (ou a ausência dele) é DITO.
    Formato: {"no", "nivel" ('forte'|'leve'), "mensagem"}."""
    entradas: dict = {}
    saidas: dict = {}
    for a in arestas:
        if a["destino_no"] is not None:
            entradas[a["destino_no"]] = entradas.get(a["destino_no"], 0) + 1
        if a["origem_no"] is not None:
            saidas[a["origem_no"]] = saidas.get(a["origem_no"], 0) + 1
    avisos = []
    for no in nos:                       # ordenados por id → determinístico
        i, t = no["id"], no["tipo"]
        e, s = entradas.get(i, 0), saidas.get(i, 0)
        if t == "aguarde":
            if s > 0 and e == 0:
                avisos.append({"no": i, "nivel": "forte", "mensagem":
                               "Aguarde sem entradas: nenhuma dependência "
                               "será criada — ligue as entradas"})
            elif e == 1:
                avisos.append({"no": i, "nivel": "leve", "mensagem":
                               "Aguarde com uma única entrada — junção de uma "
                               "perna só (provável esquecimento)"})
            if s == 0:
                avisos.append({"no": i, "nivel": "leve", "mensagem":
                               "Aguarde sem saída — vale como marco visual; "
                               "nenhuma dependência nasce dele"})
        elif t in ("notificacao", "fim") and e == 0:
            avisos.append({"no": i, "nivel": "forte", "mensagem":
                           f"{_ROTULO_NO[t]} sem entrada — a guardiã não "
                           "avalia este nó (nada será emitido)"})
        elif t == "inicio" and s == 0:
            avisos.append({"no": i, "nivel": "forte", "mensagem":
                           "Início sem saída — o agendamento da malha não "
                           "alcançará nenhum pipeline"})
    return avisos


def _chave_ponta(no, pipe):
    """Identidade de uma ponta no grafo do desenho: nó por id, pipeline por
    casefold (colação CI do banco)."""
    return ("no", no) if no is not None else ("pipe", (pipe or "").casefold())


def _criaria_ciclo_desenho(arestas, chave_origem, chave_destino) -> bool:
    """True se origem→destino fecharia ciclo no grafo do DESENHO da malha
    (nós e pipelines ligados por arestas de nó): BFS para FRENTE a partir do
    destino — se alcançar a origem, a aresta proposta fecha o ciclo.

    FRONTEIRA F10/F11 (desenho §3.3, registrada de propósito): nesta fase o
    ciclo validado é o TOPOLÓGICO do desenho. O ciclo do conjunto
    PÓS-EXPANSÃO contra a 067 (Decisão 15 — um aguarde inocente pode fechar
    A→…→A por linhas que o gesto cria aos pares, validado com o BFS da F1 e a
    mensagem canônica compartilhada) chega com o compilador, na F11."""
    if chave_origem == chave_destino:
        return True
    adj: dict = {}
    for a in arestas:
        o = _chave_ponta(a["origem_no"], a["origem_pipeline"])
        d = _chave_ponta(a["destino_no"], a["destino_pipeline"])
        adj.setdefault(o, []).append(d)
    vistos, fila = set(), [chave_destino]
    while fila:
        atual = fila.pop(0)
        if atual == chave_origem:
            return True
        if atual in vistos:
            continue
        vistos.add(atual)
        fila.extend(adj.get(atual, ()))
    return False


def _resolver_ponta(cur, conn, malha, ponta, lado):
    """Resolve uma ponta {"no": id} | {"pipeline": nome} da aresta (§9).

    Nó: precisa existir NESTA malha (nó de outra malha é desenho de outra
    malha — 422 claro). Pipeline: canonizado pela grafia registrada (PR #236)
    e precisa ser MEMBRO da malha — aresta para não-membro deixaria o desenho
    apontando para fora do conjunto (o outro lado desse invariante, recusar
    remover membro ligado a nó, chega na F11 com o §7.3).
    Devolve {"no": id|None, "pipeline": nome|None, "tipo": tipo}."""
    if not isinstance(ponta, dict) or (("no" in ponta) == ("pipeline" in ponta)):
        _fechar_silencioso(conn)
        raise HTTPException(
            status_code=422,
            detail=f"{lado} deve ter exatamente uma das chaves: 'no' ou 'pipeline'")
    if "no" in ponta:
        no_id = ponta.get("no")
        if not isinstance(no_id, int) or isinstance(no_id, bool):
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422,
                                detail=f"{lado}.no deve ser o id numérico do nó")
        cur.execute("SELECT id, tipo FROM dbo.etl_malha_no "
                    "WHERE id = ? AND malha_name = ?", (no_id, malha))
        row = cur.fetchone()
        if row is None:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422,
                                detail=f"Nó {no_id} não existe na malha '{malha}'")
        return {"no": int(row[0]), "pipeline": None,
                "tipo": (row[1] or "").strip().lower()}
    nome = (str(ponta.get("pipeline") or "")).strip()
    if not nome:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=422, detail=f"{lado}.pipeline é obrigatório")
    oficial = _pipeline_oficial(cur, nome)
    if oficial is None:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=422, detail=f"Pipeline inexistente: '{nome}'")
    cur.execute("SELECT 1 FROM dbo.etl_malha_pipeline "
                "WHERE malha_name = ? AND pipeline_name = ?", (malha, oficial))
    if not cur.fetchone():
        _fechar_silencioso(conn)
        raise HTTPException(
            status_code=422,
            detail=f"'{oficial}' não é membro da malha '{malha}' — adicione-o "
                   "à malha antes de ligá-lo a um componente")
    return {"no": None, "pipeline": oficial, "tipo": "pipeline"}


def _rotulo_ponta(p) -> str:
    """Rótulo de uma ponta para mensagem de erro: pipeline pelo nome, nó pelo
    tipo + id — o texto do ciclo é ESPELHADO no cliente (regra F8)."""
    if p["pipeline"] is not None:
        return f"'{p['pipeline']}'"
    return f"{_ROTULO_NO.get(p['tipo'], 'nó')} #{p['no']}"


def _tabelas_067_execucao(cur) -> bool:
    """True se etl_pipeline_execucao E etl_dependencia_evento (migration 067)
    existem. Mesma regra das outras checagens: uma consulta por request, para a
    visão de execução (F9) degradar num deploy parcial em vez de estourar
    'Invalid object name' — a malha continua abrindo, sem status."""
    try:
        cur.execute(
            "SELECT OBJECT_ID('dbo.etl_pipeline_execucao', 'U'), "
            "OBJECT_ID('dbo.etl_dependencia_evento', 'U')"
        )
        row = cur.fetchone()
        return bool(row and row[0] is not None and row[1] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem das tabelas de execução da migration 067 falhou: %s", e)
        return False


def _virada_global(cur):
    """Valor CRU de etl_app_config['dependencia_hora_virada'] — implementação
    extraída para services.dependencias na F5 (reuso pelos dois routers); o
    parse tolerante segue em services.data_referencia."""
    return deps_svc.virada_global(cur)


def _ligar_dag_config_pendente(cur, pipeline_name) -> bool:
    """Liga a pendência de publicação (migration 073) do DEPENDENTE, na MESMA
    transação da escrita da dependência (Decisão 6/D30): mudar dependência
    troca o `schedule` da DAG do filho — o pai NÃO precisa regerar (F3 §2.2:
    ele lê a tabela ao vivo). Grava o CARIMBO GETDATE() em vez de um bit
    (achado 2 da revisão — TOCTOU): o reconciliador só limpa carimbos <=
    início da publicação concluída, então uma edição feita DURANTE uma
    publicação em voo sobrevive ao clear. `WHERE dag_criada = 1`: pipeline
    nunca publicado não tem versão velha rodando. Sem a coluna (073 pendente),
    degrada em silêncio — comportamento = hoje. Devolve True se a flag foi
    ligada (a resposta ao front segue sendo o booleano).

    ⚠️ `dag_criada = 0` também é o estado de quem está SENDO REGERADO agora (é
    assim que a factory seleciona o lote). Sem o OR abaixo, a aresta desenhada
    no meio de uma publicação — cenário que a republicação da malha torna
    comum, porque o operador continua no canvas — não deixava carimbo nenhum:
    o pipeline terminava "em dia" com a DAG sem a dependência, mudo. O EXISTS
    reconhece a publicação em voo pela fila do reconciliador (achado da
    revisão adversarial)."""
    try:
        cur.execute(
            "UPDATE dbo.etl_pipeline SET dag_config_pendente_em = GETDATE() "
            "WHERE pipeline_name = ? AND (dag_criada = 1 OR EXISTS ("
            "  SELECT 1 FROM dbo.etl_dag_pendente q "
            "  WHERE q.pipeline_name = dbo.etl_pipeline.pipeline_name "
            "    AND q.status = 'pendente'))",
            (pipeline_name,))
        return (cur.rowcount or 0) > 0
    except Exception as e:
        log.debug("[MALHA] dag_config_pendente_em indisponível (migration 073?): %s", e)
        return False


def _coluna_073(cur) -> bool:
    """True se etl_pipeline.dag_config_pendente_em (migration 073) existe — o
    guard de LEITURA do carimbo de publicação pendente (o de escrita é o
    try/except de _ligar_dag_config_pendente). Best-effort no padrão dos
    demais guards de coluna: falha conta como ausente e quem lê degrada para
    "não sei se está pendente" (chave ausente no payload), nunca para uma
    tela quebrada."""
    try:
        cur.execute("SELECT COL_LENGTH('dbo.etl_pipeline', 'dag_config_pendente_em')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem da coluna da migration 073 falhou: %s", e)
        return False


def _agora() -> datetime:
    """Relógio do servidor, isolado para os testes congelarem o tempo."""
    return datetime.now()


def _malha_oficial(cur, malha_name):
    """Grafia registrada da malha (a colação CI casa qualquer caixa; o retorno
    é a oficial) ou None se não existe."""
    cur.execute("SELECT malha_name FROM dbo.etl_malha WHERE malha_name = ?",
                (malha_name,))
    row = cur.fetchone()
    return (row[0] or "").strip() if row else None


def _pipeline_oficial(cur, pipeline_name):
    """Grafia registrada do pipeline em etl_pipeline, ou None se não existe.

    Mesma regra da PR #236 (incidente 2026-08-01): membro gravado em grafia
    divergente do registro some nos dicts case-sensitive do Python — aqui o
    nome é canonizado ANTES de qualquer gravação. Implementação extraída para
    services.execucao_identidade na F2 (o drill-down por etapa precisa da MESMA
    canonização) — mesmo padrão de _virada_global delegando para o service."""
    return ident_svc.pipeline_oficial(cur, pipeline_name)


def _espelho_csv(cur, pipeline, depende_de, acao):
    """Sincroniza o CSV etl_pipeline.depends_on do DEPENDENTE com a tabela 067,
    na MESMA transação da escrita (regra da F6 da spec: o CSV é o fallback do
    etl_dag_factory e do preview até a retomada — divergir aqui recriaria o
    defeito que a F1 fechou, a tela contando uma história e a DAG outra).

    acao: 'add' acrescenta se ausente; 'remove' tira se presente — sempre por
    comparação case-insensitive (a colação do banco é CI) e sem duplicar
    (deduplicar da F1). Devolve True se o CSV mudou."""
    cur.execute("SELECT depends_on FROM dbo.etl_pipeline WHERE pipeline_name = ?",
                (pipeline,))
    row = cur.fetchone()
    raw = str(row[0]).strip() if row and row[0] else ""
    lista = deduplicar(d for d in raw.split(",") if d.strip())
    chave = (depende_de or "").casefold()
    if acao == "add":
        if any(d.casefold() == chave for d in lista):
            return False
        lista.append(depende_de)
    else:
        nova = [d for d in lista if d.casefold() != chave]
        if len(nova) == len(lista):
            return False
        lista = nova
    cur.execute(
        "UPDATE dbo.etl_pipeline SET depends_on = ?, updated_at = GETDATE() "
        "WHERE pipeline_name = ?", (",".join(lista) or None, pipeline))
    return True


def criticidade_agregada(criticidades):
    """A criticidade da malha é a MAIS ALTA entre os membros
    (Critica > Alta > Media > Baixa) — regra do cartão da tela.

    Valor fora do domínio conta como Media (o mesmo default do ISNULL do
    GET /malha) para um texto livre inesperado não derrubar a listagem.
    Malha sem membros devolve None: não se inventa criticidade do nada."""
    melhor = None          # valor como está gravado (a tela upper-casa)
    melhor_rank = -1
    for crit in criticidades:
        c = (str(crit).strip() if crit else "") or "Media"
        rank = _CRIT_ORDEM.get(c.upper(), _CRIT_ORDEM["MEDIA"])
        if rank > melhor_rank:
            melhor, melhor_rank = c, rank
    return melhor


# ── Compilador do Aguarde (F11 — desenho §3/§7) ──────────────────────────────
# O Aguarde é açúcar de compilação: a expansão N×M (canônico em dags/utils/
# malha_nos.py, port em services) vira linhas NORMAIS da 067 assinadas com
# origem_no. O diff de cada gesto é calculado sobre o estado PROSPECTIVO do
# desenho × o estado CORRENTE da 067 — dry_run devolve o efeito §7.2 sem
# gravar; o write recomputa e aplica na MESMA transação (espelho CSV +
# carimbo). Nada aqui é lido pelo motor: quem libera segue sendo liberado().


def _efeito_vazio() -> dict:
    """O bloco `efeito` do §7.2 com todas as chaves — o schema é contrato
    (o modal da F12 itera as listas): gesto sem efeito devolve listas vazias,
    nunca chave ausente. `agendamentos` é preenchido pela F13 (Início)."""
    return {"dependencias_criar": [], "dependencias_remover": [],
            "dependencias_transferir": [], "ja_existentes_manuais": [],
            "agendamentos": [], "republicar": []}


def _nos_globais(cur) -> dict:
    """Mapa global id → {"malha", "tipo"} de etl_malha_no: é o que diz de QUEM
    é cada linha assinada da 067 (a ponte da Decisão 1) e quais OUTRAS malhas
    são candidatas na transferência (§7.3)."""
    cur.execute("SELECT id, malha_name, tipo FROM dbo.etl_malha_no")
    return {int(r[0]): {"malha": (str(r[1]) or "").strip(),
                        "tipo": (str(r[2]) or "").strip().lower()}
            for r in cur.fetchall()}


def _linhas_067(cur) -> dict:
    """Todas as linhas tipo PIPELINE da 067 COM a assinatura, num SELECT só
    (agregação em Python — o padrão do arquivo): {(dep_cf, pred_cf):
    {"dependente", "predecessor", "origem_no"}}. Chamar só com a coluna
    origem_no presente (o chamador guarda)."""
    cur.execute(
        "SELECT pipeline_name, depende_de, origem_no "
        "FROM dbo.etl_pipeline_dependencia WHERE tipo = 'PIPELINE'")
    out = {}
    for r in cur.fetchall():
        dep = str(r[0] or "").strip()
        pred = str(r[1] or "").strip()
        out[(dep.casefold(), pred.casefold())] = {
            "dependente": dep, "predecessor": pred,
            "origem_no": int(r[2]) if r[2] is not None else None}
    return out


def _pares_expansao(dependencias) -> dict:
    """Conjunto compilado {(dep, pred, no_id)} → pares por chave CI:
    {(dep_cf, pred_cf): {"dependente", "predecessor", "nos": set[int]}}.
    Dois Aguardes da mesma malha podem produzir o MESMO par (a 067 tem uma
    linha só por par — ux_dep): o dono é UM nó por vez; o menor id é o
    escolhido determinístico quando a linha nasce."""
    pares: dict = {}
    for dependente, predecessor, no_id in dependencias:
        ch = (dependente.casefold(), predecessor.casefold())
        item = pares.setdefault(ch, {"dependente": dependente,
                                     "predecessor": predecessor, "nos": set()})
        item["nos"].add(no_id)
    return pares


def _dag_criada(cur, pipeline) -> bool:
    """dag_criada do pipeline — decide quem entra em `republicar` (o carimbo
    só existe para DAG publicada; pipeline nunca publicado não tem versão
    velha rodando — a mesma regra do WHERE dag_criada = 1 da 073)."""
    cur.execute("SELECT CAST(dag_criada AS INT) FROM dbo.etl_pipeline "
                "WHERE pipeline_name = ?", (pipeline,))
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) == 1)


def _diff_compilacao(cur, malha, nos_l, arestas_l):
    """O diff §7.2 do gesto: expansão do desenho PROSPECTIVO da malha × estado
    corrente da 067. Devolve o dict interno (itens carregam origem_no para o
    apply; a versão pública sai de _efeito_publico):

      criar      — pares novos, assinados com o menor nó produtor
      manuais    — par desejado que JÁ EXISTE manual (origem_no NULL): não é
                   adotado nem re-criado (Decisão 5 — a linha continua do
                   operador; a exclusão do nó não a leva)
      transferir — linha assinada cujo nó dono deixou de produzi-la mas que a
                   expansão (desta malha OU de outra, §7.3) ainda produz:
                   re-assinada, nunca removida — dentro da própria malha isso
                   também é obrigatório, senão a FK da 075 travaria o DELETE
                   do nó e a proveniência mentiria
      remover    — linha assinada por nó DESTA malha que expansão nenhuma
                   produz mais
      avisos     — par desejado já compilado por OUTRA malha (Decisão 4: não
                   re-assinado; quem manda é a dona — se ela descompilar, a
                   transferência §7.3 o traz para cá)
      republicar — dependentes de criar/remover com dag_criada=1
      pares_pos  — o conjunto PÓS-gesto {(dep_cf,pred_cf): (dep, pred)} — a
                   base do ciclo da Decisão 15 e do preview_expandido (F12)
    """
    expansao = malha_nos_svc.expandir(nos_l, arestas_l)
    desejado = _pares_expansao(expansao["dependencias"])
    nos_info = _nos_globais(cur)
    linhas = _linhas_067(cur)
    malha_cf = malha.casefold()

    def _malha_do_no(no_id):
        info = nos_info.get(no_id)
        return (info["malha"] if info else "").casefold()

    criar, remover, transferir, manuais, avisos = [], [], [], [], []

    # 1) pares que a expansão PROSPECTIVA desta malha produz
    for ch in sorted(desejado):
        item = desejado[ch]
        linha = linhas.get(ch)
        no_alvo = min(item["nos"])
        if linha is None:
            criar.append({"dependente": item["dependente"],
                          "predecessor": item["predecessor"],
                          "origem_no": no_alvo})
        elif linha["origem_no"] is None:
            manuais.append({"dependente": linha["dependente"],
                            "predecessor": linha["predecessor"]})
        elif _malha_do_no(linha["origem_no"]) == malha_cf:
            if linha["origem_no"] not in item["nos"]:
                # o nó dono saiu do desenho (ou perdeu o par), mas OUTRO nó
                # desta malha ainda o produz: re-assina — transferência dentro
                # da própria malha
                transferir.append({"dependente": linha["dependente"],
                                   "predecessor": linha["predecessor"],
                                   "para_malha": malha, "para_no": no_alvo,
                                   "origem_no": linha["origem_no"]})
            # senão: já compilada por este desenho — nada a fazer
        else:
            dona = nos_info.get(linha["origem_no"], {})
            avisos.append(
                f"'{linha['dependente']}' → '{linha['predecessor']}' já "
                f"compilada pelo Aguarde #{linha['origem_no']} da malha "
                f"'{dona.get('malha')}' — não re-assinada (a linha continua "
                "da malha dona; se ela descompilar, a assinatura transfere)")

    # 2) linhas assinadas por nós DESTA malha que a expansão nova não produz:
    #    transferência para OUTRA malha que as produza (§7.3) ou remoção
    cache_outras: dict = {}
    for ch in sorted(linhas):
        linha = linhas[ch]
        if linha["origem_no"] is None or ch in desejado:
            continue
        if _malha_do_no(linha["origem_no"]) != malha_cf:
            continue
        destino = _transferencia_externa(cur, ch, malha_cf, nos_info,
                                         cache_outras)
        if destino is not None:
            transferir.append({"dependente": linha["dependente"],
                               "predecessor": linha["predecessor"],
                               "para_malha": destino[0], "para_no": destino[1],
                               "origem_no": linha["origem_no"]})
        else:
            remover.append({"dependente": linha["dependente"],
                            "predecessor": linha["predecessor"],
                            "origem_no": linha["origem_no"]})

    # 3) republicar: dependentes afetados COM DAG publicada (transferência não
    #    muda o grafo do motor — só a proveniência — e fica de fora)
    republicar = []
    for nome in sorted({i["dependente"] for i in criar + remover},
                       key=str.casefold):
        if _dag_criada(cur, nome):
            republicar.append(nome)

    # 4) o conjunto PÓS-gesto (067 − remoções ∪ adições) — Decisão 15 e preview
    pares_pos = {ch: (linha["dependente"], linha["predecessor"])
                 for ch, linha in linhas.items()}
    for item in remover:
        pares_pos.pop((item["dependente"].casefold(),
                       item["predecessor"].casefold()), None)
    for item in criar:
        pares_pos[(item["dependente"].casefold(),
                   item["predecessor"].casefold())] = (item["dependente"],
                                                       item["predecessor"])

    return {"criar": criar, "remover": remover, "transferir": transferir,
            "manuais": manuais, "avisos": avisos, "republicar": republicar,
            "pares_pos": pares_pos}


def _transferencia_externa(cur, ch, malha_cf, nos_info, cache):
    """Outra malha cuja expansão produz o par `ch` (§7.3): devolve
    (malha_oficial, no_id) ou None. Só malhas com nó Aguarde entram; a busca é
    determinística (malhas em ordem CI, menor nó produtor) e o resultado por
    malha é cacheado dentro do gesto — malhas são dezenas, não milhares."""
    candidatas = sorted({info["malha"] for info in nos_info.values()
                         if info["tipo"] == "aguarde"
                         and info["malha"].casefold() != malha_cf},
                        key=str.casefold)
    for outra in candidatas:
        if outra not in cache:
            expansao = malha_nos_svc.expandir(_nos_da_malha(cur, outra),
                                              _arestas_da_malha(cur, outra))
            cache[outra] = _pares_expansao(expansao["dependencias"])
        pares = cache[outra]
        if ch in pares:
            return outra, min(pares[ch]["nos"])
    return None


def _erros_ciclo_canonico(diff) -> list:
    """Ciclo sobre o conjunto PÓS-expansão do gesto (Decisão 15), com o BFS
    canônico da F1 (_check_circular_grafo) e a MESMA mensagem literal — o
    defeito 3 do QA não renasce pela porta da expansão: um aguarde inocente
    pode fechar A→…→A por linhas que o gesto cria aos pares."""
    if not diff["criar"]:
        return []
    adjacencia: dict = {}
    for dependente, predecessor in diff["pares_pos"].values():
        adjacencia.setdefault(dependente.casefold(), []).append(predecessor)
    por_dependente: dict = {}
    for item in diff["criar"]:
        por_dependente.setdefault(item["dependente"], []).append(item["predecessor"])
    erros = []
    for dependente in sorted(por_dependente, key=str.casefold):
        try:
            _check_circular_grafo(
                dependente, sorted(por_dependente[dependente], key=str.casefold),
                lambda nome: adjacencia.get(nome.casefold(), []))
        except ValueError as e:
            erros.append(str(e))
    return erros


def _aplicar_compilacao(cur, diff, criado_por):
    """Aplica o diff na transação ABERTA do gesto (quem commita é o endpoint —
    uma transação só, rollback explícito): transferências primeiro (UPDATE de
    assinatura — obrigatórias ANTES do DELETE do nó, §1.4), depois remoções e
    criações, cada uma com o espelho CSV do dependente na MESMA transação (o
    mesmíssimo _espelho_csv das portas F5/F8 — nunca uma cópia), e por fim o
    carimbo de republicação dos afetados (WHERE dag_criada = 1)."""
    for item in diff["transferir"]:
        cur.execute(
            "UPDATE dbo.etl_pipeline_dependencia SET origem_no = ? "
            "WHERE pipeline_name = ? AND depende_de = ? AND tipo = 'PIPELINE'",
            (item["para_no"], item["dependente"], item["predecessor"]))
    afetados = {i["dependente"] for i in diff["criar"]}
    for item in diff["remover"]:
        # DELETE pela ASSINATURA: linha manual coincidente (origem_no NULL)
        # nunca é atingida — Decisão 5, garantida no próprio WHERE.
        cur.execute(
            "DELETE FROM dbo.etl_pipeline_dependencia "
            "WHERE pipeline_name = ? AND depende_de = ? AND tipo = 'PIPELINE' "
            "AND origem_no = ?",
            (item["dependente"], item["predecessor"], item["origem_no"]))
        if (cur.rowcount or 0) > 0:
            # Espelho e carimbo SÓ para remoção EFETIVADA (achado da revisão):
            # rowcount 0 = gesto concorrente transferiu/limpou a assinatura
            # entre o cômputo do diff e o apply — tirar o predecessor do CSV
            # com a linha da 067 ainda viva recriaria a divergência que a F6
            # existe para impedir.
            _espelho_csv(cur, item["dependente"], item["predecessor"], "remove")
            afetados.add(item["dependente"])
    for item in diff["criar"]:
        cur.execute(
            "INSERT INTO dbo.etl_pipeline_dependencia "
            "(pipeline_name, depende_de, tipo, criado_por, origem_no) "
            "VALUES (?, ?, 'PIPELINE', ?, ?)",
            (item["dependente"], item["predecessor"],
             (criado_por or "")[:100] or None, item["origem_no"]))
        _espelho_csv(cur, item["dependente"], item["predecessor"], "add")
    for nome in sorted(afetados, key=str.casefold):
        _ligar_dag_config_pendente(cur, nome)


def _efeito_publico(diff) -> dict:
    """O bloco `efeito` do contrato §7.2 (chaves literais; origem_no interno
    fica de fora — a proveniência pública é a do transferir)."""
    if diff is None:
        return _efeito_vazio()
    return {
        "dependencias_criar": [
            {"dependente": i["dependente"], "predecessor": i["predecessor"]}
            for i in diff["criar"]],
        "dependencias_remover": [
            {"dependente": i["dependente"], "predecessor": i["predecessor"]}
            for i in diff["remover"]],
        "dependencias_transferir": [
            {"dependente": i["dependente"], "predecessor": i["predecessor"],
             "para_malha": i["para_malha"], "para_no": i["para_no"]}
            for i in diff["transferir"]],
        "ja_existentes_manuais": list(diff["manuais"]),
        "agendamentos": [],          # F13 (Início) — chave presente por contrato
        "republicar": list(diff["republicar"]),
    }


def _avisos_gesto(nos_l, arestas_l, diff) -> list:
    """Avisos do gesto = estruturais do desenho (§2.2, formato F10) + os do
    COMPILADOR (par já compilado por outra malha — Decisão 4), no MESMO
    formato {"no", "nivel", "mensagem"} para o toast/banner da F12 renderizar
    uma lista só (aviso de compilação não pertence a um nó do desenho:
    no=None)."""
    avisos = _avisos_desenho(nos_l, arestas_l)
    for msg in (diff["avisos"] if diff else []):
        avisos.append({"no": None, "nivel": "leve", "mensagem": msg})
    return avisos


def _preview_expandido(diff) -> list:
    """O conjunto PÓS-gesto como pares {pipeline_name, depende_de} — ADITIVO ao
    §7.2, é sobre ele que o espelho client-side do ciclo (criaCiclo, F12) roda
    (§3.3: cliente avisa antes, servidor é a autoridade, texto idêntico)."""
    if diff is None:
        return []
    return [{"pipeline_name": dep, "depende_de": pred}
            for dep, pred in sorted(diff["pares_pos"].values(),
                                    key=lambda p: (p[0].casefold(),
                                                   p[1].casefold()))]


def _exigir_compilacao(cur, conn):
    """Gesto que COMPILA (envolve Aguarde) precisa da 067 e da coluna de
    assinatura: sem elas não existe 'gravar sem assinar' honesto — 503 com a
    migration certa, no padrão das guardas do arquivo."""
    _exigir_tabela_067(cur, conn)
    if not _coluna_origem_no(cur):
        _fechar_silencioso(conn)
        raise HTTPException(status_code=503, detail=_MSG_SEM_075)


def _descompilacao_possivel(cur) -> bool:
    """Gesto que só DESCOMPILA (remover aresta/nó): sem 067 ou sem a coluna de
    assinatura não EXISTE linha compilada — o gesto segue como na F10, com
    diff vazio (deploy parcial não trava a limpeza do desenho)."""
    return _tabela_067(cur) and _coluna_origem_no(cur)


# ── Compilador do Início (F13 — desenho §4) ──────────────────────────────────
# O agendamento mora na MALHA (etl_malha.agendamento_json, Decisão 8); o nó
# Início é a representação visual e o fio que diz QUEM recebe. Compilar =
# COPIAR os campos para as colunas reais de cada raiz ligada + assinar
# agenda_no + carimbar dag_config_pendente_em — o scheduler do Airflow dispara
# todas no mesmo tick, cada uma na própria DAG; nenhum disparador novo (§4.2).
# O motor NUNCA lê o JSON da malha.

# O schema do agendamento é EXATAMENTE o subconjunto de campos do register
# (§4.1) — chave fora dele é 422: o JSON é fonte de compilação, não saco de
# configuração. hora_virada incluída de propósito (Decisão 9: UMA virada por
# malha, aplicada a TODAS as raízes — mata o risco 4 da spec na raiz).
_CAMPOS_AGENDAMENTO = (
    "schedule_type", "schedule_hour", "schedule_minute", "schedule_dow",
    "schedule_dom", "horarios_especificos", "dias_semana",
    "dias_horarios_mes", "somente_dias_uteis", "calendario_nome",
    "hora_virada",
)

# Nomes dos dias p/ resumo humano (D05 de guarda: convenção cron, 0=domingo).
_DOW_NOMES = {0: "dom", 1: "seg", 2: "ter", 3: "qua", 4: "qui", 5: "sex",
              6: "sáb"}


def _colunas_agenda(cur) -> bool:
    """True se as colunas de agendamento da 075 existem (etl_malha.
    agendamento_json + etl_pipeline.agenda_no). Best-effort no padrão dos
    guards de coluna (073/074): falha conta como ausente e o Início se
    comporta como na F12 (só desenho, zero efeito)."""
    try:
        cur.execute(
            "SELECT COL_LENGTH('dbo.etl_malha', 'agendamento_json'), "
            "COL_LENGTH('dbo.etl_pipeline', 'agenda_no')")
        row = cur.fetchone()
        return bool(row and row[0] is not None and row[1] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem das colunas de agendamento da 075 falhou: %s", e)
        return False


def _int_agenda(bruto, campo, minimo, maximo, default):
    """Inteiro de um campo do agendamento, com faixa: o JSON da malha é
    superfície NOVA — dá para validar faixa sem quebrar paridade com o
    register (que herda a tolerância do formulário)."""
    v = bruto.get(campo)
    if v is None or v == "":
        return default
    if isinstance(v, bool) or not isinstance(v, int):
        raise HTTPException(status_code=422,
                            detail=f"{campo} deve ser um inteiro")
    if not (minimo <= v <= maximo):
        raise HTTPException(
            status_code=422,
            detail=f"{campo} fora do intervalo ({minimo}-{maximo}): {v}")
    return v


def _validar_agendamento(bruto):
    """Valida e NORMALIZA o agendamento da malha (§4.1, Decisão 8) — pelas
    MESMAS funções do register: _validate_dias_horarios_mes,
    _parse_horarios_especificos (422 nos inválidos) e _parse_hora_opcional
    (hora_virada inválida degrada para NULL com aviso — D35). Devolve
    (agendamento_normalizado, avisos_texto).

    'on_demand' é recusado de propósito: desligar raiz do cron é o gesto de
    DESLIGAR a aresta/o Início (Decisão 10) — um agendamento 'sob demanda'
    seria um não-agendamento guardado como se fosse um."""
    if not isinstance(bruto, dict) or not bruto:
        raise HTTPException(status_code=422,
                            detail="agendamento deve ser um objeto com os "
                                   "campos do agendamento da malha")
    extras = sorted(set(bruto) - set(_CAMPOS_AGENDAMENTO))
    if extras:
        raise HTTPException(
            status_code=422,
            detail="Campos fora do schema do agendamento da malha: "
                   + ", ".join(extras))
    st = str(bruto.get("schedule_type") or "").strip().lower()
    if not st:
        raise HTTPException(status_code=422,
                            detail="schedule_type é obrigatório no "
                                   "agendamento da malha")
    if st == "on_demand":
        raise HTTPException(
            status_code=422,
            detail="O agendamento da malha não aceita 'on_demand' — para "
                   "tirar uma raiz do cron, desligue-a do Início (a raiz "
                   "vira sob demanda no gesto).")
    avisos: list[str] = []
    horarios = _parse_horarios_especificos(bruto.get("horarios_especificos"))
    if st == "custom" and not horarios:
        raise HTTPException(
            status_code=422,
            detail="horarios_especificos é obrigatório para schedule_type "
                   "'custom'")
    dias_horarios = _validate_dias_horarios_mes(bruto.get("dias_horarios_mes"))
    if st == "monthly_days_times" and not dias_horarios:
        # Mesma mensagem literal do register.
        raise HTTPException(
            status_code=422,
            detail="dias_horarios_mes é obrigatório para schedule_type "
                   "'monthly_days_times'")
    dias_semana = None
    dias_raw = str(bruto.get("dias_semana") or "").strip()
    if dias_raw:
        dias = []
        for d in dias_raw.split(","):
            d = d.strip()
            if not d:
                continue
            if not d.isdigit() or not (0 <= int(d) <= 6):
                raise HTTPException(
                    status_code=422,
                    detail=f"dias_semana inválido: '{d}' (use 0-6, 0=domingo)")
            dias.append(int(d))
        dias_semana = ",".join(str(d) for d in sorted(set(dias))) or None
    hora = _int_agenda(bruto, "schedule_hour", 0, 23, 6)
    minuto = _int_agenda(bruto, "schedule_minute", 0, 59, 0)
    dom = _int_agenda(bruto, "schedule_dom", 1, 28, 1)
    if st == "biweekly" and dom > 13:
        # Quinzenal é dia D e D+15: dom 17–28 gera cron com dia 32–43 (não
        # existe → Broken DAG após republicar, e a raiz PARA de agendar) e
        # 14–16 cai em 29–31, que pula meses curtos — quinzena falsa. A MESMA
        # regra e mensagem do wizard (defeito GRAVE da revisão adversarial).
        raise HTTPException(
            status_code=422,
            detail=f"Dia da 1ª quinzena inválido (1–13): {dom}")
    # custom/monthly_days_times: hora/minuto seguem o PRIMEIRO horário — a
    # mesma derivação do wizard (buildSchedulePayload), para as colunas das
    # raízes contarem uma história só.
    if st == "custom" and horarios:
        hora, minuto = int(horarios[:2]), int(horarios[3:5])
    elif st == "monthly_days_times" and dias_horarios:
        primeiro = json.loads(dias_horarios)[0]["horarios"][0]
        hora, minuto = int(primeiro[:2]), int(primeiro[3:5])
    return {
        "schedule_type": st,
        "schedule_hour": hora,
        "schedule_minute": minuto,
        "schedule_dow": _int_agenda(bruto, "schedule_dow", 0, 6, 1),
        "schedule_dom": dom,
        "horarios_especificos": horarios,
        "dias_semana": dias_semana,
        "dias_horarios_mes": dias_horarios,
        "somente_dias_uteis": 1 if bruto.get("somente_dias_uteis") in (1, True) else 0,
        "calendario_nome": (str(bruto.get("calendario_nome") or "").strip() or None),
        "hora_virada": _parse_hora_opcional("hora_virada",
                                            bruto.get("hora_virada"), avisos),
    }, avisos


def _scheduled_time_do_agendamento(ag) -> str:
    """scheduled_time DERIVADO do agendamento (a mesma derivação do wizard):
    o gerador de DAGs monta o cron a partir de scheduled_time — sem alinhar a
    coluna, cada raiz dispararia no horário antigo dela e o aceite 'crons
    idênticos' (§10-F13) seria impossível. Não entra no schema §4.1 porque é
    derivado, nunca escolhido."""
    st = ag.get("schedule_type")
    if st == "custom" and ag.get("horarios_especificos"):
        return f"{ag['horarios_especificos'][:5]}:00"
    if st == "monthly_days_times" and ag.get("dias_horarios_mes"):
        try:
            primeiro = json.loads(ag["dias_horarios_mes"])[0]["horarios"][0]
            return f"{primeiro}:00"
        except Exception:
            pass
    return f"{int(ag.get('schedule_hour') or 0):02d}:" \
           f"{int(ag.get('schedule_minute') or 0):02d}:00"


def _resumo_agendamento(ag) -> str:
    """Resumo humano de um agendamento (o 'de'/'para' do diff §7.2 e o
    subtítulo do nó Início). Display-only: a autoridade do gatilho é o
    scheduler — mesmo estatuto do calcularDataRef da F5."""
    if not isinstance(ag, dict) or not ag:
        return "sem agendamento"
    st = str(ag.get("schedule_type") or "").strip().lower()
    if st == "on_demand":
        return "sob demanda"
    try:
        h = int(ag.get("schedule_hour") or 0)
        m = int(ag.get("schedule_minute") or 0)
    except (TypeError, ValueError):
        h, m = 0, 0
    hm = f"{h:02d}:{m:02d}"
    if st == "weekly":
        # dow 0 é DOMINGO (D05) — `or 1` engoliria o zero e viraria segunda.
        dow_raw = ag.get("schedule_dow")
        try:
            dow = int(dow_raw) if dow_raw not in (None, "") else 1
        except (TypeError, ValueError):
            dow = 1
        corpo = f"semanal ({_DOW_NOMES.get(dow, '?')}) {hm}"
    elif st == "monthly":
        corpo = f"mensal (dia {ag.get('schedule_dom') or 1}) {hm}"
    elif st == "biweekly":
        try:
            d = int(ag.get("schedule_dom") or 1)
        except (TypeError, ValueError):
            d = 1
        corpo = f"quinzenal (dias {d} e {d + 15}) {hm}"
    elif st == "hourly":
        corpo = f"de hora em hora (minuto {m:02d})"
    elif st == "custom":
        corpo = f"horários {ag.get('horarios_especificos') or '—'}"
        dias = str(ag.get("dias_semana") or "").strip()
        if dias:
            nomes = ", ".join(_DOW_NOMES.get(int(d), "?")
                              for d in dias.split(",") if d.strip().isdigit())
            corpo += f" ({nomes})"
    elif st == "monthly_days_times":
        try:
            entradas = json.loads(ag.get("dias_horarios_mes") or "[]")
            corpo = "dia+hora: " + "; ".join(
                f"dia {e['dia']} às {', '.join(e['horarios'])}"
                for e in entradas)
        except Exception:
            corpo = "dia+hora (configuração ilegível)"
    elif st == "daily":
        corpo = f"diário {hm}"
    else:
        corpo = f"{st} {hm}"
    extras = []
    if int(ag.get("somente_dias_uteis") or 0):
        extras.append("só dias úteis")
    if ag.get("calendario_nome"):
        extras.append(f"calendário {ag['calendario_nome']}")
    if ag.get("hora_virada"):
        extras.append(f"virada {str(ag['hora_virada'])[:5]}")
    return " · ".join([corpo] + extras)


def _agendamento_da_malha(cur, malha):
    """agendamento_json da malha → dict, ou None (ausente/ilegível — mesmo
    espírito do _no_config: valor quebrado por SQL direto degrada com log,
    nunca tela quebrada). Chamar só com _colunas_agenda True."""
    cur.execute("SELECT agendamento_json FROM dbo.etl_malha "
                "WHERE malha_name = ?", (malha,))
    row = cur.fetchone()
    return _no_config(row[0] if row else None)


def _agenda_da_raiz(cur, pipeline):
    """Fotografia de agendamento de um pipeline raiz: o dict de agenda (o
    'de' do diff), a assinatura agenda_no (+ malha dona do nó) e dag_criada.
    Chamar só com _colunas_agenda True."""
    cur.execute(
        "SELECT p.schedule_type, CAST(p.schedule_hour AS INT), "
        "CAST(p.schedule_minute AS INT), CAST(p.schedule_dow AS INT), "
        "CAST(p.schedule_dom AS INT), p.horarios_especificos, p.dias_semana, "
        "p.dias_horarios_mes, CAST(p.somente_dias_uteis AS INT), "
        "p.calendario_nome, CONVERT(VARCHAR(5), p.hora_virada, 108), "
        "p.agenda_no, n.malha_name, CAST(p.dag_criada AS INT) "
        "FROM dbo.etl_pipeline p "
        "LEFT JOIN dbo.etl_malha_no n ON n.id = p.agenda_no "
        "WHERE p.pipeline_name = ?", (pipeline,))
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "agendamento": {
            "schedule_type": (str(row[0]).strip().lower() if row[0] else None),
            "schedule_hour": row[1], "schedule_minute": row[2],
            "schedule_dow": row[3], "schedule_dom": row[4],
            "horarios_especificos": row[5], "dias_semana": row[6],
            "dias_horarios_mes": row[7], "somente_dias_uteis": row[8],
            "calendario_nome": row[9], "hora_virada": row[10],
        },
        "agenda_no": int(row[11]) if row[11] is not None else None,
        "agenda_malha": (str(row[12]).strip() if row[12] else None),
        "dag_criada": int(row[13] or 0),
    }


def _mesma_agenda(agenda_raiz, ag_malha) -> bool:
    """True se a raiz JÁ carrega o agendamento da malha, campo a campo (hora
    normalizada para HH:MM — a coluna devolve VARCHAR(5), o JSON guarda
    HH:MM:SS). Decide se um re-salvar de aresta tem efeito ou é no-op."""
    def _hv(v):
        return str(v)[:5] if v else None

    for campo in _CAMPOS_AGENDAMENTO:
        a, b = agenda_raiz.get(campo), ag_malha.get(campo)
        if campo == "hora_virada":
            a, b = _hv(a), _hv(b)
        elif campo == "somente_dias_uteis":
            a, b = int(a or 0), int(b or 0)
        elif campo in ("schedule_hour", "schedule_minute", "schedule_dow",
                       "schedule_dom"):
            a = int(a) if a is not None else None
            b = int(b) if b is not None else None
        else:
            a = str(a).strip() if a not in (None, "") else None
            b = str(b).strip() if b not in (None, "") else None
        if a != b:
            return False
    return True


def _raiz_tem_dependencia(cur, pipeline) -> bool:
    """True se o pipeline tem QUALQUER dependência (tipo PIPELINE) na 067 —
    a pergunta do 422 de raiz (§2.2): dependente vira schedule=None no
    gerador, e o agendamento plantado seria mentira."""
    cur.execute(
        "SELECT TOP 1 1 FROM dbo.etl_pipeline_dependencia "
        "WHERE pipeline_name = ? AND tipo = 'PIPELINE'", (pipeline,))
    return cur.fetchone() is not None


def _msg_raiz_com_dependencia(pipeline) -> str:
    """422 do §2.2 (a pendência declarada pela revisão da F12): raiz não pode
    ter dependência — o schedule=None do motor venceria o cron e o
    agendamento da malha seria mentira."""
    return (f"'{pipeline}' não pode ser raiz da malha: raiz não pode ter "
            "dependência — o schedule=None do motor venceria o cron e o "
            "agendamento da malha seria mentira. Remova a dependência ou "
            "chegue a ele por um Aguarde.")


def _msg_raiz_de_outra_malha(pipeline, malha_dona, no_id) -> str:
    """422 da Decisão 11: um dono por vez — nunca last-write-wins mudo entre
    malhas; transferência é gesto explícito na malha dona."""
    return (f"'{pipeline}' já é agendado pelo Início #{no_id} da malha "
            f"'{malha_dona}' — um dono por vez: desligue-o de lá antes de "
            "agendá-lo por aqui.")


def _aplicar_agenda_na_raiz(cur, pipeline, ag, no_id):
    """COPIA o agendamento da malha para as colunas REAIS da raiz + assina
    agenda_no + carimba a republicação (WHERE dag_criada=1), na transação
    ABERTA do gesto (§4.2 — quem commita é o endpoint). UM UPDATE só, sem
    try/except por grupo de migration: o endpoint já exigiu a 075, e banco
    com a 075 tem as colunas de agenda (017/018/024/067) — falha aqui é
    rollback TOTAL, nunca cópia pela metade."""
    cur.execute(
        "UPDATE dbo.etl_pipeline SET scheduled_time = ?, schedule_type = ?, "
        "schedule_hour = ?, schedule_minute = ?, schedule_dow = ?, "
        "schedule_dom = ?, horarios_especificos = ?, dias_semana = ?, "
        "dias_horarios_mes = ?, somente_dias_uteis = ?, calendario_nome = ?, "
        "hora_virada = ?, agenda_no = ?, updated_at = GETDATE() "
        "WHERE pipeline_name = ?",
        (_scheduled_time_do_agendamento(ag), ag["schedule_type"],
         ag.get("schedule_hour"), ag.get("schedule_minute"),
         ag.get("schedule_dow"), ag.get("schedule_dom"),
         ag.get("horarios_especificos"), ag.get("dias_semana"),
         ag.get("dias_horarios_mes"), int(ag.get("somente_dias_uteis") or 0),
         ag.get("calendario_nome"), ag.get("hora_virada"), no_id, pipeline))
    _ligar_dag_config_pendente(cur, pipeline)


def _desligar_raiz(cur, pipeline):
    """Decisão 10: desligar a raiz do Início = 'on_demand' + limpar a
    assinatura + carimbo — NUNCA restauração do agendamento antigo (classe
    D40: pipeline voltando a rodar sozinho em silêncio). on_demand →
    schedule=None no gerador: DAG ativa, só manual, visível. As demais
    colunas de agenda ficam como estão — inertes para o gatilho (o
    on_demand curto-circuita o cron no gerador) e a hora_virada é
    PRESERVADA de propósito: mudá-la mudaria o rótulo ODATE de execuções
    já registradas."""
    cur.execute(
        "UPDATE dbo.etl_pipeline SET schedule_type = 'on_demand', "
        "agenda_no = NULL, updated_at = GETDATE() WHERE pipeline_name = ?",
        (pipeline,))
    _ligar_dag_config_pendente(cur, pipeline)


def _raizes_assinadas_do_no(cur, no_id) -> list:
    """Pipelines cuja assinatura agenda_no aponta para o nó — a fonte honesta
    para a exclusão do Início (§7.3): a FK NO ACTION da 075 derruba o DELETE
    do nó com assinatura pendurada, então desligar TODAS antes é a única
    ordem possível."""
    cur.execute("SELECT pipeline_name FROM dbo.etl_pipeline "
                "WHERE agenda_no = ?", (no_id,))
    return sorted((str(r[0]).strip() for r in cur.fetchall()),
                  key=str.casefold)


def _lista_curta(nomes, teto: int = 4) -> str:
    """`'A', 'B' e mais 3` — nomes de verdade na frase, sem virar parede.

    Aviso com contagem só ("3 pipelines desatualizados") obriga o operador a
    caçar QUAIS; aviso com 40 nomes ele não lê. O teto é baixo de propósito, e
    a lista completa continua no campo estruturado da resposta."""
    nomes = list(nomes)
    cabeca = ", ".join(f"'{n}'" for n in nomes[:teto])
    resto = len(nomes) - teto
    return f"{cabeca} e mais {resto}" if resto > 0 else cabeca


def _msg_disparo_raiz_com_dependencia(pipeline) -> str:
    """Aviso do dry_run do disparo manual (F15): a raiz tem dependência na
    067 — o trigger manual NÃO consulta liberado(), então a corrida parte por
    cima do predecessor. Mesma linguagem do 422 do §2.2 (raiz não pode ter
    dependência), em tom de aviso: o gesto continua sendo do operador."""
    return (f"'{pipeline}' tem dependência cadastrada — o disparo manual não "
            "consulta a liberação: a corrida parte POR CIMA do predecessor, "
            "sem esperar o SUCESSO dele na data. Se a intenção é respeitar a "
            "dependência, dispare o predecessor.")


def _msg_corrida_existente(pipeline, quantas, data_ref) -> str:
    """Aviso do dry_run do disparo manual (F15): já existe corrida da raiz na
    data. Os DEPENDENTES são protegidos pelo claim serializable (uma corrida
    por data), a RAIZ não — disparar de novo roda de novo."""
    return (f"'{pipeline}' já tem {quantas} corrida(s) registrada(s) em "
            f"{data_ref.strftime('%Y-%m-%d')} — disparar de novo executa o "
            "pipeline outra vez (a proteção de corrida única vale para os "
            "dependentes, não para a raiz disparada à mão).")


def _msg_contradicao(pipeline) -> str:
    """Aviso do badge de contradição (§2.2, última linha): raiz assinada que
    ganhou dependência por OUTRA porta — aviso, nunca bloqueio das portas."""
    return (f"raiz '{pipeline}' tem dependência cadastrada — o motor obedece "
            "a dependência e o agendamento da malha está inerte nela")


def _mesclar_efeito_agenda(efeito, efeito_ag, republicar_ag):
    """Anexa o efeito de agendamento do Início (F13) ao bloco §7.2 do gesto —
    `agendamentos` deixa de ser sempre-vazio e `republicar` une compilação e
    agenda, sem duplicar."""
    if efeito_ag:
        efeito["agendamentos"] = list(efeito_ag)
    if republicar_ag:
        efeito["republicar"] = sorted({*efeito["republicar"], *republicar_ag},
                                      key=str.casefold)
    return efeito


# ── Agregados do CARD da lista (etapas · última execução · gatilho) ──────────
# Os três campos são ADITIVOS no contrato do GET /malhas (front antigo ignora)
# e cada um degrada SOZINHO quando a migration que o sustenta falta. Nenhum
# deles abre consulta POR MALHA: a lista pode ter dezenas de malhas e um N+1
# aqui viraria dezenas de round-trips a cada refresh da tela.

# Campos de agendamento que o resumo do GATILHO lê do MEMBRO. É EXATAMENTE
# _CAMPOS_AGENDAMENTO (o mesmo schema da malha), inclusive os qualificadores
# somente_dias_uteis/calendario_nome/hora_virada: eles viram extras no
# _resumo_agendamento ("· só dias úteis · calendário X") e omiti-los faria a
# MESMA malha ter duas verdades — texto completo quando o gatilho vem do
# Início, texto podado quando vem dos membros. Uma linguagem só no card.
_CAMPOS_CRON_MEMBRO = _CAMPOS_AGENDAMENTO


def _ultima_execucao_por_pipeline(cur) -> dict:
    """{pipeline_casefold: (momento, status, pipeline)} — a corrida MAIS
    RECENTE de cada pipeline que é membro de ALGUMA malha. A composição por
    malha é feita em Python, sobre as linhas de membros que o endpoint já leu.

    O timestamp que responde "quando esta malha foi usada" é o **início da
    corrida** (COALESCE com criado_em, porque corrida ainda não partida —
    AGUARDANDO_DEPENDENCIA — tem inicio NULL e mesmo assim é registro real).
    NÃO é `data_referencia`: o ODATE é o dia de PROCESSAMENTO e pode estar no
    futuro ou no passado do relógio (uma corrida de 05/08 iniciada em 03/08 é
    rotina) — exibi-lo como "última execução" mentiria para o operador. E NÃO
    é `fim`: corrida EXECUTANDO ainda não tem fim e sumiria justamente quando
    é mais interessante.

    FORMA da consulta (top-1 por pipeline com CROSS APPLY, não um ROW_NUMBER
    sobre o JOIN inteiro): etl_pipeline_execucao é HISTÓRICO sem expurgo e
    esta leitura roda a cada abertura da tela. Ranquear o JOIN inteiro obriga
    a varrer a tabela toda; o APPLY entra por `pipeline_name = ?` — um SEEK
    por pipeline membro no índice ix_pipe_exec_ultima (migration 077), lendo
    só as corridas de quem está em alguma malha. NÃO existe recorte por data
    de propósito: malha parada há meses tem de continuar mostrando quando
    rodou pela última vez.

    Chamar só com _tabelas_067_execucao True."""
    cur.execute(
        "SELECT m.pipeline_name, u.status, u.momento "
        "FROM (SELECT DISTINCT pipeline_name FROM dbo.etl_malha_pipeline) m "
        "CROSS APPLY ("
        " SELECT TOP 1 e.status AS status,"
        "        COALESCE(e.inicio, e.criado_em) AS momento"
        " FROM dbo.etl_pipeline_execucao e"
        " WHERE e.pipeline_name = m.pipeline_name"
        " ORDER BY COALESCE(e.inicio, e.criado_em) DESC, e.id DESC) u")
    out = {}
    for pipeline, status, momento in cur.fetchall():
        out[str(pipeline or "").strip().casefold()] = (momento, status,
                                                       pipeline)
    return out


def _pipelines_com_dependencia(cur) -> set:
    """Nomes (casefold) dos pipelines que têm QUALQUER dependência PIPELINE na
    067. Dependente vira schedule=None no gerador: o cron gravado nele está
    INERTE, e contá-lo como gatilho da malha seria mentira na tela. Uma
    consulta só — chamar com _tabela_067 True."""
    cur.execute("SELECT DISTINCT pipeline_name "
                "FROM dbo.etl_pipeline_dependencia WHERE tipo = 'PIPELINE'")
    return {str(r[0]).strip().casefold() for r in cur.fetchall() if r[0]}


def _malhas_com_agenda_vigente(cur) -> set:
    """Malhas em que o agendamento salvo está REALMENTE VIGENTE: existe nó
    Início E existe ao menos uma raiz ASSINADA por ele (etl_pipeline.agenda_no
    apontando para aquele nó).

    Por que a checagem existe: `agendamento_json` sobrevive de propósito à
    exclusão do Início (§7.3/Decisão 10 — o nó é o plugue, recriá-lo não perde
    a configuração) e pode ser salvo ANTES de o Início ser desenhado. Nos dois
    casos as raízes estão em `on_demand` e NADA dispara — anunciar o horário
    guardado no card seria a mentira mais cara do produto, e ainda permanente
    (não há rota para limpar o agendamento).

    Uma consulta de CONJUNTO — chamar só com _tabelas_075 e _colunas_agenda
    True."""
    cur.execute(
        "SELECT DISTINCT n.malha_name FROM dbo.etl_malha_no n "
        "JOIN dbo.etl_pipeline p ON p.agenda_no = n.id "
        "WHERE n.tipo = 'inicio'")
    return {str(r[0]).strip() for r in cur.fetchall() if r[0]}


def _gatilho_sob_demanda() -> dict:
    """O gatilho honesto de quem não tem cron nenhum: a malha só anda por
    disparo manual (ou por push de um pipeline de fora dela)."""
    return {"origem": "nenhum", "resumo": "sob demanda", "horario": None,
            "qtd_pipelines": 0, "horarios": [], "detalhes": [],
            "agendamento": None}


def _gatilho_da_malha(ag) -> dict:
    """Gatilho quando a MALHA tem agendamento próprio VIGENTE (F13, Decisão 8):
    o resumo sai do MESMO _resumo_agendamento que o nó Início mostra — duas
    derivações do mesmo JSON divergiriam e a tela contradiria o diagrama.

    Chamar só para malha em _malhas_com_agenda_vigente: agendamento guardado
    sem Início ligado NÃO dispara nada e não pode virar horário no card."""
    return {"origem": "malha", "resumo": _resumo_agendamento(ag),
            "horario": _scheduled_time_do_agendamento(ag)[:5],
            "qtd_pipelines": 0, "horarios": [], "detalhes": [],
            "agendamento": ag}


def _gatilho_dos_membros(membros_cron) -> dict:
    """Gatilho DERIVADO dos membros que disparam sozinhos — cada item é
    {"pipeline", "agendamento"} já filtrado (ATIVO, schedule_type ≠ on_demand
    e sem dependência na 067).

    Um horário só → "diário 06:00 (2 pipelines)". Horários distintos → o MAIS
    CEDO com a indicação de que há outros ("06:00 · +2 horários"): o card não
    tem espaço para a lista, e esconder que existem outros faria o operador
    achar que a malha inteira parte às 06:00."""
    if not membros_cron:
        return _gatilho_sob_demanda()
    detalhes, horarios, resumos = [], [], []
    for m in membros_cron:
        ag = m["agendamento"]
        resumo = _resumo_agendamento(ag)
        hm = _scheduled_time_do_agendamento(ag)[:5]
        detalhes.append({"pipeline": m["pipeline"], "resumo": resumo,
                         "horario": hm})
        horarios.append(hm)
        resumos.append(resumo)
    detalhes.sort(key=lambda d: (d["horario"], d["pipeline"].casefold()))
    distintos = sorted(set(horarios))
    n = len(membros_cron)
    plural = "s" if n != 1 else ""
    if len(set(resumos)) == 1:
        # Todos com o MESMO agendamento: o resumo completo cabe e é exato.
        texto = f"{resumos[0]} ({n} pipeline{plural})"
    else:
        extras = len(distintos) - 1
        texto = f"{distintos[0]} · +{extras} horário{'s' if extras != 1 else ''}" \
            if extras > 0 else f"{distintos[0]} ({n} pipeline{plural})"
    return {"origem": "membros", "resumo": texto, "horario": distintos[0],
            "qtd_pipelines": n, "horarios": distintos, "detalhes": detalhes,
            "agendamento": None}


# ══════ F4 — a CORRIDA no card e no painel (spec-malha-execucao.md §9) ═══════
#
# O DEFEITO que este bloco existe para matar: o card da lista escolhe hoje a
# execução MAIS RECENTE entre os membros (`_ultima_execucao_por_pipeline` +
# o laço `melhor[malha]` de `list_malhas`). Com `CARGA_A` em FALHA às 03:00 e
# `CARGA_B` em SUCESSO às 03:40, a chave de comparação elege `CARGA_B` e o card
# diz **sucesso**. O gestor abre a tela às 8h, vê verde, e a malha falhou.
#
# A cura não é um desempate melhor: é trocar a PERGUNTA. O status passa a ser o
# da CORRIDA (`etl_malha_execucao`), que é um registro do CICLO — e o ciclo
# sabe dizer "falhou" e NOMEAR quem falhou, coisa que "o membro mais recente"
# nunca soube. `_ultima_execucao_por_pipeline` continua no payload como
# FALLBACK declarado (Decisão 41): é o que a malha sem corrida mostra, e é o que
# o front anterior a esta fase continua lendo.
#
# ── O orçamento de consultas, que é requisito e não detalhe ──────────────────
# DUAS consultas para a lista inteira, independentemente de haver 4 ou 40
# malhas (aceite da F4). Nenhuma por malha, nenhum probe extra:
#
#   (A) `_SQL_ULTIMA_CORRIDA` — um SEEK por malha em `ix_malha_exec_malha`,
#       dentro de UM `CROSS APPLY`. Traz também o relógio do teto (já avaliado
#       pelo BANCO) e o valor da config de quiescência, para que nem um nem
#       outro custem uma ida a mais;
#   (B) `_SQL_DENOMINADOR` — o snapshot de TODAS as corridas de (A) numa
#       consulta só, `WHERE malha_execucao_id IN (…)`, com a linha viva de cada
#       membro pendurada por LEFT JOIN.
#
# A sonda `tabela_085_presente()` NÃO é chamada aqui de propósito: seria uma
# terceira consulta para descobrir o que a primeira já descobre ao falhar. A
# degradação é por ERRO reconhecido (`mc._sem_085`), o mesmo padrão
# claim-não-check de `_exec_com_fallback_078` — que este bloco também usa, para
# a coluna `substituida_em` da 078.
#
# ── Por que a agregação é em Python, e não um `GROUP BY` de contadores ───────
# Porque o card precisa NOMEAR o culpado, e nome não sai de `COUNT`. A consulta
# (B) devolve uma linha por (corrida, membro, linha viva) — algumas centenas de
# linhas para 40 malhas — e quem classifica é `mc._classe_da_linha`, a MESMA
# função que a guardiã usa para decidir o desfecho (§6.4). Uma segunda
# implementação da classificação, em T-SQL, seria o motor e a tela discordando
# sobre o que é "falhou" — exatamente o que o módulo gêmeo existe para impedir.
# Os contadores da barra saem do mesmo laço, sem custo.
#
# ── O interruptor NÃO governa a leitura ─────────────────────────────────────
# `malha_corrida_ativa` (§11.2) governa quem ABRE e quem FECHA. Aqui ele não é
# consultado, e a razão é operacional: (i) com o interruptor em `0` nada abre,
# logo não há corrida, logo toda malha cai no fallback por AUSÊNCIA DE CAMPO —
# que é o estado do dia do deploy e o que a §11.3 descreve; (ii) se alguém
# DESLIGAR o interruptor com corridas já abertas (o gesto de rollback), essas
# corridas continuam existindo, continuam `ABERTA` e continuam sendo o único
# lugar onde o operador vê que precisa encerrá-las — `POST .../encerrar` não
# passa pelo portão justamente por ser a saída (§6.8). Esconder o registro
# nesse momento seria o card mentindo de novo, agora por omissão.

# `SEM_PROGRESSO` = corrida viva em que NADA se mexeu há tempo demais. O limiar
# é múltiplo da quiescência porque é o único relógio que a 085 configura, mas
# NÃO pode ser a própria quiescência: aquela é o relógio de FECHAMENTO ("nada
# mais vai acontecer", e ela só é avaliada quando não há ninguém vivo), e aqui
# há vivos por definição. Com 15 min, toda carga honesta de meia hora ficaria
# âmbar aos 15 — alarme falso semanal treina o operador a ignorar o alarme
# (Decisões 26/27). Quatro ciclos (60 min no default) é folgado o bastante para
# a etapa longa que está só trabalhando e curto o bastante para a órfã de 20h.
_SEM_SINAL_X_QUIESCENCIA = 4

# A corrente de cada malha: a de `aberta_em` mais recente, aberta ou fechada.
# `CROSS APPLY` (e não `OUTER`): malha sem corrida nenhuma não aparece, e é a
# ausência da chave `corrida` no payload que liga o fallback no front — a
# degradação da Decisão 41 é por AUSÊNCIA DE CAMPO, nunca por flag.
#
# As colunas derivadas viajam junto porque custariam uma consulta a mais se
# viessem sozinhas, e nenhuma delas é conta de tempo em Python (Decisão 10):
#   • `teto_vencido` — o `<` entre `teto_em` e `SYSDATETIME()` é avaliado pelo
#     BANCO. No dev o SQL Server está ~3h à frente do container da API, e um
#     `datetime.now()` daqui responderia "atrasada" a manhã inteira. **F7:
#     `AND {hold} IS NULL`** — com nó SEGURADO o teto NÃO CORRE (Decisão 30), e
#     o card não pode pintar de âmbar "fora do prazo" uma malha que está parada
#     porque o próprio operador a travou. O hold é DERIVADO aqui (`MIN(retido_em)`
#     na hora da leitura), nunca lido de um espelho: com dois Aguardes
#     segurados, soltar um limparia o espelho e o card voltaria a acusar atraso
#     com a malha ainda travada;
#   • `teto_total_min` — o denominador da barra de limite, `aberta_em → teto_em`,
#     JÁ com o crédito de hold dentro (é `teto_em` que se move). Subtrair no
#     cliente exigiria os dois carimbos e o relógio do banco na mesma conta;
#   • `retido_desde`/`retido_nos`/`retido_por` — a explicação de por que a barra
#     parou. Sem eles a tela mostraria uma barra congelada sem dizer por quê,
#     que é a mesma família de mentira que a barra que recua em silêncio;
#   • `teto_horas_malha` — `etl_malha.teto_horas`, e é o `IS NOT NULL` dele que
#     decide se a barra EXISTE (Decisão 61: o teto é anti-travamento, não SLA;
#     uma barra em 80% às 20h numa malha que sempre fecha em 3h faria escalar
#     por nada);
#   • `quiescencia_cfg` — a config que o limiar de sinal usa. `TOP 1` com a
#     chave exata; ausente/estranha volta ao default do módulo.
#
# `{hold}` é SLOT, e não texto fixo, por causa do deploy parcial: sem a 082
# (`etl_malha_no.retido_em`) a subconsulta seria "Invalid column name" e
# derrubaria o bloco `corrida` INTEIRO — card e painel calariam por causa de uma
# coluna que só serve para explicar um caso raro. Sem a 082 não há retenção
# possível, então o slot vira `NULL` e o teto volta a ser o de antes.
#
# O `tipo <> 'inicio'` é o MESMO recorte de `mc.SQL_HOLD_DA_MALHA`, e por isso
# sai da constante dele: quem trava o ciclo em voo é o Aguarde (segurado, ele
# faz `liberado()` devolver False para o dependente); o Início segura a
# PARTIDA, não o ciclo já aberto. Card e motor divergirem aqui é o card
# pintando "os relógios estão parados" numa corrida que a guardiã está
# fechando — a família de mentira que esta spec inteira existe para matar.
_HOLD_DA_CORRIDA = (
    "(SELECT MIN(n.retido_em) FROM dbo.etl_malha_no n "
    "WHERE n.malha_name = m.malha_name AND n.retido_em IS NOT NULL "
    + mc._SO_NO_QUE_TRAVA.format(a="n") + ")")
_HOLD_POR = (
    "(SELECT TOP 1 n2.retido_por FROM dbo.etl_malha_no n2 "
    "WHERE n2.malha_name = m.malha_name AND n2.retido_em IS NOT NULL "
    + mc._SO_NO_QUE_TRAVA.format(a="n2") +
    "ORDER BY n2.retido_em, n2.id)")
_HOLD_NOS = (
    "(SELECT COUNT(*) FROM dbo.etl_malha_no n3 "
    "WHERE n3.malha_name = m.malha_name AND n3.retido_em IS NOT NULL "
    + mc._SO_NO_QUE_TRAVA.format(a="n3") + ")")
_SQL_ULTIMA_CORRIDA = (
    "SELECT m.malha_name, " + mc._COLS_ME.replace("me.", "c.") + ", "
    "CASE WHEN c.teto_em IS NOT NULL AND c.teto_em < SYSDATETIME() "
    "AND {hold} IS NULL THEN 1 ELSE 0 END AS teto_vencido, "
    "DATEDIFF(MINUTE, c.aberta_em, SYSDATETIME()) AS decorrido_min, "
    "SYSDATETIME() AS apurado_em, "
    "(SELECT TOP 1 cfg.config_value FROM dbo.etl_app_config cfg "
    " WHERE cfg.config_key = '" + mc.CHAVE_QUIESCENCIA + "') AS quiescencia_cfg, "
    "DATEDIFF(MINUTE, c.aberta_em, c.teto_em) AS teto_total_min, "
    "{teto_malha} AS teto_horas_malha, "
    "{hold} AS retido_desde, {hold_nos} AS retido_nos, "
    "{hold_por} AS retido_por "
    "FROM dbo.etl_malha m "
    "CROSS APPLY (SELECT TOP 1 " + mc._COLS_ME + " "
    "             FROM dbo.etl_malha_execucao me "
    "             WHERE me.malha_name = m.malha_name {alvo}"
    "             ORDER BY me.aberta_em DESC, me.id DESC) c "
    "{filtro}ORDER BY m.malha_name")
# Sem a 082 as três perguntas do hold viram literais: "nunca retido".
_HOLD_AUSENTE = {"hold": "CAST(NULL AS DATETIME)", "hold_nos": "0",
                 "hold_por": "CAST(NULL AS NVARCHAR(64))"}
_HOLD_PRESENTE = {"hold": _HOLD_DA_CORRIDA, "hold_nos": _HOLD_NOS,
                  "hold_por": _HOLD_POR}
# Os dois recortes entram por SLOT, e não por `.replace()` no texto pronto: o
# `WHERE` da malha tem de nascer DEPOIS do `CROSS APPLY` (um replace sobre
# "FROM dbo.etl_malha m" o colocaria antes, e o SQL inválido só apareceria no
# banco), e a LENTE `?corrida={id}` tem de entrar DENTRO do APPLY — filtrar o
# id por fora traria a corrente e devolveria vazio quando a lente aponta para
# uma corrida anterior, que é justamente o caso que a lente existe para servir.
# A ordem dos parâmetros segue a ordem do TEXTO: alvo (dentro) antes de filtro
# (fora).
_FILTRO_UMA_MALHA = "WHERE m.malha_name = ? "
_ALVO_UMA_CORRIDA = "AND me.id = ? "

# O ESCOPO da linha de um membro nesta corrida — o predicado da Decisão 23,
# literal, com UMA adição que só a tela precisa:
#
#   e.data_referencia = me.data_referencia
#   AND (   e.malha_execucao_id = me.id
#        OR COALESCE(e.inicio, e.criado_em) >= me.aberta_em )
#   AND e.substituida_em IS NULL
#
# A adição é o TETO do ramo de recorte por tempo (`<= me.fechada_em`). O
# predicado do §6.4 é escrito para o FECHADOR, que só olha corrida ABERTA — lá
# `fechada_em` é NULL e a cláusula é inerte. A tela olha também corrida
# FECHADA, e sem o teto a corrida #1 de 04/08 (01:10→04:02) "enxergaria" as
# linhas da corrida #2 do MESMO dia, que começaram depois: as duas corridas do
# aceite se sobreporiam, e a #1 mudaria de número ao ser reaberta na tela.
# Proveniência (`malha_execucao_id`) continua entrando sempre — ela tem dono e
# não depende de janela.
#
# `substituida_em IS NULL` é a Decisão 55 e vale no numerador E no painel, na
# MESMA PR: sem ela, um rerun às 3h deixa o nó verde no canvas com a linha que
# o motor já aposentou enquanto a faixa conta outra coisa — a MESMA tela
# contando duas coisas diferentes. Banco sem a 078 cai no texto legado por
# `_exec_com_fallback_078`.
_ESCOPO_LINHA_078 = (
    " AND e.data_referencia = me.data_referencia"
    " AND e.substituida_em IS NULL"
    " AND (e.malha_execucao_id = me.id"
    "      OR (COALESCE(e.inicio, e.criado_em) >= me.aberta_em"
    "          AND (me.fechada_em IS NULL"
    "               OR COALESCE(e.inicio, e.criado_em) <= me.fechada_em)))")
_ESCOPO_LINHA_LEGADO = _ESCOPO_LINHA_078.replace(
    " AND e.substituida_em IS NULL", "")

# O snapshot de TODAS as corridas correntes numa consulta — o denominador que
# NÃO ENCOLHE (Decisão 52): ele é `etl_malha_execucao_membro`, congelado na
# abertura, e não a lista de membros de AGORA. Um membro marcado `PULADO` pelo
# ciclo seguinte muda de CLASSE (vira dispensado) e continua no denominador; se
# o denominador fosse `total − dispensados`, `2 de 7` viraria `2 de 4` sem nada
# ter acontecido, e o olho leria "avançou" onde três pipelines foram barrados.
#
# `sem_sinal_min` sai do BANCO em MINUTOS já subtraídos (Decisão 10) — o Python
# só escolhe o MENOR intervalo entre as linhas da corrida, o que é seleção e não
# aritmética de relógio. Com o SQL Server ~3h à frente do container da API (o
# desvio medido no dev), qualquer `datetime.now()` daqui responderia "sem sinal
# há -3h" e o alarme nunca dispararia.
_SQL_DENOMINADOR = (
    "SELECT mm.malha_execucao_id, mm.pipeline_name, "
    "CAST(mm.ativo_na_abertura AS INT), CAST(mm.conta_para_fim AS INT), "
    "e.status, COALESCE(e.inicio, e.criado_em) AS desde, "
    "CASE WHEN e.status = 'EXECUTANDO' AND EXISTS "
    "(SELECT 1 FROM dbo.etl_dependencia_evento ev "
    " WHERE ev.pipeline_name = e.pipeline_name "
    " AND ev.data_referencia = e.data_referencia "
    " AND ev.tipo = '" + mc.EVENTO_ORFA + "') THEN 1 ELSE 0 END AS orfa, "
    "DATEDIFF(MINUTE, COALESCE(e.fim, e.inicio, e.criado_em), SYSDATETIME()) "
    "AS sem_sinal_min, "
    "COALESCE(e.fim, e.inicio, e.criado_em) AS movimento_em, "
    # F9 (§9.1) — `quiescencia_ate`: quando esta corrida fecharia sozinha se
    # NADA mais se mexesse. `DATEADD` no BANCO (Decisão 10), com os minutos
    # entrando por PARÂMETRO já validados no domínio da config: somar minutos a
    # um carimbo do banco em Python devolveria um instante na régua errada (o
    # SQL Server está ~3h à frente do container da API no dev), e a tela diria
    # "por volta de 07:17" para uma corrida que fecha às 04:17.
    #
    # É o número que sustenta a Decisão 45 — dizer a REGRA antes da hora: "fecha
    # 15 min após o último movimento; se nada mais mexer, por volta de 04:17".
    # Sem ele o card, com todos os membros prontos, teria de escolher entre
    # calar (e o operador reportar bug às 04:03, com o último pipeline verde e a
    # malha ainda "em andamento") ou dizer "concluída" antes do fechamento — que
    # é exatamente a mentira que esta spec existe para matar.
    "DATEADD(MINUTE, ?, COALESCE(e.fim, e.inicio, e.criado_em)) "
    "AS quiescencia_ate, "
    "CASE WHEN EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao o "
    " WHERE o.malha_execucao_id = me.id "
    " AND o.pipeline_name = mm.pipeline_name "
    " AND o.data_referencia <> me.data_referencia{sub_o}) THEN 1 ELSE 0 END "
    "AS fora_do_odate, "
    "SYSDATETIME() AS apurado_em "
    "FROM dbo.etl_malha_execucao_membro mm "
    "JOIN dbo.etl_malha_execucao me ON me.id = mm.malha_execucao_id "
    "LEFT JOIN dbo.etl_pipeline_execucao e "
    "ON e.pipeline_name = mm.pipeline_name{escopo} "
    "WHERE mm.malha_execucao_id IN ({ids}) "
    "ORDER BY mm.malha_execucao_id, mm.pipeline_name, e.id")

# Saúde (§9.3 / Decisão 11) — DERIVADA na leitura, nunca guardada. A ordem é a
# da AÇÃO, não a do alfabeto:
#   1. COM_FALHA  — há culpado com nome; é o único que já define o que fazer;
#   2. ATRASADA   — o teto venceu (o prazo estourou, mas ninguém falhou);
#   3. SEM_PROGRESSO — há vivo e nada se mexe: o sintoma nº 1 da execução órfã;
#   4. OK.
SAUDE_OK = "OK"
SAUDE_COM_FALHA = "COM_FALHA"
SAUDE_ATRASADA = "ATRASADA"
SAUDE_SEM_PROGRESSO = "SEM_PROGRESSO"

# As classes de pendência que significam "isto JÁ deu errado" — as duas que
# pintam a corrida viva de vermelho. `nao_liberou` e `nao_partiu` são pendências
# de ORDENAÇÃO (a linha morreu sem ser liberada; a DAG nunca partiu): entram em
# `pendentes[]` com o nome e a classe, mas não transformam uma corrida em voo
# em incidente vermelho — quem decide isso é o operador olhando a aba.
_CLASSES_FALHA = ("falhou", "orfa")

# As classes que viram o CHIP VERMELHO "▲ N travados" ao lado da barra
# (Decisão 54) — e `nao_partiu` NÃO é uma delas.
#
# ⚠️ Isto é correção de um alarme falso NOTURNO, medido: a corrida abre às
# 01:10 e, nos primeiros segundos, NENHUM membro tem linha em
# `etl_pipeline_execucao`. Todos caem em `nao_partiu` (a resposta conservadora
# de `_corrida_do_card`), e com `travados = len(pendentes)` o card de TODA
# malha nasceria com `0 de 7 · ▲ 7 travados` em vermelho — todas as noites, em
# todas as malhas, sobre um ciclo perfeitamente saudável. "Alarme falso semanal
# treina o operador a ignorar o alarme" (Decisões 26/27); alarme falso DIÁRIO
# faz pior. A tabela da Decisão 54 é literal: `falhou`/`orfa`/`nao_liberou`
# ganham chip, `nao_partiu` fica só no trilho vazio — e é ele que o painel
# mostra à parte, como "1 não chegou a iniciar" (ASCII do §9.13).
#
# Quem ainda não partiu continua no denominador e continua em `pendentes[]`
# com o nome e a classe: some o VERMELHO, não a informação.
_CLASSES_TRAVADAS = ("falhou", "orfa", "nao_liberou")

# As classes em que "esperando quem?" é uma pergunta de verdade, e por isso as
# únicas que entram no lote do predicado (F10). `falhou`/`orfa` são veredito
# sobre o PRÓPRIO pipeline: ele rodou, logo os predecessores dele concluíram —
# perguntar de quem ele espera devolveria lista vazia e gastaria nome no `IN`.
_CLASSES_QUE_ESPERAM = ("nao_liberou", "nao_partiu")

# ══════ F10 — o raio de alcance por travado (§9.5, Decisão 63) ═══════════════
#
# `↳ falhou: CARGA_A` não diz se atrás dela há 1 ou 17 pipelines parados, nem se
# algum é `ALTA` — e é exatamente isso que decide acordar alguém. O número que
# falta é o RAIO: quantos membros DESTA corrida dependem, direta ou
# indiretamente, do que está travado.
#
# ── Por que no servidor, e não no canvas ────────────────────────────────────
# A Decisão 63 aposta em `cadeiaRealce` (client-side, sobre as arestas do
# desenho). Só que o desenho e a cadeia que TRAVA não são a mesma coisa: os nós
# do canvas incluem Início, Aguarde e Fim, então `qtdFrente` contaria caixas que
# não são pipeline; e a dependência que segura de verdade é a linha COMPILADA em
# `etl_pipeline_dependencia`, que pode existir sem aresta correspondente
# (dependência avulsa) — a tela diria "2 parados atrás" onde há 5. O número tem
# de sair de onde o motor lê, pelo mesmo motivo que `liberado()` é um port e não
# uma segunda opinião.
#
# ── Uma consulta, e o passeio no Python ─────────────────────────────────────
# A consulta traz o SNAPSHOT (Decisão 52 — os membros da abertura, não os de
# agora), a criticidade de cada um e as arestas de dependência entre eles. O
# fecho transitivo é feito em Python com conjunto de visitados: um CTE recursivo
# em T-SQL estouraria `MAXRECURSION` (erro 530, e a leitura inteira cairia) na
# primeira dependência circular do cadastro — e cadastro com ciclo é dado do
# usuário, não impossibilidade. Passeio de grafo não é conta de tempo: a
# Decisão 10 proíbe aritmética de relógio em Python, e isto é topologia.
#
# A aresta só conta com as DUAS pontas no snapshot: o raio é "quantos membros
# DESTA corrida estão parados atrás", e um dependente de outra malha não está
# parado por esta corrida — contá-lo inflaria o número que decide a escalação.
_SQL_GRAFO_DA_CORRIDA = (
    "SELECT mm.pipeline_name, p.criticidade, d.depende_de "
    "FROM dbo.etl_malha_execucao_membro mm "
    "LEFT JOIN dbo.etl_pipeline p ON p.pipeline_name = mm.pipeline_name "
    "LEFT JOIN dbo.etl_pipeline_dependencia d "
    "  ON d.pipeline_name = mm.pipeline_name AND d.tipo = 'PIPELINE' "
    "  AND EXISTS (SELECT 1 FROM dbo.etl_malha_execucao_membro m2 "
    "              WHERE m2.malha_execucao_id = mm.malha_execucao_id "
    "              AND m2.pipeline_name = d.depende_de "
    "              AND m2.ativo_na_abertura = 1) "
    "WHERE mm.malha_execucao_id = ? AND mm.ativo_na_abertura = 1")

_CRITICIDADE_ALTA = "alta"


def _grafo_da_corrida(cur, corrida_id: int):
    """`(filhos, criticidade)` do snapshot desta corrida, numa consulta.

    `filhos` = `{pai_casefold: {filho_casefold}}` — o sentido em que a travada
    se PROPAGA. `criticidade` = `{pipeline_casefold: texto}`.

    Chaves em `casefold` porque o SQL Server compara nome de pipeline sem
    distinguir caixa e o dict do Python distingue: sem a ponte, uma aresta
    gravada como `carga_a` não encontraria o membro `CARGA_A` e o raio sairia
    zero com o grafo inteiro carregado — o GOTCHA de grafia que já quebrou
    pipeline em produção, agora silencioso porque zero parece uma resposta.

    Falha de leitura devolve `(None, None)`: o chamador publica `alcance: null`,
    que é "não apurei" — o oposto de publicar `0` como se fosse medida."""
    try:
        cur.execute(_SQL_GRAFO_DA_CORRIDA, (int(corrida_id),))
        linhas = cur.fetchall()
    except Exception as e:  # noqa: BLE001 — leitura degrada, nunca 500
        log.warning("[MALHA] grafo da corrida #%s indisponivel (%s) — "
                    "pendentes sem raio de alcance", corrida_id, e)
        return None, None
    filhos: dict = {}
    criticidade: dict = {}
    for pipeline, critic, depende_de in linhas:
        chave = str(pipeline or "").strip().casefold()
        criticidade[chave] = (str(critic).strip() if critic else None)
        if depende_de is None:
            continue
        filhos.setdefault(str(depende_de).strip().casefold(), set()).add(chave)
    return filhos, criticidade


def _parados_atras(filhos: dict, origem: str, parados: dict) -> list:
    """Os PENDENTES alcançáveis a partir de `origem`, andando para a frente.

    `parados` = `{pipeline_casefold: pendente}` — só quem está pendente entra na
    conta, e a razão é a palavra: "4 pipelines **parados** atrás". Um dependente
    que já concluiu não está parado, e contá-lo transformaria o número que
    decide a escalação num número que só cresce com o tamanho da malha.

    Conjunto de visitados de propósito: dependência circular no cadastro é dado
    do usuário, e um passeio ingênuo giraria para sempre com o operador olhando
    um spinner às 3h."""
    vistos = {origem}
    fila = [origem]
    achados = []
    while fila:
        atual = fila.pop()
        for filho in filhos.get(atual, ()):  # noqa: SIM118 — set, não dict
            if filho in vistos:
                continue
            vistos.add(filho)
            fila.append(filho)
            pendente = parados.get(filho)
            if pendente is not None:
                achados.append(pendente)
    return achados


def _raio_dos_pendentes(cur, corrida_payload: dict) -> None:
    """Preenche `alcance`, `alcance_alta` e `criticidade` em `pendentes[]`.

    Muta o payload no lugar (o mesmo dicionário que a faixa já consome): criar
    uma segunda lista faria a tela ter duas fontes para a mesma pendência, que é
    a família de defeito que esta spec inteira existe para matar."""
    pendentes = corrida_payload.get("pendentes") or []
    filhos, criticidade = _grafo_da_corrida(cur, int(corrida_payload["id"]))
    if filhos is None:
        return                          # `alcance` fica `null` — "não apurei"
    parados = {p["pipeline"].strip().casefold(): p for p in pendentes}
    for p in pendentes:
        chave = p["pipeline"].strip().casefold()
        p["criticidade"] = criticidade.get(chave)
        atras = _parados_atras(filhos, chave, parados)
        p["alcance"] = len(atras)
        # Quantos dos parados atrás são de criticidade ALTA. É o segundo número
        # da Decisão 63, e ele é o que muda a resposta: 18 parados atrás sem
        # nenhum crítico espera o horário comercial; 2 com um `ALTA` no meio,
        # não.
        p["alcance_alta"] = sum(
            1 for q in atras
            if str(criticidade.get(q["pipeline"].strip().casefold()) or "")
            .strip().casefold() == _CRITICIDADE_ALTA)


def _quiescencia_da_linha(bruto) -> int:
    """Config de quiescência que veio junto da consulta (A) → int no domínio.

    Fora do domínio ou ausente volta ao default do módulo — a MESMA regra de
    `mc.quiescencia_minutos`, sem a consulta que ela faria."""
    valor = mc._inteiro_no_dominio(bruto, mc.QUIESCENCIA_MIN_MIN,
                                   mc.QUIESCENCIA_MIN_MAX)
    return mc.QUIESCENCIA_MIN_PADRAO if valor is None else valor


def _ultima_corrida_por_malha(cur, malha=None, corrida_id=None):
    """Consulta (A): `{malha_name: linha_da_corrida}` para TODAS as malhas.

    Devolve `(por_malha, sem_085)`. `sem_085 = True` significa "a migration 085
    não está neste banco": o chamador omite a chave `corrida` de todos os cards
    e liga `migration_085_pendente`. Qualquer outra falha de leitura degrada do
    mesmo jeito, mas com log de aviso — nunca 500 (a corrida é aditiva; sem ela
    a tela de Malha continua de pé).

    `malha` recorta para uma malha só (o painel); `corrida_id` é a LENTE
    `?corrida={id}`, e o recorte por malha vem junto de propósito — pedir a
    corrida de OUTRA malha devolve vazio em vez de vazar o ciclo do vizinho.

    F7: as três perguntas do HOLD entram por slot, conforme a 082 esteja no
    banco — sem ela, `_colunas_082` devolve False e o SQL nasce com literais.
    A alternativa (deixar a subconsulta e degradar no `except`) derrubaria o
    bloco `corrida` inteiro num banco sem a 082: card e painel calariam por
    causa de uma coluna que só serve para explicar um caso raro."""
    sql = _SQL_ULTIMA_CORRIDA.format(
        alvo=_ALVO_UMA_CORRIDA if corrida_id else "",
        filtro=_FILTRO_UMA_MALHA if malha else "",
        # `etl_malha.teto_horas` nasce na 085, mas em BLOCO SEPARADO da tabela
        # da corrida: um deploy que aplicou meia migration teria a tabela e não
        # a coluna, e o `Invalid column name` NÃO casa `_MARCAS_085` — cairia no
        # degrade genérico e o card perderia o ciclo inteiro por causa de uma
        # coluna que só decide se a barra aparece.
        teto_malha=("m.teto_horas" if _coluna_teto_horas(cur)
                    else "CAST(NULL AS INT)"),
        **(_HOLD_PRESENTE if _colunas_082(cur) else _HOLD_AUSENTE))
    params: tuple = tuple(
        p for p in (int(corrida_id) if corrida_id else None, malha)
        if p is not None)
    try:
        cur.execute(sql, params)
        linhas = cur.fetchall()
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        if mc._sem_085(e):
            log.warning("[MALHA] migration 085 ausente — o card e o painel "
                        "voltam ao 'membro mais recente' (fallback)")
            return {}, True
        log.warning("[MALHA] corrida corrente das malhas indisponivel (%s) — "
                    "cards sem o bloco 'corrida'", e)
        return {}, False
    fim = len(mc._CAMPOS) + 1
    por_malha = {}
    for r in linhas:
        c = mc._como_dict(r[1:fim])
        c["_teto_vencido"] = bool(r[fim])
        c["_decorrido_min"] = int(r[fim + 1] or 0)
        c["_apurado_em"] = r[fim + 2]
        c["_quiescencia"] = _quiescencia_da_linha(r[fim + 3])
        # F7 — os relógios. `teto_total_min` pode ser NULL (corrida aberta antes
        # da 085 ter teto, ou `teto_em` nulo): None viaja como None e a barra
        # simplesmente não existe, que é a degradação correta.
        c["_teto_total_min"] = (int(r[fim + 4])
                                if r[fim + 4] is not None else None)
        c["_teto_horas_malha"] = (int(r[fim + 5])
                                  if r[fim + 5] is not None else None)
        c["_retido_desde"] = r[fim + 6]
        c["_retido_nos"] = int(r[fim + 7] or 0)
        c["_retido_por"] = r[fim + 8]
        por_malha[str(r[0]).strip()] = c
    return por_malha, False


def _denominador_das_corridas(cur, corridas: list, quiescencia: int) -> dict:
    """Consulta (B): a classificação de cada membro do snapshot de CADA corrida.

    `{corrida_id: {membros: {...}, apurado_em, sem_sinal_min, movimento_em,
    quiescencia_ate}}`. Falha de leitura devolve `{}` — o chamador publica a
    corrida SEM os contadores (`membros_total = null`), que é a resposta honesta
    a "não consegui apurar" e o oposto de publicar zero como se fosse medida.

    `quiescencia` são os minutos JÁ validados no domínio da config (a consulta
    (A) trouxe o valor cru junto da corrida, sem gastar uma ida a mais). Ele
    entra como parâmetro do `DATEADD` — a soma acontece no banco, e o Python só
    escolhe qual linha responde pelo movimento mais recente.
    """
    if not corridas:
        return {}
    ids = [int(c["id"]) for c in corridas]
    marcadores = ",".join("?" for _ in ids)
    sql_078 = _SQL_DENOMINADOR.format(escopo=_ESCOPO_LINHA_078, ids=marcadores,
                                      sub_o=" AND o.substituida_em IS NULL")
    sql_legado = _SQL_DENOMINADOR.format(escopo=_ESCOPO_LINHA_LEGADO,
                                         ids=marcadores, sub_o="")
    # A ordem dos parâmetros segue a ordem do TEXTO: o `?` do DATEADD aparece
    # antes do `IN (…)`.
    params = (int(quiescencia),) + tuple(ids)
    try:
        deps_svc._exec_com_fallback_078(cur, sql_078, sql_legado, params)
        linhas = cur.fetchall()
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("[MALHA] snapshot das corridas %s indisponivel (%s) — "
                    "corrida publicada sem contadores", ids[:5], e)
        return {}
    out: dict = {}
    for (cid, pipeline, ativo, conta_fim, status, desde, orfa, sem_sinal,
         movimento, quiescencia_ate, fora_odate, apurado) in linhas:
        agg = out.setdefault(int(cid), {"membros": {}, "apurado_em": apurado,
                                        "sem_sinal_min": None,
                                        "movimento_em": None,
                                        "quiescencia_ate": None})
        m = agg["membros"].setdefault(pipeline, {
            "ativo": bool(ativo), "conta_para_fim": bool(conta_fim),
            "classe": None, "desde": None, "fora_do_odate": False})
        if fora_odate:
            m["fora_do_odate"] = True
        if status is None:
            continue                    # membro sem linha no escopo
        classe = mc._classe_da_linha(status, bool(orfa))
        atual = m["classe"]
        # A MESMA precedência do `estado()` do módulo gêmeo: vivo na frente de
        # tudo (nunca fechar com trabalho em voo) e `ok` na frente de `falhou`
        # (o rerun que deu certo apaga a tentativa que o operador consertou).
        if atual is None or (mc._ORDEM_CLASSE.index(classe)
                             < mc._ORDEM_CLASSE.index(atual)):
            m["classe"], m["desde"] = classe, desde
        if sem_sinal is not None:
            atual_sinal = agg["sem_sinal_min"]
            if atual_sinal is None or int(sem_sinal) < atual_sinal:
                agg["sem_sinal_min"] = int(sem_sinal)
                agg["movimento_em"] = movimento
                # O relógio de fechamento é do ÚLTIMO movimento — o mesmo que
                # responde pelo `sem_sinal_min`. Guardar o `quiescencia_ate`
                # aqui (e não num `max()` à parte) é o que garante que os dois
                # números da tela contem a mesma linha: "sem sinal há 3 min" e
                # "fecha por volta de 04:17" saem do MESMO carimbo.
                agg["quiescencia_ate"] = quiescencia_ate
    return out


def _corrida_do_card(c: dict, agg) -> dict:
    """A corrida no formato que o card e a faixa consomem — `_corrida_publica`
    (o cabeçalho do ciclo, já usado por `GET /corridas`) mais os derivados da
    leitura.

    Regras que este dicionário carrega, e que a tela não pode reinventar:

    • **o denominador é `membros_total` e ele NÃO ENCOLHE** (Decisão 52);
      `membros_dispensados` é classe SEPARADA, nunca subtração do total;
    • **`membros_travados` fica FORA do que a barra preenche** (Decisão 54): a
      barra é `ok + vivos + dispensados`, e o travado é chip ao lado. Vale a
      identidade
      `total = ok + vivos + dispensados + travados + nao_partiram`, e é ela que
      impede a barra de pintar 5/6 de vermelho e ser lida como "quase pronto"
      a 1,5 m de distância. `nao_partiram` é a quinta parcela e vem separada
      DE PROPÓSITO (ver `_CLASSES_TRAVADAS`): pintá-la de vermelho faria toda
      corrida nascer com um alarme falso nos primeiros segundos;
    • **`saude` é derivada na leitura**, nunca guardada, e só existe com a
      corrida `ABERTA` — em corrida terminal o `status` já diz tudo, e uma
      saúde `OK` embaixo de um `FALHA` seria a contradição na mesma linha;
    • **`apurado_em` é o relógio do BANCO** no instante da apuração (Decisão
      40). Ele serve ao texto ABSOLUTO do tooltip; o "atualizado há 8s" é do
      relógio LOCAL do navegador (Decisão 60), e misturar os dois com o desvio
      de 3h medido no dev produziria "atualizado há -3h".

    `agg = None` (a consulta (B) não respondeu) → contadores `null` e
    `pendentes` vazio: a tela mostra o estado do ciclo e NÃO desenha a barra.
    """
    out = _corrida_publica(c)
    out["reaberta_por"] = c["reaberta_por"]
    out["decorrido_min"] = c["_decorrido_min"]
    out["apurado_em"] = _fmt_dt(c["_apurado_em"])
    # ── F7: os relógios do prazo, sempre — inclusive com `agg is None` ───────
    # Eles não dependem da consulta (B): saem da mesma linha da corrida. Numa
    # falha de leitura do denominador a tela perde a BARRA DE PROGRESSO, mas
    # continua sabendo que o limite de segurança venceu — que é exatamente o
    # que o operador precisa quando o banco está ruim às 3h.
    out.update(_prazo_da_corrida(c))
    # F9 (§9.1) — os minutos da carência de fechamento. Vêm da consulta (A)
    # (config lida junto da corrida) e existem MESMO sem o denominador: a frase
    # da Decisão 45 diz a REGRA antes da hora, e a regra ("fecha 15 min após o
    # último movimento") continua verdadeira quando a apuração falhou.
    out["quiescencia_min"] = c["_quiescencia"]
    if agg is None:
        out.update({"saude": None, "membros_total": None, "membros_ok": None,
                    "membros_vivos": None, "membros_dispensados": None,
                    "membros_travados": None, "membros_nao_partiram": None,
                    "membros_fora_do_odate": None,
                    "membros_inativos": None, "pendentes": [],
                    "ultimo_movimento_em": None, "sem_sinal_min": None,
                    "quiescencia_ate": None,
                    # `False` e não `None`: aqui não sabemos NADA, e afirmar
                    # "sem membros" seria trocar uma ignorância por um fato.
                    "sem_membros": False})
        return out
    ok = vivos = dispensados = inativos = fora_odate = 0
    pendentes = []
    for pipeline in sorted(agg["membros"]):
        m = agg["membros"][pipeline]
        if m["fora_do_odate"]:
            fora_odate += 1
        if not m["ativo"]:
            # §6.9/#9: quem já estava inativo na abertura fica FORA do
            # denominador, mas nunca some em silêncio.
            inativos += 1
            continue
        classe = m["classe"]
        if classe is None:
            # Membro sem linha nenhuma no escopo. `nao_partiu` é a resposta
            # conservadora e deliberada: separar "não rodou hoje por regra de
            # dia" exigiria avaliar `dia_permitido` por membro (o callback que
            # a guardiã injeta em `estado()`), e isso é uma consulta de agenda
            # por membro — o N+1 que este bloco existe para não ter. O membro
            # dispensado de verdade tem linha `PULADO`, e essa a consulta vê.
            classe = "nao_partiu"
        if classe == "ok":
            ok += 1
        elif classe == "vivo":
            vivos += 1
        elif classe == "dispensado":
            dispensados += 1
        else:
            pendentes.append({"pipeline": pipeline, "classe": classe,
                              "desde": _fmt_dt(m["desde"]),
                              # Os quatro campos que só o PAINEL apura (F10).
                              # `null` aqui é "não perguntei", nunca "não há":
                              # o card serve 40 malhas com orçamento de DUAS
                              # consultas (aceite da F4), e o predicado das
                              # dependências mais o grafo do snapshot são mais
                              # duas — por malha, elas nem cabem; em lote sobre
                              # a lista inteira, seriam ~1.600 nomes num `IN`
                              # para nomear UM culpado por card, que é tudo o
                              # que o card mostra. O painel é uma malha só, tem
                              # a aba `Travando` inteira para preencher, e é lá
                              # que os quatro nascem.
                              "faltante": None, "faltantes": None,
                              "alcance": None, "alcance_alta": None,
                              "criticidade": None})
    # O card tem espaço para UM nome, e ele tem de ser o do problema mais
    # grave — não o primeiro do alfabeto. A ordem é a mesma precedência de
    # classificação do módulo gêmeo, então `pendentes[0]` é sempre o que a tela
    # deve nomear: `falhou` na frente de `orfa`, `orfa` na frente de
    # `nao_liberou`, e `nao_partiu` por último.
    pendentes.sort(key=lambda x: (mc._ORDEM_CLASSE.index(x["classe"]),
                                  x["pipeline"]))
    total = ok + vivos + dispensados + len(pendentes)
    travados = sum(1 for p in pendentes if p["classe"] in _CLASSES_TRAVADAS)
    out.update({
        "membros_total": total, "membros_ok": ok, "membros_vivos": vivos,
        "membros_dispensados": dispensados, "membros_travados": travados,
        # Os que ainda não têm linha nenhuma. Campo PRÓPRIO, e não somado ao
        # chip vermelho: "ainda não começou" às 01:10 é o estado normal de toda
        # corrida recém-aberta, e "não chegou a iniciar" às 04:00 é problema —
        # o que separa os dois é o relógio, não a classe. Enquanto o relógio
        # de partida não existe (F7), a tela mostra o número sem pintá-lo.
        "membros_nao_partiram": len(pendentes) - travados,
        "membros_fora_do_odate": fora_odate, "membros_inativos": inativos,
        "pendentes": pendentes,
        "ultimo_movimento_em": _fmt_dt(agg["movimento_em"]),
        "sem_sinal_min": agg["sem_sinal_min"],
        # Quando esta corrida fecharia sozinha se nada mais se mexesse —
        # `DATEADD` do BANCO sobre o último movimento. `None` enquanto nenhum
        # membro tiver linha: sem movimento não há de onde contar, e inventar
        # "por volta de" a partir da abertura seria promessa, não medida.
        "quiescencia_ate": _fmt_dt(agg["quiescencia_ate"]),
        # `total == 0` é um FATO, não uma falha de leitura: a corrida abriu e o
        # snapshot saiu vazio (malha sem membro ativo no instante da abertura).
        # Sem esta marca ele chegaria à tela igualzinho ao `agg is None` do lock
        # timeout — contadores em branco —, e são coisas opostas: uma pede que
        # alguém olhe o cadastro da malha, a outra que alguém tente de novo.
        "sem_membros": total == 0,
    })
    if agg.get("apurado_em") is not None:
        out["apurado_em"] = _fmt_dt(agg["apurado_em"])
    out["saude"] = _saude_da_corrida(c, out)
    return out


def _prazo_da_corrida(c: dict) -> dict:
    """Os relógios do PRAZO da corrida (F7, §6.6/§6.7 e Decisão 61).

    Sete campos, e cada um responde uma pergunta que a tela hoje não consegue
    fazer:

      • `teto_configurado` — `etl_malha.teto_horas IS NOT NULL`. É ele que decide
        se a BARRA de limite existe. O teto é **anti-travamento**, não SLA: o
        default global de 24h vale para toda malha, e desenhar uma barra em 80%
        às 20h numa malha que sempre fecha em 3h faria escalar por nada
        (Decisão 61). Configurou na malha → configurou porque quer ver;
      • `teto_horas` — o número que a malha configurou (`null` = segue o global);
      • `teto_total_min` / `teto_em` — o denominador e o fim da barra, **já com
        o crédito de hold dentro**, porque é `teto_em` que se move;
      • `teto_creditado_min` — o quanto o teto já andou por retenção. É o que
        permite à tela dizer POR QUE a barra recuou, em vez de recuar em
        silêncio (Decisão 61);
      • `teto_vencido` — avaliado pelo BANCO, e `False` enquanto houver nó
        segurado (Decisão 30);
      • `retido_desde` / `retido_nos` / `retido_por` — por que os relógios
        pararam. Nomes e instante, nunca só um cadeado.

    Tudo já veio da consulta (A): nenhuma ida a mais ao banco, nenhuma conta de
    tempo em Python. `teto_em` NÃO está aqui de propósito — ele já é campo de
    `_corrida_publica`, que a lista de corridas também usa; duplicá-lo criaria
    duas fontes para o mesmo carimbo."""
    return {
        "teto_vencido": bool(c["_teto_vencido"]),
        "teto_total_min": c.get("_teto_total_min"),
        "teto_creditado_min": int(c.get("teto_creditado_min") or 0),
        "teto_horas": c.get("_teto_horas_malha"),
        "teto_configurado": c.get("_teto_horas_malha") is not None,
        "retido_desde": _fmt_dt(c.get("_retido_desde")),
        "retido_nos": int(c.get("_retido_nos") or 0),
        "retido_por": c.get("_retido_por"),
    }


def _saude_da_corrida(c: dict, publico: dict):
    """O eixo SAÚDE (§6.1) — o que a cor do card lê quando o ciclo está aberto.

    `None` fora de `ABERTA`: o eixo CICLO já respondeu, e pendurar uma saúde
    numa corrida terminal criaria duas afirmações sobre o mesmo fato."""
    if c["status"] != mc.STATUS_ABERTA:
        return None
    if any(p["classe"] in _CLASSES_FALHA for p in publico["pendentes"]):
        return SAUDE_COM_FALHA
    if c["_teto_vencido"]:
        return SAUDE_ATRASADA
    limiar = c["_quiescencia"] * _SEM_SINAL_X_QUIESCENCIA
    sem_sinal = publico["sem_sinal_min"]
    # Sem NENHUM movimento ainda, o relógio do sinal é o da própria abertura:
    # uma corrida aberta há 3h sem uma única linha é o caso mais mudo que
    # existe, e é o que a `ABORTADA` da guardiã atende — enquanto ela não
    # passa, quem avisa é a saúde.
    if sem_sinal is None:
        sem_sinal = c["_decorrido_min"]
    elif not publico["membros_vivos"]:
        # Sem vivo, "nada se mexe" é o estado NORMAL de quem terminou: é a
        # quiescência, e quem age sobre ela é o fechador, não a cor do card.
        return SAUDE_OK
    return SAUDE_SEM_PROGRESSO if sem_sinal >= limiar else SAUDE_OK


def _bloco_corrida(cur, malha=None, corrida_id=None):
    """As duas consultas, juntas: `{malha_name: payload_da_corrida}`.

    Devolve `(publicas, sem_085, brutas)`. É o ÚNICO ponto de entrada — o card
    da lista e a faixa do painel leem o mesmo dicionário, porque o defeito que
    esta fase mata é justamente o de duas superfícies derivando o mesmo fato
    por caminhos diferentes.

    `brutas` traz as linhas com os DATETIME2 originais. Só o painel a usa, e o
    motivo é de precisão: os instantes do payload público passam por `_fmt_dt`,
    que corta a fração de segundo, e `aberta_em`/`fechada_em` são as pontas de
    um intervalo `>=`/`<=` — arredondar a borda de um recorte é como uma linha
    entra ou sai da corrida errada."""
    correntes, sem_085 = _ultima_corrida_por_malha(cur, malha, corrida_id)
    if not correntes:
        return {}, sem_085, {}
    # A quiescência é config GLOBAL (uma chave só), e a consulta (A) já a trouxe
    # validada em toda linha — pegar a da primeira é ler o mesmo valor, não
    # eleger um vencedor entre valores diferentes.
    quiescencia = next(iter(correntes.values()))["_quiescencia"]
    agregado = _denominador_das_corridas(cur, list(correntes.values()),
                                         quiescencia)
    return ({nome: _corrida_do_card(c, agregado.get(int(c["id"])))
             for nome, c in correntes.items()}, False, correntes)


# ══════ F9 — a corrida que NÃO ABRIU (§9.2, Decisão 58) ═════════════════════
#
# O PIOR MODO DE FALHA desta tela, e o único que ela ainda não sabia contar: o
# Início não disparou às 01:00 — DAG pausada, Airflow fora, agendamento quebrado
# —, e às 8h o card mostra a corrida de ONTEM, `concluída`, verde, com carimbo
# de frescor recente. Toda a camada de visibilidade pressupõe "a corrida
# existe"; quem sabe o que DEVERIA ter acontecido é o agendamento, e ele nunca
# foi comparado com o relógio.
#
# ── Por que na API, e não no front ─────────────────────────────────────────
# Comparar a hora agendada com "agora" no relógio do NAVEGADOR é a armadilha da
# Decisão 60 numa casa em que o desvio medido é de 3h. E há uma comparação que o
# navegador não pode fazer de jeito nenhum: `aberta_em` é carimbado por
# `GETDATE()` — para saber se ALGUMA corrida abriu depois do horário previsto é
# preciso pôr o previsto na RÉGUA DO BANCO antes de comparar. É o mesmo gesto do
# `desvio_banco` de `_divergencias_e_falhas` (dags/etl_dependencia_guardia.py:749),
# e pela mesma razão: o corte nasce em hora local (é o cron que o define) e a
# coluna com que ele é comparado nasce no banco.
#
# ── As quatro travas contra o alarme falso ─────────────────────────────────
# "Não abriu" pinta o card de âmbar e o joga para o topo da lista. Alarme falso
# diário treina o operador a ignorar o alarme (Decisões 26/27), então cada trava
# aqui é uma classe inteira de falso positivo:
#
#   1. **só malha que JÁ TEVE corrida.** É a trava do DIA DO DEPLOY: o
#      interruptor `malha_corrida_ativa` nasce em `0` (§11.2), NADA abre corrida,
#      e sem esta trava as 40 malhas amanheceriam âmbar com "não abriu" — a
#      lista inteira gritando sobre uma configuração, não sobre um incidente. A
#      corrida anterior é a prova de que o registro funciona para aquela malha, e
#      é ela que o próprio card exibe na linha "anterior: 03/08 · concluída";
#   2. **só malha ATIVA** — inativa não dispara nada, por definição;
#   3. **só gatilho que de fato existe hoje** — o agendamento é julgado pelo
#      mesmo desenho que `proximaExecucao.ts` julga do outro lado (dia da semana,
#      dia do mês, dias úteis, calendário): sábado de uma malha "seg a sex" não
#      é atraso, é sábado;
#   4. **folga configurável** — o Airflow não dispara no segundo do relógio, e a
#      corrida só nasce quando a primeira raiz parte. Acusar às 01:00:30 seria
#      acusar a latência normal do scheduler.
#
# Sem QUALQUER uma das quatro, o campo não sai: silêncio é melhor que uma
# acusação errada.
CHAVE_FOLGA_NAO_ABRIU = "malha_nao_abriu_folga_min"
FOLGA_NAO_ABRIU_PADRAO = 15
FOLGA_NAO_ABRIU_MIN, FOLGA_NAO_ABRIU_MAX = 1, 720

# Convenção de cron da casa (D05): 0 = domingo. `weekday()` do Python é
# 0 = segunda — a conversão fica aqui, num lugar só.
def _dow_cron(dia) -> int:
    return (dia.weekday() + 1) % 7


def _hm_texto(h, m) -> str:
    """`(hora, minuto)` → 'HH:MM'. Irmão de `_hhmm`, que converte um TIME do
    banco; aqui a entrada são dois inteiros vindos do agendamento."""
    return f"{int(h):02d}:{int(m):02d}"


def _int_ou(valor, padrao: int) -> int:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return padrao


def _hm_valido(texto):
    """'H:MM'/'HH:MM' → `(hora, minuto)` normalizado, ou `None`.

    Sem regex de propósito: este módulo não importa `re`, e a validação aqui
    precisa ser a mesma do front (que aceita `H:MM` e normaliza com zero à
    esquerda) — o par tem de casar dígito a dígito, senão as duas telas
    discordam sobre o mesmo `horarios_especificos`."""
    partes = str(texto or "").strip().split(":")
    if len(partes) != 2:
        return None
    h, m = partes[0].strip(), partes[1].strip()
    if not (h.isdigit() and m.isdigit()) or not (1 <= len(h) <= 2) or len(m) != 2:
        return None
    if int(h) > 23 or int(m) > 59:
        return None
    return int(h), int(m)


def _horarios_do_dia(ag: dict, dia) -> list:
    """Os `HH:MM` em que este agendamento dispara NAQUELE dia de calendário.

    Port da mesma regra que `proximaExecucao.ts` aplica no front (`horariosDoDia`)
    — as duas leituras do mesmo JSON precisam concordar, senão o card diz "não
    abriu" e o rodapé do diagrama diz "próxima execução: hoje 01:00" sobre o
    mesmo agendamento e o mesmo relógio.

    `hourly` devolve `[]` DE PROPÓSITO: uma malha não abre uma corrida por hora,
    e transformar cadência em instante seria inventar um horário previsto que
    ninguém prometeu. Tipo desconhecido e `on_demand` idem — o que não dá para
    afirmar não vira alarme."""
    st = str(ag.get("schedule_type") or "").strip().lower()
    hora = _hm_texto(_int_ou(ag.get("schedule_hour"), 6),
                     _int_ou(ag.get("schedule_minute"), 0))
    if st == "daily":
        return [hora]
    if st == "weekly":
        return [hora] if _dow_cron(dia) == _int_ou(ag.get("schedule_dow"), 1) else []
    if st == "monthly":
        return [hora] if dia.day == _int_ou(ag.get("schedule_dom"), 1) else []
    if st == "biweekly":
        dom = _int_ou(ag.get("schedule_dom"), 1)
        return [hora] if dia.day in (dom, dom + 15) else []
    if st == "custom":
        dias = [d.strip() for d in str(ag.get("dias_semana") or "").split(",")
                if d.strip()]
        if dias and str(_dow_cron(dia)) not in dias:
            return []
        saida = []
        for bruto in str(ag.get("horarios_especificos") or "").split(","):
            hm = _hm_valido(bruto)
            if hm:
                saida.append(_hm_texto(*hm))
        return sorted(saida)
    if st == "monthly_days_times":
        try:
            entradas = json.loads(ag.get("dias_horarios_mes") or "[]")
        except Exception:  # noqa: BLE001 — JSON estragado não vira alarme
            return []
        saida = []
        for e in entradas:
            if not isinstance(e, dict) or _int_ou(e.get("dia"), -1) != dia.day:
                continue
            for bruto in (e.get("horarios") or []):
                hm = _hm_valido(bruto)
                if hm:
                    saida.append(_hm_texto(*hm))
        return sorted(saida)
    return []


def _primeiro_previsto(agendamentos: list, agora_local: datetime):
    """O instante em que esta malha DEVERIA ter aberto a corrente — o PRIMEIRO
    horário previsto das últimas 24h, ou `None`.

    Por que o PRIMEIRO, e não o mais recente: a corrida é UMA por ciclo, e quem
    a abre é o primeiro gatilho do dia. Numa malha com raízes às 01:00 e às
    06:00, os membros das 06:00 entram na corrida que já está aberta desde as
    01:00 (mesmo ODATE) — eleger as 06:00 como "previsto" faria o card acusar
    "não abriu" às 06:15 de uma malha que abriu, rodou e está saudável desde a
    01:10. A janela de 24h basta porque a comparação seguinte é com
    `aberta_em`: se a corrida de ontem abriu no horário, ela é ≥ o previsto de
    ontem e o card se cala sozinho.

    `somente_dias_uteis` pula sábado e domingo — a MESMA regra que o motor
    julga, e a mesma que o front aplica no texto da próxima execução."""
    candidatos = []
    for dia in (agora_local.date() - timedelta(days=1), agora_local.date()):
        for ag in agendamentos:
            if not isinstance(ag, dict):
                continue
            if int(ag.get("somente_dias_uteis") or 0) and dia.weekday() >= 5:
                continue
            for hm in _horarios_do_dia(ag, dia):
                # `datetime(...)` e não `datetime.combine(dia, time(...))`:
                # `time` neste módulo é o MÓDULO time do Python (import da
                # linha 90), não `datetime.time`.
                momento = datetime(dia.year, dia.month, dia.day,
                                   int(hm[:2]), int(hm[3:5]))
                if momento <= agora_local:
                    candidatos.append(momento)
    if not candidatos:
        return None
    limite = agora_local - timedelta(hours=24)
    dentro = [m for m in candidatos if m >= limite]
    return min(dentro) if dentro else None


def _calendario_bloqueia(cur, calendario: str, dia):
    """O calendário de feriados barra este dia? `None` = não deu para saber.

    Chamada SÓ para candidato a "não abriu" (o caso raro), e por isso não entra
    no orçamento de consultas da lista. Falha de leitura devolve `None` e o
    chamador se cala: feriado é exatamente o dia em que nada roda, e acusar
    atraso no Natal é o alarme falso mais caro que esta tela poderia inventar."""
    try:
        cur.execute("SELECT TOP 1 1 FROM dbo.etl_calendario "
                    "WHERE calendario_nome = ? AND data = ?",
                    (calendario, dia))
        return cur.fetchone() is not None
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("[MALHA] calendario '%s' indisponivel (%s) — sem aviso de "
                    "corrida que nao abriu", calendario, e)
        return None


def _relogio_e_folga(cur):
    """`(agora_banco, agora_local, folga_min)` — ou `None` quando o relógio do
    banco não respondeu.

    UM statement para a lista inteira, e ele traz as duas coisas que a Decisão
    58 precisa: o relógio do BANCO (a régua de `aberta_em`) e a folga.

    Falhar aqui **cala** o campo, em vez de cair no relógio do processo como
    `_agora_do_banco` faz: lá o pior caso é um ODATE de borda; aqui seria
    publicar "atrasada há 3h" às 01:05 no dev, com o banco 3h à frente — um
    alarme inventado pelo desvio, que é justamente o defeito que a Decisão 58
    manda evitar."""
    try:
        cur.execute(
            "SELECT GETDATE(), (SELECT TOP 1 config_value "
            "FROM dbo.etl_app_config WHERE config_key = ?)",
            (CHAVE_FOLGA_NAO_ABRIU,))
        row = cur.fetchone()
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.debug("[MALHA] relogio do banco indisponivel (%s) — lista sem "
                  "'corrida que nao abriu'", e)
        return None
    if not row or row[0] is None:
        return None
    # `len(row) > 1` não é paranoia de estilo: um banco (ou um dublê) que
    # responda só o relógio não pode derrubar a lista inteira por um
    # IndexError — a folga tem default, e ele é a resposta certa aqui.
    folga = mc._inteiro_no_dominio(row[1] if len(row) > 1 else None,
                                   FOLGA_NAO_ABRIU_MIN, FOLGA_NAO_ABRIU_MAX)
    return (row[0], _agora(),
            FOLGA_NAO_ABRIU_PADRAO if folga is None else folga)


def _corrida_esperada(cur, malha: str, agendamentos: list, corrente,
                      relogio) -> dict | None:
    """A corrida que deveria existir e não existe — ou `None`.

    `corrente` é a corrida mais recente da malha (a do bloco `corrida`), e ela é
    OBRIGATÓRIA: sem histórico não há "não abriu" (trava 1). `relogio` é a tupla
    de `_relogio_e_folga`.

    "ABRIU" tem DUAS portas, e as duas precisam existir:

        previsto_banco = previsto_local + (agora_banco − agora_local)
        abriu = corrente.aberta_em >= previsto_banco          # (i) o relógio
             OR corrente.data_referencia == odate_do_previsto  # (ii) o ODATE

    (i) é a barata e responde o caso comum. O desvio some da conta do ATRASO
    (ele aparece nos dois lados) e é indispensável aqui, porque `aberta_em` é
    coluna carimbada pelo banco. Somar minutos "à mão" em cima de um dos dois
    relógios é o defeito que o dev exibe em 3h de diferença.

    (ii) é a condição LITERAL da Decisão 58 — *"não existe corrida com aquele
    `data_referencia`"* — e sem ela o card acusa malha que abriu, porque a
    corrida DESTE ciclo pode nascer ANTES do horário previsto por três caminhos
    rotineiros, nenhum deles borda:

      • **disparo manual** às 00:50, uma das três portas do §6.2 — o operador
        sabe que o insumo chegou cedo e não espera o cron das 01:00;
      • **corrida implícita**, nas 3 de 4 malhas sem nó Início: quem a abre é a
        primeira raiz a partir, e ela pode partir por push de fora;
      • **virada da malha** (§7): com `hora_virada` às 22:00, a corrida aberta
        ontem às 23:00 carimba o ODATE de HOJE — ela É a de hoje.

    Sem (ii) o card exibia, na mesma caixa e em duas linhas seguidas,
    *"nenhuma corrida de 05/08"* e *"anterior: corrida de 05/08 · em
    andamento"* — e escondia a barra de progresso da corrida que estava
    rodando, porque o estado "não abriu" tem precedência no card."""
    agora_banco, agora_local, folga = relogio
    previsto = _primeiro_previsto(agendamentos, agora_local)
    if previsto is None:
        return None
    # Trava 4: a latência normal do scheduler não é atraso.
    if agora_local - previsto < timedelta(minutes=folga):
        return None
    desvio = agora_banco - agora_local
    aberta_em = corrente.get("aberta_em")
    if aberta_em is not None and aberta_em >= previsto + desvio:
        return None                     # abriu — e no horário ou depois dele
    # Porta (ii). O ODATE é o que a corrida carimbaria se tivesse aberto NO
    # HORÁRIO PREVISTO — `previsto + desvio` põe esse horário na régua do banco,
    # a única que `odate_da_abertura` entende (Decisão 10). Não é "o ODATE de
    # agora": com virada às 06:00, previsto 01:00 e agora 08:00 caem em DIAS
    # diferentes, e o card anunciaria uma data que a corrida ausente nunca teria
    # usado.
    #
    # A consulta acontece só DEPOIS de a porta barata falhar, e é a mesma que o
    # payload abaixo já fazia: no caminho saudável (a corrida abriu depois do
    # previsto) continua sendo zero consulta a mais por malha.
    odate = mc.odate_da_abertura(cur, malha, previsto + desvio)
    if odate is not None and _fmt_dia(corrente.get("data_referencia")) == _fmt_dia(odate):
        return None                     # a corrida DESTE ciclo existe
    # Trava 3 (a parte que mora no servidor): feriado não é atraso.
    for ag in agendamentos:
        nome = (ag.get("calendario_nome") or "").strip() if isinstance(ag, dict) else ""
        if not nome:
            continue
        bloqueia = _calendario_bloqueia(cur, nome, previsto.date())
        if bloqueia is None or bloqueia:
            return None
    atraso = int((agora_local - previsto).total_seconds() // 60)
    return {
        # O ODATE que a corrida carimbaria se tivesse aberto — pela virada da
        # MALHA (Decisão 18), a mesma função das três portas. É o MESMO `odate`
        # que a porta (ii) acabou de comparar: dois cálculos dariam duas datas
        # no dia em que a virada estivesse entre o previsto e o agora, e o card
        # acusaria uma data e se calaria sobre a outra.
        "data_referencia": _fmt_dia(odate),
        "previsto_para": previsto.strftime("%H:%M"),
        "atrasada_desde": _fmt_dt(previsto),
        # Minutos, e não um instante para o front subtrair: o "há 7h" da tela
        # sai daqui somado ao relógio LOCAL desde a resposta (Decisão 60).
        "atrasada_min": atraso,
        # Há uma corrida ABERTA de OUTRO ciclo segurando a porta (o índice
        # `ux_malha_exec_aberta`, §5.3). Muda a AÇÃO — não é "o Airflow morreu",
        # é "alguém precisa fechar a de ontem" —, e por isso é campo, não texto.
        "bloqueada_por_corrida_aberta": corrente.get("status") == mc.STATUS_ABERTA,
    }


# `execucoes[]` do painel. Três textos, e o que muda entre eles é só o recorte:
#   • sem lente          — o dia inteiro (o comportamento anterior à F4);
#   • lente em corrida ABERTA  — proveniência OU "começou depois da abertura";
#   • lente em corrida FECHADA — o mesmo, com o teto `<= fechada_em`, que é o
#     que impede a corrida #1 de 04/08 de mostrar as linhas da #2 do mesmo dia.
# `substituida_em IS NULL` (Decisão 55) entra nos TRÊS; sem a 078 no banco, o
# `_exec_com_fallback_078` repete sem a cláusula.
_SQL_EXEC_PAINEL = (
    "SELECT pipeline_name, status, inicio, fim, disparado_por, motivo, "
    "execution_id FROM dbo.etl_pipeline_execucao "
    "WHERE data_referencia = ?{sub}{escopo}")
_ESCOPO_PAINEL_ABERTA = (
    " AND (malha_execucao_id = ? OR COALESCE(inicio, criado_em) >= ?)")
_ESCOPO_PAINEL_FECHADA = (
    " AND (malha_execucao_id = ? OR (COALESCE(inicio, criado_em) >= ? "
    "AND COALESCE(inicio, criado_em) <= ?))")


def _exec_linhas_do_painel(cur, data_ref, bruta) -> None:
    """Executa o SELECT de `execucoes[]` — com a lente da corrida quando há
    uma, e sempre com `substituida_em IS NULL`. O chamador faz o `fetchall`."""
    escopo, extras = "", ()
    if bruta is not None:
        if bruta["fechada_em"] is None:
            escopo = _ESCOPO_PAINEL_ABERTA
            extras = (int(bruta["id"]), bruta["aberta_em"])
        else:
            escopo = _ESCOPO_PAINEL_FECHADA
            extras = (int(bruta["id"]), bruta["aberta_em"],
                      bruta["fechada_em"])
    deps_svc._exec_com_fallback_078(
        cur,
        _SQL_EXEC_PAINEL.format(sub=" AND substituida_em IS NULL",
                                escopo=escopo),
        _SQL_EXEC_PAINEL.format(sub="", escopo=escopo),
        (data_ref,) + extras)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/malhas", tags=["malhas"])
def list_malhas(_auth: dict = Depends(get_current_user)):
    """Lista malhas com agregados por malha: qtd de pipelines, qtd de ativos, a
    criticidade mais alta entre os membros e — o que o card da tela mostra —
    total de ETAPAS, ÚLTIMA EXECUÇÃO e GATILHO. Ordenada por nome.

    Os três últimos são ADITIVOS (front antigo ignora) e degradam sozinhos:
    sem a 067 não há última execução (`null`) nem como saber quem é dependente;
    sem a coluna de agendamento da 075 o gatilho sai só dos membros. Tudo em
    consultas de CONJUNTO — nenhuma por malha.

    O `gatilho` só afirma o que VALE HOJE: agendamento da malha exige Início
    ligado a raiz assinada (senão vira `agendamento_guardado` e a precedência
    segue), e membro só conta se estiver ATIVO, com cron e sem dependência —
    inativo tem DAG pausada, dependente vira schedule=None.

    F4 (spec-malha-execucao §9.1): cada malha COM ciclo registrado ganha o bloco
    `corrida` — status do CICLO, saúde derivada, o denominador do snapshot e os
    pendentes com CLASSE. É ele que faz o card parar de dizer "sucesso" quando
    `CARGA_A` falhou e `CARGA_B` terminou depois. Duas consultas para a lista
    inteira, nunca uma por malha. Malha SEM corrida (ou banco sem a 085) não
    ganha a chave: a degradação é por AUSÊNCIA DE CAMPO (Decisão 41), e
    `ultima_execucao` continua no payload como o fallback "(membro mais
    recente)".

    F9 (Decisão 58): malha ATIVA, com corrida anterior registrada e com gatilho
    cujo horário do dia já venceu **sem** nenhuma corrida ter aberto ganha
    `corrida_esperada` — o estado "não abriu", que é o único jeito de a tela
    contar o pior modo de falha (o Início que não disparou) em vez de exibir a
    corrida de ontem, verde, com carimbo de frescor recente."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        if not _tabelas_070(cur):
            cur.close(); conn.close()
            log.warning("[MALHA] tabelas da migration 070 ausentes — lista degradada para vazio")
            # migration_pendente é CONTRATO com o front: é ela que liga o banner
            # de deploy parcial e desabilita o "Nova malha" na tela.
            return {"malhas": [], "migration_pendente": True}

        # orientacao (074) é ADITIVA na lista: o card pode ignorar; a coluna
        # ausente degrada para o default sem mudar o SQL de hoje. Idem
        # agendamento_json (075): sem a coluna, o gatilho cai nos membros.
        tem_074 = _coluna_074(cur)
        tem_agenda = _colunas_agenda(cur)
        cur.execute(
            "SELECT malha_name, descricao, CAST(ativo AS INT) AS ativo, "
            "criado_em, criado_por, atualizado_em"
            + (", orientacao" if tem_074 else "")
            + (", agendamento_json" if tem_agenda else "") +
            " FROM dbo.etl_malha ORDER BY malha_name"
        )
        data = []
        indice: dict[str, dict] = {}
        ag_malha: dict[str, dict] = {}
        for r in cur.fetchall():
            rec = {
                "malha_name": r[0], "descricao": r[1], "ativo": int(r[2] or 0),
                "criado_em": _fmt_dt(r[3]), "criado_por": r[4],
                "atualizado_em": _fmt_dt(r[5]),
                "orientacao": _orientacao_norm(r[6]) if tem_074 else "horizontal",
                "qtd_pipelines": 0, "qtd_ativos": 0, "qtd_etapas": 0,
                "criticidade": None, "ultima_execucao": None,
                "gatilho": _gatilho_sob_demanda(),
                # Existe agendamento salvo que NÃO está vigente (sem Início
                # ligado a nenhuma raiz)? O `gatilho` não pode anunciá-lo, mas
                # o front tem direito de dizer que ele está guardado — some
                # sozinho quando o Início for (re)ligado.
                "agendamento_guardado": False,
            }
            data.append(rec)
            indice[rec["malha_name"]] = rec
            if tem_agenda:
                ag = _no_config(r[7 if tem_074 else 6])
                if ag:
                    ag_malha[rec["malha_name"]] = ag

        # Membros num SELECT só (agregação em Python): evita N+1 e mantém a
        # regra da criticidade num único lugar testável. As etapas entram como
        # COUNT correlacionado (PK de etl_pipeline_job é pipeline_name+job_name
        # — a contagem é um seek) e as colunas de cron alimentam o gatilho
        # derivado dos membros, sem uma segunda ida ao banco.
        cur.execute(
            "SELECT mp.malha_name, CAST(p.active AS INT) AS active, "
            "ISNULL(p.criticidade, 'Media') AS criticidade, "
            "(SELECT COUNT(*) FROM dbo.etl_pipeline_job j "
            " WHERE j.pipeline_name = mp.pipeline_name) AS qtd_etapas, "
            "p.pipeline_name, p.schedule_type, "
            "CAST(p.schedule_hour AS INT), CAST(p.schedule_minute AS INT), "
            "CAST(p.schedule_dow AS INT), CAST(p.schedule_dom AS INT), "
            "p.horarios_especificos, p.dias_semana, p.dias_horarios_mes, "
            "CAST(p.somente_dias_uteis AS INT), p.calendario_nome, "
            "CONVERT(VARCHAR(5), p.hora_virada, 108) "
            "FROM dbo.etl_malha_pipeline mp "
            "JOIN dbo.etl_pipeline p ON p.pipeline_name = mp.pipeline_name"
        )
        membros_linhas = cur.fetchall()

        # Quem é DEPENDENTE não conta como gatilho: o gerador troca o cron dele
        # por schedule=None. Sem a 067 ninguém é dependente (a tabela não
        # existe) e o schedule_type sozinho decide — o comportamento pré-F1.
        dependentes: set = set()
        if _tabela_067(cur):
            dependentes = _pipelines_com_dependencia(cur)
        else:
            log.warning("[MALHA] migration 067 ausente — gatilho da lista sem "
                        "o filtro de dependentes")

        crits: dict[str, list] = {}
        cron: dict[str, list] = {}
        for row in membros_linhas:
            malha, active, crit, qtd_etapas, pipeline, st = row[0], row[1], row[2], row[3], row[4], row[5]
            rec = indice.get(malha)
            if rec is None:
                continue
            rec["qtd_pipelines"] += 1
            rec["qtd_ativos"] += int(active or 0)
            rec["qtd_etapas"] += int(qtd_etapas or 0)
            crits.setdefault(malha, []).append(crit)
            # Pipeline INATIVO não dispara: a tela de pipelines PAUSA a DAG no
            # Airflow ao inativar e a SP de geração filtra active=1. O cron
            # continua gravado na linha, mas está morto — contá-lo faria o
            # card anunciar um horário que ninguém honra.
            if not int(active or 0):
                continue
            tipo = (str(st).strip().lower() if st else "")
            if not tipo or tipo == "on_demand":
                continue
            if str(pipeline or "").strip().casefold() in dependentes:
                continue
            cron.setdefault(malha, []).append({
                "pipeline": pipeline,
                "agendamento": dict(zip(_CAMPOS_CRON_MEMBRO,
                                        (tipo,) + tuple(row[6:16]))),
            })
        for malha, lista in crits.items():
            indice[malha]["criticidade"] = criticidade_agregada(lista)

        # Agendamento da malha só vale se estiver VIGENTE (Início ligado a pelo
        # menos uma raiz assinada). Sem as tabelas da 075 não há nó nenhum:
        # nenhum agendamento é vigente e o gatilho cai nos membros.
        vigentes: set = set()
        if ag_malha and _tabelas_075(cur):
            vigentes = _malhas_com_agenda_vigente(cur)
        for malha, rec in indice.items():
            # Agendamento PRÓPRIO da malha (F13) manda — quando ele de fato
            # está plantado nas raízes. Guardado-porém-inerte não é gatilho:
            # vira só a flag, e a precedência segue para os membros.
            if malha in ag_malha and malha in vigentes:
                rec["gatilho"] = _gatilho_da_malha(ag_malha[malha])
                continue
            if malha in ag_malha:
                rec["agendamento_guardado"] = True
            if malha in cron:
                rec["gatilho"] = _gatilho_dos_membros(cron[malha])

        # F4 — a CORRIDA: duas consultas para a lista inteira (ver o bloco de
        # comentário de `_bloco_corrida`). Vem ANTES da última execução porque
        # é ela quem responde o status da malha; a última execução fica como
        # fallback declarado para quem não tem corrida.
        corridas, sem_085, brutas = _bloco_corrida(cur)
        if sem_085:
            # Decisão 41: a degradação é POR MALHA (a chave `corrida` some), e
            # a flag é só o texto explicativo do tooltip — jamais o que o front
            # testa para decidir renderizar.
            resposta_flag_085 = True
        else:
            resposta_flag_085 = False
        for malha, payload in corridas.items():
            rec = indice.get(malha)
            if rec is not None:
                rec["corrida"] = payload

        # F9 (Decisão 58) — a corrida que NÃO ABRIU. Só chega aqui malha ATIVA
        # que JÁ TEVE corrida (a trava do dia do deploy: com o interruptor em
        # `0` ninguém tem, e a lista inteira se cala) e que tem agendamento
        # legível. Sem candidato nenhum, ZERO consulta a mais — o relógio do
        # banco só é lido quando há o que comparar com ele.
        candidatos = [m for m, rec in indice.items()
                      if rec.get("corrida") and int(rec["ativo"] or 0)
                      and ((m in ag_malha and m in vigentes) or m in cron)]
        try:
            relogio = _relogio_e_folga(cur) if candidatos else None
            if relogio:
                for malha in candidatos:
                    rec = indice[malha]
                    # O agendamento julgado é o MESMO que virou `gatilho` na
                    # tela: o da malha quando ele está vigente, senão o dos
                    # membros que disparam sozinhos. Julgar outro faria o card
                    # acusar o atraso de um horário que ele não mostra.
                    ags = ([ag_malha[malha]]
                           if rec["gatilho"]["origem"] == "malha"
                           else [m["agendamento"] for m in cron.get(malha, [])])
                    esperada = _corrida_esperada(cur, malha, ags,
                                                 brutas.get(malha) or {},
                                                 relogio)
                    if esperada:
                        rec["corrida_esperada"] = esperada
        except Exception as e:  # noqa: BLE001 — aditivo NUNCA derruba a lista
            # A lista de malhas é a tela de entrada: um agendamento estranho no
            # banco não pode transformá-la em 500. Sem o campo, o card volta a
            # mostrar a corrida anterior — que é o comportamento de antes desta
            # fase, não um terceiro comportamento inventado.
            log.warning("[MALHA] aviso de corrida que nao abriu indisponivel "
                        "(%s) — lista sem 'corrida_esperada'", e)

        # Última execução: UMA consulta (top-1 por pipeline membro) e a
        # composição por malha aqui, sobre as linhas de membros já lidas —
        # o mesmo padrão de agregação-em-Python da criticidade.
        #
        # ⚠️ Ela CONTINUA no caminho corrente mesmo quando toda malha tem
        # corrida, e a §9.1 diz "sai do caminho". A divergência é deliberada e
        # o motivo é de deploy: o `deploy.sh` publica o `dist/` na etapa 3 e a
        # `api/` só na 7 — mas um rollback do FRONT sem rollback da API deixaria
        # o card anterior a esta fase sem nada para mostrar. O custo é uma
        # consulta de CONJUNTO que já existia (nunca um N+1), e o ganho é a
        # linha "(membro mais recente)" da Decisão 41 continuar tendo dado.
        if _tabelas_067_execucao(cur):
            por_pipeline = _ultima_execucao_por_pipeline(cur)
            melhor: dict[str, tuple] = {}
            for row in membros_linhas:
                malha = row[0]
                if indice.get(malha) is None:
                    continue
                u = por_pipeline.get(str(row[4] or "").strip().casefold())
                if u is None:
                    continue
                # Desempate por nome do pipeline: duas corridas no mesmo
                # instante não podem alternar entre refreshes da tela.
                atual = melhor.get(malha)
                if atual is None or (u[0], u[2].casefold()) > (atual[0],
                                                               atual[2].casefold()):
                    melhor[malha] = u
            for malha, (momento, status, pipeline) in melhor.items():
                indice[malha]["ultima_execucao"] = {
                    "em": _fmt_dt(momento), "status": status,
                    "pipeline": pipeline}
        else:
            log.warning("[MALHA] tabelas de execução da 067 ausentes — lista "
                        "sem 'última execução'")

        cur.close(); conn.close()
        # F9 — o MARCADOR DE VERSÃO da resposta, e ele existe por causa de uma
        # janela de deploy real: o `deploy.sh` publica o `dist/` na etapa 3,
        # automático e sem pergunta, e só reconstrói a `api/` na etapa 7. Nesse
        # intervalo o front novo conversa com a API velha, que não manda
        # `corrida` **nem** `migration_085_pendente` — e, sem um marcador
        # positivo, o front não teria como distinguir "esta malha não tem ciclo"
        # (silêncio correto, o estado do dia do deploy) de "esta API não sabe
        # responder sobre ciclo" (a hora de DIZER que falta informação).
        #
        # `True` fixo de propósito: quem responde isto é a VERSÃO do código, não
        # o estado do banco. Se o front não vir a chave, é porque está falando
        # com uma API anterior a esta fase.
        saida = {"malhas": data, "corrida_suportada": True}
        if resposta_flag_085:
            saida["migration_085_pendente"] = True
        return saida
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.post("/malhas", tags=["malhas"])
def create_malha(body: dict = Body(default={}),
                 _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria uma malha. 422 para nome vazio ou duplicado (a colação do banco é
    case-insensitive — 'Fechamento' e 'FECHAMENTO' são a mesma malha)."""
    nome = (body.get("malha_name") or "").strip()
    descricao = (body.get("descricao") or "").strip() or None
    if not nome:
        raise HTTPException(status_code=422, detail="malha_name é obrigatório")
    if len(nome) > 200:
        raise HTTPException(status_code=422, detail="malha_name excede 200 caracteres")
    # '/' e '\' no nome tornariam a malha inendereçável nos endpoints de path
    # (o ASGI decodifica %2F antes do match de rota e o 404 vem do roteador).
    if "/" in nome or "\\" in nome:
        raise HTTPException(status_code=422,
                            detail="malha_name não pode conter '/' nem '\\'")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        existente = _malha_oficial(cur, nome)
        if existente is not None:
            cur.close(); conn.close()
            raise HTTPException(status_code=422,
                                detail=f"Já existe uma malha com este nome: '{existente}'")
        criado_por = None
        if isinstance(_auth, dict):
            criado_por = (str(_auth.get("matricula") or "").strip() or None)
        cur.execute(
            "INSERT INTO dbo.etl_malha (malha_name, descricao, criado_por) VALUES (?, ?, ?)",
            (nome, descricao, (criado_por or "")[:100] or None),
        )
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "malha_name": nome}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.get("/malhas/{malha_name}", tags=["malhas"])
def get_malha_detalhe(malha_name: str, _auth: dict = Depends(get_current_user)):
    """Detalhe da malha + membros (nome, ativo, criticidade, agendamento e a
    posição salva do nó no diagrama da F8)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        # orientacao (074): preferência de visão que viaja com o layout — sem a
        # coluna, degrada para 'horizontal' (o comportamento de sempre).
        tem_074 = _coluna_074(cur)
        # F2 (081): a virada da MALHA e a marca de equalização — aditivas, no
        # mesmo esquema condicional da orientacao.
        tem_081 = _colunas_081(cur)
        # F7 (085): o limite de segurança POR MALHA. Aditivo pelo mesmo esquema
        # das anteriores — sem a 085 a chave simplesmente não vem, e a tela não
        # oferece um campo que o banco não sabe guardar.
        tem_teto = _coluna_teto_horas(cur)
        cur.execute(
            "SELECT malha_name, descricao, CAST(ativo AS INT) AS ativo, "
            "criado_em, criado_por, atualizado_em"
            + (", orientacao" if tem_074 else "")
            + (", hora_virada, CAST(equalizar_data AS INT)" if tem_081 else "")
            + (", teto_horas" if tem_teto else "") +
            " FROM dbo.etl_malha WHERE malha_name = ?",
            (malha_name,),
        )
        row = cur.fetchone()
        if row is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        malha = {
            "malha_name": row[0], "descricao": row[1], "ativo": int(row[2] or 0),
            "criado_em": _fmt_dt(row[3]), "criado_por": row[4],
            "atualizado_em": _fmt_dt(row[5]),
            "orientacao": _orientacao_norm(row[6]) if tem_074 else "horizontal",
        }
        _i081 = 7 if tem_074 else 6
        row_virada = row[_i081] if tem_081 else None
        equalizar = row[_i081 + 1] if tem_081 else 0
        if tem_teto:
            # `None` é RESPOSTA, não ausência: significa "esta malha segue o
            # limite global". A chave só some quando a COLUNA não existe — e aí
            # a tela não oferece o campo, em vez de oferecer um que não grava.
            _i085 = _i081 + (2 if tem_081 else 0)
            malha["teto_horas"] = (int(row[_i085])
                                   if row[_i085] is not None else None)
        # F10/F13: as tabelas da 075 habilitam nós e assinaturas — checadas UMA
        # vez por request; as colunas de agendamento (F13) têm guard próprio,
        # porque a 075 pode estar aplicada pela metade num deploy parcial.
        tem_075 = _tabelas_075(cur)
        tem_agenda = tem_075 and _colunas_agenda(cur)
        # JOIN em etl_pipeline: além dos metadados, garante que membro de
        # pipeline excluído simplesmente some (aceite da F7) — e a FK CASCADE
        # da 070 já removeu a linha de qualquer forma. agenda_no (F13) é
        # ADITIVO: entra no SELECT só com as colunas da 075 presentes.
        # dag_criada + o carimbo da 073 entram no membro para a tela responder
        # "esta malha está publicada?" — é o insumo do botão de republicação
        # (o contador de pendentes) e do badge por nó. Sem a 073, a chave
        # `publicacao_pendente` simplesmente não vem: a UI não inventa um
        # "está em dia" que o banco não sustenta.
        tem_073 = _coluna_073(cur)
        # hora_virada nasce na 067 (que a malha NÃO exige para abrir) — guard
        # próprio, como as demais colunas aditivas deste SELECT.
        tem_virada_pipe = _coluna_hora_virada(cur)
        cur.execute(
            "SELECT p.pipeline_name, CAST(p.active AS INT) AS active, "
            "ISNULL(p.criticidade, 'Media') AS criticidade, p.schedule_type, "
            "mp.layout_x, mp.layout_y, CAST(ISNULL(p.dag_criada, 0) AS INT)"
            + (", p.agenda_no" if tem_agenda else "")
            + (", p.dag_config_pendente_em" if tem_073 else "")
            + (", p.hora_virada" if tem_virada_pipe else "") +
            " FROM dbo.etl_malha_pipeline mp "
            "JOIN dbo.etl_pipeline p ON p.pipeline_name = mp.pipeline_name "
            "WHERE mp.malha_name = ? ORDER BY p.pipeline_name",
            (malha["malha_name"],),
        )
        membros = []
        for r in cur.fetchall():
            m = {
                "pipeline_name": r[0], "active": int(r[1] or 0),
                "criticidade": r[2], "schedule_type": r[3],
                "layout_x": r[4], "layout_y": r[5],
                "dag_criada": int(r[6] or 0),
            }
            i = 7
            if tem_agenda:
                m["agenda_no"] = int(r[i]) if r[i] is not None else None
                i += 1
            if tem_073:
                m["publicacao_pendente"] = r[i] is not None
                i += 1
            if tem_virada_pipe:
                m["hora_virada"] = _hhmm(r[i])
            membros.append(m)
        # Quantos predecessores cada membro tem na 067 (F1 da
        # spec-malha-data-unica). É o que permite à tela apontar o pipeline que
        # TEM dependência mas ainda dispara por AGENDA: a DAG dele não foi
        # republicada, então roda fora da malha, calcula a própria data de
        # referência e mistura a corrida. Foi essa a causa do incidente da
        # Carga_Vida. Sem a 067 a chave não vem e a tela não afirma nada.
        if _tabela_067(cur) and membros:
            cur.execute(
                "SELECT pipeline_name, COUNT(*) FROM dbo.etl_pipeline_dependencia "
                "WHERE tipo = 'PIPELINE' GROUP BY pipeline_name")
            por_nome = {str(r[0] or "").strip().casefold(): int(r[1] or 0)
                        for r in cur.fetchall()}
            for m in membros:
                m["qtd_predecessores"] = por_nome.get(
                    m["pipeline_name"].casefold(), 0)
        # F2: a virada da MALHA (migration 081) e quem está fora dela. É a
        # virada que decide o ODATE de quem roda por agenda — membros em
        # viradas diferentes carimbam datas diferentes para a MESMA corrida.
        if tem_081:
            malha["hora_virada"] = _hhmm(row_virada)
            malha["equalizar_data"] = int(equalizar or 0)
            if tem_virada_pipe:
                alvo = malha["hora_virada"]     # None = a global manda
                malha["virada_divergente"] = sorted(
                    m["pipeline_name"] for m in membros
                    if (m.get("hora_virada") or None) != alvo)
        # Arestas (F8): dependências GLOBAIS da 067 em que AMBAS as pontas são
        # membros desta malha — a mesma dependência aparece em toda malha que
        # contenha os dois pipelines (aceite da F8: a aresta é real nas duas).
        # Filtro em Python sobre um SELECT só, como nos agregados da listagem.
        # Deploy parcial (067 pendente): a malha ainda abre, com "arestas": [] —
        # migration_067_pendente é o sinal para o front avisar e travar a edição.
        tem_067 = _tabela_067(cur)
        arestas = []
        if tem_067:
            # Mapa casefold → grafia OFICIAL (a dos nós do diagrama). Linhas
            # legadas da 067 podem carregar grafia divergente (o register da F1
            # gravava como digitado e a 069 não normalizou esta tabela — a 071
            # normaliza); sem canonizar aqui, o React Flow descarta a aresta em
            # silêncio (id não casa com nó) e ela some do desenho.
            membro_oficial = {m["pipeline_name"].casefold(): m["pipeline_name"]
                              for m in membros}
            if tem_075 and _coluna_origem_no(cur):
                # Com a assinatura da 075 (§7.4 do desenho de componentes):
                # linha assinada por nó DESTA malha não vira aresta direta (ela
                # é o desenho do nó); assinada por nó de OUTRA malha vira
                # aresta anotada compilada_por — o editor a desenha com
                # cadeado, somente-leitura (F12). Na F10 nada assina linhas
                # (a compilação é a F11): o contrato de leitura nasce pronto.
                cur.execute(
                    "SELECT d.pipeline_name, d.depende_de, d.origem_no, n.malha_name "
                    "FROM dbo.etl_pipeline_dependencia d "
                    "LEFT JOIN dbo.etl_malha_no n ON n.id = d.origem_no "
                    "WHERE d.tipo = 'PIPELINE'")
                linhas_067 = [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]
            else:
                cur.execute(
                    "SELECT pipeline_name, depende_de FROM dbo.etl_pipeline_dependencia "
                    "WHERE tipo = 'PIPELINE'")
                linhas_067 = [(r[0], r[1], None, None) for r in cur.fetchall()]
            for dep_pipe, dep_de, origem_no, malha_do_no in linhas_067:
                a = membro_oficial.get(str(dep_pipe or "").strip().casefold())
                b = membro_oficial.get(str(dep_de or "").strip().casefold())
                if not (a and b):
                    continue
                if origem_no is not None and malha_do_no is not None and \
                        str(malha_do_no).strip().casefold() == \
                        malha["malha_name"].casefold():
                    continue    # desenho do nó desta malha, não aresta direta
                item = {"pipeline_name": a, "depende_de": b}
                if origem_no is not None:
                    item["compilada_por"] = {"malha": malha_do_no,
                                             "no": int(origem_no)}
                arestas.append(item)
            arestas.sort(key=lambda x: (x["pipeline_name"], x["depende_de"]))
        else:
            log.warning("[MALHA] migration 067 ausente — malha '%s' aberta sem arestas",
                        malha["malha_name"])
            malha["migration_067_pendente"] = True

        # Nós do desenho (F10) — com o upstream calculado pelo SERVIDOR (port
        # da expansão com paridade): o front nunca expande. Sem a 075, o resto
        # da malha segue intacto e a flag liga o aviso de deploy parcial.
        nos_payload, arestas_no_payload, avisos = [], [], []
        if tem_075:
            nos_l = _nos_da_malha(cur, malha["malha_name"])
            arestas_l = _arestas_da_malha(cur, malha["malha_name"])
            expansao = malha_nos_svc.expandir(nos_l, arestas_l)
            nos_payload = [{
                "id": n["id"], "tipo": n["tipo"],
                "config": _no_config(n["config_json"]),
                "layout_x": n["layout_x"], "layout_y": n["layout_y"],
                "upstream": sorted(expansao["nos"][n["id"]]["upstream"]),
                # 082 (aditivo): o Aguarde SEGURADO não solta ninguém — a
                # tela mostra o estado e quem segurou.
                **({"retido_em": n["retido_em"], "retido_por": n["retido_por"]}
                   if "retido_em" in n else {}),
            } for n in nos_l]
            arestas_no_payload = arestas_l
            avisos = _avisos_desenho(nos_l, arestas_l)
            # F13: o agendamento da MALHA (Decisão 8) + os avisos de agenda —
            # Início ligado sem agendamento configurado (aviso forte enquanto
            # durar) e o badge de contradição da raiz assinada que ganhou
            # dependência por outra porta (§2.2, última linha).
            if tem_agenda:
                agendamento = _agendamento_da_malha(cur, malha["malha_name"])
                malha["agendamento"] = agendamento
                malha["agendamento_resumo"] = (
                    _resumo_agendamento(agendamento) if agendamento else None)
                inicio = next((n for n in nos_l if n["tipo"] == "inicio"), None)
                if inicio is not None:
                    tem_saida_inicio = any(a["origem_no"] == inicio["id"]
                                           for a in arestas_l)
                    if agendamento is None and tem_saida_inicio:
                        avisos.append({
                            "no": inicio["id"], "nivel": "forte", "mensagem":
                            "o Início está ligado a raízes, mas a malha ainda "
                            "não tem agendamento — configure no painel do "
                            "Início"})
                    if tem_067:
                        for m in membros:
                            if m.get("agenda_no") != inicio["id"]:
                                continue
                            if _raiz_tem_dependencia(cur, m["pipeline_name"]):
                                m["agenda_contradicao"] = True
                                # `tipo` (F15): chave ESTÁVEL para o front
                                # filtrar este aviso na visão de Execução (é
                                # onde mora o disparo manual, que atropela a
                                # dependência) sem casar texto — a mensagem
                                # continua tendo uma fonte só, aqui.
                                avisos.append({
                                    "no": inicio["id"], "nivel": "forte",
                                    "tipo": "contradicao",
                                    "mensagem": _msg_contradicao(
                                        m["pipeline_name"])})
        else:
            log.warning("[MALHA] migration 075 ausente — malha '%s' aberta sem nós",
                        malha["malha_name"])
            malha["migration_075_pendente"] = True
        cur.close(); conn.close()
        malha["membros"] = membros
        malha["arestas"] = arestas
        malha["nos"] = nos_payload
        malha["arestas_no"] = arestas_no_payload
        malha["avisos"] = avisos
        malha["qtd_pipelines"] = len(membros)
        malha["qtd_ativos"] = sum(m["active"] for m in membros)
        malha["criticidade"] = criticidade_agregada(m["criticidade"] for m in membros)
        return malha
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.get("/malhas/{malha_name}/execucao", tags=["malhas"])
def get_malha_execucao(malha_name: str, data_referencia: str | None = None,
                       corrida: int | None = None,
                       _auth: dict = Depends(get_current_user)):
    """Visão de execução da malha numa data de referência (F9, spec §4b) — ou,
    a partir da F4, na LENTE de uma CORRIDA (`?corrida={id}`).

    Devolve, APENAS para pipelines MEMBROS da malha, a execução MAIS RECENTE de
    cada um na data (regra do §6 risco 6: pipeline com horários específicos
    roda N vezes ao dia — vale a última) e os eventos da guardiã
    (etl_dependencia_evento) da mesma data, do mais novo para o mais antigo.

    Sem `data_referencia` na query, usa o ODATE corrente calculado com a hora
    de virada GLOBAL de etl_app_config — mesma semântica de
    dags/utils/data_referencia.py (port com teste de paridade).

    ── A lente `?corrida={id}` (F4, §9.6) ──────────────────────────────────
    A data sozinha NÃO distingue duas corridas do mesmo ODATE: redisparar às
    05h depois de um incidente é gesto legítimo e diário, e `?data_referencia`
    devolveria as duas madrugadas embaralhadas numa lista só, com a segunda
    sobrepondo a primeira em cada pipeline. Com a lente:

    • o ODATE vem da PRÓPRIA corrida (o parâmetro `data_referencia` passa a ser
      redundante e é ignorado — a corrida é a identidade, a data é o atalho);
    • `execucoes[]` é recortado pelo escopo do §6.4 (proveniência OU janela
      `[aberta_em, fechada_em]`), com `substituida_em IS NULL`;
    • corrida de OUTRA malha, ou id inexistente, responde **404** — nunca a
      corrida corrente disfarçada, que faria o ◀ ▶ "funcionar" mostrando o
      ciclo errado.

    Sem `corrida` e sem `data_referencia` — a pergunta "o que está acontecendo
    AGORA" — a corrente da malha vira a lente e o ODATE da RESPOSTA passa a ser
    o dela. É aqui que some a divergência confessada em `:2377-2384`: a data
    que o painel mostra deixa de ser calculada com a virada GLOBAL e passa a
    ser a que o ciclo carimbou, que é a mesma que o disparo usou.

    Com `?data_referencia=D` explícito (a navegação por dia), nada disso vale:
    o recorte é o dia inteiro, como antes da F4, e o bloco `corrida` só vem se
    a corrida corrente for daquele dia — uma faixa falando de 05/08 sobre uma
    lista de 03/08 seria o card mentindo com layout novo.

    ⚠️ `substituida_em IS NULL` entra no `SELECT` de `execucoes[]` **sempre**
    (Decisão 55), com ou sem lente: sem ela, depois de um rerun às 3h o nó do
    canvas fica verde com a linha que o motor já aposentou enquanto a faixa
    conta outro número — a mesma tela contando duas coisas diferentes. Banco
    sem a coluna (078 pendente) cai no texto legado.

    Produção PRÉ-retomada (F2–F4): as tabelas da 067 existem mas NADA as
    alimenta — a resposta é o estado vazio HONESTO (arrays vazios), nunca tela
    quebrada nem promessa falsa. Deploy parcial SEM a 067: arrays vazios +
    migration_067_pendente, e a malha continua abrindo. Sem a 085 o bloco
    `corrida` simplesmente NÃO VEM (Decisão 41) e o painel volta ao banner de
    hoje.
    """
    # Valida a data ANTES de abrir conexão: 422 de formato não gasta banco.
    data_ref = None
    if data_referencia is not None and str(data_referencia).strip() != "":
        try:
            data_ref = datetime.strptime(str(data_referencia).strip(), "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"data_referencia inválida: '{data_referencia}' "
                       "(use o formato YYYY-MM-DD)")
    if corrida is not None and int(corrida) <= 0:
        raise HTTPException(status_code=422,
                            detail=f"corrida inválida: '{corrida}' "
                                   "(o id é um inteiro positivo)")
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")

        # F4 — a corrida (a da lente, ou a corrente). As DUAS consultas do
        # bloco, para uma malha só. Vem antes do resto porque é ela quem decide
        # o ODATE quando a lente está em uso.
        corridas, sem_085, brutas = _bloco_corrida(cur, malha, corrida)
        corrida_payload = corridas.get(malha)
        corrida_bruta = brutas.get(malha)
        if corrida is not None and corrida_payload is None:
            cur.close(); conn.close()
            raise HTTPException(
                status_code=404,
                detail=f"Não encontrei essa corrida na malha "
                       f"'{malha}'." + (" A migration 085 ainda não foi "
                                        "aplicada neste banco." if sem_085
                                        else ""))
        # A LENTE — e ela nunca é adivinhada. Só existe em dois casos:
        #   1. `?corrida={id}` explícito: a corrida é a identidade e o ODATE
        #      sai dela (pedir `&data_referencia=X` divergente devolveria uma
        #      faixa falando de um dia sobre a lista de outro);
        #   2. sem NENHUM parâmetro — "o que está acontecendo agora": a
        #      corrente vira a lente e o ODATE da resposta é o que o ciclo
        #      carimbou, não o que a virada global calcularia.
        # Com `?data_referencia` explícito não há lente: navegar por dia é
        # navegar por dia, e recortar pela corrida corrente devolveria a
        # madrugada de hoje sob o rótulo do dia pedido.
        lente = None
        if corrida is not None:
            lente = corrida_bruta
            data_ref = corrida_bruta["data_referencia"]
        elif data_ref is None and corrida_bruta is not None:
            lente = corrida_bruta
            data_ref = corrida_bruta["data_referencia"]
        if data_ref is None:
            # ODATE corrente: virada GLOBAL (a mesma chave que dags/ lê) sobre o
            # relógio do servidor. Config ausente/ruim degrada para 00:00.
            data_ref = dref.calcular(_agora(), _virada_global(cur))
        if lente is None and corrida_payload is not None and \
                corrida_payload["data_referencia"] != _fmt_dia(data_ref):
            # Navegação por dia numa data que não é a da corrida corrente: o
            # bloco sai do payload em vez de descrever outro ciclo.
            corrida_payload = None
        corridas_no_dia = None
        if lente is None and corrida_payload is not None:
            # Mesma data da corrente, mas o DIA pode ter tido mais de uma
            # corrida (rerun às 5h, o gesto que o aceite "duas corridas no mesmo
            # ODATE" descreve). Sem lente, `execucoes[]` traz o dia INTEIRO — as
            # linhas das duas — enquanto o bloco descreveria só a última: o nó
            # da corrida #1 verde no canvas ao lado de uma faixa dizendo "0 de
            # 2" da #2. É a MESMA tela contando duas coisas, que é exatamente o
            # que a Decisão 55 e esta fase existem para matar; então o bloco sai
            # e o front manda escolher uma corrida (o ◀ ▶, que aplica a lente e
            # aí sim recorta as duas pontas juntas).
            # Consulta própria, e não uma coluna no SQL compartilhado, porque
            # aquele serve a lista de 40 malhas com aceite de DUAS consultas;
            # aqui é uma malha só, e o custo é um seek em ix_malha_exec_malha.
            try:
                cur.execute(
                    "SELECT COUNT(*) FROM dbo.etl_malha_execucao "
                    "WHERE malha_name = ? AND data_referencia = ?",
                    (malha, data_ref))
                corridas_no_dia = int(cur.fetchone()[0] or 0)
            except Exception as e:  # noqa: BLE001 — leitura degrada
                log.warning("[malhas] contagem de corridas do dia indisponivel "
                            "(%s); o bloco da corrida segue no payload", e)
                corridas_no_dia = None
            if corridas_no_dia and corridas_no_dia > 1:
                corrida_payload = None

        # Membros da malha (JOIN garante que pipeline excluído some, como no
        # detalhe) — mapa casefold → grafia OFICIAL, a mesma canonização das
        # arestas da F8: linha de execução legada com caixa divergente não pode
        # sumir do colorido dos nós por causa de dict case-sensitive.
        cur.execute(
            "SELECT p.pipeline_name FROM dbo.etl_malha_pipeline mp "
            "JOIN dbo.etl_pipeline p ON p.pipeline_name = mp.pipeline_name "
            "WHERE mp.malha_name = ?",
            (malha,))
        membro_oficial = {str(r[0]).strip().casefold(): str(r[0]).strip()
                          for r in cur.fetchall()}

        resposta = {
            "data_referencia": data_ref.strftime("%Y-%m-%d"),
            "execucoes": [],
            "eventos": [],
            # F14: eventos dos nós observadores desta malha (marcador #no:{id}
            # resolvido para o id — risco 6 do desenho: o único leitor do
            # marcador é este endpoint) e a conclusão da malha na data.
            "eventos_no": [],
            "malha_concluida": None,
        }
        if corrida_payload is not None:
            resposta["corrida"] = corrida_payload
        elif sem_085:
            resposta["migration_085_pendente"] = True
        if corrida_payload is None and corridas_no_dia and corridas_no_dia > 1:
            # O front precisa distinguir "este dia não teve corrida" (o bloco
            # simplesmente não vem) de "teve VÁRIAS e você está vendo o dia
            # inteiro" — no segundo caso existe uma ação a oferecer, e é ela
            # que evita a leitura errada de um canvas que mistura dois ciclos.
            resposta["corridas_no_dia"] = corridas_no_dia
        if not _tabelas_067_execucao(cur):
            log.warning("[MALHA] migration 067 ausente — visão de execução da "
                        "malha '%s' degradada para vazio", malha)
            resposta["migration_067_pendente"] = True
            cur.close(); conn.close()
            return resposta

        # Execuções do dia num SELECT só (filtro de membros em Python, como nos
        # agregados da listagem); por pipeline vence a MAIS RECENTE — regra F9
        # extraída para services.dependencias.mais_recente_da_data na F5:
        # maior inicio, desempate por execution_id (linha AGUARDANDO ainda sem
        # start perde de qualquer linha iniciada). Status vai CRU — a legenda
        # da tela fala o mesmo domínio da tabela (AGUARDANDO_DEPENDENCIA |
        # EXECUTANDO | SUCESSO | FALHA | PULADO | NAO_LIBEROU).
        _exec_linhas_do_painel(cur, data_ref, lente)
        linhas_membro: dict[str, list] = {}
        for r in cur.fetchall():
            oficial = membro_oficial.get(str(r[0] or "").strip().casefold())
            if oficial is None:
                continue        # execução de quem não é membro não aparece
            linhas_membro.setdefault(oficial, []).append({
                "status": r[1], "inicio": r[2], "fim": r[3],
                "disparado_por": r[4], "motivo": r[5],
                "execution_id": str(r[6] or "")})
        # F10 (§9.6, Decisão 73) — os que precisam da resposta "de quem esta
        # corrida espera", num LOTE só. Antes desta fase cada um deles gastava
        # uma ida ao banco (três, no modo SEQUÊNCIA): com 12 esperando numa
        # malha de 40, o painel fazia 12 a 36 round-trips A CADA REFETCH, e é
        # exatamente durante o incidente que esse número cresce.
        esperando = []
        itens_esperando = {}
        for oficial in sorted(linhas_membro):
            vencedora = deps_svc.mais_recente_da_data(linhas_membro[oficial])
            item = {
                "pipeline_name": oficial,
                "status": vencedora["status"],
                "inicio": _fmt_dt(vencedora["inicio"]),
                "fim": _fmt_dt(vencedora["fim"]),
                "disparado_por": vencedora["disparado_por"],
                "motivo": vencedora["motivo"],
            }
            # F5 (D32): quem está esperando ganha `faltantes` ADITIVO — de quem
            # a corrida espera, pelo MESMO predicado do motor (o port, nunca um
            # "mais recente" paralelo). Campo novo opcional: front antigo ignora.
            if vencedora["status"] in ("AGUARDANDO_DEPENDENCIA", "NAO_LIBEROU"):
                esperando.append(oficial)
                itens_esperando[oficial] = item
            resposta["execucoes"].append(item)
        # Os pendentes da CORRIDA entram no mesmo lote (§9.5): a aba `Travando`
        # precisa da mesma resposta, e perguntá-la à parte seria reabrir o N+1
        # numa segunda porta. Só as classes em que "esperando quem?" é uma
        # pergunta de verdade — `falhou`/`orfa` são sobre o próprio pipeline, e
        # os predecessores deles concluíram (senão ele não teria rodado).
        #
        # ⚠️ A deduplicação é em `casefold`, e não por igualdade de string: os
        # nomes de `execucoes[]` vêm da grafia OFICIAL de `etl_pipeline` e os de
        # `pendentes[]` vêm do SNAPSHOT (`etl_malha_execucao_membro`), que
        # guarda a grafia do dia da abertura. As duas divergirem em caixa é o
        # GOTCHA que já quebrou pipeline em produção — aqui ele custaria o mesmo
        # nome duas vezes no `IN` e um faltante procurado numa chave que não
        # existe (a tela calando sobre quem está esperando).
        pendentes_da_corrida = (corrida_payload or {}).get("pendentes") or []
        ja_no_lote = {n.strip().casefold() for n in esperando}
        for p in pendentes_da_corrida:
            chave = str(p["pipeline"]).strip().casefold()
            if p["classe"] in _CLASSES_QUE_ESPERAM and chave not in ja_no_lote:
                ja_no_lote.add(chave)
                esperando.append(p["pipeline"])
        if esperando:
            # F6 (Decisão 39): a corrida da LINHA avaliada — aqui, a da LENTE,
            # que é justamente o recorte de onde estas linhas saíram. Sem ela,
            # no modo SEQUÊNCIA o painel cortaria pela janela de 12h enquanto o
            # motor corta pelo `aberta_em` da corrida: a tela diria "aguardando
            # PAI_X" com PAI_X já contado pelo motor (ou o contrário) — a
            # divergência painel×motor que a paridade do D29 existe para
            # impedir, reaparecendo pela porta do corte.
            faltantes = deps_svc.faltantes_em_lote(
                cur, esperando, data_ref,
                lente["id"] if lente is not None else None)
            # A mesma ponte de caixa da montagem do lote, agora na volta.
            por_chave = {str(k).strip().casefold(): v
                         for k, v in faltantes.items()}
            for oficial, item in itens_esperando.items():
                item["faltantes"] = por_chave.get(
                    oficial.strip().casefold(), [])
            for p in pendentes_da_corrida:
                falt = por_chave.get(str(p["pipeline"]).strip().casefold())
                if falt is None:
                    continue
                p["faltantes"] = falt
                # `faltante` (singular) é o campo que a F4 deixou reservado: o
                # card tem espaço para UM nome. A lista completa viaja ao lado,
                # para a aba do painel, que tem espaço para todos.
                p["faltante"] = falt[0] if falt else None
        # O RAIO DE ALCANCE (Decisão 63) — quantos membros esta corrida tem
        # parados atrás de cada pendente. É o que separa "um job parado no fim
        # da cadeia" de "um job parado que segura 18 outros", e é a informação
        # que decide se alguém acorda às 3h ou espera até as 7h.
        if pendentes_da_corrida:
            _raio_dos_pendentes(cur, corrida_payload)

        # Nós desta malha (F14): resolve o marcador '#no:{id}' dos eventos de
        # observador. Sem a 075 (deploy parcial) degrada — eventos_no vazio +
        # flag, o resto da visão intacto (princípio 6; padrão do GET detalhe).
        marcador_no: dict[str, dict] = {}
        if _tabelas_075(cur):
            for n in _nos_da_malha(cur, malha):
                marcador_no[f"#no:{n['id']}"] = n
        else:
            resposta["migration_075_pendente"] = True

        # Eventos da guardiã da MESMA data — de membros (F9) e dos nós desta
        # malha (F14) — mais novo primeiro. Marcador de nó de OUTRA malha não
        # resolve aqui e não aparece (mesma regra do filtro por membro).
        cur.execute(
            "SELECT pipeline_name, tipo, detectado_em, detalhe "
            "FROM dbo.etl_dependencia_evento WHERE data_referencia = ?",
            (data_ref,))
        eventos = []
        eventos_no = []
        eventos_corrida = []
        # F7: o marcador da corrida em foco. Até aqui os sete `MALHA_*` do ciclo
        # eram gravados e **nunca chegavam à tela** — `membro_oficial` não os
        # reconhece (a corrida não é um pipeline) e eles caíam no `continue`. O
        # crédito de retenção (Decisão 61) e o `MALHA_ATRASADA` são justamente
        # os dois fatos que o operador precisa ler para entender por que a barra
        # do limite mudou de lugar ou ficou âmbar.
        marcador_corrida = (MARCADOR_CORRIDA.format(corrida_payload["id"])
                            if corrida_payload is not None else None)
        for r in cur.fetchall():
            bruto = str(r[0] or "").strip()
            if marcador_corrida is not None and bruto == marcador_corrida:
                eventos_corrida.append({
                    "tipo": r[1],
                    "criado_em": _fmt_dt(r[2]),
                    "mensagem": r[3],
                })
                continue
            no = marcador_no.get(bruto)
            if no is not None:
                eventos_no.append({
                    "no_id": no["id"],
                    "tipo_no": no["tipo"],
                    "tipo": r[1],
                    "criado_em": _fmt_dt(r[2]),
                    "mensagem": r[3],
                })
                continue
            oficial = membro_oficial.get(bruto.casefold())
            if oficial is None:
                continue
            eventos.append({
                "pipeline_name": oficial,
                "tipo": r[1],
                "criado_em": _fmt_dt(r[2]),
                "mensagem": r[3],
            })
        eventos.sort(key=lambda e: (e["criado_em"] or "", e["pipeline_name"]),
                     reverse=True)
        eventos_no.sort(key=lambda e: (e["criado_em"] or "", e["no_id"]),
                        reverse=True)
        eventos_corrida.sort(key=lambda e: (e["criado_em"] or "", e["tipo"]),
                             reverse=True)
        resposta["eventos"] = eventos
        resposta["eventos_no"] = eventos_no
        # ADITIVO e só quando há corrida na lente: front antigo ignora a chave,
        # e a ausência dela não muda nada do que já era mostrado.
        if marcador_corrida is not None:
            resposta["eventos_corrida"] = eventos_corrida
        # Conclusão da malha (§9.6): com a corrida no payload quem responde é o
        # STATUS DELA — o evento vira rastro, não fonte de verdade. Sem isso, o
        # banner verde e o card vermelho conviveriam na mesma tela: o
        # `MALHA_CONCLUIDA` de uma corrida ANTERIOR do mesmo dia continua na
        # tabela (evento emitido é histórico verdadeiro e não se apaga), e o
        # laço abaixo o encontraria mesmo com a corrida corrente em FALHA.
        #
        # Sem corrida (malha sem ciclo registrado, ou banco sem a 085) o
        # comportamento é o de hoje, byte a byte — é assim que o painel degrada
        # junto com o card, e não um verde sobrando de cada vez.
        if corrida_payload is not None:
            resposta["malha_concluida"] = (
                {"em": corrida_payload["fechada_em"]}
                if corrida_payload["status"] == "CONCLUIDA" else None)
        else:
            for ev in eventos_no:
                if ev["tipo"] == "MALHA_CONCLUIDA" and ev["tipo_no"] == "fim":
                    resposta["malha_concluida"] = {"em": ev["criado_em"]}
                    break

        cur.close(); conn.close()
        return resposta
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.post("/malhas/{malha_name}/disparo", tags=["malhas"])
async def disparar_malha(malha_name: str, body: dict = Body(default={}),
                         auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Disparo MANUAL da malha (F15): dispara as RAÍZES ligadas ao Início com
    o MESMO ODATE, via trigger REST do Airflow — a cascata anda pelo push da
    F3 (o filho herda a data e dispara em segundos após o último predecessor).

    NENHUM executor novo (princípio 1 do desenho): este endpoint é o mesmo
    gesto de "rodar pipeline" da tela Pipelines, repetido para cada raiz, com
    o conf da casa (o schema de montar_conf do push, §7 da retomada):
      • data_referencia — o rótulo ODATE pedido (default: ODATE corrente pela
        virada da MALHA — Decisão 9 — ou, sem agendamento, pela virada global);
        o filho NÃO recalcula: herança pela cadeia inteira;
      • dia_operacional — HOJE (F3: o dia de um disparo manual é o dia em que
        o operador ordenou — as regras de DIA julgam contra ele);
      • disparado_por — auditoria: malha + matrícula de quem disparou (o
        registro da corrida grava em etl_pipeline_execucao.disparado_por).
    run_id com prefixo 'manual' — a origem F3 do disparo é 'manual' (não
    julga hora, julga dia), como no botão da tela Pipelines.

    Body: {"data_referencia"?: "YYYY-MM-DD", "dry_run"?: bool}. dry_run
    devolve o que SERÁ disparado (raízes + ODATE + avisos) sem tocar o
    Airflow — o modal de confirmação da tela mostra essa lista (§7.2, a
    mesma cadência dos gestos do desenho). Os avisos por raiz são honestos
    sobre o que o gesto atropela: DAG não publicada, pipeline inativo, raiz
    COM DEPENDÊNCIA (o trigger manual não consulta liberado() — a corrida
    parte por cima do predecessor) e corrida JÁ existente na data (o claim
    protege os dependentes, não a raiz disparada à mão). O write reporta
    erro POR RAIZ (uma raiz recusada não impede as outras — o resultado é
    dito, nunca escondido). Permissão: acao_executar, a mesma do trigger de
    pipeline.

    Sem a 075 não existe desenho (Início/raízes) — 503 instrutivo. Malha
    sem Início ou Início sem raízes é 422: não há o que disparar."""
    dry_run = bool(body.get("dry_run"))
    # Valida a data ANTES de abrir conexão (mesma regra do GET /execucao).
    data_ref = None
    bruto = body.get("data_referencia")
    if bruto is not None and str(bruto).strip() != "":
        try:
            data_ref = datetime.strptime(str(bruto).strip(), "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"data_referencia inválida: '{bruto}' "
                       "(use o formato YYYY-MM-DD)")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        _exigir_tabelas_075(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        nos_l = _nos_da_malha(cur, malha)
        arestas_l = _arestas_da_malha(cur, malha)
        inicio = next((n for n in nos_l if n["tipo"] == "inicio"), None)
        if inicio is None:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=422,
                detail=f"A malha '{malha}' não tem componente Início — o "
                       "disparo manual parte das raízes ligadas a ele. "
                       "Adicione o Início no diagrama e ligue-o às raízes.")
        raizes = sorted({a["destino_pipeline"] for a in arestas_l
                         if a["origem_no"] == inicio["id"]
                         and a["destino_pipeline"]}, key=str.casefold)
        if not raizes:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=422,
                detail=f"O Início da malha '{malha}' não está ligado a "
                       "nenhuma raiz — ligue-o aos pipelines que abrem a "
                       "malha antes de disparar.")
        # Quem escolheu o ODATE: o operador (data no body) ou o default da
        # tela. A F3 usa isso para não avisar de divergência quando a data foi
        # ESCOLHIDA — reprocessar um dia anterior é gesto legítimo e diário, e
        # um aviso a cada vez ensina o operador a ignorar todos os avisos.
        data_do_body = data_ref is not None
        if data_ref is None:
            # ODATE corrente pela virada GLOBAL — a MESMA régua do
            # GET /execucao (o painel de onde o gesto parte). Uma fonte só
            # para o ODATE default: usar a virada da MALHA aqui faria o
            # painel mostrar D e o disparo carimbar D+1 no mesmo minuto
            # (virada da malha 20:00 × global 00:00, às 21:00) — divergência
            # entre a tela e o que foi disparado, a doença que a retomada
            # inteira existiu para matar. Se um dia a régua do painel passar
            # a ser a virada da malha (Decisão 9), muda-se no /execucao e
            # este default acompanha; não é escopo da F15. Na prática o front
            # sempre manda a data EXIBIDA — este default é a rede de proteção
            # de quem chama a API direto.
            data_ref = dref.calcular(_agora(), _virada_global(cur))

        # Fotografia honesta por raiz (avisos ditos ANTES do gesto — §2.2).
        avisos: list = []
        cur.execute("SELECT CAST(ativo AS INT) FROM dbo.etl_malha "
                    "WHERE malha_name = ?", (malha,))
        row = cur.fetchone()
        if row is not None and int(row[0] or 0) == 0:
            avisos.append({"no": None, "nivel": "forte", "mensagem":
                           "malha inativa — os observadores (Notificação e "
                           "Fim) não emitem eventos enquanto ativo=0; o "
                           "disparo das raízes acontece mesmo assim"})
        tem_067 = _tabela_067(cur)
        tem_exec_067 = _tabelas_067_execucao(cur)
        raizes_info = []
        for p in raizes:
            cur.execute(
                "SELECT CAST(active AS INT), CAST(dag_criada AS INT) "
                "FROM dbo.etl_pipeline WHERE pipeline_name = ?", (p,))
            r = cur.fetchone()
            ativo_p = int(r[0] or 0) if r else 0
            dag_criada = int(r[1] or 0) if r else 0
            info = {"pipeline": p, "active": ativo_p, "dag_criada": dag_criada,
                    "tem_dependencia": False, "corridas_na_data": 0}
            raizes_info.append(info)
            # Raiz que ganhou dependência por outra porta (§2.2): o disparo
            # manual parte a corrida POR CIMA do predecessor — o trigger
            # manual não consulta liberado(). Aviso, nunca bloqueio (a mesma
            # régua do badge de contradição): o gesto é do operador, mas ele
            # precisa saber o que está atropelando ANTES de confirmar.
            if tem_067 and _raiz_tem_dependencia(cur, p):
                info["tem_dependencia"] = True
                avisos.append({"no": inicio["id"], "nivel": "forte",
                               "tipo": "contradicao",
                               "mensagem": _msg_disparo_raiz_com_dependencia(p)})
            # Corrida JÁ registrada na data: os filhos são protegidos pelo
            # claim serializable, a RAIZ não — disparar de novo roda de novo.
            if tem_exec_067:
                cur.execute(
                    "SELECT COUNT(*) FROM dbo.etl_pipeline_execucao "
                    "WHERE pipeline_name = ? AND data_referencia = ?",
                    (p, data_ref))
                row_c = cur.fetchone()
                n_corridas = int(row_c[0] or 0) if row_c else 0
                info["corridas_na_data"] = n_corridas
                if n_corridas > 0:
                    avisos.append({
                        "no": inicio["id"], "nivel": "forte",
                        "tipo": "corrida_existente",
                        "mensagem": _msg_corrida_existente(p, n_corridas,
                                                           data_ref)})
            if dag_criada == 0:
                avisos.append({"no": inicio["id"], "nivel": "forte",
                               "mensagem": f"'{p}': a DAG ainda não foi "
                               "publicada — o disparo desta raiz vai falhar "
                               "no Airflow (Pipelines ▸ Publicar nova versão)"})
            elif ativo_p == 0:
                avisos.append({"no": inicio["id"], "nivel": "leve",
                               "mensagem": f"'{p}' está inativo — a DAG pode "
                               "estar pausada no Airflow; a corrida criada "
                               "só anda com a DAG despausada"})
        # F5 da spec-malha-execucao (§12.2, risco 9) — a sonda do `force_all`,
        # POR MEMBRO. A F5 é a única fase que exige regeração das DAGs, e o
        # gesto não está no deploy.sh: enquanto ele não acontece, metade dos
        # membros carimba o ODATE pela corrida e metade calcula sozinha — a
        # doença com aparência de cura. O disparo AVISA e segue: o gesto é do
        # operador, e recusar aqui pararia a malha por causa de um arquivo
        # desatualizado que ninguém sabe que existe.
        #
        # Vale para TODO membro, não só para as raízes: quem calcula a própria
        # data no meio da malha é justamente o membro com cron próprio — o
        # `Carga_Vida` invertido do §7.
        #
        # DESCONHECIDO tem frase PRÓPRIA e nunca vira acusação: não conseguir
        # ler o fonte não prova nada sobre ele.
        # A sonda só fala com o interruptor LIGADO: enquanto ele está em 0,
        # ninguém carimba ODATE pela corrida e "sua DAG não tem o carimbo" seria
        # ruído puro — e ruído que aparece em todo disparo ensina a operação a
        # ignorar a caixa de avisos inteira.
        sondas: list = []
        try:
            if mc.corrida_ativa(cur):
                cur.execute(_SQL_MEMBROS_DA_MALHA, (malha,))
                _membros_sonda = sorted({r[0] for r in cur.fetchall() if r[0]},
                                        key=str.casefold)
                sondas = espera_svc.carimbo_corrida_dos_pipelines(
                    cur, _membros_sonda)
        except Exception as e:  # noqa: BLE001 — sonda é diagnóstico, nunca porta
            log.warning("[MALHA] sonda do carimbo de ODATE indisponivel: %s", e)
            sondas = []
        sem_carimbo = [s["pipeline"] for s in sondas
                       if s["sonda"] == espera_svc.CORRIDA_AUSENTE]
        carimbo_incerto = [s["pipeline"] for s in sondas
                           if s["sonda"] == espera_svc.CORRIDA_DESCONHECIDO]
        if sem_carimbo:
            avisos.append({
                "no": inicio["id"], "nivel": "forte", "tipo": "sem_carimbo_odate",
                "mensagem": (
                    f"{_lista_curta(sem_carimbo)} — a DAG publicada foi gerada "
                    f"antes do carimbo de data pela corrida da malha: "
                    f"{'esses pipelines' if len(sem_carimbo) > 1 else 'esse pipeline'} "
                    f"vai calcular a própria data de referência em vez de "
                    f"aderir à do ciclo. Publique a DAG de novo (Pipelines ▸ "
                    f"Publicar nova versão) para o ciclo inteiro ficar na "
                    f"mesma data")})
        if carimbo_incerto:
            avisos.append({
                "no": inicio["id"], "nivel": "leve", "tipo": "carimbo_incerto",
                "mensagem": (
                    f"não foi possível conferir o fonte publicado de "
                    f"{_lista_curta(carimbo_incerto)} — se a DAG for anterior "
                    f"ao carimbo de data pela corrida, o membro calcula a "
                    f"própria data; na dúvida, publique a DAG de novo")})

        # F1 da spec-malha-data-unica: a malha começa do ZERO. Corrida viva de
        # membro ou data de referência divergente NESTE ciclo barram o disparo
        # — a partida por cima de uma corrida em andamento é o que produziu, na
        # Carga_Vida, metade da malha num ODATE e metade em outro.
        # (Gancho da F3: com `equalizar_data` ligado na malha, este ponto passa
        # a recarimbar em vez de recusar — o desenho está na spec.)
        bloqueios = ({"em_aberto": [], "datas_divergentes": []}
                     if not tem_exec_067
                     else _bloqueios_do_ciclo(cur, malha, data_ref))

        # F3: a malha marcada NÃO para para perguntar — ela carimba todos com a
        # data do ciclo e segue. Vale só para DATA: corrida em ANDAMENTO
        # continua barrando com ou sem a marca (recarimbar uma corrida em voo
        # trocaria a chave dela no meio do caminho).
        equaliza = (tem_exec_067 and bool(bloqueios["datas_divergentes"])
                    and _equalizar_data_da_malha(cur, malha))
        equalizaveis, nao_equalizaveis = ([], [])
        if equaliza:
            equalizaveis, nao_equalizaveis = _equalizaveis(
                cur, malha, data_ref, bloqueios["datas_divergentes"])
        quem = (str(auth.get("matricula") or "").strip() or "?")
        equalizados: list = []
        if equaliza and not dry_run and not bloqueios["em_aberto"]:
            equalizados = _equalizar(cur, malha, data_ref, equalizaveis, quem)
            conn.commit()
            # Reconta com o banco JÁ equalizado: o que sobrar aqui é bloqueio
            # de verdade (o que não pôde ser recarimbado).
            bloqueios = _bloqueios_do_ciclo(cur, malha, data_ref)
            log.info("[MALHA] malha '%s': %d execução(ões) equalizadas para %s "
                     "por %s", malha, len(equalizados), data_ref, quem)

        tem_bloqueio = bool(bloqueios["em_aberto"]
                            or bloqueios["datas_divergentes"])

        # ── Porta 1 do §6.2 — a corrida abre AQUI, na mesma transação dos
        # bloqueios e ANTES dos triggers (spec-malha-execucao, F3) ───────────
        #
        # A ORDEM importa e é o que torna a expiração preguiçosa segura: só se
        # chega ao portão da corrida com `tem_bloqueio` falso, isto é, com
        # NENHUM membro da malha `EXECUTANDO`/`AGUARDANDO_DEPENDENCIA` em data
        # nenhuma. Assim a Decisão 25 ("o teto nunca fecha corrida com membro
        # vivo") vale por construção, e não por sorte — o `estado()` que o
        # `_expirar_na_porta` consulta é a segunda trava, não a única.
        #
        # `corrida` é ADITIVO na resposta: quando o portão do §11.1 está
        # fechado, a chave não aparece e o disparo responde exatamente como
        # antes desta fase (degradação por AUSÊNCIA do campo, o contrato da F4).
        corrida = None            # a corrida que ESTE disparo abriu
        corrida_previa = None     # o que o dry_run mostra, sem escrever nada
        erro_corrida = None       # a frase do 422 "já existe corrida aberta"
        opera_corrida, _razao = _corrida_operavel(cur, malha)
        if opera_corrida:
            aberta = mc.corrida_aberta(cur, malha)
            # Divergência VISÍVEL é o oposto de divergência silenciosa (§6.2): o
            # ODATE default do disparo é a virada GLOBAL (a régua do painel) e o
            # canônico da malha (Decisão 18) é a virada DELA. Quando as duas
            # discordam, a corrida nasce com a data que este disparo vai
            # carimbar — e o operador lê isso ANTES de confirmar, em vez de
            # descobrir no card. Só quando a data NÃO foi escolhida: reprocessar
            # um dia anterior de propósito não é divergência, é o gesto.
            if not data_do_body:
                odate_canonico = mc.odate_da_abertura(cur, malha,
                                                      _agora_do_banco(cur))
                if odate_canonico != data_ref:
                    avisos.append({
                        "no": inicio["id"], "nivel": "leve",
                        "tipo": "odate_malha",
                        "mensagem": (
                            f"a virada desta malha aponta "
                            f"{_fmt_dia(odate_canonico)} e o disparo vai "
                            f"carimbar {_fmt_dia(data_ref)} (a régua do "
                            f"painel) — a corrida nasce com a data do disparo; "
                            f"informe a data no modal se quiser a outra")})
            if dry_run:
                if aberta is not None:
                    # O dry_run NÃO escreve (é prévia, não gesto): mostra a
                    # corrida e diz o que o gesto real FARIA com ela. Sem esta
                    # segunda frase o modal mentiria por omissão — anunciaria
                    # bloqueio numa corrida que o disparo vai expirar sozinho.
                    #
                    # F7: com nó SEGURADO o teto não corre (Decisão 30) — e a
                    # prévia tem de dizer a MESMA coisa que o gesto real fará,
                    # senão o modal promete "esta corrida será expirada" e o
                    # disparo, meio segundo depois, recusa por corrida aberta.
                    hold_previa = mc.hold_da_malha(cur, malha)
                    vencido = (not hold_previa["retido"]) and mc.relogios(
                        cur, aberta, mc.CARENCIA_PARTIDA_PADRAO,
                        mc.QUIESCENCIA_MIN_PADRAO).get("teto_vencido")
                    corrida_previa = {**_corrida_publica(aberta),
                                      "teto_vencido": bool(vencido),
                                      "sera_expirada": bool(vencido),
                                      "nos_retidos": hold_previa["nos"]}
            elif not tem_bloqueio:
                if aberta is not None and _expirar_na_porta(cur, aberta, quem):
                    aberta = None          # Decisão 29 — expirou e prossegue
                if aberta is not None:
                    erro_corrida = _msg_corrida_aberta(aberta)
                else:
                    corrida = _abrir_corrida_do_disparo(
                        cur, malha, nos_l, arestas_l, data_ref, quem,
                        inicio["id"])
                    if corrida is not None and not corrida["nova"]:
                        # Aderimos ao ciclo de outra ponta (a guardiã abriu
                        # entre a conferência e o INSERT). Recusar é a mesma
                        # resposta do caso acima — e é o que impede o disparo de
                        # partir por cima de um ciclo recém-nascido.
                        erro_corrida = _msg_corrida_aberta(corrida)
                        corrida = None

        # O banco fecha ANTES das chamadas ao Airflow: uma rede lenta não
        # pode segurar conexão de pool aberta (padrão do proxy).
        if erro_corrida:
            # Rollback explícito: a expiração preguiçosa pode ter escrito antes
            # de descobrirmos que ainda havia corrida (duas abertas é
            # impossível, mas a leitura e a decisão são dois instantes).
            _fechar_silencioso(conn); conn = None
            raise HTTPException(status_code=422, detail=erro_corrida)
        if opera_corrida:
            # Abertura + snapshot num commit só (§6.2). Sem corrida aberta o
            # commit é de uma transação sem escrita — inofensivo, e mantém um
            # caminho só.
            conn.commit()
        cur.close(); conn.close(); conn = None

        if dry_run:
            # O dry_run NÃO recusa: ele MOSTRA. O modal precisa exibir quem
            # está segurando a malha (com nome e data) para o operador agir —
            # um 422 seco aqui esconderia a lista. Com a marca de equalização,
            # mostra também o que SERÁ recarimbado: a malha anda sozinha, mas
            # o operador vê o de→para antes de confirmar.
            resp = {"data_referencia": data_ref.strftime("%Y-%m-%d"),
                    "raizes": raizes_info, "avisos": avisos,
                    "bloqueios": bloqueios,
                    "bloqueado": tem_bloqueio and not equaliza}
            # ADITIVO e só quando há o que reportar (§12.2): as duas colunas —
            # pipeline e sonda — para o operador republicar só quem ficou para
            # trás. Quem está em dia não entra na lista: um relatório que
            # sempre aparece deixa de ser lido.
            if sem_carimbo or carimbo_incerto:
                resp["carimbo_odate"] = [
                    s for s in sondas if s["sonda"] != espera_svc.CORRIDA_OK]
            if equaliza:
                resp["equalizacao"] = {
                    "prevista": equalizaveis,
                    "impedidos": nao_equalizaveis,
                    # Corrida em aberto não é resolvida por equalização: com
                    # ela presente, o bloqueio continua de pé.
                    "bloqueado_por_corrida": bool(bloqueios["em_aberto"]),
                }
                resp["bloqueado"] = bool(bloqueios["em_aberto"]
                                         or nao_equalizaveis)
            if corrida_previa is not None:
                # ADITIVO e só quando há corrida aberta: o modal mostra qual
                # ciclo está em voo e se o disparo real vai expirá-lo sozinho.
                # `dry_run` NÃO abre e NÃO expira nada — é prévia, não gesto.
                resp["corrida"] = corrida_previa
                resp["bloqueado"] = (resp["bloqueado"]
                                     or not corrida_previa["sera_expirada"])
            return resp

        if tem_bloqueio:
            raise HTTPException(
                status_code=422,
                detail=_msg_bloqueio(bloqueios, data_ref.strftime("%Y-%m-%d")))

        hoje = _agora().date()
        conf = {
            "data_referencia": data_ref.strftime("%Y-%m-%d"),
            "dia_operacional": hoje.strftime("%Y-%m-%d"),
            "disparado_por": f"malha:{malha} ({quem})",
        }
        disparadas: list = []
        falhas: list = []
        # ⚠️ Da linha do `conn.commit()` acima até aqui a corrida JÁ ESTÁ
        # COMMITADA e nenhuma raiz partiu ainda. Uma exceção que escape do
        # `try` POR RAIZ (o cliente HTTP que não sobe, o `aclose` que
        # estoura) sairia pelo 500 do fim da função deixando a corrida
        # ABERTA sem nada que a originasse — e o §6.9/#4 existe justamente
        # para isso não acontecer. O aborto do caminho "todas as raízes
        # falharam" não cobre este: lá `falhas` está cheia, aqui ela está
        # VAZIA porque nem se chegou a tentar. Mesma resposta, mesma
        # segunda conexão — senão a malha congela até o teto de 24h.
        try:
            async with get_airflow_client() as client:
                for p in raizes:
                    if not _DAG_ID_RE.match(p):
                        falhas.append({"pipeline": p, "erro":
                                       "nome de pipeline não é um dag_id válido"})
                        continue
                    # Mesmo formato do novo_run_id da retomada, origem 'manual'.
                    carimbo = datetime.now().strftime("%Y%m%dT%H%M%S%f")
                    run_id = (f"manual__{data_ref.strftime('%Y-%m-%d')}__"
                              f"{p[:60]}__{carimbo}")
                    try:
                        r = await client.post(
                            f"/api/v1/dags/{p}/dagRuns",
                            json={"dag_run_id": run_id, "conf": conf},
                            headers={"Content-Type": "application/json"})
                        if r.is_success:
                            disparadas.append({
                                "pipeline": p,
                                "dag_run_id": r.json().get("dag_run_id", run_id)})
                        elif r.status_code == 404:
                            falhas.append({"pipeline": p, "erro":
                                           "DAG não encontrada no Airflow — "
                                           "publique o pipeline antes de disparar "
                                           "(Pipelines ▸ Publicar nova versão)"})
                        elif r.status_code == 409:
                            falhas.append({"pipeline": p, "erro":
                                           "o Airflow recusou: já existe uma "
                                           "corrida com este run_id"})
                        else:
                            falhas.append({"pipeline": p, "erro":
                                           f"Airflow recusou o disparo "
                                           f"(HTTP {r.status_code}): {r.text[:200]}"})
                    except Exception as e:      # noqa: BLE001 — erro POR RAIZ
                        falhas.append({"pipeline": p, "erro":
                                       f"falha ao contatar o Airflow: {e}"})
        except Exception as e:  # noqa: BLE001 — aborta e RELANÇA
            # `not disparadas`: se alguma raiz JÁ partiu, a corrida é dela e
            # abortá-la seria fechar um ciclo em voo — o oposto do objetivo.
            if corrida is not None and not disparadas:
                _abortar_corrida_do_disparo(
                    corrida, quem,
                    [{"pipeline": p,
                      "erro": f"o disparo não chegou a ser tentado: {e}"}
                     for p in raizes])
            raise
        log.info("[MALHA] disparo manual da malha '%s' por %s — data_ref=%s, "
                 "%d disparada(s), %d falha(s)", malha, quem,
                 conf["data_referencia"], len(disparadas), len(falhas))
        # `equalizados` é ADITIVO e só aparece quando houve recarimbo: a tela
        # avisa o operador do que foi mudado no histórico em nome dele.
        resp_write = {"ok": len(falhas) == 0,
                      "data_referencia": conf["data_referencia"],
                      "disparadas": disparadas, "falhas": falhas,
                      "avisos": avisos}
        if sem_carimbo or carimbo_incerto:
            resp_write["carimbo_odate"] = [
                s for s in sondas if s["sonda"] != espera_svc.CORRIDA_OK]
        if equalizados:
            resp_write["equalizados"] = equalizados
        if corrida is not None:
            # §6.9/#4 — TODAS as raízes falharam: a corrida não pode sobreviver
            # ao gesto que não aconteceu. O aborto vai numa SEGUNDA conexão
            # porque a transação do disparo já foi commitada acima; sem ele, o
            # primeiro Airflow fora do ar congelaria a malha até o teto, com o
            # próximo disparo recusado por uma corrida FANTASMA.
            precisa_abortar = bool(falhas and not disparadas)
            fechada = (_abortar_corrida_do_disparo(corrida, quem, falhas)
                       if precisa_abortar else None)
            resp_write["corrida"] = {
                # A corrida RELIDA quando o aborto passou: `status` e
                # `fechada_em` são a mesma informação no modelo, e publicá-los
                # em desacordo faria a tela ler "fechada" de um campo e
                # "aberta" do outro.
                **_corrida_publica(fechada if fechada is not None else corrida),
                "abortada": fechada is not None,
            }
            if precisa_abortar and fechada is None:
                # O aborto NÃO passou (segunda conexão fora do ar, ou outra
                # ponta mexeu na corrida no vão). A malha fica travada até o
                # teto e só um gesto humano a destrava — e até aqui isso só
                # existia no log do servidor, que o operador não lê. A regra da
                # casa é frase de AÇÃO: o que aconteceu, por que, e o que a
                # pessoa faz agora. Sem ela o plantonista vê "nenhuma raiz
                # partiu", tenta de novo e leva um 422 de uma corrida que ele
                # não sabe que existe.
                avisos.append({
                    "no": inicio["id"], "nivel": "forte",
                    "tipo": "corrida_orfa",
                    "mensagem": (
                        f"nenhuma raiz partiu e a {_rotulo_corrida(corrida)} "
                        f"NÃO pôde ser encerrada automaticamente — ela segue "
                        f"aberta e vai recusar o próximo disparo desta malha. "
                        f"Encerre-a em Malha ▸ Encerrar corrida (com motivo) "
                        f"antes de disparar de novo; encerrar fecha o ciclo e "
                        f"não interrompe pipeline nenhum")})
        return resp_write
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


_MSG_SEM_085 = (
    "Corrida de malha indisponível: a migration 085 (etl_malha_execucao) ainda "
    "não foi aplicada neste banco — não há ciclo registrado para listar nem "
    "para encerrar."
)


@router.post("/malhas/{malha_name}/corridas/{corrida_id}/encerrar",
             tags=["malhas"])
def encerrar_corrida(malha_name: str, corrida_id: int,
                     body: dict = Body(default={}),
                     auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """A porta de saída do operador (§6.8, Decisão 32): fecha a corrida como
    `CANCELADA`, com motivo OBRIGATÓRIO, e libera o disparo NA HORA.

    Por que existe: sem ela, a única saída para uma corrida travada às 3h seria
    esperar as 24h do teto ou apagar a malha. Teto de 24h não é ferramenta de
    plantão, é espera.

    ⚠️ **Encerrar a corrida NÃO mata processo nenhum.** O que está `EXECUTANDO`
    continua executando: o gesto fecha o CICLO — o registro que diz "esta
    madrugada acabou" —, não os DagRuns. Quem precisa parar um pipeline usa a
    tela de Execuções. A resposta diz isso nominalmente, porque é a dúvida que
    faz o operador não apertar o botão.

    Motivo é obrigatório e vai para `motivo` + `fechada_por`: uma corrida
    cancelada sem razão registrada é um buraco no histórico da malha justamente
    no dia em que algo deu errado.

    **NÃO passa pelo portão do §11.1** (interruptor / capacidade do `dags/` /
    heartbeat), de propósito: é a saída de emergência, e ela precisa funcionar
    exatamente nos ambientes em que o resto não funciona — motor antigo,
    guardiã morta, interruptor desligado depois de uma corrida já aberta. Exige
    só que a 085 exista, senão não há o que encerrar.

    Permissão: `acao_executar` — a mesma do disparo (é o par dele).
    """
    motivo = str(body.get("motivo") or "").strip()
    if not motivo:
        raise HTTPException(
            status_code=422,
            detail="Informe o motivo do encerramento: ele fica no histórico da "
                   "corrida e é o que explica, depois, por que este ciclo foi "
                   "fechado à mão (ex.: 'carga do dia refeita por fora').")
    motivo = motivo[:300]
    quem = (str(auth.get("matricula") or "").strip() or "?")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        if not mc.tabela_085_presente(cur):
            _fechar_silencioso(conn)
            raise HTTPException(status_code=503, detail=_MSG_SEM_085)
        corrida = mc.corrida(cur, corrida_id)
        if corrida is None:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=404,
                detail="Não encontrei essa corrida. Ela pode ter sido de outra malha, ou o link está velho — abra a malha e escolha a corrida na lista.")
        # A corrida é identificada pelo `id` (Decisão 7), mas o endpoint vive
        # sob a malha: encerrar a corrida de OUTRA malha por um id digitado
        # errado é o tipo de gesto que ninguém desfaz.
        if str(corrida["malha_name"]).casefold() != str(malha).casefold():
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=422,
                detail=f"Essa corrida é da malha "
                       f"'{corrida['malha_name']}', não de '{malha}'. Abra a "
                       f"malha dona da corrida para encerrá-la.")
        if corrida["fechada_em"] is not None:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=422,
                detail=f"A {_rotulo_corrida(corrida)} já foi encerrada em "
                       f"{_fmt_dt(corrida['fechada_em'])} como "
                       f"{corrida['status']}"
                       + (f" por {corrida['fechada_por']}"
                          if corrida["fechada_por"] else "")
                       + ". O disparo desta malha já está liberado — se ele "
                         "ainda recusa, o motivo é outro (a mensagem do 422 do "
                         "disparo nomeia qual).")
        detalhe = f"encerrada por {quem}: {motivo}"
        # Evento e fechamento no MESMO commit (Decisão 20): a detecção do que
        # ainda está aberto consome a própria fonte (`fechada_em IS NULL`), e
        # uma falha entre dois commits perderia o card PARA SEMPRE.
        if not mc.fechar_corrida(cur, corrida["id"], "CANCELADA",
                                 f"manual:{quem}", motivo=detalhe):
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=422,
                detail=f"A {_rotulo_corrida(corrida)} foi encerrada por outra ponta "
                       f"enquanto esta tela pedia o encerramento. Recarregue a "
                       f"malha: o ciclo já está fechado.")
        _evento_da_corrida(cur, corrida, "MALHA_CANCELADA", detalhe)
        conn.commit()
        fechada = mc.corrida(cur, corrida["id"]) or corrida
        cur.close(); conn.close(); conn = None
        log.warning("[MALHA] corrida #%s da malha '%s' CANCELADA por %s: %s",
                    corrida_id, malha, quem, motivo)
        return {
            "ok": True,
            "corrida": _corrida_publica(fechada),
            # A resposta diz o que NÃO aconteceu. É a metade da verdade que o
            # operador precisa para não achar que "encerrar" é "matar".
            "execucoes_interrompidas": 0,
            "aviso": ("O ciclo da malha foi encerrado. Os pipelines que já "
                      "estavam rodando CONTINUAM rodando — encerrar a corrida "
                      "fecha o registro do ciclo, não interrompe execução "
                      "nenhuma. O disparo desta malha volta a funcionar agora."),
        }
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.get("/malhas/{malha_name}/corridas", tags=["malhas"])
def listar_corridas(malha_name: str, data_referencia: str | None = None,
                    limite: int = 30,
                    _auth: dict = Depends(get_current_user)):
    """Os ciclos desta malha, do mais recente para o mais antigo.

    É o que a F4 navega: duas corridas do MESMO ODATE (redisparo) são legítimas
    e vêm as duas, distinguidas por `sequencia` — o rótulo humano da N-ésima do
    dia — e identificadas pelo `id`, que é a identidade de verdade (Decisão 7).
    Com `?data_referencia=YYYY-MM-DD` a lista já vem recortada no dia, que é
    como o ◀ ▶ do painel pede.

    Leitura: degrada, nunca 503 por causa da 085 — sem a migration a lista sai
    vazia com `migration_085_pendente`, e o painel volta ao texto de hoje. A
    falta do ciclo não pode tirar a tela de Malha do ar.
    """
    limite = max(1, min(int(limite or 30), 200))
    data_ref = None
    if data_referencia is not None and str(data_referencia).strip() != "":
        try:
            data_ref = datetime.strptime(
                str(data_referencia).strip(), "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"data_referencia inválida: '{data_referencia}' "
                       "(use o formato YYYY-MM-DD)")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        resposta = {"malha_name": malha, "corridas": [], "aberta": None,
                    "data_referencia": _fmt_dia(data_ref)}
        if not mc.tabela_085_presente(cur):
            log.warning("[MALHA] migration 085 ausente — lista de corridas da "
                        "malha '%s' degradada para vazia", malha)
            resposta["migration_085_pendente"] = True
            cur.close(); conn.close()
            return resposta
        try:
            if data_ref is None:
                cur.execute(_SQL_CORRIDAS_DA_MALHA, (limite, malha))
            else:
                cur.execute(_SQL_CORRIDAS_DA_MALHA_NA_DATA,
                            (limite, malha, data_ref))
            linhas = [mc._como_dict(r) for r in cur.fetchall()]
        except Exception as e:  # noqa: BLE001 — leitura degrada larga
            log.warning("[MALHA] corridas da malha '%s' indisponíveis (%s) — "
                        "lista vazia", malha, e)
            linhas = []
        resposta["corridas"] = [_corrida_publica(c) for c in linhas]
        # `aberta` é o id do ciclo em voo, e vem separado porque a página pode
        # estar recortada por data: a corrida aberta é a única sobre a qual há
        # um GESTO possível (encerrar), e escondê-la atrás da paginação seria
        # esconder justamente o botão que destrava a malha.
        em_voo = next((c for c in linhas if c["fechada_em"] is None), None)
        if em_voo is None:
            # A releitura é INCONDICIONAL, e não só quando há recorte por data.
            # A ordenação é `data_referencia DESC` e a corrida aberta pode ser
            # de um ODATE ANTIGO — reprocessar um dia anterior é gesto legítimo
            # e diário (o `data_referencia` do body do disparo existe para
            # isso). Numa malha com mais de `limite` corridas, essa corrida
            # aberta cai FORA da página, `aberta` sairia `null` e a F4 esconderia
            # exatamente o botão que destrava a malha — o oposto do que o
            # comentário acima promete.
            em_voo = mc.corrida_aberta(cur, malha)
        resposta["aberta"] = (_corrida_publica(em_voo)
                              if em_voo is not None else None)
        resposta["total"] = len(resposta["corridas"])
        cur.close(); conn.close()
        return resposta
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


# ── Estado do ciclo da malha (spec-malha-data-unica.md, F1) ─────────────────
# A malha começa do ZERO: nenhum membro correndo e todos na MESMA data de
# referência. Duas perguntas, uma consulta cada — as duas são sobre MEMBROS
# desta malha, nunca sobre o banco inteiro.
_STATUS_EM_ABERTO = ("EXECUTANDO", "AGUARDANDO_DEPENDENCIA")


def _corridas_em_aberto(cur, malha: str) -> list:
    """Membros com corrida viva (EXECUTANDO/AGUARDANDO), em QUALQUER data.

    Sem filtro de data de propósito: uma corrida presa em outro ODATE é
    exatamente o que a regra quer barrar — a malha não pode recomeçar por cima
    de si mesma. Corrida substituída (rerun, migration 078) não conta."""
    marcadores = ",".join("?" for _ in _STATUS_EM_ABERTO)
    sql = ("SELECT e.pipeline_name, e.data_referencia, e.status, e.inicio "
           "FROM dbo.etl_pipeline_execucao e "
           "JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name "
           f"WHERE mp.malha_name = ? AND e.status IN ({marcadores}) ")
    deps_svc._exec_com_fallback_078(
        cur, sql + "AND e.substituida_em IS NULL", sql,
        (malha, *_STATUS_EM_ABERTO))
    return [{"pipeline": r[0], "data_referencia": _fmt_dia(r[1]),
             "status": r[2], "inicio": _fmt_dt(r[3])}
            for r in cur.fetchall()]


def _datas_divergentes(cur, malha: str, data_ref, desde) -> list:
    """Membros com execução carimbada em data DIFERENTE da do ciclo, iniciada
    de `desde` para cá (a virada corrente).

    O recorte por `inicio` é o que separa "a corrida de ontem, encerrada" —
    que é histórico legítimo — de "esta mesma madrugada, com dois ODATEs
    diferentes", que é a doença. Sem ele, toda malha com histórico seria
    barrada para sempre."""
    cur.execute(
        "SELECT e.pipeline_name, e.data_referencia, e.status, e.inicio "
        "FROM dbo.etl_pipeline_execucao e "
        "JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name "
        "WHERE mp.malha_name = ? AND e.data_referencia <> ? AND e.inicio >= ? "
        "ORDER BY e.pipeline_name, e.inicio",
        (malha, data_ref, desde))
    return [{"pipeline": r[0], "data_referencia": _fmt_dia(r[1]),
             "status": r[2], "inicio": _fmt_dt(r[3])}
            for r in cur.fetchall()]


def _inicio_do_ciclo(cur, agora: datetime):
    """Instante da virada mais recente — o começo do ciclo corrente.

    Convertido para a régua do BANCO (GETDATE pode estar em outro fuso que o
    container da API — caso real do dev): `inicio` é carimbado por lá, e
    comparar relógios diferentes produziria divergência fantasma ou, pior,
    silêncio."""
    virada = dref.parse_virada(_virada_global(cur))
    base = (agora.date() if agora.time() >= virada
            else agora.date() - timedelta(days=1))
    corte = datetime.combine(base, virada)
    try:
        cur.execute("SELECT GETDATE()")
        row = cur.fetchone()
        if row and row[0] is not None:
            corte += (row[0] - agora)
    except Exception as e:
        log.debug("[MALHA] relógio do banco indisponível para o corte: %s", e)
    return corte


def _bloqueios_do_ciclo(cur, malha: str, data_ref) -> dict:
    """As duas travas juntas, no formato que a tela e o 422 consomem."""
    em_aberto = _corridas_em_aberto(cur, malha)
    divergentes = _datas_divergentes(cur, malha, data_ref,
                                     _inicio_do_ciclo(cur, _agora()))
    return {"em_aberto": em_aberto, "datas_divergentes": divergentes}


def _equalizar_data_da_malha(cur, malha: str) -> bool:
    """A malha está marcada para equalizar sozinha (F3)? Sem a 081, não."""
    if not _colunas_081(cur):
        return False
    try:
        cur.execute("SELECT CAST(equalizar_data AS INT) FROM dbo.etl_malha "
                    "WHERE malha_name = ?", (malha,))
        row = cur.fetchone()
        return bool(row and int(row[0] or 0))
    except Exception as e:
        log.warning("[MALHA] leitura de equalizar_data falhou: %s", e)
        return False


def _equalizaveis(cur, malha: str, data_ref, divergentes: list) -> tuple:
    """Separa o que PODE ser recarimbado do que não pode.

    Não pode: pipeline que já tem linha na data-alvo. Recarimbar criaria duas
    corridas do mesmo pipeline no mesmo ODATE — e a leitura "mais recente da
    data" passaria a escolher entre duas verdades. Melhor recusar nominalmente
    do que produzir um estado que ninguém consegue explicar depois."""
    podem, nao_podem = [], []
    for d in divergentes:
        cur.execute(
            "SELECT COUNT(*) FROM dbo.etl_pipeline_execucao "
            "WHERE pipeline_name = ? AND data_referencia = ?",
            (d["pipeline"], data_ref))
        row = cur.fetchone()
        if row and int(row[0] or 0) > 0:
            nao_podem.append({**d, "motivo":
                              "já existe corrida deste pipeline na data da "
                              "malha — recarimbar criaria duas"})
        else:
            podem.append(d)
    return podem, nao_podem


def _equalizar(cur, malha: str, data_ref, alvos: list, quem: str) -> list:
    """Recarimba para `data_ref` as execuções listadas e registra o de→para.

    Escrita em linha de EXECUÇÃO — histórico não pode mudar em silêncio:
    o `motivo` da própria linha guarda a origem da mudança e um evento
    DATA_EQUALIZADA fica no painel da malha, com quem mandou. Só linhas do
    ciclo corrente chegam aqui (o recorte é de quem chama)."""
    feitos = []
    for a in alvos:
        origem = a["data_referencia"]
        cur.execute(
            "UPDATE dbo.etl_pipeline_execucao "
            "SET data_referencia = ?, atualizado_em = GETDATE(), "
            "    motivo = LEFT(ISNULL(motivo + ' | ', '') + ?, 500) "
            "WHERE pipeline_name = ? AND data_referencia = ? "
            "  AND status = ?",
            (data_ref,
             f"data de referência equalizada de {origem} para "
             f"{_fmt_dia(data_ref)} pela malha {malha} ({quem})",
             a["pipeline"], origem, a["status"]))
        if (cur.rowcount or 0) > 0:
            feitos.append({"pipeline": a["pipeline"], "de": origem,
                           "para": _fmt_dia(data_ref)})
    if feitos:
        detalhe = "; ".join(f"{f['pipeline']}: {f['de']} -> {f['para']}"
                            for f in feitos)
        try:
            cur.execute(
                "INSERT INTO dbo.etl_dependencia_evento "
                "(pipeline_name, data_referencia, tipo, detalhe) "
                "VALUES (?, ?, 'DATA_EQUALIZADA', ?)",
                (feitos[0]["pipeline"], data_ref,
                 f"malha {malha} ({quem}): {detalhe}"[:1000]))
        except Exception as e:
            # O evento é o RASTRO, não a operação: perdê-lo não desfaz o
            # recarimbo (que já está na transação), mas tem de aparecer no log.
            log.warning("[MALHA] evento DATA_EQUALIZADA não registrado: %s", e)
    return feitos


def _msg_bloqueio(bloqueios: dict, data_ref: str) -> str:
    """Mensagem única do 422 e do modal — um texto só, como a do ciclo da F8."""
    partes = []
    if bloqueios["em_aberto"]:
        quem = ", ".join(f"{b['pipeline']} ({b['status'].lower()}"
                         f", {b['data_referencia']})"
                         for b in bloqueios["em_aberto"][:5])
        partes.append(
            f"{len(bloqueios['em_aberto'])} pipeline(s) da malha ainda com "
            f"corrida em andamento: {quem}"
            + ("…" if len(bloqueios["em_aberto"]) > 5 else ""))
    if bloqueios["datas_divergentes"]:
        quem = ", ".join(f"{b['pipeline']} em {b['data_referencia']}"
                         for b in bloqueios["datas_divergentes"][:5])
        partes.append(
            f"{len(bloqueios['datas_divergentes'])} pipeline(s) executaram "
            f"neste ciclo com data de referência diferente de {data_ref}: "
            f"{quem}" + ("…" if len(bloqueios["datas_divergentes"]) > 5 else ""))
    return ("A malha não pode começar: " + " · ".join(partes)
            + ". A malha só parte do zero — encerre as corridas em aberto e "
              "iguale a data de referência dos membros antes de disparar "
              "(Malha ▸ Republicar pipelines resolve o caso mais comum: "
              "dependente que ainda dispara por agenda).")


# ══════ A CORRIDA DE MALHA na API — docs/spec-malha-execucao.md, fase F3 ═════
#
# A porta 1 do §6.2: o disparo manual ABRE a corrida, na MESMA transação dos
# bloqueios e ANTES dos triggers do Airflow; o operador ENCERRA pela tela; a
# lista alimenta a navegação da F4; o rename CARIMBA e a exclusão CANCELA.
#
# Onde mora o SQL, e por quê a fronteira é esta:
#   • toda TRANSIÇÃO do ciclo (abrir, congelar snapshot, expirar, fechar) e
#     toda leitura que o MOTOR também faz vivem em `services/malha_corrida.py`,
#     que é o par exato de `dags/utils/malha_corrida.py` — o teste de paridade
#     compara os dois textos, e é ele que impede a API e o motor de discordarem
#     sobre o que é uma corrida;
#   • os dois statements daqui de baixo (`_SQL_CORRIDAS_DA_MALHA` e
#     `_SQL_CORRIDA_RENOMEAR`) são de TELA e de CADASTRO, e só existem nesta
#     árvore. Pô-los no módulo gêmeo criaria uma constante SEM PAR do outro
#     lado — exatamente a divergência silenciosa que a paridade existe para
#     pegar, com o agravante de parecer coberta.
#
# NADA aqui roda quando o portão do §11.1 está fechado, e a recusa é sempre
# "responder como antes desta fase", nunca 500.

# Quanto tempo o heartbeat da guardiã pode ter sem que ela conte como ausente.
# A guardiã roda a cada 5 min e carimba ao fim de todo ciclo que OPEROU a
# corrida: 15 min = três ciclos, a mesma folga do default de quiescência. Menos
# que isso faria um ciclo lento (banco ocupado às 3h) virar "motor antigo", e a
# API pararia de abrir corrida no meio da madrugada sem nada ter mudado.
HEARTBEAT_MINUTOS = 15

# `pipeline_name` do evento da corrida — a tabela de eventos é chaveada por
# pipeline e a corrida não é um pipeline. MESMA grafia do MARCADOR_CORRIDA da
# guardiã (`dags/etl_dependencia_guardia.py`): o painel da F4 resolve UM
# marcador, e duas grafias fariam metade dos eventos sumir da tela.
MARCADOR_CORRIDA = "#corrida:{}"

# As razões pelas quais a API NÃO opera a corrida. São nomes, e não um booleano,
# porque cada uma tem uma frase diferente no log de plantão — e nenhuma delas é
# erro para quem disparou: o disparo responde exatamente como antes da F3.
MOTIVO_INTERRUPTOR = "malha_corrida_desligada"
MOTIVO_SEM_085 = "migration_085_pendente"
MOTIVO_GUARDIA_AUSENTE = "guardia_sem_heartbeat"


def _corrida_operavel(cur, malha: str):
    """A API pode OPERAR a corrida de malha nesta request? `(bool, motivo)`.

    Quatro perguntas, nesta ordem:

      1. o interruptor `malha_corrida_ativa` (§11.2). Nasce em `0` na própria
         085 e só vai a `1` depois da F7 — é o gesto de rollback da spec
         inteira, e vem primeiro porque é absoluto;
      2. a 085 no banco;
      3. o `dags/` DEPLOYADO declara `malha_corrida_085`. **É a célula mais
         provável da matriz §11.1**: no `deploy.sh` a etapa 7 (`api/`) é
         automática e a etapa 5 (`dags/`) é padrão-NÃO, então a API nova sobe
         sozinha o tempo todo. Sem esta pergunta a API abriria corridas que o
         motor deployado não sabe vincular nem fechar: TODA corrida ficaria
         aberta até o teto e, enquanto isso, BLOQUEARIA o disparo — a API
         paralisando a malha com uma trava que o motor não sabe destravar;
      4. o heartbeat da guardiã é recente. O item (3) prova o que está no
         DISCO; só o heartbeat prova que a guardiã daquele disco está RODANDO
         e operando a corrida. DAG da guardiã pausada, worker fora do ar ou
         interruptor desligado só no worker produzem exatamente o mesmo estrago
         do motor antigo, e nenhum dos três aparece no arquivo.

    ⚠️ A recusa vale para a porta INTEIRA: sem os quatro, a API não abre, não
    expira e **também não recusa disparo por corrida aberta**. Recusar sem poder
    abrir nem expirar prenderia o operador a uma corrida que nada no ambiente
    sabe encerrar — o oposto do que a §11.1 pede. `POST .../encerrar` segue
    disponível de propósito: ele é a saída, e por isso não passa por aqui.
    """
    if not mc.corrida_ativa(cur):
        return False, MOTIVO_INTERRUPTOR
    if not mc.tabela_085_presente(cur):
        log.warning("[MALHA] migration 085 ausente — a corrida da malha '%s' "
                    "não é operada pela API; o disparo segue como antes", malha)
        return False, MOTIVO_SEM_085
    cap = rerun_svc.capacidade_dags(capacidade=rerun_svc.CAPACIDADE_CORRIDA)
    if cap != rerun_svc.CAP_OK:
        log.warning("[MALHA] dags/ deployado não declara '%s' (%s) — a API NÃO "
                    "abre corrida para a malha '%s': o motor no ar não saberia "
                    "fechá-la e ela bloquearia o disparo até o teto",
                    rerun_svc.CAPACIDADE_CORRIDA, cap, malha)
        return False, cap
    if not mc.heartbeat_guardia(cur, HEARTBEAT_MINUTOS)["recente"]:
        log.warning("[MALHA] guardiã sem heartbeat de corrida nos últimos %d "
                    "min — a API NÃO abre corrida para a malha '%s' (quem abre "
                    "sem quem fecha congela a malha)", HEARTBEAT_MINUTOS, malha)
        return False, MOTIVO_GUARDIA_AUSENTE
    return True, None


# Espelho `?` do `_SQL_EVENTO[(True, True)]` de dags/utils/dependencias.py — a
# MESMA chave de idempotência do `ux_dep_evento_corrida` (pipeline, data, tipo,
# corrida). O `ISNULL(..., -1)` dos dois lados não é decoração: em índice único
# do SQL Server dois NULLs são IGUAIS, mas `= NULL` nunca é verdadeiro em
# predicado — sem ele o INSERT passaria pelo NOT EXISTS e morreria no 2601 do
# índice, dentro da transação do chamador.
_SQL_EVENTO_CORRIDA = (
    "INSERT INTO dbo.etl_dependencia_evento "
    "(pipeline_name, data_referencia, tipo, detalhe, malha_execucao_id) "
    "SELECT ?, ?, ?, ?, ? "
    "WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_dependencia_evento "
    "WHERE pipeline_name=? AND data_referencia=? AND tipo=? "
    "AND ISNULL(malha_execucao_id, -1) = ISNULL(CAST(? AS BIGINT), -1))")
_SQL_EVENTO_SEM_CORRIDA = (
    "INSERT INTO dbo.etl_dependencia_evento "
    "(pipeline_name, data_referencia, tipo, detalhe) "
    "SELECT ?, ?, ?, ? "
    "WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_dependencia_evento "
    "WHERE pipeline_name=? AND data_referencia=? AND tipo=?)")
# `notificar=False` (F7): o evento nasce JÁ carimbado com `notificado_em` e
# nunca entra na fila do Teams (`eventos_nao_notificados` filtra por
# `notificado_em IS NULL`) — mas existe, e vive no painel. É a MESMA técnica do
# `gravar_evento` do motor, pela mesma razão: "o evento e o painel são sempre;
# o card é opt-in". Carimbar no NASCIMENTO (em vez de filtrar na fila) é o que
# impede o evento de entupir o lote por dois dias.
_SQL_EVENTO_CORRIDA_MUDO = _SQL_EVENTO_CORRIDA.replace(
    "malha_execucao_id) SELECT ?, ?, ?, ?, ? ",
    "malha_execucao_id, notificado_em) SELECT ?, ?, ?, ?, ?, GETDATE() ")


def _evento_da_corrida(cur, corrida: dict, tipo: str, detalhe: str,
                       notificar: bool = True) -> bool:
    """Grava o evento do ciclo (`MALHA_CANCELADA`, `MALHA_ABORTADA`) na
    transação de quem chama. True = evento novo.

    O CHAMADOR commita — evento e fechamento no MESMO commit (Decisão 20). A
    ordem antiga (fechar, commitar, e só então o evento) perdia o card PARA
    SEMPRE se a falha caísse entre os dois commits, porque a detecção consome a
    própria fonte: aqui a detecção é `fechada_em IS NULL`, e é ela que o
    fechamento consome.

    Reusar `etl_dependencia_evento` é o que faz o alerta chegar ao Teams **sem
    uma linha de mudança na guardiã** — ela já drena todo evento sem
    `notificado_em`, e os sete tipos da corrida já estão em `ds_teams.ESTILO`.

    Nunca levanta: o evento é o RASTRO do gesto, não o gesto. Perdê-lo não pode
    desfazer um encerramento que o operador já mandou fazer.
    """
    texto = (str(detalhe)[:1000] if detalhe is not None else None)
    base = (MARCADOR_CORRIDA.format(corrida["id"]), corrida["data_referencia"],
            tipo)
    cid = int(corrida["id"])
    try:
        cur.execute(_SQL_EVENTO_CORRIDA if notificar
                    else _SQL_EVENTO_CORRIDA_MUDO,
                    base + (texto, cid) + base + (cid,))
        return (cur.rowcount or 0) == 1
    except Exception as e:  # noqa: BLE001
        # Banco com as tabelas da 085 mas sem a coluna no evento (migration
        # aplicada pela metade): grava na forma antiga, sem a corrida. É a mesma
        # degradação do `gravar_evento` do motor — o alerta sai, sem o vínculo.
        if "malha_execucao_id" not in str(e):
            log.warning("[MALHA] evento %s da corrida #%s não gravado: %s",
                        tipo, corrida["id"], e)
            return False
        try:
            cur.execute(_SQL_EVENTO_SEM_CORRIDA, base + (texto,) + base)
            log.warning("[MALHA] evento %s gravado SEM o vínculo da corrida "
                        "#%s (banco sem a coluna da 085)", tipo, corrida["id"])
            return (cur.rowcount or 0) == 1
        except Exception as e2:  # noqa: BLE001
            log.warning("[MALHA] evento %s da corrida #%s não gravado: %s",
                        tipo, corrida["id"], e2)
            return False


def _corrida_publica(c: dict) -> dict:
    """A corrida no formato da tela — datas em texto, e só o que a F4 consome.

    Projeção EXPLÍCITA (nunca `dict(c)`): o dicionário do módulo carrega colunas
    de auditoria e de efeito colateral (`falha_vista_em`, `atraso_visto_em`) que
    são memória interna do ciclo, e publicá-las convidaria o front a derivar
    estado delas — que é justamente o que a §5.2 proíbe.
    """
    return {
        "id": c["id"],
        "malha_name": c["malha_name"],
        "data_referencia": _fmt_dia(c["data_referencia"]),
        # `sequencia` é o rótulo humano ("2ª corrida de 04/08") e é o que faz o
        # ◀ ▶ da F4 distinguir DUAS corridas do mesmo ODATE. Identidade é o
        # `id`, sempre — nunca o par (malha, data), que é o beco de onde esta
        # spec inteira sai.
        "sequencia": c["sequencia"],
        "status": c["status"],
        "aberta_em": _fmt_dt(c["aberta_em"]),
        "fechada_em": _fmt_dt(c["fechada_em"]),
        "fechada_por": c["fechada_por"],
        "origem": c["origem"],
        "aberta_por": c["aberta_por"],
        "ancora_pipeline": c["ancora_pipeline"],
        "modo_fechamento": c["modo_fechamento"],
        "teto_em": _fmt_dt(c["teto_em"]),
        "tentativas": c["tentativas"],
        "reaberta_em": _fmt_dt(c["reaberta_em"]),
        "motivo": c["motivo"],
    }


def _rotulo_corrida(c: dict) -> str:
    """O nome HUMANO da corrida (Decisão 74): `corrida de 04/08`, e só a partir
    da segunda do dia, `2ª corrida de 04/08`.

    O `#` fica de fora de propósito, e não por estilo: hoje três numerações
    diferentes disputam essa notação (`id`, `sequencia` e o `inicio:#12` de
    `aberta_por`), então `#12` numa malha diária lê-se como "12ª tentativa
    hoje". Mensagem de erro da API É interface — ela sai no toast da tela.
    """
    dia = _fmt_dia(c["data_referencia"])
    try:
        seq = int(c.get("sequencia") or 1)
    except (TypeError, ValueError):
        seq = 1                     # rótulo humano nunca derruba a resposta
    return f"corrida de {dia}" if seq <= 1 else f"{seq}ª corrida de {dia}"


# ── F8: o que a EDIÇÃO do desenho faz (e não faz) com o ciclo em voo ────────
#
# §6.9/#16 e #17. O snapshot da corrida CONGELA membros, `conta_para_fim` e
# `modo_fechamento` na abertura: qualquer edição vale da PRÓXIMA corrida em
# diante. A regra já existia; o que faltava era a tela DIZER isso — sem a frase,
# o operador adiciona um membro às 3h, olha o painel, não o vê no denominador e
# conclui que a tela está quebrada (ou, pior, que o pipeline não vai rodar).
#
# **Avisa, nunca recusa.** Recusar seria transformar "esta malha tem ciclo em
# voo" em "esta malha não pode ser editada por horas" — e a edição é legítima:
# ela é o preparo do ciclo seguinte, que muitas vezes é o motivo pelo qual o
# operador está acordado.
_AVISOS_CICLO_EM_VOO = {
    "inativar":
        "a malha foi inativada, mas a {rotulo} continua até fechar sozinha — "
        "nenhuma execução é interrompida, e nenhum ciclo NOVO abre. Para "
        "encerrar o ciclo agora, use Encerrar corrida (com motivo)",
    "membro_add":
        "a {rotulo} está em andamento e o quadro de membros dela foi congelado "
        "na abertura: o pipeline entra na malha agora, mas só passa a contar a "
        "partir do próximo ciclo",
    "membro_remove":
        "a {rotulo} está em andamento e o quadro de membros dela foi congelado "
        "na abertura: o pipeline sai da malha agora, mas continua contando "
        "neste ciclo até ele fechar",
    "republicar":
        "a {rotulo} está em andamento: os membros que ainda não partiram vão "
        "rodar com a versão NOVA da DAG e os que já partiram terminam com a "
        "anterior — este ciclo fica metade com cada uma. Republicar depois de o "
        "ciclo fechar evita isso",
}


def _aviso_ciclo_em_voo(cur, malha: str, gesto: str):
    """A frase do §6.9/#16-#17 quando — e SÓ quando — há corrida aberta.

    `None` é a resposta normal (malha sem ciclo em voo, banco sem a 085,
    leitura indisponível): a chave nem entra na resposta, e a tela fica como
    era antes desta fase. Um aviso inventado por leitura que falhou seria pior
    que aviso nenhum.

    Não passa pelo portão do §11.1 de propósito — ele governa quem OPERA a
    corrida, e isto aqui só LÊ. Uma corrida aberta antes de alguém desligar o
    interruptor continua em voo, e continuar avisando sobre ela é a verdade.
    """
    try:
        if not mc.tabela_085_presente(cur):
            return None
        c = mc.corrida_aberta(cur, malha)
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("[MALHA] ciclo em voo de '%s' indisponível (%s) — gesto "
                    "sem aviso", malha, e)
        return None
    if c is None:
        return None
    modelo = _AVISOS_CICLO_EM_VOO.get(gesto)
    return modelo.format(rotulo=_rotulo_corrida(c)) if modelo else None


def _msg_corrida_aberta(c: dict) -> str:
    """O 422 da porta 1 — o que aconteceu, por que, e o que a pessoa faz agora.

    Nomeia a corrida (§6.9/#14) e aponta a saída (§6.8). A última frase existe
    porque é a dúvida que trava o operador às 3h: encerrar a corrida **não**
    mata processo nenhum, e sem dizer isso o botão não é usado.
    """
    rotulo = _rotulo_corrida(c)
    return (
        f"A malha '{c['malha_name']}' já tem a {rotulo} em andamento "
        f"desde {_fmt_dt(c['aberta_em'])}. Disparar agora abriria um SEGUNDO "
        f"ciclo por cima do que está em voo — é assim que a mesma malha termina "
        f"metade num dia e metade em outro. Encerre a {rotulo} "
        f"(Malha ▸ Encerrar corrida, com motivo) e dispare de novo; encerrar "
        f"fecha o CICLO e não interrompe pipeline nenhum — o que já está "
        f"rodando continua rodando.")


def _expirar_na_porta(cur, corrida: dict, quem: str) -> bool:
    """Decisão 29 — expiração PREGUIÇOSA: a corrida presa com o teto vencido
    expira AQUI, na mesma transação, e o disparo prossegue. True = expirou.

    Por que na porta e não só na guardiã: com `teto_horas = 24` numa malha
    diária, a corrida de 01:00 vence às 01:00 do dia seguinte. Se a raiz roda às
    01:00:00 e a guardiã só passa às 01:03, a malha **pula o dia inteiro** — e
    no dia seguinte a mesma moeda é jogada de novo. Pior: um operador travado às
    3h porque a guardiã morreu não tem como esperar por ela. Nunca depender de
    outro processo ter passado.

    **Decisão 25 é conferida antes**: o teto NUNCA fecha corrida com membro
    vivo. Aqui isso vale duas vezes — o disparo só chega neste ponto com
    `_bloqueios_do_ciclo` vazio (nenhum membro da malha `EXECUTANDO` ou
    `AGUARDANDO_DEPENDENCIA`, em data nenhuma), e ainda assim se pergunta ao
    `estado()`, que é a autoridade do §6.4. A segunda pergunta não é redundância
    cosmética: o bloqueio olha `etl_malha_pipeline` (o desenho de AGORA) e o
    `estado()` olha o SNAPSHOT congelado na abertura — o membro removido da
    malha no meio do ciclo existe só no segundo.

    ⚠️ O teto é lido por `relogios()` e o fechamento é um `UPDATE ... WHERE id =
    ? AND fechada_em IS NULL` com `rowcount` de árbitro; a Decisão 29 escreve os
    dois num statement só. São dois aqui porque o SQL da corrida mora no módulo
    gêmeo (e um SQL só desta árvore seria uma constante sem par do outro lado).
    **A F7 fechou a janela que essa composição abria**: `teto_creditado_min`
    passou a ser escrito (o crédito de hold reprojeta `teto_em`), então entre a
    leitura e o `UPDATE` o teto pode ANDAR. A guarda é o `hold_da_malha` abaixo —
    enquanto houver nó segurado nada expira, e o crédito só acontece no
    `soltar`, que limpa a retenção no MESMO commit. A corrida cujo teto acabou
    de andar tem, por construção, um hold recém-solto: ou a porta viu a
    retenção e não expirou, ou o crédito já estava aplicado quando ela leu.
    """
    # HOLD suspende os relógios (Decisão 30) — e aqui a guarda vale duas vezes:
    # a porta é a ÚNICA que expira sem passar pela guardiã, então sem ela um
    # Aguarde segurado às 22h faria o disparo das 01:00 expirar a corrida que o
    # próprio operador travou de propósito. Vem ANTES do `relogios()` porque é
    # mais barata e responde sozinha.
    hold = mc.hold_da_malha(cur, corrida["malha_name"])
    if hold["retido"]:
        log.info("[MALHA] corrida #%s da malha '%s' com %d no(s) SEGURADO(s) — "
                 "o teto nao corre e ela NAO expira na porta (Decisão 30)",
                 corrida["id"], corrida["malha_name"], hold["nos"])
        return False
    # Só `teto_vencido` é consumido: os outros dois relógios (carência de
    # partida e quiescência) decidem desfechos que são do FECHADOR — a guardiã,
    # sempre (Decisão 19). Os parâmetros vão nos padrões do módulo porque as
    # respostas correspondentes são descartadas aqui.
    if not mc.relogios(cur, corrida, mc.CARENCIA_PARTIDA_PADRAO,
                       mc.QUIESCENCIA_MIN_PADRAO).get("teto_vencido"):
        return False
    est = mc.estado(cur, corrida)
    # ⚠️ `estado()` degrada LARGA: se a consulta não puder ser feita (lock
    # timeout em `etl_pipeline_execucao` às 3h, deadlock, coluna ausente) ela
    # loga e devolve os BALDES VAZIOS. Vazio lido como "ninguém vivo" inverteria
    # a Decisão 25 no pior momento possível: a corrida com um pipeline
    # `EXECUTANDO` sairia EXPIRADA e o disparo partiria por cima dele — e as
    # linhas que terminassem depois carregariam id de corrida FECHADA. É a
    # única pergunta que enxerga o membro REMOVIDO da malha no meio do ciclo
    # (o bloqueio olha `etl_malha_pipeline`, o desenho de AGORA), então perdê-la
    # em silêncio é perder a trava inteira.
    #
    # `membros` é o discriminador honesto: toda corrida nasce com o snapshot
    # congelado no mesmo commit (§6.2), logo `membros = 0` só acontece quando a
    # leitura NÃO respondeu. Não expirar custa um ciclo de 5 min da guardiã —
    # ou o botão Encerrar corrida, que existe justamente para isto (§6.8). É a
    # mesma política do `ERRO_CONSULTA`, e a que `ha_no_retido` já aplica no
    # módulo gêmeo: "não consegui perguntar" NUNCA vira "pode fechar".
    if int(est.get("membros") or 0) == 0:
        log.warning("[MALHA] corrida #%s da malha '%s' com teto vencido, mas o "
                    "estado do snapshot não pôde ser lido — NÃO expirada na "
                    "porta (a guardiã ou o botão Encerrar corrida resolvem)",
                    corrida["id"], corrida["malha_name"])
        return False
    vivos = est.get("vivos") or []
    if vivos:
        log.warning("[MALHA] corrida #%s da malha '%s' com teto vencido mas "
                    "%d membro(s) ainda vivo(s) (%s) — NÃO expirada na porta",
                    corrida["id"], corrida["malha_name"], len(vivos),
                    ", ".join(vivos[:5]))
        return False
    detalhe = (f"teto vencido em {_fmt_dt(corrida['teto_em'])} e nenhum membro "
               f"vivo — corrida expirada na porta do disparo por {quem}")
    if not mc.fechar_corrida(cur, corrida["id"], "EXPIRADA",
                             f"manual:{quem}", motivo=detalhe):
        return False        # outra ponta fechou primeiro — resposta, não erro
    _evento_da_corrida(cur, corrida, "MALHA_EXPIRADA", detalhe)
    log.warning("[MALHA] corrida #%s da malha '%s' EXPIRADA na porta do "
                "disparo (%s)", corrida["id"], corrida["malha_name"], detalhe)
    return True


def _agora_do_banco(cur):
    """O relógio do BANCO (Decisão 10) — nenhuma conta de tempo em Python.

    No dev o SQL Server está ~3h à frente do container da API (medido, não
    suposto), e um ODATE calculado sobre `datetime.now()` do processo carimbaria
    o dia errado em toda hora vizinha da virada. Falha de leitura cai em
    `_agora()`, que é o comportamento anterior a esta fase — nunca uma exceção.
    """
    try:
        cur.execute("SELECT GETDATE()")
        row = cur.fetchone()
        if row and row[0] is not None:
            return row[0]
    except Exception as e:  # noqa: BLE001
        log.debug("[MALHA] relógio do banco indisponível: %s", e)
    return _agora()


# Membros da malha pela grafia OFICIAL (o JOIN faz o pipeline excluído sumir) —
# o mesmo SELECT do painel, de propósito: o denominador do card e o alvo do
# `conta_para_fim` têm de vir da mesma lista.
_SQL_MEMBROS_DA_MALHA = (
    "SELECT p.pipeline_name FROM dbo.etl_malha_pipeline mp "
    "JOIN dbo.etl_pipeline p ON p.pipeline_name = mp.pipeline_name "
    "WHERE mp.malha_name = ?")


def _abrir_corrida_do_disparo(cur, malha: str, nos_l: list, arestas_l: list,
                              data_ref, quem: str, no_inicio):
    """Porta 1 do §6.2 — abre a corrida do disparo manual, com o snapshot no
    MESMO commit. Devolve o dict da corrida, ou None quando não deu para abrir.

    O ODATE é o `data_ref` **que este disparo vai carimbar**, e não o
    `odate_da_abertura` da Decisão 18. ⚠️ Divergência deliberada, e o motivo é
    de correção: o disparo manda `data_referencia` no `conf` de toda raiz, e uma
    corrida nascida com outro ODATE classificaria TODAS as suas linhas como
    `fora_do_odate` (§6.4) — a corrida nunca fecharia, o card diria 0 de N com a
    malha inteira verde embaixo, e o teto a mataria 24h depois. A Decisão 18
    governa as portas AUTOMÁTICAS, cujo insumo é um instante do banco e onde não
    existe data pedida por gente; aqui o rótulo é escolha do operador (ou o
    default da tela, que é a virada GLOBAL de propósito — o `/execucao` usa a
    mesma régua, e divergir dela devolveria o defeito "painel mostra D, disparo
    carimba D+1"). Alinhar as duas réguas é mudar o `conf` do disparo, que é
    assunto do §7/F5, não desta fase.

    `aberta_em` fica `None` = `SYSDATETIME()` do BANCO: aqui não há linha âncora
    para recuar (nada partiu ainda — os triggers vêm depois), e o recuo das
    portas 2 e 3 existe justamente porque lá a corrida nasce até um ciclo depois
    do trabalho. Nenhum `datetime.now()` do processo: no dev o banco está ~3h à
    frente da API, e um `aberta_em` do relógio errado faria o recorte de tempo
    da Decisão 23 varrer três horas de linhas alheias — ou nenhuma.
    """
    fins = [n["id"] for n in nos_l if n["tipo"] == "fim"]
    conta_fim = None
    if fins:
        # `conta_para_fim` = o upstream EXPANDIDO do nó Fim, pela única
        # autoridade da expansão (a mesma que a guardiã usa do outro lado).
        # Conjunto VAZIO é diferente de None e não é erro (§6.9/#2): existe um
        # Fim e ele não alcança ninguém — o fechamento continua exigindo nenhum
        # membro vivo, e o painel lista os `fora_do_fim` nominalmente.
        expansao = malha_nos_svc.expandir(nos_l, arestas_l)
        alvo: set = set()
        for no_id in fins:
            alvo |= set(expansao["nos"].get(no_id, {}).get("upstream", ()))
        # A lista de membros só é lida quando existe Fim — 3 das 4 malhas do dev
        # não têm, e uma consulta a mais no caminho quente do disparo por nada é
        # o tipo de custo que ninguém revisa depois.
        cur.execute(_SQL_MEMBROS_DA_MALHA, (malha,))
        membros = {str(r[0]).strip() for r in cur.fetchall()}
        conta_fim = sorted(alvo & membros)
    corrida = mc.abrir_corrida(
        cur, malha, data_ref, "manual",
        aberta_por=f"manual:{quem}",
        no_inicio=no_inicio, no_fim=(fins[0] if fins else None),
        # Derivado do DESENHO e congelado com ele (§6.9/#1): 3 das 4 malhas do
        # dev não têm nó Fim e fecham por quiescência. Nunca é configurado à mão.
        modo_fechamento=("fim" if fins else "quiescencia"))
    if corrida is None:
        return None
    if not corrida["nova"]:
        # INSERT-first, nunca SELECT-then-INSERT (Decisão 14): a conferência
        # "não há corrida aberta" e o INSERT são dois instantes, e a guardiã
        # pode ter aberto entre eles. `nova=False` significa que ADERIMOS a um
        # ciclo alheio — e disparar as raízes por cima de um ciclo que acabou de
        # nascer é o mesmo estrago que o 422 recusa quando a corrida já estava
        # lá. Quem chama devolve o 422 e NÃO congela snapshot: o dono do
        # snapshot é quem abriu.
        return corrida
    mc.congelar_snapshot(cur, corrida["id"], malha, conta_para_fim=conta_fim)
    return corrida


def _abortar_corrida_do_disparo(corrida: dict, quem: str, falhas: list):
    """§6.9/#4 — TODAS as raízes falharam no trigger: a corrida sai `ABORTADA`
    **numa SEGUNDA conexão**, na mesma resposta. Devolve a corrida RELIDA do
    banco quando abortou, ou None.

    Relê em vez de remendar o dict em memória porque `status` e `fechada_em`
    são a MESMA informação no modelo (`CK_mexec_coerente`), e devolver
    `status='ABORTADA'` com `fechada_em: null` seria publicar um estado que o
    banco recusaria — a tela leria "fechada" de um campo e "aberta" do outro.

    A segunda conexão não é preciosismo: a transação do disparo já foi
    **commitada** quando os triggers rodam (o banco fecha antes das chamadas ao
    Airflow, para que uma rede lenta não segure conexão de pool). Sem isto, o
    primeiro Airflow fora do ar deixaria uma corrida ABERTA que nada originou —
    ela ocuparia o slot do índice filtrado, o próximo disparo seria recusado por
    uma corrida FANTASMA e a malha ficaria congelada até o teto de 24h.

    Nunca levanta: a resposta do disparo já foi construída e as falhas já estão
    nela. Se o aborto não passar, quem destrava é o teto ou o botão de encerrar —
    e o log diz nominalmente qual dos dois vai ser preciso.
    """
    conn2 = None
    try:
        conn2 = get_db_conn(); cur2 = conn2.cursor()
        nomes = ", ".join(str(f.get("pipeline")) for f in falhas[:5])
        detalhe = (f"nenhuma das {len(falhas)} raiz(es) partiu — o Airflow "
                   f"recusou todas ({nomes}); ciclo abortado na resposta do "
                   f"disparo de {quem}")
        if not mc.fechar_corrida(cur2, corrida["id"], "ABORTADA",
                                 f"manual:{quem}", motivo=detalhe):
            # Outra ponta já fechou (a guardiã pelo piso de partida, ou o
            # operador). O objetivo — não deixar corrida fantasma — está
            # cumprido do mesmo jeito.
            conn2.rollback()
            log.info("[MALHA] corrida #%s já estava fechada quando o disparo "
                     "tentou abortá-la", corrida["id"])
            return None
        _evento_da_corrida(cur2, corrida, "MALHA_ABORTADA", detalhe)
        conn2.commit()          # evento e fechamento no MESMO commit (D20)
        log.warning("[MALHA] corrida #%s da malha '%s' ABORTADA: %s",
                    corrida["id"], corrida["malha_name"], detalhe)
        return mc.corrida(cur2, corrida["id"])
    except Exception as e:  # noqa: BLE001 — o aborto não pode derrubar a resposta
        _fechar_silencioso(conn2); conn2 = None
        log.error("[MALHA] corrida #%s NÃO foi abortada (%s) — ela seguirá "
                  "ABERTA bloqueando o disparo até o teto ou até alguém "
                  "encerrá-la pela tela", corrida["id"], e)
        return None
    finally:
        if conn2 is not None:
            try:
                conn2.close()
            except Exception:
                pass


# §6.9/#13 — o rename faz INSERT do nome novo + DELETE do antigo (a FK da 070 é
# cascade de DELETE, não de UPDATE). Sem este carimbo a corrida aberta ficaria
# ÓRFÃ sob o nome antigo, ocupando o slot de `ux_malha_exec_aberta` para sempre,
# e o nome novo nasceria sem corrida: DUPLA ABERTURA por construção.
#
# Só a corrida ABERTA, como manda a spec. As fechadas ficam com o nome de
# quando aconteceram — é histórico, e reescrever histórico por causa de um
# cadastro é o oposto do que a 076 decidiu quando derrubou a FK do evento. O
# preço é conhecido e aceito: o `GET /corridas` do nome novo não mostra o que
# rodou sob o nome velho.
_SQL_CORRIDA_RENOMEAR = (
    "UPDATE dbo.etl_malha_execucao SET malha_name = ?, "
    "atualizado_em = SYSDATETIME() "
    "WHERE malha_name = ? AND fechada_em IS NULL")


def _carimbar_corrida_no_rename(cur, conn, de: str, para: str) -> int:
    """Leva a corrida ABERTA para o nome novo, na MESMA transação do rename.
    Devolve quantas linhas carimbou.

    Sem a 085 não há corrida nenhuma: degrada com log e devolve 0 — o rename é
    gesto de cadastro e não pode virar 503 por causa de uma migration que este
    banco talvez nunca vá receber.

    Violação de `ux_malha_exec_seq` (o nome de destino já teve corridas do mesmo
    ODATE e da mesma sequência, de uma malha homônima anterior) é recusa
    explícita, e não rollback mudo: renomear por cima disso deixaria a corrida
    órfã — que é exatamente o defeito que este carimbo existe para evitar.
    """
    if not mc.tabela_085_presente(cur):
        log.warning("[MALHA] migration 085 ausente — corrida da malha '%s' não "
                    "foi carimbada no rename para '%s'", de, para)
        return 0
    try:
        cur.execute(_SQL_CORRIDA_RENOMEAR, (para, de))
        return int(cur.rowcount or 0)
    except Exception as e:  # noqa: BLE001
        if mc.IX_SEQUENCIA in str(e):
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=422,
                detail=f"A malha '{de}' tem uma corrida em andamento e o nome "
                       f"'{para}' já tem histórico de corridas do mesmo dia com "
                       f"a mesma sequência — renomear agora deixaria a corrida "
                       f"órfã sob o nome antigo. Encerre a corrida em andamento "
                       f"(Malha ▸ Encerrar corrida) e renomeie em seguida.")
        if mc.IX_ABERTA in str(e):
            # O nome de destino já tem uma corrida ABERTA sem malha por trás —
            # a órfã que sobra quando um rename anterior aconteceu com a 085
            # ausente (o `return 0` degradado acima). O duplicado de `etl_malha`
            # não pega este caso: lá não há linha de cadastro nenhuma. Sem esta
            # frase o operador levava um 500 "Erro DB: ... 2601 ..." num gesto
            # de cadastro, e nada dizia onde está a corrida que trava o nome.
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=422,
                detail=f"O nome '{para}' já tem uma corrida em andamento sem "
                       f"malha por trás (ficou órfã de um rename anterior) e a "
                       f"malha '{de}' também tem a sua — duas corridas abertas "
                       f"com o mesmo nome é o que o modelo proíbe. Encerre a "
                       f"corrida aberta de '{para}' (Malha ▸ Encerrar corrida, "
                       f"pelo id que a lista de corridas mostra) e renomeie em "
                       f"seguida.")
        raise


# ⚠️ DIVERGÊNCIA DA SPEC, deliberada e reportada — §6.9/#14 ("malha excluída com
# corrida aberta: o DELETE cancela a corrida na mesma transação") NÃO tem onde
# ser implementada: **não existe `DELETE /malhas/{m}` neste código**. Levantado
# no repo inteiro, o único lugar que apaga uma linha de `etl_malha` é o rename
# do `PATCH` acima (INSERT do nome novo + DELETE do antigo), e ele está coberto
# pelo `_carimbar_corrida_no_rename` — a corrida acompanha o nome, não fica
# órfã, e o nome antigo fica livre. A tela de Malha também não oferece o gesto
# (não há `deleteMalha` no front).
#
# Escrever aqui um endpoint destrutivo novo só para pendurar nele o
# cancelamento seria entregar exclusão de malha — com o cascade da 070 levando
# membros, e o da 075 levando Início/Fim/Aguarde/Notificação — dentro de uma
# fase cujo entregável é a porta 1 do disparo. Quando o `DELETE` existir, a
# única linha que ele precisa é a mesma do encerramento: fechar como
# `CANCELADA` com `fechada_por`, na transação da exclusão, ANTES de apagar a
# malha — senão a corrida órfã presa no índice filtrado impede recriar uma
# malha com o mesmo nome.

# Projeção da listagem: a MESMA de `services/malha_corrida.py`, reusada em vez
# de redigitada. `_COLS`/`_como_dict` são derivados um do outro lá dentro, então
# reusá-los é o que impede a lista de degradar em silêncio no dia em que alguém
# acrescentar uma coluna à corrida. Alcançar um privado de outro módulo tem
# precedente literal neste arquivo (`deps_svc._exec_com_fallback_078`), e o
# risco aqui é menor: um `_COLS` que suma quebra o import na hora, não na tela.
_SQL_CORRIDAS_DA_MALHA = (
    "SELECT TOP (?) " + mc._COLS + " FROM dbo.etl_malha_execucao "
    "WHERE malha_name = ? "
    "ORDER BY data_referencia DESC, sequencia DESC, id DESC")
_SQL_CORRIDAS_DA_MALHA_NA_DATA = (
    "SELECT TOP (?) " + mc._COLS + " FROM dbo.etl_malha_execucao "
    "WHERE malha_name = ? AND data_referencia = ? "
    "ORDER BY sequencia DESC, id DESC")


async def _dags_existentes(nomes: list) -> dict:
    """{pipeline: True|False|None} — a DAG existe no Airflow?

    None = não deu para saber (Airflow fora do ar, timeout, nome inválido):
    quem consome NÃO afirma nada nesse caso. É a diferença entre "esta é a
    primeira publicação" e "não sei dizer" — e a tela só pode prometer o que
    o dado sustenta."""
    fora = {p: None for p in nomes}
    alvos = [p for p in nomes if _DAG_ID_RE.match(p or "")]
    if not alvos:
        return fora

    # Teto de chamadas simultâneas: malha grande não pode virar uma rajada de
    # centenas de GETs no webserver do Airflow, que é o mesmo que serve a UI
    # dos plantonistas.
    porta = asyncio.Semaphore(8)

    async def _um(client, pname):
        try:
            async with porta:
                r = await client.get(f"/api/v1/dags/{pname}")
            if r.status_code == 404:
                return pname, False
            if r.is_success:
                return pname, True
        except Exception as e:      # noqa: BLE001 — rede/timeout
            log.debug("[MALHA] consulta da DAG %s no Airflow: %s", pname, e)
        return pname, None

    try:
        async with get_airflow_client() as client:
            pares = await asyncio.gather(*[_um(client, p) for p in alvos])
        fora.update(dict(pares))
    except Exception as e:          # noqa: BLE001 — cliente indisponível
        log.warning("[MALHA] Airflow indisponível ao conferir as DAGs: %s", e)
    return fora


def _marcar_para_regeneracao(pipelines: list) -> None:
    """dag_criada=0 nos alvos — a MESMA marcação do "Publicar DAGs" do Admin,
    restrita ao escopo da malha. Um UPDATE por nome (o lote é de poucas
    dezenas) para não montar lista de placeholders."""
    if not pipelines:
        return
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        for nome in pipelines:
            cur.execute(
                "UPDATE dbo.etl_pipeline SET dag_criada = 0, updated_at = GETDATE() "
                "WHERE pipeline_name = ?", (nome,))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao liberar os pipelines para regeneração: {e}")


def _desmarcar_regeneracao(pipelines: list) -> None:
    """Desfaz a marcação quando o disparo NÃO aconteceu — só para quem estava
    publicado (dag_criada=1); quem já era pendente continua pendente. Deixar
    a marcação de pé anunciaria "DAG não publicada" para DAG viva, sem
    ninguém a caminho para republicá-la. Best-effort: falhar aqui não pode
    substituir o erro original do disparo."""
    if not pipelines:
        return
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        for nome in pipelines:
            cur.execute(
                "UPDATE dbo.etl_pipeline SET dag_criada = 1 "
                "WHERE pipeline_name = ?", (nome,))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.warning("[MALHA] falha ao desfazer a marcação de %s: %s",
                    ", ".join(pipelines), e)
        _fechar_silencioso(conn)


@router.post("/malhas/{malha_name}/republicar", tags=["malhas"])
async def republicar_malha(malha_name: str, body: dict = Body(default={}),
                           auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Republica as DAGs de TODOS os pipelines membros da malha.

    Mudar o desenho da malha (aresta nova, Aguarde, agendamento do Início)
    grava a dependência no banco na hora, mas a DAG que o Airflow executa
    continua sendo a versão ANTERIOR até ser regerada — é o que o carimbo
    dag_config_pendente_em (073) anuncia pipeline a pipeline. Este endpoint é
    o "Publicar nova versão" da tela Pipelines aplicado à malha inteira, para
    o operador não ter de caçar os membros um a um depois de montar.

    NENHUM executor novo (o mesmo princípio do disparo manual): marca os
    membros ATIVOS como pendentes (dag_criada=0, a marcação do "Publicar DAGs"
    do Admin restrita ao escopo da malha) e dispara UMA execução da
    etl_dag_factory com a lista deles em `conf["pipelines"]` — o mesmo caminho
    do "Publicar nova versão" por pipeline, que já mandava
    `conf["pipeline_name"]`. A factory regenera com o cadastro atual
    (dependências incluídas) e, ao concluir cada arquivo, zera o carimbo da
    publicação pendente.

    A marcação é feita AQUI de propósito, mesmo a factory nova refazendo-a: um
    deploy que atualize `api/` e adie `dags/` (o deploy.sh pergunta separado)
    deixaria a factory antiga ignorar `conf["pipelines"]`, gerar um lote vazio
    e fechar SUCCESS — verde perfeito para um gesto que não regenerou nada.
    Se o disparo falhar, a marcação é desfeita para quem estava publicado.

    UMA execução, não uma por membro: disparada com um alvo só, a factory gera
    TODOS os pendentes e reprova o run se o alvo pedido não entrar no lote —
    N runs concorrentes pelo mesmo lote produziriam FAILED de corrida no log,
    sem nenhuma DAG a mais ou a menos.

    Efeito colateral DITO, nunca escondido: pipelines pendentes de fora desta
    malha entram no mesmo lote (é o gerador de sempre, o botão por pipeline já
    faz isso) — o dry_run conta quantos são e o modal avisa antes. Falha de um
    pendente de terceiro vira AVISO no run, não erro: o run da malha só fica
    vermelho pelo que é dela (provado ao vivo no dev, onde um pipeline sem
    etapas alheio à malha reprovava o run inteiro).

    Pipeline INATIVO não entra: a sp_etl_pipelines_pendentes_criar filtra
    active=1, e é a mesma recusa (409) do botão por pipeline. Vem na resposta
    como `ignorados`, com o motivo — nunca sumindo em silêncio.

    Depois do run, o reconciliador confere CADA membro no Airflow (fila
    etl_dag_pendente): quem não tinha DAG entra como ativação (a DAG nasce
    pausada), quem já tinha entra em modo VERIFICAÇÃO (migration 080) — sem
    notificar sucesso, só para cobrar erro de importação. Sem essa conferência,
    um arquivo que o Airflow não consegue importar deixa a versão ANTERIOR
    rodando com a tela dizendo "publicado e em dia".

    Body: {"dry_run"?: bool}. dry_run devolve o que SERÁ republicado (membros,
    ignorados, avisos, o total de pendentes de fora e, por membro,
    `dag_no_airflow`) sem escrever nada. Permissão: acao_executar, a mesma do
    publicar/disparar.
    """
    dry_run = bool(body.get("dry_run"))
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        tem_073 = _coluna_073(cur)
        cur.execute(
            "SELECT p.pipeline_name, CAST(p.active AS INT), "
            "CAST(ISNULL(p.dag_criada, 0) AS INT)"
            + (", p.dag_config_pendente_em" if tem_073 else "") +
            " FROM dbo.etl_malha_pipeline mp "
            "JOIN dbo.etl_pipeline p ON p.pipeline_name = mp.pipeline_name "
            "WHERE mp.malha_name = ? ORDER BY p.pipeline_name",
            (malha,))
        membros = []
        for r in cur.fetchall():
            membros.append({"pipeline": r[0], "active": int(r[1] or 0),
                            "dag_criada": int(r[2] or 0),
                            "publicacao_pendente": (r[3] is not None) if tem_073 else None})
        if not membros:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=422,
                detail=f"A malha '{malha}' não tem pipelines vinculados — "
                       "não há o que republicar.")

        alvos, ignorados = [], []
        for m in membros:
            if m["active"] == 0:
                ignorados.append({
                    "pipeline": m["pipeline"],
                    "motivo": "pipeline inativo — o gerador de DAGs só "
                              "considera pipelines ativos; ative-o e "
                              "republique para que ele receba os vínculos"})
            elif not _DAG_ID_RE.match(m["pipeline"]):
                ignorados.append({
                    "pipeline": m["pipeline"],
                    "motivo": "o nome do pipeline não é um dag_id válido"})
            else:
                alvos.append(m)
        if not alvos:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=422,
                detail=f"Nenhum pipeline da malha '{malha}' pode ser "
                       "republicado: todos os membros estão inativos (o "
                       "gerador de DAGs só considera pipelines ativos).")

        avisos: list = []
        # Sem a 067 a factory cai no CSV legado: a DAG sai publicada, mas as
        # ligações desenhadas na malha podem não estar nela — o motivo pelo
        # qual o operador clicou no botão. Dito ANTES do gesto.
        if not _tabela_067(cur):
            avisos.append({
                "no": None, "nivel": "forte", "mensagem":
                "migration 067 pendente neste banco — as DAGs serão regeradas "
                "sem a tabela de dependências (as ligações da malha podem não "
                "entrar na nova versão)"})
        # Pendentes de FORA da malha: a factory processa o lote inteiro de
        # pendentes, não só o escopo pedido (é assim desde sempre, inclusive
        # no botão por pipeline). Contar e dizer é a única forma honesta.
        cur.execute(
            "SELECT COUNT(*) FROM dbo.etl_pipeline p "
            "WHERE p.active = 1 AND ISNULL(p.dag_criada, 0) = 0 "
            "AND NOT EXISTS (SELECT 1 FROM dbo.etl_malha_pipeline mp "
            "                WHERE mp.malha_name = ? "
            "                  AND mp.pipeline_name = p.pipeline_name)",
            (malha,))
        row_f = cur.fetchone()
        pendentes_de_fora = int(row_f[0] or 0) if row_f else 0
        if pendentes_de_fora:
            avisos.append({
                "no": None, "nivel": "leve", "mensagem":
                (f"{pendentes_de_fora} pipeline(s) de fora desta malha também "
                 "estão pendentes de publicação e serão gerados na mesma "
                 "execução do gerador (comportamento normal da factory)")})
        # §6.9/#17 (F8) — republicar com ciclo em voo deixa metade dos membros
        # com código novo e metade com o anterior, dentro do MESMO ciclo. É
        # `forte` porque é um efeito que ninguém enxerga depois: as duas metades
        # rodam verdes, e a divergência só aparece no dado. Avisa e deixa
        # seguir: às 3h, republicar no meio do ciclo pode ser exatamente o
        # conserto que o operador precisa fazer.
        aviso_ciclo = _aviso_ciclo_em_voo(cur, malha, "republicar")
        if aviso_ciclo:
            avisos.append({"no": None, "nivel": "forte",
                           "mensagem": aviso_ciclo})

        # O banco fecha ANTES de falar com o Airflow (padrão do proxy): rede
        # lenta não pode segurar conexão de pool aberta.
        nomes = [m["pipeline"] for m in alvos]
        cur.close(); conn.close(); conn = None

        # Quem já tem DAG lá? A pergunta é do AIRFLOW, não do cadastro:
        # `dag_criada` fica 0 durante toda a regeneração (é assim que a factory
        # seleciona o lote), então usá-lo aqui anunciaria "primeira publicação"
        # para DAG que roda há meses sempre que houvesse um run em voo.
        existe_no_airflow = await _dags_existentes(nomes)
        sem_dag = [p for p in nomes if existe_no_airflow.get(p) is False]
        if sem_dag:
            avisos.append({
                "no": None, "nivel": "leve", "mensagem":
                (f"{len(sem_dag)} pipeline(s) ainda sem DAG no Airflow entram "
                 "nesta publicação como PRIMEIRA versão: "
                 + ", ".join(sem_dag[:5])
                 + ("…" if len(sem_dag) > 5 else ""))})

        if dry_run:
            for m in alvos:
                m["dag_no_airflow"] = existe_no_airflow.get(m["pipeline"])
            return {"malha": malha, "pipelines": alvos, "ignorados": ignorados,
                    "avisos": avisos, "pendentes_de_fora": pendentes_de_fora}

        quem = (str(auth.get("matricula") or "").strip() or "?")
        run_id = f"orquestra_malha_{int(time.time() * 1000)}"
        conf = {"pipelines": nomes,
                "escopo_rotulo": f"Malha {malha}",
                "requested_by": f"malha:{malha} ({quem})"}
        # A marcação AQUI é o que faz o gesto funcionar mesmo com a factory
        # ANTIGA no servidor (deploy que atualiza api/ e adia dags/ — o
        # deploy.sh pergunta separado): a factory antiga ignora
        # `conf["pipelines"]` e geraria um lote VAZIO, devolvendo SUCCESS sem
        # regenerar nada — verde perfeito para um gesto que não aconteceu. Com
        # os alvos já pendentes, ela os encontra pelo caminho de sempre. A
        # factory nova refaz a marcação (idempotente) e ainda isola terceiros.
        publicados = [m["pipeline"] for m in alvos if m["dag_criada"] == 1]
        _marcar_para_regeneracao(nomes)
        try:
            async with get_airflow_client() as client:
                r = await client.post(
                    f"/api/v1/dags/{FACTORY_DAG_ID}/dagRuns",
                    json={"dag_run_id": run_id, "conf": conf},
                    headers={"Content-Type": "application/json"})
                if not r.is_success:
                    raise HTTPException(
                        status_code=502,
                        detail=f"O Airflow recusou a publicação "
                               f"(HTTP {r.status_code}): {r.text[:200]}")
        except HTTPException:
            _desmarcar_regeneracao(publicados)
            raise
        except Exception as e:      # noqa: BLE001 — rede/timeout
            _desmarcar_regeneracao(publicados)
            raise HTTPException(status_code=502,
                                detail=f"Erro ao disparar o gerador de DAGs: {e}")

        # Fila do reconciliador para TODOS os alvos — o que muda é o papel:
        #  • sem DAG no Airflow (ou desconhecido): ATIVAÇÃO — a DAG nasce
        #    pausada e alguém precisa despausá-la e avisar;
        #  • com DAG: VERIFICAÇÃO (migration 080) — o estado no Airflow já
        #    está certo, mas ninguém conferiria se a versão NOVA é importável.
        #    Sem isso, um erro de carga deixa a DAG ANTERIOR rodando com a tela
        #    dizendo "publicado e em dia" (achado da revisão adversarial).
        for pname in nomes:
            verificar = existe_no_airflow.get(pname) is True
            await asyncio.to_thread(enqueue_dag_pendente, pname, False,
                                    auth.get("matricula"), run_id, verificar)

        log.info("[MALHA] republicação da malha '%s' por %s — %d pipeline(s), "
                 "%d ignorado(s), run=%s", malha, quem, len(alvos),
                 len(ignorados), run_id)
        return {"ok": True, "malha": malha, "dag_run_id": run_id,
                "republicados": nomes, "ignorados": ignorados,
                "avisos": avisos, "pendentes_de_fora": pendentes_de_fora}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.patch("/malhas/{malha_name}", tags=["malhas"])
def update_malha(malha_name: str, body: dict = Body(default={}),
                 _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Atualiza descricao/ativo/orientacao e/ou renomeia a malha.

    Renomear atualiza as DUAS tabelas na MESMA transação: a FK da 070 é
    cascade de DELETE, não de UPDATE — trocar o PK com filhas apontando para
    ele viola a FK em qualquer ordem de UPDATE simples. O caminho é criar a
    linha-mãe nova (preservando criado_em/criado_por), migrar as filhas e
    apagar a antiga (já sem filhas, o CASCADE não leva nada junto).

    orientacao (074): 'horizontal' | 'vertical' — outro valor é 422. Sem a
    coluna (deploy parcial), NÃO é 503: o precedente do arquivo para COLUNA
    opcional é o degrade suave (_ligar_dag_config_pendente / migration 073) —
    log + migration_074_pendente=True na resposta, e a tela avisa. O 503 fica
    reservado às TABELAS (070/067), sem as quais o recurso inteiro não existe.
    """
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        atual = _malha_oficial(cur, malha_name)
        if atual is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")

        tem_descricao = "descricao" in body
        descricao = (str(body.get("descricao") or "").strip() or None) if tem_descricao else None
        tem_ativo = "ativo" in body
        if tem_ativo:
            if body.get("ativo") not in (0, 1, True, False):
                _fechar_silencioso(conn)
                raise HTTPException(status_code=422, detail="ativo deve ser 0 ou 1")
            ativo = int(bool(body.get("ativo")))
        # Valida a orientação ANTES de qualquer escrita (um rename não pode ir
        # pela metade por causa de um valor inválido aqui). Caixa é tolerada na
        # entrada ('Vertical' vale) e o gravado é o canônico minúsculo — mesmo
        # espírito da colação CI do banco.
        tem_orientacao = "orientacao" in body
        if tem_orientacao:
            orientacao = str(body.get("orientacao") or "").strip().lower()
            if orientacao not in _ORIENTACOES:
                _fechar_silencioso(conn)
                raise HTTPException(
                    status_code=422,
                    detail="orientacao deve ser 'horizontal' ou 'vertical'")
        tem_074 = _coluna_074(cur)
        # F2 (081): virada da malha e a marca de equalização. `hora_virada`
        # aceita 'HH:MM' ou null (null = a malha segue a virada global). Valor
        # inválido é 422 ANTES de qualquer escrita — a mesma régua da
        # orientacao, e o oposto do D35 (que aceita NULL com aviso): aqui o
        # campo É a régua de data, e cair calado no global seria o bug.
        tem_virada = "hora_virada" in body
        hora_virada = None
        if tem_virada:
            # `_parse_hora_opcional` do register é tolerante por contrato (D35:
            # valor ruim vira NULL com aviso). Aqui NÃO pode ser: o campo É a
            # régua de data da malha, e cair calado na virada global mudaria o
            # ODATE de todos os membros sem ninguém pedir. Por isso a recusa.
            _avisos_hora: list = []
            hora_virada = _parse_hora_opcional("hora_virada",
                                               body.get("hora_virada"),
                                               _avisos_hora)
            if _avisos_hora:
                _fechar_silencioso(conn)
                raise HTTPException(
                    status_code=422,
                    detail=f"hora_virada inválida: '{body.get('hora_virada')}' "
                           "(use HH:MM, ou null para seguir a virada global)")
        tem_equalizar = "equalizar_data" in body
        equalizar_data = 0
        if tem_equalizar:
            if body.get("equalizar_data") not in (0, 1, True, False):
                _fechar_silencioso(conn)
                raise HTTPException(status_code=422,
                                    detail="equalizar_data deve ser 0 ou 1")
            equalizar_data = int(bool(body.get("equalizar_data")))
        # F7 (085): o LIMITE DE SEGURANÇA desta malha, em horas. `null` = segue
        # o global (`malha_teto_horas_padrao`, 24 por padrão) — e é o `null` que
        # apaga a barra da tela, porque o teto é anti-travamento e não SLA
        # (Decisão 61). Domínio conferido pelo MESMO `_inteiro_no_dominio` do
        # módulo da corrida: a API recusar 0 e o motor aceitar faria uma corrida
        # nascer com `teto_em = aberta_em`, isto é, EXPIRADA no ato de abrir.
        tem_teto = "teto_horas" in body
        teto_horas = None
        if tem_teto and body.get("teto_horas") is not None:
            teto_horas = mc._inteiro_no_dominio(body.get("teto_horas"),
                                                mc.TETO_HORAS_MIN,
                                                mc.TETO_HORAS_MAX)
            if teto_horas is None:
                _fechar_silencioso(conn)
                raise HTTPException(
                    status_code=422,
                    detail=(f"teto_horas inválido: '{body.get('teto_horas')}' "
                            f"(use um inteiro de {mc.TETO_HORAS_MIN} a "
                            f"{mc.TETO_HORAS_MAX} horas, ou null para seguir o "
                            f"limite global)"))
        tem_081 = _colunas_081(cur)

        novo_nome = (body.get("novo_nome") or "").strip()
        renomeada = False
        nome_antigo = atual
        corridas_renomeadas = 0
        if novo_nome and novo_nome != atual:
            if len(novo_nome) > 200:
                _fechar_silencioso(conn)
                raise HTTPException(status_code=422, detail="novo_nome excede 200 caracteres")
            if "/" in novo_nome or "\\" in novo_nome:
                # mesma regra da criação: nome com '/' fica inendereçável no path
                _fechar_silencioso(conn)
                raise HTTPException(status_code=422,
                                    detail="novo_nome não pode conter '/' nem '\\'")
            if novo_nome.casefold() == atual.casefold():
                # Só mudança de caixa: para a colação CI é o MESMO valor, então
                # o UPDATE direto não viola a FK — o insert/migra/apaga acima
                # estouraria o PK (a linha nova colidiria com a antiga).
                cur.execute(
                    "UPDATE dbo.etl_malha SET malha_name = ?, atualizado_em = SYSDATETIME() "
                    "WHERE malha_name = ?", (novo_nome, atual))
                cur.execute(
                    "UPDATE dbo.etl_malha_pipeline SET malha_name = ? WHERE malha_name = ?",
                    (novo_nome, atual))
            else:
                duplicada = _malha_oficial(cur, novo_nome)
                if duplicada is not None:
                    _fechar_silencioso(conn)
                    raise HTTPException(status_code=422,
                                        detail=f"Já existe uma malha com este nome: '{duplicada}'")
                # Com a 074, a orientação viaja junto no rename — a cópia por
                # lista explícita de colunas deixaria a linha nova cair no
                # DEFAULT 'horizontal' e a preferência salva se perderia.
                if tem_074:
                    cur.execute(
                        "INSERT INTO dbo.etl_malha "
                        "(malha_name, descricao, ativo, criado_em, criado_por, "
                        "atualizado_em, orientacao) "
                        "SELECT ?, descricao, ativo, criado_em, criado_por, "
                        "SYSDATETIME(), orientacao "
                        "FROM dbo.etl_malha WHERE malha_name = ?",
                        (novo_nome, atual))
                else:
                    cur.execute(
                        "INSERT INTO dbo.etl_malha "
                        "(malha_name, descricao, ativo, criado_em, criado_por, atualizado_em) "
                        "SELECT ?, descricao, ativo, criado_em, criado_por, SYSDATETIME() "
                        "FROM dbo.etl_malha WHERE malha_name = ?",
                        (novo_nome, atual))
                cur.execute(
                    "UPDATE dbo.etl_malha_pipeline SET malha_name = ? WHERE malha_name = ?",
                    (novo_nome, atual))
                cur.execute("DELETE FROM dbo.etl_malha WHERE malha_name = ?", (atual,))
            atual = novo_nome
            renomeada = True
            # §6.9/#13 — a corrida ABERTA acompanha o nome, na MESMA transação.
            # Sem isto ela ficaria órfã sob o nome antigo, ocupando o slot de
            # `ux_malha_exec_aberta` para sempre (o nome velho não existe mais
            # em etl_malha, então nada nem ninguém a encontraria para encerrar),
            # e o nome novo nasceria sem corrida: DUPLA ABERTURA por construção
            # — a próxima raiz abriria a corrida #2 por cima do ciclo em voo.
            corridas_renomeadas = _carimbar_corrida_no_rename(
                cur, conn, nome_antigo, atual)

        if tem_descricao:
            cur.execute(
                "UPDATE dbo.etl_malha SET descricao = ?, atualizado_em = SYSDATETIME() "
                "WHERE malha_name = ?", (descricao, atual))
        aviso_ciclo = None
        if tem_ativo:
            cur.execute(
                "UPDATE dbo.etl_malha SET ativo = ?, atualizado_em = SYSDATETIME() "
                "WHERE malha_name = ?", (ativo, atual))
            # §6.9/#8 — inativar NÃO mata o ciclo em voo: corrida já aberta
            # segue até fechar (órfã eterna é o pior resultado), e o que a
            # inativação impede é a PRÓXIMA abrir. A tela tem de dizer isso; do
            # contrário o operador inativa a malha achando que parou a
            # madrugada, e ela continua andando.
            if ativo == 0:
                aviso_ciclo = _aviso_ciclo_em_voo(cur, atual, "inativar")
        migration_074_pendente = False
        if tem_orientacao:
            if tem_074:
                cur.execute(
                    "UPDATE dbo.etl_malha SET orientacao = ?, atualizado_em = SYSDATETIME() "
                    "WHERE malha_name = ?", (orientacao, atual))
            else:
                # Degrade suave (ver docstring): a tela segue funcionando na
                # orientação escolhida; só a persistência espera a 074.
                migration_074_pendente = True
                log.warning("[MALHA] migration 074 ausente — orientacao da "
                            "malha '%s' não foi persistida", atual)

        # F2 da spec-malha-data-unica: a virada da MALHA é a régua de data do
        # ciclo — e ela SÓ vale se chegar a todos os membros, que é onde o
        # motor a lê. Gravar na malha sem compilar deixaria o campo decorativo,
        # com a corrida continuando partida (a doença da Carga_Vida).
        equalizados: list = []
        migration_081_pendente = False
        if tem_virada or tem_equalizar:
            if not tem_081:
                migration_081_pendente = True
                log.warning("[MALHA] migration 081 ausente — virada/equalização "
                            "da malha '%s' não foram persistidas", atual)
            else:
                if tem_virada:
                    cur.execute(
                        "UPDATE dbo.etl_malha SET hora_virada = ?, "
                        "atualizado_em = SYSDATETIME() WHERE malha_name = ?",
                        (hora_virada, atual))
                    equalizados = _compilar_virada(cur, atual, hora_virada)
                if tem_equalizar:
                    cur.execute(
                        "UPDATE dbo.etl_malha SET equalizar_data = ?, "
                        "atualizado_em = SYSDATETIME() WHERE malha_name = ?",
                        (equalizar_data, atual))

        # F7: o limite de segurança da malha. Vale da PRÓXIMA corrida em diante
        # — `teto_em` é congelado na abertura (§6.9/#16, o snapshot congela o
        # ciclo), e reprojetar o teto de um ciclo em voo mudaria a régua no meio
        # do jogo. A resposta diz isso ao operador em vez de deixá-lo descobrir.
        migration_085_pendente = False
        if tem_teto:
            if not mc.tabela_085_presente(cur):
                migration_085_pendente = True
                log.warning("[MALHA] migration 085 ausente — teto_horas da "
                            "malha '%s' não foi persistido", atual)
            else:
                cur.execute(
                    "UPDATE dbo.etl_malha SET teto_horas = ?, "
                    "atualizado_em = SYSDATETIME() WHERE malha_name = ?",
                    (teto_horas, atual))

        conn.commit(); cur.close(); conn.close()
        # Chaves da orientação são CONDICIONAIS (aditivas): quem não mexeu nela
        # recebe a resposta de sempre, byte a byte.
        resp = {"ok": True, "malha_name": atual, "renomeada": renomeada}
        # ADITIVO e só quando houve o quê dizer: a tela avisa que o ciclo em voo
        # acompanhou o nome novo. Banco sem a 085 (ou malha sem corrida aberta)
        # devolve a resposta de sempre, byte a byte.
        if corridas_renomeadas:
            resp["corridas_renomeadas"] = corridas_renomeadas
        # ADITIVO e só quando há ciclo em voo (F8, §6.9/#8): front antigo
        # ignora a chave, e malha sem corrida aberta responde byte a byte como
        # antes desta fase.
        if aviso_ciclo:
            resp["aviso_ciclo"] = aviso_ciclo
        if tem_orientacao:
            resp["orientacao"] = orientacao
            if migration_074_pendente:
                resp["migration_074_pendente"] = True
        if tem_teto:
            if migration_085_pendente:
                resp["migration_085_pendente"] = True
            else:
                resp["teto_horas"] = teto_horas
        if tem_virada or tem_equalizar:
            if migration_081_pendente:
                resp["migration_081_pendente"] = True
            else:
                if tem_virada:
                    resp["hora_virada"] = _hhmm(hora_virada)
                    # Quem foi alinhado à régua nova — o front usa para dizer
                    # "N pipelines precisam ser republicados" logo em seguida.
                    resp["equalizados"] = equalizados
                if tem_equalizar:
                    resp["equalizar_data"] = equalizar_data
        return resp
    except HTTPException:
        raise
    except Exception as e:
        # Rollback explícito: o rename é insert/migra/apaga na mesma transação —
        # uma falha no meio não pode deixar a malha duplicada ou sem filhas.
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.post("/malhas/{malha_name}/pipelines", tags=["malhas"])
def add_membro(malha_name: str, body: dict = Body(default={}),
               _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Adiciona um pipeline à malha.

    Pré-valida a existência do pipeline (422 com o nome, ANTES da FK) e grava a
    grafia CANONIZADA pelo registro em etl_pipeline — mesma regra da PR #236.
    Idempotente: membro que já existe devolve 200 sem regravar nada."""
    nome_pedido = (body.get("pipeline_name") or "").strip()
    if not nome_pedido:
        raise HTTPException(status_code=422, detail="pipeline_name é obrigatório")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        pipeline = _pipeline_oficial(cur, nome_pedido)
        if pipeline is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=422,
                                detail=f"Pipeline inexistente: '{nome_pedido}'")
        cur.execute(
            "SELECT 1 FROM dbo.etl_malha_pipeline WHERE malha_name = ? AND pipeline_name = ?",
            (malha, pipeline))
        if cur.fetchone():
            cur.close(); conn.close()
            return {"ok": True, "malha_name": malha, "pipeline_name": pipeline,
                    "ja_membro": True}
        cur.execute(
            "INSERT INTO dbo.etl_malha_pipeline (malha_name, pipeline_name) VALUES (?, ?)",
            (malha, pipeline))
        # §6.9/#16 (F8) — o snapshot da corrida congelou na abertura: o membro
        # entra no CADASTRO agora e no CICLO só no próximo. Avisa, não recusa:
        # preparar o ciclo seguinte no meio do atual é gesto legítimo, e
        # recusá-lo deixaria a malha inteditável por horas.
        aviso_ciclo = _aviso_ciclo_em_voo(cur, malha, "membro_add")
        conn.commit(); cur.close(); conn.close()
        resp = {"ok": True, "malha_name": malha, "pipeline_name": pipeline,
                "ja_membro": False}
        if aviso_ciclo:
            resp["aviso_ciclo"] = aviso_ciclo
        return resp
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.delete("/malhas/{malha_name}/pipelines/{pipeline_name}", tags=["malhas"])
def remove_membro(malha_name: str, pipeline_name: str,
                  _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Remove um pipeline da malha (só o vínculo — o pipeline continua
    existindo, e a dependência global da 067 NÃO é tocada aqui).

    F11 (§7.3): membro LIGADO a componente do desenho é recusado com 422 —
    remover o membro por baixo do desenho deixaria arestas apontando para um
    não-membro. Desligar primeiro (excluir a aresta/nó) é o gesto honesto,
    com o diff da descompilação dito lá. Sem a 075 (deploy parcial), o
    comportamento é o de sempre — não existe desenho para proteger."""
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        nome = (pipeline_name or "").strip()
        if _tabelas_075(cur):
            cur.execute(
                "SELECT 1 FROM dbo.etl_malha_aresta WHERE malha_name = ? "
                "AND (origem_pipeline = ? OR destino_pipeline = ?)",
                (malha, nome, nome))
            if cur.fetchone():
                _fechar_silencioso(conn)
                raise HTTPException(
                    status_code=422,
                    detail=f"'{nome}' está ligado a componente(s) do desenho "
                           f"da malha '{malha}' — desligue-o dos componentes "
                           "primeiro (exclua as arestas dele no diagrama).")
        cur.execute(
            "DELETE FROM dbo.etl_malha_pipeline WHERE malha_name = ? AND pipeline_name = ?",
            (malha, nome))
        if (cur.rowcount or 0) == 0:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=404,
                detail=f"'{pipeline_name}' não é membro da malha '{malha}'")
        # §6.9/#16 (F8): o membro sai do cadastro, mas o snapshot do ciclo em
        # voo já o congelou — ele continua no denominador até o ciclo fechar.
        # Sem a frase, o operador remove o membro e não entende por que o
        # painel continua esperando por ele.
        aviso_ciclo = _aviso_ciclo_em_voo(cur, malha, "membro_remove")
        conn.commit(); cur.close(); conn.close()
        resp = {"ok": True, "malha_name": malha}
        if aviso_ciclo:
            resp["aviso_ciclo"] = aviso_ciclo
        return resp
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.put("/malhas/{malha_name}/layout", tags=["malhas"])
def salvar_layout(malha_name: str, body: dict = Body(default={}),
                  _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Persiste a posição dos nós do diagrama (F8) em etl_malha_pipeline.

    Só MEMBROS da malha são atualizados: posição de não-membro é ignorada e
    contada fora de 'atualizados' (o UPDATE não afeta linha) — o front pode
    ter um nó recém-removido da malha no estado local, e isso não é erro.
    Tudo na MESMA transação: um salvar não pode deixar metade do layout novo.

    F10 (§9 do desenho de componentes): entrada com pipeline_name "no:{id}"
    é posição de NÓ ESPECIAL e grava em etl_malha_no.layout_* — mesma regra
    de tolerância (nó de outra malha/excluído conta em 'ignorados'). Sem a
    075, entrada de nó dá 503 instrutivo; layout só de pipelines segue ok."""
    posicoes = body.get("posicoes")
    if not isinstance(posicoes, list):
        raise HTTPException(status_code=422, detail="posicoes deve ser uma lista")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        atualizados = 0
        ignorados = 0
        tem_075 = None      # lazy: só consulta o banco se aparecer nó especial
        for pos in posicoes:
            nome = (pos.get("pipeline_name") or "").strip() if isinstance(pos, dict) else ""
            x = pos.get("layout_x") if isinstance(pos, dict) else None
            y = pos.get("layout_y") if isinstance(pos, dict) else None
            # bool é subclasse de int em Python: true/false no JSON passaria
            # como número e viraria 1.0/0.0 no banco em silêncio.
            if (not nome
                    or not isinstance(x, (int, float)) or isinstance(x, bool)
                    or not isinstance(y, (int, float)) or isinstance(y, bool)):
                _fechar_silencioso(conn)
                raise HTTPException(
                    status_code=422,
                    detail="Cada posição precisa de pipeline_name, layout_x e "
                           "layout_y numéricos")
            if nome.startswith("no:"):
                # Nó especial (F10): "no:{id}" é o contrato do §9 — o prefixo
                # não colide com pipeline real (nome com ':' não é dag_id
                # válido no Airflow).
                if tem_075 is None:
                    tem_075 = _tabelas_075(cur)
                if not tem_075:
                    _fechar_silencioso(conn)
                    raise HTTPException(status_code=503, detail=_MSG_SEM_075)
                try:
                    no_id = int(nome[3:])
                except ValueError:
                    _fechar_silencioso(conn)
                    raise HTTPException(
                        status_code=422,
                        detail="Posição de nó deve usar o formato 'no:{id}'")
                cur.execute(
                    "UPDATE dbo.etl_malha_no SET layout_x = ?, layout_y = ? "
                    "WHERE id = ? AND malha_name = ?",
                    (float(x), float(y), no_id, malha))
            else:
                cur.execute(
                    "UPDATE dbo.etl_malha_pipeline SET layout_x = ?, layout_y = ? "
                    "WHERE malha_name = ? AND pipeline_name = ?",
                    (float(x), float(y), malha, nome))
            if (cur.rowcount or 0) > 0:
                atualizados += 1
            else:
                ignorados += 1
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "atualizados": atualizados, "ignorados": ignorados}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.post("/malhas/{malha_name}/agendamento", tags=["malhas"])
def salvar_agendamento_malha(malha_name: str, body: dict = Body(default={}),
                             _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Salva o agendamento da MALHA (F13 — §4, Decisão 8) e o COMPILA para as
    raízes ligadas ao Início: cópia campo a campo para as colunas reais
    (scheduled_time derivado incluído), assinatura agenda_no e carimbo de
    republicação, numa transação única. Todas as raízes ficam com o MESMO
    cron e a MESMA virada (Decisão 9) → o scheduler dispara todas no mesmo
    tick, em paralelo, cada uma na própria DAG (§4.2) — nenhum disparador
    novo, nenhuma DAG-mestre.

    Body (§9): {"agendamento": {...subconjunto do register, §4.1...},
    "dry_run"?}. dry_run devolve o efeito §7.2 sem gravar ({efeito, avisos,
    erros} — conflito de assinatura vai em `erros`, HTTP 200, como o ciclo
    do compilador); o write RECOMPUTA sobre o estado corrente e o conflito
    vira 422 nomeando a malha e o nó donos (Decisão 11). Raiz assinada que
    ganhou dependência por outra porta recebe AVISO de contradição (badge
    §2.2) — nunca bloqueio. Sem nó Início (ou sem saídas) o JSON é salvo
    com aviso forte: o nó é o plugue, a configuração não se perde ao
    recriá-lo (Decisão 8)."""
    dry_run = bool(body.get("dry_run"))
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        _exigir_tabelas_075(cur, conn)
        if not _colunas_agenda(cur):
            _fechar_silencioso(conn)
            raise HTTPException(status_code=503, detail=_MSG_SEM_075)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        ag, avisos_validacao = _validar_agendamento(body.get("agendamento"))
        resumo_para = _resumo_agendamento(ag)
        nos_l = _nos_da_malha(cur, malha)
        arestas_l = _arestas_da_malha(cur, malha)
        inicio = next((n for n in nos_l if n["tipo"] == "inicio"), None)
        raizes = sorted({a["destino_pipeline"] for a in arestas_l
                         if inicio is not None
                         and a["origem_no"] == inicio["id"]
                         and a["destino_pipeline"]}, key=str.casefold)

        tem_067 = _tabela_067(cur)
        erros: list = []
        efeito = _efeito_vazio()
        avisos = _avisos_desenho(nos_l, arestas_l)
        for msg in avisos_validacao:        # hora_virada inválida → NULL (D35)
            avisos.append({"no": None, "nivel": "leve", "mensagem": msg})
        if inicio is None:
            avisos.append({"no": None, "nivel": "forte", "mensagem":
                           "a malha não tem nó Início — o agendamento fica "
                           "guardado e só alcança raízes quando um Início "
                           "for ligado"})
        aplicar: list = []          # raízes que recebem a cópia no write
        for p in raizes:
            info = _agenda_da_raiz(cur, p)
            if info is None:
                continue    # membro sumiu num gesto concorrente — defensivo
            if info["agenda_no"] is not None and \
                    (info["agenda_malha"] or "").casefold() != malha.casefold():
                # Decisão 11: um dono por vez — nunca last-write-wins mudo.
                erros.append(_msg_raiz_de_outra_malha(
                    p, info["agenda_malha"], info["agenda_no"]))
                continue
            if tem_067 and _raiz_tem_dependencia(cur, p):
                avisos.append({"no": inicio["id"], "nivel": "forte",
                               "mensagem": _msg_contradicao(p)})
            if info["agenda_no"] == inicio["id"] and \
                    _mesma_agenda(info["agendamento"], ag):
                continue            # já compilada campo a campo — no-op honesto
            aplicar.append(p)
            efeito["agendamentos"].append({
                "pipeline": p,
                "de": _resumo_agendamento(info["agendamento"]),
                "para": resumo_para})
            if info["dag_criada"] == 1:
                efeito["republicar"].append(p)

        if dry_run:
            cur.close(); conn.close()
            return {"efeito": efeito, "avisos": avisos, "erros": erros}
        if erros:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422, detail=erros[0])

        cur.execute(
            "UPDATE dbo.etl_malha SET agendamento_json = ?, "
            "atualizado_em = SYSDATETIME() WHERE malha_name = ?",
            (json.dumps(ag, ensure_ascii=False), malha))
        for p in aplicar:
            _aplicar_agenda_na_raiz(cur, p, ag, inicio["id"])
        # F2 da spec-malha-data-unica: a virada do agendamento É a régua de
        # data da MALHA — guardá-la só nas raízes deixaria os demais membros
        # calculando ODATE por outra régua (a doença da Carga_Vida) e faria a
        # própria tela acusar as raízes como "fora da régua", porque
        # etl_malha.hora_virada continuaria nula. Uma porta só: salvar o
        # agendamento aqui grava a régua e a compila para a malha inteira.
        equalizados_virada: list = []
        if _colunas_081(cur):
            cur.execute(
                "UPDATE dbo.etl_malha SET hora_virada = ?, "
                "atualizado_em = SYSDATETIME() WHERE malha_name = ?",
                (ag.get("hora_virada"), malha))
            equalizados_virada = _compilar_virada(cur, malha,
                                                  ag.get("hora_virada"))
        conn.commit(); cur.close(); conn.close()
        resp_ag = {"ok": True, "efeito": efeito, "avisos": avisos,
                   "agendamento": ag, "agendamento_resumo": resumo_para,
                   # o cron pela MESMA função do register (conferência visual —
                   # a autoridade do gatilho segue sendo o scheduler)
                   "cron": _build_cron(ag["schedule_type"], ag["schedule_hour"],
                                       ag["schedule_minute"], ag["schedule_dow"],
                                       ag["schedule_dom"])}
        if equalizados_virada:
            # Membros NÃO-raiz que foram alinhados à régua de data: o efeito da
            # F13 fala das raízes, e este é maior — precisa ser dito.
            resp_ag["virada_equalizada"] = equalizados_virada
        return resp_ag
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


# ── Nós especiais (F10) — o DESENHO dos componentes de malha ─────────────────
# O desenho e sua validação: a compilação do Aguarde (expansão → 067 assinada
# + espelho CSV + carimbo + dry_run) é a F11; o agendamento do Início é a F13;
# os observadores (Notificação/Fim) são avaliados pela guardiã (F14) — aqui a
# F14 só valida o config por tipo (_validar_config_no).

@router.post("/malhas/{malha_name}/nos", tags=["malhas"])
def add_no(malha_name: str, body: dict = Body(default={}),
           _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria um nó especial do desenho (F10 — §1/§2 do desenho de componentes).

    `config` é validado na estrutura (objeto JSON) e por TIPO
    (_validar_config_no, F14): Notificação {titulo?, mensagem?}, Fim
    {notificar_teams?} — o agendamento do Início mora na MALHA (F13,
    Decisão 8). Um Início e um Fim por malha: 422 aqui e índice filtrado da
    075 por baixo — um INSERT por SQL direto também estoura."""
    tipo = (body.get("tipo") or "").strip().lower()
    if tipo not in _TIPOS_NO:
        raise HTTPException(status_code=422,
                            detail="tipo deve ser um de: inicio, aguarde, "
                                   "notificacao, fim")
    config = body.get("config")
    if config is not None and not isinstance(config, dict):
        raise HTTPException(status_code=422, detail="config deve ser um objeto JSON")
    _validar_config_no(tipo, config)
    x = body.get("layout_x")
    y = body.get("layout_y")
    for v in (x, y):
        if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool)):
            raise HTTPException(status_code=422,
                                detail="layout_x/layout_y devem ser numéricos")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        _exigir_tabelas_075(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        if tipo in ("inicio", "fim"):
            cur.execute("SELECT 1 FROM dbo.etl_malha_no "
                        "WHERE malha_name = ? AND tipo = ?", (malha, tipo))
            if cur.fetchone():
                _fechar_silencioso(conn)
                raise HTTPException(
                    status_code=422,
                    detail=f"A malha já tem um nó {_ROTULO_NO[tipo]} — só "
                           "pode haver um por malha")
        criado_por = None
        if isinstance(_auth, dict):
            criado_por = (str(_auth.get("matricula") or "").strip() or None)
        cur.execute(
            "INSERT INTO dbo.etl_malha_no "
            "(malha_name, tipo, config_json, layout_x, layout_y, criado_por) "
            "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?)",
            (malha, tipo,
             json.dumps(config, ensure_ascii=False) if config is not None else None,
             None if x is None else float(x), None if y is None else float(y),
             (criado_por or "")[:100] or None))
        novo_id = int(cur.fetchone()[0])
        avisos = _avisos_desenho(_nos_da_malha(cur, malha),
                                 _arestas_da_malha(cur, malha))
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "id": novo_id, "avisos": avisos}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.patch("/malhas/{malha_name}/nos/{no_id}", tags=["malhas"])
def update_no(malha_name: str, no_id: int, body: dict = Body(default={}),
              _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Atualiza config e/ou layout de um nó (F10 — §9).

    `tipo` NÃO é editável: trocar o tipo mudaria a semântica do desenho por
    baixo do que já está ligado — recriar o nó é o gesto honesto. `config`
    presente com None LIMPA a configuração; config não-nulo é validado por
    TIPO (_validar_config_no, F14) — o tipo vem da LINHA, não do body."""
    tem_config = "config" in body
    config = body.get("config")
    if tem_config and config is not None and not isinstance(config, dict):
        raise HTTPException(status_code=422, detail="config deve ser um objeto JSON")
    tem_layout = ("layout_x" in body) or ("layout_y" in body)
    if tem_layout:
        x, y = body.get("layout_x"), body.get("layout_y")
        for v in (x, y):
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise HTTPException(status_code=422,
                                    detail="layout_x e layout_y devem vir "
                                           "juntos e numéricos")
    if not tem_config and not tem_layout:
        raise HTTPException(status_code=422,
                            detail="Nada para atualizar: envie config e/ou "
                                   "layout_x/layout_y")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        _exigir_tabelas_075(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        cur.execute("SELECT id, tipo FROM dbo.etl_malha_no "
                    "WHERE id = ? AND malha_name = ?", (no_id, malha))
        linha_no = cur.fetchone()
        if linha_no is None:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=404,
                                detail=f"Nó {no_id} não existe na malha '{malha}'")
        if tem_config and config is not None:
            try:
                _validar_config_no((str(linha_no[1] or "")).strip().lower(),
                                   config)
            except HTTPException:
                _fechar_silencioso(conn)
                raise
        if tem_config:
            cur.execute(
                "UPDATE dbo.etl_malha_no SET config_json = ? "
                "WHERE id = ? AND malha_name = ?",
                (json.dumps(config, ensure_ascii=False) if config is not None else None,
                 no_id, malha))
        if tem_layout:
            cur.execute(
                "UPDATE dbo.etl_malha_no SET layout_x = ?, layout_y = ? "
                "WHERE id = ? AND malha_name = ?",
                (float(x), float(y), no_id, malha))
        avisos = _avisos_desenho(_nos_da_malha(cur, malha),
                                 _arestas_da_malha(cur, malha))
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "avisos": avisos}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.post("/malhas/{malha_name}/nos/{no_id}/retencao", tags=["malhas"])
def reter_no(malha_name: str, no_id: int, body: dict = Body(default={}),
             auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """SEGURA ou LIBERA um nó Aguarde ou Início (migration 082).

    Segurado, ele não solta ninguém: o predicado canônico de liberação
    (`utils/dependencias.liberado`) traz o id do Aguarde retido junto com os
    faltantes, então push, guardiã e painel obedecem à trava sem que nenhum
    deles precise saber que ela existe — a lição da F4 (regra que mora numa
    porta só não protege) aplicada de propósito.

    É gesto de EXECUÇÃO (acao_executar), não de edição: segurar a malha é
    operação, e quem opera pode não ter permissão de mexer no desenho.

    Body: {"reter": true|false}. Sem a 082 é 503 com instrução — botão que não
    segura seria pior que botão ausente.

    **F7 — os relógios (spec-malha-execucao §6.7).** Enquanto qualquer
    **Aguarde** da malha estiver segurado, o teto da corrida não corre — o
    Início NÃO conta: ele segura a partida da próxima corrida, e a que já está
    em andamento segue (é o que o `aviso` da resposta diz, e o hold da corrida
    tem de concordar com essa frase). Soltar o **último** Aguarde retido
    credita ao teto o tempo que a malha passou parada
    (`teto_creditado_min`) e reprojeta `teto_em` — soltar após 6h de hold numa
    malha com teto de 4h empurra o teto em 6h, e a corrida NÃO expirou. O
    crédito e a limpeza do `retido_em` caem no MESMO commit, nesta ordem: é o
    `retido_em` que mede o crédito.

    O crédito vira EVENTO (`MALHA_TETO_CREDITADO`, Decisão 61) porque a barra do
    limite de segurança anda PARA TRÁS quando ele acontece — uma barra de prazo
    que recua sem explicação destrói a confiança em todas as outras.
    """
    reter = bool(body.get("reter", True))
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        _exigir_tabelas_075(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        if not _colunas_082(cur):
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=503,
                detail="Segurar o Aguarde exige a migration 082 "
                       "(etl_malha_no.retido_em), ainda não aplicada neste banco.")
        cur.execute("SELECT tipo FROM dbo.etl_malha_no WHERE id = ? AND malha_name = ?",
                    (no_id, malha))
        row = cur.fetchone()
        if row is None:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=404,
                                detail=f"Nó {no_id} não existe na malha '{malha}'")
        tipo = (row[0] or "").strip().lower()
        # Aguarde segura o PONTO DE JUNÇÃO (o predicado de liberação obedece);
        # Início segura a MALHA INTEIRA antes de partir (o check_agenda da raiz
        # pergunta). Notificação e Fim não liberam ninguém — só observam e
        # emitem evento —, então segurá-los não teria efeito nenhum: recusa
        # nominal em vez de um botão que aceita o clique e não faz nada.
        if tipo not in ("aguarde", "inicio"):
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=422,
                detail=f"'{_ROTULO_NO.get(tipo, tipo)}' não pode ser segurado — "
                       "só o Aguarde (o ponto de junção) e o Início (a partida "
                       "da malha). Notificação e Fim apenas observam.")
        quem = (str(auth.get("matricula") or "").strip() or "?")
        # A corrida ABERTA, lida ANTES da escrita: ela decide as duas coisas
        # novas desta fase — o crédito do teto (ao soltar) e a frase que o
        # operador lê (ao segurar o Início). Sem a 085 ou com o interruptor em
        # 0, `corrida_aberta` nem vai ao banco/devolve None e este endpoint se
        # comporta byte a byte como antes da spec.
        corrida_viva = (mc.corrida_aberta(cur, malha)
                        if mc.corrida_ativa(cur) else None)
        credito = None
        if reter:
            cur.execute(
                "UPDATE dbo.etl_malha_no SET retido_em = GETDATE(), retido_por = ? "
                "WHERE id = ? AND malha_name = ?", (quem[:64], no_id, malha))
        else:
            # ⚠️ ORDEM: creditar ANTES de limpar. O crédito é
            # `DATEDIFF(MINUTE, MIN(retido_em), SYSDATETIME())` — com o
            # `retido_em` já apagado, `MIN` volta NULL e o hold inteiro se perde
            # em silêncio. Os dois statements + o evento caem no mesmo commit
            # abaixo: se algo estourar no meio, nada aconteceu e o operador
            # clica de novo.
            if corrida_viva is not None:
                credito = mc.creditar_hold(cur, malha, no_id)
            cur.execute(
                "UPDATE dbo.etl_malha_no SET retido_em = NULL, retido_por = NULL "
                "WHERE id = ? AND malha_name = ?", (no_id, malha))
            if credito is not None:
                _evento_da_corrida(
                    cur, corrida_viva, mc.EVENTO_TETO_CREDITADO,
                    f"limite de seguranca adiado em {credito['minutos']} min "
                    f"por retencao ({_ROTULO_NO.get(tipo, tipo)} liberado por "
                    f"{quem}) — novo limite {_fmt_dt(credito['teto_em'])}",
                    notificar=False)
        conn.commit()
        # Quem estava esperando: com a trava solta, o próximo ciclo da guardiã
        # (ou o próximo publish de um pai) libera. Dito para o operador não
        # ficar esperando um disparo imediato que não vem.
        dependentes = []
        if _tabela_067(cur) and _coluna_origem_no(cur):
            cur.execute(
                "SELECT DISTINCT pipeline_name FROM dbo.etl_pipeline_dependencia "
                "WHERE origem_no = ? ORDER BY pipeline_name", (no_id,))
            dependentes = [r[0] for r in cur.fetchall()]
        cur.close(); conn.close()
        log.info("[MALHA] Aguarde #%s da malha '%s' %s por %s", no_id, malha,
                 "SEGURADO" if reter else "liberado", quem)
        resp = {"ok": True, "no_id": no_id, "retido": reter,
                "retido_por": quem if reter else None,
                "dependentes": dependentes}
        # ── ADITIVOS da F7, e só quando há o quê dizer ──────────────────────
        # Segurar o INÍCIO com corrida em voo é o gesto mais mal-entendido da
        # tela: o botão parece "parar a malha" e não para — ele segura a
        # PARTIDA. Sem esta frase o operador segura o Início às 3h achando que
        # travou o ciclo que está rodando, e o ciclo continua (Decisão 45: a
        # regra dita ANTES, não o horário exato depois). Sem "#N": o número da
        # corrida não aparece na interface (Decisão 74).
        if reter and tipo == "inicio" and corrida_viva is not None:
            resp["aviso"] = ("Início segurado: a próxima corrida não parte. "
                             "A corrida em andamento SEGUE — segurar o Início "
                             "segura a partida, não o ciclo já aberto.")
        if credito is not None:
            resp["credito_teto"] = {
                "minutos": credito["minutos"],
                "teto_em": _fmt_dt(credito["teto_em"]),
                "total_min": credito["total_min"],
            }
            log.info("[MALHA] corrida da malha '%s': +%d min de limite por "
                     "retencao (total %d min); novo limite %s", malha,
                     credito["minutos"], credito["total_min"],
                     _fmt_dt(credito["teto_em"]))
        return resp
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.delete("/malhas/{malha_name}/nos/{no_id}", tags=["malhas"])
def remove_no(malha_name: str, no_id: int, dry_run: bool = False,
              _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Exclui um nó do desenho — gesto destrutivo (§7.3): a MESMA transação
    DESCOMPILA as linhas assinadas do nó (remove com espelho CSV + carimbo, ou
    TRANSFERE a assinatura quando a expansão de outra malha — ou de outro nó
    desta — ainda produz o par), remove as arestas do nó e o nó, nesta ordem.
    A FK NO ACTION da 075 (§1.3/§1.4) não deixa ordem outra: um DELETE de nó
    por SQL direto com arestas ou assinaturas penduradas falha alto, nunca
    leva desenho ou dependência junto em silêncio.

    ?dry_run=true devolve o efeito §7.2 sem gravar. A recompilação pode
    CRIAR linhas (067 divergida do desenho) — o ciclo canônico da Decisão 15
    vale aqui também: dry_run devolve em `erros`, write é 422. O Início
    assinado (raiz vira on_demand) é a F13 — a FK agenda_no garantirá a
    mesma ordem lá."""
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        _exigir_tabelas_075(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        cur.execute("SELECT id, tipo FROM dbo.etl_malha_no "
                    "WHERE id = ? AND malha_name = ?", (no_id, malha))
        row = cur.fetchone()
        if row is None:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=404,
                                detail=f"Nó {no_id} não existe na malha '{malha}'")
        tipo_no = (row[1] or "").strip().lower()
        nos_l = _nos_da_malha(cur, malha)
        arestas = _arestas_da_malha(cur, malha)
        nos_prospectivos = [n for n in nos_l if n["id"] != no_id]
        prospectivas = [a for a in arestas
                        if a["origem_no"] != no_id and a["destino_no"] != no_id]
        # Só a exclusão de AGUARDE muda compilação: pela gramática §2.1 nenhum
        # outro tipo entra no upstream nem nas saídas de um Aguarde.
        diff, erros = None, []
        if tipo_no == "aguarde" and _descompilacao_possivel(cur):
            diff = _diff_compilacao(cur, malha, nos_prospectivos, prospectivas)
            # A recompilação (Decisão 7) pode conter CRIAÇÕES quando a 067
            # divergiu do desenho (achado da revisão: linha manual apagada +
            # aresta inversa criada no vão) — criação passa pelo MESMO ciclo
            # canônico do add, senão a remoção recriaria o par fechando A↔D.
            erros = _erros_ciclo_canonico(diff)

        # F13 — excluir o INÍCIO (Decisão 10/§7.3): toda raiz ASSINADA por
        # este nó vira on_demand + carimbo, ANTES do DELETE — a FK agenda_no
        # (NO ACTION, §1.4) derruba o DELETE com assinatura pendurada, então
        # esta é a única ordem possível. O agendamento_json da MALHA fica:
        # o nó é o plugue; recriar o Início não perde a configuração
        # (Decisão 8).
        efeito_ag, republicar_ag = [], []
        if tipo_no == "inicio" and _colunas_agenda(cur):
            for p in _raizes_assinadas_do_no(cur, no_id):
                info = _agenda_da_raiz(cur, p)
                if info is None:
                    continue
                efeito_ag.append({
                    "pipeline": p,
                    "de": _resumo_agendamento(info["agendamento"]),
                    "para": "sob demanda"})
                if info["dag_criada"] == 1:
                    republicar_ag.append(p)

        if dry_run:
            avisos = _avisos_gesto(nos_prospectivos, prospectivas, diff)
            cur.close(); conn.close()
            return {"efeito": _mesclar_efeito_agenda(_efeito_publico(diff),
                                                     efeito_ag, republicar_ag),
                    "avisos": avisos, "erros": erros,
                    "preview_expandido": _preview_expandido(diff)}
        if erros:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422, detail=erros[0])

        if diff is not None:
            criado_por = None
            if isinstance(_auth, dict):
                criado_por = (str(_auth.get("matricula") or "").strip() or None)
            # Descompila ANTES do DELETE do nó — com linha assinada pendurada
            # a FK FK_dep_origem_no derrubaria o DELETE (a ordem do §1.4).
            _aplicar_compilacao(cur, diff, criado_por)
        for item in efeito_ag:
            _desligar_raiz(cur, item["pipeline"])
        cur.execute("DELETE FROM dbo.etl_malha_aresta "
                    "WHERE origem_no = ? OR destino_no = ?", (no_id, no_id))
        arestas_removidas = max(cur.rowcount or 0, 0)
        cur.execute("DELETE FROM dbo.etl_malha_no WHERE id = ?", (no_id,))
        avisos = _avisos_gesto(nos_prospectivos, prospectivas, diff)
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "arestas_removidas": arestas_removidas,
                "avisos": avisos,
                "efeito": _mesclar_efeito_agenda(_efeito_publico(diff),
                                                 efeito_ag, republicar_ag)}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.post("/malhas/{malha_name}/arestas", tags=["malhas"])
def add_aresta_no(malha_name: str, body: dict = Body(default={}),
                  _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria uma aresta do desenho envolvendo nó, com a GRAMÁTICA COMPLETA da
    tabela §2.1 — cada célula proibida devolve 422 com a mensagem da célula;
    pipeline→pipeline é recusado AQUI com a instrução da porta certa (a aresta
    direta do F8 grava dependência REAL na 067 — outra semântica, outra porta).

    Body (§9): {"origem": {"no": id} | {"pipeline": nome}, "destino": {...},
    "dry_run": bool?}. Idempotente: aresta que já existe devolve
    ja_existia=True — e o write ainda RECONCILIA a compilação se a 067 tiver
    divergido do desenho (o invariante da Decisão 7: o desenho É o compilado).

    F11 — aresta envolvendo AGUARDE compila (expansão → 067 assinada + espelho
    CSV + carimbo, uma transação): dry_run devolve o efeito §7.2 sem gravar
    (erros de ciclo vão na lista `erros`, HTTP 200 — o modal da F12 mostra);
    o write recomputa sobre o estado corrente e o ciclo vira 422. O ciclo é
    validado PRIMEIRO sobre o conjunto pós-expansão (BFS canônico da F1 +
    mensagem literal — Decisão 15); o topológico do desenho segue de
    retaguarda para o ciclo só-de-nós, que não compila nada."""
    dry_run = bool(body.get("dry_run"))
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        _exigir_tabelas_075(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        origem = _resolver_ponta(cur, conn, malha, body.get("origem"), "origem")
        destino = _resolver_ponta(cur, conn, malha, body.get("destino"), "destino")
        erro = _erro_gramatica(origem["tipo"], destino["tipo"])
        if erro:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422, detail=erro)
        nos_l = _nos_da_malha(cur, malha)
        arestas = _arestas_da_malha(cur, malha)
        chave_o = _chave_ponta(origem["no"], origem["pipeline"])
        chave_d = _chave_ponta(destino["no"], destino["pipeline"])
        ja_existia = next(
            (a for a in arestas
             if _chave_ponta(a["origem_no"], a["origem_pipeline"]) == chave_o
             and _chave_ponta(a["destino_no"], a["destino_pipeline"]) == chave_d),
            None)
        prospectivas = arestas if ja_existia is not None else arestas + [{
            "id": None, "origem_no": origem["no"],
            "origem_pipeline": origem["pipeline"],
            "destino_no": destino["no"],
            "destino_pipeline": destino["pipeline"]}]

        # Compilação (F11): só aresta que toca AGUARDE tem efeito na 067 —
        # Início planta agenda (F13) e Notificação/Fim observam (F14).
        diff, erros = None, []
        if "aguarde" in (origem["tipo"], destino["tipo"]):
            _exigir_compilacao(cur, conn)
            diff = _diff_compilacao(cur, malha, nos_l, prospectivas)
            erros = _erros_ciclo_canonico(diff)
        if ja_existia is None and not erros \
                and _criaria_ciclo_desenho(arestas, chave_o, chave_d):
            # Retaguarda topológica (texto espelhado no cliente, regra F8).
            erros.append(
                f"Ciclo no desenho: {_rotulo_ponta(origem)} → "
                f"{_rotulo_ponta(destino)} fecha um ciclo (o caminho "
                f"volta para {_rotulo_ponta(origem)})")

        # F13 — Início → pipeline: o Início planta o agendamento da malha na
        # raiz (§4.2). As validações são do MOMENTO DO GESTO (aresta NOVA,
        # como a gramática): raiz com dependência na 067 → 422 (§2.2 — o
        # schedule=None do motor venceria o cron e o agendamento da malha
        # seria mentira); raiz assinada por Início de OUTRA malha → 422
        # nomeando a dona (Decisão 11). Re-salvar aresta existente segue
        # no-op reconciliável: a contradição vira aviso/badge, nunca recusa.
        efeito_ag, avisos_ag, republicar_ag = [], [], []
        ag_malha = None
        if origem["tipo"] == "inicio" and destino["pipeline"] is not None:
            if ja_existia is None and _tabela_067(cur) \
                    and _raiz_tem_dependencia(cur, destino["pipeline"]):
                _fechar_silencioso(conn)
                raise HTTPException(
                    status_code=422,
                    detail=_msg_raiz_com_dependencia(destino["pipeline"]))
            if _colunas_agenda(cur):
                info = _agenda_da_raiz(cur, destino["pipeline"])
                assinada_outra = (
                    info is not None and info["agenda_no"] is not None
                    and (info["agenda_malha"] or "").casefold()
                    != malha.casefold())
                if assinada_outra and ja_existia is None:
                    _fechar_silencioso(conn)
                    raise HTTPException(
                        status_code=422,
                        detail=_msg_raiz_de_outra_malha(
                            destino["pipeline"], info["agenda_malha"],
                            info["agenda_no"]))
                ag_malha = _agendamento_da_malha(cur, malha)
                if ag_malha is None:
                    # Liga só o fio, com o aviso do §4.2 — nada plantado.
                    avisos_ag.append({
                        "no": origem["no"], "nivel": "forte", "mensagem":
                        "configure o agendamento no Início — o fio fica "
                        "ligado, mas nenhuma agenda foi plantada ainda"})
                elif assinada_outra:
                    # Re-salvar de aresta cuja raiz é de outra malha: nunca
                    # re-assinada (o mesmo espírito da Decisão 4) — dito.
                    avisos_ag.append({
                        "no": origem["no"], "nivel": "leve", "mensagem":
                        _msg_raiz_de_outra_malha(
                            destino["pipeline"], info["agenda_malha"],
                            info["agenda_no"]) + " Nada foi re-assinado."})
                elif info is not None and not (
                        info["agenda_no"] == origem["no"]
                        and _mesma_agenda(info["agendamento"], ag_malha)):
                    # A cópia acontece (P com agendamento próprio NÃO
                    # assinado pode — a substituição é consentida no diff).
                    efeito_ag.append({
                        "pipeline": destino["pipeline"],
                        "de": _resumo_agendamento(info["agendamento"]),
                        "para": _resumo_agendamento(ag_malha)})
                    if info["dag_criada"] == 1:
                        republicar_ag.append(destino["pipeline"])
                if ja_existia is not None and _tabela_067(cur) \
                        and _raiz_tem_dependencia(cur, destino["pipeline"]):
                    # Badge de contradição (§2.2): aviso, nunca bloqueio.
                    avisos_ag.append({"no": origem["no"], "nivel": "forte",
                                      "mensagem": _msg_contradicao(
                                          destino["pipeline"])})

        if dry_run:
            avisos = _avisos_gesto(nos_l, prospectivas, diff) + avisos_ag
            efeito = _mesclar_efeito_agenda(_efeito_publico(diff),
                                            efeito_ag, republicar_ag)
            cur.close(); conn.close()
            return {"efeito": efeito, "avisos": avisos,
                    "erros": erros,
                    "preview_expandido": _preview_expandido(diff)}
        if erros:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422, detail=erros[0])

        novo_id = ja_existia["id"] if ja_existia is not None else None
        if ja_existia is None:
            cur.execute(
                "INSERT INTO dbo.etl_malha_aresta "
                "(malha_name, origem_no, origem_pipeline, destino_no, destino_pipeline) "
                "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?)",
                (malha, origem["no"], origem["pipeline"],
                 destino["no"], destino["pipeline"]))
            novo_id = int(cur.fetchone()[0])
        tem_efeito = diff is not None and (diff["criar"] or diff["remover"]
                                           or diff["transferir"])
        if tem_efeito:
            criado_por = None
            if isinstance(_auth, dict):
                criado_por = (str(_auth.get("matricula") or "").strip() or None)
            _aplicar_compilacao(cur, diff, criado_por)
        if efeito_ag:
            # F13: cópia do agendamento + assinatura + carimbo, na MESMA
            # transação da aresta (§4.2) — o desenho É o compilado.
            _aplicar_agenda_na_raiz(cur, destino["pipeline"], ag_malha,
                                    origem["no"])
        avisos = _avisos_gesto(nos_l, prospectivas, diff) + avisos_ag
        if ja_existia is None or tem_efeito or efeito_ag:
            conn.commit()
        # aresta re-salvada SEM efeito novo: no-op de verdade — nem commit
        cur.close(); conn.close()
        return {"ok": True, "id": novo_id,
                "ja_existia": ja_existia is not None, "avisos": avisos,
                "efeito": _mesclar_efeito_agenda(_efeito_publico(diff),
                                                 efeito_ag, republicar_ag)}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.delete("/malhas/{malha_name}/arestas/{aresta_id}", tags=["malhas"])
def remove_aresta_no(malha_name: str, aresta_id: int, dry_run: bool = False,
                     _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Remove UMA aresta de nó do desenho e RECOMPILA o efeito (F11, §7.3):
    linha assinada que a expansão nova não produz é removida (com espelho CSV
    e carimbo) — ou TRANSFERIDA quando a expansão desta ou de OUTRA malha
    ainda a produz. ?dry_run=true devolve o efeito §7.2 sem gravar; a
    confirmação quando remove ≥1 linha real é gesto da tela (F12), como no
    DELETE /dependencias do F8 — a API executa, quem avisa é a tela. Como a
    recompilação pode CRIAR linhas (067 divergida do desenho), o ciclo
    canônico da Decisão 15 vale AQUI também: dry_run devolve em `erros`,
    write é 422 com a mensagem literal da F1."""
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        _exigir_tabelas_075(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        nos_l = _nos_da_malha(cur, malha)
        arestas = _arestas_da_malha(cur, malha)
        alvo = next((a for a in arestas if a["id"] == aresta_id), None)
        if alvo is None:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=404,
                detail=f"Aresta {aresta_id} não existe na malha '{malha}'")
        prospectivas = [a for a in arestas if a["id"] != aresta_id]
        tipos = {n["id"]: n["tipo"] for n in nos_l}
        envolve_aguarde = ("aguarde" in (tipos.get(alvo["origem_no"]),
                                         tipos.get(alvo["destino_no"])))
        diff, erros = None, []
        if envolve_aguarde and _descompilacao_possivel(cur):
            diff = _diff_compilacao(cur, malha, nos_l, prospectivas)
            # A recompilação pode conter CRIAÇÕES quando a 067 divergiu do
            # desenho (achado da revisão) — ciclo canônico como no add: sem
            # isto o gesto de remoção recriaria uma linha que fecha A↔D.
            erros = _erros_ciclo_canonico(diff)

        # F13 — desligar a raiz do Início (Decisão 10): raiz ASSINADA por este
        # Início vira on_demand + carimbo — nunca restauração do agendamento
        # antigo, nunca cron remanescente. Sem as colunas da 075 (deploy
        # parcial) não existe assinatura — o gesto segue como na F12.
        efeito_ag, republicar_ag = [], []
        if tipos.get(alvo["origem_no"]) == "inicio" \
                and alvo["destino_pipeline"] and _colunas_agenda(cur):
            info = _agenda_da_raiz(cur, alvo["destino_pipeline"])
            if info is not None and info["agenda_no"] == alvo["origem_no"]:
                efeito_ag.append({
                    "pipeline": alvo["destino_pipeline"],
                    "de": _resumo_agendamento(info["agendamento"]),
                    "para": "sob demanda"})
                if info["dag_criada"] == 1:
                    republicar_ag.append(alvo["destino_pipeline"])

        if dry_run:
            avisos = _avisos_gesto(nos_l, prospectivas, diff)
            cur.close(); conn.close()
            return {"efeito": _mesclar_efeito_agenda(_efeito_publico(diff),
                                                     efeito_ag, republicar_ag),
                    "avisos": avisos, "erros": erros,
                    "preview_expandido": _preview_expandido(diff)}
        if erros:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422, detail=erros[0])

        if diff is not None:
            criado_por = None
            if isinstance(_auth, dict):
                criado_por = (str(_auth.get("matricula") or "").strip() or None)
            _aplicar_compilacao(cur, diff, criado_por)
        for item in efeito_ag:
            _desligar_raiz(cur, item["pipeline"])
        cur.execute("DELETE FROM dbo.etl_malha_aresta "
                    "WHERE id = ? AND malha_name = ?", (aresta_id, malha))
        if (cur.rowcount or 0) == 0:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=404,
                detail=f"Aresta {aresta_id} não existe na malha '{malha}'")
        avisos = _avisos_gesto(nos_l, prospectivas, diff)
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "avisos": avisos,
                "efeito": _mesclar_efeito_agenda(_efeito_publico(diff),
                                                 efeito_ag, republicar_ag)}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


# ── Dependências (F8) — a aresta do diagrama é a dependência REAL da F1 ──────

@router.post("/dependencias", tags=["malhas"])
def add_dependencia(body: dict = Body(default={}),
                    _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria UMA dependência em etl_pipeline_dependencia (tipo PIPELINE).

    É a porta de gravação do MalhaEditor: desenhar a aresta chama aqui, com as
    MESMAS validações do cadastro da F1 (existência e ciclo BFS, importadas de
    routers.pipelines) e a MESMA mensagem de ciclo — o cliente espelha o texto.

    Idempotente: aresta que já existe devolve ja_existia=True sem revalidar
    ciclo (ela foi validada quando nasceu; reprovar um re-salvar quebraria o
    aceite 'salvar sem mudanças é no-op'). Nos dois casos o espelho CSV
    etl_pipeline.depends_on do dependente é reconciliado na mesma transação."""
    nome_dep = (body.get("pipeline_name") or "").strip()
    nome_pred = (body.get("depende_de") or "").strip()
    if not nome_dep or not nome_pred:
        raise HTTPException(status_code=422,
                            detail="pipeline_name e depende_de são obrigatórios")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabela_067(cur, conn)
        # Canoniza as DUAS grafias pela registrada (regra da PR #236): a tabela
        # e o CSV têm de contar a mesma história que os dicts case-sensitive
        # do Python leem depois.
        pipeline = _pipeline_oficial(cur, nome_dep)
        if pipeline is None:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422,
                                detail=f"Pipeline inexistente: '{nome_dep}'")
        faltando = _validar_existencia(cur, [nome_pred])
        if faltando:
            _fechar_silencioso(conn)
            # Mesmo texto do cadastro da F1 (register_pipeline) de propósito.
            raise HTTPException(
                status_code=422,
                detail="Pipeline inexistente em 'depende de': "
                       + ", ".join(f"'{n}'" for n in faltando))
        depende_de = _pipeline_oficial(cur, nome_pred)
        if pipeline.casefold() == depende_de.casefold():
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422,
                                detail="Pipeline não pode depender de si mesmo")

        cur.execute(
            "SELECT 1 FROM dbo.etl_pipeline_dependencia "
            "WHERE pipeline_name = ? AND depende_de = ? AND tipo = 'PIPELINE'",
            (pipeline, depende_de))
        ja_existia = cur.fetchone() is not None
        if not ja_existia:
            # BFS da F1 sobre TODAS as dependências — ValueError vira 422 com a
            # mensagem do servidor (o aceite exige cliente e servidor iguais).
            _check_circular(cur, pipeline, [depende_de])
            criado_por = None
            if isinstance(_auth, dict):
                criado_por = (str(_auth.get("matricula") or "").strip() or None)
            cur.execute(
                "INSERT INTO dbo.etl_pipeline_dependencia "
                "(pipeline_name, depende_de, tipo, criado_por) VALUES (?, ?, 'PIPELINE', ?)",
                (pipeline, depende_de, (criado_por or "")[:100] or None))
        mudou_csv = _espelho_csv(cur, pipeline, depende_de, "add")
        # Dependência NOVA troca o schedule da DAG do dependente: liga a
        # pendência de publicação na MESMA transação (Decisão 6/D30). Aresta
        # que já existia não mudou configuração — não liga nada.
        dag_pendente = _ligar_dag_config_pendente(cur, pipeline) if not ja_existia else False
        if not ja_existia or mudou_csv:
            conn.commit()
        cur.close(); conn.close()
        return {"ok": True, "ja_existia": ja_existia,
                "dag_config_pendente": dag_pendente}
    except HTTPException:
        raise
    except ValueError as e:
        # _check_circular sinaliza ciclo por ValueError — mesma tradução da F1.
        _fechar_silencioso(conn)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.delete("/dependencias", tags=["malhas"])
def remove_dependencia(body: dict = Body(default={}),
                       _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Remove UMA dependência REAL (tabela 067 + espelho CSV, mesma transação).

    A confirmação explícita ('isto apaga a dependência real, não só o desenho' —
    §4b da spec) é responsabilidade do MalhaEditor ANTES de chamar aqui: a API
    executa, quem avisa é a tela.

    F11 (Decisão 4): linha ASSINADA (compilada por Aguarde de malha) é recusada
    com 422 nomeando malha e nó donos — apagá-la por aqui deixaria o desenho da
    malha dona contando uma história e o motor outra (e o Aguarde dela a
    recriaria... ou nunca). A porta certa é o desenho da malha."""
    nome_dep = (body.get("pipeline_name") or "").strip()
    nome_pred = (body.get("depende_de") or "").strip()
    if not nome_dep or not nome_pred:
        raise HTTPException(status_code=422,
                            detail="pipeline_name e depende_de são obrigatórios")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabela_067(cur, conn)
        if _coluna_origem_no(cur):
            ass = deps_svc.assinatura(cur, nome_dep, nome_pred)
            if ass is not None:
                _fechar_silencioso(conn)
                raise HTTPException(
                    status_code=422,
                    detail=deps_svc.msg_linha_assinada(
                        nome_dep, nome_pred, ass["malha"], ass["origem_no"]))
        # A colação CI do banco casa qualquer caixa no DELETE; o espelho CSV
        # também remove por casefold — canonização aqui seria redundante.
        cur.execute(
            "DELETE FROM dbo.etl_pipeline_dependencia "
            "WHERE pipeline_name = ? AND depende_de = ? AND tipo = 'PIPELINE'",
            (nome_dep, nome_pred))
        if (cur.rowcount or 0) == 0:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=404,
                detail=f"Dependência não encontrada: '{nome_dep}' depende de '{nome_pred}'")
        _espelho_csv(cur, nome_dep, nome_pred, "remove")
        # Remoção também muda o schedule da DAG do dependente (pode voltar ao
        # cron): mesma pendência de publicação, mesma transação (Decisão 6).
        dag_pendente = _ligar_dag_config_pendente(cur, nome_dep)
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "dag_config_pendente": dag_pendente}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
