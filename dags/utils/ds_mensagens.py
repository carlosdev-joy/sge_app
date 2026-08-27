"""
dags/utils/ds_mensagens.py — mensagens configuráveis dos alertas da supervisão.

Cada tipo de alerta tem texto próprio, porque um job liga até quatro alertas
diferentes e uma frase única não explica os quatro casos: "abortou" e "não
iniciou até 03:15, com tolerância de 15 min" não cabem no mesmo texto.

O usuário escreve a mensagem com variáveis entre chaves — {janela_inicio},
{tolerancia}, {inicio} — e a coleta as substitui pelo contexto real do dia.
Quando não há mensagem cadastrada, vale o padrão daqui.

Interpolação TOLERANTE: variável desconhecida fica intacta no texto, no mesmo
espírito do `_notif_interpola` do etl_dag_factory. Mensagem de alerta com erro
de digitação ainda tem de ser enviada — chegar torta é melhor que não chegar.

ESPELHO: `api/routers/ds_supervisao.py` repete este catálogo para exibir as
variáveis na tela de cadastro (a API não importa de dags/). A paridade entre os
dois é travada por teste — tests/test_ds_mensagens.py.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from utils.ds_logsum import DsRun
from utils.ds_supervisao_regras import (
    ABORTOU, ATRASO, ESTRUTURA, FILHO_AUSENTE, NAO_EXECUTOU, SITUACAO_INICIAL,
    SUCESSO_FALSO, JobSupervisionado, descrever_dia, dias_ativos, janela_do_dia,
)

_NOMES_DIA = {1: "seg", 2: "ter", 3: "qua", 4: "qui", 5: "sex", 6: "sáb", 7: "dom"}

# (nome, descrição para a tela, exemplo). A ordem é a que aparece no cadastro.
VARIAVEIS: list[tuple[str, str, str]] = [
    ("projeto",       "Projeto do DataStage",                      "BI_CVP"),
    ("job",           "Nome do job / sequence",                    "SeqSsdVida7Peps"),
    ("descricao",     "Descrição cadastrada do job",               "Carga diária de vida"),
    ("tipo",          "Tipo do alerta",                            "ATRASO"),
    ("data",          "Dia a que o alerta se refere",              "2026-07-29"),
    ("janela_inicio", "Início da janela esperada",                 "02:00"),
    ("janela_fim",    "Fim da janela esperada",                    "03:00"),
    ("tolerancia",    "Tolerância configurada, em minutos",        "15"),
    ("limite",        "Horário limite (fim da janela + tolerância)", "03:15"),
    ("dias",          "Dias da semana supervisionados",            "seg, ter, qua, qui, sex"),
    ("inicio",        "Início da execução observada",              "02:10"),
    ("fim",           "Término da execução observada",             "02:50"),
    ("duracao",       "Duração da execução observada",             "40 min"),
    ("situacao",      "Frase automática com a situação do dia",    "não iniciou até 03:15"),
    ("total_filhos",     "Quantos jobs rodaram abaixo do supervisionado", "12"),
    ("filhos_falharam",  "Jobs abaixo que abortaram",                 "CargaVida, CargaPrev"),
    ("filhos_ausentes",  "Jobs esperados que não rodaram",            "CargaMensal"),
    ("filhos_ok",        "Jobs abaixo que concluíram",                "CargaA, CargaB"),
]

NOMES_VARIAVEIS = [v[0] for v in VARIAVEIS]

# Texto usado quando o job não tem mensagem cadastrada para o tipo.
MENSAGENS_PADRAO: dict[str, str] = {
    ABORTOU: (
        "🚨 {job} ({projeto}) abortou em {data}.\n"
        "Início {inicio}, parada {fim}. {situacao}"),
    NAO_EXECUTOU: (
        "🚨 {job} ({projeto}) não executou em {data}.\n"
        "Janela esperada: {janela_inicio}–{janela_fim} ({dias})."),
    ATRASO: (
        "⏰ {job} ({projeto}) não iniciou até {limite} em {data}.\n"
        "Janela {janela_inicio}–{janela_fim} com tolerância de {tolerancia} min."),
    ESTRUTURA: (
        "⚠️ Não foi possível verificar {job} ({projeto}) em {data}.\n{situacao}"),
    SITUACAO_INICIAL: (
        "✅ Monitoramento iniciado para {job} ({projeto}).\n"
        "Janela {janela_inicio}–{janela_fim} ({dias}), tolerância de {tolerancia} min.\n"
        "{situacao}"),
    # O DataStage deu a sequence como concluída — o alerta existe porque ela
    # não foi concluída de verdade.
    SUCESSO_FALSO: (
        "🚨 {job} ({projeto}) foi reportado como CONCLUÍDO em {data}, "
        "mas jobs abaixo dele abortaram.\n"
        "Abortados: {filhos_falharam}.\n"
        "Execução {inicio} → {fim} · {total_filhos} job(s) no fluxo."),
    FILHO_AUSENTE: (
        "⚠️ {job} ({projeto}) rodou em {data} sem jobs que costumam fazer "
        "parte do fluxo.\n"
        "Não executaram: {filhos_ausentes}.\n"
        "Execução {inicio} → {fim} · {total_filhos} job(s) no fluxo."),
}

_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")


def _hm(momento) -> str:
    if isinstance(momento, (datetime,)):
        return momento.strftime("%H:%M")
    return "—"


def _duracao(segundos) -> str:
    if segundos is None:
        return "—"
    horas, resto = divmod(int(segundos), 3600)
    minutos = resto // 60
    return f"{horas}h{minutos:02d}m" if horas else f"{minutos} min"


def _lista(nomes) -> str:
    """['A','B'] → 'A, B'. Vazio vira travessão, para o texto não ficar truncado."""
    return ", ".join(nomes) if nomes else "—"


def montar_contexto(job: JobSupervisionado, tipo: str, data_ref: date,
                    runs: list[DsRun], agora: datetime,
                    situacao: str | None = None,
                    run: DsRun | None = None,
                    estrutura=None) -> dict[str, str]:
    """Valores das variáveis para um alerta específico.

    `run` é a execução que originou o alerta (o abort, por exemplo). Sem ele,
    usa a última execução observada no dia — e, se não houve nenhuma, os campos
    de horário viram travessão em vez de sumir do texto."""
    from utils.ds_estrutura import Estrutura, resumo_dependencia

    inicio_janela, fim_janela, limite = janela_do_dia(job, data_ref)
    alvo = run
    if alvo is None:
        do_dia = [r for r in runs if r.inicio is not None]
        alvo = do_dia[-1] if do_dia else None

    # Variáveis da análise de dependência (jobs abaixo do supervisionado).
    dep = resumo_dependencia(alvo, estrutura or Estrutura()) if alvo else {
        "total_filhos": 0, "filhos_ok": [], "filhos_falharam": [], "filhos_ausentes": [],
    }

    return {
        "total_filhos":    str(dep["total_filhos"]),
        "filhos_ok":       _lista(dep["filhos_ok"]),
        "filhos_falharam": _lista(dep["filhos_falharam"]),
        "filhos_ausentes": _lista(dep["filhos_ausentes"]),
        "projeto":       job.project,
        "job":           job.job_name,
        "descricao":     job.descricao or job.rotulo,
        "tipo":          tipo,
        "data":          data_ref.isoformat(),
        "janela_inicio": _hm(inicio_janela),
        "janela_fim":    _hm(fim_janela),
        "tolerancia":    str(job.tolerancia_min),
        "limite":        _hm(limite),
        "dias":          ", ".join(_NOMES_DIA[d] for d in sorted(dias_ativos(job.dias_semana))) or "—",
        "inicio":        _hm(alvo.inicio) if alvo else "—",
        "fim":           _hm(alvo.fim) if alvo else "—",
        "duracao":       _duracao(alvo.duracao_seg) if alvo else "—",
        "situacao":      situacao if situacao is not None else descrever_dia(job, data_ref, runs, agora),
    }


def interpolar(texto: str, contexto: dict[str, str]) -> str:
    """Substitui {variavel} pelos valores do contexto.

    Variável desconhecida permanece literal — erro de digitação não pode
    impedir o alerta de sair, e o texto torto mostra ao usuário o que corrigir.
    """
    if not texto:
        return ""

    def troca(m: re.Match) -> str:
        chave = m.group(1)
        return str(contexto.get(chave, m.group(0)))

    return _PLACEHOLDER_RE.sub(troca, texto)


def montar_mensagem(job: JobSupervisionado, tipo: str, data_ref: date,
                    runs: list[DsRun], agora: datetime,
                    mensagens: dict[str, str] | None = None,
                    situacao: str | None = None,
                    run: DsRun | None = None, estrutura=None) -> str:
    """Mensagem final de um alerta: a cadastrada para o tipo, ou o padrão."""
    cadastrada = (mensagens or {}).get(tipo)
    modelo = cadastrada.strip() if cadastrada and cadastrada.strip() else MENSAGENS_PADRAO.get(tipo, "{situacao}")
    return interpolar(modelo, montar_contexto(job, tipo, data_ref, runs, agora,
                                              situacao, run, estrutura))


def variaveis_desconhecidas(texto: str) -> list[str]:
    """Variáveis citadas no texto que não existem no catálogo.

    Serve para a tela avisar antes de salvar — depois de enviado, o placeholder
    literal no canal do Teams já é tarde."""
    return sorted({m for m in _PLACEHOLDER_RE.findall(texto or "")
                   if m not in NOMES_VARIAVEIS})
