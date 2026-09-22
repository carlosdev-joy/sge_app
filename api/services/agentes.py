"""api/services/agentes.py — catálogo e RBAC da tela Agentes (F1 da spec
docs/spec-agentes-datastage.md).

O que mora aqui:

  • **o catálogo**, em código, não em tabela (decisão da spec — sem CRUD nem
    valor hoje): cada agente declara `perfis_elegiveis` e `concessao`. O
    agente `datastage` é `concessao='manual_por_usuario'`: nunca concedido
    por perfil, sempre usuário a usuário, pelo admin — reforçado por
    `require_agente()`, que ignora o recurso se ele vier de
    `etl_perfil_permissao` (só conta em `permissoes_extra`, a fatia que
    `carregar_usuario` já separa como overrides por usuário).
  • **`require_agente()`**: a dependency FastAPI que guarda cada endpoint de
    agente. Admin passa sempre (`acao_admin`) — é o mesmo "sempre tem todos
    os menus e acessos" que `require_ds_console` já aplica a outra tela.
  • **`identidade_gateway()`**: função pura — cadastro do usuário
    (`etl_usuario.identidade_gateway`) se preenchido, senão o padrão
    `cvp-<matrícula em minúsculas>`. Nunca decide sozinha se manda ou não
    chamar o gateway (quem decide é o chamador, ao ver `None`).

`tela_agentes` (a tela em si) NÃO tem tratamento especial aqui: é checada
direto por `require_perm('tela_agentes')` nos routers, como qualquer outra
tela — só os AGENTES (`agente_*`) precisam desta política extra.

F2 (a mesma spec) acrescenta a ORQUESTRAÇÃO da rodada — `conversar()`: pede
ferramenta ao modelo (bloco ```json, mesma régua do Maestro —
`extrair_pedido_ferramenta`), executa pela allowlist de
`agentes_ferramentas`, nunca deixa `base`/`dsjob` rodar sem o PROJETO
DataStage resolvido na conversa, e nunca estoura o orçamento de tempo da
rodada (`ORCAMENTO_AGENTE_S`, abaixo do `proxy_read_timeout` do nginx).
"""
from __future__ import annotations

import asyncio
import json
import re
import time

from fastapi import Depends, HTTPException

from deps import PERM_ADMIN, get_current_user
from services import agentes_ferramentas as af
from services import ia_provedor
from services.ssh_datastage import DsConsoleError

# ── Catálogo (código, não tabela) ───────────────────────────────────────────

AGENTE_DATASTAGE = "datastage"

CATALOGO: dict[str, dict] = {
    AGENTE_DATASTAGE: {
        "id": AGENTE_DATASTAGE,
        "nome": "Mapeamento DataStage",
        "descricao": (
            "Explica fluxos DataStage existentes: jobs, tabelas, campos, "
            "parâmetros e lineage. Leitura ao vivo sem alterar o DataStage; "
            "pode extrair ISX (com acao_editar do usuário) e consultar DSX."
        ),
        # Recurso concedido usuário a usuário (nunca por perfil — ver
        # require_agente). Config liga/desliga em `agente_datastage_enabled`.
        "recurso": "agente_datastage",
        "recurso_curador": "agente_curador",
        "config_enabled": "agente_datastage_enabled",
        "perfis_elegiveis": ("desenvolvedor",),
        "concessao": "manual_por_usuario",
    },
}


def agente(agente_id: str) -> dict | None:
    return CATALOGO.get(agente_id)


# ── RBAC por agente ──────────────────────────────────────────────────────────

