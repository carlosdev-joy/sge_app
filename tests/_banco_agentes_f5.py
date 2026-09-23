"""Banco em memória para os testes da F5 (fatos e propostas do agente).

Entende SÓ os comandos que `services/agentes_conhecimento.py` emite, pelo
trecho do SQL — o mesmo estilo dos outros dublês de agentes, mas com ESTADO
e TRANSAÇÃO: `commit` fixa, `rollback` volta ao último commit. É isso que
permite provar "aprovar 2× gera 1 fato" e "recusar não grava nada" sem um
SQL Server de verdade (a conferência no SQL Server real é feita à parte).
"""
from __future__ import annotations

import copy
import datetime as dt


class BancoF5:
    def __init__(self):
        self.fatos: list[dict] = []
        self.propostas: dict[int, dict] = {}
        self._seq_fato = 0
        self._seq_prop = 0
        self._salvo = None
        self.commits = 0
        self.rollbacks = 0
        self.execs: list[tuple[str, tuple]] = []
        self._fixar()

    # ── transação ────────────────────────────────────────────────────────
    def _fixar(self):
        self._salvo = copy.deepcopy((self.fatos, self.propostas, self._seq_fato, self._seq_prop))

    def commit(self):
        self.commits += 1
        self._fixar()

    def rollback(self):
        self.rollbacks += 1
        self.fatos, self.propostas, self._seq_fato, self._seq_prop = copy.deepcopy(self._salvo)

    def close(self):
        pass

    def cursor(self):
        return _Cursor(self)

    def abrir(self):
        """Fábrica `() -> (conn, cur)` no formato que `services.agentes` usa."""
        return self, self.cursor()

    # ── consultas de conveniência para os testes ─────────────────────────
    def vigentes(self, **filtro) -> list[dict]:
        return [f for f in self.fatos if f["obsoleto_em"] is None
                and all(f.get(k) == v for k, v in filtro.items())]

    def nova_proposta(self, *, matricula="DEV1", estado="pendente", idade_dias=0, **campos) -> int:
        self._seq_prop += 1
        pid = self._seq_prop
        base = {"id": pid, "conversa_id": "conv-00000001", "agente": "datastage", "matricula": matricula,
                "ds_project": "BI_CVP", "job_name": "JobX", "tipo": "descricao", "chave": "job",
                "valor_json": '"carrega clientes"', "evidencia": "stage LerClientes", "motivo": "m",
                "estado": estado, "criada_em": dt.datetime.now() - dt.timedelta(days=idade_dias),
                "decidida_por": None, "decidida_em": None, "fato_id": None}
        base.update(campos)
        self.propostas[pid] = base
        self._fixar()
        return pid


_COLS = ("id", "ds_project", "job_name", "tipo", "chave", "valor_json", "evidencia", "motivo", "estado",
         "criada_em", "decidida_por", "decidida_em", "fato_id")


