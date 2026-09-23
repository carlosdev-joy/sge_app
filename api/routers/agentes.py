"""api/routers/agentes.py — tela Agentes: catálogo, status do gateway por
usuário, config do admin e a conversa com o agente DataStage (F1+F2 da spec
docs/spec-agentes-datastage.md).

  GET  /agentes/catalogo               agentes que o usuário logado pode abrir
  GET  /agentes/status                 estado da sonda de cadastro no gateway (cacheado)
  GET  /agentes/admin/config           config de Agentes (admin)
  POST /agentes/admin/config           grava config de Agentes (admin)
  POST /agentes/datastage/conversar    uma rodada com o agente DataStage (F2)
  POST /agentes/propostas/{id}/decidir aprovar/recusar uma proposta do agente (F5)
  GET  /agentes/aprendizados           fila do curador, por estado (F6)
  POST /agentes/aprendizados/{id}/decidir  validar/rejeitar/obsoletar (F6, curador)

`tela_agentes` é checada por `require_perm` puro — como qualquer outra tela
(perfil ∪ overrides). O que É especial é o acesso a CADA AGENTE
(`agente_datastage`, `agente_curador`): ver `services/agentes.require_agente`.

A conversa persiste em `etl_agente_conversa`/`etl_agente_mensagem` (migration
117), mas NÃO segura uma conexão de banco durante a rodada com o modelo — a
orquestração (`services.agentes.conversar`) abre conexões curtas, uma por
ferramenta, e só este router mantém uma conexão de cada vez (antes e depois
da rodada), nunca durante.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from db import get_db_conn
from deps import PERM_ADMIN, PERM_EDITAR, get_admin_user, require_perm
from services import agentes as svc
from services import agentes_aprendizado as ap
from services import agentes_conhecimento as ac
from services import agentes_ferramentas as af
from services import ia_provedor

router = APIRouter()
log = logging.getLogger(__name__)

_require_tela = require_perm("tela_agentes")
_require_datastage = svc.require_agente(svc.AGENTE_DATASTAGE)
_require_curador = svc.require_agente(svc.AGENTE_DATASTAGE, curador=True)

_RE_CAMPO = re.compile(r"^(header|body):.+$")
_RE_CONVERSA_ID = re.compile(r"^[A-Za-z0-9_-]{8,36}$")
_MAX_MENSAGEM = 4000  # mesmo teto do Maestro (MAX_MENSAGEM em maestro.py)


_FALSOS = {"0", "false", "no", "nao", "não", "off", ""}


def _verdadeiro(valor) -> bool:
    """Liga/desliga tolerante ao tipo que chegou no corpo.

    `bool(valor)` sozinho é uma armadilha aqui: a string `"0"` é VERDADEIRA
    em Python, então um cliente que mandasse `{"agentes_enabled": "0"}` —
    exatamente o que a aba do Admin mandava — DESLIGAVA pela tela e LIGAVA
    no banco. E como o "salvar" manda o rascunho inteiro, editar qualquer
    outro campo com os agentes desligados os religava sozinhos. Achado real
    da revisão adversarial da F3 (o interruptor geral é o kill switch de uma
    feature que fala com o gateway de IA — precisa desligar de verdade).

    Booleano continua valendo; string só é verdadeira quando não é uma das
    formas explícitas de "não".
    """
    if isinstance(valor, str):
        return valor.strip().lower() not in _FALSOS
    return bool(valor)


def _iso(valor) -> str | None:
    """`DATETIME2` do driver → ISO 8601, ou `None`. A tela mostra a data de
    cada resposta antiga (critério 3 da F4), e string pronta evita que cada
    consumidor invente o seu formato."""
    if valor is None:
        return None
    try:
        return valor.isoformat(sep=" ", timespec="seconds")
    except AttributeError:  # já veio string do driver
        return str(valor)


def _json_lista(bruto) -> list:
    """`artefatos_json` → lista. Conteúdo inválido (ou de uma versão
    anterior do formato) vira lista vazia: o histórico continua legível,
    só sem a trilha de ferramentas daquela resposta."""
    if not bruto:
        return []
    try:
        dado = json.loads(bruto)
    except (ValueError, TypeError):
        return []
    return dado if isinstance(dado, list) else []


def _separar_artefatos(lista: list) -> tuple[list, list[int]]:
    """`artefatos_json` guarda, na mesma lista, as ferramentas que rodaram
    (`{"ferramenta", "args"}`) e os ids das propostas daquela resposta
    (`{"proposta_id"}`, F5). A tela recebe os dois SEPARADOS: a linha
    "Consultei:" só conhece ferramenta, e o cartão só conhece proposta."""
    ferramentas, ids = [], []
    for a in lista:
        if not isinstance(a, dict):
            continue
        if "proposta_id" in a:
            try:
                ids.append(int(a["proposta_id"]))
            except (TypeError, ValueError):
                pass
        elif "ferramenta" in a:
            ferramentas.append(a)
    return ferramentas, ids


def _duracao_de(lista: list) -> int | None:
    """`{"duracao_ms"}` gravado junto com a resposta (quanto ela levou)."""
    for a in lista:
        if isinstance(a, dict) and isinstance(a.get("duracao_ms"), int):
            return a["duracao_ms"]
    return None


def _falhas_da_conversa(cur, conversa_id: str) -> set[str]:
    """As chamadas que já falharam de forma permanente NESTA conversa (F6,
    guarda de reexecução) — gravadas pela orquestração em `artefatos_json`
    como `{"falhou", "chamada"}`. Leitura tolerante: sem a informação, a
    guarda só vale dentro da pergunta atual (nada quebra)."""
    try:
        cur.execute(
            "SELECT artefatos_json FROM dbo.etl_agente_mensagem "
            "WHERE conversa_id = ? AND papel = 'assistant' AND artefatos_json LIKE ?",
            [conversa_id, '%"falhou"%'])
        falhas = set()
        for r in cur.fetchall() or []:
            for a in _json_lista(r[0] if r else None):
                if isinstance(a, dict) and a.get("falhou") and isinstance(a.get("chamada"), str):
                    falhas.add(a["chamada"])
        return falhas
    except Exception:  # noqa: BLE001
        return set()


def _validade_dias(cfg: dict) -> int:
    try:
        return max(1, int(cfg.get("agentes_fato_validade_dias") or 7))
    except (TypeError, ValueError):
        return 7


def _abrir():
    conn = get_db_conn()
    return conn, conn.cursor()


def _fechar(conn, cur, commit: bool = False) -> None:
    try:
        if commit:
            conn.commit()
    finally:
        for x in (cur, conn):
            try:
                x.close()
            except Exception:  # noqa: BLE001
                pass


@router.get("/agentes/catalogo", tags=["agentes"])
async def agentes_catalogo(user: dict = Depends(_require_tela)):
    """Agentes que ESTE usuário pode abrir: no catálogo, elegível (perfil e
    grant em `permissoes_extra` — admin sempre passa) e com os dois
    interruptores ligados. Vazio não é erro: é 'nenhum agente liberado
    ainda', o estado normal antes de o admin conceder o primeiro."""
    conn, cur = _abrir()
    try:
        cfg = svc.carregar_config(cur)
    finally:
        _fechar(conn, cur)
    # `cadastro_texto` viaja AQUI, e não no `/agentes/status`, por dois
    # motivos: o catálogo já lê a config (custo zero) e o status tem um
    # contrato que não pode mudar — `test_status_cache_hit_nao_toca_banco_nem_sonda`
    # prende que um acerto de cache não abre conexão nenhuma, e buscar o
    # texto ali obrigaria a abrir. É o mesmo dado, no lugar que já o tinha.
    #
    # Ele vem sempre, não só quando o usuário está sem cadastro: quem decide
    # MOSTRAR é a tela, e só no estado `sem_cadastro` (`AvisoSonda`, preso
    # por tests/test_agentes_f3_front.py). Não é segredo — é o aviso que o
    # admin escreveu justamente para ser lido por quem precisa se cadastrar.
    return {"agentes": svc.catalogo_do_usuario(user, cfg),
            "cadastro_texto": cfg.get("agentes_cadastro_texto") or None}