def require_agente(agente_id: str, curador: bool = False):
    """Dependency FastAPI que guarda os endpoints de um agente.

    Admin passa sempre (`acao_admin`), sem grant — é a mesma regra de
    `deps.require_ds_console`. Não-admin precisa das DUAS coisas: perfil
    elegível E o recurso em `permissoes_extra` (não em `permissoes`, que
    inclui o que vem do PERFIL — um `agente_datastage` marcado num perfil
    pela tela genérica de Admin › Perfis não deve dar acesso a ninguém além
    do admin; é a defesa em profundidade da spec, risco 26)."""
    ag = CATALOGO.get(agente_id)
    if ag is None:
        raise ValueError(f"agente desconhecido no catálogo: {agente_id!r}")
    recurso = ag["recurso_curador"] if curador else ag["recurso"]

    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if PERM_ADMIN in user.get("permissoes", []):
            return user
        if user.get("perfil") not in ag["perfis_elegiveis"]:
            raise HTTPException(status_code=403, detail={
                "code": "agente_nao_elegivel",
                "message": f"Perfil '{user.get('perfil')}' não pode usar este agente"})
        if recurso not in user.get("permissoes_extra", []):
            raise HTTPException(status_code=403, detail={
                "code": "agente_nao_liberado",
                "message": "Agente não liberado para este usuário — peça ao administrador"})
        return user

    return _dep


def elegivel_por_perfil(agente_id: str, perfil: str) -> bool:
    """Só a elegibilidade de PERFIL — sem olhar grant nenhum. Usada pelo
    Admin (`user_perm_set`) para recusar (422) conceder `agente_*` a um
    perfil que nunca poderia usá-lo — a mesma régua de `require_agente`, do
    lado de quem concede. `perfil == 'admin'` é sempre elegível (ele já usa
    o agente por `acao_admin`; recusar o grant explícito seria só atrito)."""
    ag = CATALOGO.get(agente_id)
    if ag is None:
        return False
    return perfil == "admin" or perfil in ag["perfis_elegiveis"]


def agente_do_recurso(recurso: str) -> dict | None:
    """`agente_datastage`/`agente_curador` → o agente dono do recurso, ou
    None se `recurso` não é um recurso de agente (ex.: `tela_jobs`)."""
    for ag in CATALOGO.values():
        if recurso in (ag["recurso"], ag["recurso_curador"]):
            return ag
    return None


def catalogo_do_usuario(user: dict, config: dict[str, str]) -> list[dict]:
    """Agentes que `user` pode abrir: no catálogo, elegível (perfil+grant,
    admin sempre), e com os DOIS interruptores ligados (`agentes_enabled`
    geral e o do próprio agente). `config` é `{config_key: config_value}` já
    lido de etl_app_config (mesmas chaves que `_carregar_config` devolve)."""
    if (config.get("agentes_enabled") or "0") != "1":
        return []  # geral desligado: ninguém vê nada, nem o admin (padrão maestro_enabled)
    saida = []
    is_admin = PERM_ADMIN in user.get("permissoes", [])
    extras = set(user.get("permissoes_extra", []))
    for ag in CATALOGO.values():
        if (config.get(ag["config_enabled"]) or "0") != "1":
            continue
        liberado = is_admin or (
            user.get("perfil") in ag["perfis_elegiveis"] and ag["recurso"] in extras)
        if not liberado:
            continue
        saida.append({"id": ag["id"], "nome": ag["nome"], "descricao": ag["descricao"],
                      "curador": is_admin or ag["recurso_curador"] in extras})
    return saida


# ── Identidade no gateway (D-16) ────────────────────────────────────────────

# Vai em header (a maioria dos gateways não aceita espaço/quebra de linha em
# valor de header): letras, números e um punhado de separadores comuns em
# identificador corporativo (login, e-mail, matrícula com prefixo).
RE_IDENTIDADE_GATEWAY = re.compile(r"^[A-Za-z0-9._@-]{1,100}$")


CONFIG_DEFAULTS: dict[str, str] = {
    "agentes_enabled": "0",
    "agente_datastage_enabled": "0",
    # 'header:NOME' | 'body:CAMPO' — vazio = D-01 ainda não fechada, e a
    # sonda devolve sem_contrato sem chamar o gateway (ver ia_provedor).
    "agentes_gateway_campo_usuario": "",
    "agentes_cadastro_texto": "Solicite o cadastro no gateway de IA ao administrador.",
    "agentes_ssh_max": "10",
    "agentes_fato_validade_dias": "7",
}


