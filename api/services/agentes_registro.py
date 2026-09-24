"""Agentes criados pela tela (B1 da spec docs/spec-agentes-admin.md §4.1–§4.2).

O DataStage continua no `CATALOGO` do código (`services/agentes.py`). Os
agentes que o admin cria moram em `dbo.etl_agente` (migration 121) e entram no
MESMO formato de dicionário, por `carregar(cur)` — que as funções de catálogo e
acesso de `services/agentes` recebem em `agentes=`.

  • **Sem cache**: o registro é lido a cada requisição que precisa dele, como a
    versão do prompt (T2 — a API roda com 2 workers). Criar, desativar ou mudar
    o acesso vale na próxima requisição, nos dois.
  • **Id nunca reaproveitado**: desativar é `ativo = 0`; não há exclusão.
  • **Recursos sem colisão**: `agente_<id>` (uso) e `agente_<id>_curador`
    (só com ferramentas). Os ids `curador` e `*_curador` são reservados — senão
    um grant daria dois papéis (o uso de `curador` seria o `agente_curador` do
    DataStage).
"""
from __future__ import annotations

import json
import logging
import re

from services import agentes as svc
from services import agentes_prompt as apr
from services.ssh_arquivos import utf16_len

logger = logging.getLogger(__name__)

# `\A…\Z`, não `^…$`: em Python o `$` casa ANTES de um `\n` final, e
# "datastage\n" passava pelo formato E escapava dos reservados (revisão da B1).
RE_ID = re.compile(r"\A[a-z][a-z0-9_]{2,29}\Z")
# Palavras das rotas `/agentes/<x>/…` — um agente com esse id ficaria à sombra
# de uma rota fixa.
_IDS_DE_ROTA = frozenset({"admin", "catalogo", "status", "conversas", "propostas", "aprendizados"})
NOME_MAX, DESCRICAO_MAX, PERFIS_JSON_MAX = 100, 500, 200  # unidades UTF-16 (NVARCHAR)
MAX_PARES_BANCO = 50
CONEXAO_MAX, BANCO_MAX = 100, 128  # etl_conexao.conn_id VARCHAR(100); sysname
ACESSOS = ("manual", "perfil")


def id_reservado(agente_id: str) -> bool:
    return (agente_id in svc.CATALOGO or agente_id in _IDS_DE_ROTA
            or agente_id == "curador" or agente_id.endswith("_curador"))


class AgenteInvalido(ValueError):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


# ── leitura ─────────────────────────────────────────────────────────────────

_COLS = ("agente_id, nome, descricao, acesso, perfis_json, ferramentas_json, ativo, "
         "criado_em, criado_por, atualizado_em, atualizado_por")
# Migration 122 (ferramenta de banco). Sem ela, lê-se `_COLS` e o agente
# fica sem banco nenhum — o que fecha a ferramenta, nunca abre.
_COLS_122 = _COLS + ", bancos_json, mascarar_dados"


def _coluna_ausente(e: Exception) -> bool:
    """Coluna inexistente (SQLSTATE 42S22 / erro 207) — a 122 não rodou."""
    args = getattr(e, "args", None) or ()
    return (bool(args) and str(args[0]) == "42S22") or "(207)" in str(e)


def _selecionar(cur, onde: str = "", params=()):
    try:
        cur.execute(f"SELECT {_COLS_122} FROM dbo.etl_agente{onde}", list(params))
    except Exception as e:  # noqa: BLE001
        if not _coluna_ausente(e):
            raise
        cur.execute(f"SELECT {_COLS} FROM dbo.etl_agente{onde}", list(params))


def _lista_json(bruto) -> list[str]:
    try:
        v = json.loads(bruto or "[]")
    except (TypeError, ValueError):
        return []
    return [str(x) for x in v if isinstance(x, str)] if isinstance(v, list) else []


