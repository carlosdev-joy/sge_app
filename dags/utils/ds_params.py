"""
dags/utils/ds_params.py — parâmetros de execução dos jobs DataStage: o que o
DataStageOperator manda em `-param` (spec docs/spec-parametros-job-datastage.md, F2).

⚠️ ESPELHO de api/services/job_params.py. O vocabulário e as funções de cálculo
(deslocar_meses, ancorar, calcular_data, formatar, descrever, parse_data) são
cópia byte a byte: api/ e dags/ rodam em containers diferentes e o repo nunca
importou uma árvore da outra. tests/test_job_params_antidrift.py cobra valor E
descrição iguais nas duas. Mudou lá, muda aqui.

O que só existe aqui (runtime):

  carregar_etapa   linhas da etapa em etl_pipeline_job_param (placeholders %s — a
                   árvore dags/ fala pymssql; api/ fala pyodbc com `?`)
  parse_lparams    nomes que o job DECLARA (saída do `dsjob -lparams`)
  mesclar          pipeline (só o que o job declara) < etapa (não declarado = ERRO)
                   < sobreposição do rerun — o contrato do §4 da spec
  resolver         origem → valor (Encrypted decifrado com a ORQUESTRA_CONN_KEY),
                   com fonte e descrição
  montar_args      os pares `-param nome=valor`, quotados para o shell remoto
  linha_de_log / para_json   o RASTRO do que foi enviado — Encrypted SEMPRE `***`

Tudo puro exceto carregar_etapa (recebe o hook). A validação de formato/tipo NÃO
mora aqui: ela é da API (e dos CHECKs da migration 107) — o runtime confia no que
o banco guardou e falha alto no que não consegue resolver.
"""
from __future__ import annotations

import calendar
import json
import os
import re
import shlex
from datetime import date, datetime, timedelta

# ═══════════════════════════════════════════════════════════════════════════
# Vocabulário e cálculo — ESPELHO de api/services/job_params.py
# ═══════════════════════════════════════════════════════════════════════════

DS_PARAM_TYPES = ("String", "Integer", "Float", "Date", "Time", "Timestamp",
                  "Pathname", "List", "Encrypted")
DS_PARAM_SOURCES = ("fixo", "data_referencia", "data_logica", "data_execucao", "run_id")
DS_SOURCES_DATA = ("data_referencia", "data_logica", "data_execucao")
DS_PARAM_ANCORAS = ("inicio_mes", "fim_mes", "inicio_trimestre", "fim_trimestre",
                    "inicio_ano", "fim_ano", "inicio_semana", "fim_semana")
FORMATO_PADRAO = "%Y-%m-%d"
ENCRYPTED_MASCARA = "***"

ROTULO_ORIGEM = {
    "data_referencia": "referência",
    "data_logica": "data lógica",
    "data_execucao": "data da execução",
}
ROTULO_ANCORA = {
    "inicio_mes": "início do mês",
    "fim_mes": "fim do mês",
    "inicio_trimestre": "início do trimestre",
    "fim_trimestre": "fim do trimestre",
    "inicio_ano": "início do ano",
    "fim_ano": "fim do ano",
    "inicio_semana": "segunda da semana",
    "fim_semana": "domingo da semana",
}


def deslocar_meses(d: date, meses: int) -> date:
    """`d` deslocada `meses` meses, com o dia TRUNCADO ao último válido do mês
    de destino: 31/03 −1 = 28/02 (29/02 em bissexto); 30/04 +1 = 30/05."""
    if not meses:
        return d
    total = d.year * 12 + (d.month - 1) + meses
    ano, mes0 = divmod(total, 12)
    mes = mes0 + 1
    ultimo = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(d.day, ultimo))