@router.get("/agentes/status", tags=["agentes"])
async def agentes_status(agente: str | None = Query(default=None),
                         user: dict = Depends(_require_tela)):
    """Estado da sonda de cadastro no gateway PARA ESTE USUÁRIO (não expõe
    config). `agente` é aceito por simetria com o catálogo mas a sonda é
    sobre o CADASTRO da matrícula — agente-agnóstica; um id desconhecido dá
    404 antes de qualquer chamada de rede."""
    if agente is not None and svc.agente(agente) is None:
        raise HTTPException(status_code=404, detail={
            "code": "agente_desconhecido", "message": f"Agente '{agente}' não existe"})
    matricula = (user.get("matricula") or "").strip()
    cacheado = svc.sonda_cacheada(matricula) if matricula else None
    if cacheado is not None:
        return {"estado": cacheado, "cache": True}
    conn, cur = _abrir()
    try:
        cadastro = None
        if matricula:
            # A coluna só existe a partir da 117 (F1). Sem ela, "sem cadastro
            # próprio" é a leitura correta (cai no padrão cvp-<matrícula>) —
            # diferente da ESCRITA (user_identidade_set, admin.py), que 503
            # nomeado: aqui não há nada de errado em degradar em silêncio,
            # porque o resultado (usar o padrão) já é o comportamento normal
            # de quem nunca configurou um cadastro.
            try:
                cur.execute("SELECT identidade_gateway FROM dbo.etl_usuario WHERE matricula = ?", [matricula])
                row = cur.fetchone()
                cadastro = row[0] if row else None
            except Exception:
                cadastro = None
        provedor_cfg = ia_provedor.load_config(cur)
        agentes_cfg = svc.carregar_config(cur)
    finally:
        _fechar(conn, cur)
    identidade = svc.identidade_gateway(matricula, cadastro)
    campo = agentes_cfg.get("agentes_gateway_campo_usuario") or None
    estado = await ia_provedor.sondar_usuario(provedor_cfg, identidade, campo)
    if matricula:
        svc.guardar_sonda(matricula, estado)
    return {"estado": estado, "cache": False}