def _normalizar_ferramentas(nomes) -> tuple[str, ...]:
    """Só as da allowlist, na ordem canônica, e `resolver_projeto` junto de
    qualquer uma que dependa de projeto — a mesma regra da criação."""
    conjunto = {f for f in nomes if f in svc.FERRAMENTAS_TELA}
    if conjunto & {"base", "dsjob", "dsx_consulta", "isx_extrair"}:
        conjunto.add("resolver_projeto")
    return tuple(f for f in svc.FERRAMENTAS_TELA if f in conjunto)


def _pares_json(bruto) -> tuple[tuple[str, str], ...]:
    """`bancos_json` → pares `(conexao, banco)` sem repetição; o que não
    tiver o formato é descartado (linha editada à mão não amplia nada)."""
    try:
        v = json.loads(bruto or "[]")
    except (TypeError, ValueError):
        return ()
    pares: list[tuple[str, str]] = []
    for item in v if isinstance(v, list) else []:
        if isinstance(item, dict) and isinstance(item.get("conexao"), str) and isinstance(item.get("banco"), str):
            par = (item["conexao"].strip(), item["banco"].strip())
            if all(par) and par not in pares:
                pares.append(par)
    return tuple(pares)


def do_banco(r) -> dict:
    """Linha de `etl_agente` → o dicionário do catálogo. Uma linha editada à
    mão no banco NÃO amplia nada — as regras do código mandam aqui também:
      • ferramenta fora da allowlist é descartada; `resolver_projeto` entra
        quando precisa;
      • o perfil `consulta` sai da lista;
      • acesso 'perfil' com ferramenta de servidor vira 'manual' (fecha, não
        abre: D3 — sem isto o agente com `dsjob` ficava aberto ao perfil)."""
    agente_id = r[0]
    ferramentas = _normalizar_ferramentas(_lista_json(r[5]))
    bancos = _pares_json(r[11]) if len(r) > 11 else ()
    if not bancos:
        # Ferramenta de banco sem par liberado (ou antes da 122): sai.
        ferramentas = tuple(f for f in ferramentas if f not in svc.FERRAMENTAS_BANCO)
    else:
        bancos = bancos if any(f in svc.FERRAMENTAS_BANCO for f in ferramentas) else ()
    mascarar = bool(r[12]) if len(r) > 12 and r[12] is not None else True
    acesso = r[3] if r[3] in ACESSOS else "manual"
    if acesso == "perfil" and any(f in svc.FERRAMENTAS_SERVIDOR for f in ferramentas):
        acesso = "manual"
    return {
        "id": agente_id, "nome": r[1], "descricao": r[2],
        "recurso": f"agente_{agente_id}",
        "recurso_curador": f"agente_{agente_id}_curador" if ferramentas else None,
        "config_enabled": None,
        "perfis_elegiveis": tuple(p for p in _lista_json(r[4]) if p not in svc.PERFIS_PROIBIDOS),
        "concessao": "manual_por_usuario" if acesso == "manual" else "perfil",
        "origem": "banco", "acesso": acesso, "ferramentas": ferramentas, "ativo": bool(r[6]),
        "bancos": bancos, "mascarar_dados": mascarar,
        "criado_em": r[7], "criado_por": r[8], "atualizado_em": r[9], "atualizado_por": r[10],
    }


def carregar(cur) -> dict[str, dict]:
    """Código + banco, com o do código sempre ganhando num id repetido (não
    deveria existir: é reservado na criação). Sem a tabela (antes da 121) ou
    com erro de leitura, fica só o código — o DataStage não depende disto."""
    agentes = dict(svc.CATALOGO)
    try:
        _selecionar(cur)
        linhas = cur.fetchall()
    except Exception:  # noqa: BLE001
        logger.warning("agentes: leitura de dbo.etl_agente falhou — só os agentes do código", exc_info=True)
        return agentes
    for r in linhas:
        # Id fora do formato ou reservado (linha gravada à mão): ignorado. Um
        # `curador` aqui teria o recurso `agente_curador` do DataStage e o
        # mapa de recursos recusaria a carga — derrubando todo user_perm_set.
        if not isinstance(r[0], str) or not RE_ID.match(r[0]) or id_reservado(r[0]):
            logger.warning("agentes: id %r do banco é inválido ou reservado — ignorado", r[0])
            continue
        agentes[r[0]] = do_banco(r)
    return agentes


