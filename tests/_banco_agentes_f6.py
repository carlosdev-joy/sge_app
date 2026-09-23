"""Banco em memória para os testes da F6 (aprendizados + curadoria).

Estende o dublê da F5 (`_banco_agentes_f5.BancoF5`, que já tem fatos,
propostas e transação com commit/rollback) com o SQL que
`services/agentes_aprendizado.py` emite. `agora` pode ser deslocado para
provar o vencimento de `revalidar_em`.
"""
from __future__ import annotations

import copy
import datetime as dt

from tests._banco_agentes_f5 import BancoF5, _Cursor

_COLS = ("id", "tipo", "titulo", "corpo", "evidencia", "origem", "estado", "criado_em", "validado_por",
         "validado_em", "ultimo_uso_em", "usos", "revalidar_em")


class BancoF6(BancoF5):
    def __init__(self):
        self.aprendizados: dict[int, dict] = {}
        self._seq_ap = 0
        self.deslocamento = dt.timedelta(0)
        super().__init__()

    def agora(self):
        return dt.datetime.now() + self.deslocamento

    def _fixar(self):
        super()._fixar()
        self._salvo_ap = copy.deepcopy((self.aprendizados, self._seq_ap))

    def rollback(self):
        super().rollback()
        self.aprendizados, self._seq_ap = copy.deepcopy(self._salvo_ap)

    def cursor(self):
        return _CursorF6(self)

    def novo_aprendizado(self, *, estado="validado", origem="interpretacao", tipo="leitura", agente="datastage",
                         titulo="t", corpo="c", assinatura=None, revalidar_em=None, usos=1) -> int:
        self._seq_ap += 1
        i = self._seq_ap
        self.aprendizados[i] = {
            "id": i, "agente": agente, "tipo": tipo, "assinatura": assinatura or f"{i:064d}", "titulo": titulo,
            "corpo": corpo, "evidencia": "ev", "origem": origem, "estado": estado, "criado_em": self.agora(),
            "validado_por": None, "validado_em": None, "ultimo_uso_em": None, "usos": usos,
            "revalidar_em": revalidar_em}
        self._fixar()
        return i

    def por_assinatura(self, assinatura: str) -> dict | None:
        return next((a for a in self.aprendizados.values() if a["assinatura"] == assinatura), None)


class _CursorF6(_Cursor):
    def _linha(self, a):
        return tuple(a[c] for c in _COLS)

    def _vigente(self, a):
        return a["revalidar_em"] is None or a["revalidar_em"] > self.b.agora()

    def execute(self, sql, params=None):
        b = self.b
        p = list(params or ())
        s = " ".join(sql.lower().split())
        if "etl_agente_aprendizado" not in s and "agente_aprendizado:" not in str(p[:1]):
            return super().execute(sql, params)
        b.execs.append((sql, tuple(p)))
        self._rows, self.rowcount = [], -1
        agora = b.agora()

        def mais(dias):
            return None if dias is None else agora + dt.timedelta(days=dias)

        if "sp_getapplock" in s:
            self._rows = [(0,)]
        elif s.startswith("update dbo.etl_agente_aprendizado set usos = usos + 1, estado = case"):
            titulo, corpo, evid, dias, _d2, agente, ass = p
            alvo = [a for a in b.aprendizados.values() if a["agente"] == agente and a["assinatura"] == ass]
            for a in alvo:
                a["usos"] += 1
                if a["estado"] != "rejeitado":
                    a["estado"] = "validado"
                a.update(titulo=titulo, corpo=corpo, evidencia=evid, revalidar_em=mais(dias))
            self.rowcount = len(alvo)
        elif s.startswith("update dbo.etl_agente_aprendizado set usos = usos + 1 where"):
            agente, ass = p
            alvo = [a for a in b.aprendizados.values() if a["agente"] == agente and a["assinatura"] == ass]
            for a in alvo:
                a["usos"] += 1
            self.rowcount = len(alvo)
        elif s.startswith("insert into dbo.etl_agente_aprendizado"):
            agente, tipo, ass, titulo, corpo, evid, origem, estado, dias, _d2 = p
            if any(a["agente"] == agente and a["assinatura"] == ass for a in b.aprendizados.values()):
                raise AssertionError("UNIQUE (agente, assinatura) violada")
            b._seq_ap += 1
            b.aprendizados[b._seq_ap] = {
                "id": b._seq_ap, "agente": agente, "tipo": tipo, "assinatura": ass, "titulo": titulo,
                "corpo": corpo, "evidencia": evid, "origem": origem, "estado": estado, "criado_em": agora,
                "validado_por": None, "validado_em": None, "ultimo_uso_em": None, "usos": 1,
                "revalidar_em": mais(dias)}
        elif s.startswith("select id, titulo, corpo from dbo.etl_agente_aprendizado"):
            agente, ass = p
            self._rows = [(a["id"], a["titulo"], a["corpo"]) for a in b.aprendizados.values()
                          if a["agente"] == agente and a["assinatura"] == ass and a["tipo"] == "erro"
                          and a["estado"] == "validado" and self._vigente(a)]
        elif s.startswith("select top (?) id, tipo, titulo, corpo, origem, usos"):
            limite, agente = p
            vig = [a for a in b.aprendizados.values()
                   if a["agente"] == agente and a["estado"] == "validado" and self._vigente(a)
                   and not (a["tipo"] == "erro" and a["origem"] == "ferramenta")]
            vig.sort(key=lambda a: (a["usos"], a["id"]), reverse=True)
            self._rows = [(a["id"], a["tipo"], a["titulo"], a["corpo"], a["origem"], a["usos"]) for a in vig][:limite]
        elif s.startswith("update dbo.etl_agente_aprendizado set ultimo_uso_em"):
            b.aprendizados[p[0]]["ultimo_uso_em"] = agora
        elif s.startswith("select top (200)"):
            agente, estado = p
            self._rows = [self._linha(a) for a in b.aprendizados.values()
                          if a["agente"] == agente and a["estado"] == estado]
        elif s.startswith("update dbo.etl_agente_aprendizado set estado = 'validado'"):
            mat, i, agente, *origens = p
            a = b.aprendizados.get(i)
            if a and a["agente"] == agente and a["estado"] in origens:
                a.update(estado="validado", validado_por=mat, validado_em=agora,
                         revalidar_em=mais(7) if a["tipo"] == "erro" and a["origem"] == "ferramenta" else None)
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif s.startswith("update dbo.etl_agente_aprendizado set estado = ?"):
            destino, mat, i, agente, *origens = p
            a = b.aprendizados.get(i)
            if a and a["agente"] == agente and a["estado"] in origens:
                a.update(estado=destino, validado_por=mat, validado_em=agora)
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif "from dbo.etl_agente_aprendizado where id = ? and agente = ?" in s:
            a = b.aprendizados.get(p[0])
            self._rows = [self._linha(a)] if a and a["agente"] == p[1] else []
        else:
            raise AssertionError(f"SQL de aprendizado não previsto pelo dublê: {sql}")
