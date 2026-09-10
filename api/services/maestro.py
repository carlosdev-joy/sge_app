"""api/services/maestro.py — Maestro, o assistente de parâmetros DataStage
(spec docs/spec-maestro-parametros.md, F1).

O usuário descreve o cenário na seção "Parâmetros do job" (Etapas/Fluxos) e o
Maestro explica como preencher cada campo, devolvendo uma PROPOSTA que a tela
aplica no editor. O que mora aqui:

  • o SYSTEM PROMPT, gerado do vocabulário de services/job_params — nunca
    digitado à mão, para o Maestro não prometer origem/âncora/tipo que o
    operador não tem (tests/test_maestro_servico.py prende o anti-drift);
  • o contexto que vai junto: catálogo de cenários (migration 110), parâmetros
    que o job DECLARA (lineage ISX, 106), defaults do pipeline (108) e as linhas
    atuais do editor SEM valor Encrypted;
  • a leitura da proposta (último bloco ```json da resposta) e a sua VALIDAÇÃO
    pela mesma régua do salvar (normalizar_lista + resolver_preview). Proposta
    que não passa vira `nao_atendido` com o erro da régua — a régua manda, não
    o modelo (risco 1 da spec: o falso verde);
  • o registro de cada rodada em etl_maestro_conversa.

Banco só nas funções que recebem `cur` (pyodbc, placeholders `?`); o resto é
puro. Sem a 110 as leituras levantam MaestroIndisponivel — nunca "sem catálogo,
segue o jogo".
"""
from __future__ import annotations

import json
import re
from datetime import date

from services import job_params as jp
from services.rerun_params import _defaults_pipeline as _defaults_pipeline_108
from services.ssh_arquivos import cortar_utf16

K_ENABLED = "maestro_enabled"

STATUS_ATENDIDO = "atendido"
STATUS_NAO_ATENDIDO = "nao_atendido"
STATUS_PERGUNTA = "pergunta"
STATUS_ERRO = "erro"
STATUS_DO_MODELO = (STATUS_ATENDIDO, STATUS_NAO_ATENDIDO, STATUS_PERGUNTA)

# Limites defensivos (a tela manda mensagens curtas + o estado do editor).
MAX_MENSAGEM = 4000         # o que o USUÁRIO digita (custo/abuso)
# Resposta anterior do próprio Maestro no histórico: pode passar de 4.000
# (MAX_TOKENS 4096 ≈ 12k chars). Recusá-la mataria a conversa a partir da
# primeira resposta longa (achado 1 da revisão adversarial da F1); o histórico
# é só contexto, então ela é TRUNCADA, não recusada.
MAX_MENSAGEM_HISTORICO = 6000
MAX_HISTORICO = 12          # rodadas enviadas ao provedor por chamada
MAX_PARAMS_EDITOR = 50
MAX_VALOR_EDITOR = 200      # valor fixo truncado no contexto (não é o que vai ao DataStage)
LIMITE_MOTIVO = 600         # NVARCHAR(600) em etl_maestro_conversa.motivo (UTF-16)
LIMITE_CENARIO = 40

ORIENTACAO_ADMIN = ("Este cenário ainda não é atendido pelos parâmetros do Orquestra. "
                    "Procure o administrador do Orquestra para avaliar a inclusão — "
                    "o pedido ficou registrado.")
ERRO_SEM_110 = ("Maestro indisponível: migration 110 pendente "
                "(tabelas dbo.etl_maestro_cenario / dbo.etl_maestro_conversa).")

_SEM_TABELA_RE = re.compile(r"Invalid object name", re.I)
_PLACEHOLDER_RE = re.compile(r"^<[A-Za-z_][A-Za-z0-9_]*>$")
# `(?:(?!```).)*` impede o miolo de atravessar uma fence: com `.*?` uma fence
# anterior aberta com `{` e sem `}` engolia o bloco final válido (achado 2 da
# revisão adversarial da F1) e um nao_atendido virava `pergunta` em silêncio.
_BLOCO_JSON_RE = re.compile(r"```[ \t]*(?:json)?[ \t]*\n?(\{(?:(?!```).)*\})\s*```", re.S | re.I)