def um(cur, agente_id: str) -> dict | None:
    """O agente pelo id — código primeiro (sem banco), depois `etl_agente`
    (com a mesma régua de `carregar`: id inválido ou reservado não existe)."""
    if agente_id in svc.CATALOGO:
        return svc.CATALOGO[agente_id]
    if not RE_ID.match(agente_id) or id_reservado(agente_id):
        return None
    _selecionar(cur, " WHERE agente_id = ?", [agente_id])
    r = cur.fetchone()
    # A comparação do banco ignora maiúsculas e espaço no fim: 'foo' acha uma
    # linha 'Foo' ou 'foo ' gravada à mão — que `carregar` ignora. Só vale a
    # linha cujo id é EXATAMENTE o pedido, para os dois nunca discordarem.
    return do_banco(r) if r and r[0] == agente_id else None


def perfis_existentes(cur) -> set[str]:
    cur.execute("SELECT perfil_nome FROM dbo.etl_perfil")
    return {r[0] for r in cur.fetchall()}


# ── validação ───────────────────────────────────────────────────────────────

def _texto(valor, campo: str, maximo: int) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise AgenteInvalido(f"{campo}_obrigatorio", f"{campo} é obrigatório")
    t = valor.strip()
    if utf16_len(t) > maximo:
        raise AgenteInvalido(f"{campo}_grande", f"{campo} passa de {maximo} caracteres")
    achados = [m for m in apr.MARCADORES_RESERVADOS if m in t]
    if achados:
        raise AgenteInvalido("texto_com_marcador", f"{campo} usa trechos reservados do protocolo: {', '.join(achados)}")
    return t


def _perfis(valor, existentes: set[str]) -> list[str]:
    if not isinstance(valor, list) or not valor or not all(isinstance(p, str) and p.strip() for p in valor):
        raise AgenteInvalido("perfis_obrigatorios", "informe ao menos um perfil")
    perfis = sorted({p.strip() for p in valor})
    proibidos = [p for p in perfis if p in svc.PERFIS_PROIBIDOS]
    if proibidos:
        raise AgenteInvalido("perfil_nao_permitido",
                             f"o perfil {', '.join(proibidos)} não pode receber agente "
                             "(é o perfil de quem entra sem cadastro)")
    desconhecidos = [p for p in perfis if p not in existentes]
    if desconhecidos:
        raise AgenteInvalido("perfil_desconhecido", f"perfil inexistente: {', '.join(desconhecidos)}")
    if utf16_len(json.dumps(perfis, ensure_ascii=False)) > PERFIS_JSON_MAX:
        raise AgenteInvalido("perfis_demais", "perfis demais para um agente")
    return perfis


def _ferramentas(valor) -> list[str]:
    if not isinstance(valor, list) or not all(isinstance(f, str) for f in valor):
        raise AgenteInvalido("ferramentas_invalidas", "ferramentas deve ser uma lista (vazia = só conversa)")
    fora = sorted({f for f in valor if f not in svc.FERRAMENTAS_TELA})
    if fora:
        raise AgenteInvalido("ferramentas_invalidas",
                             f"ferramenta fora da allowlist: {', '.join(fora)} — ferramenta nova só por PR")
    # Toda ferramenta que depende de projeto precisa de quem o resolve.
    return list(_normalizar_ferramentas(valor))


