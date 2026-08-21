"""dags/utils/triagem_ia.py — o chamado tem informação suficiente para começar?

Porta a triagem do painel `ritm_geresd_ed.html` para dentro do produto. Roda em
LOTE, no ciclo do sync — nunca no request da tela: uma chamada de IA por
chamado dentro do request tornaria a tela refém do gateway.

Três decisões que moldam este módulo:

1. **O veredito é binário.** `PODE INICIAR` ou `RETORNAR AO SOLICITANTE`.
   "Mais ou menos suficiente" não ajuda ninguém a decidir o que fazer com o
   chamado agora, que é a única razão de a triagem existir.

2. **Nunca fica sem veredito.** Gateway fora do ar, resposta em formato
   inesperado, JSON truncado — tudo cai na heurística de recorte, que é a
   mesma do painel. A fila continua triada; o que muda é a ORIGEM.

3. **A origem é sempre gravada.** Heurística apresentada como análise de IA é
   engano do operador, que passa a confiar num julgamento que ninguém fez.

⚠️ Este módulo vive na árvore `dags/` e NÃO importa de `api/`: o worker não
tem aquela árvore no path. Ele fala com o gateway por conta própria, lendo a
MESMA config (`caixa_ia_*` em `dbo.etl_app_config`) que o Admin grava — e por
isso os literais das chaves estão duplicados aqui, como já acontece em
`servicenow_sync.py`.
"""
from __future__ import annotations

import hashlib
import json
import re

from utils.frescor_modulo import carimbar

carimbar(__file__)

# ── Config (espelha api/services/caixa_ia.py — mesma tabela, outra árvore) ──
K_PROVIDER = "caixa_ia_provider"
K_MODEL = "caixa_ia_model"
K_BASE_URL = "caixa_ia_base_url"
K_API_KEY = "caixa_ia_api_key_enc"
K_USA_PROXY = "caixa_ia_usa_proxy"
# Interruptor PRÓPRIO: `caixa_ia_enabled` governa os assistentes do Caixa
# Seguro, e amarrar os dois faria desligar o Diego desligar a triagem.
K_HABILITADA = "chamados_triagem_habilitada"
K_LOTE = "chamados_triagem_lote"

LOTE_PADRAO = 20
TIMEOUT_S = 45
MAX_TOKENS = 800

VEREDITO_OK = "PODE INICIAR"
VEREDITO_RETORNAR = "RETORNAR AO SOLICITANTE"
VEREDITOS = (VEREDITO_OK, VEREDITO_RETORNAR)

ORIGEM_IA = "ia"
ORIGEM_HEURISTICA = "heuristica"

# Limites das colunas (migration 093).
RESUMO_MAX = 400
ENTENDIMENTO_MAX = 1000
LACUNAS_MAX = 2000
PERGUNTAS_MAX = 2000
ERRO_MAX = 400

# Quanto do texto vai para o prompt. Os mesmos cortes do painel: além disso o
# ganho de contexto não paga o custo de token.
DESCRICAO_NO_PROMPT = 1500
WORKNOTES_NO_PROMPT = 2000


def texto_para_hash(descricao: str, work_notes: str, titulo: str) -> str:
    """A marca do que foi analisado.

    Existe para dois defeitos opostos: sem ela, o lote re-tria a fila inteira
    a cada 15 min (custo), e um chamado cuja descrição MUDOU fica com o
    veredito antigo (silencioso, e pior).
    """
    base = f"{titulo or ''}\x1f{descricao or ''}\x1f{work_notes or ''}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════════════
# Heurística — o fallback que garante veredito para todo mundo
# ══════════════════════════════════════════════════════════════════════════

_TEM_QUERY = re.compile(r"\b(SELECT|FROM|WHERE|JOIN|EXEC|USE)\b", re.IGNORECASE)

# Sinais de que o pedido tem alvo técnico definido.
_CONCRETOS = (
    r"\bDMDB\d+\b", r"\bDM_\d+", r"\bTB_", r"\bVW_", r"\bPRC_",
    r"\bcertificado\b", r"\bcoluna", r"\bcampo", r"\btabela", r"\bservidor",
    r"\bschedule", r"\bprocedure", r"\bview\b",
)
# Sinais de que o pedido delega o conteúdo para fora do texto.
_VAGOS = (
    r"\banexo\b", r"\bconforme falamos\b", r"\bimagem\b", r"\bprint\b",
    r"\bfigma\b", r"\bapresentado abaixo\b", r"\bconforme combinado\b",
)

TEXTO_CURTO = 80


