"""api/services/agentes_conhecimento.py — FATOS e PROPOSTAS do agente DataStage
(F5 da spec docs/spec-agentes-datastage.md).

Duas coisas com regras opostas, e é por isso que moram juntas:

  • **Fato** é o que uma FERRAMENTA leu (`dsjob -lstages/-lparams/-report`,
    extração ISX de job fora de pipeline, `.dsx` local). Grava direto em
    `etl_agente_fato`, com origem, evidência autocontida e `lido_em` — sem
    aprovação, porque não é opinião de ninguém. `gravar_fatos` recusa
    qualquer origem que não seja de ferramenta (critério 1): o único caminho
    para `interpretacao_aprovada` é `decidir_proposta`.
  • **Proposta** é o que o MODELO concluiu. Nunca vira fato sozinha: fica
    `pendente` em `etl_agente_proposta` até o DONO da conversa aprovar
    (critério 2). Antes disso passa pela régua (`validar_proposta`): tipo
    conhecido, tamanhos das colunas, nada com cara de segredo (critério 4)
    e — o que impede o "falso verde" do risco 1 — a EVIDÊNCIA tem de ser um
    trecho LITERAL do que as ferramentas devolveram nesta mesma pergunta.
    Uma interpretação sem lastro no que foi lido não chega nem ao cartão.

Obsolescência (a "mudança detectada" da spec): cada leitura de ferramenta é
um RETRATO completo daquela origem para o job. Chave que sumiu ou mudou de
valor em relação ao retrato anterior ganha `obsoleto_em` — a linha fica
(auditoria), só sai do que a ferramenta `base` devolve. Um retrato VAZIO
não obsoleta nada: um parse que não achou nada é mais provavelmente um
formato inesperado do `dsjob` (D-07 segue aberta) do que um job sem stages.

Nada aqui tem FK para a conversa (spec §4): a purga de 30 dias apaga a
conversa e deixa fato, proposta e decisão intactos (critério 5).
"""
from __future__ import annotations

import json
import re

from services import agentes_ferramentas as af
from services.ssh_arquivos import cortar_utf16

# ── Vocabulário ──────────────────────────────────────────────────────────────

ORIGENS_FERRAMENTA = ("dsjob_lstages", "dsjob_lparams", "dsjob_report", "isx", "dsx")
ORIGEM_INTERPRETACAO = "interpretacao_aprovada"
TIPOS_FATO = ("stage", "parametro", "tabela", "campo", "lineage", "descricao")

# Larguras de etl_agente_fato/etl_agente_proposta (migration 117). NVARCHAR
# conta UTF-16 — `cortar_utf16`, nunca fatia de Python.
_L_PROJETO = 50
_L_JOB = 200
_L_CHAVE = 300
_L_MOTIVO = 600
_L_LAST_MODIFIED = 40

MAX_VALOR_JSON = 4000      # um fato é um dado pontual, não um documento
MAX_EVIDENCIA = 2000
MAX_FATOS_POR_RETRATO = 500
MAX_FATOS_NA_BASE = 150    # o que `base` devolve ao modelo (ainda passa por _truncar)
MAX_COLUNAS_POR_STAGE = 60
MAX_SQL = 1500

# Comando do dsjob → origem do fato. `ljobs` e `jobinfo` não viram fato:
# `ljobs` é a lista do PROJETO (não de um job) e `jobinfo` é estado de
# execução, que muda a cada rodada da malha e envelheceria no minuto seguinte.
_ORIGEM_DO_DSJOB = {"lstages": "dsjob_lstages", "lparams": "dsjob_lparams", "report": "dsjob_report"}

# Uma linha de `-lstages`/`-lparams` só é aceita como NOME se parecer um
# identificador DataStage — sem espaço. O formato exato da saída não está
# confirmado (D-07): linha de status ("Status code = 0"), cabeçalho ou
# mensagem de erro têm espaço e ficam de fora sozinhas.
_RE_NOME_DS = re.compile(r"^[A-Za-z0-9_.$#-]{1,300}$")


