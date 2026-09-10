---
name: gotcha-nvarchar-utf16
description: "⚠️ GOTCHA SQL Server: NVARCHAR(n) conta unidades UTF-16, Python len() conta code points — validar/cortar com len()/[:n] deixa emoji estourar a coluna; em auditoria best-effort a linha SOME em silêncio"
metadata: 
  node_type: memory
  type: project
  originSessionId: 97a32f84-3b42-4486-82ed-a61083d760aa
  modified: 2026-09-03T04:25:52.625Z
---

**Sintoma:** validação `len(s) <= 1000` passa, o `INSERT` numa coluna `NVARCHAR(1000)`
falha com "String or binary data would be truncated" — e, se o INSERT é best-effort
(auditoria dentro de try/except), a linha simplesmente **não existe**. Foi achado pela
revisão adversarial da F1 dos Utilitários do Orquestra (2026-09-03): um caminho com 600
emojis tinha 610 code points e 1.210 unidades UTF-16 → a auditoria de uma tentativa de
traversal sumia.

**Causa:** `NVARCHAR(n)` mede em unidades UTF-16 (caractere fora do BMP = 2 unidades);
`len()` e fatias `[:n]` em Python medem code points.

**Como aplicar:** medir e cortar em UTF-16 —
`len(s.encode("utf-16-le", errors="surrogatepass")) // 2` para medir, e cortar os bytes
em `n*2` descartando uma metade alta de par substituto que sobre no fim (senão o decode
parte um emoji). Implementação de referência: `utf16_len`/`cortar_utf16` em
`api/services/ssh_arquivos.py` do [[orquestra-sge-app]]. Vale para QUALQUER coluna
NVARCHAR alimentada por entrada de usuário (caminhos, nomes, mensagens, detalhes de log).
Detalhe irmão: `NAME_MAX` do Linux (255) é em **bytes UTF-8** — outra régua ainda.

Ver [[orquestra-spec-utilitarios-arquivos]].
