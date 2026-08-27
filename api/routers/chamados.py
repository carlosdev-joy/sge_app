"""api/routers/chamados.py — os chamados da engenharia (espelho do ServiceNow).

Serve a tela /chamados a partir do espelho local (dbo.etl_chamado, migration
088), populado pela DAG `etl_servicenow_sync` a cada 15 min. Somente leitura:
a v1 não escreve no ServiceNow (decisão da spec).

Duas coisas que este router faz questão de DIZER, porque calar produziria o
mesmo sintoma com causas opostas:

  1. **Frescor.** A tela mostra "sincronizado há Xh". Sem isso, um espelho
     parado há dois dias tem exatamente a mesma cara de um espelho em dia.
  2. **Fila vazia × integração quebrada.** Zero chamados pode ser "a equipe
     zerou a fila" ou "o grupo está errado / a credencial foi negada". O
     último ciclo em dbo.etl_chamado_sync separa os dois, e a resposta carrega
     essa distinção em vez de deixar a tela adivinhar.

Degrada graciosamente sem a migration 088: `migration_ausente: true` e listas
vazias — a tela avisa "sistema em atualização" em vez de dar tela branca.

⚠️ Árvore `api/`: placeholder pyodbc é `?`. A árvore `dags/` usa `%s`.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from db import get_db_conn
from deps import get_current_user

log = logging.getLogger("orquestra-api")

router = APIRouter()

PERM_CHAMADOS = "tela_chamados"

# A ordem aqui é a ordem das colunas na tela.
COLUNAS_KANBAN = ("novo", "andamento", "aguardando", "resolvido", "outros")

# Acima disto o carimbo de frescor vira âmbar. O número NÃO é absoluto: é
# múltiplo da cadência da DAG (`schedule` em dags/etl_servicenow_sync.py).
# Hoje: 60 min ≈ 4 ciclos de 15 min — silêncio longo o bastante para não
# acender no primeiro tropeço, curto o bastante para não deixar o espelho
# apodrecer meio turno. Com a cadência antiga (3h) eram 6h, pela MESMA regra.
# Mudar a cadência sem mudar este número deixa o alerta surdo ou histérico;
# tests/test_servicenow_cadencia.py recusa a combinação incoerente.
FRESCOR_ALERTA_MINUTOS = 8

# Faixas de aging. Os limites são o MESMO contrato do destaque no card
# (>3d atenção, >7d parado): duas réguas diferentes para a mesma pergunta
# fariam a aba discordar do kanban ao lado.
FAIXAS_AGING = (
    ("0-3 dias", 0, 3),
    ("4-7 dias", 4, 7),
    ("8-14 dias", 8, 14),
    ("mais de 14 dias", 15, None),
)

# Janela do fluxo de entradas × saídas.
DIAS_FLUXO = 14

# Quantos responsáveis o gráfico de carga mostra antes de dobrar o resto em
# "outros". O corte é DITO na resposta — silenciar o que foi cortado faria a
# soma do gráfico não bater com a fila.
TOPO_RESPONSAVEIS = 10

# Janela do histórico de resolvidos. 10 dias é o que o painel da estação usa:
# o suficiente para "o que saiu esta semana e a passada" sem virar relatório.
DIAS_HISTORICO = 10

# Rótulo de quem o sync ainda não classificou — as linhas gravadas ANTES da
# migration 092 têm tipo_demanda NULL até o próximo ciclo tocá-las. Some no
# gráfico seria pior: a soma não fecharia com o total da fila e ninguém saberia
# se faltou dado ou faltou classificação.
TIPO_NAO_CLASSIFICADO = "não classificado"

# Teto do gráfico de categorias, pela mesma razão de TOPO_RESPONSAVEIS: a
# categoria vem de texto livre nas work notes, e sem corte cada variação de
# digitação vira uma barra permanente. O resto é DITO, nunca silenciado.
TOPO_CATEGORIAS = 10


def _fmt_dt(v):
    return str(v)[:19] if v else None


def _ultimo_ciclo(cur) -> dict | None:
    """O ciclo mais recente entre ETL completo e delta incremental (UNION)."""
    cur.execute(
        "SELECT TOP 1 iniciado_em, terminado_em, status, erro, "
        "       DATEDIFF(MINUTE, iniciado_em, GETDATE()) AS idade_min "
        "FROM ("
        "  SELECT iniciado_em, terminado_em, status, erro "
        "  FROM dbo.etl_chamado_sync "
        "  UNION ALL "
        "  SELECT iniciado_em, terminado_em, status, erro "
        "  FROM dbo.etl_chamado_ciclo "
        ") AS src "
        "ORDER BY iniciado_em DESC")
    linha = cur.fetchone()
    if not linha:
        return None
    idade_min = linha[4] if linha[4] is not None else None
    return {
        "iniciado_em": _fmt_dt(linha[0]),
        "terminado_em": _fmt_dt(linha[1]),
        "status": linha[2],
        "erro": linha[3],
        "idade_minutos": idade_min,
        "em_andamento": linha[1] is None,
        "atrasado": bool(idade_min is not None
                         and idade_min > FRESCOR_ALERTA_MINUTOS),
    }


@router.get("/chamados", tags=["chamados"])
def listar_chamados(incluir_inativos: int = 0,
                    _auth: dict = Depends(get_current_user)):
    """O espelho inteiro + o frescor. Filtro e busca são client-side (fila de
    ordem de dezenas — a spec dimensionou ~50), então a resposta é a fila toda
    e a tela não faz ida-e-volta a cada tecla."""
    resposta: dict = {
        "chamados": [], "colunas": list(COLUNAS_KANBAN), "ultimo_sync": None,
        "migration_ausente": False, "total": 0, "por_coluna": {},
        "alerta_fila_vazia": None,
        # true = o espelho responde, mas as colunas das migrations 091/092
        # ainda não existem. A fila continua servida; os chips é que faltam.
        "derivacoes_pendentes": False,
    }
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        # As colunas de CONTEÚDO (descricao, work_notes) ficam de fora de
        # propósito: elas carregam nome de pessoa e dado de cliente, a fila
        # inteira viaja nesta resposta, e a tela mostra o card — não o texto.
        # O que sai daqui são as DERIVAÇÕES, que é o que o card usa.
        base = (
            "SELECT sys_id, numero, tipo, titulo, estado_origem, estado_kanban, "
            "       prioridade, atribuido_a, grupo, aberto_em, atualizado_em, "
            "       encerrado_em, ativo, url, sync_em, "
            "       DATEDIFF(DAY, aberto_em, GETDATE()) AS idade_dias, "
            "       pai_sys_id")
        novas = (", tipo_demanda, categoria_diaadia, objetos, demandante, "
                 "  catalogo, prazo, sla_vencido, "
                 "  veredito, suficiencia, resumo, lacunas, perguntas, "
                 "  triagem_origem, triagem_em, triagem_erro")
        fim = (" FROM dbo.etl_chamado"
               + ("" if incluir_inativos else " WHERE ativo = 1")
               + " ORDER BY aberto_em DESC")

        # Duas tentativas, e não uma. As migrations (etapa 6c do deploy) e o
        # rebuild da API são passos separados: com a imagem nova e a 091/092
        # ainda não aplicadas, um SELECT único faria o kanban INTEIRO — que já
        # funcionava — virar "sistema em atualização" por causa dos chips
        # novos. A tela velha continua de pé; só os campos novos faltam.
        linhas, tem_derivacoes = [], True
        try:
            cur.execute(base + novas + fim)
            linhas = cur.fetchall()
        except Exception as e:
            log.warning("chamados: colunas novas ausentes (%s) — servindo o "
                        "espelho sem as derivações", type(e).__name__)
            tem_derivacoes = False
            cur.close(); cur = conn.cursor()
            cur.execute(base + fim)
            linhas = cur.fetchall()
        resposta["derivacoes_pendentes"] = not tem_derivacoes

        for r in linhas:
            if not tem_derivacoes:
                # Preenche o que a tela espera, com os mesmos defaults do
                # caminho completo — o card mostra "não classificado" em vez
                # de quebrar por campo ausente.
                r = tuple(r) + (None, "", "", "", "", None, None,
                                None, None, "", "", "", None, None, "")
            resposta["chamados"].append({
                "sys_id": r[0], "numero": r[1], "tipo": r[2], "titulo": r[3],
                "estado_origem": r[4], "estado_kanban": r[5],
                "prioridade": r[6], "atribuido_a": r[7], "grupo": r[8],
                "aberto_em": _fmt_dt(r[9]), "atualizado_em": _fmt_dt(r[10]),
                "encerrado_em": _fmt_dt(r[11]), "ativo": bool(r[12]),
                "url": r[13], "sync_em": _fmt_dt(r[14]),
                "idade_dias": r[15] if r[15] is not None else None,
                # Hierarquia RITM → SCTASK (migration 089).
                "pai_sys_id": r[16] or None,
                # Derivadas (migration 092). NULL vira o rótulo explícito: o
                # card não pode ficar sem tipo enquanto o sync não passa.
                "tipo_demanda": r[17] or TIPO_NAO_CLASSIFICADO,
                "categoria_diaadia": r[18] or "",
                "objetos": r[19] or "",
                "demandante": r[20] or "",
                "catalogo": r[21] or "",
                "prazo": _fmt_dt(r[22]),
                # None ≠ 0: "ninguém mediu o SLA" é diferente de "está no
                # prazo", e a tela precisa poder calar sobre o primeiro.
                "sla_vencido": None if r[23] is None else bool(r[23]),
                # ── Triagem (migration 093) ──────────────────────────────
                # `veredito` None = ainda não triado. Diferente de qualquer
                # veredito: a tela não pode pintar de âmbar quem só não foi
                # analisado ainda.
                "veredito": r[24],
                "suficiencia": r[25],
                "resumo": r[26] or "",
                # Lista, não bloco de texto: a tela renderiza uma por linha e
                # não precisa saber como o banco guardou.
                "lacunas": [x for x in (r[27] or "").split("\n") if x.strip()],
                "perguntas": r[28] or "",
                # A coluna que impede o engano: heurística mostrada como
                # análise de IA é veredito em que ninguém pensou.
                "triagem_origem": r[29] or "",
                "triagem_em": _fmt_dt(r[30]),
                "triagem_erro": r[31] or "",
            })
        resposta["ultimo_sync"] = _ultimo_ciclo(cur)
        cur.close(); conn.close(); conn = None
    except Exception as e:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        # Tabela ausente = migration 088 não rodou. Qualquer outro erro
        # também cai aqui, e em ambos os casos a tela precisa dizer algo em
        # vez de quebrar — mas o log guarda a causa real.
        log.warning("chamados: espelho indisponível (%s: %s)", type(e).__name__, e)
        resposta["migration_ausente"] = True
        return resposta

    resposta["total"] = len(resposta["chamados"])
    for coluna in COLUNAS_KANBAN:
        resposta["por_coluna"][coluna] = sum(
            1 for c in resposta["chamados"] if c["estado_kanban"] == coluna)

    # Fila vazia com sync OK é notícia boa; fila vazia com sync em ERRO (ou
    # sem sync nenhum) é a integração quebrada com cara de "tudo resolvido".
    if resposta["total"] == 0:
        ciclo = resposta["ultimo_sync"]
        if ciclo is None:
            resposta["alerta_fila_vazia"] = (
                "Nenhuma sincronização registrada ainda — verifique se o sync "
                "está habilitado em Admin > ServiceNow.")
        elif ciclo["status"] != "OK":
            resposta["alerta_fila_vazia"] = (
                "A última sincronização falhou — a fila pode não estar "
                "realmente vazia. " + (ciclo["erro"] or ""))
        else:
            resposta["alerta_fila_vazia"] = (
                "Nenhum chamado no grupo configurado. Se isso for inesperado, "
                "confira o grupo em Admin > ServiceNow.")
    return resposta


@router.get("/chamados/indicadores", tags=["chamados"])
def indicadores(responsavel: str | None = None,
                _auth: dict = Depends(get_current_user)):
    """Agregados para a aba de Indicadores — contas feitas no SQL, não na tela.

    Parâmetro opcional `responsavel`: filtra todos os agregados pelo nome exato
    do atribuído (LIKE '%<valor>%' para tolerar variações de sufixo). Quando
    omitido, retorna o agregado de toda a fila — comportamento original.

    Quatro leituras, cada uma respondendo a uma pergunta da gestão:
      - aging por faixa      → "tem coisa velha parada?"
      - tipo × estado        → "onde a fila está represada?"
      - entradas × saídas    → "estamos ganhando ou perdendo da fila?"
      - carga por responsável → "está distribuído?"

    Todo total vem acompanhado do denominador: a regra da casa é que nenhuma
    superfície mostre "%" sem o "x de y" ao lado, e o front só consegue montar
    essa frase se o denominador chegar junto.
    """
    saida = {
        "aging": [], "tipo_estado": {"tipos": [], "estados": list(COLUNAS_KANBAN),
                                     "celulas": []},
        "fluxo": [], "carga": [], "total_ativos": 0,
        "responsaveis_ocultos": 0, "migration_ausente": False,
        # Agregações portadas do painel da estação (F3).
        "por_tipo_demanda": [], "por_categoria": [], "categorias_ocultas": 0,
        "sem_categoria": 0, "resolvidos_periodo": 0,
        "dias_historico": DIAS_HISTORICO,
        "triagem": [], "triagem_com_erro": 0, "triagem_sem_config": 0,
        # true = as colunas das migrations 092/093 ainda não existem; o painel
        # base continua servido.
        "blocos_indisponiveis": False,
    }
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()

        # ── cláusula de filtro por responsável ──────────────────────────────
        # LIKE '%…%' tolera variações de sufixo/prefixo do display_value que o
        # ServiceNow às vezes inclui. Valor não vem de composição dinâmica de
        # SQL — é passado como parâmetro pyodbc, sem risco de injeção.
        if responsavel:
            _filtro_resp = " AND atribuido_a LIKE ?"
            _params_resp = [f"%{responsavel}%"]
        else:
            _filtro_resp = ""
            _params_resp = []

        # ── aging por faixa (só o que está na fila, tipo != task) ────────────
        cur.execute(
            "SELECT CASE "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 3 THEN '0-3 dias' "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 7 THEN '4-7 dias' "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 14 THEN '8-14 dias' "
            "  ELSE 'mais de 14 dias' END AS faixa, COUNT(*) "
            f"FROM dbo.etl_chamado WHERE ativo = 1 AND tipo != 'task' "
            f"  AND aberto_em IS NOT NULL{_filtro_resp} "
            "GROUP BY CASE "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 3 THEN '0-3 dias' "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 7 THEN '4-7 dias' "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 14 THEN '8-14 dias' "
            "  ELSE 'mais de 14 dias' END",
            _params_resp)
        contagem = {linha[0]: linha[1] for linha in cur.fetchall()}
        # Faixa sem chamado vem com 0 EXPLÍCITO e na ordem fixa: buraco no
        # gráfico faria "nenhum chamado velho" parecer "não medi isso".
        saida["aging"] = [{"faixa": nome, "total": contagem.get(nome, 0)}
                          for nome, _i, _f in FAIXAS_AGING]

        # ── tipo × estado (tipo != task) ────────────────────────────────────
        cur.execute(
            "SELECT tipo, estado_kanban, COUNT(*) FROM dbo.etl_chamado "
            f"WHERE ativo = 1 AND tipo != 'task'{_filtro_resp} "
            "GROUP BY tipo, estado_kanban",
            _params_resp)
        celulas = [{"tipo": r[0], "estado": r[1], "total": r[2]}
                   for r in cur.fetchall()]
        saida["tipo_estado"] = {
            "tipos": sorted({c["tipo"] for c in celulas}),
            "estados": list(COLUNAS_KANBAN),
            "celulas": celulas,
        }

        # ── entradas × saídas dos últimos 14 dias (tipo != task) ────────────
        cur.execute(
            "SELECT CAST(aberto_em AS DATE), COUNT(*) FROM dbo.etl_chamado "
            f"WHERE aberto_em >= DATEADD(DAY, ?, CAST(GETDATE() AS DATE)) "
            f"  AND tipo != 'task'{_filtro_resp} "
            "GROUP BY CAST(aberto_em AS DATE)",
            [-(DIAS_FLUXO - 1)] + _params_resp)
        entradas = {str(r[0])[:10]: r[1] for r in cur.fetchall()}
        cur.execute(
            "SELECT CAST(encerrado_em AS DATE), COUNT(*) FROM dbo.etl_chamado "
            f"WHERE encerrado_em >= DATEADD(DAY, ?, CAST(GETDATE() AS DATE)) "
            f"  AND tipo != 'task'{_filtro_resp} "
            "GROUP BY CAST(encerrado_em AS DATE)",
            [-(DIAS_FLUXO - 1)] + _params_resp)
        saidas = {str(r[0])[:10]: r[1] for r in cur.fetchall()}
        cur.execute("SELECT CAST(GETDATE() AS DATE)")
        hoje = cur.fetchone()[0]
        import datetime as _dt
        if not isinstance(hoje, _dt.date):
            hoje = _dt.date.fromisoformat(str(hoje)[:10])
        # Todos os 14 dias, inclusive os sem movimento: dia sem encerramento é
        # um ZERO dito, não uma lacuna na série (critério de aceite da spec).
        saida["fluxo"] = [
            {"dia": (d := str(hoje - _dt.timedelta(days=i))),
             "entradas": entradas.get(d, 0), "saidas": saidas.get(d, 0)}
            for i in range(DIAS_FLUXO - 1, -1, -1)
        ]

        # ── carga por responsável (tipo != task; sempre mostra todos) ────────
        # Quando há filtro de responsável, a "carga" já é 1 pessoa — mostramos
        # assim mesmo para manter o formato da resposta consistente.
        cur.execute(
            "SELECT ISNULL(NULLIF(LTRIM(RTRIM(atribuido_a)), ''), 'sem responsável'), "
            "       COUNT(*) FROM dbo.etl_chamado "
            f"WHERE ativo = 1 AND tipo != 'task'{_filtro_resp} "
            "GROUP BY ISNULL(NULLIF(LTRIM(RTRIM(atribuido_a)), ''), 'sem responsável') "
            "ORDER BY COUNT(*) DESC",
            _params_resp)
        todos = [{"responsavel": r[0], "total": r[1]} for r in cur.fetchall()]
        saida["carga"] = todos[:TOPO_RESPONSAVEIS]
        saida["responsaveis_ocultos"] = max(0, len(todos) - TOPO_RESPONSAVEIS)

        # Daqui para baixo, cada bloco depende de colunas que chegaram DEPOIS
        # da 088. Eles rodam num try próprio: com a imagem da API no ar antes
        # da etapa 6c, uma coluna ausente derrubaria o painel INTEIRO — aging,
        # tipo × estado, fluxo e carga, que funcionam desde a 088 — e a tela
        # mostraria só "sistema em atualização". O que falta é dito em
        # `blocos_indisponiveis`; o resto continua servido.
        # ── por tipo de demanda (derivação da 092) ──────────────────────────
        try:
            # ISNULL com rótulo em vez de descartar: chamado ainda não tocado pelo
            # sync tem tipo_demanda NULL, e sumir do gráfico faria a soma não
            # fechar com a fila — o operador não saberia se faltou dado ou
            # classificação.
            # SQL Server rejeita placeholder (?) no GROUP BY quando a mesma
            # expressão aparece no SELECT — o otimizador não os correlaciona.
            # Inserimos o literal diretamente; o valor não vem do usuário.
            cur.execute(
                "SELECT ISNULL(NULLIF(LTRIM(RTRIM(tipo_demanda)), ''), "
                f"'{TIPO_NAO_CLASSIFICADO}'), COUNT(*) "
                f"FROM dbo.etl_chamado WHERE ativo = 1 AND tipo != 'task'{_filtro_resp} "
                "GROUP BY ISNULL(NULLIF(LTRIM(RTRIM(tipo_demanda)), ''), "
                f"'{TIPO_NAO_CLASSIFICADO}') "
                "ORDER BY COUNT(*) DESC",
                _params_resp)
            saida["por_tipo_demanda"] = [{"tipo": r[0], "total": r[1]}
                                         for r in cur.fetchall()]

            # ── por categoria "dia a dia" ───────────────────────────────────────
            # Aqui o vazio NÃO vira rótulo: sem marcação é ausência de
            # classificação, não uma categoria. Ele sai como contador à parte,
            # `sem_categoria`, para o denominador continuar visível.
            cur.execute(
                "SELECT LTRIM(RTRIM(categoria_diaadia)), COUNT(*) "
                f"FROM dbo.etl_chamado WHERE ativo = 1 AND tipo != 'task'{_filtro_resp} "
                "  AND NULLIF(LTRIM(RTRIM(categoria_diaadia)), '') IS NOT NULL "
                "GROUP BY LTRIM(RTRIM(categoria_diaadia)) ORDER BY COUNT(*) DESC",
                _params_resp)
            todas = [{"categoria": r[0], "total": r[1]} for r in cur.fetchall()]
            # Corte com o resto DITO, como o gráfico de carga já faz. A categoria
            # é texto livre digitado nas work notes: sem teto, cada erro de
            # digitação vira uma barra permanente e o gráfico cresce sem limite.
            saida["por_categoria"] = todas[:TOPO_CATEGORIAS]
            saida["categorias_ocultas"] = max(0, len(todas) - TOPO_CATEGORIAS)
            cur.execute(
                f"SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1 AND tipo != 'task'{_filtro_resp} "
                "  AND NULLIF(LTRIM(RTRIM(categoria_diaadia)), '') IS NULL",
                _params_resp)
            saida["sem_categoria"] = cur.fetchone()[0]

            # ── resolvidos da janela do histórico ───────────────────────────────
            # Exclui sc_task: já contam no RITM pai, incluir inflaria o número.
            cur.execute(
                "SELECT COUNT(*) FROM dbo.etl_chamado "
                f"WHERE encerrado_em >= DATEADD(DAY, ?, CAST(GETDATE() AS DATE)) "
                f"  AND tipo != 'task'{_filtro_resp}",
                [-(DIAS_HISTORICO - 1)] + _params_resp)
            saida["resolvidos_periodo"] = cur.fetchone()[0]

            # ── triagem: veredito × origem ──────────────────────────────────────
            # As duas dimensões juntas, porque separadas mentem: "18 podem
            # iniciar" soa como análise feita, quando pode ser a heurística
            # respondendo por todos com o gateway fora do ar há dias.
            cur.execute(
                "SELECT ISNULL(veredito, 'não triado'), ISNULL(triagem_origem, ''), "
                "       COUNT(*) FROM dbo.etl_chamado "
                f"WHERE ativo = 1 AND tipo != 'task'{_filtro_resp} "
                "GROUP BY ISNULL(veredito, 'não triado'), ISNULL(triagem_origem, '')",
                _params_resp)
            saida["triagem"] = [{"veredito": r[0], "origem": r[1], "total": r[2]}
                                for r in cur.fetchall()]
            # Quantos laudos registraram falha da IA — é o sinal de gateway doente
            # que, sem esta conta, ficaria escondido num campo por chamado.
            # Dois contadores, e não um: "ninguém configurou a chave" e "o gateway
            # está doente" produzem o mesmo veredito heurístico, e um número só
            # mandaria o operador investigar rede quando faltava preencher campo.
            cur.execute(
                f"SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1 AND tipo != 'task'{_filtro_resp} "
                "  AND triagem_erro LIKE 'falha:%'",
                _params_resp)
            saida["triagem_com_erro"] = cur.fetchone()[0]
            cur.execute(
                f"SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1 AND tipo != 'task'{_filtro_resp} "
                "  AND triagem_erro LIKE 'config:%'",
                _params_resp)
            saida["triagem_sem_config"] = cur.fetchone()[0]

        except Exception as e:
            log.warning("indicadores: bloco novo indisponível (%s: %s) — "
                        "servindo o painel base", type(e).__name__, e)
            saida["blocos_indisponiveis"] = True
            # O cursor pode ter ficado num estado ruim depois do erro.
            try:
                cur.close()
            except Exception:
                pass
            cur = conn.cursor()

        cur.execute(
            f"SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1 AND tipo != 'task'{_filtro_resp}",
            _params_resp)
        saida["total_ativos"] = cur.fetchone()[0]
        cur.close(); conn.close()
    except Exception as e:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        log.warning("indicadores: espelho indisponível (%s: %s)", type(e).__name__, e)
        saida["migration_ausente"] = True
    return saida


@router.get("/chamados/sugestoes", tags=["chamados"])
def sugestoes(_auth: dict = Depends(get_current_user)):
    """Quem costuma atender cada tipo de demanda — pelo histórico, não por IA.

    O painel da estação sugeria responsável a partir de quem já tinha
    resolvido coisa parecida. Aqui a conta é a mesma, feita em SQL: por tipo
    de demanda, quem mais ENCERROU chamados nos últimos 90 dias.

    Sai como SUGESTÃO e nada mais. Distribuir chamado é decisão de gestão, e
    uma tela que atribuísse sozinha estaria trocando o julgamento de quem
    conhece a equipe por uma contagem de frequência — que ignora férias,
    carga atual e quem está aprendendo o quê.
    """
    saida = {"dias": 90, "sugestoes": [], "migration_ausente": False}
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        # Um responsável por tipo: o de maior contagem. ROW_NUMBER em vez de
        # trazer tudo e decidir no Python — a ordenação por desempate fica
        # explícita (mais recente ganha de mais antigo em caso de empate).
        cur.execute(
            "WITH conta AS ("
            "  SELECT tipo_demanda, atribuido_a, COUNT(*) AS total, "
            "         MAX(encerrado_em) AS ultimo "
            "  FROM dbo.etl_chamado "
            "  WHERE encerrado_em >= DATEADD(DAY, -90, GETDATE()) "
            "    AND NULLIF(LTRIM(RTRIM(atribuido_a)), '') IS NOT NULL "
            "    AND NULLIF(LTRIM(RTRIM(tipo_demanda)), '') IS NOT NULL "
            "  GROUP BY tipo_demanda, atribuido_a), "
            "ranqueado AS ("
            "  SELECT *, ROW_NUMBER() OVER (PARTITION BY tipo_demanda "
            "         ORDER BY total DESC, ultimo DESC) AS posicao FROM conta) "
            "SELECT tipo_demanda, atribuido_a, total FROM ranqueado "
            "WHERE posicao = 1 ORDER BY total DESC")
        saida["sugestoes"] = [
            {"tipo_demanda": r[0], "responsavel": r[1], "resolvidos": r[2]}
            for r in cur.fetchall()]
        cur.close(); conn.close()
    except Exception as e:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        log.warning("sugestoes: espelho indisponível (%s: %s)", type(e).__name__, e)
        saida["migration_ausente"] = True
    return saida


@router.get("/chamados/historico", tags=["chamados"])
def historico(dias: int = DIAS_HISTORICO,
              _auth: dict = Depends(get_current_user)):
    """Os chamados RESOLVIDOS na janela — o que o kanban não mostra.

    A tela vive da fila viva, e o que foi resolvido sai dela (ativo=0). O
    resultado é que o trabalho entregue fica invisível: a equipe olha o painel
    e vê só o que falta. O painel da estação resolvia isso com uma seção de
    resolvidos dos últimos 10 dias, e é ela que este endpoint serve.

    Também é o insumo do "quem costuma atender o quê" — por isso o responsável
    vem junto.
    """
    # Teto e piso: o parâmetro vem da URL, e uma janela de 3650 dias varreria o
    # espelho inteiro a cada abertura da tela.
    #
    # Sem `or DIAS_HISTORICO`: zero é falsy, e o `or` transformaria `dias=0`
    # no padrão de 10 em vez de no mínimo de 1 — silenciosamente devolvendo
    # dez vezes mais do que foi pedido. O default já vem da assinatura.
    dias = max(1, min(int(dias), 90))
    saida = {"dias": dias, "chamados": [], "total": 0,
             "ainda_na_fila": 0, "migration_ausente": False}
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT numero, tipo, titulo, atribuido_a, demandante, "
            "       tipo_demanda, categoria_diaadia, encerrado_em, url, "
            "       DATEDIFF(DAY, aberto_em, encerrado_em) AS dias_ate_resolver, "
            "       ativo "
            "FROM dbo.etl_chamado "
            "WHERE encerrado_em >= DATEADD(DAY, ?, CAST(GETDATE() AS DATE)) "
            "  AND tipo != 'task' "
            "ORDER BY encerrado_em DESC", [-(dias - 1)])
        for r in cur.fetchall():
            saida["chamados"].append({
                "numero": r[0], "tipo": r[1], "titulo": r[2],
                "atribuido_a": r[3] or "", "demandante": r[4] or "",
                "tipo_demanda": r[5] or TIPO_NAO_CLASSIFICADO,
                "categoria_diaadia": r[6] or "",
                "encerrado_em": _fmt_dt(r[7]), "url": r[8],
                # Pode ser negativo se as datas da origem discordarem; melhor
                # mostrar o absurdo do que escondê-lo com um max(0, …).
                "dias_ate_resolver": r[9] if r[9] is not None else None,
                # "Resolvido" mantém ativo=1 no espelho — só 'encerrado' tira
                # da fila. Sem este campo, um chamado apareceria ao mesmo
                # tempo na coluna Resolvido do kanban e numa seção que se diz
                # "o que saiu da fila". A tela marca esses.
                "ainda_na_fila": bool(r[10]),
            })
        saida["ainda_na_fila"] = sum(1 for c in saida["chamados"]
                                     if c["ainda_na_fila"])
        saida["total"] = len(saida["chamados"])
        cur.close(); conn.close()
    except Exception as e:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        log.warning("historico: espelho indisponível (%s: %s)", type(e).__name__, e)
        saida["migration_ausente"] = True
    return saida


@router.get("/chamados/dashboard", tags=["chamados"])
def dashboard(visao: str = "geral", _auth: dict = Depends(get_current_user)):
    """Painel estratégico — 8 grupos de chamados para visão executiva/operacional.

    `visao=geral`   → toda a fila ativa (tipo != task).
    `visao=proprio` → filtrado pelo email do usuário logado (migration 093:
                      atribuido_a_email = email), com fallback para LIKE por
                      nome enquanto registros sem email forem sincronizados.

    Cada grupo traz `total` e `chamados` — a lista completa para o modal da
    tela. Nenhuma paginação: o maior grupo (backlog) tem ~37 itens; trazer tudo
    em um round-trip é mais rápido do que abrir um segundo request ao clicar.
    """
    # Filtro "Meu painel" — usa email exato quando disponível (migration 093),
    # cai em LIKE por nome como fallback para registros ainda sem email sincronizado.
    email_proprio = ""
    nome_proprio = ""
    if visao == "proprio":
        email_proprio = (_auth.get("email") or "").strip()
        fn = (_auth.get("primeiro_nome") or "").strip()
        ln = (_auth.get("ultimo_nome") or "").strip()
        nome_proprio = f"{fn} {ln}".strip()

    if visao in ("diaadia", "iniciativa"):
        _cat = "dia a dia" if visao == "diaadia" else "iniciativa"
        _filtro = " AND categoria_diaadia = ?"
        _p = [_cat]
    elif email_proprio:
        _filtro = " AND atribuido_a_email = ?"
        _p = [email_proprio]
    elif nome_proprio:
        _filtro = " AND atribuido_a LIKE ?"
        _p = [f"%{nome_proprio}%"]
    else:
        _filtro = ""
        _p = []

    # Campos retornados em cada chamado do modal
    _COLS = (
        "sys_id, numero, titulo, atribuido_a, estado_kanban, "
        "prazo, aberto_em, url, sla_vencido, tipo_demanda, atribuido_a_email"
    )

    def _rows(cur):
        return [
            {
                "sys_id": r[0], "numero": r[1], "titulo": r[2],
                "atribuido_a": r[3] or "", "estado_kanban": r[4],
                "prazo": _fmt_dt(r[5]), "aberto_em": _fmt_dt(r[6]),
                "url": r[7], "sla_vencido": bool(r[8]) if r[8] is not None else None,
                "tipo_demanda": r[9] or TIPO_NAO_CLASSIFICADO,
                "atribuido_a_email": r[10] or "",
            }
            for r in cur.fetchall()
        ]

    _BASE = "FROM dbo.etl_chamado WHERE ativo=1 AND tipo!='task'"

    grupos = {
        "backlog":           ("backlog",           "Demandas Backlog",         "amber"),
        "abertas":           ("abertas",           "Abertas",                  "amber"),
        "resolvidas_hoje":   ("resolvidas_hoje",   "Resolvidas hoje",          "green"),
        "andamento":         ("andamento",         "Em Andamento",             "indigo"),
        "pendentes":         ("pendentes",         "Pendentes",                "neutral"),
        "sem_analista":      ("sem_analista",      "Backlog Sem Analista",     "amber"),
        "resolvidas":        ("resolvidas",        "Resolvidas",               "green"),
        "vencem_hoje":       ("vencem_hoje",       "Vencem Hoje",              "red"),
        "vencem_semana":     ("vencem_semana",     "Vencem essa semana",       "orange"),
        "vencidas":          ("vencidas",          "Vencidas",                 "red"),
    }

    saida: dict = {
        "visao": visao,
        "nome_proprio": nome_proprio or None,
        "migration_ausente": False,
    }
    for k, (_, label, cor) in grupos.items():
        saida[k] = {"label": label, "cor": cor, "total": 0, "chamados": []}

    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()

        # ── backlog: abertos/novos (coluna "Novo" do kanban) ───────────────────
        cur.execute(
            f"SELECT {_COLS} {_BASE}"
            f"  AND estado_kanban='novo'{_filtro}"
            "  ORDER BY aberto_em ASC", _p)
        saida["backlog"]["chamados"] = _rows(cur)
        saida["backlog"]["total"] = len(saida["backlog"]["chamados"])

        # ── abertas: entradas de hoje (aberto_em = hoje) ────────────────────
        cur.execute(
            f"SELECT {_COLS} {_BASE}"
            f"  AND CAST(aberto_em AS DATE) = CAST(GETDATE() AS DATE){_filtro}"
            "  ORDER BY aberto_em DESC", _p)
        saida["abertas"]["chamados"] = _rows(cur)
        saida["abertas"]["total"] = len(saida["abertas"]["chamados"])

        # ── andamento ────────────────────────────────────────────────────────
        cur.execute(
            f"SELECT {_COLS} {_BASE}"
            f"  AND estado_kanban='andamento'{_filtro}"
            "  ORDER BY aberto_em ASC", _p)
        saida["andamento"]["chamados"] = _rows(cur)
        saida["andamento"]["total"] = len(saida["andamento"]["chamados"])

        # ── pendentes: aguardando ────────────────────────────────────────────
        cur.execute(
            f"SELECT {_COLS} {_BASE}"
            f"  AND estado_kanban='aguardando'{_filtro}"
            "  ORDER BY aberto_em ASC", _p)
        saida["pendentes"]["chamados"] = _rows(cur)
        saida["pendentes"]["total"] = len(saida["pendentes"]["chamados"])

        # ── sem analista ─────────────────────────────────────────────────────
        cur.execute(
            f"SELECT {_COLS} {_BASE}"
            f"  AND NULLIF(LTRIM(RTRIM(atribuido_a)),'') IS NULL{_filtro}"
            "  ORDER BY aberto_em ASC", _p)
        saida["sem_analista"]["chamados"] = _rows(cur)
        saida["sem_analista"]["total"] = len(saida["sem_analista"]["chamados"])

        # ── resolvidas hoje: encerradas/resolvidas com encerrado_em = hoje ─────
        cur.execute(
            f"SELECT {_COLS} FROM dbo.etl_chamado WHERE tipo!='task'"
            f"  AND estado_kanban IN ('resolvido','encerrado')"
            f"  AND CAST(encerrado_em AS DATE) = CAST(GETDATE() AS DATE){_filtro}"
            "  ORDER BY encerrado_em DESC", _p)
        saida["resolvidas_hoje"]["chamados"] = _rows(cur)
        saida["resolvidas_hoje"]["total"] = len(saida["resolvidas_hoje"]["chamados"])

        # ── resolvidas: estado resolvido ainda ativo ─────────────────────────
        cur.execute(
            f"SELECT {_COLS} {_BASE}"
            f"  AND estado_kanban='resolvido'{_filtro}"
            "  ORDER BY aberto_em ASC", _p)
        saida["resolvidas"]["chamados"] = _rows(cur)
        saida["resolvidas"]["total"] = len(saida["resolvidas"]["chamados"])

        # ── vencem hoje ──────────────────────────────────────────────────────
        cur.execute(
            f"SELECT {_COLS} {_BASE}"
            f"  AND estado_kanban NOT IN ('resolvido','encerrado','outros')"
            f"  AND CAST(prazo AS DATE) = CAST(GETDATE() AS DATE){_filtro}"
            "  ORDER BY prazo ASC", _p)
        saida["vencem_hoje"]["chamados"] = _rows(cur)
        saida["vencem_hoje"]["total"] = len(saida["vencem_hoje"]["chamados"])

        # ── vencem essa semana (amanhã até sexta-feira) ──────────────────────
        cur.execute(
            f"SELECT {_COLS} {_BASE}"
            f"  AND estado_kanban NOT IN ('resolvido','encerrado','outros')"
            f"  AND prazo IS NOT NULL"
            f"  AND CAST(prazo AS DATE) > CAST(GETDATE() AS DATE)"
            f"  AND CAST(prazo AS DATE) <= DATEADD(DAY, 6-DATEPART(WEEKDAY, GETDATE()), CAST(GETDATE() AS DATE)){_filtro}"
            "  ORDER BY prazo ASC", _p)
        saida["vencem_semana"]["chamados"] = _rows(cur)
        saida["vencem_semana"]["total"] = len(saida["vencem_semana"]["chamados"])

        # ── vencidas: prazo < hoje ───────────────────────────────────────────
        cur.execute(
            f"SELECT {_COLS} {_BASE}"
            f"  AND estado_kanban NOT IN ('resolvido','encerrado','outros')"
            f"  AND prazo IS NOT NULL"
            f"  AND CAST(prazo AS DATE) < CAST(GETDATE() AS DATE){_filtro}"
            "  ORDER BY prazo ASC", _p)
        saida["vencidas"]["chamados"] = _rows(cur)
        saida["vencidas"]["total"] = len(saida["vencidas"]["chamados"])

        # ── fluxo do dia: entradas x saídas ─────────────────────────────────
        _p_base = _p if _filtro else []
        cur.execute(
            "SELECT COUNT(*) FROM dbo.etl_chamado"
            " WHERE tipo!='task'"
            f"  AND CAST(aberto_em AS DATE) = CAST(GETDATE() AS DATE){_filtro}", _p)
        entradas = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM dbo.etl_chamado"
            " WHERE tipo!='task'"
            f"  AND estado_kanban IN ('resolvido','encerrado')"
            f"  AND CAST(encerrado_em AS DATE) = CAST(GETDATE() AS DATE){_filtro}", _p)
        saidas = cur.fetchone()[0]
        saida["fluxo_hoje"] = {"entradas": entradas, "saidas": saidas}

        # ── total fila = mesmo critério do kanban: ativo=1 sem tasks ─────────
        cur.execute(
            f"SELECT COUNT(*) {_BASE}{_filtro}", _p)
        saida["total_fila"] = cur.fetchone()[0]

        cur.close(); conn.close()
    except Exception as e:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        log.warning("dashboard: espelho indisponível (%s: %s)", type(e).__name__, e)
        saida["migration_ausente"] = True
    return saida


# IMPORTANTE: /chamados/indicadores/historico é declarada ANTES de
# /chamados/{sys_id}/... para evitar conflito de matching (FastAPI lê rotas em
# ordem; "indicadores" casaria com {sys_id} e "historico" com "tasks").

@router.get("/chamados/indicadores/historico", tags=["chamados"])
def indicadores_historico(periodo: str = "30d", grupo: str | None = None,
                          _auth: dict = Depends(get_current_user)):
    """Histórico de snapshots de indicadores operacionais."""
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()

        if periodo == "hoje":
            trunc = "DATEPART(hour, s.capturado_em)"
            janela = "s.capturado_em >= DATEADD(DAY, -1, GETDATE())"
        elif periodo == "historico":
            trunc = "DATEPART(week, s.capturado_em)"
            janela = "1=1"
        else:  # 30d (default)
            trunc = "CAST(s.capturado_em AS DATE)"
            janela = "s.capturado_em >= DATEADD(DAY, -30, GETDATE())"

        cur.execute(f"""
            SELECT TOP 500
                MIN(s.capturado_em),
                AVG(CAST(s.total_ativos AS DECIMAL(8,1))),
                AVG(CAST(s.novo AS DECIMAL(8,1))),
                AVG(CAST(s.andamento AS DECIMAL(8,1))),
                AVG(CAST(s.aguardando AS DECIMAL(8,1))),
                AVG(CAST(s.resolvido AS DECIMAL(8,1))),
                AVG(CAST(s.outros AS DECIMAL(8,1))),
                AVG(CAST(s.sla_vencidos AS DECIMAL(8,1))),
                AVG(s.idade_media_dias),
                AVG(s.tempo_medio_resolucao_horas),
                AVG(CAST(s.qtd_encerrados_7d AS DECIMAL(8,1))),
                AVG(CAST(s.qtd_abertos_7d AS DECIMAL(8,1))),
                AVG(CAST(s.qtd_iniciativas_abertas AS DECIMAL(8,1)))
            FROM dbo.etl_indicador_snapshot s
            WHERE {janela}
            GROUP BY {trunc}
            ORDER BY 1 DESC
        """)
        snapshots = [
            {"capturado_em": str(r[0]), "total_ativos": r[1], "novo": r[2],
             "andamento": r[3], "aguardando": r[4], "resolvido": r[5],
             "outros": r[6], "sla_vencidos": r[7], "idade_media_dias": r[8],
             "tempo_medio_resolucao_horas": r[9], "qtd_encerrados_7d": r[10],
             "qtd_abertos_7d": r[11], "qtd_iniciativas_abertas": r[12]}
            for r in cur.fetchall()
        ]

        cur.execute("SELECT MAX(id) FROM dbo.etl_indicador_snapshot")
        ultimo_id = (cur.fetchone() or (None,))[0]

        por_analista = []
        por_grupo = []
        if ultimo_id:
            cur.execute(
                "SELECT atribuido_a, atribuido_a_email, total_ativos, "
                "  sla_vencidos, idade_media_dias "
                "FROM dbo.etl_indicador_snapshot_analista "
                "WHERE id_snapshot=? ORDER BY total_ativos DESC", [ultimo_id])
            por_analista = [
                {"atribuido_a": r[0], "atribuido_a_email": r[1],
                 "total_ativos": r[2], "sla_vencidos": r[3],
                 "idade_media_dias": r[4]}
                for r in cur.fetchall()
            ]
            filtro_grupo = "AND grupo=?" if grupo else ""
            params_g = [ultimo_id, grupo] if grupo else [ultimo_id]
            cur.execute(
                f"SELECT grupo, total_ativos, sla_vencidos, idade_media_dias "
                f"FROM dbo.etl_indicador_snapshot_grupo "
                f"WHERE id_snapshot=? {filtro_grupo} ORDER BY total_ativos DESC",
                params_g)
            por_grupo = [
                {"grupo": r[0], "total_ativos": r[1], "sla_vencidos": r[2],
                 "idade_media_dias": r[3]}
                for r in cur.fetchall()
            ]

        cur.execute(
            "SELECT metrica, valor_meta, grupo FROM dbo.etl_indicador_meta "
            "WHERE periodo_fim IS NULL OR periodo_fim >= CAST(GETDATE() AS DATE)")
        metas = [
            {"metrica": r[0], "valor_meta": float(r[1]), "grupo": r[2]}
            for r in cur.fetchall()
        ]

        cur.close(); conn.close()
        return {"snapshots": snapshots, "por_analista": por_analista,
                "por_grupo": por_grupo, "metas": metas}
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        log.warning("indicadores_historico: erro (%s: %s)", type(e).__name__, e)
        raise _HTTPException(status_code=500, detail=str(e))


@router.get("/chamados/{sys_id}/tasks", tags=["chamados"])
def tasks_do_ritm(sys_id: str, _auth: dict = Depends(get_current_user)):
    """SCTASKs filhas de um RITM — hierarquia RITM → SCTASK (migration 089).

    Retorna todos os chamados cujo pai_sys_id bate com o sys_id passado.
    Inclui inativos: a tela de detalhe precisa ver o histórico completo,
    não só a fila viva.
    """
    saida: dict = {"sys_id": sys_id, "tasks": [], "total": 0,
                   "migration_ausente": False}
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT sys_id, numero, tipo, titulo, estado_kanban, prioridade, "
            "       atribuido_a, grupo, aberto_em, atualizado_em, encerrado_em, "
            "       ativo, url, sync_em "
            "FROM dbo.etl_chamado "
            "WHERE pai_sys_id = ? "
            "ORDER BY aberto_em DESC",
            [sys_id])
        for r in cur.fetchall():
            saida["tasks"].append({
                "sys_id": r[0], "numero": r[1], "tipo": r[2], "titulo": r[3],
                "estado_kanban": r[4], "prioridade": r[5],
                "atribuido_a": r[6] or "", "grupo": r[7] or "",
                "aberto_em": _fmt_dt(r[8]), "atualizado_em": _fmt_dt(r[9]),
                "encerrado_em": _fmt_dt(r[10]), "ativo": bool(r[11]),
                "url": r[12], "sync_em": _fmt_dt(r[13]),
            })
        saida["total"] = len(saida["tasks"])
        cur.close(); conn.close()
    except Exception as e:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        log.warning("tasks_do_ritm: espelho indisponível (%s: %s)", type(e).__name__, e)
        saida["migration_ausente"] = True
    return saida


# ── Categorias ServiceNow ────────────────────────────────────────────────────
# Fonte única de verdade para as categorias que classificam chamados
# (dia a dia / iniciativa / …). O filtro do kanban lê daqui em vez de ter
# os valores hardcoded no frontend — nova categoria cadastrada aqui aparece
# automaticamente no filtro sem tocar no bundle.

@router.get("/chamados/categorias", tags=["chamados"])
def listar_categorias(_auth: dict = Depends(get_current_user)):
    """Categorias ativas para classificação de chamados (ex.: dia a dia, iniciativa)."""
    saida: list = []
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT id, slug, label, descricao, padrao "
            "FROM dbo.etl_sn_categoria "
            "ORDER BY padrao DESC, label")
        saida = [{"id": r[0], "slug": r[1], "label": r[2],
                  "descricao": r[3] or "", "padrao": bool(r[4])}
                 for r in cur.fetchall()]
        cur.close(); conn.close()
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        log.warning("categorias: indisponível (%s: %s)", type(e).__name__, e)
    return saida


@router.post("/admin/servicenow/categorias", tags=["admin"])
def criar_categoria(body: dict, _auth: dict = Depends(get_current_user)):
    """Cadastra uma nova categoria de classificação de chamados."""
    slug = (body.get("slug") or "").strip().lower()
    label = (body.get("label") or "").strip()
    descricao = (body.get("descricao") or "").strip() or None
    if not slug or not label:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="slug e label são obrigatórios")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.etl_sn_categoria (slug, label, descricao) "
            "VALUES (?, ?, ?)", [slug, label, descricao])
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "slug": slug, "label": label}


@router.delete("/admin/servicenow/categorias/{cat_id}", tags=["admin"])
def excluir_categoria(cat_id: int, _auth: dict = Depends(get_current_user)):
    """Remove uma categoria (apenas as não-padrão podem ser excluídas)."""
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT padrao FROM dbo.etl_sn_categoria WHERE id = ?", [cat_id])
        row = cur.fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Categoria não encontrada")
        if row[0]:
            from fastapi import HTTPException
            raise HTTPException(status_code=409,
                                detail="Categorias padrão não podem ser excluídas")
        cur.execute("DELETE FROM dbo.etl_sn_categoria WHERE id = ?", [cat_id])
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        if "HTTPException" in type(e).__name__:
            raise
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}


# ── Novos endpoints: detalhe, proxy de anexos, indicadores históricos, admin ──
import httpx as _httpx
import os as _os

from fastapi import HTTPException as _HTTPException
from fastapi.responses import StreamingResponse as _StreamingResponse
from services.conn_crypto import decrypt_password



@router.get("/chamados/{sys_id}/detalhe", tags=["chamados"])
def chamado_detalhe(sys_id: str, _auth: dict = Depends(get_current_user)):
    """Detalhe completo de um chamado: dados + notas + anexos."""
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT sys_id, numero, tipo, titulo, descricao, estado_kanban, "
            "  atribuido_a, atribuido_a_email, grupo, aberto_em, url, "
            "  ISNULL(tem_anexo,0), ISNULL(sla_vencido,0), prazo "
            "FROM dbo.etl_chamado WHERE sys_id=?", [sys_id])
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close()
            raise _HTTPException(status_code=404, detail="chamado não encontrado")

        chamado = {
            "sys_id": row[0], "numero": row[1], "tipo": row[2],
            "titulo": row[3], "descricao": row[4], "estado_kanban": row[5],
            "atribuido_a": row[6], "atribuido_a_email": row[7], "grupo": row[8],
            "aberto_em": str(row[9]) if row[9] else None, "url": row[10],
            "tem_anexo": bool(row[11]), "sla_vencido": bool(row[12]),
            "prazo": str(row[13]) if row[13] else None,
        }

        cur.execute(
            "SELECT sys_id_nota, autor, autor_email, criado_em, texto, tipo "
            "FROM dbo.etl_chamado_nota WHERE sys_id_chamado=? "
            "ORDER BY criado_em", [sys_id])
        notas = [
            {"sys_id_nota": r[0], "autor": r[1], "autor_email": r[2],
             "criado_em": str(r[3]) if r[3] else None,
             "texto": r[4], "tipo": r[5]}
            for r in cur.fetchall()
        ]

        cur.execute(
            "SELECT sys_id_anexo, nome_arquivo, mime_type, tamanho_bytes, criado_em "
            "FROM dbo.etl_chamado_anexo WHERE sys_id_chamado=? "
            "ORDER BY criado_em", [sys_id])
        anexos = [
            {"sys_id_anexo": r[0], "nome_arquivo": r[1], "mime_type": r[2],
             "tamanho_bytes": r[3],
             "url_proxy": f"/chamados/{sys_id}/anexos/{r[0]}",
             "criado_em": str(r[4]) if r[4] else None}
            for r in cur.fetchall()
        ]

        cur.close(); conn.close()
        return {"chamado": chamado, "notas": notas, "anexos": anexos}
    except _HTTPException:
        raise
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        log.warning("chamado_detalhe: erro (%s: %s)", type(e).__name__, e)
        raise _HTTPException(status_code=500, detail=str(e))


@router.get("/chamados/{sys_id}/anexos/{sys_id_anexo}", tags=["chamados"])
def chamado_anexo_proxy(sys_id: str, sys_id_anexo: str,
                        _auth: dict = Depends(get_current_user)):
    """Proxy de download de anexo — credencial lida do banco a cada request."""
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT url_download, nome_arquivo, mime_type "
            "FROM dbo.etl_chamado_anexo "
            "WHERE sys_id_anexo=? AND sys_id_chamado=?",
            [sys_id_anexo, sys_id])
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close()
            raise _HTTPException(status_code=404, detail="anexo não encontrado")
        url_dl, nome_arquivo, mime_type = row[0], row[1], row[2]

        # credencial lida a cada request — sem cache
        cur.execute(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN ('servicenow_url','servicenow_usuario',"
            "'servicenow_senha_enc')")
        cfg = dict(cur.fetchall())
        cur.close(); conn.close(); conn = None
        usuario = cfg.get("servicenow_usuario", "")
        senha = decrypt_password(cfg.get("servicenow_senha_enc", ""))

        with _httpx.Client(auth=(usuario, senha), timeout=30,
                           follow_redirects=True) as cli:
            try:
                sn_resp = cli.get(url_dl)
                sn_resp.raise_for_status()
            except Exception as e:
                raise _HTTPException(status_code=502,
                                     detail=f"ServiceNow indisponível: {e}")

        headers = {}
        mime = mime_type or sn_resp.headers.get("content-type", "application/octet-stream")
        if not mime.startswith("image/"):
            nome_safe = (nome_arquivo or "arquivo").replace('"', '')
            headers["Content-Disposition"] = f'attachment; filename="{nome_safe}"'

        return _StreamingResponse(
            iter([sn_resp.content]), media_type=mime, headers=headers)
    except _HTTPException:
        raise
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        log.warning("chamado_anexo_proxy: erro (%s: %s)", type(e).__name__, e)
        raise _HTTPException(status_code=500, detail=str(e))


# ── Admin ServiceNow ──────────────────────────────────────────────────────────

@router.get("/admin/servicenow/config", tags=["admin"])
def admin_sn_config(_auth: dict = Depends(get_current_user)):
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN ('servicenow_url','servicenow_usuario',"
            "'servicenow_habilitado')")
        cfg = dict(cur.fetchall())
        cur.close(); conn.close()
        return {
            "url": cfg.get("servicenow_url", ""),
            "usuario": cfg.get("servicenow_usuario", ""),
            "habilitado": cfg.get("servicenow_habilitado", "0") == "1",
        }
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        log.warning("admin_sn_config: erro (%s: %s)", type(e).__name__, e)
        raise _HTTPException(status_code=500, detail=str(e))


@router.put("/admin/servicenow/config", tags=["admin"])
def admin_sn_config_salvar(payload: dict, _auth: dict = Depends(get_current_user)):
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _campos_validos = {"servicenow_url", "servicenow_usuario",
                           "servicenow_habilitado", "servicenow_senha_enc"}
        for campo, valor in payload.items():
            if campo not in _campos_validos:
                continue
            cur.execute(
                "MERGE dbo.etl_app_config AS t "
                "USING (SELECT ? AS config_key) AS s ON t.config_key=s.config_key "
                "WHEN MATCHED THEN UPDATE SET config_value=? "
                "WHEN NOT MATCHED THEN INSERT (config_key,config_value) "
                "VALUES (?,?)",
                [campo, str(valor), campo, str(valor)])
        conn.commit(); cur.close(); conn.close()
        return {"ok": True}
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        log.warning("admin_sn_config_salvar: erro (%s: %s)", type(e).__name__, e)
        raise _HTTPException(status_code=500, detail=str(e))


@router.post("/admin/servicenow/testar", tags=["admin"])
def admin_sn_testar(_auth: dict = Depends(get_current_user)):
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN ('servicenow_url','servicenow_usuario',"
            "'servicenow_senha_enc')")
        cfg = dict(cur.fetchall())
        cur.close(); conn.close(); conn = None
        url = (cfg.get("servicenow_url") or "").rstrip("/")
        usuario = cfg.get("servicenow_usuario", "")
        senha = decrypt_password(cfg.get("servicenow_senha_enc", ""))

        import time
        t0 = time.time()
        try:
            with _httpx.Client(auth=(usuario, senha), timeout=10) as cli:
                resp = cli.get(f"{url}/api/now/table/incident"
                               "?sysparm_limit=1&sysparm_fields=sys_id")
                resp.raise_for_status()
            latencia_ms = int((time.time() - t0) * 1000)
            return {"ok": True, "latencia_ms": latencia_ms,
                    "status_code": resp.status_code}
        except Exception as e:
            return {"ok": False, "erro": str(e)[:200]}
    except _HTTPException:
        raise
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        log.warning("admin_sn_testar: erro (%s: %s)", type(e).__name__, e)
        raise _HTTPException(status_code=500, detail=str(e))


@router.get("/admin/servicenow/grupos", tags=["admin"])
def admin_sn_grupos(_auth: dict = Depends(get_current_user)):
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT id, nome, ativo, criado_em FROM dbo.etl_servicenow_grupo "
            "ORDER BY ativo DESC, nome")
        result = [
            {"id": r[0], "nome": r[1], "ativo": bool(r[2]),
             "criado_em": str(r[3]) if r[3] else None}
            for r in cur.fetchall()
        ]
        cur.close(); conn.close()
        return result
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        log.warning("admin_sn_grupos: erro (%s: %s)", type(e).__name__, e)
        raise _HTTPException(status_code=500, detail=str(e))


@router.post("/admin/servicenow/grupos", tags=["admin"])
def admin_sn_grupo_criar(payload: dict, _auth: dict = Depends(get_current_user)):
    nome = (payload.get("nome") or "").strip()
    if not nome:
        raise _HTTPException(status_code=422, detail="nome obrigatório")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.etl_servicenow_grupo (nome) VALUES (?)", [nome])
        conn.commit(); cur.close(); conn.close()
        return {"ok": True}
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        log.warning("admin_sn_grupo_criar: erro (%s: %s)", type(e).__name__, e)
        if "2627" in str(e) or "UQ_sn_grupo" in str(e) or "duplicate key" in str(e).lower():
            raise _HTTPException(status_code=409, detail=f"Grupo '{nome}' já existe.")
        raise _HTTPException(status_code=500, detail=str(e))


@router.put("/admin/servicenow/grupos/{grupo_id}", tags=["admin"])
def admin_sn_grupo_editar(grupo_id: int, payload: dict,
                          _auth: dict = Depends(get_current_user)):
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        if "ativo" in payload:
            cur.execute(
                "UPDATE dbo.etl_servicenow_grupo "
                "SET ativo=?, alterado_em=GETDATE() WHERE id=?",
                [1 if payload["ativo"] else 0, grupo_id])
        if "nome" in payload:
            cur.execute(
                "UPDATE dbo.etl_servicenow_grupo "
                "SET nome=?, alterado_em=GETDATE() WHERE id=?",
                [(payload["nome"] or "").strip(), grupo_id])
        conn.commit(); cur.close(); conn.close()
        return {"ok": True}
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        log.warning("admin_sn_grupo_editar: erro (%s: %s)", type(e).__name__, e)
        raise _HTTPException(status_code=500, detail=str(e))


@router.get("/admin/servicenow/ciclos", tags=["admin"])
def admin_sn_ciclos(_auth: dict = Depends(get_current_user)):
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT TOP 20 id, modo, iniciado_em, terminado_em, status, "
            "  qtd_chamados, qtd_notas, qtd_anexos, qtd_desativados, "
            "  disparado_por, erro "
            "FROM dbo.etl_chamado_ciclo ORDER BY id DESC")
        result = [
            {"id": r[0], "modo": r[1],
             "iniciado_em": str(r[2]) if r[2] else None,
             "terminado_em": str(r[3]) if r[3] else None,
             "status": r[4], "qtd_chamados": r[5], "qtd_notas": r[6],
             "qtd_anexos": r[7], "qtd_desativados": r[8],
             "disparado_por": r[9], "erro": r[10]}
            for r in cur.fetchall()
        ]
        cur.close(); conn.close()
        return result
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        log.warning("admin_sn_ciclos: erro (%s: %s)", type(e).__name__, e)
        raise _HTTPException(status_code=500, detail=str(e))


@router.post("/admin/servicenow/disparar-delta", tags=["admin"])
def admin_sn_disparar_delta(_auth: dict = Depends(get_current_user)):
    airflow_url = _os.getenv("AIRFLOW_URL", "http://airflow-webserver:8080")
    airflow_user = _os.getenv("AIRFLOW_USER", "airflow")
    airflow_pass = _os.getenv("AIRFLOW_PASSWORD", "airflow")
    try:
        with _httpx.Client(
                auth=(airflow_user, airflow_pass), timeout=10) as cli:
            resp = cli.post(
                f"{airflow_url}/api/v1/dags/etl_servicenow_delta/dagRuns",
                json={})
            resp.raise_for_status()
        return {"ok": True, "dag_run_id": resp.json().get("dag_run_id")}
    except Exception as e:
        raise _HTTPException(status_code=502,
                             detail=f"Airflow indisponível: {e}")


@router.get("/admin/servicenow/perfis-acesso", tags=["admin"])
def admin_sn_perfis(_auth: dict = Depends(get_current_user)):
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT config_value FROM dbo.etl_app_config "
            "WHERE config_key='servicenow_admin_perfis'")
        row = cur.fetchone()
        perfis = (row[0] or "").split(",") if row else []
        cur.close(); conn.close()
        return {"perfis": [p.strip() for p in perfis if p.strip()]}
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        log.warning("admin_sn_perfis: erro (%s: %s)", type(e).__name__, e)
        raise _HTTPException(status_code=500, detail=str(e))


@router.put("/admin/servicenow/perfis-acesso", tags=["admin"])
def admin_sn_perfis_salvar(payload: dict, _auth: dict = Depends(get_current_user)):
    perfis = ",".join(payload.get("perfis", []))
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "MERGE dbo.etl_app_config AS t "
            "USING (SELECT 'servicenow_admin_perfis' AS config_key) AS s "
            "ON t.config_key=s.config_key "
            "WHEN MATCHED THEN UPDATE SET config_value=? "
            "WHEN NOT MATCHED THEN INSERT (config_key,config_value) VALUES (?,?)",
            [perfis, "servicenow_admin_perfis", perfis])
        conn.commit(); cur.close(); conn.close()
        return {"ok": True}
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        log.warning("admin_sn_perfis_salvar: erro (%s: %s)", type(e).__name__, e)
        raise _HTTPException(status_code=500, detail=str(e))
