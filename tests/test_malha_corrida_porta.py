"""
F3 da spec docs/spec-malha-execucao.md — a PORTA 1 do §6.2 (o disparo manual
abre a corrida) e o controle do operador (encerrar, listar, rename).

O que esta suíte prova, e por que cada prova existe:

  • o disparo abre UMA corrida, com o ODATE que ele vai carimbar e o snapshot
    congelado no MESMO commit; `dry_run` **não** abre — é prévia, não gesto;
  • **expiração preguiçosa** (Decisão 29): a corrida presa com o teto vencido
    expira NA PORTA e o disparo prossegue, sem depender de a guardiã ter
    passado. Um operador travado às 3h porque a guardiã morreu é exatamente o
    que não pode acontecer — e a mesma expiração NÃO acontece com membro vivo
    (Decisão 25), senão a rede de segurança viraria assassina de corrida;
  • **todas as raízes falharam → `ABORTADA` em SEGUNDA conexão**: quando os
    triggers rodam, a transação do disparo já foi commitada. O dublê distingue
    conexões e a primeira fica FECHADA — reusá-la levanta, então o teste prova
    a segunda conexão, não a intenção dela;
  • **portão do §11.1**: motor antigo (sem `malha_corrida_085` em
    `CAPACIDADES`) com a 085 aplicada é a célula mais provável do deploy real,
    e nela a API responde EXATAMENTE como antes desta fase — nem abre, nem
    recusa por corrida. A prova é de AUSÊNCIA da chave `corrida`;
  • encerrar exige motivo, grava `fechada_por`, libera o disparo NA HORA e diz
    o que NÃO aconteceu (ninguém foi interrompido);
  • renomear com corrida aberta CARIMBA a corrida: o nome antigo fica livre e
    não sobra órfã presa no índice filtrado.

O dublê é o da F15 (que já modela o disparo inteiro) + um SQL Server em
miniatura para a 085: os dois índices únicos da corrida, o relógio do BANCO
**3h à frente** do relógio do processo (o desvio MEDIDO no dev — Decisão 10) e
as consultas de estado/relógios. SQL não previsto levanta `AssertionError`: o
dublê é contrato, e mudar o SQL do módulo sem passar por aqui quebra a suíte.

⚠️ **REGRA DE HONESTIDADE DO DUBLÊ** (a lição cara da F1 e da F2, em que a
suíte ficou verde com dois defeitos ALTOS): *guarda que mora no `WHERE` do SQL
só é aplicada aqui se o SQL emitido a contiver*. Cada `_guarda(...)` abaixo lê
o texto do statement antes de filtrar — apagar `AND fechada_em IS NULL` do
`fechar_corrida` ou do `_SQL_CORRIDA_RENOMEAR` deixa o dublê fechar duas vezes
e renomear corrida encerrada, e é um teste que fica VERMELHO. Aplicar a regra
por conta própria faria a mutação "apaga a cláusula" passar verde, e o teste
provaria a si mesmo.
"""
from __future__ import annotations

import copy
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, PERM_EXECUTAR, get_current_user
from services import malha_corrida as mc
from services import rerun as rerun_svc
from tests.test_malha_corrida import CAMPOS, erro_duplicata
from tests.test_malhas_f10 import _aresta, _cria_no, _monta_malha
from tests.test_malhas_f15 import (FakeAirflowClient, FakeCur as FakeCurF15,
                                   FakeDb as FakeDbF15, _pipes)

# O relógio do PROCESSO e o do BANCO, deslocados de propósito: no dev o SQL
# Server está ~3h à frente do container da API (medido). Toda conta de tempo
# feita em Python aparece como resultado errado, não como teste verde.
AGORA_API = datetime(2026, 8, 5, 7, 0, 0)
AGORA_BANCO = datetime(2026, 8, 5, 10, 0, 0)
ODATE = date(2026, 8, 5)


# ═════════════════════ dublê: F15 + a 085 em miniatura ══════════════════════

class Conexao:
    """Uma CONEXÃO, e não só um cursor.

    O dublê da F15 devolve o próprio `FakeDb` como conexão, o que torna
    indistinguíveis "a mesma conexão" e "outra conexão". A F3 depende dessa
    distinção: o aborto da corrida acontece numa SEGUNDA conexão, porque a
    transação do disparo já foi commitada quando os triggers rodam. Aqui a
    conexão fechada RECUSA cursor — reusá-la levanta, e o teste passa a provar
    o fato, não a intenção.
    """

    def __init__(self, db):
        self.db = db
        self.fechada = False

    def _viva(self):
        if self.fechada:
            raise RuntimeError("conexão já fechada (dublê da F3)")

    def cursor(self):
        self._viva()
        return self.db.cursor()

    def commit(self):
        self._viva()
        self.db.commit()

    def rollback(self):
        self.db.rollback()

    def close(self):
        # ⚠️ Fechar com transação ABERTA faz ROLLBACK — é o que o pyodbc faz
        # (autocommit desligado), e é o que transforma "esqueci o commit" em
        # teste vermelho em vez de linha fantasma no dublê. Sem isto, remover o
        # `conn.commit()` da abertura passaria despercebido aqui e a corrida
        # sumiria só em produção.
        if not self.fechada:
            self.db.rollback()
        self.fechada = True
        self.db.closes += 1


