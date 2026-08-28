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

from fastapi import APIRouter, Depends, HTTPException

from db import get_db_conn
from deps import get_admin_user, get_current_user

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

# O balde de quem não tem ninguém. Precisa de nome próprio porque a tela o
# oferece no seletor: "sem responsável" é o que o gestor procura primeiro
# quando abre a análise, e um seletor que não o ofereça esconde o problema.
SEM_RESPONSAVEL = "sem responsável"

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
# O fim da janela dos "próximos dias": a PRÓXIMA sexta-feira, sempre à frente.
#
# ⚠️ DOIS DEFEITOS MORARAM AQUI, e os dois davam número plausível:
#
# 1. `DATEADD(DAY, 6-DATEPART(WEEKDAY, GETDATE()), …)` devolvia HOJE quando
#    hoje era sexta. O balde é `prazo > hoje AND prazo <= fim`, então virava
#    condição IMPOSSÍVEL: toda sexta-feira o cartão zerava, e os chamados que
#    venciam na semana seguinte não apareciam em cartão nenhum. Medido em
#    2026-08-28 (uma sexta): 14 venciam hoje, 16 depois, e o cartão dizia 0.
#    A spec de origem tinha a proteção — o `|| 7` do JavaScript — e ela se
#    perdeu na tradução para SQL.
# 2. `DATEPART(WEEKDAY)` depende de `SET DATEFIRST`, que varia por sessão e
#    por idioma do login. A mesma consulta daria janelas diferentes conforme
#    quem conecta. `DATEDIFF(DAY, 0, data) % 7` não depende de configuração
#    nenhuma: o dia 0 do SQL Server (1900-01-01) foi uma SEGUNDA-feira, então
#    0=segunda … 4=sexta … 6=domingo, sempre.
def _proxima_sexta() -> str:
    """Expressão SQL: a próxima sexta-feira, nunca hoje."""
    idx = "DATEDIFF(DAY, 0, GETDATE()) % 7"          # 0=segunda … 4=sexta
    dias = f"((4 - ({idx}) + 7) % 7)"
    # 0 significa "hoje é sexta" — e aí a janela vai para a sexta seguinte,
    # senão o cartão nasce vazio no dia em que ele mais importa.
    return (f"DATEADD(DAY, CASE WHEN {dias} = 0 THEN 7 ELSE {dias} END, "
            f"CAST(GETDATE() AS DATE))")