def carregar_config(cur) -> dict[str, str]:
    """Lê as chaves `agentes_*`/`agente_*_enabled` de etl_app_config, com os
    padrões de `CONFIG_DEFAULTS` quando ausentes. Degrada graciosamente
    (tudo desligado) se a tabela ou a migration 117 ainda não existirem —
    mesmo espírito de `ia_provedor.load_config`."""
    valores = dict(CONFIG_DEFAULTS)
    try:
        chaves = list(CONFIG_DEFAULTS)
        marcadores = ",".join("?" * len(chaves))
        cur.execute(
            f"SELECT config_key, config_value FROM dbo.etl_app_config WHERE config_key IN ({marcadores})",
            chaves)
        for k, v in cur.fetchall():
            if v is not None and str(v).strip():
                valores[k] = str(v).strip()
    except Exception:
        pass
    return valores


def identidade_gateway(matricula: str, cadastro: str | None) -> str | None:
    """O identificador a enviar ao gateway: o CADASTRO do usuário
    (`etl_usuario.identidade_gateway`) se preenchido; senão o padrão
    `cvp-<matrícula em minúsculas>` (o banco grava a matrícula em MAIÚSCULAS
    — `auth.py:38` — por isso o `.lower()` aqui é obrigatório). Sem
    matrícula, devolve None: quem chama NUNCA cai para `cvp-orquestra` (isso
    faria o usuário agir como o app e anularia a autorização por usuário)."""
    if cadastro and cadastro.strip():
        return cadastro.strip()
    mat = (matricula or "").strip()
    if not mat:
        return None
    return f"cvp-{mat.lower()}"


# ── Cache da sonda (D-03: TTL por estado) ───────────────────────────────────
#
# Em memória do processo, por matrícula (a sonda é sobre o CADASTRO do
# usuário no gateway — não muda por agente). `ok` guarda por mais tempo
# porque cadastro não vai e volta; `sem_cadastro` guarda pouco para o botão
# "verificar de novo" fazer sentido logo depois que a pessoa se cadastra;
# `gateway_indisponivel` (e qualquer estado fora do mapa) NUNCA é cacheado —
# uma queda momentânea do gateway não pode virar "sem cadastro" por 10 min.
_TTL_POR_ESTADO_S = {"ok": 600, "sem_cadastro": 60}

_sonda_cache: dict[str, tuple[str, float]] = {}


def sonda_cacheada(matricula: str) -> str | None:
    item = _sonda_cache.get(matricula)
    if item is None:
        return None
    estado, expira_em = item
    if time.monotonic() >= expira_em:
        _sonda_cache.pop(matricula, None)
        return None
    return estado


def guardar_sonda(matricula: str, estado: str) -> None:
    ttl = _TTL_POR_ESTADO_S.get(estado)
    if not ttl:
        _sonda_cache.pop(matricula, None)
        return
    _sonda_cache[matricula] = (estado, time.monotonic() + ttl)


def invalidar_sonda(matricula: str) -> None:
    """Chamado quando o admin muda `identidade_gateway` de alguém (ação
    `user_identidade_set`, admin.py): o estado cacheado descrevia o
    identificador ANTIGO."""
    _sonda_cache.pop(matricula, None)


# ══════════════════════════════════════════════════════════════════════════
# Orquestração da rodada (F2) — o agente pede ferramenta, o backend decide
# ══════════════════════════════════════════════════════════════════════════

_RE_BLOCO_JSON = re.compile(r"```[ \t]*(?:json)?[ \t]*\n?(\{(?:(?!```).)*\})\s*```", re.S | re.I)

# Abaixo do proxy_read_timeout (300 s na rota /orquestra/, D-14 ✅) — margem
# para a resposta HTTP em si voltar antes do nginx desistir.
ORCAMENTO_AGENTE_S = 240
MAX_RODADAS_FERRAMENTA = 3
MAX_HISTORICO = 12  # mesmo teto do Maestro (MAX_HISTORICO em maestro.py)