class FakeDb(FakeDbF15):
    """FakeDb da F15 + `etl_malha_execucao`, `etl_malha_execucao_membro`,
    `etl_dependencia_evento` e o relógio do banco.

    `com_085=False` é o banco anterior à migration: a sonda devolve NULL e a
    API degrada para o comportamento de antes da F3.
    """

    def __init__(self, pipelines=None, config=None, com_085=True,
                 agora_banco=AGORA_BANCO, com_082=False, **kw):
        super().__init__(pipelines=pipelines, config=config, **kw)
        self.com_085 = com_085
        # F7: a retenção do Aguarde (082). Default AUSENTE — é o estado do
        # dublê herdado, e ligá-lo muda o SQL do card (o hold entra por slot).
        self.com_082 = com_082
        self.corridas: list[dict] = []
        self.membros_corrida: list[dict] = []
        self.eventos: list[dict] = []
        # ⚠️ o relógio do banco entra pelo construtor porque o heartbeat default
        # é derivado DELE: montar o dublê com um relógio e trocá-lo depois
        # deixaria a guardiã "morta há 12h" e fecharia o portão do §11.1 — um
        # teste que provaria a degradação achando que prova a regra.
        self.agora_banco = agora_banco
        self._prox_corrida = 1
        self.conexoes: list[Conexao] = []
        self.closes = 0
        self.rollbacks = 0
        # Gatilhos de CONCORRÊNCIA — `callable(db)` disparado UMA vez, dentro
        # do statement, para simular a outra ponta commitando no vão entre a
        # leitura que decidiu e a escrita que executa. É a única forma honesta
        # de exercitar as guardas que moram no `WHERE` (INSERT-first da Decisão
        # 14 e `rowcount` de árbitro da Decisão 8): sem elas, o teste provaria a
        # intenção do código em vez do comportamento dele.
        self.antes_de_abrir = None
        self.ao_fechar = None
        # Injeção de falha no snapshot: prova que a corrida e os membros são UM
        # commit só (§6.2) — se o snapshot morre, não sobra corrida sem membros.
        self.falhar_snapshot = False
        # Heartbeat da guardiã: por default RECENTE (o caminho feliz). O texto
        # é ISO porque `etl_app_config.config_value` é VARCHAR — é assim que a
        # guardiã o grava, com `CONVERT(..., 120)` do próprio banco.
        self.config.setdefault(mc.CHAVE_ATIVA, "1")
        self.config.setdefault(
            mc.CHAVE_HEARTBEAT,
            (agora_banco - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S"))

    # ── conexões ────────────────────────────────────────────────────────────
    def conectar(self):
        c = Conexao(self)
        self.conexoes.append(c)
        return c

    # ── transação (o snapshot do F11 estendido com as tabelas da 085) ───────
    def _estado(self):
        return super()._estado() + (self.corridas, self.membros_corrida,
                                    self.eventos, self._prox_corrida)

    def cursor(self):
        self._snapshot = copy.deepcopy(self._estado())
        return FakeCur(self)

    def rollback(self):
        self.rollbacks += 1
        if self._snapshot is not None:
            *herdado, self.corridas, self.membros_corrida, self.eventos, \
                self._prox_corrida = self._snapshot
            self._snapshot = tuple(herdado)
            super().rollback()

    # ── helpers de cenário ──────────────────────────────────────────────────
    def abertas(self, malha=None):
        return [c for c in self.corridas
                if c["fechada_em"] is None
                and (malha is None
                     or c["malha_name"].casefold() == malha.casefold())]

    def por_id(self, cid):
        return next((c for c in self.corridas if c["id"] == int(cid)), None)

    def tipos_de_evento(self):
        return [e["tipo"] for e in self.eventos]

    def abrir_corrida(self, malha, odate=ODATE, aberta_em=None, teto_horas=24,
                      membros=(), status="ABERTA"):
        """Corrida pré-existente (a que a guardiã teria aberto). Escrever a
        linha direto é o certo aqui: o cenário é "a corrida JÁ estava lá", e
        fabricá-la pela API misturaria o que se prova com o que se prepara."""
        ab = aberta_em or self.agora_banco
        seq = 1 + max([c["sequencia"] for c in self.corridas
                       if c["malha_name"].casefold() == malha.casefold()
                       and c["data_referencia"] == odate] or [0])
        linha = {campo: None for campo in CAMPOS}
        linha.update(id=self._prox_corrida, malha_name=malha,
                     data_referencia=odate, sequencia=seq, status=status,
                     aberta_em=ab, origem="inicio", aberta_por="inicio:#1",
                     modo_fechamento="quiescencia", teto_creditado_min=0,
                     tentativas=1,
                     teto_em=(ab + timedelta(hours=teto_horas)
                              if teto_horas else None))
        if status != "ABERTA":
            linha["fechada_em"] = ab + timedelta(hours=1)
        self.corridas.append(linha)
        for p in membros:
            self.membros_corrida.append(
                {"malha_execucao_id": linha["id"], "pipeline_name": p,
                 "conta_para_fim": 1, "ativo_na_abertura": 1, "eh_raiz": 1})
        self._prox_corrida += 1
        return linha


def _proj(c):
    return tuple(c[campo] for campo in CAMPOS)


def _guarda(sql: str, clausula: str) -> bool:
    """O statement emitido contém esta cláusula? (a REGRA DE HONESTIDADE do
    cabeçalho).

    Existe para que o dublê nunca aplique de graça uma guarda que só o SQL
    deveria aplicar. Onde este helper é chamado, apagar a cláusula do módulo
    muda o COMPORTAMENTO do dublê — que é o único jeito de a mutação virar
    teste vermelho em vez de teste verde por conta própria."""
    return " ".join(clausula.split()) in sql


class FakeCur(FakeCurF15):
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        p = tuple(params)

        # A sonda vem ANTES de tudo: OBJECT_ID de tabela inexistente devolve
        # NULL, não levanta — é por isso que ela serve de sonda.
        if "OBJECT_ID('dbo.etl_malha_execucao'" in s:
            self._rows = [(1, 1, 8)] if db.com_085 else [(None, None, None)]
            self.rowcount = -1
            return
        # F7: `etl_malha.teto_horas` nasce na 085, em BLOCO SEPARADO da tabela
        # da corrida — por isso guard próprio no router e branch próprio aqui.
        if "COL_LENGTH('dbo.etl_malha', 'teto_horas')" in s:
            self._rows = [(4,)] if db.com_085 else [(None,)]
            self.rowcount = -1
            return
        # F7: a retenção (082). Default AUSENTE — é o estado do dublê herdado
        # (a checagem levantava e o router degradava); `com_082=True` liga o
        # hold e é o que os cenários de retenção usam.
        if "COL_LENGTH('dbo.etl_malha_no', 'retido_em')" in s:
            self._rows = ([(8, 64)] if getattr(db, "com_082", False)
                          else [(None, None)])
            self.rowcount = -1
            return
        # O SELECT de nós COM as colunas da 082 (o router só o emite com
        # `com_082=True`). Espelha o da F10 mais as duas colunas da retenção.
        if s.startswith("SELECT id, tipo, config_json, layout_x, layout_y, "
                        "retido_em, retido_por FROM dbo.etl_malha_no"):
            k = str(p[0] or "").casefold()
            self._rows = sorted(
                (nid, n["tipo"], n["config_json"], n["layout_x"], n["layout_y"],
                 n.get("retido_em"), n.get("retido_por"))
                for nid, n in db.nos.items() if n["malha"].casefold() == k)
            self.rowcount = -1
            return
        # O tipo do nó, que o endpoint de retenção lê antes de decidir.
        if s.startswith("SELECT tipo FROM dbo.etl_malha_no WHERE id = ?"):
            no = db.nos.get(int(p[0]))
            k = db._malha_key(p[1])
            self._rows = ([(no["tipo"],)] if no is not None
                          and str(no["malha"]).casefold() == str(k or "").casefold()
                          else [])
            self.rowcount = -1
            return
        # Segurar/soltar — as duas escritas do endpoint de retenção.
        if s.startswith("UPDATE dbo.etl_malha_no SET retido_em = GETDATE()"):
            no = db.nos.get(int(p[1]))
            if no is not None:
                no["retido_em"] = db.agora_banco
                no["retido_por"] = p[0]
            self.rowcount = 1 if no is not None else 0
            return
        if s.startswith("UPDATE dbo.etl_malha_no SET retido_em = NULL"):
            no = db.nos.get(int(p[0]))
            if no is not None:
                no["retido_em"] = None
                no["retido_por"] = None
            self.rowcount = 1 if no is not None else 0
            return
        if not db.com_085 and "etl_malha_execucao" in s:
            raise RuntimeError(
                "[42S02] Invalid object name 'dbo.etl_malha_execucao'. (208)")

        # ── quantas corridas a malha teve NESTE dia (F4, achado 4) ──────────
        # O painel usa isto para decidir se descrever UMA corrida sobre a lista
        # do dia inteiro seria honesto. Fica ANTES dos demais SELECTs de
        # etl_malha_execucao porque é o mais específico.
        if s.startswith("SELECT COUNT(*) FROM dbo.etl_malha_execucao "
                        "WHERE malha_name = ?"):
            alvo = db._malha_key(p[0])
            self._rows = [(sum(1 for c in db.corridas
                               if c["malha_name"].casefold() == (alvo or "").casefold()
                               and c["data_referencia"] == p[1]),)]
            self.rowcount = -1
            return

        # ── heartbeat da guardiã (a comparação é do BANCO) ──────────────────
        if s.startswith("SELECT c.config_value, CASE WHEN TRY_CONVERT"):
            valor = db.config.get(p[1])
            if valor is None:
                self._rows = []
            else:
                visto = datetime.strptime(valor, "%Y-%m-%d %H:%M:%S")
                recente = visto >= db.agora_banco - timedelta(minutes=p[0])
                self._rows = [(valor, 1 if recente else 0)]
            self.rowcount = -1
            return

        # ── configs da malha (virada e teto), na forma de UMA consulta ──────
        if s.startswith("SELECT m.hora_virada, c.config_value"):
            k = db._malha_key(p[0])
            self._rows = ([(db.malhas[k].get("hora_virada"),
                            db.config.get("dependencia_hora_virada"))]
                          if k else [])
            self.rowcount = -1
            return
        if s.startswith("SELECT m.teto_horas, c.config_value"):
            k = db._malha_key(p[0])
            self._rows = ([(db.malhas[k].get("teto_horas"),
                            db.config.get(mc.CHAVE_TETO))] if k else [])
            self.rowcount = -1
            return

        # ── leituras da corrida ────────────────────────────────────────────
        if s.startswith("SELECT id, malha_name") or \
                s.startswith("SELECT TOP (?) id, malha_name"):
            self._rows = self._ler_corridas(s, p)
            self.rowcount = -1
            return
        if s.startswith("SELECT pipeline_name, conta_para_fim"):
            self._rows = [(m["pipeline_name"], m["conta_para_fim"],
                           m["ativo_na_abertura"], m["eh_raiz"])
                          for m in sorted(db.membros_corrida,
                                          key=lambda m: m["pipeline_name"])
                          if m["malha_execucao_id"] == int(p[0])]
            self.rowcount = -1
            return
        if s.startswith("SELECT m.pipeline_name, m.conta_para_fim"):
            self._rows = self._estado_da_corrida(s, p)
            self.rowcount = -1
            return
        if s.startswith("SELECT DISTINCT e.pipeline_name, e.data_referencia"):
            self._rows = sorted(
                {(e["pipeline"], e["data_referencia"]) for e in db.execucoes
                 if e.get("malha_execucao_id") == int(p[0])
                 and e["data_referencia"] != p[1]
                 and e.get("substituida_em") is None})
            self.rowcount = -1
            return
        if s.startswith("SELECT CASE WHEN me.teto_em IS NOT NULL"):
            self._rows = self._relogios(p)
            self.rowcount = -1
            return
        # ── F7: o HOLD, derivado de MIN(retido_em) ─────────────────────────
        # Nunca materializado: o dublê recalcula a cada chamada, do jeito que o
        # banco faz. É isto que torna vermelho o teste "soltar UM de DOIS
        # Aguardes destravou os relógios".
        if s.startswith("SELECT COUNT(*), MIN(n.retido_em)"):
            self._rows = self._hold(s, p)
            self.rowcount = -1
            return
        if s.startswith("UPDATE me SET teto_creditado_min"):
            self._rows = self._creditar_hold(s, p)
            self.rowcount = len(self._rows)
            return

        # ── escritas da corrida ────────────────────────────────────────────
        # O membro vem ANTES da corrida: `etl_malha_execucao` é prefixo de
        # `etl_malha_execucao_membro`.
        if s.startswith("INSERT INTO dbo.etl_malha_execucao_membro"):
            self._snapshot_da_corrida(s, p)
            return
        if s.startswith("INSERT INTO dbo.etl_malha_execucao"):
            self._abrir(s, p)
            return
        if s.startswith("UPDATE dbo.etl_malha_execucao SET status = ?"):
            self._fechar(s, p)
            return
        if s.startswith("UPDATE dbo.etl_malha_execucao SET malha_name = ?"):
            # §6.9/#13: **só a corrida ABERTA** troca de nome. As fechadas
            # ficam com o nome de quando aconteceram — é histórico. A guarda é
            # do WHERE, então o dublê só a aplica se o WHERE a tiver.
            so_abertas = _guarda(s, "AND fechada_em IS NULL")
            alvo = [c for c in db.corridas
                    if c["malha_name"].casefold() == p[1].casefold()
                    and (c["fechada_em"] is None or not so_abertas)]
            for c in alvo:
                c["malha_name"] = p[0]
            self.rowcount = len(alvo)
            return
        if s.startswith("INSERT INTO dbo.etl_dependencia_evento"):
            self._evento(s, p)
            return

        super().execute(sql, params)

    # ── implementações ──────────────────────────────────────────────────────
    def _ler_corridas(self, s, p):
        db = self.db
        if "WHERE malha_name = ?" in s and _guarda(s, "AND fechada_em IS NULL"):
            return [_proj(c) for c in db.abertas(p[0])]
        if "WHERE id = ?" in s:
            achada = db.por_id(p[0])
            return [_proj(achada)] if achada else []
        if s.startswith("SELECT TOP (?)"):
            linhas = [c for c in db.corridas
                      if c["malha_name"].casefold() == p[1].casefold()]
            if _guarda(s, "AND data_referencia = ?"):
                linhas = [c for c in linhas if c["data_referencia"] == p[2]]
            linhas.sort(key=lambda c: (c["data_referencia"], c["sequencia"],
                                       c["id"]), reverse=True)
            return [_proj(c) for c in linhas[:p[0]]]
        raise AssertionError(f"SELECT da corrida fora do contrato: {s}")

    def _estado_da_corrida(self, s, p):
        """`SQL_ESTADO` — o snapshot LEFT JOIN as linhas do escopo da Decisão
        23: data = ODATE **e** (proveniência OU recorte de tempo).

        As três cláusulas do escopo são lidas do TEXTO: elas são o que impede o
        reprocesso de OUTRO dia de contar como trabalho desta corrida, e um
        dublê que as aplicasse sozinho esconderia a remoção de qualquer uma."""
        odate, cid, aberta_em = p[0], int(p[1]), p[2]
        exige_odate = _guarda(s, "AND e.data_referencia = ?")
        exige_viva = _guarda(s, "AND e.substituida_em IS NULL")
        recorta = _guarda(s, "AND (e.malha_execucao_id = ? "
                             "OR COALESCE(e.inicio, e.criado_em) >= ?)")
        out = []
        for m in sorted(self.db.membros_corrida,
                        key=lambda m: m["pipeline_name"]):
            if m["malha_execucao_id"] != int(p[3]):
                continue
            base = (m["pipeline_name"], m["conta_para_fim"],
                    m["ativo_na_abertura"], m["eh_raiz"])
            linhas = [e for e in self.db.execucoes
                      if e["pipeline"].casefold() == m["pipeline_name"].casefold()
                      and (e["data_referencia"] == odate or not exige_odate)
                      and (e.get("substituida_em") is None or not exige_viva)
                      and (not recorta
                           or e.get("malha_execucao_id") == cid
                           or (e.get("inicio") or e.get("criado_em")) >= aberta_em)]
            if not linhas:
                out.append(base + (None, None, 0))
                continue
            for e in linhas:
                orfa = 1 if any(
                    ev["pipeline_name"] == e["pipeline"]
                    and ev["tipo"] == mc.EVENTO_ORFA for ev in self.db.eventos) \
                    else 0
                out.append(base + (e["status"],
                                   e.get("inicio") or e.get("criado_em"), orfa))
        return out

    def _relogios(self, p):
        """`SQL_RELOGIOS` — as três comparações, **todas** contra o relógio do
        BANCO. É este dublê que transforma qualquer aritmética em Python (que
        usaria o relógio do processo, 3h atrás) em teste vermelho."""
        db = self.db
        c = db.por_id(p[3])
        if c is None:
            return []
        agora = db.agora_banco
        teto = c["teto_em"] is not None and c["teto_em"] < agora
        partida = c["aberta_em"] < agora - timedelta(minutes=int(p[0]))
        ultimo = max(
            [e.get("fim") or e.get("inicio") or e.get("criado_em")
             for e in db.execucoes
             if e["data_referencia"] == c["data_referencia"]
             and any(m["malha_execucao_id"] == c["id"]
                     and m["pipeline_name"].casefold() == e["pipeline"].casefold()
                     for m in db.membros_corrida)] or [c["aberta_em"]])
        quiescente = (c["aberta_em"] < agora - timedelta(minutes=int(p[1]))
                      and ultimo < agora - timedelta(minutes=int(p[2])))
        return [(1 if teto else 0, 1 if partida else 0,
                 1 if quiescente else 0)]

    # ── F7 — o hold e o crédito do teto ────────────────────────────────────
    def _nos_retidos(self, malha, sem_inicio=False):
        """Os nós SEGURADOS da malha, do mais antigo para o mais novo.

        `sem_inicio` é a cláusula `AND n.tipo <> 'inicio'` do statement, e ela
        NUNCA é aplicada de graça: quem segura o ciclo em voo é o Aguarde; o
        Início segura a PARTIDA, e a corrida em andamento segue (§6.7). Sem o
        recorte, segurar o Início congelaria o teto da corrida aberta — e
        apagar a cláusula do módulo tem de virar teste vermelho aqui."""
        db = self.db
        k = db._malha_key(malha) or malha
        return sorted(
            ((nid, n) for nid, n in getattr(db, "nos", {}).items()
             if str(n.get("malha", "")).casefold() == str(k).casefold()
             and n.get("retido_em") is not None
             and not (sem_inicio and str(n.get("tipo")) == "inicio")),
            key=lambda item: (item[1]["retido_em"], item[0]))

    def _hold(self, s, p):
        """`SQL_HOLD_DA_MALHA` — contagem, `MIN(retido_em)`, o DATEDIFF contra
        o relógio do BANCO e quem segurou o mais antigo. O dublê nunca guarda
        "está retido": ele deriva, como a spec manda.

        ⚠️ REGRA DE HONESTIDADE: o recorte "só os nós SEGURADOS" mora no
        `WHERE` do statement. Sem ele o banco contaria TODO nó da malha como
        retido — Início, Fim e Notificação inclusive — e a malha inteira
        nasceria travada para sempre, com o teto congelado e a quiescência
        muda. O dublê só filtra se o SQL filtrar; do contrário a mutação
        "apaga o `AND n.retido_em IS NOT NULL`" passaria verde."""
        so_retidos = _guarda(s, "AND n.retido_em IS NOT NULL")
        sem_inicio = _guarda(s, "AND n.tipo <> 'inicio'")
        retidos = (self._nos_retidos(p[0], sem_inicio) if so_retidos
                   else self._todos_os_nos(p[0]))
        if not retidos:
            return [(0, None, None, None)]
        desde = retidos[0][1].get("retido_em")
        minutos = (int((self.db.agora_banco - desde).total_seconds() // 60)
                   if desde is not None else None)
        return [(len(retidos), desde, minutos, retidos[0][1].get("retido_por"))]

    def _todos_os_nos(self, malha):
        """O que a consulta devolveria SEM o filtro da retenção — existe só
        para que apagar o filtro mude o comportamento do dublê."""
        db = self.db
        k = db._malha_key(malha) or malha
        return sorted(((nid, n) for nid, n in getattr(db, "nos", {}).items()
                       if str(n.get("malha", "")).casefold() == str(k).casefold()),
                      key=lambda item: (item[1].get("retido_em") or
                                        db.agora_banco, item[0]))

    def _creditar_hold(self, s, p):
        """`SQL_CREDITAR_HOLD` — o `WHERE` aplicado a partir do TEXTO emitido.

        ⚠️ REGRA DE HONESTIDADE, e aqui ela é o assunto da fase: cada cláusula
        abaixo só é aplicada se o statement a contiver. Aplicá-las por conta
        própria deixaria a suíte verde com o crédito acontecendo no meio de um
        hold ainda em curso (`n2.id <> ?`), sobre corrida já fechada
        (`fechada_em IS NULL`) ou com crédito zero — e a mutação "apaga a
        cláusula" provaria o dublê, não o módulo."""
        db = self.db
        malha, no_id = p[0], int(p[1])
        # `NOT EXISTS (... n2.id <> ?)` — o "ÚLTIMO nó". Sem esta cláusula o
        # crédito sai com outro Aguarde ainda segurado, que é exatamente o
        # defeito que o espelho materializado teria.
        if _guarda(s, "AND n2.id <> ?"):
            outros = self._nos_retidos(malha,
                                       _guarda(s, "AND n2.tipo <> 'inicio'"))
            if [nid for nid, _ in outros if nid != no_id]:
                return []
        # `MIN(retido_em)` do CROSS APPLY — com o MESMO recorte do Início, e
        # por isso lido do alias `n` (o do CROSS APPLY), não do `n2`.
        retidos = self._nos_retidos(malha, _guarda(s, "AND n.tipo <> 'inicio'"))
        if not retidos:
            return []          # `MIN` sobre conjunto vazio: `h.cred` é NULL
        candidatas = [c for c in db.corridas
                      if c["malha_name"].casefold() == str(
                          db._malha_key(malha) or malha).casefold()]
        if _guarda(s, "AND me.fechada_em IS NULL"):
            candidatas = [c for c in candidatas if c["fechada_em"] is None]
        if _guarda(s, "AND me.teto_em IS NOT NULL"):
            candidatas = [c for c in candidatas if c["teto_em"] is not None]
        alvo = next(iter(candidatas), None)
        if alvo is None:
            return []
        # A corrida é escolhida ANTES do cálculo porque o piso do crédito é
        # `me.aberta_em` — e, como toda guarda desta suíte, ele só vale se o SQL
        # o contiver. Sem esta leitura, apagar o CASE do módulo passaria verde e
        # um nó esquecido há dias voltaria a creditar dias a um teto de horas.
        desde = retidos[0][1]["retido_em"]
        if _guarda(s, "CASE WHEN MIN(n.retido_em) < me.aberta_em THEN me.aberta_em"):
            desde = max(desde, alvo["aberta_em"])
        cred = int((db.agora_banco - desde).total_seconds() // 60)
        if _guarda(s, "AND h.cred > 0") and cred <= 0:
            return []
        alvo["teto_creditado_min"] = int(alvo.get("teto_creditado_min") or 0) + cred
        if _guarda(s, "teto_em = DATEADD(MINUTE, h.cred, me.teto_em)"):
            alvo["teto_em"] = alvo["teto_em"] + timedelta(minutes=cred)
        # A memória do alarme de atraso falava de um teto que acabou de mudar
        # de lugar: sem zerá-la, o próximo atraso — depois do crédito — fica
        # mudo para sempre. O dublê só zera se o `SET` zerar.
        if _guarda(s, "atraso_visto_em = NULL"):
            alvo["atraso_visto_em"] = None
        return [(alvo["id"], cred, alvo["teto_em"], alvo["teto_creditado_min"],
                 alvo["data_referencia"])]

    def _abrir(self, s, p):
        """O INSERT-first com os DOIS índices únicos aplicados de verdade: a
        violação que o módulo trata (`ux_malha_exec_aberta`) tem de vir do
        MODELO, não de um `if` do dublê."""
        db = self.db
        assert len(p) == 14, f"abertura com {len(p)} parâmetros: {p}"
        assert p[0] == p[2] and p[1] == p[3], f"malha/odate fora de par: {p}"
        malha, odate = p[0], p[1]
        if db.antes_de_abrir is not None:
            # A guardiã abriu a corrida ENTRE a conferência e este INSERT — a
            # janela real que a Decisão 14 (claim, não check) cobre.
            db.antes_de_abrir, gatilho = None, db.antes_de_abrir
            gatilho(db)
        if db.abertas(malha):
            raise erro_duplicata(mc.IX_ABERTA, driver="pyodbc")
        ab = p[13] if p[13] is not None else db.agora_banco
        seq = 1 + max([c["sequencia"] for c in db.corridas
                       if c["malha_name"].casefold() == malha.casefold()
                       and c["data_referencia"] == odate] or [0])
        linha = {campo: None for campo in CAMPOS}
        linha.update(id=db._prox_corrida, malha_name=malha,
                     data_referencia=odate, sequencia=seq, status="ABERTA",
                     aberta_em=ab, origem=p[4], aberta_por=p[5],
                     ancora_pipeline=p[6], ancora_execution_id=p[7],
                     no_inicio=p[8], no_fim=p[9], modo_fechamento=p[10],
                     teto_em=ab + timedelta(hours=int(p[11])), motivo=p[12],
                     teto_creditado_min=0, tentativas=1)
        db.corridas.append(linha)
        db._prox_corrida += 1
        self._rows = [_proj(linha)]
        self.rowcount = 1

    def _snapshot_da_corrida(self, s, p):
        db = self.db
        if db.falhar_snapshot:
            raise RuntimeError("deadlock simulado no snapshot da corrida (teste)")
        cid, malha = int(p[0]), p[-2]
        if "1 = 1" in s:
            conta = None                       # malha sem nó Fim: todos contam
        elif "1 = 0" in s:
            conta = set()
        else:
            conta = set(p[1:-2])
        k = db._malha_key(malha)
        # A idempotência é do `NOT EXISTS` final, e o dublê só a aplica se ele
        # estiver no texto: sem a cláusula, aderir a uma corrida que já congelou
        # duplicaria o snapshot (violação de PK que rolaria de volta a transação
        # de quem chamou, inclusive o INSERT da corrida).
        idempotente = _guarda(
            s, "AND NOT EXISTS (SELECT 1 FROM dbo.etl_malha_execucao_membro m")
        gravados = 0
        for m in db.membros:
            if not (k and m["malha"].casefold() == k.casefold()):
                continue
            pipe = m["pipeline"]
            if idempotente and any(
                    x["malha_execucao_id"] == cid
                    and x["pipeline_name"].casefold() == pipe.casefold()
                    for x in db.membros_corrida):
                continue                       # NOT EXISTS — idempotente
            pk = db._pipeline_key(pipe)
            ativo = int(db.pipelines.get(pk, {}).get("active") or 0) if pk else 0
            tem_pred = any(
                d["pipeline"].casefold() == pipe.casefold()
                and any(o["malha"].casefold() == k.casefold()
                        and o["pipeline"].casefold() == d["depende_de"].casefold()
                        for o in db.membros)
                for d in db.dependencias)
            db.membros_corrida.append({
                "malha_execucao_id": cid, "pipeline_name": pipe,
                "conta_para_fim": 1 if (conta is None or pipe in conta) else 0,
                "ativo_na_abertura": ativo,
                "eh_raiz": 0 if tem_pred else 1})
            gravados += 1
        self.rowcount = gravados

    def _fechar(self, s, p):
        """`WHERE id = ? AND fechada_em IS NULL` — o `rowcount` é o árbitro.

        A guarda `fechada_em IS NULL` é lida do TEXTO: é ela que impede duas
        pontas de fecharem a mesma corrida com desfechos diferentes (Decisão 8),
        e um dublê que a aplicasse por conta própria deixaria a mutação "apaga a
        cláusula" passar verde."""
        db = self.db
        assert len(p) == 5, f"fechamento com {len(p)} parâmetros: {p}"
        if db.ao_fechar is not None:
            # Outra ponta commitou no vão entre a LEITURA que decidiu fechar e
            # este UPDATE. É a janela que o `rowcount` de árbitro existe para
            # cobrir, e ela só se prova disparando-a de fora.
            db.ao_fechar, gatilho = None, db.ao_fechar
            gatilho(db)
        desfecho, fechada_por, motivo, cid = p[0], p[1], p[2], int(p[4])
        c = db.por_id(cid)
        if c is None or (c["fechada_em"] is not None
                         and _guarda(s, "AND fechada_em IS NULL")):
            self.rowcount = 0
            return
        prefixo = (c["motivo"] + " | ") if c["motivo"] else ""
        c.update(status=desfecho, fechada_em=db.agora_banco,
                 fechada_por=fechada_por,
                 motivo=(prefixo + motivo)[:500] if motivo else c["motivo"])
        self.rowcount = 1

    def _evento(self, s, p):
        db = self.db
        com_corrida = "malha_execucao_id" in s
        pipeline, data_ref, tipo = p[0], p[1], p[2]
        corrida = int(p[4]) if com_corrida else None
        # A idempotência do evento é o `WHERE NOT EXISTS` do próprio INSERT (a
        # mesma chave de `ux_dep_evento_corrida`). Sem ele no texto, o dublê
        # grava duplicado — que é o que o banco faria antes de estourar o 2601.
        if _guarda(s, "WHERE NOT EXISTS") and any(
                e["pipeline_name"] == pipeline and e["data_referencia"] == data_ref
                and e["tipo"] == tipo and e.get("malha_execucao_id") == corrida
                for e in db.eventos):
            self.rowcount = 0
            return
        db.eventos.append({"pipeline_name": pipeline, "data_referencia": data_ref,
                           "tipo": tipo, "detalhe": p[3],
                           "malha_execucao_id": corrida,
                           # F7: `notificar=False` grava o evento JÁ carimbado
                           # com `notificado_em` — ele existe e vive no painel,
                           # mas nunca entra na fila do Teams. O dublê tem de
                           # espelhar isso, senão o teste da Decisão 61 não
                           # conseguiria distinguir "evento" de "card".
                           "notificado_em": (db.agora_banco
                                             if "notificado_em" in s else None)})
        self.rowcount = 1


# ═══════════════════════════ fixtures e helpers ═════════════════════════════

@pytest.fixture(autouse=True)
def _sem_caches():
    """O interruptor tem cache de 30s no processo da API (divergência
    deliberada do canônico) e a capacidade do `dags/` tem cache por mtime. Um
    teste que herdasse qualquer um dos dois provaria o cache, não a regra."""
    mc.limpar_cache()
    rerun_svc._cache_capacidade.clear()
    yield
    mc.limpar_cache()
    rerun_svc._cache_capacidade.clear()


@pytest.fixture
def auth_operador(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "OPER1", "perfil": "operador",
        "permissoes": [PERM_EDITAR, PERM_EXECUTAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_sem_executar(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EDITAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _patch_db(db):
    """Cada `get_db_conn()` devolve uma CONEXÃO nova — é o que permite provar
    que o aborto usa a segunda."""
    return patch("routers.malhas.get_db_conn", side_effect=db.conectar)


def _patch_agora():
    """O relógio do PROCESSO, 3h atrás do banco."""
    return patch("routers.malhas._agora", return_value=AGORA_API)


def _dags_novo():
    """O `dags/` DEPLOYADO é o do repo — que declara `malha_corrida_085` de
    verdade. Dublar a capacidade aqui provaria o dublê; apontar para a árvore
    real prova a declaração que o deploy leva."""
    return patch.dict(os.environ,
                      {"DAGS_FOLDER": str(_RAIZ_DAGS)}, clear=False)


_RAIZ_DAGS = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "dags")


def _dags_antigo(tmp_path):
    """O motor de ANTES da F2: o arquivo existe e não declara a capacidade —
    a célula mais provável da matriz §11.1 (api/ nova, dags/ velho)."""
    utils = tmp_path / "utils"
    utils.mkdir(parents=True, exist_ok=True)
    (utils / "dependencias.py").write_text(
        'CAPACIDADES = ("rerun_cascata_078",)\n', encoding="utf-8")
    return patch.dict(os.environ, {"DAGS_FOLDER": str(tmp_path)}, clear=False)


def _malha_com_inicio(client, nome="M1", raizes=("RAIZ_A", "RAIZ_B")):
    _monta_malha(client, nome, [*raizes, "PIPE_MEIO"])
    inicio = _cria_no(client, nome, "inicio")
    for p in raizes:
        assert _aresta(client, nome, {"no": inicio},
                       {"pipeline": p}).status_code == 200
    return inicio


def _disparar(client, malha="M1", body=None):
    return client.post(f"/malhas/{malha}/disparo", json=body or {})


# ═════════════ o gesto: o disparo abre; o dry_run não abre ══════════════════

def test_disparo_abre_uma_corrida_com_o_odate_do_disparo_e_o_snapshot(
        client, auth_operador):
    """§10/F3, aceite 1: uma linha ABERTA com o ODATE do disparo e o snapshot
    congelado.

    O ODATE é o que o disparo CARIMBA no conf das raízes. Uma corrida nascida
    com outro rótulo classificaria todas as próprias linhas como
    `fora_do_odate` (§6.4) e nunca fecharia."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        r = _disparar(client, body={"data_referencia": "2026-08-05"})
    assert r.status_code == 200, r.text
    assert len(db.corridas) == 1
    c = db.corridas[0]
    assert (c["status"], c["origem"], c["aberta_por"]) == \
        ("ABERTA", "manual", "manual:OPER1")
    assert c["data_referencia"] == ODATE
    # `aberta_em` é o relógio do BANCO, nunca o do processo (Decisão 10).
    assert c["aberta_em"] == AGORA_BANCO
    assert c["teto_em"] == AGORA_BANCO + timedelta(hours=24)
    # snapshot congelado no MESMO gesto — corrida sem membros tem denominador
    # zero e a §6.5 a levaria a ABORTADA com a malha rodando ao lado.
    assert {m["pipeline_name"] for m in db.membros_corrida} == \
        {"RAIZ_A", "RAIZ_B", "PIPE_MEIO"}
    # malha sem nó Fim: fecha por quiescência e TODOS contam (§6.9/#1)
    assert c["modo_fechamento"] == "quiescencia"
    assert all(m["conta_para_fim"] == 1 for m in db.membros_corrida)
    # a resposta carrega a corrida (aditivo — a F4 lê daqui)
    assert r.json()["corrida"]["id"] == c["id"]
    assert r.json()["corrida"]["abortada"] is False


def test_dry_run_nao_abre_corrida(client, auth_operador):
    """§10/F3, aceite 1: `dry_run` → NENHUMA linha. É prévia, não gesto."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        r = _disparar(client, body={"dry_run": True})
    assert r.status_code == 200, r.text
    assert db.corridas == [] and db.membros_corrida == []
    assert "corrida" not in r.json()      # nada aberto, nada a mostrar


def test_virada_da_malha_divergente_vira_aviso_LEVE_e_nao_muda_o_odate(
        client, auth_operador):
    """Divergência VISÍVEL é o oposto de silenciosa (§6.2), mas o ODATE que a
    corrida carimba continua sendo o do DISPARO.

    ⚠️ Divergência deliberada da Decisão 18, e o motivo é de correção: o
    disparo manda `data_referencia` no conf de toda raiz, e uma corrida nascida
    com outro rótulo classificaria TODAS as suas linhas como `fora_do_odate`
    (§6.4) — nunca fecharia, o card diria 0 de N com a malha verde embaixo, e o
    teto a mataria 24h depois. Trocar a régua do default é mudar o conf do
    disparo, que é assunto do §7/F5. Aqui o operador é AVISADO.

    E quando ele ESCOLHE a data (reprocessar ontem, gesto diário), não há
    aviso nenhum: um alarme que toca no caminho normal deixa de ser alarme."""
    # 22:00 no BANCO (07:00 no processo, 3h atrás): passou da virada da MALHA e
    # não passou da global — é exatamente a fresta em que as duas réguas
    # discordam, e é uma pergunta que só o relógio do banco responde.
    db = FakeDb(pipelines=_pipes(),
                config={"dependencia_hora_virada": "00:00"},
                agora_banco=datetime(2026, 8, 5, 22, 0, 0))
    with _patch_db(db), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        db.malhas["M1"]["hora_virada"] = "20:00"     # a virada da MALHA diverge
        r = _disparar(client, body={"dry_run": True})
        escolhida = _disparar(client, body={"dry_run": True,
                                            "data_referencia": "2026-08-01"})
    assert r.status_code == 200, r.text
    avisos = [a for a in r.json()["avisos"] if a.get("tipo") == "odate_malha"]
    assert len(avisos) == 1 and avisos[0]["nivel"] == "leve"
    assert "2026-08-06" in avisos[0]["mensagem"]     # o canônico da malha
    assert r.json()["data_referencia"] == "2026-08-05"   # e o disparo carimba D
    assert [a for a in escolhida.json()["avisos"]
            if a.get("tipo") == "odate_malha"] == []


def test_a_corrida_nasce_com_o_odate_do_disparo_e_nao_com_o_canonico(
        client, auth_operador):
    """A corrida nasce com o ODATE que o disparo vai CARIMBAR no `conf` das
    raízes — mesmo quando a virada da malha aponta outro dia.

    ⚠️ Divergência deliberada da Decisão 18, e ela é de CORREÇÃO: a corrida
    nascida com o outro rótulo classificaria todas as próprias linhas como
    `fora_do_odate` (§6.4) — nunca fecharia, o card diria 0 de N com a malha
    inteira verde embaixo, e o teto a mataria 24h depois. A Decisão 18 governa
    as portas AUTOMÁTICAS, cujo insumo é um instante do banco; aqui o rótulo é
    escolha de gente. O que o operador recebe é o AVISO (teste acima)."""
    db = FakeDb(pipelines=_pipes(),
                config={"dependencia_hora_virada": "00:00"},
                agora_banco=datetime(2026, 8, 5, 22, 0, 0))
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        db.malhas["M1"]["hora_virada"] = "20:00"   # canônico da malha = 06/08
        r = _disparar(client)
    assert r.status_code == 200, r.text
    assert r.json()["data_referencia"] == "2026-08-05"
    assert db.corridas[0]["data_referencia"] == ODATE
    assert r.json()["corrida"]["data_referencia"] == "2026-08-05"


def test_dry_run_mostra_a_corrida_aberta_e_o_que_o_gesto_real_fara(
        client, auth_operador):
    """O `dry_run` NÃO recusa: ele MOSTRA. E não pode mentir por omissão —
    anunciar bloqueio numa corrida que o disparo real vai expirar sozinho faria
    o operador procurar um problema que não existe."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        presa = db.abrir_corrida("M1")
        r_travada = _disparar(client, body={"dry_run": True})
        # agora a MESMA corrida, com o teto vencido pelo relógio do BANCO
        presa["aberta_em"] -= timedelta(hours=25)
        presa["teto_em"] -= timedelta(hours=25)
        r_expiravel = _disparar(client, body={"dry_run": True})
    assert r_travada.status_code == 200 and r_expiravel.status_code == 200
    travada = r_travada.json()["corrida"]
    assert travada["id"] == presa["id"] and travada["sera_expirada"] is False
    assert r_travada.json()["bloqueado"] is True
    assert r_expiravel.json()["corrida"]["sera_expirada"] is True
    assert r_expiravel.json()["bloqueado"] is False
    # e nenhuma das duas prévias escreveu coisa alguma
    assert db.por_id(presa["id"])["status"] == "ABERTA"
    assert len(db.corridas) == 1


def test_snapshot_que_falha_nao_deixa_corrida_sem_membros(client,
                                                          auth_operador):
    """Abertura e snapshot são UM commit só (§6.2).

    Corrida sem membros tem denominador ZERO: a §6.5 a levaria a `ABORTADA`
    depois da carência de partida com a malha rodando ao lado, e até lá ela
    bloquearia o disparo. Aqui o snapshot morre com um erro que NÃO é da 085 —
    e a escrita degrada ESTREITA (só 207/208 nomeando os objetos da 085 viram
    None): o erro sobe, a transação inteira rola de volta e não sobra corrida.
    """
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    db.falhar_snapshot = True
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        r = _disparar(client)
    assert r.status_code == 500, r.text
    assert db.corridas == [] and db.membros_corrida == []
    assert fake.chamadas == []            # e nada foi disparado no Airflow


def test_disparo_bloqueado_pelo_ciclo_nao_deixa_corrida_aberta(client,
                                                               auth_operador):
    """O portão da corrida vem DEPOIS dos bloqueios do ciclo, e é isso que faz
    a Decisão 25 valer por construção.

    Se a corrida abrisse antes (ou apesar) do bloqueio, o 422 de "membro em
    execução" deixaria para trás uma corrida ABERTA que ninguém originou — e o
    disparo seguinte passaria a ser recusado por ela, não pelo membro vivo."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        db.execucoes.append({"pipeline": "PIPE_MEIO", "data_referencia": ODATE,
                             "execution_id": "run_x", "status": "EXECUTANDO",
                             "inicio": AGORA_BANCO - timedelta(minutes=10),
                             "substituida_em": None})
        r = _disparar(client)
    assert r.status_code == 422, r.text
    assert db.corridas == []
    assert fake.chamadas == []


def test_guardia_abre_entre_a_conferencia_e_o_insert_a_api_adere_e_recusa(
        client, auth_operador):
    """Decisão 14 — INSERT-first, nunca SELECT-then-INSERT.

    A conferência "não há corrida aberta" e o INSERT são dois instantes, e a
    guardiã pode abrir no vão (é uma janela real: as duas pontas consultam e
    decidem separadamente). O gatilho do dublê commita a corrida da guardiã
    exatamente aí. A resposta certa é a MESMA do 422 de sempre — disparar as
    raízes por cima de um ciclo recém-nascido é o mesmo estrago —, e quem
    ADERE não congela snapshot: o dono do snapshot é quem abriu.

    ⚠️ O dublê tem UM armazenamento só, então o rollback do 422 também desfaz a
    linha do gatilho; por isso a prova é a RESPOSTA e a ausência de trigger, e
    não a contagem de linhas depois do gesto."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        db.antes_de_abrir = lambda d: d.abrir_corrida("M1")
        r = _disparar(client)
    assert r.status_code == 422, r.text
    detalhe = r.json()["detail"]
    # Decisao 74: nomeia a corrida pelo DIA, e o "#" nao aparece — tres
    # numeracoes disputam essa notacao, e "#1" numa malha diaria le-se
    # como "1a tentativa hoje".
    assert "corrida de" in detalhe and "M1" in detalhe
    assert "#" not in detalhe
    assert fake.chamadas == []            # nenhuma raiz partiu por cima
    assert db.membros_corrida == []       # quem adere NÃO congela snapshot


def test_snapshot_congela_conta_para_fim_do_upstream_do_no_fim(
        client, auth_operador):
    """Com nó Fim, `conta_para_fim` é o upstream EXPANDIDO dele — quem não é
    alcançado fica fora do denominador do fechamento e o painel o lista como
    `fora_do_fim` (§6.9/#2), em vez de a corrida fechar com membro vivo."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db), _dags_novo(), _patch_agora():
        inicio = _malha_com_inicio(client)
        fim = _cria_no(client, "M1", "fim")
        assert _aresta(client, "M1", {"pipeline": "RAIZ_A"},
                       {"no": fim}).status_code == 200
        assert inicio is not None
        r = _disparar(client)
    assert r.status_code == 200, r.text
    contam = {m["pipeline_name"] for m in db.membros_corrida
              if m["conta_para_fim"] == 1}
    assert contam == {"RAIZ_A"}
    assert db.corridas[0]["modo_fechamento"] == "fim"


# ═════════════ o 422 que nomeia a corrida e aponta a saída ══════════════════

def test_corrida_aberta_recusa_422_nomeando_a_corrida_e_a_saida(
        client, auth_operador):
    """§10/F3, aceite 7 + §6.9/#14: o 422 nomeia a corrida e traz a frase de
    ação — inclusive a metade que destrava o operador (encerrar NÃO mata
    processo)."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        db.abrir_corrida("M1", aberta_em=AGORA_BANCO - timedelta(hours=1))
        r = _disparar(client)
    assert r.status_code == 422, r.text
    detalhe = r.json()["detail"]
    assert "corrida de" in detalhe and "M1" in detalhe
    assert "#" not in detalhe   # Decisao 74
    assert "Encerrar corrida" in detalhe
    assert "não interrompe pipeline nenhum" in detalhe
    assert fake.chamadas == []            # nada foi disparado
    assert len(db.corridas) == 1          # e nada foi aberto


# ═══════════ Decisão 29 — a expiração PREGUIÇOSA, na porta ══════════════════

def test_corrida_com_teto_vencido_expira_na_porta_e_o_disparo_prossegue(
        client, auth_operador):
    """§10/F3, aceite 3 e Decisão 29.

    O cenário é o que trava o plantão: a guardiã morreu, a corrida ficou presa
    e o teto já venceu. Sem a expiração na porta, o operador espera a guardiã
    voltar — que é o processo que acabou de morrer.

    ⚠️ O teto vence pelo relógio do BANCO: com o processo 3h atrás, uma conta
    em Python diria que ainda faltam 3 horas."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        presa = db.abrir_corrida(
            "M1", odate=date(2026, 8, 4),
            aberta_em=AGORA_BANCO - timedelta(hours=25), membros=["RAIZ_A"])
        r = _disparar(client)
    assert r.status_code == 200, r.text
    assert db.por_id(presa["id"])["status"] == "EXPIRADA"
    assert db.por_id(presa["id"])["fechada_por"] == "manual:OPER1"
    assert "MALHA_EXPIRADA" in db.tipos_de_evento()
    # e o disparo PROSSEGUIU: corrida nova + as raízes no Airflow
    assert len(db.abertas("M1")) == 1
    assert db.abertas("M1")[0]["id"] != presa["id"]
    assert sorted(c["dag_id"] for c in fake.chamadas) == ["RAIZ_A", "RAIZ_B"]


def test_reprocesso_de_OUTRO_dia_nao_segura_a_expiracao_na_porta(
        client, auth_operador):
    """Decisão 23 vista da porta: o escopo do `estado()` exige o ODATE da
    corrida, e por isso uma linha viva de OUTRO dia não a mantém aberta.

    O cenário é o plantão real: a corrida do dia 04 ficou presa e alguém está
    reprocessando o mesmo pipeline **para o dia 05**. Sem o ODATE no escopo,
    esse `EXECUTANDO` de outro dia contaria como membro vivo desta corrida — o
    teto nunca a expiraria, e o operador ficaria travado por trabalho que nem é
    dela. (O espelho disto é o §6.9/#15: a linha de outro dia também nunca
    conta como OK.)"""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        presa = db.abrir_corrida(
            "M1", odate=date(2026, 8, 4),
            aberta_em=AGORA_BANCO - timedelta(hours=25),
            membros=["SAIU_DA_MALHA"])
        # viva, do MESMO membro, mas do dia SEGUINTE — outro ciclo, não este
        db.execucoes.append({"pipeline": "SAIU_DA_MALHA",
                             "data_referencia": ODATE,
                             "execution_id": "run_outro_dia",
                             "status": "EXECUTANDO",
                             "inicio": AGORA_BANCO - timedelta(hours=2),
                             "substituida_em": None})
        r = _disparar(client)
    assert r.status_code == 200, r.text
    assert db.por_id(presa["id"])["status"] == "EXPIRADA"
    assert len(db.abertas("M1")) == 1
    assert db.abertas("M1")[0]["id"] != presa["id"]


def test_teto_vencido_NAO_expira_com_membro_vivo(client, auth_operador):
    """Decisão 25 — o teto nunca fecha corrida com membro vivo, nem na porta.

    Sem esta trava, a rede de segurança viraria assassina: a corrida sairia
    EXPIRADA, o disparo partiria por cima de pipelines ainda `EXECUTANDO` e as
    linhas que terminassem depois carregariam id de corrida FECHADA — o card
    ficaria `EXPIRADA` para sempre com verdes embaixo.

    ⚠️ O cenário é de propósito o que `_bloqueios_do_ciclo` **não** vê:
    `SAIU_DA_MALHA` está no SNAPSHOT congelado da corrida e já não está em
    `etl_malha_pipeline` (alguém o removeu no meio do ciclo). O bloqueio olha o
    desenho de AGORA e o `estado()` olha o snapshot — se a única trava fosse a
    ordem das duas perguntas, este é o caso que passaria por baixo dela."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        presa = db.abrir_corrida(
            "M1", aberta_em=AGORA_BANCO - timedelta(hours=25),
            membros=["SAIU_DA_MALHA"])
        db.execucoes.append({"pipeline": "SAIU_DA_MALHA",
                             "data_referencia": ODATE,
                             "execution_id": "run_v", "status": "EXECUTANDO",
                             "inicio": AGORA_BANCO - timedelta(hours=20),
                             "malha_execucao_id": presa["id"],
                             "substituida_em": None})
        r = _disparar(client)
    # o bloqueio de hoje NÃO enxerga essa linha (o pipeline não é mais membro):
    # quem recusa é o portão da corrida, e é isso que o teste prova
    assert r.status_code == 422, r.text
    assert "corrida de" in r.json()["detail"]   # Decisao 74: dia, nao id
    assert "#" not in r.json()["detail"]
    assert db.por_id(presa["id"])["status"] == "ABERTA"
    assert "MALHA_EXPIRADA" not in db.tipos_de_evento()
    assert fake.chamadas == []


# ═══════ §6.9/#4 — todas as raízes falharam: ABORTADA em 2ª conexão ═════════

def test_todas_as_raizes_falham_a_corrida_sai_abortada_em_segunda_conexao(
        client, auth_operador):
    """§10/F3, aceite 2.

    A prova da SEGUNDA conexão é estrutural: o dublê fecha a conexão do disparo
    antes dos triggers e uma conexão fechada RECUSA cursor. Se o aborto tentasse
    reusá-la, este teste levantaria em vez de passar.

    E o que ele realmente protege: sem o aborto, o primeiro Airflow fora do ar
    deixaria uma corrida ABERTA que nada originou, e o PRÓXIMO disparo seria
    recusado por uma corrida fantasma — a malha congelada por 24h."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient(falhas={"RAIZ_A": 500, "RAIZ_B": 500})
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        r = _disparar(client)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ok"] is False and len(corpo["falhas"]) == 2
    assert corpo["corrida"]["abortada"] is True
    assert corpo["corrida"]["status"] == "ABORTADA"
    # `status` e `fechada_em` são a MESMA informação no modelo
    # (`CK_mexec_coerente`): publicá-los em desacordo faria a tela ler "fechada"
    # de um campo e "aberta" do outro. Por isso a resposta traz a corrida RELIDA.
    assert corpo["corrida"]["fechada_em"] is not None
    assert corpo["corrida"]["fechada_por"] == "manual:OPER1"
    assert db.corridas[0]["status"] == "ABORTADA"
    assert "MALHA_ABORTADA" in db.tipos_de_evento()
    # a conexão do disparo já estava FECHADA quando o aborto rodou
    assert db.conexoes[-2].fechada is True
    assert db.conexoes[-1] is not db.conexoes[-2]


def test_o_proximo_disparo_nao_fica_bloqueado_pela_corrida_abortada(
        client, auth_operador):
    """A metade que importa do aceite 2: depois do aborto, o disparo seguinte
    funciona. Corrida fantasma é pior que corrida nenhuma."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        with patch("routers.malhas.get_airflow_client",
                   return_value=FakeAirflowClient(
                       falhas={"RAIZ_A": 500, "RAIZ_B": 500})):
            assert _disparar(client).status_code == 200
        ok = FakeAirflowClient()
        with patch("routers.malhas.get_airflow_client", return_value=ok):
            segundo = _disparar(client)
    assert segundo.status_code == 200, segundo.text
    assert len(ok.chamadas) == 2
    assert len(db.abertas("M1")) == 1


def test_o_aborto_que_nao_passa_nao_derruba_a_resposta_do_disparo(
        client, auth_operador):
    """O contra-teste da segunda conexão, e a prova de que ela é NECESSÁRIA:
    aqui o aborto recebe a conexão do disparo, que já foi commitada e FECHADA.

    Duas coisas têm de valer ao mesmo tempo: a resposta chega inteira (as
    falhas por raiz já estavam nela e o operador precisa delas) e a resposta
    NÃO mente — `abortada` sai `False`, porque a corrida de fato continua
    aberta e alguém vai ter de encerrá-la."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient(falhas={"RAIZ_A": 500, "RAIZ_B": 500})
    with _patch_db(db), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)

    # a sabotagem vale só para o disparo: a 1ª conexão é a dele, e toda
    # chamada seguinte (a do aborto) recebe a MESMA — já fechada
    estado: dict = {}

    def _sempre_a_mesma():
        if "conn" not in estado:
            estado["conn"] = db.conectar()
        return estado["conn"]

    with patch("routers.malhas.get_db_conn", side_effect=_sempre_a_mesma), \
            patch("routers.malhas.get_airflow_client", return_value=fake), \
            _dags_novo(), _patch_agora():
        r = _disparar(client)
    assert r.status_code == 200, r.text
    assert len(r.json()["falhas"]) == 2
    assert r.json()["corrida"]["abortada"] is False
    assert r.json()["corrida"]["status"] == "ABERTA"
    assert db.corridas[0]["status"] == "ABERTA"


def test_uma_raiz_que_parte_mantem_a_corrida_aberta(client, auth_operador):
    """Aborto é para "NENHUMA raiz partiu". Com uma que partiu, o ciclo
    começou — abortá-lo deixaria a execução em voo sem corrida."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient(falhas={"RAIZ_B": 500})
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        r = _disparar(client)
    assert r.status_code == 200, r.text
    assert r.json()["corrida"]["abortada"] is False
    assert db.corridas[0]["status"] == "ABERTA"


# ═════════════════ o portão da §11.1 (deploy parcial) ═══════════════════════

def test_motor_antigo_com_a_085_aplicada_nao_abre_e_responde_como_hoje(
        client, auth_operador, tmp_path):
    """§10/F3, aceite 6 — **a célula mais provável da matriz §11.1**.

    A etapa 7 (api/) do deploy.sh é automática e a 5 (dags/) é padrão-NÃO, então
    a API nova sobe sozinha o tempo todo. Se ela abrisse corrida aqui, o motor
    deployado não saberia vincular nem fechar: toda corrida ficaria aberta até o
    teto e, enquanto isso, bloquearia o disparo.

    A prova é de AUSÊNCIA: nenhuma linha e nenhuma chave `corrida` na resposta —
    "exatamente como hoje" é o payload de antes desta fase, não um payload novo
    com um aviso."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_antigo(tmp_path), \
            _patch_agora():
        _malha_com_inicio(client)
        r = _disparar(client)
    assert r.status_code == 200, r.text
    assert db.corridas == []
    assert "corrida" not in r.json()
    assert len(fake.chamadas) == 2         # o disparo em si não muda


def test_interruptor_desligado_nao_abre_corrida(client, auth_operador):
    """§11.2 — `malha_corrida_ativa = 0` é o gesto de rollback da spec inteira:
    com ele, nada abre e o disparo é o de sempre."""
    db = FakeDb(pipelines=_pipes(), config={mc.CHAVE_ATIVA: "0"})
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        r = _disparar(client)
    assert r.status_code == 200, r.text
    assert db.corridas == [] and "corrida" not in r.json()


def test_guardia_sem_heartbeat_nao_abre_corrida(client, auth_operador):
    """O arquivo do `dags/` prova o que está no DISCO; só o heartbeat prova que
    a guardiã daquele disco está RODANDO. DAG pausada, worker fora do ar e
    interruptor desligado no worker dão o mesmo estrago do motor antigo, e
    nenhum dos três aparece no arquivo."""
    db = FakeDb(pipelines=_pipes())
    db.config[mc.CHAVE_HEARTBEAT] = (
        AGORA_BANCO - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        r = _disparar(client)
    assert r.status_code == 200, r.text
    assert db.corridas == [] and "corrida" not in r.json()


def test_sem_a_085_o_disparo_responde_como_antes(client, auth_operador):
    """Banco sem a migration: a sonda devolve NULL e a API não toca em nada da
    085 — nem um `Invalid object name` no meio do gesto."""
    db = FakeDb(pipelines=_pipes(), com_085=False)
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        r = _disparar(client)
    assert r.status_code == 200, r.text
    assert "corrida" not in r.json() and len(fake.chamadas) == 2


def test_portao_fechado_nao_recusa_por_corrida_aberta(client, auth_operador,
                                                      tmp_path):
    """A recusa vale para a porta INTEIRA: com o portão fechado a API não abre,
    não expira e **também não recusa**.

    Recusar sem poder abrir nem expirar prenderia o operador a uma corrida que
    nada no ambiente sabe encerrar — o oposto do que a §11.1 pede."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_antigo(tmp_path), \
            _patch_agora():
        _malha_com_inicio(client)
        db.abrir_corrida("M1")
        r = _disparar(client)
    assert r.status_code == 200, r.text
    assert len(fake.chamadas) == 2
    assert db.abertas("M1")[0]["status"] == "ABERTA"   # intocada


# ═══════════════════ a porta de saída do operador (§6.8) ════════════════════

def _encerrar(client, corrida_id, motivo="carga refeita por fora", malha="M1"):
    return client.post(f"/malhas/{malha}/corridas/{corrida_id}/encerrar",
                       json={} if motivo is None else {"motivo": motivo})


def test_rotas_novas_registradas(client):
    caminhos = client.get("/openapi.json").json().get("paths", {})
    assert "/malhas/{malha_name}/corridas" in caminhos
    assert "/malhas/{malha_name}/corridas/{corrida_id}/encerrar" in caminhos


def test_encerrar_sem_acao_executar_403(client, auth_sem_executar):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        assert _encerrar(client, 1).status_code == 403


def test_encerrar_exige_motivo(client, auth_operador):
    """Motivo obrigatório: uma corrida cancelada sem razão registrada é um
    buraco no histórico justamente no dia em que algo deu errado."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        db.abrir_corrida("M1")
        r = _encerrar(client, 1, motivo="   ")
    assert r.status_code == 422
    assert "motivo" in r.json()["detail"].lower()
    assert db.corridas[0]["status"] == "ABERTA"


def test_encerrar_cancela_grava_quem_e_libera_o_disparo_na_hora(
        client, auth_operador):
    """§10/F3, aceite 4: `CANCELADA` + `fechada_por`, e o disparo volta a
    funcionar NA HORA — sem esperar a guardiã, sem esperar o teto."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        db.abrir_corrida("M1")
        assert _disparar(client).status_code == 422       # travado
        r = _encerrar(client, 1, motivo="reprocesso manual da carga")
        depois = _disparar(client)                        # destravado
    assert r.status_code == 200, r.text
    assert db.por_id(1)["status"] == "CANCELADA"
    assert db.por_id(1)["fechada_por"] == "manual:OPER1"
    assert "reprocesso manual da carga" in db.por_id(1)["motivo"]
    assert "OPER1" in db.por_id(1)["motivo"]
    assert "MALHA_CANCELADA" in db.tipos_de_evento()
    # Projeção EXPLÍCITA (§5.2): as colunas de EFEITO COLATERAL do ciclo são
    # memória interna da guardiã — publicá-las convidaria o front a derivar
    # estado delas, que é o que a spec proíbe.
    assert "falha_vista_em" not in r.json()["corrida"]
    assert "atraso_visto_em" not in r.json()["corrida"]
    # a resposta diz o que NÃO aconteceu — a dúvida que trava o operador
    assert r.json()["execucoes_interrompidas"] == 0
    assert "CONTINUAM rodando" in r.json()["aviso"]
    assert depois.status_code == 200, depois.text
    assert len(fake.chamadas) == 2


def test_encerrar_corrida_ja_fechada_422_nomeando_o_desfecho(client,
                                                             auth_operador):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        db.abrir_corrida("M1", status="CONCLUIDA")
        r = _encerrar(client, 1)
    assert r.status_code == 422
    assert "CONCLUIDA" in r.json()["detail"]


def test_encerrar_corrida_inexistente_404(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        r = _encerrar(client, 999)
    assert r.status_code == 404
    # O id sai do texto (Decisao 74) e entra uma frase de acao: ecoar "999"
    # nao ajuda quem digitou errado; dizer onde achar a corrida, sim.
    assert "escolha a corrida na lista" in r.json()["detail"]
    assert "#" not in r.json()["detail"]


def test_outra_ponta_fecha_no_vao_e_o_encerramento_recusa_sem_reescrever(
        client, auth_operador):
    """Decisão 8 — `UPDATE ... WHERE id = ? AND fechada_em IS NULL` com o
    `rowcount` de árbitro.

    A leitura que decidiu encerrar e o `UPDATE` são dois instantes; no vão a
    guardiã pode ter fechado a corrida como `CONCLUIDA` (ou outro operador a
    cancelou). Sem a guarda no `WHERE`, este gesto reescreveria o desfecho
    ALHEIO — a corrida sairia `CANCELADA` sobre um ciclo que terminou bem, com
    `fechada_por` trocado e o card mentindo em cima de um fato já registrado.
    `rowcount = 0` não é erro: é "outra ponta chegou primeiro", e a resposta
    manda recarregar."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        db.abrir_corrida("M1")

        def _guardia_fecha(d):
            alvo = d.por_id(1)
            alvo.update(status="CONCLUIDA", fechada_em=d.agora_banco,
                        fechada_por="guardia")

        db.ao_fechar = _guardia_fecha
        r = _encerrar(client, 1, motivo="ciclo travado")
    assert r.status_code == 422, r.text
    assert "outra ponta" in r.json()["detail"]
    assert "MALHA_CANCELADA" not in db.tipos_de_evento()


def test_encerrar_corrida_de_outra_malha_422(client, auth_operador):
    """A corrida é identificada pelo id (Decisão 7), mas o endpoint vive sob a
    malha: encerrar a corrida de OUTRA malha por um id digitado errado é o tipo
    de gesto que ninguém desfaz."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        _monta_malha(client, "M2", ["RAIZ_B"])
        db.abrir_corrida("M2")
        r = _encerrar(client, 1, malha="M1")
    assert r.status_code == 422
    assert "M2" in r.json()["detail"]
    assert db.corridas[0]["status"] == "ABERTA"


def test_encerrar_funciona_com_o_motor_antigo(client, auth_operador, tmp_path):
    """A saída de emergência não passa pelo portão do §11.1, de propósito: ela
    precisa funcionar exatamente nos ambientes em que o resto não funciona."""
    db = FakeDb(pipelines=_pipes(), config={mc.CHAVE_ATIVA: "0"})
    with _patch_db(db), _dags_antigo(tmp_path):
        _monta_malha(client, "M1", ["RAIZ_A"])
        db.abrir_corrida("M1")
        r = _encerrar(client, 1)
    assert r.status_code == 200, r.text
    assert db.por_id(1)["status"] == "CANCELADA"


def test_encerrar_sem_a_085_503_instrutivo(client, auth_operador):
    db = FakeDb(pipelines=_pipes(), com_085=False)
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        r = _encerrar(client, 1)
    assert r.status_code == 503
    assert "085" in r.json()["detail"]


# ═════════════════════════ GET /malhas/{m}/corridas ═════════════════════════

def test_lista_traz_as_DUAS_corridas_do_mesmo_odate(client, auth_operador):
    """§10/F3, aceite: duas corridas do mesmo ODATE (redisparo) são legítimas e
    a lista traz as duas, distinguidas por `sequencia` — é o que o ◀ ▶ da F4
    navega. Identidade continua sendo o `id` (Decisão 7)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        primeira = db.abrir_corrida("M1", status="CONCLUIDA")
        segunda = db.abrir_corrida("M1")
        r = client.get("/malhas/M1/corridas")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert [c["id"] for c in corpo["corridas"]] == [segunda["id"],
                                                    primeira["id"]]
    assert [c["sequencia"] for c in corpo["corridas"]] == [2, 1]
    assert corpo["aberta"]["id"] == segunda["id"]
    assert corpo["total"] == 2


def test_lista_recortada_por_data_ainda_mostra_a_corrida_aberta(
        client, auth_operador):
    """A corrida aberta é a única sobre a qual há um GESTO possível (encerrar);
    escondê-la atrás do recorte por data seria esconder o botão que destrava a
    malha."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        db.abrir_corrida("M1", odate=date(2026, 8, 1), status="CONCLUIDA")
        aberta = db.abrir_corrida("M1", odate=ODATE)
        r = client.get("/malhas/M1/corridas?data_referencia=2026-08-01")
    assert r.status_code == 200, r.text
    assert [c["data_referencia"] for c in r.json()["corridas"]] == ["2026-08-01"]
    assert r.json()["aberta"]["id"] == aberta["id"]


def test_lista_sem_a_085_degrada_vazia(client, auth_operador):
    """Leitura degrada LARGA: a falta do ciclo não pode tirar a tela do ar."""
    db = FakeDb(pipelines=_pipes(), com_085=False)
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        r = client.get("/malhas/M1/corridas")
    assert r.status_code == 200, r.text
    assert r.json()["corridas"] == []
    assert r.json()["migration_085_pendente"] is True


def test_lista_de_malha_inexistente_404(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        assert client.get("/malhas/NAO_EXISTE/corridas").status_code == 404


# ══════════════ §6.9/#13 — renomear com corrida aberta ══════════════════════

def test_rename_carimba_a_corrida_aberta_e_nao_deixa_orfa(client,
                                                          auth_operador):
    """§10/F3, aceite 5.

    Sem o carimbo, a corrida ficaria órfã sob um nome que não existe mais em
    `etl_malha` — ocupando o slot de `ux_malha_exec_aberta` para sempre, sem
    tela que a encontre para encerrar — e o nome novo nasceria sem corrida:
    DUPLA ABERTURA por construção."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        db.abrir_corrida("M1")
        r = client.patch("/malhas/M1", json={"novo_nome": "M1_NOVA"})
    assert r.status_code == 200, r.text
    assert r.json()["corridas_renomeadas"] == 1
    assert db.corridas[0]["malha_name"] == "M1_NOVA"
    assert db.abertas("M1") == []          # o nome antigo ficou livre
    assert len(db.abertas("M1_NOVA")) == 1


def test_rename_carimba_tambem_a_mudanca_so_de_caixa(client, auth_operador):
    """A colação do SQL Server é CI: sem o carimbo, a corrida ficaria com a
    grafia antiga e a tela mostraria dois nomes para a mesma malha."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        db.abrir_corrida("M1")
        r = client.patch("/malhas/M1", json={"novo_nome": "m1"})
    assert r.status_code == 200, r.text
    assert db.corridas[0]["malha_name"] == "m1"


def test_rename_nao_reescreve_o_nome_das_corridas_ja_fechadas(client,
                                                              auth_operador):
    """Só a corrida ABERTA acompanha o nome (§6.9/#13).

    As fechadas ficam com o nome de quando aconteceram: são HISTÓRICO, e
    reescrever histórico por causa de um gesto de cadastro é o oposto do que a
    076 decidiu ao derrubar a FK do evento. O preço — o `GET /corridas` do nome
    novo não mostra o que rodou sob o nome velho — é conhecido e aceito; o que
    não pode é o passado mudar de dono sozinho."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        antiga = db.abrir_corrida("M1", odate=date(2026, 8, 4),
                                  status="CONCLUIDA")
        em_voo = db.abrir_corrida("M1")
        r = client.patch("/malhas/M1", json={"novo_nome": "M1_NOVA"})
    assert r.status_code == 200, r.text
    assert r.json()["corridas_renomeadas"] == 1     # UMA, não duas
    assert db.por_id(em_voo["id"])["malha_name"] == "M1_NOVA"
    assert db.por_id(antiga["id"])["malha_name"] == "M1"


def test_rename_sem_corrida_aberta_responde_como_antes(client, auth_operador):
    """Chave ADITIVA: quem não tem ciclo em voo recebe a resposta de sempre,
    byte a byte."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        r = client.patch("/malhas/M1", json={"novo_nome": "M1_NOVA"})
    assert r.status_code == 200, r.text
    assert "corridas_renomeadas" not in r.json()


def test_rename_sem_a_085_nao_quebra(client, auth_operador):
    """Rename é gesto de CADASTRO: não pode virar 503 por causa de uma
    migration que este banco talvez nunca receba."""
    db = FakeDb(pipelines=_pipes(), com_085=False)
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        r = client.patch("/malhas/M1", json={"novo_nome": "M1_NOVA"})
    assert r.status_code == 200, r.text
    assert "corridas_renomeadas" not in r.json()


# ═══════ o que a API ESCREVE precisa ser o que o outro lado LÊ ══════════════

def test_o_marcador_do_evento_tem_a_MESMA_grafia_da_guardia():
    """`etl_dependencia_evento` é chaveada por PIPELINE, e a corrida não é um
    pipeline: as duas árvores gravam o marcador `#corrida:{id}` no lugar do
    nome. O painel da F4 resolve UM marcador — duas grafias fariam metade dos
    eventos sumir da tela, e a metade que some é justamente a que a API grava
    (cancelamento e aborto: os dois gestos de plantão).

    A comparação é TEXTUAL contra `dags/`, como nos testes de paridade: o
    container da API não embarca `dags/`, então importar de lá quebraria no
    primeiro deploy parcial — que é a célula mais provável da matriz §11.1."""
    from routers import malhas as router
    fonte = (Path(_RAIZ_DAGS) / "etl_dependencia_guardia.py").read_text(
        encoding="utf-8")
    assert f'MARCADOR_CORRIDA = "{router.MARCADOR_CORRIDA}"' in fonte


def test_os_eventos_que_a_API_grava_tem_estilo_e_proximo_passo_no_Teams():
    """Reusar `etl_dependencia_evento` é o que faz o alerta chegar ao Teams sem
    uma linha de mudança na guardiã — ela já drena todo evento sem
    `notificado_em`. Mas um tipo sem entrada em `ESTILO` cai no `_PADRAO`: às 3h
    o celular mostra "🔔 Alerta" âmbar com o subtítulo `#corrida:12` — cor de
    "atenção" para o evento mais grave do produto, e nenhuma pista de QUAL
    malha quebrou. E sem entrada em `ACAO_MALHA` o card não diz o próximo
    passo, que na maioria das noites é a única superfície que a pessoa vê.

    Os três tipos conferidos são os que ESTA árvore grava: cancelamento
    (operador), aborto (nenhuma raiz partiu) e expiração na porta."""
    import re
    fonte = (Path(_RAIZ_DAGS) / "utils/ds_teams.py").read_text(encoding="utf-8")
    for tipo in ("MALHA_CANCELADA", "MALHA_ABORTADA", "MALHA_EXPIRADA"):
        assert re.search(r'"%s":\s*\{"rotulo"' % tipo, fonte), f"{tipo}: ESTILO"
        assert re.search(r'"%s":\s*\(' % tipo, fonte), f"{tipo}: ACAO_MALHA"


# ═════════════ nenhuma conta de tempo em Python (Decisão 10) ════════════════

def test_a_porta_nao_faz_conta_de_tempo_em_python():
    """Prova por AUSÊNCIA, pela árvore sintática: nenhuma das funções da porta
    usa `datetime.now`, `date.today` ou `timedelta`.

    O relógio do disparo é o do BANCO — no dev o SQL Server está 3h à frente da
    API, e uma soma feita aqui daria "o teto vence daqui a 3h" numa corrida que
    para o banco já venceu. O `datetime.strptime` da validação de data fica de
    fora: ele lê um RÓTULO digitado, não mede tempo."""
    import ast
    import inspect
    from routers import malhas as router

    alvos = ("_expirar_na_porta", "_abrir_corrida_do_disparo",
             "_agora_do_banco", "_abortar_corrida_do_disparo",
             "_corrida_operavel", "encerrar_corrida")
    proibidos = {"now", "today", "utcnow", "timedelta"}
    for nome in alvos:
        fonte = inspect.getsource(getattr(router, nome))
        arvore = ast.parse(fonte.lstrip())
        for no in ast.walk(arvore):
            if isinstance(no, ast.Attribute):
                assert no.attr not in proibidos, (nome, no.attr)
            if isinstance(no, ast.Name):
                assert no.id not in proibidos, (nome, no.id)


# ═══════ o que a REVISÃO ADVERSARIAL encontrou (e o que o conserto trava) ════

def test_estado_ilegivel_NAO_expira_corrida_com_membro_vivo(client,
                                                            auth_operador):
    """Decisão 25 sob leitura que FALHA — o furo que a revisão da F3 achou.

    `mc.estado()` degrada LARGA: lock timeout em `etl_pipeline_execucao` (a
    maior tabela do schema, e às 3h a mais disputada) faz a função logar e
    devolver os baldes VAZIOS. Lido como "ninguém vivo", isso INVERTE a trava:
    a corrida com um pipeline `EXECUTANDO` saía EXPIRADA e o disparo partia por
    cima dele — e as linhas que terminassem depois carregariam id de corrida
    FECHADA, a mentira estável que nenhum refresh corrige.

    E é a única pergunta que enxerga o membro REMOVIDO da malha no meio do
    ciclo: `_bloqueios_do_ciclo` olha `etl_malha_pipeline` (o desenho de AGORA)
    e não vê `SAIU_DA_MALHA`. Perder essa pergunta em silêncio é perder a trava
    inteira, e é por isso que "não consegui perguntar" tem de recusar."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    original = FakeCur.execute

    def execute(self, sql, params=()):
        if " ".join(str(sql).split()).startswith(
                "SELECT m.pipeline_name, m.conta_para_fim"):
            raise RuntimeError(
                "[HY000] Lock request time out period exceeded. (1222)")
        return original(self, sql, params)

    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), \
            _patch_agora(), patch.object(FakeCur, "execute", execute):
        _malha_com_inicio(client)
        presa = db.abrir_corrida(
            "M1", aberta_em=AGORA_BANCO - timedelta(hours=25),
            membros=["SAIU_DA_MALHA"])
        db.execucoes.append({"pipeline": "SAIU_DA_MALHA",
                             "data_referencia": ODATE,
                             "execution_id": "run_v", "status": "EXECUTANDO",
                             "inicio": AGORA_BANCO - timedelta(hours=20),
                             "malha_execucao_id": presa["id"],
                             "substituida_em": None})
        r = _disparar(client)
    assert r.status_code == 422, r.text
    assert db.por_id(presa["id"])["status"] == "ABERTA"
    assert "MALHA_EXPIRADA" not in db.tipos_de_evento()
    # e NADA partiu por cima do ciclo em voo
    assert fake.chamadas == []


def test_excecao_antes_dos_triggers_nao_deixa_corrida_orfa(client,
                                                           auth_operador):
    """§6.9/#4 pela porta que faltava.

    O aborto cobria "todas as raízes falharam" — `falhas` cheia. Mas quando a
    exceção acontece ANTES do `try` por raiz (o cliente HTTP que não sobe),
    `falhas` fica VAZIA porque nem se chegou a tentar: o 500 subia e a corrida
    já COMMITADA ficava ABERTA sem nada que a originasse, recusando todo
    disparo desta malha até o teto de 24h. Mesmo estrago, outra porta."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              side_effect=RuntimeError("cliente HTTP fora")), \
            _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        r = _disparar(client)
    assert r.status_code == 500
    assert db.abertas("M1") == []
    assert db.corridas[0]["status"] == "ABORTADA"


def test_aborto_que_nao_passa_diz_ao_operador_o_que_fazer(client,
                                                          auth_operador):
    """A corrida ficou aberta e só um gesto humano a destrava — isso não pode
    existir apenas no log do servidor.

    Sem a frase, o plantonista lê "nenhuma raiz partiu", tenta de novo e leva
    um 422 de uma corrida que ele não sabe que existe. A regra da casa é frase
    de AÇÃO: o que aconteceu, por que, e o que a pessoa faz agora."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient(falhas={"RAIZ_A": 500, "RAIZ_B": 500})
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), \
            _patch_agora(), patch(
                "routers.malhas._abortar_corrida_do_disparo",
                return_value=None):
        _malha_com_inicio(client)
        r = _disparar(client)
    corpo = r.json()
    assert corpo["corrida"]["abortada"] is False
    orfa = [a for a in corpo["avisos"] if a.get("tipo") == "corrida_orfa"]
    assert len(orfa) == 1, corpo["avisos"]
    assert orfa[0]["nivel"] == "forte"
    assert "corrida de" in orfa[0]["mensagem"]   # Decisao 74: dia, nao id
    assert "#" not in orfa[0]["mensagem"]
    assert "Encerrar corrida" in orfa[0]["mensagem"]


def test_corrida_aberta_de_ODATE_antigo_nao_some_da_lista_paginada(
        client, auth_operador):
    """`aberta` é o botão que destrava a malha — ele não pode cair da página.

    A ordenação é `data_referencia DESC`, e a corrida aberta pode ser de um
    ODATE ANTIGO: reprocessar um dia anterior é gesto legítimo e diário (é para
    isso que o disparo aceita `data_referencia` no body). Com mais corridas do
    que o `limite`, essa corrida sai da página — e a releitura só acontecia
    quando havia recorte por data, então `aberta` vinha `null` e a F4 esconderia
    justamente o gesto possível."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        antiga = db.abrir_corrida("M1", odate=date(2026, 7, 1))
        for dia in range(1, 6):
            db.abrir_corrida("M1", odate=date(2026, 8, dia),
                             status="CONCLUIDA")
        r = client.get("/malhas/M1/corridas?limite=3")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert len(corpo["corridas"]) == 3
    assert antiga["id"] not in [c["id"] for c in corpo["corridas"]]
    assert corpo["aberta"] is not None and corpo["aberta"]["id"] == antiga["id"]


# ═══════ a sonda do `force_all` no disparo (F5/§12.2, risco 9) ══════════════
#
# A F5 é a única fase que exige regeração das DAGs, e o gesto NÃO está no
# deploy.sh. Enquanto ele não acontece, metade dos membros carimba o ODATE pela
# corrida e metade calcula sozinha — a doença com aparência de cura. O disparo
# AVISA (nunca recusa) e nomeia quem ficou para trás.
#
# A sonda em si (ler o fonte publicado) é provada contra ARQUIVOS DE VERDADE em
# tests/test_dag_factory_odate_corrida.py; aqui se prova a FIAÇÃO: quem chama,
# com que lista, e o que aparece na resposta.

def _sonda_fixa(mapa):
    """Substitui a sonda por uma resposta conhecida — a leitura de disco tem
    teste próprio, e reproduzi-la aqui provaria o dublê duas vezes."""
    import services.espera as esp_svc
    return patch.object(
        esp_svc, "carimbo_corrida_dos_pipelines",
        side_effect=lambda cur, pipelines: [
            {"pipeline": p, "sonda": mapa.get(p, esp_svc.CORRIDA_OK)}
            for p in pipelines])


def test_disparo_avisa_membro_sem_o_carimbo_e_NAO_recusa(client, auth_operador):
    """O membro com a DAG velha calcula a própria data em vez de aderir ao
    ciclo — é o `Carga_Vida` invertido do §7, e o operador precisa saber ANTES
    de confirmar. Aviso FORTE; o gesto continua sendo dele."""
    import services.espera as esp_svc
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora(), \
            _sonda_fixa({"PIPE_MEIO": esp_svc.CORRIDA_AUSENTE}):
        _malha_com_inicio(client)
        r = _disparar(client)
    assert r.status_code == 200, r.text
    corpo = r.json()
    aviso = [a for a in corpo["avisos"] if a.get("tipo") == "sem_carimbo_odate"]
    assert len(aviso) == 1 and aviso[0]["nivel"] == "forte"
    assert "PIPE_MEIO" in aviso[0]["mensagem"]
    # ADITIVO: as duas colunas do §12.2, e SÓ quem não está OK
    assert corpo["carimbo_odate"] == [{"pipeline": "PIPE_MEIO",
                                       "sonda": esp_svc.CORRIDA_AUSENTE}]
    assert fake.chamadas, "o disparo AVISA, nunca recusa"


def test_a_sonda_cobre_todo_MEMBRO_e_nao_so_as_raizes(client, auth_operador):
    """Quem calcula a própria data no meio da malha é justamente o membro com
    cron próprio — cobrir só as raízes deixaria de fora o caso do incidente."""
    import services.espera as esp_svc
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora(), \
            _sonda_fixa({}) as sonda:
        _malha_com_inicio(client)
        _disparar(client)
    pedidos = sonda.call_args[0][1]
    assert set(pedidos) >= {"RAIZ_A", "RAIZ_B", "PIPE_MEIO"}


def test_DESCONHECIDO_vira_aviso_LEVE_com_frase_propria(client, auth_operador):
    """Não conseguir ler o fonte não prova nada sobre ele: a frase é de dúvida,
    não de acusação, e o nível é leve."""
    import services.espera as esp_svc
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora(), \
            _sonda_fixa({"RAIZ_A": esp_svc.CORRIDA_DESCONHECIDO}):
        _malha_com_inicio(client)
        r = _disparar(client)
    corpo = r.json()
    assert [a for a in corpo["avisos"] if a.get("tipo") == "sem_carimbo_odate"] == []
    incerto = [a for a in corpo["avisos"] if a.get("tipo") == "carimbo_incerto"]
    assert len(incerto) == 1 and incerto[0]["nivel"] == "leve"
    assert "não foi possível conferir" in incerto[0]["mensagem"]


def test_malha_toda_regerada_nao_gera_aviso_nenhum(client, auth_operador):
    """Aviso que aparece sempre deixa de ser lido: com todo mundo em dia, nem
    aviso nem a chave aditiva na resposta."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora(), \
            _sonda_fixa({}):
        _malha_com_inicio(client)
        r = _disparar(client)
    corpo = r.json()
    assert "carimbo_odate" not in corpo
    assert [a for a in corpo["avisos"]
            if a.get("tipo") in ("sem_carimbo_odate", "carimbo_incerto")] == []


def test_interruptor_desligado_nao_sonda_nada(client, auth_operador):
    """Com a corrida em 0, ninguém carimba ODATE pela corrida — dizer "sua DAG
    não tem o carimbo" seria ruído puro, e ruído em todo disparo ensina a
    operação a ignorar a caixa de avisos inteira."""
    db = FakeDb(pipelines=_pipes(), config={mc.CHAVE_ATIVA: "0"})
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora(), \
            _sonda_fixa({}) as sonda:
        _malha_com_inicio(client)
        r = _disparar(client)
    assert r.status_code == 200, r.text
    assert sonda.call_count == 0


def test_a_sonda_que_QUEBRA_nao_impede_o_disparo(client, auth_operador):
    """A sonda é DIAGNÓSTICO, nunca porta. Ela lê arquivo do disco — permissão,
    disco cheio, `DAGS_FOLDER` errado no ambiente — e nada disso pode virar
    "a malha não parte". O comentário no router promete exatamente isso; sem
    teste, a promessa é uma frase."""
    import services.espera as esp_svc
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora(), \
            patch.object(esp_svc, "carimbo_corrida_dos_pipelines",
                         side_effect=OSError("permissao negada em generated/")):
        _malha_com_inicio(client)
        r = _disparar(client)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert fake.chamadas, "a sonda quebrou e o disparo parou junto"
    assert "carimbo_odate" not in corpo
    assert [a for a in corpo["avisos"]
            if a.get("tipo") in ("sem_carimbo_odate", "carimbo_incerto")] == []
