"""api/services/job_params.py — parâmetros de execução dos jobs DataStage.

Vocabulário (tipos, origens, âncoras), validação por tipo e o CÁLCULO DE DATA
declarativo da spec docs/spec-parametros-job-datastage.md (§4, "Regras de
resolução"):

    base (origem) → +meses → âncora → +dias → formato

A ordem é fixa de propósito: deslocar o mês ANTES de ancorar é o que faz
"mês anterior" funcionar em qualquer dia (31/03 −1 mês = 28/02, depois
fim_mes = 28/02; ancorar antes daria 31/03 → 31/03 −1 mês = 28/02 por sorte,
mas 30/04 → 30/04 −1 mês = 30/03, que NÃO é fim de março).

Módulo PURO: sem banco, sem FastAPI, sem Airflow — testável sozinho.

⚠️ ESPELHO: dags/utils/ds_params.py (F2) carrega uma cópia destas funções,
porque api/ e dags/ rodam em containers diferentes e o repo nunca importou uma
árvore da outra. tests/test_job_params_antidrift.py confere valor E descrição
iguais nas duas. Mudou aqui, muda lá.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

# ── Vocabulário ──────────────────────────────────────────────────────────────

DS_PARAM_TYPES = ("String", "Integer", "Float", "Date", "Time", "Timestamp",
                  "Pathname", "List", "Encrypted")
DS_PARAM_SOURCES = ("fixo", "data_referencia", "data_logica", "data_execucao", "run_id")
DS_SOURCES_DATA = ("data_referencia", "data_logica", "data_execucao")
DS_PARAM_ANCORAS = ("inicio_mes", "fim_mes", "inicio_trimestre", "fim_trimestre",
                    "inicio_ano", "fim_ano", "inicio_semana", "fim_semana")
# Tipos que aceitam origem de data (o valor enviado é a data formatada).
DS_TIPOS_COM_DATA = ("String", "Date", "Timestamp")
FORMATO_PADRAO = "%Y-%m-%d"
LIMITE_MESES = 120
LIMITE_DIAS = 3660
# Larguras da SP (migration 107): @param_name VARCHAR(128), @param_formato VARCHAR(40).
LIMITE_NOME = 128
LIMITE_FORMATO = 40
# O que a API devolve no lugar de um valor Encrypted — e o que o front manda
# de volta para dizer "mantém o token gravado".
ENCRYPTED_MASCARA = "***"

# Nome do parâmetro do DataStage; um ponto opcional = membro de Parameter Set
# (`PSet.Param`). Vira `-param 'nome=valor'` no dsjob — sem espaço/aspas.
NOME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")
# Allowlist do strftime: diretivas de data/hora e separadores. Um `%` solto ou
# uma diretiva fora da lista é recusado — o formato vai direto ao strftime.
FORMATO_RE = re.compile(r"^(?:%[YmdyHMS]|[-/._: ])+$")
# Valor FIXO por tipo. String/List/Encrypted: livre, sem quebra de linha.
VALOR_FIXO_RE = {
    "Integer":   re.compile(r"^-?\d+$"),
    "Float":     re.compile(r"^-?\d+(?:\.\d+)?$"),
    "Date":      re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "Time":      re.compile(r"^\d{2}:\d{2}:\d{2}$"),
    "Timestamp": re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"),
    # Absoluto, sem espaço/aspas: vira argumento de shell via shlex.quote, que
    # transforma `~` em literal (gotcha do lineage ISX) — por isso absoluto.
    "Pathname":  re.compile(r"^/[^\s'\"]+$"),
}

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


# ── Cálculo de data ──────────────────────────────────────────────────────────

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


# ── Validação / normalização ─────────────────────────────────────────────────

def _inteiro(valor, nome: str, limite: int, erros: list[str]) -> int | None:
    """None/'' → None; inteiro dentro de ±limite; senão registra o erro."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        erros.append(f"{nome} inválido ({valor!r}) — informe um inteiro")
        return None
    if abs(n) > limite:
        erros.append(f"{nome} fora da faixa ±{limite}")
        return None
    return n


