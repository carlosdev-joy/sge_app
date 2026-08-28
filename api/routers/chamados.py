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
FRESCOR_ALERTA_MINUTOS = 60

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


# O MESMO recorte da fila, em SQL — para quem só CONTA.
#
# A tela separa em JavaScript porque precisa dos DOIS registros: o pai vira
# card e o filho vira linha dentro dele (`lib/filaChamados.separarFila`). As
# agregações não mostram o filho, então trazer a tabela inteira para contar
# linha em Python seria desperdício — elas cortam no banco.
#
# São dois caminhos para a mesma regra, e é exatamente por isso que existe o
# teste de paridade: sem ele a aba Indicadores diz 95 enquanto a Fila diz 59, e
# as duas parecem certas. Medido no dev em 2026-08-28, contra a instância real.
#
# As três condições, e o que cada uma impede:
#
#   tipo = 'task'          — só a tarefa sai. RITM com pai (dado torto) segue
#                            contando: um defeito de dado não pode sumir com
#                            PEDIDO das contas.
#   pai_sys_id <> ''       — o sync grava '' quando o campo não vem da API.
#                            Tratar '' como valor faria TODA linha ter pai e
#                            zeraria as agregações inteiras, sem erro nenhum.
#   pai_sys_id <> sys_id   — auto-referência. Sem esta, uma task que aponte
#                            para si mesma sumiria da conta E da fila, e nada
#                            avisaria.
#
# NUNCA `NOT IN`: com um NULL na subconsulta ele devolve conjunto vazio, e a
# conta inteira viraria zero sem erro. Aqui não há subconsulta — e é para que
# continue assim que o teste `test_o_predicado_nao_usa_not_in` existe.
def _so_trabalhos() -> str:
    """Predicado SQL: a tarefa já representada pelo card do pai não conta."""
    return (" AND NOT (tipo = 'task' "
            "          AND pai_sys_id IS NOT NULL "
            "          AND pai_sys_id <> '' "
            "          AND pai_sys_id <> sys_id) ")


def _fmt_dt(v):
    return str(v)[:19] if v else None