def suficiencia_heuristica(descricao: str) -> tuple[str, str]:
    """(nível, motivo) por recorte de texto — sem IA nenhuma.

    Deliberadamente conservadora: na dúvida devolve 'parcial', que leva a
    RETORNAR. Um falso "pode iniciar" faz alguém começar um trabalho que vai
    travar na metade; um falso "retornar" custa uma leitura humana.
    """
    desc = (descricao or "").strip()
    if len(desc) < 10:
        return "insuficiente", "Descrição ausente ou muito curta."
    concretos = sum(1 for p in _CONCRETOS if re.search(p, desc, re.IGNORECASE))
    vagos = sum(1 for p in _VAGOS if re.search(p, desc, re.IGNORECASE))
    if _TEM_QUERY.search(desc):
        return "suficiente", "Contém query SQL — contexto técnico explícito."
    if concretos >= 3 and vagos == 0:
        return "suficiente", "Descreve objetos e campos específicos."
    if vagos >= 2:
        return "insuficiente", ("Descrição delega o conteúdo a anexo ou imagem "
                                "sem detalhar o objeto técnico.")
    if len(desc) < TEXTO_CURTO:
        return "insuficiente", "Descrição curta demais para execução."
    if concretos >= 1 and vagos <= 1:
        return "parcial", "Há contexto técnico, mas pode faltar detalhe."
    return "parcial", "Contexto de negócio presente, sem detalhe técnico explícito."


def triagem_heuristica(titulo: str, descricao: str, motivo_erro: str = "") -> dict:
    """Laudo completo sem IA. É o piso: todo chamado tem veredito."""
    nivel, obs = suficiencia_heuristica(descricao)
    return {
        "veredito": VEREDITO_OK if nivel == "suficiente" else VEREDITO_RETORNAR,
        "suficiencia": nivel,
        "resumo": (titulo or "")[:RESUMO_MAX],
        "entendimento": obs[:ENTENDIMENTO_MAX],
        "lacunas": "" if nivel == "suficiente" else obs[:LACUNAS_MAX],
        # A heurística NÃO inventa perguntas: ela não leu o pedido, apenas
        # mediu sinais do texto. Pergunta genérica gera ruído no chamado.
        "perguntas": "",
        "origem": ORIGEM_HEURISTICA,
        "modelo": "",
        "erro": (motivo_erro or "")[:ERRO_MAX],
    }


# ══════════════════════════════════════════════════════════════════════════
# IA — o prompt do painel, disparado contra o gateway configurado
# ══════════════════════════════════════════════════════════════════════════

PROMPT = """Você é um analista sênior de dados em uma seguradora. Analise o chamado abaixo e produza um relatório de triagem técnica em português.

Chamado: {numero}
Catálogo: {catalogo}
Título: {titulo}

--- DESCRIÇÃO ORIGINAL ---
{descricao}

--- COMENTÁRIOS / WORK NOTES ---
{work_notes}

Produza um JSON com exatamente esta estrutura (sem markdown, sem texto fora do JSON):
{{
  "resumo": "resumo em 1 linha, máx 180 chars, formato: Tipo: X | Objeto: Y | Pedido: Z",
  "entendimento": "2-3 frases técnicas objetivas sobre o que foi solicitado",
  "lacunas": ["lacuna curta 1", "lacuna curta 2"],
  "veredito": "PODE INICIAR",
  "justificativa": "uma frase",
  "perguntas": "até 5 perguntas numeradas, cada uma em 1 linha (máx 400 chars total)"
}}

Regras:
- "lacunas": strings curtas (máx 12 palavras cada); lista vazia se não houver lacunas críticas
- "veredito": exatamente "PODE INICIAR" ou "RETORNAR AO SOLICITANTE"
- "perguntas": só preencher se veredito for RETORNAR AO SOLICITANTE; caso contrário ""

Critérios de lacuna:
- Campos/colunas do resultado não descritos textualmente (anexo sem descrição não basta)
- Tabelas/fontes de dados de origem não identificadas
- Critério de aceite / definição de pronto ausente
- Frequência/periodicidade de atualização não definida
- Regras de negócio, filtros ou segmentações ausentes

Veredito PODE INICIAR: fonte de dado + critério de aceite claramente definidos.
Veredito RETORNAR AO SOLICITANTE: qualquer lacuna crítica presente.

Responda SOMENTE com o JSON."""