def normalizar_item(item: dict) -> tuple[dict, list[str]]:
    """Valida UM parâmetro DataStage e devolve (normalizado, erros).

    O normalizado tem SEMPRE as chaves: param_name, param_type, param_source,
    param_value, param_offset_meses, param_ancora, param_offset_dias,
    param_formato. Fora de origem de data, os campos de cálculo saem None
    (o CHECK da migration 107 exige isso). Encrypted com valor `***` passa
    aqui — é o chamador (que tem o banco) quem decide se há token para manter.
    """
    erros: list[str] = []
    if not isinstance(item, dict):
        return {}, ["parâmetro inválido (esperado objeto)"]
    nome = str(item.get("param_name") or "").strip()
    tipo = str(item.get("param_type") or "").strip()
    # Origem OBRIGATÓRIA, sem default: um chamador que não a manda (a tela de
    # antes da F3 reenvia só nome/tipo/valor) receberia 'fixo' e rebaixaria um
    # parâmetro de data em silêncio (achado 1 da revisão adversarial da F1).
    origem = str(item.get("param_source") or "").strip()
    valor = item.get("param_value")
    valor = None if valor is None else str(valor)

    if not nome or not NOME_RE.match(nome):
        erros.append(f"nome '{nome}' inválido — letras/números/_ e no máximo um ponto (PSet.Param)")
    elif len(nome) > LIMITE_NOME:
        # A SP declara VARCHAR(128): parâmetro de SP TRUNCA em silêncio, e o
        # dsjob recusaria o nome cortado (achado 2 da revisão adversarial).
        erros.append(f"nome com {len(nome)} caracteres — máximo {LIMITE_NOME}")
    if tipo not in DS_PARAM_TYPES:
        erros.append(f"tipo '{tipo}' inválido — use um de {', '.join(DS_PARAM_TYPES)}")
    if not origem:
        erros.append(f"origem obrigatória — use uma de {', '.join(DS_PARAM_SOURCES)}")
    elif origem not in DS_PARAM_SOURCES:
        erros.append(f"origem '{origem}' inválida — use uma de {', '.join(DS_PARAM_SOURCES)}")
    if erros:
        return {}, [f"'{nome}': {e}" if nome else e for e in erros]

    meses = ancora = dias = formato = None
    if origem in DS_SOURCES_DATA:
        if tipo not in DS_TIPOS_COM_DATA:
            erros.append(f"origem de data só com tipo {', '.join(DS_TIPOS_COM_DATA)} (é {tipo})")
        meses = _inteiro(item.get("param_offset_meses"), "meses", LIMITE_MESES, erros)
        dias = _inteiro(item.get("param_offset_dias"), "dias", LIMITE_DIAS, erros)
        ancora = str(item.get("param_ancora") or "").strip() or None
        if ancora and ancora not in DS_PARAM_ANCORAS:
            erros.append(f"âncora '{ancora}' inválida — use uma de {', '.join(DS_PARAM_ANCORAS)}")
        formato = str(item.get("param_formato") or "").strip() or None
        if formato and not FORMATO_RE.match(formato):
            erros.append(f"formato '{formato}' inválido — só %Y %m %d %y %H %M %S e separadores - / . _ :")
        elif formato and len(formato) > LIMITE_FORMATO:
            # VARCHAR(40) na SP: truncaria em silêncio e a prévia (calculada do
            # payload) divergiria do runtime (calculado do banco).
            erros.append(f"formato com {len(formato)} caracteres — máximo {LIMITE_FORMATO}")
        valor = None  # o valor nasce em runtime; nada fixo sobrevive aqui
    else:
        # fixo / run_id: campos de cálculo NÃO podem vir preenchidos (CHECK 107).
        for chave, rotulo in (("param_offset_meses", "meses"), ("param_ancora", "âncora"),
                              ("param_offset_dias", "dias"), ("param_formato", "formato")):
            v = item.get(chave)
            if v is not None and str(v).strip() != "" and str(v).strip() != "0":
                erros.append(f"{rotulo} só vale com origem de data (origem é '{origem}')")
        if origem == "run_id":
            if tipo != "String":
                erros.append(f"origem run_id só com tipo String (é {tipo})")
            valor = None
        else:  # fixo
            if valor is None or (valor == "" and tipo != "String"):
                erros.append("valor obrigatório para origem fixa")
            elif "\n" in valor or "\r" in valor:
                erros.append("valor não pode ter quebra de linha")
            elif tipo in VALOR_FIXO_RE and not VALOR_FIXO_RE[tipo].match(valor):
                erros.append(f"valor '{valor}' não é um {tipo} válido")

    norm = {
        "param_name": nome, "param_type": tipo, "param_source": origem,
        "param_value": valor, "param_offset_meses": meses, "param_ancora": ancora,
        "param_offset_dias": dias, "param_formato": formato,
    }
    return norm, [f"'{nome}': {e}" for e in erros]


