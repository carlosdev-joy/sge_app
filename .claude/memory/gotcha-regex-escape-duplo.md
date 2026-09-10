---
name: gotcha-regex-escape-duplo
description: "GOTCHA transversal: regex literal com escape duplo (/\\\\d/, /\\\\D/) passa tsc+lint+build e nunca casa — falso verde clássico em código escrito via heredoc/string"
metadata: 
  node_type: memory
  type: project
  originSessionId: a34cdce7-292c-458c-a7e9-8860d9d70f07
  modified: 2026-08-14T09:30:51.983Z
---

Num regex **literal** de JS/TS, `\\d` significa "uma barra invertida literal seguida de d" — não
um dígito. Então `/^\\d{4}-\\d{2}$/.test("2026-08")` é `false` e `String(x).replace(/\\D/g,"")`
não remove nada. **`tsc --noEmit`, o eslint e o `next build` passam todos** — a regex é
sintaticamente válida, só semanticamente errada. É falso verde puro: a tela aceita o valor, a
gravação "dá certo", e o campo chega nulo/sujo no banco.

Onde nasce: código escrito por agente através de heredoc, string escapada ou JSON, onde a barra
sobrevive duplicada na gravação do arquivo. O escape duplo só é correto dentro de
`new RegExp("\\d")` (string), nunca no literal `/.../`.

**Como caçar antes do merge** (rodar na branch, não só no diff renderizado):

```bash
for f in $(git diff --name-only origin/main...HEAD); do
  git show "HEAD:$f" | grep -n '\\\\[dDwWsSbn]' | sed "s|^|$f:|"
done
```

Se o padrão não existe no `main` e aparece só na branch, é regressão introduzida — foi assim que
identifiquei os 2 casos da PR #45 do NexxaFarma (ver [[nexxafarma-cadastro-mestre-iqvia]]).
No diff do `git`, a linha removida serve de contraprova: ali aparecia `/\D/g` correto.

Validar a correção sem subir a app: `node -e '/* teste do literal */'` — a técnica de validar
front sem runtime já usada em [[orquestra-caixa-seguro-poc]].

Parente próximo: [[orquestra-modos-de-falso-verde]] (catálogo de testes que passam com o defeito
intacto).
