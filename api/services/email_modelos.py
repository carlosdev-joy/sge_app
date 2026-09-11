"""api/services/email_modelos.py — o catálogo de modelos de e-mail
(`dbo.etl_email_modelo`, migration 112; spec docs/spec-email-modelos-e-navegacao.md).

O modelo é o **layout institucional**: cabeçalho, cores, estrutura. O nó guarda
só o `modelo_id` e o corpo é lido no envio, então trocar o layout aqui vale
para todos os nós sem republicar DAG nem reeditar nó.

⚠️ Duas regras que existem por causa do catálogo de cards do Teams, onde
template apagado ou desativado faz o envio cair em silêncio para a mensagem
embutida:
  * **apagar modelo em uso é recusado** (quem chama responde 409 nomeando os
    pipelines) — desativar é sempre permitido e não afeta quem já usa;
  * **modelo que sumiu faz a etapa falhar** no worker, nunca degrada calado.
"""
from __future__ import annotations

from services import email_mime as em
from services.ssh_arquivos import utf16_len

LIMITE_NOME = 120
LIMITE_DESCRICAO = 400
CAMPOS = ("id", "nome", "descricao", "assunto", "corpo", "html", "ativo", "padrao",
          "criado_por", "criado_em", "atualizado_em")

_SELECT = (
    "SELECT id, nome, descricao, assunto, corpo, CAST(html AS INT), CAST(ativo AS INT), "
    "CAST(padrao AS INT), criado_por, CONVERT(VARCHAR(19), criado_em, 120), "
    "CONVERT(VARCHAR(19), atualizado_em, 120) FROM dbo.etl_email_modelo ")


def _linha(r) -> dict:
    d = dict(zip(CAMPOS, r))
    for b in ("html", "ativo", "padrao"):
        d[b] = bool(d[b])
    return d


def tabela_existe(cur) -> bool:
    """Sem a 112 o catálogo não existe — a tela diz isso em vez de quebrar."""
    cur.execute("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_email_modelo'")
    return bool(cur.fetchone()[0])


def listar(cur, *, apenas_ativos: bool = False, com_corpo: bool = True) -> list[dict]:
    cur.execute(_SELECT + ("WHERE ativo = 1 " if apenas_ativos else "")
                + "ORDER BY padrao DESC, nome")
    modelos = [_linha(r) for r in cur.fetchall()]
    if not com_corpo:
        # A lista do Admin não precisa do HTML inteiro de cada modelo; só o
        # tamanho, para a tela mostrar o peso sem trafegar tudo.
        for m in modelos:
            m["corpo_tamanho"] = len(m["corpo"] or "")
            m.pop("corpo", None)
    return modelos


def obter(cur, modelo_id: int) -> dict | None:
    cur.execute(_SELECT + "WHERE id = ?", (int(modelo_id),))
    r = cur.fetchone()
    return _linha(r) if r else None


def validar(body) -> tuple[dict, list[str]]:
    """O que o admin manda → (valores normalizados, erros).

    O corpo passa pela MESMA régua do nó (`validar_corpo`): um modelo que o
    envio recusaria não pode entrar no catálogo e quebrar N fluxos de uma vez.
    """
    erros: list[str] = []
    if not isinstance(body, dict):
        return {}, ["corpo inválido"]

    nome = str(body.get("nome") or "").strip()
    if not nome:
        erros.append("informe o nome do modelo")
    # NVARCHAR conta UTF-16: `len()` deixaria 100 emoji (200 unidades) passar a
    # régua e estourar a coluna no INSERT, virando 500 opaco em vez de 422.
    elif utf16_len(nome) > LIMITE_NOME:
        erros.append(f"nome com mais de {LIMITE_NOME} caracteres")
    elif not em._sem_quebra(nome):
        erros.append("o nome não pode ter quebra de linha")

    descricao = str(body.get("descricao") or "").strip()
    if utf16_len(descricao) > LIMITE_DESCRICAO:
        erros.append(f"descrição com mais de {LIMITE_DESCRICAO} caracteres")

    # Assunto do modelo é SUGESTÃO (o nó é dono do seu), por isso pode ser vazio
    # — mas, quando vier, passa pela régua do assunto de verdade.
    assunto = str(body.get("assunto") or "").strip()
    if assunto:
        _, erro = em.validar_assunto(assunto)
        if erro:
            erros.append(f"assunto sugerido: {erro}")

    corpo, erro = em.validar_corpo(body.get("corpo"))
    if erro:
        erros.append(erro)

    for campo in ("html", "ativo", "padrao"):
        if body.get(campo) is not None and not isinstance(body.get(campo), bool):
            erros.append(f"'{campo}' deve ser verdadeiro ou falso")

    valores = {
        "nome": nome,
        "descricao": descricao or None,
        "assunto": assunto or None,
        "corpo": corpo or "",
        "html": True if body.get("html") is None else bool(body.get("html")),
        "ativo": True if body.get("ativo") is None else bool(body.get("ativo")),
        "padrao": bool(body.get("padrao")),
    }
    return valores, erros