def montar_prompt(chamado: dict) -> str:
    return PROMPT.format(
        numero=chamado.get("numero") or "",
        catalogo=chamado.get("catalogo") or "(sem catálogo)",
        titulo=chamado.get("titulo") or "",
        descricao=(chamado.get("descricao") or "")[:DESCRICAO_NO_PROMPT],
        work_notes=(chamado.get("work_notes") or "")[:WORKNOTES_NO_PROMPT]
        or "(sem comentários)",
    )


def extrair_json(resposta: str) -> dict | None:
    """O JSON de dentro da resposta, tolerando cerca de markdown.

    Modelo instruído a responder "somente JSON" às vezes responde com ```json
    em volta — e um parse rígido transformaria isso em falha de IA, mandando
    para a heurística um laudo que estava lá, correto, dentro da cerca.
    """
    if not resposta:
        return None
    limpa = re.sub(r"^```(?:json)?\s*", "", resposta.strip(), flags=re.MULTILINE)
    limpa = re.sub(r"```\s*$", "", limpa.strip(), flags=re.MULTILINE)
    achado = re.search(r"\{.*\}", limpa, re.DOTALL)
    if not achado:
        return None
    try:
        obj = json.loads(achado.group())
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def _linhas(valor) -> str:
    """Lista da IA → uma por linha. Aceita string também: o modelo às vezes
    devolve texto no lugar da lista, e recusar isso jogaria fora um laudo
    perfeitamente utilizável."""
    if isinstance(valor, list):
        itens = [str(x).strip() for x in valor if str(x).strip()]
        return "\n".join(itens)
    return str(valor or "").strip()


def laudo_da_ia(obj: dict, modelo: str) -> dict | None:
    """Normaliza o JSON do modelo. `None` = resposta inaproveitável.

    O veredito é validado contra a lista fechada: um modelo que responda
    "TALVEZ" não pode virar coluna — a tela pinta o card pelo veredito, e um
    valor inesperado apareceria como categoria nova, sem cor nem significado.
    """
    veredito = str(obj.get("veredito") or "").strip().upper()
    if veredito not in VEREDITOS:
        return None
    lacunas = _linhas(obj.get("lacunas"))
    if veredito == VEREDITO_OK:
        suficiencia = "suficiente"
    else:
        suficiencia = "parcial" if lacunas else "insuficiente"
    return {
        "veredito": veredito,
        "suficiencia": suficiencia,
        "resumo": str(obj.get("resumo") or "").strip()[:RESUMO_MAX],
        "entendimento": str(obj.get("entendimento") or "").strip()[:ENTENDIMENTO_MAX],
        "lacunas": lacunas[:LACUNAS_MAX],
        # Pergunta só faz sentido quando o veredito manda devolver: numa
        # aprovação, ela vira ruído colado num chamado que já pode andar.
        "perguntas": ("" if veredito == VEREDITO_OK
                      else _linhas(obj.get("perguntas"))[:PERGUNTAS_MAX]),
        "origem": ORIGEM_IA,
        "modelo": (modelo or "")[:60],
        "erro": "",
    }


def config_da_triagem(cfg: dict) -> dict:
    """Config lida de etl_app_config, já normalizada."""
    try:
        lote = int((cfg.get(K_LOTE) or "").strip() or LOTE_PADRAO)
    except ValueError:
        lote = LOTE_PADRAO
    return {
        "habilitada": (cfg.get(K_HABILITADA) or "").strip() == "1",
        "provider": (cfg.get(K_PROVIDER) or "").strip(),
        "modelo": (cfg.get(K_MODEL) or "").strip(),
        "base_url": (cfg.get(K_BASE_URL) or "").strip().rstrip("/"),
        "api_key_enc": (cfg.get(K_API_KEY) or "").strip(),
        "usa_proxy": (cfg.get(K_USA_PROXY) or "").strip() == "1",
        "lote": max(1, min(lote, 200)),
    }