@router.get("/agentes/conversas", tags=["agentes"])
async def agentes_conversas(q: str | None = Query(default=None, max_length=200),
                            agente: str | None = Query(default=None),
                            user: dict = Depends(_require_tela)):
    """As conversas DESTE usuário nos últimos `RETENCAO_CONVERSAS_DIAS`.

    Três coisas que este endpoint NÃO faz, de propósito:
      • não vê conversa de outro usuário — o `WHERE matricula = ?` é da
        SESSÃO, nunca de parâmetro;
      • não devolve conversa vencida, mesmo que a purga noturna não tenha
        rodado — o prazo vale na leitura (critério 2 da F4);
      • não trata `q` como padrão de LIKE: `%` e `_` digitados pelo
        usuário são escapados (`svc.escapar_like`), senão buscar "100%"
        traria tudo.
    """
    matricula = (user.get("matricula") or "").strip()
    if not matricula:
        return {"conversas": []}
    if agente is not None and svc.agente(agente) is None:
        raise HTTPException(status_code=404, detail={
            "code": "agente_desconhecido", "message": f"Agente '{agente}' não existe"})

    sql = ["SELECT conversa_id, agente, titulo, projeto, criada_em, ultima_msg_em",
           "FROM dbo.etl_agente_conversa",
           "WHERE matricula = ? AND ultima_msg_em >= DATEADD(day, -?, GETDATE())"]
    params: list = [matricula, svc.RETENCAO_CONVERSAS_DIAS]
    if agente:
        sql.append("AND agente = ?")
        params.append(agente)
    termo = (q or "").strip()
    if termo:
        # O título é a 1ª pergunta; buscar nele é o que o operador espera
        # ("aquela conversa sobre o job X").
        sql.append("AND titulo LIKE ? ESCAPE '\\'")
        params.append(f"%{svc.escapar_like(termo)}%")
    sql.append("ORDER BY ultima_msg_em DESC")
    sql.append("OFFSET 0 ROWS FETCH NEXT 100 ROWS ONLY")

    conn, cur = _abrir()
    try:
        cur.execute(" ".join(sql), params)
        linhas = cur.fetchall()
    finally:
        _fechar(conn, cur)
    return {"conversas": [
        {"conversa_id": r[0], "agente": r[1], "titulo": r[2], "projeto": r[3],
         "criada_em": _iso(r[4]), "ultima_msg_em": _iso(r[5])}
        for r in linhas]}


@router.get("/agentes/conversas/{conversa_id}", tags=["agentes"])
async def agentes_conversa(conversa_id: str, user: dict = Depends(_require_tela)):
    """As mensagens de UMA conversa, para retomar de onde parou.

    Conversa de outro usuário, inexistente ou vencida → **404 igual**, sem
    distinguir: um 403 só para a alheia diria "existe, mas não é sua", e
    isso é um oráculo de ids (critério 1 da F4). A vencida devolve um
    `code` próprio porque é informação sobre a PRÓPRIA conversa do usuário
    — a tela usa isso para dizer "expirou" em vez de "não existe".
    """
    if not _RE_CONVERSA_ID.match(conversa_id or ""):
        raise HTTPException(status_code=404, detail={
            "code": "conversa_nao_encontrada", "message": "conversa não encontrada"})
    matricula = (user.get("matricula") or "").strip()
    conn, cur = _abrir()
    try:
        cur.execute(
            "SELECT agente, titulo, projeto, criada_em, ultima_msg_em, matricula, "
            "       DATEDIFF(day, ultima_msg_em, GETDATE()) "
            "FROM dbo.etl_agente_conversa WHERE conversa_id = ?", [conversa_id])
        cab = cur.fetchone()
        if cab is None or not matricula or cab[5] != matricula:
            raise HTTPException(status_code=404, detail={
                "code": "conversa_nao_encontrada", "message": "conversa não encontrada"})
        if cab[6] is not None and int(cab[6]) > svc.RETENCAO_CONVERSAS_DIAS:
            raise HTTPException(status_code=404, detail={
                "code": "conversa_expirada",
                "message": f"conversa com mais de {svc.RETENCAO_CONVERSAS_DIAS} dias"})
        cur.execute(
            "SELECT papel, conteudo, status, artefatos_json, criada_em "
            "FROM dbo.etl_agente_mensagem WHERE conversa_id = ? ORDER BY id", [conversa_id])
        msgs = cur.fetchall()
        # Propostas com o estado ATUAL (a decisão pode ter sido tomada depois
        # da resposta). Sem a tabela/coluna, a conversa abre do mesmo jeito.
        try:
            propostas = {p["id"]: p for p in ac.propostas_da_conversa(cur, conversa_id, matricula)}
        except Exception:  # noqa: BLE001
            propostas = {}
    finally:
        _fechar(conn, cur)
    mensagens = []
    for m in msgs:
        # O artefato é gravado como JSON; a tela quer a lista, não a string.
        ferramentas, ids = _separar_artefatos(_json_lista(m[3]))
        item = {"papel": m[0], "conteudo": m[1], "status": m[2],
                "artefatos": ferramentas, "criada_em": _iso(m[4])}
        duracao = _duracao_de(_json_lista(m[3]))
        if duracao is not None:
            item["duracao_ms"] = duracao
        if ids:
            item["propostas"] = [propostas[i] for i in ids if i in propostas]
        mensagens.append(item)
    return {
        "conversa_id": conversa_id, "agente": cab[0], "titulo": cab[1], "projeto": cab[2],
        "criada_em": _iso(cab[3]), "ultima_msg_em": _iso(cab[4]),
        "mensagens": mensagens,
    }