# Valor cifrado do DataStage (`{iisenc}<base64>`) é segredo por FORMATO,
# não por palavra-chave: numa linha como `CONN_STR {iisenc}AbC==` não há
# "password" nenhum para `redigir()` achar, e o valor passava intacto.
# Achado real da revisão adversarial da F5 — sem isto, o blob ia para a
# evidência e para o fato do `-report`, que (ao contrário da conversa) não
# expiram em 30 dias. Máscara estrutural, sem heurística: o token inteiro,
# até o primeiro espaço/aspa/delimitador.
# `\\` também encerra: dentro de um JSON a quebra de linha é o `\n` LITERAL,
# e sem isso a máscara engolia a linha seguinte (base64 não tem `\`).
_RE_CIFRADO = re.compile(r"\{iisenc\}[^\s\"',;)\]}\\]*", re.I)
_MASCARA_CIFRADO = "{iisenc}••••"


def sem_cifrado(texto: str) -> str:
    return _RE_CIFRADO.sub(_MASCARA_CIFRADO, texto or "")


def _c(valor, largura: int) -> str:
    return cortar_utf16(str(valor or "").strip(), largura)


def _json_valor(valor) -> str | None:
    if valor is None:
        return None
    texto = sem_cifrado(json.dumps(af.redigir_estrutura(valor), ensure_ascii=False, default=str, sort_keys=True))
    if len(texto) > MAX_VALOR_JSON:
        # Nunca corta um JSON no meio (ficaria inválido): troca por um resumo.
        texto = json.dumps({"truncado": True, "tamanho": len(texto)})
    return texto


# ══════════════════════════════════════════════════════════════════════════
# Fatos: derivar do que a ferramenta devolveu
# ══════════════════════════════════════════════════════════════════════════

def _fatos_de_stages(stages) -> list[dict]:
    """Um fato `stage` por stage e um `tabela` por objeto de origem/destino.
    O mesmo formato serve para ISX (`parse_isx`) e DSX (`DSXEngine.extrair`),
    que já devolvem os mesmos campos (`stage_name`, `direction`...)."""
    fatos: list[dict] = []
    for s in stages or []:
        if not isinstance(s, dict):
            continue
        nome = str(s.get("stage_name") or "").strip()
        if not nome:
            continue
        colunas = s.get("columns") or s.get("output_columns") or []
        nomes_col = [str(c.get("name") if isinstance(c, dict) else c) for c in colunas][:MAX_COLUNAS_POR_STAGE]
        sql = s.get("sql_expression")
        valor = {
            "tipo_stage": s.get("stage_type_raw"),
            "direcao": s.get("direction"),
            "objeto_tipo": s.get("object_type"),
            "banco": s.get("database_name"),
            "arquivo": s.get("file_path"),
            "colunas": nomes_col,
            "sql": (str(sql)[:MAX_SQL] if sql else None),
        }
        fatos.append({"tipo": "stage", "chave": nome,
                      "valor": {k: v for k, v in valor.items() if v not in (None, "", [])}})
        direcao = str(s.get("direction") or "")
        objeto = _objeto(s)
        if direcao in ("origem", "destino") and objeto and objeto != nome:
            fatos.append({"tipo": "tabela", "chave": f"{direcao}:{objeto}",
                          "valor": {"stage": nome, "banco": s.get("database_name"),
                                    "objeto_tipo": s.get("object_type")}})
    return fatos


def _objeto(s: dict) -> str:
    """O "objeto" do stage — a mesma regra de `lineage_isx._object_name`:
    tabela declarada no conector, senão o arquivo, senão o nome do stage."""
    if s.get("sql_tag") == "TableName" and s.get("sql_expression"):
        return str(s["sql_expression"]).strip().splitlines()[0]
    if s.get("classe") == "arquivo" and s.get("file_path"):
        return str(s["file_path"])
    if s.get("object_name") and s.get("object_name") != s.get("stage_name"):
        return str(s["object_name"])
    return str(s.get("stage_name") or "")


def fatos_do_isx(resultado: dict | None) -> list[dict]:
    """Retrato de uma extração ISX de job FORA de pipeline (a de dentro vai
    para `etl_job_lineage` pelo `gravar` do botão — nada aqui). Parâmetro
    guarda NOME, tipo e descrição; o valor padrão NUNCA (é onde mora o
    `{iisenc}` de um Encrypted — o parse já o troca por `***`, mas o fato
    não precisa dele de jeito nenhum)."""
    if not resultado:
        return []
    fatos = _fatos_de_stages(resultado.get("stages"))
    for p in resultado.get("parameters") or []:
        if not isinstance(p, dict) or not str(p.get("name") or "").strip():
            continue
        fatos.append({"tipo": "parametro", "chave": str(p["name"]).strip(),
                      "valor": {k: p.get(k) for k in ("type", "description") if p.get(k)}})
    descricao = resultado.get("job_description")
    if descricao:
        fatos.append({"tipo": "descricao", "chave": "job", "valor": {"texto": str(descricao)[:1000]}})
    return fatos