def chamar_gateway(conf: dict, api_key: str, prompt: str) -> tuple[str, str]:
    """(texto, erro). Nunca levanta: falha aqui vira heurística, não parada.

    Fala o dialeto do gateway interno — `x-api-key` e resposta em
    `content[0].text` — com `choices[0].message.content` como segunda
    tentativa, porque a rota se chama /chat/completions e nada garante que o
    formato continue o mesmo depois de uma atualização do gateway.
    """
    import httpx

    if not conf["base_url"]:
        return "", "gateway sem base_url configurada"
    try:
        # trust_env só quando pedido: o gateway é intranet, e o proxy
        # corporativo do worker derrubaria a chamada.
        with httpx.Client(timeout=TIMEOUT_S, trust_env=conf["usa_proxy"]) as cli:
            r = cli.post(
                f"{conf['base_url']}/chat/completions",
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json={"model": conf["modelo"],
                      "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": MAX_TOKENS},
            )
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"
    if r.status_code >= 400:
        return "", f"HTTP {r.status_code}"
    try:
        payload = r.json()
    except ValueError:
        return "", "resposta não é JSON (portal de proxy?)"
    try:
        blocos = payload.get("content")
        if isinstance(blocos, list) and blocos:
            texto = "".join(b.get("text", "") for b in blocos
                            if isinstance(b, dict))
            if texto.strip():
                return texto.strip(), ""
        texto = (payload["choices"][0]["message"]["content"] or "").strip()
        if texto:
            return texto, ""
    except (KeyError, IndexError, TypeError, AttributeError):
        pass
    return "", "resposta sem texto reconhecível"


def triar(chamado: dict, conf: dict, api_key: str) -> dict:
    """O laudo de um chamado. SEMPRE devolve laudo — a origem é que varia."""
    titulo = chamado.get("titulo") or ""
    descricao = chamado.get("descricao") or ""

    if not conf["habilitada"] or not api_key:
        return triagem_heuristica(titulo, descricao,
                                  "triagem por IA desligada" if not conf["habilitada"]
                                  else "sem chave de API configurada")
    resposta, erro = chamar_gateway(conf, api_key, montar_prompt(chamado))
    if erro:
        return triagem_heuristica(titulo, descricao, erro)
    obj = extrair_json(resposta)
    if obj is None:
        return triagem_heuristica(titulo, descricao,
                                  "resposta da IA não continha JSON válido")
    laudo = laudo_da_ia(obj, conf["modelo"])
    if laudo is None:
        return triagem_heuristica(
            titulo, descricao,
            f"veredito inesperado da IA: {str(obj.get('veredito'))[:60]!r}")
    return laudo


# ── SQL do lote (placeholder %s — árvore dags/, pymssql) ──────────────────

def sql_candidatos() -> str:
    """A fila viva com o hash da última triagem.

    O filtro do que mudou NÃO cabe no SQL: o hash é do texto normalizado em
    Python, e reproduzir essa normalização em T-SQL criaria duas verdades que
    divergem no dia em que uma delas mudar. A fila é de dezenas — trazer todos
    e decidir em Python é barato e tem uma regra só.

    Só o que está ATIVO: gastar IA com chamado encerrado é pagar por análise
    que ninguém vai ler. `triagem_hash IS NULL` primeiro para que os nunca
    triados não fiquem atrás dos que só mudaram de texto.
    """
    return """
        SELECT sys_id, numero, titulo, descricao, work_notes, catalogo,
               triagem_hash
        FROM dbo.etl_chamado
        WHERE ativo = 1
        ORDER BY CASE WHEN triagem_hash IS NULL THEN 0 ELSE 1 END,
                 aberto_em DESC
    """


def pendentes(linhas, limite: int) -> list[dict]:
    """Dos candidatos, quem precisa de triagem — até o teto do lote.

    Cada item já sai com o `hash` do texto ATUAL: é ele que será gravado,
    porque gravar o hash de um texto diferente do analisado faria a próxima
    execução pular um chamado que mudou.
    """
    fila = []
    for r in linhas:
        chamado = {
            "sys_id": r[0], "numero": r[1], "titulo": r[2],
            "descricao": r[3], "work_notes": r[4], "catalogo": r[5],
        }
        atual = texto_para_hash(chamado["descricao"], chamado["work_notes"],
                                chamado["titulo"])
        if (r[6] or "") == atual:
            continue          # já triado com este mesmo texto
        chamado["hash"] = atual
        fila.append(chamado)
        if len(fila) >= limite:
            break
    return fila


def sql_gravar() -> str:
    return """
        UPDATE dbo.etl_chamado
        SET veredito=%s, suficiencia=%s, resumo=%s, entendimento=%s,
            lacunas=%s, perguntas=%s, triagem_origem=%s, triagem_modelo=%s,
            triagem_erro=%s, triagem_hash=%s, triagem_em=GETDATE()
        WHERE sys_id=%s
    """


def params_gravar(laudo: dict, hash_texto: str, sys_id: str) -> tuple:
    """Os parâmetros do UPDATE, na ordem do SQL acima."""
    return (laudo["veredito"], laudo["suficiencia"], laudo["resumo"],
            laudo["entendimento"], laudo["lacunas"], laudo["perguntas"],
            laudo["origem"], laudo["modelo"], laudo["erro"],
            hash_texto, sys_id)