def _filtro_responsavel(nome: str | None) -> tuple[str, list]:
    """Recorte por responsável — o filtro único da aba de Indicadores.

    Vale para TODAS as agregações da aba, e é por isso que devolve o par
    (sql, params) em vez de cada consulta montar o seu: filtro que alcança
    metade das contas produz uma aba onde o aging fala de uma pessoa e o
    fluxo de todas — com os dois números parecendo certos.

    O `?` entra sempre no FIM do WHERE. As três consultas que já têm parâmetro
    o usam antes, na janela de dias, então a ordem posicional do pyodbc
    continua correta.
    """
    alvo = (nome or "").strip()
    if not alvo:
        return "", []
    if alvo == SEM_RESPONSAVEL:
        # Sem `?`: é uma condição, não um valor. Comparar com a string
        # "sem responsável" não acharia ninguém — ela é rótulo da tela, e o
        # banco guarda NULL ou vazio.
        return " AND NULLIF(LTRIM(RTRIM(atribuido_a)), '') IS NULL ", []
    return " AND atribuido_a = ? ", [alvo]


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
def indicadores(responsavel: str | None = None,
                _auth: dict = Depends(get_current_user)):
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
        # O filtro em vigor e as opções — a tela precisa dos dois para desenhar
        # o seletor e para DIZER que está filtrando: número filtrado sem aviso
        # é a mesma armadilha do total que não bate com a lista.
        "responsavel": (responsavel or "").strip() or None, "responsaveis": [],
        # Denominador do aging: ativos que ainda NÃO foram resolvidos.
        "total_em_fila": 0,
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
    # O filtro vale para TODAS as contas desta aba — ver `_filtro_responsavel`.
    _fr, _frp = _filtro_responsavel(responsavel)
    saida["responsavel"] = (responsavel or "").strip() or None

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
            # ⚠️ Chamado RESOLVIDO sai do aging.
            #
            # A pergunta aqui é "tem coisa velha parada?", e ela existe para
            # priorizar. Um chamado resolvido há 40 dias não está parado —
            # está pronto. Contá-lo enchia a faixa "mais de 14 dias" com
            # trabalho FEITO, e a barra mais alarmante do painel passava a
            # medir justamente o que ninguém precisa olhar.
            "  AND estado_kanban NOT IN ('resolvido','encerrado') "
            + _so_trabalhos() + _fr +
            "GROUP BY CASE "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 3 THEN '0-3 dias' "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 7 THEN '4-7 dias' "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 14 THEN '8-14 dias' "
            "  ELSE 'mais de 14 dias' END", _frp)
        contagem = {linha[0]: linha[1] for linha in cur.fetchall()}
        # O denominador do "x de y" do aging é o MESMO recorte do numerador.
        # Com `total_ativos` (que inclui os resolvidos), "8 de 56" seria oito
        # velhos sobre uma fila que ele não mediu — e a soma das faixas não
        # fecharia com o total ao lado.
        saida["total_em_fila"] = sum(contagem.values())
        # Faixa sem chamado vem com 0 EXPLÍCITO e na ordem fixa: buraco no
        # gráfico faria "nenhum chamado velho" parecer "não medi isso".
        saida["aging"] = [{"faixa": nome, "total": contagem.get(nome, 0)}
                          for nome, _i, _f in FAIXAS_AGING]

        # ── tipo × estado ───────────────────────────────────────────────────
        cur.execute(
            "SELECT tipo, estado_kanban, COUNT(*) FROM dbo.etl_chamado "
            "WHERE ativo = 1 "
            + _so_trabalhos() + _fr +
            "GROUP BY tipo, estado_kanban", _frp)
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
            + _so_trabalhos() + _fr +
            "GROUP BY CAST(aberto_em AS DATE)", [-(DIAS_FLUXO - 1)] + _frp)
        entradas = {str(r[0])[:10]: r[1] for r in cur.fetchall()}
        cur.execute(
            "SELECT CAST(encerrado_em AS DATE), COUNT(*) FROM dbo.etl_chamado "
            "WHERE encerrado_em >= DATEADD(DAY, ?, CAST(GETDATE() AS DATE)) "
            + _so_trabalhos() + _fr +
            "GROUP BY CAST(encerrado_em AS DATE)", [-(DIAS_FLUXO - 1)] + _frp)
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
            + _so_trabalhos() + _fr +
            "GROUP BY ISNULL(NULLIF(LTRIM(RTRIM(atribuido_a)), ''), 'sem responsável') "
            "ORDER BY COUNT(*) DESC", _frp)
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
            # ⚠️ O rótulo do vazio é aplicado no PYTHON, não no SQL.
            #
            # A versão anterior fazia `GROUP BY ISNULL(expr, ?)` — com
            # PARÂMETRO dentro do GROUP BY. O SQL Server recusa: o valor não é
            # conhecido em tempo de compilação, então a expressão do GROUP BY
            # não é reconhecida como a mesma do SELECT, e a consulta morre com
            # "Column 'tipo_demanda' is invalid in the select list because it
            # is not contained in either an aggregate function or the GROUP BY
            # clause".
            #
            # O estrago era mudo: a exceção caía no `except` deste bloco
            # inteiro, e a resposta seguia "servindo o painel base". Os chips
            # de tipo, categoria, sem_categoria, resolvidos do período e os
            # três da triagem simplesmente não apareciam — sem erro na tela,
            # sem número errado, sem nada. Só o log sabia.
            #
            # Descoberto em 2026-08-28 rodando contra o banco do dev: os
            # testes com cursor dublê não executam SQL, e por isso passavam.
            cur.execute(
                "SELECT NULLIF(LTRIM(RTRIM(tipo_demanda)), ''), COUNT(*) "
                "FROM dbo.etl_chamado WHERE ativo = 1 "
                + _so_trabalhos() + _fr +
                "GROUP BY NULLIF(LTRIM(RTRIM(tipo_demanda)), '') "
                "ORDER BY COUNT(*) DESC", _frp)
            saida["por_tipo_demanda"] = [
                {"tipo": r[0] or TIPO_NAO_CLASSIFICADO, "total": r[1]}
                for r in cur.fetchall()]

            # ── por categoria "dia a dia" ───────────────────────────────────────
            # Aqui o vazio NÃO vira rótulo: sem marcação é ausência de
            # classificação, não uma categoria. Ele sai como contador à parte,
            # `sem_categoria`, para o denominador continuar visível.
            cur.execute(
                "SELECT LTRIM(RTRIM(categoria_diaadia)), COUNT(*) "
                "FROM dbo.etl_chamado WHERE ativo = 1 "
                + _so_trabalhos() + _fr +
                "  AND NULLIF(LTRIM(RTRIM(categoria_diaadia)), '') IS NOT NULL "
                "GROUP BY LTRIM(RTRIM(categoria_diaadia)) ORDER BY COUNT(*) DESC", _frp)
            todas = [{"categoria": r[0], "total": r[1]} for r in cur.fetchall()]
            # Corte com o resto DITO, como o gráfico de carga já faz. A categoria
            # é texto livre digitado nas work notes: sem teto, cada erro de
            # digitação vira uma barra permanente e o gráfico cresce sem limite.
            saida["por_categoria"] = todas[:TOPO_CATEGORIAS]
            saida["categorias_ocultas"] = max(0, len(todas) - TOPO_CATEGORIAS)
            cur.execute(
                "SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1 "
                + _so_trabalhos() + _fr +
                "  AND NULLIF(LTRIM(RTRIM(categoria_diaadia)), '') IS NULL", _frp)
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
                + _so_trabalhos() + _fr +
                "GROUP BY ISNULL(veredito, 'não triado'), ISNULL(triagem_origem, '')", _frp)
            saida["triagem"] = [{"veredito": r[0], "origem": r[1], "total": r[2]}
                                for r in cur.fetchall()]
            # Quantos laudos registraram falha da IA — é o sinal de gateway doente
            # que, sem esta conta, ficaria escondido num campo por chamado.
            # Dois contadores, e não um: "ninguém configurou a chave" e "o gateway
            # está doente" produzem o mesmo veredito heurístico, e um número só
            # mandaria o operador investigar rede quando faltava preencher campo.
            cur.execute(
                "SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1 "
                + _so_trabalhos() + _fr +
                "  AND triagem_erro LIKE 'falha:%'", _frp)
            saida["triagem_com_erro"] = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1 "
                + _so_trabalhos() + _fr +
                "  AND triagem_erro LIKE 'config:%'", _frp)
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

        # `total_ativos` é o denominador de todos os "x de y" desta aba, e por
        # isso acompanha o filtro: sem ele, filtrar por uma pessoa mostraria
        # "3 de 57" — três dela sobre a fila inteira, uma fração que não
        # significa nada.
        cur.execute("SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1"
                    + _so_trabalhos() + _fr, _frp)
        saida["total_ativos"] = cur.fetchone()[0]

        # ── as opções do seletor ─────────────────────────────────────────────
        # ⚠️ SEM o filtro aplicado (`_fr` fica de fora de propósito). Com ele,
        # escolher uma pessoa deixaria o seletor com uma opção só e não haveria
        # como voltar nem trocar: a tela prenderia quem analisa na escolha que
        # acabou de fazer.
        #
        # O total de cada um vem junto — quem vai analisar escolhe melhor
        # vendo "Fulano (12)" do que uma lista de nomes soltos.
        # O rótulo do vazio é aplicado no PYTHON. `GROUP BY ISNULL(expr, ?)`
        # é recusado pelo SQL Server — o mesmo defeito que derrubava o bloco
        # de tipo de demanda em silêncio, e que o anti-drift
        # `test_nenhuma_query_usa_parametro_no_group_by` pegou aqui também.
        cur.execute(
            "SELECT NULLIF(LTRIM(RTRIM(atribuido_a)), ''), COUNT(*) "
            "FROM dbo.etl_chamado WHERE ativo = 1"
            + _so_trabalhos() +
            "GROUP BY NULLIF(LTRIM(RTRIM(atribuido_a)), '') "
            "ORDER BY COUNT(*) DESC")
        saida["responsaveis"] = [{"nome": r[0] or SEM_RESPONSAVEL, "total": r[1]}
                                 for r in cur.fetchall()]

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