@router.get("/agentes/admin/config", tags=["agentes-admin"])
async def agentes_admin_config_get(_admin: dict = Depends(get_admin_user)):
    conn, cur = _abrir()
    try:
        cfg = svc.carregar_config(cur)
    finally:
        _fechar(conn, cur)
    # O catálogo vai junto com `recurso`/`perfis_elegiveis` porque a aba
    # Admin › Agentes precisa saber A QUEM pode oferecer cada agente. Sem
    # isso o front teria de repetir essa regra à mão — e uma 2ª lista de
    # RBAC fora de sincronia é exatamente o defeito que `RBAC_RECURSOS` já
    # custou uma vez (tests/test_rbac_recursos_admin.py existe por isso).
    catalogo = [{"id": ag["id"], "nome": ag["nome"], "recurso": ag["recurso"],
                 "recurso_curador": ag["recurso_curador"],
                 "config_enabled": ag["config_enabled"],
                 "perfis_elegiveis": list(ag["perfis_elegiveis"])}
                for ag in svc.CATALOGO.values()]
    return {"sucesso": True, "config": cfg, "agentes": catalogo}


@router.post("/agentes/admin/config", tags=["agentes-admin"])
async def agentes_admin_config_set(body: dict = Body(default={}),
                                   admin: dict = Depends(get_admin_user)):
    valores: dict[str, str] = {}
    erros: list[str] = []

    for chave in ("agentes_enabled", "agente_datastage_enabled"):
        if chave in body:
            valores[chave] = "1" if _verdadeiro(body.get(chave)) else "0"

    if "agentes_gateway_campo_usuario" in body:
        v = str(body.get("agentes_gateway_campo_usuario") or "").strip()
        if v and not _RE_CAMPO.match(v):
            erros.append("agentes_gateway_campo_usuario deve ser 'header:NOME' ou 'body:CAMPO'")
        else:
            valores["agentes_gateway_campo_usuario"] = v

    if "agentes_cadastro_texto" in body:
        v = str(body.get("agentes_cadastro_texto") or "").strip()
        if len(v) > 500:
            erros.append("agentes_cadastro_texto excede 500 caracteres")
        else:
            valores["agentes_cadastro_texto"] = v or svc.CONFIG_DEFAULTS["agentes_cadastro_texto"]

    if "agentes_ssh_max" in body:
        try:
            n = int(body.get("agentes_ssh_max"))
            if not (1 <= n <= 50):
                raise ValueError
            valores["agentes_ssh_max"] = str(n)
        except (TypeError, ValueError):
            erros.append("agentes_ssh_max deve ser um número inteiro entre 1 e 50")

    if "agentes_fato_validade_dias" in body:
        try:
            n = int(body.get("agentes_fato_validade_dias"))
            if not (1 <= n <= 365):
                raise ValueError
            valores["agentes_fato_validade_dias"] = str(n)
        except (TypeError, ValueError):
            erros.append("agentes_fato_validade_dias deve ser um número inteiro entre 1 e 365")

    if erros:
        raise HTTPException(status_code=422, detail={"code": "agentes_config_invalida", "errors": erros})
    if not valores:
        raise HTTPException(status_code=422, detail={"code": "agentes_config_vazia",
                                                      "message": "nada para salvar"})

    conn, cur = _abrir()
    try:
        for k, v in valores.items():
            cur.execute(
                "MERGE dbo.etl_app_config AS t "
                "USING (SELECT ? AS k) AS s ON t.config_key = s.k "
                "WHEN MATCHED THEN UPDATE SET config_value=?, updated_by=?, updated_at=GETDATE() "
                "WHEN NOT MATCHED THEN INSERT (config_key, config_value, descricao, updated_by, updated_at) "
                "  VALUES (s.k, ?, 'Tela Agentes', ?, GETDATE());",
                [k, v, admin["matricula"], v, admin["matricula"]])
        _fechar(conn, cur, commit=True)
    except Exception:
        _fechar(conn, cur)
        raise
    return {"sucesso": True, "mensagem": "Configuração de Agentes salva."}


