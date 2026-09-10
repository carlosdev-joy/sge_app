---
name: gotcha-tsc-noemit-nao-checa
description: "No ui-react do Orquestra, `npx tsc --noEmit` sai 0 sem checar arquivo nenhum — o verificador de verdade é `tsc -b`"
metadata: 
  node_type: memory
  type: project
  originSessionId: 80eeec2c-39eb-4217-a273-e34383d916bf
  modified: 2026-08-28T18:18:11.006Z
---

Em `/opt/orquestra-dev/ui-react` (template Vite), o `tsconfig.json` raiz é só um
roteador:

```json
{ "files": [], "references": [{ "path": "./tsconfig.app.json" },
                              { "path": "./tsconfig.node.json" }] }
```

Com `"files": []`, **`npx tsc --noEmit` não olha um único arquivo e sai 0**. É
falso verde silencioso: em 2026-08-28 ele aprovou um `<ExternalLink />` usado
**sem import** em `pages/ChamadosDashboard.tsx`. O `eslint` também não pegou
(`no-undef` fica desligado em projeto TypeScript).

**O verificador é `npx tsc -b`** (o mesmo que `npm run build` roda antes do
Vite). Nele o defeito aparece: `error TS2552: Cannot find name 'ExternalLink'`.

**Como aplicar:** nunca fechar mudança de front dizendo "tsc: 0 erros" a partir
de `--noEmit`. Use `npx tsc -b` — e, quando quiser recheck completo depois de
mexer no tsconfig ou suspeitar de cache, `npx tsc -b --force` (há
`tsbuildinfo`, então um `-b` sem `--force` pode reaproveitar resultado antigo).

Mesma família de [[gotcha-regex-escape-duplo]] e
[[orquestra-modos-de-falso-verde]]: ferramenta que responde verde sem ter
verificado. Vale para qualquer front do usuário com o template Vite
(ConectAI, NexxaFarma, LC — conferir o `tsconfig.json` antes de confiar).