# Tipo do ISX (extendedType/typeCode, minúsculo) → tipo DataStage do Orquestra.
# Espelha ISX_TIPO de ui-react/src/lib/dsParams.ts (F6).
ISX_TIPO = {
    "string": "String", "integer": "Integer", "float": "Float", "date": "Date",
    "time": "Time", "timestamp": "Timestamp", "pathname": "Pathname", "list": "List",
    "stringlist": "List", "encrypted": "Encrypted",
}


class MaestroIndisponivel(Exception):
    """A migration 110 não foi aplicada (ou a tabela sumiu)."""


def _sem_tabela(e: Exception) -> bool:
    return bool(_SEM_TABELA_RE.search(str(e)))


# ── Leituras (cur) ───────────────────────────────────────────────────────────

def enabled(cur) -> bool:
    """`maestro_enabled` em etl_app_config. Degrada para False (tabela ausente,
    chave ausente): o botão some da tela em vez de a tela quebrar."""
    try:
        cur.execute("SELECT config_value FROM dbo.etl_app_config WHERE config_key = ?", (K_ENABLED,))
        row = cur.fetchone()
    except Exception:
        return False
    return bool(row) and str(row[0] or "").strip() == "1"


def carregar_catalogo(cur) -> list[dict]:
    """Cenários ATIVOS: [{codigo, titulo, descricao, receita}] — receita já
    como dict (linha com JSON inválido é pulada, não derruba o Maestro)."""
    try:
        cur.execute(
            "SELECT codigo, titulo, descricao, receita_json FROM dbo.etl_maestro_cenario "
            "WHERE ativo = 1 ORDER BY id")
        rows = cur.fetchall()
    except Exception as e:
        if _sem_tabela(e):
            raise MaestroIndisponivel(ERRO_SEM_110) from e
        raise
    saida: list[dict] = []
    for codigo, titulo, descricao, receita_json in rows:
        try:
            receita = json.loads(receita_json or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(receita, dict):
            continue
        saida.append({"codigo": str(codigo), "titulo": str(titulo or ""),
                      "descricao": str(descricao or ""), "receita": receita})
    return saida


def parametros_declarados(cur, pipeline: str | None, job: str | None) -> dict:
    """O que o job DECLARA segundo o lineage ISX já extraído (106):
    {disponivel, status, extracted_at, itens: [{name, type}]}. Sem pipeline/job,
    sem tabela ou sem extração → disponivel=False (o Maestro pede os nomes)."""
    vazio = {"disponivel": False, "status": None, "extracted_at": None, "itens": []}
    if not pipeline or not job:
        return vazio
    try:
        from services import lineage_isx as svc
        cab = svc.cabecalho(cur, pipeline, job)
    except Exception:
        return vazio
    if not cab:
        return vazio
    try:
        params = json.loads(cab.get("parameters_json") or "[]")
    except (TypeError, ValueError):
        params = []
    itens = []
    for p in params if isinstance(params, list) else []:
        if not isinstance(p, dict):
            continue
        nome = str(p.get("name") or "").strip()
        if not nome:
            continue
        itens.append({"name": nome, "type": str(p.get("type") or "").strip().lower()})
    status = str(cab.get("status") or "").strip() or None
    extracted_at = cab.get("extracted_at")
    if hasattr(extracted_at, "strftime"):
        extracted_at = extracted_at.strftime("%Y-%m-%d %H:%M")
    return {"disponivel": status == "ok", "status": status,
            "extracted_at": str(extracted_at) if extracted_at else None, "itens": itens}


def defaults_pipeline(cur, pipeline: str | None) -> list[dict]:
    """Defaults da 108 (nome/tipo/origem), sem valor Encrypted."""
    if not pipeline:
        return []
    try:
        linhas = _defaults_pipeline_108(cur, pipeline)
    except Exception:
        return []
    return sanear_editor(linhas)


# ── Puro: contexto ───────────────────────────────────────────────────────────

_COLS = ("param_name", "param_type", "param_source", "param_value",
         "param_offset_meses", "param_ancora", "param_offset_dias", "param_formato")


def sanear_editor(params) -> list[dict]:
    """As linhas do editor como o modelo pode vê-las: só as colunas do
    contrato, valor de Encrypted SEMPRE removido (o modelo não precisa dele
    para orientar e o provedor pode ser externo), valores truncados, no máximo
    MAX_PARAMS_EDITOR linhas."""
    saida: list[dict] = []
    for p in (params or [])[:MAX_PARAMS_EDITOR]:
        if not isinstance(p, dict):
            continue
        nome = str(p.get("param_name") or "").strip()
        if not nome:
            continue
        item: dict = {}
        for c in _COLS:
            v = p.get(c)
            if v is None or v == "":
                continue
            if isinstance(v, str):
                v = v[:MAX_VALOR_EDITOR]
            item[c] = v
        if str(p.get("param_type") or "") == "Encrypted":
            item.pop("param_value", None)
        item["param_name"] = nome[:jp.LIMITE_NOME]
        saida.append(item)
    return saida


def _lista(valores, rotulos: dict | None = None) -> str:
    if rotulos:
        return ", ".join(f"{v} ({rotulos[v]})" if v in rotulos else v for v in valores)
    return ", ".join(valores)


def system_prompt(catalogo: list[dict], contexto: dict) -> str:
    """O prompt inteiro, gerado do vocabulário de job_params + catálogo +
    contexto da etapa. Mudou o vocabulário, muda aqui sem ninguém lembrar."""
    linhas = [
        "Você é o Maestro, assistente do ORQUESTRA (gestão de pipelines) que ajuda a preencher os "
        "PARÂMETROS DE EXECUÇÃO de uma etapa DataStage nas telas Etapas e Fluxos. O usuário descreve "
        "o cenário; você explica como preencher cada campo e devolve uma proposta estruturada. "
        "Você NÃO salva nada: o usuário aplica a proposta no editor e salva a etapa.",
        "",
        "## Como o Orquestra envia parâmetros",
        "- A cada execução o operador monta `-param nome=valor` no `dsjob -run`. O job precisa DECLARAR "
        "o parâmetro no Designer (o DataStage distingue maiúsculas de minúsculas); membro de Parameter "
        "Set é `PSet.Param`. Nome: letras, números e _, no máximo um ponto, até "
        f"{jp.LIMITE_NOME} caracteres.",
        "- Campos de cada parâmetro: nome, tipo, origem e — só com origem de data — meses, âncora, dias "
        "e formato. Com origem fixa: valor.",
        f"- Tipos: {_lista(jp.DS_PARAM_TYPES)}. Origem de data só com tipo "
        f"{_lista(jp.DS_TIPOS_COM_DATA)}; origem run_id só com String.",
        "- Origens: fixo (valor digitado, igual em toda execução); data_referencia (a data de "
        "referência da corrida — a ODATE definida na agenda; é a origem RECOMENDADA para cargas "
        "periódicas); data_logica (data lógica do Airflow); data_execucao (data em que a etapa "
        "disparou, relógio do worker); run_id (o run_id do Airflow, para rastreabilidade).",
        "- Cálculo de data, SEMPRE nesta ordem: meses → âncora → dias → formato. O deslocamento de "
        "meses vem antes da âncora, por isso '-1 mês + fim do mês' é o último dia do mês anterior em "
        "qualquer dia (31/03 −1 mês = 28/02 → fim do mês = 28/02). Dia truncado ao último válido do mês.",
        f"- Âncoras: {_lista(jp.DS_PARAM_ANCORAS, jp.ROTULO_ANCORA)}. Semana = segunda a domingo.",
        f"- Limites: meses ±{jp.LIMITE_MESES}, dias ±{jp.LIMITE_DIAS}.",
        "- Formato (strftime): só as diretivas %Y %m %d %y %H %M %S e os separadores - / . _ : "
        f"(padrão {jp.FORMATO_PADRAO}; até {jp.LIMITE_FORMATO} caracteres). Para AAAAMM use %Y%m.",
        "- Valor fixo por tipo: Integer inteiro; Float decimal com ponto; Date AAAA-MM-DD; Time HH:MM:SS; "
        "Timestamp 'AAAA-MM-DD HH:MM:SS'; Pathname caminho ABSOLUTO sem ~, espaços ou aspas; "
        "String/List livre sem quebra de linha.",
        "- Encrypted: cifrado no banco, nunca em log. NUNCA peça, repita nem proponha o VALOR de um "
        "Encrypted: proponha o parâmetro sem valor e diga para digitar no editor. Use Encrypted só para "
        "parâmetro que o job declara como Encrypted (senão o DataStage grava o valor em claro no log dele).",
        "- Defaults do pipeline valem para toda etapa cujo job declara o nome; a etapa sobrepõe pelo "
        "mesmo nome. Se o pedido já é atendido por um default, diga isso em vez de duplicar.",
        "- Não calcule datas nem cite datas resultantes: o Orquestra calcula a prévia da proposta e a "
        "mostra ao usuário com a data de referência escolhida.",
        "",
        "## O que você NÃO pode prometer (responda nao_atendido, com o motivo)",
        "- Dias úteis, feriados, calendário: 'último dia útil', 'D-2 útil', 'próximo dia útil'.",
        "- Valor lido de tabela, arquivo, variável de ambiente, outro job ou outra execução.",
        "- Condições (se… então), listas de datas, laços, mais de um valor por parâmetro, horário "
        "calculado (as âncoras só movem a DATA).",
        "- Qualquer origem, âncora, tipo ou formato fora das listas acima.",
        "- Cenário que não está no catálogo abaixo e não se monta com este vocabulário.",
        "",
        "## Catálogo de cenários atendidos",
    ]
    if catalogo:
        for c in catalogo:
            receita = json.dumps(c["receita"].get("params", []), ensure_ascii=False, separators=(",", ":"))
            linhas.append(f"- [{c['codigo']}] {c['titulo']} — {c['descricao']} Receita: {receita}")
    else:
        linhas.append("- (catálogo vazio: só o vocabulário acima)")
    linhas += [
        "Nomes entre <> nas receitas são marcadores: troque pelos nomes que o job declara (abaixo) ou "
        "que o usuário informar. Sem lineage e sem nome informado, use nomes convencionais (pDataIni, "
        "pDataFim, pData) e avise que precisam ser IGUAIS aos do Designer, ou faça uma pergunta.",
        "",
        "## Contexto desta etapa",
    ]
    pipeline = contexto.get("pipeline_name") or "(não informado)"
    job = contexto.get("job_name") or "(não informado)"
    linhas.append(f"- Pipeline: {pipeline} · Etapa (job DataStage): {job}")
    decl = contexto.get("declarados") or {}
    if decl.get("disponivel") and decl.get("itens"):
        itens = ", ".join(f"{i['name']} ({i['type'] or 'tipo desconhecido'})" for i in decl["itens"])
        quando = f" (extração de {decl['extracted_at']})" if decl.get("extracted_at") else ""
        linhas.append(f"- Parâmetros que o job declara segundo o lineage ISX{quando}: {itens}. "
                      "Use SÓ estes nomes; 'parameterset' é um conjunto (os membros são PSet.Param).")
    elif decl.get("disponivel"):
        linhas.append("- O lineage ISX diz que o job NÃO declara parâmetro nenhum: avise que qualquer "
                      "parâmetro falharia no disparo até o job declará-lo no Designer.")
    else:
        linhas.append("- Sem lineage ISX extraído para este job: os nomes precisam vir do usuário "
                      "(ou confira-os no Designer). Diga isso.")
    defaults = contexto.get("defaults") or []
    if defaults:
        linhas.append("- Defaults do pipeline: "
                      + json.dumps(defaults, ensure_ascii=False, separators=(",", ":")))
    editor = contexto.get("editor") or []
    if editor:
        linhas.append("- Linhas já no editor desta etapa (valores Encrypted omitidos): "
                      + json.dumps(editor, ensure_ascii=False, separators=(",", ":")))
    else:
        linhas.append("- O editor desta etapa está vazio.")
    linhas += [
        f"- Data de referência que o usuário escolheu para a prévia: {contexto.get('referencia') or date.today().isoformat()}.",
        "",
        "## Como responder",
        "- Português do Brasil, direto. Primeiro confirme em uma frase o cenário entendido. Depois, para "
        "cada parâmetro, uma linha por campo: Nome, Tipo, Origem, Meses, Âncora, Dias, Formato (ou "
        "Valor, na origem fixa). Se faltar uma informação essencial (ex.: os nomes), faça UMA pergunta "
        "objetiva em vez de adivinhar.",
        "- Termine SEMPRE com um único bloco ```json neste contrato (e nada depois dele):",
        '{"status": "atendido", "cenario": "<codigo do catálogo ou null>", "motivo": null, '
        '"params": [{"param_name": "pDataIni", "param_type": "Date", "param_source": "data_referencia", '
        '"param_value": null, "param_offset_meses": -1, "param_ancora": "inicio_mes", '
        '"param_offset_dias": 0, "param_formato": "%Y-%m-%d"}]}',
        '{"status": "pergunta", "cenario": null, "motivo": null, "params": []}',
        '{"status": "nao_atendido", "cenario": null, "motivo": "<por que, em uma frase>", "params": []}',
        "- Com origem fixo ou run_id, meses/âncora/dias/formato ficam null. Com origem de data, "
        "param_value fica null. Encrypted vai com param_value null.",
        "- Em nao_atendido, diga ao usuário que o pedido fica registrado e que ele deve procurar o "
        "administrador do Orquestra. Nunca proponha algo 'parecido' como se fosse o pedido.",
    ]
    return "\n".join(linhas)


# ── Puro: receita e proposta ─────────────────────────────────────────────────

def validar_receita(receita) -> tuple[list[dict], list[str]]:
    """A receita de um cenário passa pela MESMA régua do salvar, com os
    marcadores `<NOME>` trocados por nomes válidos. É o que impede o catálogo
    (semente ou admin) de prometer o que a régua recusaria."""
    if not isinstance(receita, dict):
        return [], ["receita deve ser um objeto com a chave params"]
    params = receita.get("params")
    if not isinstance(params, list) or not params:
        return [], ["receita sem params"]
    trocados = []
    for i, p in enumerate(params, start=1):
        if not isinstance(p, dict):
            trocados.append(p)
            continue
        q = dict(p)
        nome = str(q.get("param_name") or "")
        if _PLACEHOLDER_RE.match(nome):
            q["param_name"] = f"p_{i}"
        if q.get("param_type") == "Encrypted" and not q.get("param_value"):
            q["param_value"] = jp.ENCRYPTED_MASCARA
        trocados.append(q)
    return jp.normalizar_lista(trocados)


def extrair_proposta(texto: str) -> tuple[str, dict | None]:
    """(texto sem o bloco, proposta) — o ÚLTIMO bloco ```json que é um objeto
    com `status`. Sem bloco válido → proposta None (o modelo só conversou)."""
    texto = texto or ""
    achado = None
    for m in _BLOCO_JSON_RE.finditer(texto):
        try:
            obj = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(obj, dict) and "status" in obj:
            achado = (m, obj)
    if not achado:
        return texto.strip(), None
    m, obj = achado
    limpo = (texto[:m.start()] + texto[m.end():]).strip()
    return limpo, obj


def _tipo_ds_do_isx(tipo: str | None) -> str | None:
    return ISX_TIPO.get((tipo or "").strip().lower())


def avaliar(proposta: dict | None, referencia: date, declarados: dict | None,
            codigos_catalogo: set[str] | None = None) -> dict:
    """Decide o status FINAL da rodada e monta o que a tela recebe:
    {status, cenario, motivo, params, previa, avisos}.

    A régua manda: `atendido` do modelo com params que não passam em
    normalizar_lista vira `nao_atendido` com o erro. Encrypted é aceito sem
    valor (o usuário digita no editor) e sai com param_value '' + tem_valor
    False. Nome que o ISX não lista (quando há ISX) e tipo diferente do
    declarado viram AVISOS — a conferência definitiva é o -lparams do disparo."""
    avisos: list[str] = []
    if not proposta:
        return {"status": STATUS_PERGUNTA, "cenario": None, "motivo": None,
                "params": None, "previa": None, "avisos": avisos}
    status = str(proposta.get("status") or "").strip().lower()
    cenario = str(proposta.get("cenario") or "").strip()[:LIMITE_CENARIO] or None
    if codigos_catalogo is not None and cenario not in (codigos_catalogo or set()):
        cenario = None
    motivo = str(proposta.get("motivo") or "").strip() or None
    if motivo:
        motivo = cortar_utf16(motivo, LIMITE_MOTIVO)

    if status == STATUS_NAO_ATENDIDO:
        return {"status": STATUS_NAO_ATENDIDO, "cenario": cenario,
                "motivo": motivo or "o cenário não se monta com o vocabulário atual",
                "params": None, "previa": None, "avisos": avisos}
    if status != STATUS_ATENDIDO:
        return {"status": STATUS_PERGUNTA, "cenario": cenario, "motivo": None,
                "params": None, "previa": None, "avisos": avisos}

    brutos = proposta.get("params")
    if not isinstance(brutos, list) or not brutos:
        return {"status": STATUS_NAO_ATENDIDO, "cenario": cenario,
                "motivo": "a resposta veio como atendida mas sem parâmetros",
                "params": None, "previa": None, "avisos": avisos}
    para_validar = []
    for p in brutos:
        if not isinstance(p, dict):
            para_validar.append(p)
            continue
        q = {c: p.get(c) for c in _COLS}
        if q.get("param_type") == "Encrypted":
            q["param_value"] = jp.ENCRYPTED_MASCARA   # valida sem valor; o usuário digita
        para_validar.append(q)
    validos, erros = jp.normalizar_lista(para_validar)
    if erros:
        return {"status": STATUS_NAO_ATENDIDO, "cenario": cenario,
                "motivo": cortar_utf16("a proposta não passou na régua dos parâmetros: "
                                       + "; ".join(erros), LIMITE_MOTIVO),
                "params": None, "previa": None, "avisos": avisos}

    previa, erros_previa = jp.resolver_preview(referencia, validos)
    if erros_previa:
        return {"status": STATUS_NAO_ATENDIDO, "cenario": cenario,
                "motivo": cortar_utf16("a prévia falhou: " + "; ".join(erros_previa), LIMITE_MOTIVO),
                "params": None, "previa": None, "avisos": avisos}

    decl = declarados or {}
    por_nome = {i["name"]: i.get("type") for i in decl.get("itens") or []}
    saida: list[dict] = []
    for v in validos:
        item = dict(v)
        if item["param_type"] == "Encrypted":
            item["param_value"] = ""
            item["tem_valor"] = False
        saida.append(item)
        if decl.get("disponivel"):
            if item["param_name"] not in por_nome:
                avisos.append(f"o job não declara '{item['param_name']}' segundo o lineage ISX"
                              + (f" (extração de {decl['extracted_at']})" if decl.get("extracted_at") else "")
                              + " — confira o nome no Designer antes de salvar")
            else:
                tipo_ds = _tipo_ds_do_isx(por_nome[item["param_name"]])
                if tipo_ds and tipo_ds != item["param_type"]:
                    avisos.append(f"o job declara '{item['param_name']}' como {tipo_ds}; "
                                  f"a proposta usa {item['param_type']}")
    if not decl.get("disponivel"):
        avisos.append("sem lineage ISX deste job: confira os nomes no Designer — "
                      "nome que o job não declara falha antes do disparo")
    return {"status": STATUS_ATENDIDO, "cenario": cenario, "motivo": None,
            "params": saida, "previa": previa, "avisos": avisos}


# ── Registro (cur) ───────────────────────────────────────────────────────────

def registrar(cur, *, conversa_id: str, matricula: str, pipeline: str | None, job: str | None,
              mensagem: str, resposta: str | None, status: str, cenario: str | None,
              params: list[dict] | None, motivo: str | None, modelo: str | None,
              duracao_ms: int | None) -> None:
    """Uma linha por rodada. `params` já vem sem valor Encrypted (avaliar);
    aqui só se garante isso de novo antes de virar JSON."""
    proposta_json = None
    if params:
        limpos = []
        for p in params:
            q = dict(p)
            if q.get("param_type") == "Encrypted":
                q["param_value"] = ""
            limpos.append(q)
        proposta_json = json.dumps({"params": limpos}, ensure_ascii=False)
    try:
        cur.execute(
            "INSERT INTO dbo.etl_maestro_conversa (conversa_id, matricula, pipeline_name, job_name, "
            " mensagem, resposta, status, cenario_codigo, proposta_json, motivo, modelo, duracao_ms) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (conversa_id[:36], (matricula or "")[:20], pipeline, job, mensagem, resposta, status[:20],
             (cenario or None), proposta_json,
             cortar_utf16(motivo, LIMITE_MOTIVO) if motivo else None,
             (modelo or None) and str(modelo)[:100], duracao_ms))
    except Exception as e:
        if _sem_tabela(e):
            raise MaestroIndisponivel(ERRO_SEM_110) from e
        raise