def _preparar_conversa(body: dict, user: dict) -> dict:
    """Tudo o que vem ANTES da rodada com o modelo: validação do corpo,
    interruptores, dono e validade da conversa, histórico, config e
    identidade. Levanta `HTTPException` — no endpoint de stream isso ainda
    sai como resposta HTTP normal, ANTES de o `text/event-stream` abrir (a
    tela trata 4xx/503 do mesmo jeito nos dois endpoints)."""
    t0 = time.monotonic()
    mensagem = str(body.get("mensagem") or "").strip()
    if not mensagem:
        raise HTTPException(status_code=422, detail={
            "code": "mensagem_obrigatoria", "message": "mensagem é obrigatória"})
    if len(mensagem) > _MAX_MENSAGEM:
        raise HTTPException(status_code=422, detail={
            "code": "mensagem_longa", "message": f"mensagem excede {_MAX_MENSAGEM} caracteres"})
    conversa_id = str(body.get("conversa_id") or "").strip()
    if conversa_id and not _RE_CONVERSA_ID.match(conversa_id):
        raise HTTPException(status_code=422, detail={
            "code": "conversa_id_invalido",
            "message": "conversa_id inválido (8 a 36 caracteres: letras, números, - e _)"})
    if not conversa_id:
        conversa_id = str(uuid.uuid4())
    # Redigida AQUI, antes de qualquer gravação — inclusive a do TÍTULO.
    # Achado do teste do critério 5 da F4: o título saía de `mensagem` CRUA
    # enquanto a redação só acontecia depois, então um segredo digitado na
    # primeira pergunta ia em claro para `etl_agente_conversa.titulo`. Passou
    # despercebido até a F4 porque, até então, o título não aparecia em lugar
    # nenhum — agora ele é o rótulo da conversa na LISTA do histórico e o
    # campo em que a busca procura.
    mensagem_redigida = af.redigir(mensagem)
    # A identidade é SEMPRE a da sessão — nunca um valor do corpo. Uma
    # `matricula` forjada no corpo é simplesmente ignorada (critério 6 da F2).
    matricula = user["matricula"]

    conn, cur = _abrir()
    try:
        agentes_cfg = svc.carregar_config(cur)
        if agentes_cfg.get("agentes_enabled") != "1" or agentes_cfg.get("agente_datastage_enabled") != "1":
            raise HTTPException(status_code=503, detail={
                "code": "agente_desligado", "message": "Agente DataStage desligado"})
        cur.execute(
            "SELECT projeto, matricula, DATEDIFF(day, ultima_msg_em, GETDATE()) "
            "FROM dbo.etl_agente_conversa WHERE conversa_id = ?", [conversa_id])
        row = cur.fetchone()
        if row is not None and row[1] != matricula:
            # 404, não 403: uma conversa alheia não deve nem confirmar que existe.
            raise HTTPException(status_code=404, detail={
                "code": "conversa_nao_encontrada", "message": "conversa não encontrada"})
        if row is not None and row[2] is not None and int(row[2]) > svc.RETENCAO_CONVERSAS_DIAS:
            # Vencida: não se retoma nem se escreve em cima. O mesmo prazo da
            # lista vale aqui — senão um `conversa_id` guardado no navegador
            # ressuscitaria uma conversa que a tela já não mostra (e que a
            # purga vai apagar na próxima madrugada).
            raise HTTPException(status_code=404, detail={
                "code": "conversa_expirada",
                "message": f"conversa com mais de {svc.RETENCAO_CONVERSAS_DIAS} dias — comece uma nova"})
        if row is None:
            cur.execute(
                "INSERT INTO dbo.etl_agente_conversa (conversa_id, agente, matricula, titulo) "
                "VALUES (?, ?, ?, ?)",
                # `titulo_da_conversa` corta em unidades UTF-16, a largura real
                # do NVARCHAR(200) — `mensagem[:200]` conta CARACTERES, e 200
                # caracteres com emoji passam de 200 unidades no banco.
                [conversa_id, svc.AGENTE_DATASTAGE, matricula,
                 svc.titulo_da_conversa(mensagem_redigida)])
            projeto_atual = None
            historico: list[dict] = []
            falhas_anteriores: set[str] = set()
        else:
            projeto_atual = row[0]
            cur.execute(
                "SELECT papel, conteudo FROM dbo.etl_agente_mensagem "
                "WHERE conversa_id = ? ORDER BY id", [conversa_id])
            # Histórico COMPLETO daqui — quem corta para as últimas rodadas
            # é `svc.conversar`, que é quem monta o prompt do gateway.
            # Cortar nos dois lugares foi o defeito que a revisão da F4
            # pegou: o corte de lá vencia, e este virava enfeite.
            historico = [{"role": r[0], "content": r[1]} for r in cur.fetchall()]
            falhas_anteriores = _falhas_da_conversa(cur, conversa_id)
        provedor_cfg = ia_provedor.load_config(cur)
        cadastro = None
        try:
            cur.execute("SELECT identidade_gateway FROM dbo.etl_usuario WHERE matricula = ?", [matricula])
            row_id = cur.fetchone()
            cadastro = row_id[0] if row_id else None
        except Exception:
            cadastro = None  # coluna pode não existir ainda (migration 117) — cai no padrão
        conn.commit()
    except HTTPException:
        raise
    finally:
        # finally, não só except HTTPException/else: uma exceção do DRIVER
        # (deadlock, timeout, conexão caindo — não é HTTPException) não caía
        # em nenhum dos dois ramos antes e vazava a conexão (achado real da
        # revisão adversarial da F2). Confirmado com reprodução isolada:
        # try/except/else nunca roda o `except` de um tipo que não bate nem
        # o `else` quando uma exceção se propaga.
        _fechar(conn, cur)

    identidade = svc.identidade_gateway(matricula, cadastro)
    campo = agentes_cfg.get("agentes_gateway_campo_usuario") or None
    try:
        ssh_max = int(agentes_cfg.get("agentes_ssh_max") or 10)
    except (TypeError, ValueError):
        ssh_max = 10

    # `acao_editar` é SEMPRE da sessão (F2b, isx_extrair) — nunca do corpo,
    # mesma régua da identidade (critério 6 da F2, estendido).
    acao_editar = PERM_EDITAR in user.get("permissoes", [])
    return {"t0": t0, "conversa_id": conversa_id, "matricula": matricula,
            "mensagem_redigida": mensagem_redigida,
            "kwargs": dict(
                mensagens=historico + [{"role": "user", "content": mensagem_redigida}],
                projeto_atual=projeto_atual, provedor_cfg=provedor_cfg,
                identidade=identidade, campo_identidade=campo, ssh_max=ssh_max,
                acao_editar=acao_editar, matricula=matricula,
                validade_fatos_dias=_validade_dias(agentes_cfg), falhas_anteriores=falhas_anteriores)}


