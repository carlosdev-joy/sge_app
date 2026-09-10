---
name: gotcha-squash-prs-empilhadas
description: "PRs empilhadas + squash merge + dist/ versionado = conflito na segunda; resolver com merge -s ours depois de provar a ancestralidade"
metadata:
  type: reference
---

Quando as PRs são **empilhadas** (B parte de A, C parte de B) e o repo usa
**squash merge**, mesclar A cria um commit NOVO com o conteúdo de A. A PR B
continua com os commits originais de A dentro dela, e o GitHub passa a marcar
**CONFLICTING/DIRTY** — o conflito é de **história**, não de conteúdo.

No `sge_app` isso morde mais forte porque **`ui-react/dist/` é versionado**: os
bundles têm nome com hash, então cada build gera arquivos com nomes diferentes
e o `index.html` aponta para o novo. É praticamente conflito garantido.

**Resolução sem reescrever história** (o usuário já recusou `--force-with-lease`
uma vez neste repo — não force-push sem pedir):

```bash
# 1. PROVE que nada se perde: a árvore da main tem de ser idêntica à ponta da
#    PR já mesclada, e essa ponta tem de ser ancestral da branch atual.
git diff --stat origin/main origin/<branch-da-PR-ja-mesclada>   # vazio
git merge-base --is-ancestor origin/<branch-ja-mesclada> origin/<branch-atual>

# 2. Só então: merge que preserva a árvore desta branch.
git checkout -B <branch-atual> origin/<branch-atual>
git merge -s ours origin/main -m "Merge main na #NNN …"
git push origin <branch-atual>        # push normal, sem --force
```

⚠️ `-s ours` **descarta** o que vem do outro lado. Ele só é seguro **depois**
das duas verificações acima. Sem elas, é uma forma silenciosa de perder código.

Depois de mesclar tudo, conferir na `main`:
`git diff --stat origin/main origin/<ultima-branch>` deve sair vazio.

Ver [[orquestra-chamados-tabela-copiar-notas]] (2026-08-28: #338 → #339 → #340).