def extrair_pedido_ferramenta(texto: str) -> tuple[str, dict | None]:
    """(texto sem o bloco, pedido) — o ÚLTIMO bloco ```json que tem a chave
    `ferramenta`. Mesmo padrão de `maestro.extrair_proposta`: sem bloco
    válido, o modelo só respondeu (`pedido` None)."""
    texto = texto or ""
    achado = None
    for m in _RE_BLOCO_JSON.finditer(texto):
        try:
            obj = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(obj, dict) and "ferramenta" in obj:
            achado = (m, obj)
    if not achado:
        return texto.strip(), None
    m, obj = achado
    limpo = (texto[:m.start()] + texto[m.end():]).strip()
    return limpo, obj


def _prompt_sistema(projeto: str | None) -> str:
    """Gerado do VOCABULÁRIO das ferramentas (allowlist de
    `agentes_ferramentas`), não digitado à mão duas vezes — o mesmo
    anti-drift do Maestro: se a allowlist de `dsjob` mudar, o prompt muda
    sozinho."""
    comandos = ", ".join(af.ALLOWLIST_DSJOB)
    if projeto:
        projeto_txt = f"O projeto DataStage desta conversa já está resolvido: {projeto}."
    else:
        projeto_txt = (
            "Esta conversa AINDA NÃO tem um projeto DataStage resolvido. Antes de usar "
            "'base' ou 'dsjob', pergunte ao usuário qual é o projeto (ou o nome de um "
            "pipeline/job do Orquestra) e peça a ferramenta 'resolver_projeto' assim que "
            "tiver um nome candidato — nunca tente 'base'/'dsjob' sem isso, o backend recusa.")
    return f"""Você é o agente de mapeamento de processos DataStage do Orquestra.

Sua única função: explicar fluxos DataStage existentes — jobs, tabelas, campos,
parâmetros e lineage. Você NUNCA altera o DataStage: não importa, não compila,
não executa, não para nem apaga job nenhum, e não roda comando fora das
ferramentas abaixo — só lê.

{projeto_txt}

Para usar uma ferramenta, termine sua resposta com UM bloco, e nada depois dele:
```json
{{"ferramenta": "NOME", "args": {{...}}}}
```

Ferramentas disponíveis:
- resolver_projeto {{"projeto": "NOME"}} OU {{"pipeline_name": "...", "job_name": "..."}} —
  valida contra o que o Orquestra já conhece (nunca toca o servidor). Se o usuário citou um
  pipeline/job do PRÓPRIO Orquestra, use pipeline_name+job_name — resolve sem perguntar mais
  nada. Se a resposta vier com estado "quase" (nome parecido, mas com caixa diferente —
  DataStage é sensível a maiúsculas/minúsculas), CONFIRME com o usuário antes de continuar;
  só chame de novo com o nome exato sugerido depois que o usuário confirmar.
- base {{"job_name": "NOME"}} — o que o Orquestra JÁ SABE sobre o job (mais rápido; tente
  sempre primeiro, antes de dsjob). A resposta traz "idade_dias" do dado — se vier None ou
  grande (dado antigo), considere usar dsjob para conferir ao vivo antes de responder algo
  que pode ter mudado.
- dsjob {{"comando": "{comandos}", "job_name": "NOME"}} — lê o job AO VIVO no servidor
  DataStage (job_name pode ser omitido só em ljobs). Só use se 'base' não bastar ou o dado
  estiver velho.

Se não precisar de nenhuma ferramenta, responda normalmente, sem bloco nenhum.
"""


