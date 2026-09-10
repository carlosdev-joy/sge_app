---
name: orquestra-coletar-producao
description: Como trazer para o git o que foi alterado direto no servidor de produção do Orquestra — script coletar-prod.sh e o método de identificar a versão deployada
metadata: 
  node_type: memory
  type: reference
  originSessionId: 80eeec2c-39eb-4217-a273-e34383d916bf
  modified: 2026-08-28T02:22:09.228Z
---

Ferramenta e método para trazer de volta ao git o que foi mexido direto em
`/opt/airflow` (produção do Orquestra, Caixa). Script: `scripts/coletar-prod.sh`, branch
`chore/coletar-prod` — o servidor baixa pelo mesmo canal do deploy (repo público):

```bash
cd /tmp && rm -rf coleta
git clone --depth=1 --branch chore/coletar-prod https://github.com/carlosdev-joy/sge_app.git coleta
bash coleta/scripts/coletar-prod.sh          # MODO=completo (padrão)
```

É só leitura: não altera `/opt/airflow`, não mexe em container, dois SELECTs no banco,
tudo em `/tmp`. Sem script, o equivalente é um `tar` de `api dags config docker
docker-compose.yaml Dockerfile ui-react/dist/index.html` excluindo `dags/generated`,
`__pycache__`, `*.pyc`, `*.bak*` e `api/wheels` → **~2 MB**.

**Levar as pastas INTEIRAS é melhor que gerar patch no servidor:** não depende de saber
lá qual commit está deployado (essa resposta está do lado que tem o histórico), não
depende de rede/proxy/credencial, e permite separar alteração manual de commit não
deployado. Com a base errada, um patch REVERTE commits que já estão no git — e isso passa
por "alteração de produção".

**Identificar de qual build a produção saiu:** os assets com hash do
`ui-react/dist/index.html` identificam o commit —
`git log --all -S"index-XXXX.js" -- ui-react/dist/index.html`. Se o asset não aparecer em
commit nenhum, **o front foi buildado no servidor** (foi o que aconteceu em
[[orquestra-porte-chamados-producao]]). Alternativa: comparar as pastas contra vários
commits candidatos e ficar com o de menor divergência.

**Validar se o servidor pode dar `git push`:** o `deploy.sh` só prova leitura (clone
anônimo, repo público). Testar com `GIT_TERMINAL_PROMPT=0 git push --dry-run origin
HEAD:refs/heads/teste-permissao-push`; o teste definitivo é um push real de branch
descartável, porque proxy corporativo costuma liberar GET e barrar o POST do envio.

⚠️ **O `deploy.sh` sobrescreve `api/` sem perguntar** (etapa 7, `rsync -av`): alteração
manual em `api/` some no próximo deploy, em silêncio. `dags/`, `config/` e
`docker-compose.yaml` perguntam antes e fazem backup.