def _zerar_padrao(cur, exceto_id: int | None = None) -> None:
    """No máximo um padrão. Sem índice filtrado de propósito: o repo já tem o
    gotcha de índice filtrado × QUOTED_IDENTIFIER quebrando DML pelo sqlcmd."""
    if exceto_id is None:
        cur.execute("UPDATE dbo.etl_email_modelo SET padrao = 0 WHERE padrao = 1")
    else:
        cur.execute("UPDATE dbo.etl_email_modelo SET padrao = 0 WHERE padrao = 1 AND id <> ?",
                    (int(exceto_id),))


def criar(cur, valores: dict, criado_por: str) -> int:
    if valores.get("padrao"):
        _zerar_padrao(cur)
    cur.execute(
        "INSERT INTO dbo.etl_email_modelo (nome, descricao, assunto, corpo, html, ativo, padrao, criado_por) "
        "OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?)",
        (valores["nome"], valores["descricao"], valores["assunto"], valores["corpo"],
         1 if valores["html"] else 0, 1 if valores["ativo"] else 0,
         1 if valores["padrao"] else 0, (criado_por or "")[:100]))
    return int(cur.fetchone()[0])


def atualizar(cur, modelo_id: int, valores: dict) -> None:
    if valores.get("padrao"):
        _zerar_padrao(cur, exceto_id=modelo_id)
    cur.execute(
        "UPDATE dbo.etl_email_modelo SET nome=?, descricao=?, assunto=?, corpo=?, html=?, "
        "ativo=?, padrao=?, atualizado_em=GETDATE() WHERE id=?",
        (valores["nome"], valores["descricao"], valores["assunto"], valores["corpo"],
         1 if valores["html"] else 0, 1 if valores["ativo"] else 0,
         1 if valores["padrao"] else 0, int(modelo_id)))


def pipelines_que_usam(cur, modelo_id: int) -> list[str]:
    """Quem referencia este modelo em `notify_json`, para a trava de exclusão.

    A busca é por texto no JSON porque o vínculo mora dentro da coluna, não em
    FK (o SQL Server desta instalação pode ser anterior ao `JSON_VALUE`).

    ⚠️ Os padrões terminam no DELIMITADOR — `,` ou `}` — e não no número. Sem
    isso, `"modelo_id": 4` casaria com `"modelo_id": 40`, e o admin veria a
    exclusão do modelo 4 recusada nomeando fluxos que usam o 40. Ids de dois
    dígitos são o caso normal: o IDENTITY não reaproveita número.

    Falha de leitura PROPAGA. Devolver lista vazia aqui diria "não está em uso"
    e deixaria apagar um modelo que N fluxos usam — o mesmo erro que o repo já
    documenta em outro ponto do register."""
    mid = int(modelo_id)
    padroes = [f'%"modelo_id": {mid},%', f'%"modelo_id":{mid},%',
               f'%"modelo_id": {mid}}}%', f'%"modelo_id":{mid}}}%']
    cur.execute(
        "SELECT DISTINCT pipeline_name FROM dbo.etl_pipeline_job "
        "WHERE job_type = 'email' AND notify_json IS NOT NULL "
        "  AND (notify_json LIKE ? OR notify_json LIKE ? "
        "    OR notify_json LIKE ? OR notify_json LIKE ?) "
        "ORDER BY pipeline_name", tuple(padroes))
    return [r[0] for r in cur.fetchall()]


def excluir(cur, modelo_id: int) -> None:
    cur.execute("DELETE FROM dbo.etl_email_modelo WHERE id = ?", (int(modelo_id),))