def _bancos(valor) -> list[tuple[str, str]]:
    """Corpo `bancos: [{"conexao": "...", "banco": "..."}]` → pares sem
    repetição. Só o FORMATO — a conferência no servidor (abre, existe, tem
    SHOWPLAN) é do router, só para os pares novos (`pares_novos`)."""
    if not isinstance(valor, list):
        raise AgenteInvalido("bancos_invalidos", 'bancos deve ser uma lista de {"conexao", "banco"}')
    pares: list[tuple[str, str]] = []
    for item in valor:
        if not (isinstance(item, dict) and isinstance(item.get("conexao"), str)
                and isinstance(item.get("banco"), str) and item["conexao"].strip() and item["banco"].strip()):
            raise AgenteInvalido("bancos_invalidos", 'cada banco liberado precisa de "conexao" e "banco"')
        par = (item["conexao"].strip(), item["banco"].strip())
        if len(par[0]) > CONEXAO_MAX or len(par[1]) > BANCO_MAX:
            raise AgenteInvalido("bancos_invalidos", "nome de conexão ou de banco longo demais")
        if par not in pares:
            pares.append(par)
    if len(pares) > MAX_PARES_BANCO:
        raise AgenteInvalido("bancos_demais", f"no máximo {MAX_PARES_BANCO} bancos por agente")
    return pares


def _coerencia_bancos(ferramentas: list[str], bancos: list[tuple[str, str]], veio_no_corpo: bool) -> list:
    """Com ferramenta de banco, pelo menos um par; sem ela, nenhum — mas
    tirar a ferramenta sem mandar `bancos` limpa os pares (não é erro)."""
    usa_banco = any(f in svc.FERRAMENTAS_BANCO for f in ferramentas)
    if usa_banco and not bancos:
        raise AgenteInvalido("bancos_obrigatorios", "a consulta a banco precisa de pelo menos um banco liberado")
    if not usa_banco and bancos:
        if veio_no_corpo:
            raise AgenteInvalido("bancos_sem_ferramenta", "bancos liberados só valem com a consulta a banco")
        return []
    return bancos


def _mascarar(valor) -> bool:
    if not isinstance(valor, bool):
        raise AgenteInvalido("mascarar_invalido", "mascarar_dados deve ser true ou false")
    return valor


def pares_novos(atual: dict | None, novo: dict) -> list[tuple[str, str]]:
    """Os pares que o router confere no servidor: os que não estavam no
    agente. Pares que não mudaram não são reconferidos — um servidor fora do
    ar não impede renomear o agente (spec ferramenta-banco §2)."""
    antes = set(atual.get("bancos", ())) if atual else set()
    return [p for p in novo["bancos"] if p not in antes]


def _coerencia(acesso: str, ferramentas: list[str]) -> None:
    if acesso not in ACESSOS:
        raise AgenteInvalido("acesso_invalido", "acesso deve ser 'manual' ou 'perfil'")
    servidor = [f for f in ferramentas if f in svc.FERRAMENTAS_SERVIDOR]
    if acesso == "perfil" and servidor:
        raise AgenteInvalido("acesso_perfil_com_servidor",
                             f"acesso por perfil não vale para agente que toca o servidor ({', '.join(servidor)}) "
                             "— use concessão manual, como no DataStage")


def validar_criacao(body: dict, perfis_do_banco: set[str]) -> dict:
    """Corpo do POST → campos prontos para gravar. O prompt inicial e o
    motivo passam pelas mesmas regras de uma versão (Fase A)."""
    agente_id = body.get("id")
    if not isinstance(agente_id, str) or not RE_ID.match(agente_id):
        raise AgenteInvalido("agente_id_invalido",
                             "id: 3 a 30 caracteres, minúsculas, números e _, começando por letra")
    if id_reservado(agente_id):
        raise AgenteInvalido("agente_id_reservado", f"o id '{agente_id}' é reservado")
    campos = {
        "id": agente_id,
        "nome": _texto(body.get("nome"), "nome", NOME_MAX),
        "descricao": _texto(body.get("descricao"), "descricao", DESCRICAO_MAX),
        "acesso": body.get("acesso"),
        "perfis": _perfis(body.get("perfis"), perfis_do_banco),
        "ferramentas": _ferramentas(body.get("ferramentas", [])),
        "mascarar_dados": _mascarar(body.get("mascarar_dados", True)),
    }
    campos["bancos"] = _coerencia_bancos(campos["ferramentas"], _bancos(body.get("bancos", [])),
                                         "bancos" in body)
    _coerencia(campos["acesso"], campos["ferramentas"])
    try:
        campos["prompt"] = apr.validar_texto(body.get("prompt"))
        campos["motivo"] = apr.validar_motivo(body.get("motivo"))
    except apr.PromptInvalido as e:
        raise AgenteInvalido(e.code, e.message) from None
    return campos


