"""
dags/utils/ds_estrutura.py — análise de dependência dos jobs filhos.

O PROBLEMA (caso real de produção): uma sequence monitorada termina com
"Finished OK" mesmo tendo um job filho ABORTADO. O DataStage não propaga a
falha do filho para o pai, então o acompanhamento diário dá o dia como bom e o
abort passa despercebido — exatamente o que a supervisão existe para evitar.

A SOLUÇÃO: aprender, das execuções que terminaram bem, quais jobs rodam abaixo
do job supervisionado; e depois conferir cada execução contra essa lista.
Sucesso REAL = a sequence terminou OK **e** nenhum filho abortou.

Duas decisões que moram aqui:

  • **Frequência, não presença.** Um filho só é cobrado como ausente se aparece
    em quase todas as execuções aprendidas. Sem isso, job condicional — o que
    roda só no dia 1º, ou só quando há arquivo — geraria alerta todo dia.
  • **Amostra mínima antes de cobrar.** Nos primeiros dias a estrutura ainda
    está sendo montada; cobrar ausência aí seria alarme sobre um mapa incompleto.

Módulo PURO: sem SSH, sem banco.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from utils.ds_logsum import OK, DsRun

# Códigos de status do DataStage para jobs filhos.
SUCESSO          = 1
COM_AVISOS       = 2
ABORTADO_FILHO   = 3
VALIDACAO_FALHOU = 13
CRASH            = 96
PARADO           = 97
SEM_STATUS       = -1

# O que dispara alerta de sucesso falso. Por decisão do usuário, SÓ o abort:
# crash (96), parado (97) e validação falhou (13) são gravados e aparecem no
# painel, mas não geram card. Ampliar é acrescentar códigos AQUI — a gravação
# já guarda todos.
CODIGOS_DE_FALHA = frozenset({ABORTADO_FILHO})

# Fração das execuções aprendidas em que o filho precisa aparecer para a
# ausência dele virar alerta.
FREQUENCIA_MINIMA = 0.8

# Execuções bem-sucedidas necessárias antes de cobrar ausência de qualquer job.
AMOSTRA_MINIMA = 3


@dataclass
class FilhoEsperado:
    """Uma linha de dbo.etl_ds_supervisao_estrutura."""
    job_filho: str
    execucoes_com_sucesso: int = 0


@dataclass
class Estrutura:
    """A lista aprendida de filhos + quantas execuções bem-sucedidas a formaram."""
    execucoes_aprendidas: int = 0
    filhos: list[FilhoEsperado] = field(default_factory=list)

    def frequencia(self, job_filho: str) -> float:
        if self.execucoes_aprendidas <= 0:
            return 0.0
        for f in self.filhos:
            if f.job_filho == job_filho:
                return f.execucoes_com_sucesso / self.execucoes_aprendidas
        return 0.0

    @property
    def madura(self) -> bool:
        """Já dá para cobrar ausência? Antes disso o mapa ainda está se formando."""
        return self.execucoes_aprendidas >= AMOSTRA_MINIMA

    def sempre_presentes(self) -> list[str]:
        """Filhos que aparecem com frequência suficiente para serem cobrados."""
        if not self.madura:
            return []
        return sorted(f.job_filho for f in self.filhos
                      if f.execucoes_com_sucesso / self.execucoes_aprendidas >= FREQUENCIA_MINIMA)


def filhos_que_falharam(run: DsRun) -> list[str]:
    """Filhos com código de falha nesta execução."""
    return sorted(nome for nome, code in (run.filhos or {}).items()
                  if code in CODIGOS_DE_FALHA)


def sucesso_real(run: DsRun) -> bool:
    """A execução foi boa DE VERDADE?

    Não basta o `Finished Job` da sequence: qualquer filho abortado invalida o
    sucesso. É a regra que o DataStage não aplica sozinho."""
    return run.resultado == OK and not filhos_que_falharam(run)


def filhos_ausentes(run: DsRun, estrutura: Estrutura) -> list[str]:
    """Jobs que a estrutura espera e que não apareceram nesta execução.

    Só considera os filhos frequentes o bastante (e só depois da amostra
    mínima), para ramo condicional não virar alarme diário."""
    presentes = set((run.filhos or {}).keys())
    return [nome for nome in estrutura.sempre_presentes() if nome not in presentes]


def aprender(run: DsRun) -> tuple[bool, list[str]]:
    """Esta execução deve alimentar a estrutura? Se sim, com quais filhos.

    Só execução com sucesso REAL ensina: aprender de um dia em que algo abortou
    gravaria a falha como se fosse o normal do fluxo."""
    if not sucesso_real(run) or not run.filhos:
        return False, []
    return True, sorted(run.filhos.keys())


def resumo_dependencia(run: DsRun, estrutura: Estrutura) -> dict:
    """Visão consolidada da execução, para o painel e para as mensagens."""
    falharam = filhos_que_falharam(run)
    ausentes = filhos_ausentes(run, estrutura)
    total = len(run.filhos or {})
    ok = sorted(nome for nome, code in (run.filhos or {}).items()
                if code in (SUCESSO, COM_AVISOS))
    return {
        "total_filhos": total,
        "filhos_ok": ok,
        "filhos_falharam": falharam,
        "filhos_ausentes": ausentes,
        # O veredito que o DataStage não dá.
        "sucesso_real": run.resultado == OK and not falharam and not ausentes,
        "sequence_disse_ok": run.resultado == OK,
    }