async def _rodar_e_gravar(ctx: dict, emit_status=None) -> dict:
    """A rodada com o modelo e a gravação da pergunta+resposta — o mesmo
    caminho para os dois endpoints. `duracao_ms` conta do recebimento da
    pergunta até a resposta pronta, e é gravado junto (em `artefatos_json`)
    para a tela mostrar também ao retomar a conversa."""
    conversa_id, matricula = ctx["conversa_id"], ctx["matricula"]
    mensagem_redigida = ctx["mensagem_redigida"]
    kwargs = dict(ctx["kwargs"])
    if emit_status is not None:
        kwargs["emit_status"] = emit_status
    resultado = await svc.conversar(_abrir, **kwargs)
    duracao_ms = int((time.monotonic() - ctx["t0"]) * 1000)

    texto_redigido = af.redigir(resultado.get("texto") or "")
    artefatos = list(resultado.get("artefatos") or [])
    propostas: list[dict] = []
    conn, cur = _abrir()
    try:
        cur.execute(
            "INSERT INTO dbo.etl_agente_mensagem (conversa_id, papel, conteudo) VALUES (?, ?, ?)",
            [conversa_id, "user", mensagem_redigida])
        if resultado.get("propostas"):
            # Na MESMA transação das mensagens: ou a resposta e os cartões
            # dela ficam juntos, ou nenhum dos dois.
            propostas = ac.inserir_propostas(
                cur, conversa_id=conversa_id, agente=svc.AGENTE_DATASTAGE, matricula=matricula,
                propostas=resultado["propostas"])
        cur.execute(
            "INSERT INTO dbo.etl_agente_mensagem "
            "(conversa_id, papel, conteudo, status, artefatos_json) VALUES (?, ?, ?, ?, ?)",
            [conversa_id, "assistant", texto_redigido, resultado.get("status"),
             json.dumps(artefatos + [{"proposta_id": p["id"]} for p in propostas]
                        + [{"duracao_ms": duracao_ms}], ensure_ascii=False)])
        cur.execute(
            "UPDATE dbo.etl_agente_conversa SET projeto = ?, ultima_msg_em = GETDATE() "
            "WHERE conversa_id = ?", [resultado.get("projeto"), conversa_id])
        conn.commit()
    finally:
        _fechar(conn, cur)

    return {"conversa_id": conversa_id, "status": resultado.get("status"),
            "texto": texto_redigido, "projeto": resultado.get("projeto"),
            "artefatos": artefatos, "propostas": propostas,
            "propostas_recusadas": list(resultado.get("propostas_recusadas") or []),
            "aprendizados_usados": list(resultado.get("aprendizados_usados") or []),
            "aprendizados_sugeridos": list(resultado.get("aprendizados_sugeridos") or []),
            "duracao_ms": duracao_ms}