def _com_cursor(abrir_conn, fn):
    """Abre uma conexão CURTA só para `fn(cur)`, fecha antes de devolver —
    mesmo espírito do Maestro ("tudo que é banco ANTES do provedor, numa
    conexão só e fechada antes de esperar a rede"), aqui repetido por
    RODADA em vez de uma vez só: a orquestração pode levar até
    `ORCAMENTO_AGENTE_S` com várias idas ao gateway, e segurar uma conexão
    de banco aberta esse tempo todo esgotaria o pool sob concorrência (a
    mesma classe de problema do risco 9 da spec, só que no SQL Server em
    vez do servidor DataStage)."""
    conn, cur = abrir_conn()
    try:
        return fn(cur)
    finally:
        try:
            conn.commit()
        except Exception:
            pass
        for x in (cur, conn):
            try:
                x.close()
            except Exception:
                pass


async def _executar_ferramenta(abrir_conn, nome: str, args: dict, *, projeto: str | None,
                               ssh_max: int, espera_max_s: float) -> tuple[dict, str | None]:
    """Executa UMA ferramenta pedida pelo modelo, sempre pela allowlist —
    NUNCA deixa `base`/`dsjob` rodar sem `projeto` resolvido (a guarda do
    risco 28). `abrir_conn` é uma fábrica `() -> (conn, cur)`: cada consulta
    de banco usa sua PRÓPRIA conexão curta (ver `_com_cursor`), nunca uma
    guardada pela rodada inteira. Nunca levanta de verdade: TODO o corpo (não
    só o ramo `dsjob`) está sob um try/except amplo — uma falha de banco
    (deadlock, timeout, conexão caindo) dentro de `resolver_projeto`/`base`
    virava exceção não tratada antes (achado real da revisão adversarial da
    F2: propagava como 500 cru e perdia a mensagem do usuário, que nunca
    chegava a ser persistida). Erro vira dado nomeado que volta ao modelo
    como conversa. Devolve (dado-para-o-modelo, projeto novo-ou-None)."""
    try:
        return await _executar_ferramenta_interna(
            abrir_conn, nome, args, projeto=projeto, ssh_max=ssh_max, espera_max_s=espera_max_s)
    except (af.ServidorOcupado, DsConsoleError) as e:
        return {"texto": str(e)}, None
    except Exception as e:  # banco/SSH/rede: nunca derruba a rodada
        return {"texto": f"Falha ao executar a ferramenta '{nome}' ({type(e).__name__}) — tente de novo."}, None