def _ultimo_ciclo(cur) -> dict | None:
    """O ciclo mais recente — a fonte do frescor e do 'por que está vazio'."""
    cur.execute(
        "SELECT TOP 1 id, iniciado_em, terminado_em, status, qtd_incident, "
        "       qtd_ritm, qtd_task, qtd_change, qtd_desativados, erro, "
        "       DATEDIFF(MINUTE, iniciado_em, GETDATE()) AS idade_min "
        "FROM dbo.etl_chamado_sync ORDER BY iniciado_em DESC")
    linha = cur.fetchone()
    if not linha:
        return None
    idade_min = linha[10] if linha[10] is not None else None
    return {
        "id": linha[0],
        "iniciado_em": _fmt_dt(linha[1]),
        "terminado_em": _fmt_dt(linha[2]),
        "status": linha[3],
        "quantidades": {"incident": linha[4], "ritm": linha[5],
                        "task": linha[6], "change": linha[7]},
        "desativados": linha[8],
        "erro": linha[9],
        "idade_minutos": idade_min,
        # "nunca terminou" é diferente de "terminou com erro": o primeiro é
        # worker morto no meio, o segundo é a integração recusando.
        "em_andamento": linha[2] is None,
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
            "       DATEDIFF(DAY, aberto_em, GETDATE()) AS idade_dias")
        novas = (", tipo_demanda, categoria_diaadia, objetos, demandante, "
                 "  catalogo, prazo, sla_vencido, "
                 "  veredito, suficiencia, resumo, lacunas, perguntas, "
                 "  triagem_origem, triagem_em, triagem_erro, "
                 # Parentesco (migration 090). Vem no bloco DEGRADÁVEL, junto
                 # com as 091/092: num ambiente sem a 090 a fila continua
                 # servida — plana, com a task como card solto, que é como
                 # sempre foi — em vez de virar "sistema em atualização".
                 "  pai_sys_id, pai_numero")
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
                                None, None, "", "", "", None, None, "",
                                # pai_sys_id, pai_numero: sem a 090 não há
                                # parentesco, e a fila serve plana.
                                None, None)
            resposta["chamados"].append({
                "sys_id": r[0], "numero": r[1], "tipo": r[2], "titulo": r[3],
                "estado_origem": r[4], "estado_kanban": r[5],
                "prioridade": r[6], "atribuido_a": r[7], "grupo": r[8],
                "aberto_em": _fmt_dt(r[9]), "atualizado_em": _fmt_dt(r[10]),
                "encerrado_em": _fmt_dt(r[11]), "ativo": bool(r[12]),
                "url": r[13], "sync_em": _fmt_dt(r[14]),
                "idade_dias": r[15] if r[15] is not None else None,
                # Derivadas (migration 092). NULL vira o rótulo explícito: o
                # card não pode ficar sem tipo enquanto o sync não passa.
                "tipo_demanda": r[16] or TIPO_NAO_CLASSIFICADO,
                "categoria_diaadia": r[17] or "",
                "objetos": r[18] or "",
                "demandante": r[19] or "",
                "catalogo": r[20] or "",
                "prazo": _fmt_dt(r[21]),
                # None ≠ 0: "ninguém mediu o SLA" é diferente de "está no
                # prazo", e a tela precisa poder calar sobre o primeiro.
                "sla_vencido": None if r[22] is None else bool(r[22]),
                # ── Triagem (migration 093) ──────────────────────────────
                # `veredito` None = ainda não triado. Diferente de qualquer
                # veredito: a tela não pode pintar de âmbar quem só não foi
                # analisado ainda.
                "veredito": r[23],
                "suficiencia": r[24],
                "resumo": r[25] or "",
                # Lista, não bloco de texto: a tela renderiza uma por linha e
                # não precisa saber como o banco guardou.
                "lacunas": [x for x in (r[26] or "").split("\n") if x.strip()],
                "perguntas": r[27] or "",
                # A coluna que impede o engano: heurística mostrada como
                # análise de IA é veredito em que ninguém pensou.
                "triagem_origem": r[28] or "",
                "triagem_em": _fmt_dt(r[29]),
                "triagem_erro": r[30] or "",
                # ── Parentesco (migration 090) ───────────────────────────
                # Todo RITM do catálogo gera uma sc_task, e as duas chegam
                # aqui como linhas irmãs. É por este campo que a tela sabe
                # que a task já está representada pelo card do pai.
                # String vazia é tratada como ausente: o sync grava '' —
                # e não NULL — quando o campo não vem da API.
                "pai_sys_id": (r[31] or None),
                "pai_numero": (r[32] or None),
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
def indicadores(_auth: dict = Depends(get_current_user)):
    """Agregados para a aba de Indicadores — contas feitas no SQL, não na tela.

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

        # ── aging por faixa (só o que está na fila) ──────────────────────────
        cur.execute(
            "SELECT CASE "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 3 THEN '0-3 dias' "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 7 THEN '4-7 dias' "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 14 THEN '8-14 dias' "
            "  ELSE 'mais de 14 dias' END AS faixa, COUNT(*) "
            "FROM dbo.etl_chamado WHERE ativo = 1 AND aberto_em IS NOT NULL "
            + _so_trabalhos() +
            "GROUP BY CASE "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 3 THEN '0-3 dias' "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 7 THEN '4-7 dias' "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 14 THEN '8-14 dias' "
            "  ELSE 'mais de 14 dias' END")
        contagem = {linha[0]: linha[1] for linha in cur.fetchall()}
        # Faixa sem chamado vem com 0 EXPLÍCITO e na ordem fixa: buraco no
        # gráfico faria "nenhum chamado velho" parecer "não medi isso".
        saida["aging"] = [{"faixa": nome, "total": contagem.get(nome, 0)}
                          for nome, _i, _f in FAIXAS_AGING]

        # ── tipo × estado ───────────────────────────────────────────────────
        cur.execute(
            "SELECT tipo, estado_kanban, COUNT(*) FROM dbo.etl_chamado "
            "WHERE ativo = 1 "
            + _so_trabalhos() +
            "GROUP BY tipo, estado_kanban")
        celulas = [{"tipo": r[0], "estado": r[1], "total": r[2]}
                   for r in cur.fetchall()]
        saida["tipo_estado"] = {
            "tipos": sorted({c["tipo"] for c in celulas}),
            "estados": list(COLUNAS_KANBAN),
            "celulas": celulas,
        }

        # ── entradas × saídas dos últimos 14 dias ───────────────────────────
        cur.execute(
            "SELECT CAST(aberto_em AS DATE), COUNT(*) FROM dbo.etl_chamado "
            "WHERE aberto_em >= DATEADD(DAY, ?, CAST(GETDATE() AS DATE)) "
            + _so_trabalhos() +
            "GROUP BY CAST(aberto_em AS DATE)", [-(DIAS_FLUXO - 1)])
        entradas = {str(r[0])[:10]: r[1] for r in cur.fetchall()}
        cur.execute(
            "SELECT CAST(encerrado_em AS DATE), COUNT(*) FROM dbo.etl_chamado "
            "WHERE encerrado_em >= DATEADD(DAY, ?, CAST(GETDATE() AS DATE)) "
            + _so_trabalhos() +
            "GROUP BY CAST(encerrado_em AS DATE)", [-(DIAS_FLUXO - 1)])
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

        # ── carga por responsável ───────────────────────────────────────────
        cur.execute(
            "SELECT ISNULL(NULLIF(LTRIM(RTRIM(atribuido_a)), ''), 'sem responsável'), "
            "       COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1 "
            + _so_trabalhos() +
            "GROUP BY ISNULL(NULLIF(LTRIM(RTRIM(atribuido_a)), ''), 'sem responsável') "
            "ORDER BY COUNT(*) DESC")
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
            cur.execute(
                "SELECT ISNULL(NULLIF(LTRIM(RTRIM(tipo_demanda)), ''), ?), COUNT(*) "
                "FROM dbo.etl_chamado WHERE ativo = 1 "
                + _so_trabalhos() +
                "GROUP BY ISNULL(NULLIF(LTRIM(RTRIM(tipo_demanda)), ''), ?) "
                "ORDER BY COUNT(*) DESC",
                [TIPO_NAO_CLASSIFICADO, TIPO_NAO_CLASSIFICADO])
            saida["por_tipo_demanda"] = [{"tipo": r[0], "total": r[1]}
                                         for r in cur.fetchall()]

            # ── por categoria "dia a dia" ───────────────────────────────────────
            # Aqui o vazio NÃO vira rótulo: sem marcação é ausência de
            # classificação, não uma categoria. Ele sai como contador à parte,
            # `sem_categoria`, para o denominador continuar visível.
            cur.execute(
                "SELECT LTRIM(RTRIM(categoria_diaadia)), COUNT(*) "
                "FROM dbo.etl_chamado WHERE ativo = 1 "
                + _so_trabalhos() +
                "  AND NULLIF(LTRIM(RTRIM(categoria_diaadia)), '') IS NOT NULL "
                "GROUP BY LTRIM(RTRIM(categoria_diaadia)) ORDER BY COUNT(*) DESC")
            todas = [{"categoria": r[0], "total": r[1]} for r in cur.fetchall()]
            # Corte com o resto DITO, como o gráfico de carga já faz. A categoria
            # é texto livre digitado nas work notes: sem teto, cada erro de
            # digitação vira uma barra permanente e o gráfico cresce sem limite.
            saida["por_categoria"] = todas[:TOPO_CATEGORIAS]
            saida["categorias_ocultas"] = max(0, len(todas) - TOPO_CATEGORIAS)
            cur.execute(
                "SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1 "
                + _so_trabalhos() +
                "  AND NULLIF(LTRIM(RTRIM(categoria_diaadia)), '') IS NULL")
            saida["sem_categoria"] = cur.fetchone()[0]

            # ── resolvidos da janela do histórico ───────────────────────────────
            cur.execute(
                "SELECT COUNT(*) FROM dbo.etl_chamado "
                "WHERE encerrado_em >= DATEADD(DAY, ?, CAST(GETDATE() AS DATE)) "
                + _so_trabalhos(),
                [-(DIAS_HISTORICO - 1)])
            saida["resolvidos_periodo"] = cur.fetchone()[0]

            # ── triagem: veredito × origem ──────────────────────────────────────
            # As duas dimensões juntas, porque separadas mentem: "18 podem
            # iniciar" soa como análise feita, quando pode ser a heurística
            # respondendo por todos com o gateway fora do ar há dias.
            cur.execute(
                "SELECT ISNULL(veredito, 'não triado'), ISNULL(triagem_origem, ''), "
                "       COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1 "
                + _so_trabalhos() +
                "GROUP BY ISNULL(veredito, 'não triado'), ISNULL(triagem_origem, '')")
            saida["triagem"] = [{"veredito": r[0], "origem": r[1], "total": r[2]}
                                for r in cur.fetchall()]
            # Quantos laudos registraram falha da IA — é o sinal de gateway doente
            # que, sem esta conta, ficaria escondido num campo por chamado.
            # Dois contadores, e não um: "ninguém configurou a chave" e "o gateway
            # está doente" produzem o mesmo veredito heurístico, e um número só
            # mandaria o operador investigar rede quando faltava preencher campo.
            cur.execute(
                "SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1 "
                + _so_trabalhos() +
                "  AND triagem_erro LIKE 'falha:%'")
            saida["triagem_com_erro"] = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1 "
                + _so_trabalhos() +
                "  AND triagem_erro LIKE 'config:%'")
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

        cur.execute("SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1"
                    + _so_trabalhos())
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
            + _so_trabalhos() +
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
            + _so_trabalhos() +
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


# IMPORTANTE: esta rota tem DOIS segmentos (`/chamados/<algo>/tasks`), então
# não disputa com `/chamados/indicadores`, `/chamados/sugestoes` nem
# `/chamados/historico`, que têm um só. A disputa apareceria no dia em que
# entrar uma rota de dois segmentos começando por literal — `/chamados/
# indicadores/historico` é o caso conhecido: ali `indicadores` casaria com
# `{sys_id}` e `historico` com `tasks`. Quando essa rota vier, ela precisa ser
# declarada ANTES desta.
@router.get("/chamados/{sys_id}/tasks", tags=["chamados"])
def tasks_do_ritm(sys_id: str, _auth: dict = Depends(get_current_user)):
    """As SCTASKs de um RITM — o trabalho que o card do pai representa.

    Inclui INATIVAS de propósito: a fila mostra o pedido vivo, mas quem abre um
    RITM quer ver a execução inteira, inclusive a task já encerrada. Filtrar
    aqui esconderia metade da história de quem foi ao card justamente para
    entendê-la.
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
        # Sem a migration 090 não existe `pai_sys_id` e a consulta falha. A
        # tela precisa saber disso para não anunciar "nenhuma tarefa" — que
        # seria uma afirmação, e falsa — quando o que houve foi ausência de
        # coluna.
        log.warning("tasks_do_ritm: espelho indisponível (%s: %s)",
                    type(e).__name__, e)
        saida["migration_ausente"] = True
    return saida
