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
from services.ssh_arquivos import cortar_utf16, utf16_len

K_ENABLED = "maestro_enabled"

STATUS_ATENDIDO = "atendido"
STATUS_NAO_ATENDIDO = "nao_atendido"
STATUS_PERGUNTA = "pergunta"
# O usuário só perguntou COMO algo funciona (herança, datas, rastro): resposta
# sem proposta, e não é pedido não atendido nem pergunta do Maestro.
STATUS_EXPLICACAO = "explicacao"
STATUS_ERRO = "erro"
STATUS_DO_MODELO = (STATUS_ATENDIDO, STATUS_NAO_ATENDIDO, STATUS_PERGUNTA, STATUS_EXPLICACAO)

# Onde o usuário está: na ETAPA (seção "Parâmetros do job") ou no PIPELINE
# (wizard, seção "Parâmetros DataStage do pipeline" — os defaults).
NIVEL_ETAPA = "etapa"
NIVEL_PIPELINE = "pipeline"
NIVEIS = (NIVEL_ETAPA, NIVEL_PIPELINE)
MAX_JOBS_PIPELINE = 30

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


def parametros_declarados_pipeline(cur, pipeline: str | None) -> dict:
    """Nível pipeline: o que CADA etapa DataStage do pipeline declara (lineage
    ISX), para o Maestro dizer quais etapas vão herdar um default —
    {nivel: 'pipeline', jobs: [{job_name, disponivel, extracted_at, itens}]}.
    Sem pipeline (cadastro novo) ou sem etapas → jobs vazio."""
    saida = {"nivel": NIVEL_PIPELINE, "jobs": [], "truncados": 0}
    if not pipeline:
        return saida
    try:
        from services.rerun_params import _jobs_datastage
        jobs = sorted(_jobs_datastage(cur, pipeline).values())
    except Exception:
        return saida
    for job in jobs[:MAX_JOBS_PIPELINE]:
        d = parametros_declarados(cur, pipeline, job)
        saida["jobs"].append({"job_name": job, "disponivel": d["disponivel"],
                              "extracted_at": d["extracted_at"], "itens": d["itens"]})
    # O teto é DITO, não silencioso: uma etapa fora dele que declara o nome
    # não pode virar "ninguém declara" (achado 3 da revisão do complemento).
    saida["truncados"] = max(0, len(jobs) - MAX_JOBS_PIPELINE)
    return saida


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
            titulo = " ".join(str(c["titulo"]).split())
            descricao = " ".join(str(c["descricao"]).split())
            linhas.append(f"- [{c['codigo']}] {titulo} — {descricao} Receita: {receita}")
    else:
        linhas.append("- (catálogo vazio: só o vocabulário acima)")
    linhas += [
        "Nomes entre <> nas receitas são marcadores: troque pelos nomes que o job declara (abaixo) ou "
        "que o usuário informar. Sem lineage e sem nome informado, use nomes convencionais (pDataIni, "
        "pDataFim, pData) e avise que precisam ser IGUAIS aos do Designer, ou faça uma pergunta.",
        "",
        "## Como os parâmetros se comportam (perguntas que o usuário costuma fazer — responda com status "
        "explicacao quando ele só quer entender, sem pedir uma proposta)",
        "- Parâmetro cadastrado no PIPELINE (seção 'Parâmetros DataStage do pipeline' do cadastro) é um "
        "DEFAULT: vale para toda etapa DataStage do pipeline cujo job DECLARA o nome (conferido no "
        "`dsjob -lparams` a cada disparo). As etapas HERDAM sem configurar nada nelas. Job que não "
        "declara o nome simplesmente não o recebe (sem erro; o nome ignorado sai no log da task). "
        "Etapas shell, python e stored procedure nunca recebem parâmetro de DataStage.",
        "- A ETAPA sobrepõe o default pelo mesmo nome (caixa exata): cadastre na etapa só quando ela "
        "precisar de um valor diferente. O painel da etapa mostra 'Defaults do pipeline: … · sobreposto "
        "pela etapa'.",
        "- O valor NÃO fica gravado: a cada disparo o operador calcula de novo a partir da base da "
        "origem. Com origem data_referencia (a recomendada) a base é a DATA DE REFERÊNCIA da corrida "
        "(a ODATE definida no check_agenda, a mesma que rege a malha e as dependências) — não o relógio; "
        "só a origem data_execucao usa o relógio do worker. Exemplo com data_referencia: pipeline "
        "mensal agendado todo dia 05 com '-1 mês + início do mês' e '-1 mês + fim do mês' manda "
        "2026-09-01 e 2026-09-30 na corrida de 05/10/2026, e 2026-10-01 e 2026-10-31 na de 05/11/2026. "
        "Se a corrida atrasar e a etapa rodar no dia 06, a referência continua sendo a do dia 05. "
        "(Este exemplo fixo pode ser citado; para o pedido do usuário, não calcule datas — a prévia é "
        "do Orquestra.)",
        "- A ordem meses → âncora → dias garante 'mês anterior' em qualquer dia do mês (31/03 −1 mês = "
        "28/02 → fim do mês = 28/02).",
        "- Reexecutar uma corrida antiga usa a referência DAQUELA corrida; o modal de reexecução deixa "
        "sobrepor um valor só naquela vez (Encrypted não).",
        "- Mudar um parâmetro (do pipeline ou da etapa) NÃO exige republicar a DAG: é lido a cada disparo.",
        "- Conferir antes de rodar: 'Simular com a referência' na própria seção mostra o valor que iria ao "
        "DataStage para a data digitada. Depois de rodar, o rastro está na linha '[DS] parâmetros:' do "
        "log da task e no bloco 'Parâmetros enviados ao DataStage' do detalhe da execução.",
        "- Erro clássico: nome com caixa diferente do Designer (dat_inicio ≠ Dat_Inicio) — no pipeline o "
        "default fica ignorado em todas as etapas; na etapa, o disparo falha antes de rodar.",
        "",
    ]
    nivel = contexto.get("nivel") or NIVEL_ETAPA
    pipeline = contexto.get("pipeline_name") or "(não informado)"
    decl = contexto.get("declarados") or {}
    if nivel == NIVEL_PIPELINE:
        linhas += [
            "## Onde o usuário está: cadastro do PIPELINE (defaults)",
            f"- Pipeline: {pipeline}. O que você propor vira DEFAULT DO PIPELINE: chega a toda etapa "
            "DataStage cujo job declarar o nome, sem configurar nada nas etapas. Diga isso quando propuser.",
        ]
        jobs = decl.get("jobs") or []
        if jobs:
            for j in jobs:
                if j.get("disponivel") and j.get("itens"):
                    nomes = ", ".join(i["name"] for i in j["itens"])
                    linhas.append(f"- Etapa {j['job_name']} declara: {nomes}.")
                elif j.get("disponivel"):
                    linhas.append(f"- Etapa {j['job_name']} não declara parâmetro nenhum (lineage ISX).")
                else:
                    linhas.append(f"- Etapa {j['job_name']}: sem lineage ISX (nomes a confirmar no Designer).")
            if decl.get("truncados"):
                linhas.append(f"- E mais {decl['truncados']} etapa(s) DataStage não conferida(s) (teto de "
                              f"{MAX_JOBS_PIPELINE}): diga que a lista acima é parcial.")
            linhas.append("- Ao propor um nome, diga QUAIS etapas o declaram (vão herdar) e quais não "
                          "(vão ignorar). Prefira nomes que várias etapas declaram (ex.: membros de "
                          "Parameter Set, PSet.Param).")
        else:
            linhas.append("- O pipeline ainda não tem etapas DataStage cadastradas (ou ainda não foi salvo): "
                          "proponha os nomes que o usuário informar e avise que só as etapas cujo job os "
                          "declarar vão herdar.")
    else:
        job = contexto.get("job_name") or "(não informado)"
        linhas += ["## Onde o usuário está: cadastro da ETAPA",
                   f"- Pipeline: {pipeline} · Etapa (job DataStage): {job}"]
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
            linhas.append("- Defaults do pipeline (a etapa herda; cadastre na etapa só para sobrepor): "
                          + json.dumps(defaults, ensure_ascii=False, separators=(",", ":")))
    editor = contexto.get("editor") or []
    onde = "do pipeline" if nivel == NIVEL_PIPELINE else "desta etapa"
    if editor:
        linhas.append(f"- Linhas já no editor {onde} (valores Encrypted omitidos): "
                      + json.dumps(editor, ensure_ascii=False, separators=(",", ":")))
    else:
        linhas.append(f"- O editor {onde} está vazio.")
    linhas += [
        f"- Data de referência que o usuário escolheu para a prévia: {contexto.get('referencia') or date.today().isoformat()}.",
        "",
        "## Como responder",
        "- Português do Brasil, direto. Primeiro confirme em uma frase o cenário entendido. Depois, para "
        "cada parâmetro, uma linha por campo: Nome, Tipo, Origem, Meses, Âncora, Dias, Formato (ou "
        "Valor, na origem fixa). Se faltar uma informação essencial (ex.: os nomes), faça UMA pergunta "
        "objetiva em vez de adivinhar.",
        "- Se o usuário só quer ENTENDER (herança, datas, rastro, 'as etapas herdam?'), explique com a "
        "seção 'Como os parâmetros se comportam' e use status explicacao, sem proposta.",
        "- Termine SEMPRE com um único bloco ```json neste contrato (e nada depois dele):",
        '{"status": "atendido", "cenario": "<codigo do catálogo ou null>", "motivo": null, '
        '"params": [{"param_name": "pDataIni", "param_type": "Date", "param_source": "data_referencia", '
        '"param_value": null, "param_offset_meses": -1, "param_ancora": "inicio_mes", '
        '"param_offset_dias": 0, "param_formato": "%Y-%m-%d"}]}',
        '{"status": "pergunta", "cenario": null, "motivo": null, "params": []}',
        '{"status": "explicacao", "cenario": null, "motivo": null, "params": []}',
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
    # Marcador repetido é checado ANTES da troca: `<D>` duas vezes viraria
    # p_1/p_2 (distintos) e passaria — e o Maestro entregaria dois nomes
    # iguais que a régua do salvar derruba como duplicata (achado 4 da
    # revisão adversarial da F3). Caixa exata, como o DataStage.
    vistos: set[str] = set()
    repetidos: list[str] = []
    trocados = []
    for i, p in enumerate(params, start=1):
        if not isinstance(p, dict):
            trocados.append(p)
            continue
        q = dict(p)
        nome = str(q.get("param_name") or "").strip()
        if nome:
            if nome in vistos and nome not in repetidos:
                repetidos.append(nome)
            vistos.add(nome)
        if _PLACEHOLDER_RE.match(nome):
            q["param_name"] = f"p_{i}"
        if q.get("param_type") == "Encrypted" and not q.get("param_value"):
            q["param_value"] = jp.ENCRYPTED_MASCARA
        trocados.append(q)
    validos, erros = jp.normalizar_lista(trocados)
    erros = [f"marcador/nome repetido na receita: {r}" for r in repetidos] + erros
    return (validos if not erros else []), erros


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
    if status == STATUS_EXPLICACAO:
        return {"status": STATUS_EXPLICACAO, "cenario": None, "motivo": None,
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
    saida: list[dict] = []
    if decl.get("nivel") == NIVEL_PIPELINE:
        # Nível pipeline: o aviso diz QUAIS etapas vão herdar cada nome (as que
        # o declaram no ISX) e quais vão ignorar — é a pergunta que o usuário faz.
        jobs = decl.get("jobs") or []
        com_isx = [j for j in jobs if j.get("disponivel")]
        truncados = int(decl.get("truncados") or 0)
        for v in validos:
            item = dict(v)
            if item["param_type"] == "Encrypted":
                item["param_value"] = ""
                item["tem_valor"] = False
            saida.append(item)
            if not com_isx:
                continue
            herdam = [j["job_name"] for j in com_isx if any(i["name"] == item["param_name"] for i in j.get("itens") or [])]
            ignoram = [j["job_name"] for j in com_isx if j["job_name"] not in herdam]
            if herdam:
                avisos.append(f"'{item['param_name']}' vai para: {', '.join(herdam)}"
                              + (f"; ignorado por (não declara): {', '.join(ignoram)}" if ignoram else ""))
            else:
                avisos.append(f"nenhuma etapa com lineage ISX declara '{item['param_name']}' — "
                              "confira o nome no Designer; o default seria ignorado por todas"
                              + (" as conferidas" if truncados else ""))
            # Tipo divergente do declarado — mesmo aviso do nível etapa.
            for j in com_isx:
                for i in j.get("itens") or []:
                    if i["name"] == item["param_name"]:
                        tipo_ds = _tipo_ds_do_isx(i.get("type"))
                        if tipo_ds and tipo_ds != item["param_type"]:
                            avisos.append(f"{j['job_name']} declara '{item['param_name']}' como {tipo_ds}; "
                                          f"a proposta usa {item['param_type']}")
        if not jobs:
            avisos.append("o pipeline ainda não tem etapas DataStage cadastradas (ou ainda não foi salvo): "
                          "só as etapas cujo job declarar o nome vão herdar — confira no Designer")
        elif not com_isx:
            avisos.append("nenhuma etapa deste pipeline tem lineage ISX: confira os nomes no Designer — "
                          "só as etapas cujo job declarar o nome vão herdar")
        sem_isx = [j["job_name"] for j in jobs if not j.get("disponivel")]
        if com_isx and sem_isx:
            avisos.append(f"sem lineage ISX (não dá para saber se herdam): {', '.join(sem_isx)}")
        if truncados:
            avisos.append(f"e mais {truncados} etapa(s) DataStage não conferida(s) (teto de {MAX_JOBS_PIPELINE})")
        return {"status": STATUS_ATENDIDO, "cenario": cenario, "motivo": None,
                "params": saida, "previa": previa, "avisos": avisos}

    por_nome = {i["name"]: i.get("type") for i in decl.get("itens") or []}
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


# ── Admin (F3): interruptor, catálogo e pedidos ──────────────────────────────

CODIGO_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
LIMITE_TITULO = 120        # NVARCHAR(120)
LIMITE_DESCRICAO = 600     # NVARCHAR(600)
LIMITE_EXEMPLO = 200
MAX_EXEMPLOS = 10
# Retenção das conversas (dags/etl_log_cleanup.py apaga o que passa disso).
RETENCAO_CONVERSAS_DIAS = 180


class CodigoExistente(Exception):
    """Outro cenário já usa o código."""


def validar_cenario(payload) -> tuple[dict, list[str]]:
    """O que o admin manda para gravar um cenário → (normalizado, erros).

    A receita passa pela MESMA régua do salvar (validar_receita): o catálogo
    não pode prometer o que o Orquestra recusaria. Os marcadores `<NOME>`
    ficam como estão na receita gravada — o Maestro os troca pelos nomes reais."""
    erros: list[str] = []
    if not isinstance(payload, dict):
        return {}, ["corpo inválido (esperado objeto)"]
    codigo = str(payload.get("codigo") or "").strip().lower()
    if not CODIGO_RE.match(codigo):
        erros.append("código: letras minúsculas, números e _, de 2 a 40 caracteres, começando por letra")
    # Título e descrição vão para UMA linha do system prompt: quebras de linha
    # e espaços repetidos colapsam (uma descrição com "## Como responder"
    # numa linha nova entraria no prompt como se fosse seção).
    titulo = " ".join(str(payload.get("titulo") or "").split())
    if not titulo:
        erros.append("título obrigatório")
    elif utf16_len(titulo) > LIMITE_TITULO:
        erros.append(f"título com mais de {LIMITE_TITULO} caracteres")
    descricao = " ".join(str(payload.get("descricao") or "").split())
    if not descricao:
        erros.append("descrição obrigatória — é o que o Maestro lê para reconhecer o cenário")
    elif utf16_len(descricao) > LIMITE_DESCRICAO:
        erros.append(f"descrição com mais de {LIMITE_DESCRICAO} caracteres")

    receita = payload.get("receita")
    if not isinstance(receita, dict):
        erros.append("receita deve ser um objeto {params, exemplos}")
        receita = {}
    _validos, erros_receita = validar_receita(receita)
    erros.extend(f"receita: {e}" for e in erros_receita)
    exemplos_raw = receita.get("exemplos")
    exemplos: list[str] = []
    if exemplos_raw is None:
        pass
    elif not isinstance(exemplos_raw, list):
        erros.append("exemplos deve ser uma lista de frases")
    else:
        for e in exemplos_raw:
            frase = str(e or "").strip()
            if not frase:
                continue
            if utf16_len(frase) > LIMITE_EXEMPLO:
                erros.append(f"exemplo com mais de {LIMITE_EXEMPLO} caracteres: '{frase[:30]}…'")
                continue
            if frase not in exemplos:
                exemplos.append(frase)
        if len(exemplos) > MAX_EXEMPLOS:
            erros.append(f"no máximo {MAX_EXEMPLOS} exemplos")
    params_limpos = []
    for p in receita.get("params") or []:
        if isinstance(p, dict):
            item = {c: p.get(c) for c in _COLS if p.get(c) not in (None, "")}
            # Valor de Encrypted NUNCA vai para a receita: ela vai inteira ao
            # system prompt (provedor pode ser externo) — a tela não oferece o
            # campo, mas o endpoint aceitava (achado 3 da revisão da F3).
            if item.get("param_type") == "Encrypted":
                item.pop("param_value", None)
            params_limpos.append(item)
    norm = {"codigo": codigo, "titulo": titulo, "descricao": descricao,
            "receita": {"params": params_limpos, "exemplos": exemplos},
            "ativo": bool(payload.get("ativo", True))}
    return norm, erros


def previa_da_receita(receita, referencia: date) -> tuple[list[dict], list[str]]:
    """A prévia de uma receita para a tela do admin ("Simular"): valida com os
    marcadores trocados e devolve os valores com os NOMES ORIGINAIS (`<DATA>`)."""
    validos, erros = validar_receita(receita)
    if erros:
        return [], erros
    originais: dict[str, str] = {}
    for i, p in enumerate(receita.get("params") or [], start=1):
        nome = str((p or {}).get("param_name") or "") if isinstance(p, dict) else ""
        if _PLACEHOLDER_RE.match(nome):
            originais[f"p_{i}"] = nome
    previa, erros_previa = jp.resolver_preview(referencia, validos)
    for item in previa:
        item["param_name"] = originais.get(item["param_name"], item["param_name"])
    return previa, erros_previa


_COLS_CENARIO = ("id", "codigo", "titulo", "descricao", "receita_json", "ativo",
                 "criado_em", "criado_por", "atualizado_em", "atualizado_por")
_SQL_CENARIO = ("SELECT id, codigo, titulo, descricao, receita_json, ativo, "
                "CONVERT(VARCHAR(19), criado_em, 120), criado_por, "
                "CONVERT(VARCHAR(19), atualizado_em, 120), atualizado_por FROM dbo.etl_maestro_cenario")


def _linha_cenario(row) -> dict:
    d = dict(zip(_COLS_CENARIO, row))
    try:
        receita = json.loads(d.pop("receita_json") or "{}")
    except (TypeError, ValueError):
        receita = {}
    if not isinstance(receita, dict):
        receita = {}
    d["receita"] = {"params": receita.get("params") or [], "exemplos": receita.get("exemplos") or []}
    d["ativo"] = bool(d["ativo"])
    return d


def listar_cenarios(cur) -> list[dict]:
    """Todos (ativos e inativos), na ordem de criação — a lista do admin."""
    try:
        cur.execute(_SQL_CENARIO + " ORDER BY id")
        rows = cur.fetchall()
    except Exception as e:
        if _sem_tabela(e):
            raise MaestroIndisponivel(ERRO_SEM_110) from e
        raise
    return [_linha_cenario(r) for r in rows]


def salvar_cenario(cur, dados: dict, matricula: str, cenario_id: int | None = None) -> dict | None:
    """INSERT (sem id) ou UPDATE (com id). None quando o id não existe.
    Código repetido → CodigoExistente (a UNIQUE da 110 pegaria, mas com uma
    mensagem de banco; aqui a resposta diz qual é o problema)."""
    receita_json = json.dumps(dados["receita"], ensure_ascii=False)
    try:
        cur.execute("SELECT id FROM dbo.etl_maestro_cenario WHERE codigo = ?", (dados["codigo"],))
        dono = cur.fetchone()
        if dono and (cenario_id is None or int(dono[0]) != int(cenario_id)):
            raise CodigoExistente(dados["codigo"])
        if cenario_id is None:
            # `OUTPUT INSERTED.id` (convenção do repo): um `INSERT; SELECT
            # SCOPE_IDENTITY()` no mesmo execute deixa o pyodbc parado no
            # INSERT ("No results") — pego no smoke do DEV.
            cur.execute(
                "INSERT INTO dbo.etl_maestro_cenario (codigo, titulo, descricao, receita_json, ativo, criado_por) "
                "OUTPUT INSERTED.id VALUES (?,?,?,?,?,?)",
                (dados["codigo"], dados["titulo"], dados["descricao"], receita_json,
                 1 if dados["ativo"] else 0, (matricula or "")[:100]))
            row = cur.fetchone()
            novo_id = int(row[0]) if row and row[0] is not None else None
        else:
            cur.execute(
                "UPDATE dbo.etl_maestro_cenario SET codigo=?, titulo=?, descricao=?, receita_json=?, ativo=?, "
                "atualizado_em=GETDATE(), atualizado_por=? WHERE id=?",
                (dados["codigo"], dados["titulo"], dados["descricao"], receita_json,
                 1 if dados["ativo"] else 0, (matricula or "")[:100], int(cenario_id)))
            if not cur.rowcount:
                return None
            novo_id = int(cenario_id)
        cur.execute(_SQL_CENARIO + " WHERE id = ?", (novo_id,))
        row = cur.fetchone()
    except CodigoExistente:
        raise
    except Exception as e:
        if _sem_tabela(e):
            raise MaestroIndisponivel(ERRO_SEM_110) from e
        raise
    return _linha_cenario(row) if row else None


def excluir_cenario(cur, cenario_id: int) -> bool:
    try:
        cur.execute("DELETE FROM dbo.etl_maestro_cenario WHERE id = ?", (int(cenario_id),))
    except Exception as e:
        if _sem_tabela(e):
            raise MaestroIndisponivel(ERRO_SEM_110) from e
        raise
    return bool(cur.rowcount)


_COLS_PEDIDO = ("id", "criado_em", "matricula", "pipeline_name", "job_name", "mensagem", "motivo",
                "tratado_em", "tratado_por")


def listar_pedidos(cur, tratados: bool = False, limite: int = 200) -> list[dict]:
    """Os `nao_atendido`: abertos (padrão) ou já tratados — a demanda que o
    catálogo ainda não cobre, para o administrador ver."""
    try:
        cur.execute(
            f"SELECT TOP ({int(limite)}) id, CONVERT(VARCHAR(19), criado_em, 120), matricula, pipeline_name, "
            "job_name, mensagem, motivo, CONVERT(VARCHAR(19), tratado_em, 120), tratado_por "
            "FROM dbo.etl_maestro_conversa WHERE status = 'nao_atendido' AND tratado_em IS "
            + ("NOT NULL" if tratados else "NULL") + " ORDER BY criado_em DESC, id DESC")
        rows = cur.fetchall()
    except Exception as e:
        if _sem_tabela(e):
            raise MaestroIndisponivel(ERRO_SEM_110) from e
        raise
    return [dict(zip(_COLS_PEDIDO, r)) for r in rows]


def marcar_pedido(cur, pedido_id: int, tratado: bool, matricula: str) -> bool:
    """Carimba (ou descarimba) `tratado_em` num pedido não atendido."""
    try:
        if tratado:
            cur.execute(
                "UPDATE dbo.etl_maestro_conversa SET tratado_em = GETDATE(), tratado_por = ? "
                "WHERE id = ? AND status = 'nao_atendido'", ((matricula or "")[:20], int(pedido_id)))
        else:
            cur.execute(
                "UPDATE dbo.etl_maestro_conversa SET tratado_em = NULL, tratado_por = NULL "
                "WHERE id = ? AND status = 'nao_atendido'", (int(pedido_id),))
    except Exception as e:
        if _sem_tabela(e):
            raise MaestroIndisponivel(ERRO_SEM_110) from e
        raise
    return bool(cur.rowcount)


def gravar_enabled(cur, ligado: bool, matricula: str) -> None:
    """`maestro_enabled` em etl_app_config (MERGE, como as caixa_ia_*)."""
    valor = "1" if ligado else "0"
    cur.execute(
        "MERGE dbo.etl_app_config AS t USING (SELECT ? AS k) AS s ON t.config_key = s.k "
        "WHEN MATCHED THEN UPDATE SET config_value=?, updated_by=?, updated_at=GETDATE() "
        "WHEN NOT MATCHED THEN INSERT (config_key, config_value, descricao, updated_by, updated_at) "
        "  VALUES (s.k, ?, 'Maestro — assistente de parâmetros DataStage (Etapas/Fluxos)', ?, GETDATE());",
        (K_ENABLED, valor, (matricula or "")[:100], valor, (matricula or "")[:100]))


def contagens(cur) -> dict:
    """Os números da aba: cenários (total/ativos) e pedidos abertos. Sem a
    110, zeros — a aba diz que a migration falta em vez de quebrar."""
    try:
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN ativo = 1 THEN 1 ELSE 0 END) FROM dbo.etl_maestro_cenario")
        total, ativos = cur.fetchone() or (0, 0)
        cur.execute("SELECT COUNT(*) FROM dbo.etl_maestro_conversa WHERE status = 'nao_atendido' AND tratado_em IS NULL")
        abertos = (cur.fetchone() or (0,))[0]
    except Exception as e:
        if _sem_tabela(e):
            raise MaestroIndisponivel(ERRO_SEM_110) from e
        raise
    return {"total_cenarios": int(total or 0), "cenarios_ativos": int(ativos or 0),
            "pedidos_abertos": int(abertos or 0)}


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