@router.post("/agentes/datastage/conversar", tags=["agentes"])
async def agentes_datastage_conversar(body: dict = Body(default={}),
                                      user: dict = Depends(_require_datastage)):
    """Uma rodada com o agente DataStage. `require_agente` já garante:
    admin passa sempre; não-admin exige perfil `desenvolvedor` e o grant em
    `permissoes_extra` (nunca o que vier só do perfil)."""
    return await _rodar_e_gravar(_preparar_conversa(body, user))


# Rodadas do stream em andamento. A rodada roda numa task PRÓPRIA, fora do
# gerador: se o usuário fechar a aba no meio, o gerador é cancelado mas a
# rodada termina e GRAVA a pergunta e a resposta (a conversa não perde a
# volta). O conjunto só segura a referência até o fim — sem ela, o coletor
# de lixo poderia descartar a task no meio.
_RODADAS_STREAM: set = set()

KEEPALIVE_S = 15  # comentário SSE periódico: o nginx corta a leitura em 300 s sem bytes


def _evento(dado: dict) -> str:
    return f"data: {json.dumps(dado, ensure_ascii=False, default=str)}\n\n"


@router.post("/agentes/datastage/conversar/stream", tags=["agentes"])
async def agentes_datastage_conversar_stream(body: dict = Body(default={}),
                                             user: dict = Depends(_require_datastage)):
    """A mesma rodada, com eventos de progresso em tempo real
    (`text/event-stream`, spec docs/spec-agentes-feedback-progresso.md):

      data: {"tipo": "status", "texto": "…"}      — a cada passo da rodada
      data: {"tipo": "resposta", …, "duracao_ms"} — a resposta final (mesmo
                                                     corpo do endpoint JSON)
      data: {"tipo": "erro", "detail": {…}}       — falha DEPOIS de o stream abrir
      : keep-alive                                — a cada 15 s sem evento

    Gate, validação e 4xx/503 acontecem ANTES do stream (resposta HTTP
    normal). `X-Accel-Buffering: no` desliga o buffer do nginx só para esta
    resposta — o `nginx.conf` de produção não precisa mudar."""
    ctx = _preparar_conversa(body, user)
    fila: asyncio.Queue = asyncio.Queue()

    async def _emitir(texto: str) -> None:
        fila.put_nowait({"tipo": "status", "texto": texto})

    rodada = asyncio.create_task(_rodar_e_gravar(ctx, _emitir))
    _RODADAS_STREAM.add(rodada)
    rodada.add_done_callback(_RODADAS_STREAM.discard)

    async def _gerar():
        yield _evento({"tipo": "status", "texto": "Pergunta recebida…"})
        proximo = None
        try:
            while True:
                if rodada.done() and fila.empty():
                    break
                proximo = asyncio.ensure_future(fila.get())
                feitos, _ = await asyncio.wait({proximo, rodada}, timeout=KEEPALIVE_S,
                                               return_when=asyncio.FIRST_COMPLETED)
                if proximo in feitos:
                    yield _evento(proximo.result())
                    continue
                proximo.cancel()
                if not feitos:
                    yield ": keep-alive\n\n"
        finally:
            # Cliente que desconecta no meio: a leitura pendente da fila é
            # cancelada aqui (senão fica órfã e o coletor loga "Task was
            # destroyed but it is pending"). A RODADA não é cancelada.
            if proximo is not None and not proximo.done():
                proximo.cancel()
        try:
            yield _evento({"tipo": "resposta", **rodada.result()})
        except HTTPException as e:
            yield _evento({"tipo": "erro", "detail": e.detail})
        except Exception:  # noqa: BLE001 — banco caiu na gravação etc.
            log.exception("agentes: falha na rodada do stream")
            yield _evento({"tipo": "erro", "detail": {
                "code": "erro_interno", "message": "Não foi possível concluir a resposta — tente de novo."}})

    return StreamingResponse(_gerar(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


_RE_DECISAO = re.compile(r"^(aprovar|recusar)$")


@router.post("/agentes/propostas/{proposta_id}/decidir", tags=["agentes"])
async def agentes_proposta_decidir(proposta_id: int, body: dict = Body(default={}),
                                   user: dict = Depends(_require_datastage)):
    """Aprovar ou recusar uma proposta do agente (F5). Só o DONO decide —
    a matrícula vem da sessão e a de outro usuário dá **404 igual** à de uma
    proposta inexistente (critério 3; sem oráculo de ids). Aprovar grava o
    fato `interpretacao_aprovada` com quem aprovou e quando; recusar não grava
    nada. Repetir a mesma decisão é inofensivo (devolve o estado atual)."""
    decisao = str(body.get("decisao") or "").strip().lower()
    if not _RE_DECISAO.match(decisao):
        raise HTTPException(status_code=422, detail={
            "code": "decisao_invalida", "message": "decisao deve ser 'aprovar' ou 'recusar'"})
    matricula = (user.get("matricula") or "").strip()
    if not matricula:
        raise HTTPException(status_code=404, detail={
            "code": "proposta_nao_encontrada", "message": "proposta não encontrada"})
    conn, cur = _abrir()
    try:
        proposta = ac.decidir_proposta(conn, cur, proposta_id=proposta_id, matricula=matricula,
                                       decisao=decisao, retencao_dias=svc.RETENCAO_CONVERSAS_DIAS)
    except ac.PropostaNaoEncontrada:
        raise HTTPException(status_code=404, detail={
            "code": "proposta_nao_encontrada", "message": "proposta não encontrada"})
    except ac.PropostaExpirada:
        raise HTTPException(status_code=409, detail={
            "code": "proposta_expirada",
            "message": f"proposta com mais de {svc.RETENCAO_CONVERSAS_DIAS} dias — não pode mais ser decidida"})
    except ac.PropostaJaDecidida as e:
        raise HTTPException(status_code=409, detail={
            "code": "proposta_ja_decidida",
            "message": f"essa proposta já foi {e.proposta['estado']}", "proposta": e.proposta})
    finally:
        _fechar(conn, cur)
    return {"proposta": proposta}


# ══════════════════════════════════════════════════════════════════════════
# Curadoria dos aprendizados (F6) — só quem tem `agente_curador` (admin passa)
# ══════════════════════════════════════════════════════════════════════════

def _checar_curadoria(user: dict, cfg: dict) -> None:
    """A curadoria segue as mesmas portas da tela (achado da auditoria de
    segurança da F6): agente DESLIGADO → 503, como o chat; e o curador
    também precisa do acesso de USO — sem ele o agente nem aparece no
    seletor, e a API não pode ser um atalho para a fila e as evidências.
    `require_agente(curador=True)` já garantiu perfil elegível + recurso de
    curador (admin passa sempre)."""
    if cfg.get("agentes_enabled") != "1" or cfg.get("agente_datastage_enabled") != "1":
        raise HTTPException(status_code=503, detail={
            "code": "agente_desligado", "message": "Agente DataStage desligado"})
    ag = svc.agente(svc.AGENTE_DATASTAGE)
    if PERM_ADMIN not in user.get("permissoes", []) and ag["recurso"] not in user.get("permissoes_extra", []):
        raise HTTPException(status_code=403, detail={
            "code": "agente_nao_liberado",
            "message": "O curador também precisa ter o agente liberado para uso — peça ao administrador"})


@router.get("/agentes/aprendizados", tags=["agentes"])
async def agentes_aprendizados(estado: str = Query(default="rascunho"),
                               user: dict = Depends(_require_curador)):
    """A fila do curador: rascunhos (sugestões do agente e a semente) para
    validar ou rejeitar, e os validados para marcar como obsoletos. A
    evidência vem junto — é o que o curador lê para decidir; o modelo nunca
    a recebe."""
    if estado not in ap.ESTADOS:
        raise HTTPException(status_code=422, detail={
            "code": "estado_invalido", "message": f"estado deve ser um de: {', '.join(ap.ESTADOS)}"})
    conn, cur = _abrir()
    try:
        _checar_curadoria(user, svc.carregar_config(cur))
        itens = ap.listar(cur, agente=svc.AGENTE_DATASTAGE, estado=estado)
    finally:
        _fechar(conn, cur)
    return {"aprendizados": itens}


@router.post("/agentes/aprendizados/{aprendizado_id}/decidir", tags=["agentes"])
async def agentes_aprendizado_decidir(aprendizado_id: int, body: dict = Body(default={}),
                                      user: dict = Depends(_require_curador)):
    acao = str(body.get("acao") or "").strip().lower()
    if acao not in ap.TRANSICOES:
        raise HTTPException(status_code=422, detail={
            "code": "acao_invalida", "message": "acao deve ser 'validar', 'rejeitar' ou 'obsoletar'"})
    conn, cur = _abrir()
    try:
        _checar_curadoria(user, svc.carregar_config(cur))
        item = ap.decidir(conn, cur, aprendizado_id=aprendizado_id, agente=svc.AGENTE_DATASTAGE,
                          acao=acao, matricula=user["matricula"])
    except ap.AprendizadoNaoEncontrado:
        raise HTTPException(status_code=404, detail={
            "code": "aprendizado_nao_encontrado", "message": "aprendizado não encontrado"})
    except ap.TransicaoInvalida as e:
        raise HTTPException(status_code=409, detail={
            "code": "transicao_invalida",
            "message": f"não dá para {acao} um aprendizado {e.atual['estado']}", "aprendizado": e.atual})
    finally:
        _fechar(conn, cur)
    return {"aprendizado": item}