async def _executar_ferramenta_interna(abrir_conn, nome: str, args: dict, *, projeto: str | None,
                                       ssh_max: int, espera_max_s: float) -> tuple[dict, str | None]:
    """O corpo de fato de `_executar_ferramenta` — pode levantar; quem chama
    (`_executar_ferramenta`) é quem garante que nunca escapa."""
    if nome == "resolver_projeto":
        candidato = str(args.get("projeto") or "").strip() or None
        pipeline_name = str(args.get("pipeline_name") or "").strip() or None
        job_name_pipeline = str(args.get("job_name") or "").strip() or None
        r = _com_cursor(abrir_conn, lambda cur: af.resolver_projeto(
            cur, candidato, pipeline_name=pipeline_name, job_name=job_name_pipeline))
        if r["estado"] == "resolvido":
            extra = " (tem arquivo .dsx disponível)" if r["tem_dsx"] else ""
            return {"texto": f"Projeto resolvido: {r['projeto']}{extra}."}, r["projeto"]
        if r["estado"] == "quase":
            # SÓ sugestão — nunca resolve sozinho aqui (critério 11 da F2).
            # O modelo confirma com o usuário e chama de novo com a grafia exata.
            return ({"texto": f"'{candidato}' é parecido com '{r['sugerido']}' (o DataStage é "
                              f"sensível a maiúsculas/minúsculas). Confirme com o usuário e, se for "
                              f"esse mesmo, peça resolver_projeto de novo com \"{r['sugerido']}\" "
                              f"exatamente assim."}, None)
        sugestoes = ", ".join(r["sugestoes"]) or "nenhuma sugestão disponível"
        alvo = candidato or f"{pipeline_name}/{job_name_pipeline}" if pipeline_name else "(nenhum)"
        return ({"texto": f"Não reconheço o projeto '{alvo}'. "
                          f"Projetos conhecidos: {sugestoes}."}, None)

    if nome not in ("base", "dsjob"):
        return {"texto": f"Ferramenta '{nome}' não existe — use resolver_projeto, base ou dsjob."}, None

    if not projeto:
        return ({"texto": "Ainda não sei o projeto DataStage desta conversa — "
                          "peça a ferramenta 'resolver_projeto' primeiro."}, None)

    job_name = str(args.get("job_name") or "").strip() or None

    if nome == "base":
        if not job_name:
            return {"texto": "A ferramenta 'base' exige job_name."}, None
        r = _com_cursor(abrir_conn, lambda cur: af.ferramenta_base(cur, projeto, job_name))
        if not r.get("encontrado"):
            return {"texto": f"Nada na base sobre o job '{job_name}' do projeto '{projeto}'."}, None
        # redigir() SEMPRE — job_description/erro são texto livre e não passam
        # por nenhuma sanitização na extração ISX (achado real da revisão
        # adversarial da F2: um segredo colado numa descrição de job ia cru
        # para o modelo, violando o critério 4 — "segredo nunca chega ao modelo").
        texto = af.redigir(json.dumps(r, ensure_ascii=False, default=str))
        return {"texto": texto}, None

    # dsjob — não toca banco nenhum (só o servidor DataStage, via SSH).
    comando = str(args.get("comando") or "").strip()
    r = await af.ferramenta_dsjob(comando, projeto, job_name,
                                  teto_sessoes=ssh_max, espera_max_s=espera_max_s)
    if r["exit_code"] != 0:
        erro_redigido = af.redigir((r.get("stderr") or "")[:1000])
        return {"texto": f"dsjob {comando} falhou (código {r['exit_code']}): {erro_redigido}"}, None
    return {"texto": r["saida_redigida"]}, None


# A proteção contra cancelar a sessão SSH real no meio (achado da revisão
# adversarial da F2) mora DENTRO de `agentes_ferramentas.ferramenta_dsjob`
# (via `asyncio.shield`, só na fase "vaga obtida → trabalho → libera") —
# não aqui. Uma versão anterior tentava resolver isso por FORA, com um
# `_esperar_sem_cancelar` que nunca cancelava a Task inteira de
# `_executar_ferramenta` — só que isso também parava de cancelar a ESPERA
# NA FILA do semáforo (ainda sem vaga), deixando tentativas "fantasmas"
# na fila por até `espera_max_s` depois da pergunta já ter sido respondida
# como "tempo esgotado" (achado moderado da 3ª rodada). Resolvido na
# origem: aqui, `wait_for` cancelando de verdade é seguro de novo — a fila
# cancela na hora, e a fase protegida cancela sozinha por dentro.