CAMPOS_ALTERAVEIS = ("nome", "descricao", "acesso", "perfis", "ferramentas", "ativo", "bancos", "mascarar_dados")


def _ferramentas_alteradas(atual: dict, body: dict) -> list[str]:
    """As ferramentas de banco só saem com `bancos` no corpo. A tela de antes
    da C2 só conhece as de DataStage e reenvia `ferramentas` sem elas a cada
    edição — sem esta regra, renomear o agente apagava a consulta a banco em
    silêncio (revisão da C1). Para tirar: `ferramentas` sem elas + `bancos: []`."""
    if "ferramentas" not in body:
        return list(atual["ferramentas"])
    novas = _ferramentas(body["ferramentas"])
    if "bancos" not in body and not any(f in svc.FERRAMENTAS_BANCO for f in novas):
        novas = list(_normalizar_ferramentas(novas + [f for f in atual["ferramentas"]
                                                       if f in svc.FERRAMENTAS_BANCO]))
    return novas


def validar_alteracao(atual: dict, body: dict, perfis_do_banco: set[str]) -> dict:
    """PUT parcial: o que não vier fica como está, e a combinação FINAL é
    validada inteira (ex.: trocar só o acesso para 'perfil' num agente com
    `dsjob` é recusado)."""
    desconhecidos = sorted(set(body) - set(CAMPOS_ALTERAVEIS))
    if desconhecidos:
        raise AgenteInvalido("campo_nao_alteravel", f"não dá para alterar: {', '.join(desconhecidos)}")
    if not body:
        raise AgenteInvalido("nada_para_alterar", "nada para alterar")
    if body == {"ativo": False}:
        # DESATIVAR sempre passa, mesmo com a linha num estado que hoje não
        # validaria (editada à mão): é a saída de emergência, e fecha acesso.
        return {"nome": atual["nome"], "descricao": atual["descricao"], "acesso": atual["acesso"],
                "perfis": list(atual["perfis_elegiveis"]), "ferramentas": list(atual["ferramentas"]),
                "bancos": list(atual.get("bancos", ())), "mascarar_dados": atual.get("mascarar_dados", True),
                "ativo": False}
    novo = {
        "nome": _texto(body["nome"], "nome", NOME_MAX) if "nome" in body else atual["nome"],
        "descricao": (_texto(body["descricao"], "descricao", DESCRICAO_MAX)
                      if "descricao" in body else atual["descricao"]),
        "acesso": body.get("acesso", atual["acesso"]),
        "perfis": _perfis(body["perfis"], perfis_do_banco) if "perfis" in body else list(atual["perfis_elegiveis"]),
        "ferramentas": _ferramentas_alteradas(atual, body),
        "mascarar_dados": (_mascarar(body["mascarar_dados"]) if "mascarar_dados" in body
                           else atual.get("mascarar_dados", True)),
        "ativo": atual["ativo"],
    }
    novo["bancos"] = _coerencia_bancos(
        novo["ferramentas"], _bancos(body["bancos"]) if "bancos" in body else list(atual.get("bancos", ())),
        "bancos" in body)
    if "ativo" in body:
        if not isinstance(body["ativo"], bool):
            raise AgenteInvalido("ativo_invalido", "ativo deve ser true ou false")
        novo["ativo"] = body["ativo"]
    if not novo["perfis"]:
        raise AgenteInvalido("perfis_obrigatorios", "informe ao menos um perfil")
    _coerencia(novo["acesso"], novo["ferramentas"])
    return novo