class _Cursor:
    def __init__(self, banco: BancoF5):
        self.b = banco
        self._rows: list = []
        self.rowcount = -1

    def close(self):
        pass

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def _linha_prop(self, p, extra=()):
        return tuple(p[c] for c in _COLS) + tuple(extra)

    def execute(self, sql, params=None):
        b = self.b
        p = list(params or ())
        b.execs.append((sql, tuple(p)))
        s = " ".join(sql.lower().split())
        self._rows, self.rowcount = [], -1
        agora = dt.datetime.now()

        if "sp_getapplock" in s:
            self._rows = [(0,)]
        # ── fatos ────────────────────────────────────────────────────────
        elif s.startswith("select id, tipo, chave, valor_json from dbo.etl_agente_fato"):
            proj, job, origem = p
            self._rows = [(f["id"], f["tipo"], f["chave"], f["valor_json"]) for f in b.fatos
                          if f["ds_project"] == proj and f["job_name"] == job and f["origem"] == origem
                          and f["obsoleto_em"] is None]
        elif s.startswith("update dbo.etl_agente_fato set lido_em"):
            lido_por, evid, lm, pipeline, fid = p
            for f in b.fatos:
                if f["id"] == fid:
                    f.update(lido_em=agora, lido_por=lido_por, evidencia=evid, ds_last_modified=lm,
                             pipeline_name=pipeline)
        elif s.startswith("update dbo.etl_agente_fato set obsoleto_em = getdate() where id"):
            for f in b.fatos:
                if f["id"] == p[0]:
                    f["obsoleto_em"] = agora
        elif s.startswith("update dbo.etl_agente_fato set obsoleto_em = getdate() where ds_project"):
            proj, job, tipo, chave, origem = p
            for f in b.fatos:
                if (f["ds_project"], f["job_name"], f["tipo"], f["chave"], f["origem"]) == (
                        proj, job, tipo, chave, origem) and f["obsoleto_em"] is None:
                    f["obsoleto_em"] = agora
        elif s.startswith("insert into dbo.etl_agente_fato"):
            b._seq_fato += 1
            if "aprovado_por" in s:
                proj, job, tipo, chave, valor, origem, evid, lido_por, aprovado_por = p
                pipeline, lm, aprovado_em = None, None, agora
            else:
                proj, job, pipeline, tipo, chave, valor, origem, evid, lm, lido_por = p
                aprovado_por = aprovado_em = None
            b.fatos.append({"id": b._seq_fato, "ds_project": proj, "job_name": job, "pipeline_name": pipeline,
                            "tipo": tipo, "chave": chave, "valor_json": valor, "origem": origem,
                            "evidencia": evid, "ds_last_modified": lm, "lido_em": agora,
                            "lido_por": lido_por, "aprovado_por": aprovado_por,
                            "aprovado_em": aprovado_em, "obsoleto_em": None})
            if "output inserted.id" in s:
                self._rows = [(b._seq_fato,)]
        elif s.startswith("select top (?) tipo, chave, valor_json, origem"):
            limite, proj, job = p
            vig = [f for f in b.fatos if f["ds_project"] == proj and f["job_name"] == job
                   and f["obsoleto_em"] is None]
            # o mesmo ORDER BY do SQL: interpretação aprovada por último
            vig.sort(key=lambda f: (f["origem"] == "interpretacao_aprovada", f["origem"], f["tipo"], f["chave"]))
            self._rows = [(f["tipo"], f["chave"], f["valor_json"], f["origem"], f["ds_last_modified"],
                           (agora - f["lido_em"]).days, f["aprovado_por"], f["aprovado_em"])
                          for f in vig][:limite]
        # ── propostas ────────────────────────────────────────────────────
        elif s.startswith("insert into dbo.etl_agente_proposta"):
            conv, agente, mat, proj, job, tipo, chave, valor, evid, motivo = p
            b._seq_prop += 1
            b.propostas[b._seq_prop] = {
                "id": b._seq_prop, "conversa_id": conv, "agente": agente, "matricula": mat,
                "ds_project": proj, "job_name": job, "tipo": tipo, "chave": chave, "valor_json": valor,
                "evidencia": evid, "motivo": motivo, "estado": "pendente", "criada_em": agora,
                "decidida_por": None, "decidida_em": None, "fato_id": None}
            self._rows = [(b._seq_prop, agora)]
        elif "from dbo.etl_agente_proposta with (updlock, holdlock) where id" in s:
            prop = b.propostas.get(p[0])
            self._rows = [self._linha_prop(prop, (prop["matricula"], (agora - prop["criada_em"]).days))] \
                if prop else []
        elif s.startswith("update dbo.etl_agente_proposta set estado = 'expirada'"):
            prop = b.propostas.get(p[0])
            if prop and prop["estado"] == "pendente":
                prop["estado"] = "expirada"
        elif s.startswith("update dbo.etl_agente_proposta set estado = ?"):
            estado, por, pid, mat = p
            prop = b.propostas.get(pid)
            if prop and prop["matricula"] == mat and prop["estado"] == "pendente":
                prop.update(estado=estado, decidida_por=por, decidida_em=agora)
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif s.startswith("update dbo.etl_agente_proposta set fato_id"):
            fid, pid = p
            b.propostas[pid]["fato_id"] = fid
        elif "from dbo.etl_agente_proposta where conversa_id = ? and matricula = ?" in s:
            conv, mat = p
            self._rows = [self._linha_prop(x) for x in sorted(b.propostas.values(), key=lambda x: x["id"])
                          if x["conversa_id"] == conv and x["matricula"] == mat]
        elif "from dbo.etl_agente_proposta where id = ?" in s:
            prop = b.propostas.get(p[0])
            self._rows = [self._linha_prop(prop)] if prop else []
        else:
            raise AssertionError(f"SQL não previsto pelo dublê: {sql}")