async def conversar(abrir_conn, *, mensagens: list[dict], projeto_atual: str | None,
                    provedor_cfg: dict, identidade: str | None, campo_identidade: str | None,
                    ssh_max: int) -> dict:
    """Uma rodada completa do agente DataStage: pede ferramenta ao modelo
    (no máximo `MAX_RODADAS_FERRAMENTA` vezes), executa cada uma pela
    allowlist, e devolve a resposta final. Controla o orçamento de tempo
    por RELÓGIO, não por contagem — um gateway lento consome o mesmo
    orçamento que uma ferramenta lenta (critério 8 da F2).

    Nunca levanta por conta do provedor/ferramenta: erro vira `status`
    nomeado com uma mensagem para o usuário, sempre 200 para quem chamou."""
    t0 = time.monotonic()

    def _resta() -> float:
        return ORCAMENTO_AGENTE_S - (time.monotonic() - t0)

    historico = list(mensagens[-MAX_HISTORICO:])
    projeto = projeto_atual
    artefatos: list[dict] = []

    texto_esgotado = {"status": "tempo_esgotado", "projeto": None, "artefatos": None,
                      "texto": "O tempo desta pergunta esgotou — tente de novo, ou peça algo mais direto."}

    for rodada in range(MAX_RODADAS_FERRAMENTA + 1):
        resta = _resta()
        if resta <= 5:
            return {**texto_esgotado, "projeto": projeto, "artefatos": artefatos}
        sistema = _prompt_sistema(projeto)
        # O orçamento também vale por OPERAÇÃO, não só entre rodadas — sem
        # isto, uma única chamada ao gateway podia levar até TIMEOUT_S (60s)
        # mesmo com o orçamento quase esgotado, e a soma gateway+ferramenta de
        # várias rodadas podia estourar os 240s sem nenhuma checagem no meio
        # (achado real da revisão adversarial da F2, risco de 504 do nginx —
        # critério 8 da F2). `wait_for` usa o relógio real do loop, não afeta
        # os testes que mockam `time.monotonic` (a checagem "entre rodadas"
        # acima continua sendo quem decide nesses testes).
        try:
            resposta, modelo = await asyncio.wait_for(
                ia_provedor.chat_conversa(provedor_cfg, sistema, historico,
                                          identidade=identidade, campo_identidade=campo_identidade),
                timeout=max(1.0, resta - 2))
        except (asyncio.TimeoutError, TimeoutError):
            return {**texto_esgotado, "projeto": projeto, "artefatos": artefatos}
        except ia_provedor.GatewayRecusou:
            return {"status": "gateway_recusou", "projeto": projeto, "artefatos": artefatos,
                    "texto": "O gateway de IA recusou esta conversa — confira seu cadastro em Agentes."}
        except HTTPException as e:
            return {"status": "erro_provedor", "projeto": projeto, "artefatos": artefatos,
                    "texto": f"O provedor de IA não respondeu ({e.detail})."}

        texto, pedido = extrair_pedido_ferramenta(resposta)
        if pedido is None:
            historico.append({"role": "assistant", "content": resposta})
            return {"status": "ok", "projeto": projeto, "artefatos": artefatos,
                    "texto": texto or resposta, "modelo": modelo, "historico": historico}

        if rodada == MAX_RODADAS_FERRAMENTA:
            return {"status": "limite_rodadas", "projeto": projeto, "artefatos": artefatos,
                    "texto": ("Preciso de mais passos do que o permitido para responder — "
                             "pode refazer a pergunta de um jeito mais direto?")}

        nome_ferramenta = str(pedido.get("ferramenta") or "").strip()
        args = pedido.get("args") if isinstance(pedido.get("args"), dict) else {}
        historico.append({"role": "assistant", "content": resposta})

        resta = _resta()
        if resta <= 5:
            return {**texto_esgotado, "projeto": projeto, "artefatos": artefatos}
        espera = max(0.5, min(resta - 5, 30))
        try:
            dado, projeto_novo = await asyncio.wait_for(
                _executar_ferramenta(abrir_conn, nome_ferramenta, args, projeto=projeto,
                                     ssh_max=ssh_max, espera_max_s=espera),
                timeout=max(1.0, resta - 2))
        except (asyncio.TimeoutError, TimeoutError):
            return {**texto_esgotado, "projeto": projeto, "artefatos": artefatos}
        if projeto_novo:
            projeto = projeto_novo
        artefatos.append({"ferramenta": nome_ferramenta, "args": args})
        # Dado DELIMITADO — nunca instrução: uma ferramenta que devolvesse
        # "ignore as instruções anteriores" entra aqui como TEXTO dentro da
        # tag, e a próxima rodada continua obedecendo só ao prompt de sistema.
        historico.append({"role": "user",
                          "content": f'<ferramenta nome="{nome_ferramenta}">\n{dado["texto"]}\n</ferramenta>'})

    return {"status": "limite_rodadas", "projeto": projeto, "artefatos": artefatos,
            "texto": "Não consegui concluir dentro do limite de passos desta pergunta."}