def historico(cur, matricula: str, limite: int = 20) -> list[dict]:
    """As últimas `limite` conversas do usuário (pela rodada mais recente),
    cada uma com TODAS as suas rodadas em ordem, sem as rodadas 'erro':
    [{conversa_id, iniciado_em, pipeline_name, job_name,
      rodadas: [{mensagem, resposta, status}]}].

    Escolhe as CONVERSAS primeiro e só então busca as linhas: um `TOP n`
    sobre as linhas cortava conversas longas em silêncio e trocava o
    `iniciado_em` (achado 3 da revisão adversarial da F1)."""
    mat = (matricula or "")[:20]
    try:
        cur.execute(
            "SELECT c.conversa_id, c.pipeline_name, c.job_name, c.mensagem, c.resposta, c.status, "
            "       CONVERT(VARCHAR(19), c.criado_em, 120) "
            "FROM dbo.etl_maestro_conversa c "
            "JOIN (SELECT TOP (?) conversa_id, MAX(criado_em) AS ultimo "
            "      FROM dbo.etl_maestro_conversa WHERE matricula = ? AND status <> 'erro' "
            "      GROUP BY conversa_id ORDER BY ultimo DESC) u ON u.conversa_id = c.conversa_id "
            "WHERE c.matricula = ? AND c.status <> 'erro' "
            "ORDER BY u.ultimo DESC, c.criado_em, c.id", (int(limite), mat, mat))
        rows = cur.fetchall()
    except Exception as e:
        if _sem_tabela(e):
            raise MaestroIndisponivel(ERRO_SEM_110) from e
        raise
    grupos: dict[str, dict] = {}
    ordem: list[str] = []
    for cid, pipeline, job, mensagem, resposta, status, quando in rows:
        g = grupos.get(cid)
        if g is None:
            g = grupos[cid] = {"conversa_id": cid, "iniciado_em": quando, "pipeline_name": pipeline,
                               "job_name": job, "rodadas": []}
            ordem.append(cid)
        g["rodadas"].append({"mensagem": mensagem, "resposta": resposta, "status": status})
    return [grupos[c] for c in ordem]


def sugestoes(catalogo: list[dict], maximo: int = 4) -> list[str]:
    """Frases de abertura do chat: o primeiro exemplo de cada cenário."""
    saida: list[str] = []
    for c in catalogo:
        exemplos = c.get("receita", {}).get("exemplos") or []
        frase = str(exemplos[0]).strip() if exemplos else c.get("titulo", "")
        if frase and frase not in saida:
            saida.append(frase)
        if len(saida) >= maximo:
            break
    return saida