# ═══════════════════════════════════════════════════════════════════════════
# Leitura — dashboard, histórico de indicadores e catálogo de categorias.
#
# ⚠️ ORDEM IMPORTA. `/chamados/indicadores/historico` tem DOIS segmentos e
# precisa ser declarada ANTES de `/chamados/{sys_id}/...`: o FastAPI casa na
# ordem, e ali `indicadores` casaria com `{sys_id}` e `historico` com o
# segmento final. A rota responderia 200 com o corpo errado — sem erro
# nenhum para avisar.
# ═══════════════════════════════════════════════════════════════════════════

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
        "prazo, aberto_em, url, sla_vencido, tipo_demanda, atribuido_a_email, "
        # As duas datas do fim, porque elas NÃO são a mesma coisa.
        #
        # No ServiceNow, "Resolvido" ainda não é "Encerrado": `closed_at` — o
        # nosso `encerrado_em` — só é preenchido no encerramento definitivo.
        # Medido no dev: dos 21 resolvidos ativos, ZERO tinham `encerrado_em`.
        # Mostrar só ele deixaria a coluna de datas vazia justamente no cartão
        # que o gestor quer conferir.
        #
        # `atualizado_em` é a data da última mudança — para um chamado
        # resolvido, é quando ele foi resolvido, salvo comentário posterior.
        # A tela recebe as DUAS e diz qual está mostrando; escolher uma e
        # chamá-la de "resolvido em" afirmaria uma data que pode não ser.
        "encerrado_em, atualizado_em"
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
                "encerrado_em": _fmt_dt(r[11]),
                "atualizado_em": _fmt_dt(r[12]),
            }
            for r in cur.fetchall()
        ]

    # O MESMO recorte do resto do módulo. Produção usa `tipo != 'task'`, que
    # descarta TODA tarefa — inclusive a ÓRFÃ, que a fila mostra como card.
    # Com os dois convivendo, no dia em que aparecer uma órfã o dashboard diria
    # um número e a tela ao lado outro, e os dois pareceriam certos.
    _BASE = "FROM dbo.etl_chamado WHERE ativo=1" + _so_trabalhos()

    grupos = {
        "backlog":           ("backlog",           "Demandas Backlog",         "amber"),
        "abertas":           ("abertas",           "Abertas",                  "amber"),
        "resolvidas_hoje":   ("resolvidas_hoje",   "Resolvidas hoje",          "green"),
        "andamento":         ("andamento",         "Em Andamento",             "indigo"),
        "pendentes":         ("pendentes",         "Pendentes",                "neutral"),
        "sem_analista":      ("sem_analista",      "Backlog Sem Analista",     "amber"),
        "resolvidas":        ("resolvidas",        "Resolvidas",               "green"),
        "vencem_hoje":       ("vencem_hoje",       "Vencem Hoje",              "red"),
        # "essa semana" mentia duas vezes: o cartão EXCLUI hoje (que tem cartão
        # próprio ao lado, e somar os dois contaria o mesmo chamado duas vezes)
        # e, quando hoje é sexta, a janela é a semana QUE VEM. "Próximos dias"
        # é o que o cartão realmente mostra, em qualquer dia da semana.
        "vencem_semana":     ("vencem_semana",     "Vencem nos próximos dias", "orange"),
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
            f"SELECT {_COLS} FROM dbo.etl_chamado WHERE 1=1"
            + _so_trabalhos()
            + f"  AND estado_kanban IN ('resolvido','encerrado')"
            f"  AND CAST(encerrado_em AS DATE) = CAST(GETDATE() AS DATE){_filtro}"
            "  ORDER BY encerrado_em DESC", _p)
        saida["resolvidas_hoje"]["chamados"] = _rows(cur)
        saida["resolvidas_hoje"]["total"] = len(saida["resolvidas_hoje"]["chamados"])

        # ── resolvidas: estado resolvido ainda ativo ─────────────────────────
        # Do mais RECENTE: o cartão responde "o que a equipe entregou", e a
        # leitura natural é começar pelo que acabou de sair. Por `aberto_em`,
        # o topo da lista era o chamado mais ANTIGO — que costuma ser o que
        # menos ajuda a validar o número.
        #
        # Ordena pela data que EXISTE: `encerrado_em` quando houver, senão a
        # última atualização. Ordenar só por `encerrado_em` colocaria os 21
        # resolvidos — todos sem essa data — numa ordem arbitrária.
        cur.execute(
            f"SELECT {_COLS} {_BASE}"
            f"  AND estado_kanban='resolvido'{_filtro}"
            "  ORDER BY COALESCE(encerrado_em, atualizado_em) DESC", _p)
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

        # ── vencem nos próximos dias (amanhã até a próxima sexta) ───────────
        cur.execute(
            f"SELECT {_COLS} {_BASE}"
            f"  AND estado_kanban NOT IN ('resolvido','encerrado','outros')"
            f"  AND prazo IS NOT NULL"
            f"  AND CAST(prazo AS DATE) > CAST(GETDATE() AS DATE)"
            f"  AND CAST(prazo AS DATE) <= {_proxima_sexta()}{_filtro}"
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
            + " WHERE 1=1"
            + _so_trabalhos()
            + f"  AND CAST(aberto_em AS DATE) = CAST(GETDATE() AS DATE){_filtro}", _p)
        entradas = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM dbo.etl_chamado"
            + " WHERE 1=1"
            + _so_trabalhos()
            + f"  AND estado_kanban IN ('resolvido','encerrado')"
            + f"  AND CAST(encerrado_em AS DATE) = CAST(GETDATE() AS DATE){_filtro}", _p)
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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chamados/categorias", tags=["chamados"])
def listar_categorias(_auth: dict = Depends(get_current_user)):
    """Categorias ativas para classificação de chamados (ex.: dia a dia, iniciativa).

    Devolve ENVELOPE, e não a lista pura como a versão de produção: sem
    `migration_ausente`, "a consulta falhou" e "não há categoria cadastrada"
    chegam à tela como o mesmo `[]` — e o operador conclui a segunda coisa.
    É o mesmo contrato das outras rotas deste módulo.
    """
    saida: dict = {"categorias": [], "migration_ausente": False}
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT id, slug, label, descricao, padrao "
            "FROM dbo.etl_sn_categoria "
            "ORDER BY padrao DESC, label")
        saida["categorias"] = [
            {"id": r[0], "slug": r[1], "label": r[2],
             "descricao": r[3] or "", "padrao": bool(r[4])}
            for r in cur.fetchall()]
        cur.close(); conn.close()
    except Exception as e:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        log.warning("categorias: indisponível (%s: %s)", type(e).__name__, e)
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
            raise HTTPException(status_code=404, detail="chamado não encontrado")

        chamado = {
            "sys_id": row[0], "numero": row[1], "tipo": row[2],
            "titulo": row[3], "descricao": row[4], "estado_kanban": row[5],
            "atribuido_a": row[6], "atribuido_a_email": row[7], "grupo": row[8],
            "aberto_em": str(row[9]) if row[9] else None, "url": row[10],
            "tem_anexo": bool(row[11]), "sla_vencido": bool(row[12]),
            "prazo": str(row[13]) if row[13] else None,
        }

        # Notas e anexos degradam SEPARADO do chamado.
        #
        # Eles vivem em tabelas que chegaram depois (094/095). Num ambiente que
        # subiu a API nova antes das migrations — que é o intervalo NORMAL do
        # deploy, entre a etapa 6c e o rebuild — um try único derrubaria o
        # detalhe INTEIRO, inclusive o que já funcionava. A tela perderia o
        # chamado por causa de uma lista vazia.
        #
        # `migration_ausente` diz qual das duas coisas aconteceu: sem ela, "não
        # há nota" e "não consegui ler as notas" chegam iguais, e quem lê
        # conclui a primeira.
        notas, anexos, faltando = [], [], False
        try:
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
        except Exception as e:
            log.warning("detalhe: notas indisponíveis (%s: %s)",
                        type(e).__name__, e)
            faltando = True
            cur.close(); cur = conn.cursor()

        try:
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
        except Exception as e:
            log.warning("detalhe: anexos indisponíveis (%s: %s)",
                        type(e).__name__, e)
            faltando = True

        cur.close(); conn.close()
        return {"chamado": chamado, "notas": notas, "anexos": anexos,
                "migration_ausente": faltando}
    except HTTPException:
        raise
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        # Espelho indisponível AVISA, como no resto do módulo. 500 aqui daria
        # tela branca em cima de um chamado que o operador acabou de clicar, e
        # ele não teria como saber se o problema é o chamado ou o sistema.
        # (O 404 de "chamado não existe" sobe pelo `except HTTPException`
        # acima — aquilo é resposta, não falha.)
        log.warning("chamado_detalhe: espelho indisponível (%s: %s)",
                    type(e).__name__, e)
        return {"chamado": None, "notas": [], "anexos": [],
                "migration_ausente": True}


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
            raise HTTPException(status_code=404, detail="anexo não encontrado")
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
                raise HTTPException(status_code=502,
                                     detail=f"ServiceNow indisponível: {e}")

        headers = {}
        mime = mime_type or sn_resp.headers.get("content-type", "application/octet-stream")
        if not mime.startswith("image/"):
            nome_safe = (nome_arquivo or "arquivo").replace('"', '')
            headers["Content-Disposition"] = f'attachment; filename="{nome_safe}"'

        return _StreamingResponse(
            iter([sn_resp.content]), media_type=mime, headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        if conn is not None:
            try: conn.close()
            except Exception: pass
        log.warning("chamado_anexo_proxy: erro (%s: %s)", type(e).__name__, e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Admin ServiceNow ──────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════════════════
# Admin do módulo ServiceNow — grupos, ciclos, categorias e perfis de acesso.
#
# ⚠️ TODAS exigem `acao_admin` (`Depends(get_admin_user)`), e isso é uma
# MUDANÇA em relação ao que roda em produção, onde as dez rotas de
# /admin/servicenow/* pedem apenas autenticação: hoje, lá, qualquer usuário
# logado lê e GRAVA a configuração da integração, edita grupos, salva os
# perfis de acesso e dispara o delta. `tests/test_chamados_admin_rbac.py`
# chama cada uma sem a permissão e exige 403 — sem esse teste a proteção volta
# a cair no próximo refactor, em silêncio.
#
# ⚠️ NÃO foram portadas três rotas que produção tem aqui, porque a `main` já
# tem equivalente melhor e duplicar criaria duas verdades:
#   • GET  /admin/servicenow/config  → já existe em `routers/admin.py`;
#   • PUT  /admin/servicenow/config  → a ação `servicenow_set` (POST /admin)
#     faz o mesmo E grava `proxy` e `grupos`, que a versão de produção
#     DESCARTA em silêncio (ela filtra o payload por uma lista de 4 campos e
#     responde {"ok": true} sem gravar os outros dois);
#   • POST /admin/servicenow/testar  → a sonda de diagnóstico da #300 é mais
#     completa e já está no Admin.
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/admin/servicenow/categorias", tags=["admin"])
def criar_categoria(body: dict, _admin: dict = Depends(get_admin_user)):
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
def excluir_categoria(cat_id: int, _admin: dict = Depends(get_admin_user)):
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


@router.get("/admin/servicenow/grupos", tags=["admin"])
def admin_sn_grupos(_admin: dict = Depends(get_admin_user)):
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
def admin_sn_grupo_criar(payload: dict, _admin: dict = Depends(get_admin_user)):
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
                          _admin: dict = Depends(get_admin_user)):
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
def admin_sn_ciclos(_admin: dict = Depends(get_admin_user)):
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
def admin_sn_disparar_delta(_admin: dict = Depends(get_admin_user)):
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
def admin_sn_perfis(_admin: dict = Depends(get_admin_user)):
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
def admin_sn_perfis_salvar(payload: dict, _admin: dict = Depends(get_admin_user)):
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