# ── gravação ────────────────────────────────────────────────────────────────

def _eh_pk_repetida(e: Exception) -> bool:
    msg = str(e)
    return any(x in msg for x in ("2627", "2601", "PK_etl_agente"))


def _bancos_para_gravar(campos: dict) -> str | None:
    pares = campos.get("bancos") or []
    return json.dumps([{"conexao": c, "banco": b} for c, b in pares], ensure_ascii=False) if pares else None


def _sem_122(campos: dict) -> bool:
    """Gravável sem as colunas da 122: sem banco e com o padrão de máscara."""
    return not campos.get("bancos") and campos.get("mascarar_dados", True) is True


def _migracao_122() -> AgenteInvalido:
    return AgenteInvalido("migracao_pendente",
                          "a consulta a banco exige a migration 122 — rode a etapa 6c do deploy", 503)


def criar(conn, cur, campos: dict, matricula: str) -> None:
    """Agente + versão 1 do prompt na MESMA transação: ou os dois ficam, ou
    nenhum (o `gravar_versao` faz o commit; um erro nele desfaz o INSERT)."""
    base = [campos["id"], campos["nome"], campos["descricao"], campos["acesso"],
            json.dumps(campos["perfis"], ensure_ascii=False), json.dumps(campos["ferramentas"])]
    try:
        try:
            cur.execute(
                "INSERT INTO dbo.etl_agente (agente_id, nome, descricao, acesso, perfis_json, ferramentas_json, "
                "bancos_json, mascarar_dados, ativo, criado_por, atualizado_por) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                base + [_bancos_para_gravar(campos), 1 if campos.get("mascarar_dados", True) else 0,
                        matricula, matricula])
        except Exception as e:  # noqa: BLE001
            if not _coluna_ausente(e):
                raise
            if not _sem_122(campos):
                raise _migracao_122() from None
            cur.execute(
                "INSERT INTO dbo.etl_agente (agente_id, nome, descricao, acesso, perfis_json, ferramentas_json, "
                "ativo, criado_por, atualizado_por) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
                base + [matricula, matricula])
    except AgenteInvalido:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    except Exception as e:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        if _eh_pk_repetida(e):
            raise AgenteInvalido("agente_existe", f"já existe um agente com o id '{campos['id']}'", 409) from e
        raise
    apr.gravar_versao(conn, cur, agente_id=campos["id"], texto=campos["prompt"], motivo=campos["motivo"],
                      matricula=matricula, versao_base=0)


def alterar(conn, cur, agente_id: str, novo: dict, matricula: str) -> None:
    base = [novo["nome"], novo["descricao"], novo["acesso"], json.dumps(novo["perfis"], ensure_ascii=False),
            json.dumps(novo["ferramentas"])]
    fim = [1 if novo["ativo"] else 0, matricula, agente_id]
    try:
        cur.execute(
            "UPDATE dbo.etl_agente SET nome = ?, descricao = ?, acesso = ?, perfis_json = ?, ferramentas_json = ?, "
            "bancos_json = ?, mascarar_dados = ?, "
            "ativo = ?, atualizado_em = GETDATE(), atualizado_por = ? WHERE agente_id = ?",
            base + [_bancos_para_gravar(novo), 1 if novo.get("mascarar_dados", True) else 0] + fim)
    except Exception as e:  # noqa: BLE001
        if not _coluna_ausente(e):
            raise
        if not _sem_122(novo):
            raise _migracao_122() from None
        cur.execute(
            "UPDATE dbo.etl_agente SET nome = ?, descricao = ?, acesso = ?, perfis_json = ?, ferramentas_json = ?, "
            "ativo = ?, atualizado_em = GETDATE(), atualizado_por = ? WHERE agente_id = ?", base + fim)
    conn.commit()