def normalizar_lista(itens) -> tuple[list[dict], list[str]]:
    """Lista de parâmetros DataStage → (normalizados na ordem, erros).

    Linha sem nome E sem valor é ignorada (linha vazia do editor). Nomes
    repetidos com CAIXA EXATA são duplicata — o DataStage distingue `pData`
    de `pdata`, e o Orquestra não pode fingir que são o mesmo."""
    if itens is None:
        return [], []
    if not isinstance(itens, list):
        return [], ["params deve ser uma lista"]
    validos: list[dict] = []
    erros: list[str] = []
    vistos: set[str] = set()
    for i, item in enumerate(itens):
        if isinstance(item, dict) and not str(item.get("param_name") or "").strip() \
                and not str(item.get("param_value") or "").strip():
            continue
        norm, errs = normalizar_item(item)
        if errs:
            erros.extend(f"parâmetro #{i + 1} {e}" for e in errs)
            continue
        if norm["param_name"] in vistos:
            erros.append(f"parâmetro #{i + 1} '{norm['param_name']}': duplicado")
            continue
        vistos.add(norm["param_name"])
        validos.append(norm)
    return validos, erros


# ── Prévia ───────────────────────────────────────────────────────────────────

def resolver_preview(referencia: date, itens: list[dict]) -> tuple[list[dict], list[str]]:
    """Para itens JÁ normalizados: (valores, erros). O valor é o que iria ao
    DataStage se a base fosse `referencia`, com a descrição. Encrypted sai
    mascarado; run_id sai como marcador (só existe em runtime). Uma borda de
    calendário (ano 9999 + 1 mês) vira erro do item, não 500."""
    saida: list[dict] = []
    erros: list[str] = []
    for it in itens:
        origem = it["param_source"]
        try:
            if origem in DS_SOURCES_DATA:
                meses = it.get("param_offset_meses") or 0
                dias = it.get("param_offset_dias") or 0
                valor = formatar(calcular_data(referencia, meses, it.get("param_ancora"), dias),
                                 it.get("param_formato"))
                desc = descrever(referencia, origem, meses, it.get("param_ancora"), dias,
                                 it.get("param_formato"))
            elif origem == "run_id":
                valor, desc = "<run_id do Airflow>", "run_id da corrida (só existe em runtime)"
            elif it["param_type"] == "Encrypted":
                valor, desc = ENCRYPTED_MASCARA, "fixo (Encrypted — nunca exibido)"
            else:
                valor, desc = it.get("param_value") or "", "fixo"
        except (ValueError, OverflowError) as e:
            erros.append(f"'{it['param_name']}': data fora do calendário para a referência "
                         f"{referencia.isoformat()} ({e})")
            continue
        saida.append({"param_name": it["param_name"], "valor": valor, "descricao": desc})
    return saida, erros