def fatos_do_dsx(resultado: dict | None) -> list[dict]:
    """Retrato de `dsx_consulta` operação `extrair` (o lineage de UM job lido
    do arquivo). Vai para `etl_agente_fato` origem `dsx`, nunca para
    `etl_job_lineage` (B-22)."""
    if not resultado or not resultado.get("sucesso"):
        return []
    return _fatos_de_stages(resultado.get("dados"))


def fatos_do_dsjob(comando: str, saida_redigida: str) -> tuple[str, list[dict]] | None:
    """(origem, fatos) de uma saída de `dsjob` que DEU CERTO — ou None quando
    o comando não produz fato (`ljobs`, `jobinfo`). A saída já chega redigida
    (`ferramenta_dsjob`)."""
    origem = _ORIGEM_DO_DSJOB.get(comando)
    if origem is None:
        return None
    texto = saida_redigida or ""
    if comando == "report":
        # Formato do -report não confirmado (D-07): guarda o texto (já
        # redigido e truncado) como UM fato de descrição, sem tentar
        # interpretá-lo.
        return origem, ([{"tipo": "descricao", "chave": "dsjob_report",
                          "valor": {"texto": texto[:MAX_VALOR_JSON // 2]}}] if texto.strip() else [])
    tipo = "stage" if comando == "lstages" else "parametro"
    nomes, vistos = [], set()
    for linha in texto.split("\n"):
        nome = linha.strip()
        if _RE_NOME_DS.match(nome) and nome not in vistos:
            vistos.add(nome)
            nomes.append({"tipo": tipo, "chave": nome, "valor": None})
    return origem, nomes


def evidencia_de(ferramenta: str, args: dict, trecho: str) -> str:
    """Evidência AUTOCONTIDA (spec §4): o comando que leu + um trecho do que
    ele devolveu, já redigido. Não aponta para a conversa — a conversa some
    em 30 dias e a evidência precisa continuar legível."""
    partes = [f"{k}={v}" for k, v in sorted((args or {}).items()) if isinstance(v, (str, int, bool))]
    cabeca = f"{ferramenta} {' '.join(partes)}".strip()
    return cortar_utf16(sem_cifrado(af.redigir(f"{cabeca}\n{trecho or ''}")), MAX_EVIDENCIA)


# ══════════════════════════════════════════════════════════════════════════
# Fatos: gravar (upsert por retrato, com obsolescência)
# ══════════════════════════════════════════════════════════════════════════

def _normalizar_fatos(fatos: list[dict]) -> list[dict]:
    saida, vistos = [], set()
    for f in fatos:
        tipo = str(f.get("tipo") or "")
        chave = _c(f.get("chave"), _L_CHAVE)
        if tipo not in TIPOS_FATO or not chave:
            continue
        if (tipo, chave) in vistos:
            continue
        vistos.add((tipo, chave))
        saida.append({"tipo": tipo, "chave": chave, "valor_json": _json_valor(f.get("valor"))})
        if len(saida) >= MAX_FATOS_POR_RETRATO:
            break
    return saida


def gravar_fatos(conn, cur, *, ds_project: str, job_name: str, pipeline_name: str | None,
                 origem: str, fatos: list[dict], evidencia: str, ds_last_modified: str | None,
                 matricula: str, parcial: bool = False) -> dict:
    """Grava o RETRATO de uma origem para um job, numa transação:

      • chave nova → INSERT;
      • chave igual com o mesmo valor → só renova `lido_em`/`lido_por`/evidência;
      • chave igual com valor diferente → a antiga ganha `obsoleto_em` e entra
        uma nova (a mudança fica visível na auditoria);
      • chave que sumiu do retrato → `obsoleto_em` — EXCETO com `parcial=True`
        (a leitura foi cortada: o que "sumiu" pode só estar depois do corte;
        achado da revisão adversarial da F5).

    `origem` fora de `ORIGENS_FERRAMENTA` → `ValueError` (critério 1: fato
    só de ferramenta). Retrato vazio → não faz nada (ver o docstring do
    módulo). Um `sp_getapplock` por (projeto, job) serializa duas conversas
    lendo o mesmo job ao mesmo tempo — sem ele, as duas veriam o retrato
    antigo e ambas inseririam as mesmas chaves."""
    if origem not in ORIGENS_FERRAMENTA:
        raise ValueError(f"origem de fato não permitida: {origem!r}")
    novos = _normalizar_fatos(fatos)
    if not novos:
        return {"novos": 0, "confirmados": 0, "obsoletos": 0}
    projeto = _c(ds_project, _L_PROJETO)
    job = _c(job_name, _L_JOB)
    pipeline = _c(pipeline_name, _L_JOB) or None
    lm = _c(ds_last_modified, _L_LAST_MODIFIED) or None
    evid = cortar_utf16(sem_cifrado(evidencia or ""), MAX_EVIDENCIA)
    contagem = {"novos": 0, "confirmados": 0, "obsoletos": 0}
    try:
        cur.execute(
            "DECLARE @r INT; EXEC @r = sp_getapplock @Resource = ?, @LockMode = 'Exclusive', "
            "@LockOwner = 'Transaction', @LockTimeout = 5000; SELECT @r",
            [cortar_utf16(f"agente_fato:{projeto}:{job}", 255)])
        row = cur.fetchone()
        if row is None or int(row[0] or 0) < 0:
            raise RuntimeError("lock de fatos ocupado")
        cur.execute(
            "SELECT id, tipo, chave, valor_json FROM dbo.etl_agente_fato "
            "WHERE ds_project = ? AND job_name = ? AND origem = ? AND obsoleto_em IS NULL",
            [projeto, job, origem])
        atuais = {(r[1], r[2]): (r[0], r[3]) for r in cur.fetchall()}
        vistos = set()
        for f in novos:
            chave = (f["tipo"], f["chave"])
            vistos.add(chave)
            atual = atuais.get(chave)
            if atual is not None and (atual[1] or None) == (f["valor_json"] or None):
                cur.execute(
                    "UPDATE dbo.etl_agente_fato SET lido_em = GETDATE(), lido_por = ?, evidencia = ?, "
                    "ds_last_modified = ?, pipeline_name = ? WHERE id = ?",
                    [matricula, evid, lm, pipeline, atual[0]])
                contagem["confirmados"] += 1
                continue
            if atual is not None:
                cur.execute("UPDATE dbo.etl_agente_fato SET obsoleto_em = GETDATE() WHERE id = ?", [atual[0]])
                contagem["obsoletos"] += 1
            cur.execute(
                "INSERT INTO dbo.etl_agente_fato (ds_project, job_name, pipeline_name, tipo, chave, "
                "valor_json, origem, evidencia, ds_last_modified, lido_por) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [projeto, job, pipeline, f["tipo"], f["chave"], f["valor_json"], origem, evid, lm, matricula])
            contagem["novos"] += 1
        for chave, (fato_id, _v) in atuais.items():
            if chave not in vistos and not parcial:
                cur.execute("UPDATE dbo.etl_agente_fato SET obsoleto_em = GETDATE() WHERE id = ?", [fato_id])
                contagem["obsoletos"] += 1
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    return contagem


# ══════════════════════════════════════════════════════════════════════════
# Fatos: ler (a ferramenta `base` — "base primeiro")
# ══════════════════════════════════════════════════════════════════════════

MAX_INTERPRETACOES_NA_BASE = 5
MAX_TEXTO_INTERPRETACAO = 600


def separar_interpretacoes(fatos: list[dict]) -> tuple[list[dict], list[dict]]:
    """(lidos por ferramenta, interpretações aprovadas) — a `base` entrega as
    interpretações numa chave PRÓPRIA no topo da resposta, compactas e
    rotuladas. No fim da lista de fatos elas eram cortadas pelo teto de
    6000 caracteres em qualquer job de porte médio (regressão apontada pela
    2ª rodada da revisão adversarial da F5): o usuário aprovava e o modelo
    nunca via. A chave própria mantém o rótulo "não foi lida por
    ferramenta" sem depender da posição na lista."""
    lidos = [f for f in fatos if f.get("origem") != ORIGEM_INTERPRETACAO]
    interp = []
    for f in fatos:
        if f.get("origem") != ORIGEM_INTERPRETACAO or len(interp) >= MAX_INTERPRETACOES_NA_BASE:
            continue
        item = dict(f)
        if "valor" in item:
            texto = item["valor"] if isinstance(item["valor"], str) else json.dumps(
                item["valor"], ensure_ascii=False, default=str)
            item["valor"] = texto[:MAX_TEXTO_INTERPRETACAO]
        interp.append(item)
    return lidos, interp


def ler_fatos(cur, ds_project: str, job_name: str, validade_dias: int) -> list[dict]:
    """Fatos VIGENTES do job, para a ferramenta `base`. Cada um diz de onde
    veio e quão velho está: `dsjob_*` vale `validade_dias` a partir de
    `lido_em` (D-08: o `dsjob` não expõe data de modificação — padrão de 7
    dias); ISX/DSX carregam a data do próprio job/arquivo em
    `ds_last_modified`. `vencido: True` é o sinal para o modelo reler ao
    vivo antes de afirmar algo que pode ter mudado (risco 5)."""
    cur.execute(
        "SELECT TOP (?) tipo, chave, valor_json, origem, ds_last_modified, "
        "       DATEDIFF(day, lido_em, GETDATE()), aprovado_por, aprovado_em "
        "FROM dbo.etl_agente_fato "
        "WHERE ds_project = ? AND job_name = ? AND obsoleto_em IS NULL "
        # Leitura de ferramenta PRIMEIRO; interpretação aprovada por último —
        # é opinião de um usuário, não dado lido (revisão de segurança da F5).
        "ORDER BY CASE WHEN origem = 'interpretacao_aprovada' THEN 1 ELSE 0 END, origem, tipo, chave",
        [MAX_FATOS_NA_BASE, ds_project, job_name])
    linhas = cur.fetchall()
    if not isinstance(linhas, list):
        return []
    saida = []
    for r in linhas:
        idade = int(r[5]) if r[5] is not None else None
        item = {"tipo": r[0], "chave": r[1], "origem": r[3], "lido_ha_dias": idade}
        valor = af._json_ou(r[2], None)
        if valor is not None:
            item["valor"] = valor
        if r[4]:
            item["data_do_job_ou_arquivo"] = r[4]
        if str(r[3]).startswith("dsjob_"):
            item["vencido"] = idade is not None and idade > validade_dias
        if r[3] == ORIGEM_INTERPRETACAO:
            # A matrícula de quem aprovou NÃO vai ao modelo (ele repetiria na
            # resposta a outro usuário); só quando, e o aviso do que isto é.
            item["aprovado_em"] = str(r[7]) if r[7] else None
            item["nota"] = "interpretação aprovada por um usuário — não foi lida por ferramenta"
        saida.append(item)
    return saida


# ══════════════════════════════════════════════════════════════════════════
# Propostas: extrair do texto do modelo e passar pela régua
# ══════════════════════════════════════════════════════════════════════════

MAX_PROPOSTAS_POR_RESPOSTA = 3
MIN_EVIDENCIA = 8

_RE_BLOCO_JSON = re.compile(r"```[ \t]*(?:json)?[ \t]*\n?(\{(?:(?!```).)*\})\s*```", re.S | re.I)


def extrair_propostas(texto: str) -> tuple[str, list]:
    """(texto sem os blocos, propostas brutas). Bloco ```json com a chave
    `propostas` (lista) ou `proposta` (objeto) — o mesmo formato do pedido
    de ferramenta, com outra chave. Sai do texto que o usuário lê: o cartão
    é quem mostra a proposta."""
    texto = texto or ""
    brutas: list = []
    trechos = []
    for m in _RE_BLOCO_JSON.finditer(texto):
        try:
            obj = json.loads(m.group(1))
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        if isinstance(obj.get("propostas"), list):
            brutas.extend(obj["propostas"])
        elif isinstance(obj.get("proposta"), dict):
            brutas.append(obj["proposta"])
        else:
            continue
        trechos.append((m.start(), m.end()))
    for ini, fim in reversed(trechos):
        texto = texto[:ini] + texto[fim:]
    return texto.strip(), brutas


def _normalizar_espacos(s: str) -> str:
    """Espaços colapsados, e os escapes de JSON desfeitos: as saídas de
    `isx_extrair`/`dsx_consulta` chegam ao modelo como `json.dumps`, então
    uma quebra de linha de um SQL aparece como `\\n` LITERAL; o modelo copia
    isso dentro do JSON da proposta, o `json.loads` vira quebra de verdade, e
    a cópia fiel deixava de bater (achado da revisão adversarial da F5). Os
    dois lados passam por aqui, então a comparação é simétrica."""
    t = (s or "").replace("\\n", " ").replace("\\r", " ").replace("\\t", " ").replace('\\"', '"')
    return " ".join(t.split())


def _parece_segredo(texto: str) -> bool:
    """A régua de segredo da proposta é mais dura que a de exibição: se
    `redigir()` mexeria em QUALQUER parte, ou se há um valor cifrado do
    DataStage, a proposta cai inteira. Uma proposta recusada por engano
    custa uma nova pergunta; um segredo aprovado vira fato permanente."""
    if not texto:
        return False
    if "{iisenc}" in texto.lower() or "••••" in texto:
        return True
    return af.redigir(texto) != texto


def validar_proposta(bruta, *, projeto: str | None, saidas: list[dict]) -> tuple[dict | None, str | None]:
    """(proposta normalizada, None) ou (None, motivo da recusa).

    `saidas` = as LEITURAS desta pergunta, `{"job", "texto"}` (já redigidas):
    só `dsjob`/`isx_extrair`/`dsx_consulta` que deram certo sobre um job —
    nunca mensagem do orquestrador nem a saída da `base` (ver `conversar`).
    O `job_name` da proposta tem de ser um desses jobs, e a evidência tem de
    aparecer, literal (espaços normalizados), no que ESSA leitura devolveu —
    é o que amarra a interpretação ao que foi lido de verdade, em vez de a um
    texto que o modelo escreveu (ou ecoou) para se justificar."""
    if not isinstance(bruta, dict):
        return None, "formato inválido"
    if not projeto:
        return None, "sem projeto resolvido na conversa"
    tipo = str(bruta.get("tipo") or "").strip()
    if tipo not in TIPOS_FATO:
        return None, f"tipo '{tipo[:30]}' desconhecido"
    job = str(bruta.get("job_name") or "").strip()
    chave = str(bruta.get("chave") or "").strip()
    if not job or cortar_utf16(job, _L_JOB) != job:
        return None, "job_name ausente ou longo demais"
    if not chave or cortar_utf16(chave, _L_CHAVE) != chave:
        return None, "chave ausente ou longa demais"
    valor = bruta.get("valor")
    if valor is None or valor == "":
        return None, "sem valor"
    valor_txt = json.dumps(valor, ensure_ascii=False, default=str, sort_keys=True)
    if len(valor_txt) > MAX_VALOR_JSON:
        return None, "valor longo demais"
    motivo = str(bruta.get("motivo") or "").strip()
    if cortar_utf16(motivo, _L_MOTIVO) != motivo:
        return None, "motivo longo demais"
    evidencia = str(bruta.get("evidencia") or "").strip()
    if len(evidencia) < MIN_EVIDENCIA or len(evidencia) > MAX_EVIDENCIA:
        return None, "evidência ausente, curta ou longa demais"
    if sem_cifrado(evidencia) != evidencia:
        # Evidência não passa por `_parece_segredo` (vem de saída já redigida,
        # que pode ter "••••"), mas um valor cifrado ali ficaria permanente.
        return None, "parece conter segredo"
    for campo in (job, chave, valor_txt, motivo):
        if _parece_segredo(campo):
            return None, "parece conter segredo"
    leituras = [s.get("texto") or "" for s in saidas if isinstance(s, dict) and s.get("job") == job]
    if not leituras:
        return None, "o job da proposta não foi lido por nenhuma ferramenta nesta pergunta"
    alvo = _normalizar_espacos(evidencia)
    if not any(alvo in _normalizar_espacos(t) for t in leituras):
        return None, "a evidência não confere com o que as ferramentas leram nesta pergunta"
    return {"ds_project": projeto, "job_name": job, "tipo": tipo, "chave": chave,
            "valor_json": valor_txt, "motivo": motivo or None, "evidencia": evidencia}, None


def filtrar_propostas(brutas: list, *, projeto: str | None, saidas: list[dict]) -> tuple[list[dict], list[str]]:
    """(válidas, motivos das recusadas) — no máximo `MAX_PROPOSTAS_POR_RESPOSTA`
    válidas; o excedente é recusado com motivo, não sumido em silêncio."""
    validas: list[dict] = []
    recusadas: list[str] = []
    for b in brutas:
        if len(validas) >= MAX_PROPOSTAS_POR_RESPOSTA:
            recusadas.append(f"limite de {MAX_PROPOSTAS_POR_RESPOSTA} propostas por resposta")
            continue
        p, motivo = validar_proposta(b, projeto=projeto, saidas=saidas)
        if p is None:
            recusadas.append(motivo or "recusada")
        else:
            validas.append(p)
    return validas, recusadas


# ══════════════════════════════════════════════════════════════════════════
# Propostas: persistir, listar e decidir
# ══════════════════════════════════════════════════════════════════════════

_COLS_PROPOSTA = ("id, ds_project, job_name, tipo, chave, valor_json, evidencia, motivo, estado, "
                  "criada_em, decidida_por, decidida_em, fato_id")


def _iso(v) -> str | None:
    if v is None:
        return None
    try:
        return v.isoformat(sep=" ", timespec="seconds")
    except AttributeError:
        return str(v)


def proposta_para_api(r) -> dict:
    return {"id": int(r[0]), "ds_project": r[1], "job_name": r[2], "tipo": r[3], "chave": r[4],
            "valor": af._json_ou(r[5], r[5]), "evidencia": r[6], "motivo": r[7], "estado": r[8],
            "criada_em": _iso(r[9]), "decidida_por": r[10], "decidida_em": _iso(r[11]),
            "fato_id": int(r[12]) if r[12] is not None else None}


def inserir_propostas(cur, *, conversa_id: str, agente: str, matricula: str,
                      propostas: list[dict]) -> list[dict]:
    """INSERT de cada proposta válida (na transação de quem chama) e devolve
    o que a tela precisa para o cartão, já com o `id`."""
    saida = []
    for p in propostas:
        cur.execute(
            "INSERT INTO dbo.etl_agente_proposta (conversa_id, agente, matricula, ds_project, job_name, "
            "tipo, chave, valor_json, evidencia, motivo) "
            "OUTPUT INSERTED.id, INSERTED.criada_em VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [conversa_id, agente, matricula, _c(p["ds_project"], _L_PROJETO), p["job_name"], p["tipo"],
             p["chave"], p["valor_json"], p["evidencia"], p["motivo"]])
        row = cur.fetchone()
        saida.append({"id": int(row[0]), "ds_project": p["ds_project"], "job_name": p["job_name"],
                      "tipo": p["tipo"], "chave": p["chave"], "valor": af._json_ou(p["valor_json"], None),
                      "evidencia": p["evidencia"], "motivo": p["motivo"], "estado": "pendente",
                      "criada_em": _iso(row[1]), "decidida_por": None, "decidida_em": None, "fato_id": None})
    return saida


def propostas_da_conversa(cur, conversa_id: str, matricula: str) -> list[dict]:
    """As propostas de UMA conversa, do dono — para o cartão reaparecer ao
    retomar, com o estado atual (aprovada/recusada/pendente)."""
    cur.execute(
        f"SELECT {_COLS_PROPOSTA} FROM dbo.etl_agente_proposta "
        "WHERE conversa_id = ? AND matricula = ? ORDER BY id", [conversa_id, matricula])
    linhas = cur.fetchall()
    return [proposta_para_api(r) for r in linhas] if isinstance(linhas, list) else []


class PropostaNaoEncontrada(Exception):
    """Inexistente OU de outro usuário — o router responde 404 igual nos dois
    casos (sem oráculo de ids, a mesma régua das conversas)."""


class PropostaJaDecidida(Exception):
    def __init__(self, proposta: dict):
        super().__init__("proposta já decidida")
        self.proposta = proposta


class PropostaExpirada(Exception):
    pass


DECISOES = {"aprovar": "aprovada", "recusar": "recusada"}


def decidir_proposta(conn, cur, *, proposta_id: int, matricula: str, decisao: str,
                     retencao_dias: int) -> dict:
    """Aprovar ou recusar, idempotente (critério 3):

      • o `UPDATE ... WHERE estado = 'pendente'` só vale para UMA chamada —
        duas abas aprovando juntas não geram dois fatos (a 2ª vê rowcount 0);
      • repetir a MESMA decisão devolve o estado atual (200, sem efeito);
        pedir a decisão OPOSTA depois de decidida é `PropostaJaDecidida`;
      • aprovar grava o fato `interpretacao_aprovada` na MESMA transação, com
        `aprovado_por`/`aprovado_em` — e obsoleta a interpretação aprovada
        anterior para a mesma chave (a nova a substitui);
      • recusar não grava fato nenhum;
      • pendente há mais que a retenção das conversas vira `expirada`: a
        conversa que dava contexto a ela já foi purgada."""
    novo_estado = DECISOES.get(decisao)
    if novo_estado is None:
        raise ValueError("decisão deve ser 'aprovar' ou 'recusar'")
    try:
        cur.execute(
            f"SELECT {_COLS_PROPOSTA}, matricula, DATEDIFF(day, criada_em, GETDATE()) "
            "FROM dbo.etl_agente_proposta WITH (UPDLOCK, HOLDLOCK) WHERE id = ?", [proposta_id])
        row = cur.fetchone()
        if row is None or row[13] != matricula:
            raise PropostaNaoEncontrada()
        atual = proposta_para_api(row)
        if atual["estado"] != "pendente":
            conn.rollback()
            if atual["estado"] == novo_estado:
                return {**atual, "ja_decidida": True}
            if atual["estado"] == "expirada":
                raise PropostaExpirada()
            raise PropostaJaDecidida(atual)
        if row[14] is not None and int(row[14]) > retencao_dias:
            cur.execute("UPDATE dbo.etl_agente_proposta SET estado = 'expirada' "
                        "WHERE id = ? AND estado = 'pendente'", [proposta_id])
            conn.commit()
            raise PropostaExpirada()
        cur.execute(
            "UPDATE dbo.etl_agente_proposta SET estado = ?, decidida_por = ?, decidida_em = GETDATE() "
            "WHERE id = ? AND matricula = ? AND estado = 'pendente'",
            [novo_estado, matricula, proposta_id, matricula])
        if int(cur.rowcount or 0) != 1:
            # Outra chamada decidiu entre o SELECT e o UPDATE (não deveria,
            # com o UPDLOCK — mas o rowcount é a garantia, não o lock).
            conn.rollback()
            raise PropostaJaDecidida(atual)
        fato_id = None
        if novo_estado == "aprovada":
            # Duas propostas DIFERENTES para a mesma chave aprovadas ao mesmo
            # tempo: sob RCSI, o UPDATE de uma não vê o INSERT não commitado
            # da outra, e ficariam duas interpretações vigentes. O lock por
            # chave serializa (apontado pela revisão adversarial da F5).
            cur.execute(
                "DECLARE @r INT; EXEC @r = sp_getapplock @Resource = ?, @LockMode = 'Exclusive', "
                "@LockOwner = 'Transaction', @LockTimeout = 5000; SELECT @r",
                [cortar_utf16(f"agente_interp:{atual['ds_project']}:{atual['job_name']}:"
                              f"{atual['tipo']}:{atual['chave']}", 255)])
            trava = cur.fetchone()
            if trava is None or int(trava[0] or 0) < 0:
                raise RuntimeError("lock da interpretação ocupado")
            cur.execute(
                "UPDATE dbo.etl_agente_fato SET obsoleto_em = GETDATE() "
                "WHERE ds_project = ? AND job_name = ? AND tipo = ? AND chave = ? "
                "AND origem = ? AND obsoleto_em IS NULL",
                [atual["ds_project"], atual["job_name"], atual["tipo"], atual["chave"], ORIGEM_INTERPRETACAO])
            cur.execute(
                "INSERT INTO dbo.etl_agente_fato (ds_project, job_name, tipo, chave, valor_json, origem, "
                "evidencia, lido_por, aprovado_por, aprovado_em) "
                "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())",
                [atual["ds_project"], atual["job_name"], atual["tipo"], atual["chave"], row[5],
                 ORIGEM_INTERPRETACAO, row[6], matricula, matricula])
            fato_id = int(cur.fetchone()[0])
            cur.execute("UPDATE dbo.etl_agente_proposta SET fato_id = ? WHERE id = ?", [fato_id, proposta_id])
        cur.execute(f"SELECT {_COLS_PROPOSTA} FROM dbo.etl_agente_proposta WHERE id = ?", [proposta_id])
        final = proposta_para_api(cur.fetchone())
        conn.commit()
        return final
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