def ancorar(d: date, ancora: str | None) -> date:
    """Leva `d` ao ponto da âncora dentro do próprio período. Semana = seg–dom."""
    if not ancora:
        return d
    if ancora == "inicio_mes":
        return d.replace(day=1)
    if ancora == "fim_mes":
        return d.replace(day=calendar.monthrange(d.year, d.month)[1])
    if ancora == "inicio_trimestre":
        return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)
    if ancora == "fim_trimestre":
        mes = 3 * ((d.month - 1) // 3) + 3
        return date(d.year, mes, calendar.monthrange(d.year, mes)[1])
    if ancora == "inicio_ano":
        return date(d.year, 1, 1)
    if ancora == "fim_ano":
        return date(d.year, 12, 31)
    if ancora == "inicio_semana":
        return d - timedelta(days=d.weekday())
    if ancora == "fim_semana":
        return d + timedelta(days=6 - d.weekday())
    raise ValueError(f"âncora desconhecida: {ancora!r}")


def calcular_data(base: date, meses: int = 0, ancora: str | None = None, dias: int = 0) -> date:
    """O contrato do §4: meses → âncora → dias. Cada passo é opcional."""
    d = deslocar_meses(base, int(meses or 0))
    d = ancorar(d, ancora or None)
    if dias:
        d = d + timedelta(days=int(dias))
    return d


def formatar(d: date, formato: str | None) -> str:
    return d.strftime(formato or FORMATO_PADRAO)


def _plural(n: int, singular: str, plural: str) -> str:
    n = int(n)
    sinal = "+" if n > 0 else "-"
    return f"{sinal}{abs(n)} {singular if abs(n) == 1 else plural}"


def descrever(base: date, origem: str, meses: int = 0, ancora: str | None = None,
              dias: int = 0, formato: str | None = None) -> str:
    """Texto humano do cálculo, o MESMO que vai para o log da task, para a
    prévia da tela e para o modal de rerun — é o rastro de "qual parâmetro
    foi usado". Ex.: `referência 2026-09-09 → -1 mês → fim do mês → 2026-08-31`."""
    partes = [f"{ROTULO_ORIGEM.get(origem, origem)} {base.isoformat()}"]
    if meses:
        partes.append(_plural(meses, "mês", "meses"))
    if ancora:
        partes.append(ROTULO_ANCORA.get(ancora, ancora))
    if dias:
        partes.append(_plural(dias, "dia", "dias"))
    partes.append(formatar(calcular_data(base, meses, ancora, dias), formato))
    return " → ".join(partes)


def parse_data(valor) -> date | None:
    """'YYYY-MM-DD' (ou date/datetime) → date; None quando inválido."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(str(valor or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Runtime — só existe aqui
# ═══════════════════════════════════════════════════════════════════════════

class ParamError(Exception):
    """Motivo pelo qual a etapa deve FALHAR antes do disparo (o operador embrulha
    em AirflowException com o prefixo [DS]). Nunca dispara "sem o parâmetro"."""


ENV_KEY = "ORQUESTRA_CONN_KEY"

# Colunas na ORDEM do SELECT — o dict de cada linha é o que mesclar/resolver leem.
COLS_ETAPA = ("param_name", "param_type", "param_value", "param_source",
              "param_offset_meses", "param_ancora", "param_offset_dias", "param_formato")
SQL_ETAPA = (
    "SELECT param_name, param_type, param_value, param_source, param_offset_meses, "
    "param_ancora, param_offset_dias, param_formato "
    "FROM dbo.etl_pipeline_job_param WHERE pipeline_name=%s AND job_name=%s "
    "ORDER BY param_order")
_SEM_107_RE = re.compile(r"invalid column name|invalid object name", re.IGNORECASE)
# F4 — defaults do pipeline (migration 108): mesmas colunas, mesma ordem.
SQL_PIPELINE = (
    "SELECT param_name, param_type, param_value, param_source, param_offset_meses, "
    "param_ancora, param_offset_dias, param_formato "
    "FROM dbo.etl_pipeline_param WHERE pipeline_name=%s ORDER BY param_order")


def _decrypt(token: str) -> str:
    """Token Fernet → valor. Mesma chave e mesma disciplina de
    dags/utils/conn_resolver._decrypt (que não é importado daqui para não
    arrastar os hooks do Airflow no import). O retorno NUNCA vai para log."""
    from cryptography.fernet import Fernet  # dependência do próprio Airflow
    key = (os.getenv(ENV_KEY) or "").strip()
    if not key:
        raise ParamError(
            f"{ENV_KEY} não configurada no worker — defina no .env/compose o MESMO "
            "valor usado pelo orquestra-api (x-airflow-common); sem ela um parâmetro "
            "Encrypted não pode ser decifrado")
    try:
        return Fernet(key.encode()).decrypt(str(token).encode("ascii")).decode("utf-8")
    except Exception as e:  # InvalidToken, base64 ruim…
        raise ParamError(
            "valor Encrypted ilegível — a ORQUESTRA_CONN_KEY do worker não corresponde "
            "à chave com que o parâmetro foi salvo no orquestra-api; redefina o valor "
            "na etapa ou restaure a chave") from e


def carregar_etapa(hook, pipeline_name: str, job_name: str, log=None) -> list[dict]:
    """Linhas de etl_pipeline_job_param da etapa, na ordem do editor.

    Sem a migration 107 (coluna param_source ausente) não pode haver parâmetro
    de etapa datastage — a API recusa gravar — então a resposta honesta é
    "nenhum", com aviso. Qualquer OUTRO erro de banco propaga: sem saber os
    parâmetros, disparar "sem eles" seria o falso verde que a spec proíbe."""
    try:
        rows = hook.get_records(SQL_ETAPA, parameters=(pipeline_name, job_name))
    except Exception as e:
        if _SEM_107_RE.search(str(e)):
            if log is not None:
                log.warning("[DS] etl_pipeline_job_param sem as colunas da migration 107 "
                            "(%s) — nenhum parâmetro de etapa será enviado", e)
            return []
        raise
    return [dict(zip(COLS_ETAPA, r)) for r in (rows or [])]


def carregar_pipeline(hook, pipeline_name: str, log=None) -> list[dict]:
    """Defaults do pipeline (etl_pipeline_param, F4), na ordem do editor.

    Sem a migration 108 (tabela ausente) não há default nenhum — resposta
    honesta é "nenhum", em debug (é o estado normal até a F4 ir para
    produção). Qualquer OUTRO erro de banco propaga, como em carregar_etapa."""
    try:
        rows = hook.get_records(SQL_PIPELINE, parameters=(pipeline_name,))
    except Exception as e:
        if _SEM_107_RE.search(str(e)):
            if log is not None:
                log.debug("[DS] etl_pipeline_param ausente (migration 108) — sem defaults do pipeline (%s)", e)
            return []
        raise
    return [dict(zip(COLS_ETAPA, r)) for r in (rows or [])]


def parse_lparams(saida: str) -> set[str]:
    """Nomes que o job declara, um por linha no `dsjob -lparams` — parâmetros
    simples e membros de Parameter Set (`PSet.Param`). Ignora a linha
    `Status code = N` (o mesmo parser do Console DataStage)."""
    nomes: set[str] = set()
    for raw in (saida or "").splitlines():
        linha = raw.strip()
        if not linha or re.match(r"^status code\s*=", linha, re.IGNORECASE):
            continue
        nomes.add(linha)
    return nomes


def mesclar(etapa: list[dict], declarados: set[str], pipeline: list[dict] | None = None,
            overrides: list[dict] | None = None) -> tuple[list[dict], list[str]]:
    """O contrato do §4 (passos 1–3): devolve (itens, ignorados_do_pipeline).

    • pipeline: só o que o job DECLARA entra; o resto vai para `ignorados`
      (e para o log) — default compartilhado por natureza.
    • etapa: sobrepõe por nome; nome NÃO declarado = ParamError listando o que
      o job declara (o operador digitou o nome de propósito).
    • overrides (F5, {param_name, param_value}): sobrepõem o valor como
      `fixo`; nome fora de tudo e não declarado = ParamError.
    Cada item sai com `fonte` ('pipeline' | 'etapa' | 'rerun')."""
    por_nome: dict[str, dict] = {}
    ignorados: list[str] = []
    for p in pipeline or []:
        if p["param_name"] in declarados:
            por_nome[p["param_name"]] = dict(p, fonte="pipeline")
        else:
            ignorados.append(p["param_name"])
    nao_declarados = [p["param_name"] for p in etapa if p["param_name"] not in declarados]
    if nao_declarados:
        raise ParamError(
            "o job NÃO declara o(s) parâmetro(s) cadastrado(s) na etapa: "
            + ", ".join(nao_declarados)
            + ". O DataStage distingue maiúsculas de minúsculas. Parâmetros que o job declara: "
            + (", ".join(sorted(declarados)) if declarados else "(nenhum)"))
    for p in etapa:
        por_nome[p["param_name"]] = dict(p, fonte="etapa")
    for o in overrides or []:
        nome = o["param_name"]
        if nome not in por_nome and nome not in declarados:
            raise ParamError(
                f"a sobreposição do rerun cita '{nome}', que o job não declara. "
                "Parâmetros que o job declara: " + (", ".join(sorted(declarados)) or "(nenhum)"))
        base = por_nome.get(nome, {"param_name": nome, "param_type": "String"})
        por_nome[nome] = dict(base, param_source="fixo", param_value=o.get("param_value"),
                              param_offset_meses=None, param_ancora=None,
                              param_offset_dias=None, param_formato=None, fonte="rerun")
    return list(por_nome.values()), ignorados


def resolver(itens: list[dict], bases: dict, run_id: str, decifrar=None) -> list[dict]:
    """Passo 4–5 do §4: cada item → {name, valor, fonte, descricao, mascarado}.

    `bases` = {origem_de_data: date} já resolvidas pelo operador (ele só busca
    a data de referência no banco quando algum item precisa). Encrypted é
    decifrado aqui e marcado `mascarado=True` — quem loga/persiste usa
    valor_exibido()."""
    decifrar = decifrar or _decrypt
    saida: list[dict] = []
    for it in itens:
        nome = it["param_name"]
        tipo = it.get("param_type") or "String"
        origem = it.get("param_source") or "fixo"
        mascarado = False
        if origem in DS_SOURCES_DATA:
            base = bases.get(origem)
            if base is None:
                raise ParamError(f"'{nome}': origem {origem} indisponível nesta execução")
            meses = it.get("param_offset_meses") or 0
            dias = it.get("param_offset_dias") or 0
            ancora = it.get("param_ancora") or None
            formato = it.get("param_formato") or None
            try:
                valor = formatar(calcular_data(base, meses, ancora, dias), formato)
                descricao = descrever(base, origem, meses, ancora, dias, formato)
            except (ValueError, OverflowError) as e:
                raise ParamError(f"'{nome}': data fora do calendário ({e})") from e
        elif origem == "run_id":
            valor, descricao = str(run_id or ""), "run_id da corrida"
        else:  # fixo
            valor = it.get("param_value")
            valor = "" if valor is None else str(valor)
            if tipo == "Encrypted":
                if not valor:
                    raise ParamError(f"'{nome}': Encrypted sem valor gravado")
                valor = decifrar(valor)
                descricao, mascarado = "fixo (Encrypted)", True
            else:
                descricao = "fixo"
        saida.append({"name": nome, "valor": valor, "fonte": it.get("fonte") or "etapa",
                      "descricao": descricao, "mascarado": mascarado})
    return saida


def valor_exibido(p: dict) -> str:
    return ENCRYPTED_MASCARA if p.get("mascarado") else str(p.get("valor", ""))


def montar_args(lista: list[dict], exibir: bool = False) -> list[str]:
    """`-param nome=valor` por item, quotado pelo shlex para o shell remoto
    (só ganha aspas quando precisa). `exibir=True` monta a versão para log e
    mensagens de erro — Encrypted vira `***`."""
    args: list[str] = []
    for p in lista:
        v = valor_exibido(p) if exibir else str(p.get("valor", ""))
        args += ["-param", shlex.quote(f"{p['name']}={v}")]
    return args


def linha_de_log(lista: list[dict], ignorados: list[str] | None = None) -> str:
    """A linha `[DS] parâmetros:` — nome=valor (fonte · descrição), Encrypted
    mascarado, mais os defaults de pipeline que o job não declara."""
    partes = [f"{p['name']}={valor_exibido(p)} ({p.get('fonte', 'etapa')} · {p.get('descricao', '')})"
              for p in lista]
    texto = " · ".join(partes) if partes else "nenhum"
    if ignorados:
        texto += " · ignorados do pipeline (o job não declara): " + ", ".join(ignorados)
    return texto


def para_json(lista: list[dict]) -> str:
    """etl_ds_job_log.params_json — [{name, valor, fonte, descricao, mascarado}],
    com o valor JÁ mascarado quando Encrypted (o segredo nunca vai ao banco em claro)."""
    return json.dumps([{"name": p["name"], "valor": valor_exibido(p),
                        "fonte": p.get("fonte", "etapa"), "descricao": p.get("descricao", ""),
                        "mascarado": bool(p.get("mascarado"))} for p in lista],
                      ensure_ascii=False)
