# Memória do projeto — cópia versionada (snapshot de 2026-09-10)

Estes arquivos são a **memória persistente** que o Claude Code mantém em `~/.claude/projects/…/memory/`
na máquina de desenvolvimento, copiada para o repo para que **qualquer outra sessão/máquina** tenha o
mesmo contexto: estado das specs, gotchas pagos, decisões do usuário e pendências de deploy.

- Fonte viva: `~/.claude/projects/-root/memory/` na VPS de desenvolvimento. Esta cópia é um snapshot —
  ao retomar o trabalho noutra máquina, leia aqui; ao fechar um marco, atualize a memória viva **e**
  esta cópia (mesmo arquivo, mesmo nome) na PR do marco.
- Só o que diz respeito ao Orquestra e às regras gerais do usuário foi copiado; memórias de outros
  projetos ficaram de fora.
- Anonimizado na cópia: o IP público da VPS de DEV (`<IP-da-VPS-DEV>`; a URL real está em `.env.dev`)
  e o nome da chave do gateway interno de IA (`<chave do gateway>`). Nada aqui contém senha ou token.
- Formato de cada arquivo: frontmatter (`name`, `description`, `type`) + o fato, com **Why** e
  **How to apply**. Estados como "PR aberta" valem para a data do snapshot — confira no GitHub.

Como usar numa sessão nova: leia este índice, abra o arquivo do assunto em que vai mexer e siga
o processo em `CLAUDE.md` (skills `organizacao`, `gerador-spec`, `testes-automatizados`, agent
`qa-adversarial`).

## Regras gerais, ambiente de DEV e gotchas
- [Preferência de idioma: português](preferencia-idioma-portugues.md) — sempre responder em pt-BR
- [Biblioteca de Skills](biblioteca-skills.md) — 11 skills + 2 agents globais em ~/.claude
- [⚠️ REGRA: não mudar a ordem dos objetos na tela](regra-nao-mudar-ordem-da-tela.md) — sem pedido claro, não reordena; na dúvida, perguntar ANTES
- [VPS: pkill atinge containers](vps-pkill-atinge-containers.md) — ⚠️ processo de container aparece no host; matar por PID, nunca por nome
- [Ambiente DEV do Orquestra](vps-ambiente-dev-orquestra.md) — ▶️ NO AR (2026-08-31); UI :8090, credenciais em `.env.dev`; ⚠️ `dist/` é VOLUME — build local aparece na hora
- [⚠️ GOTCHA: squash em PRs empilhadas conflita](gotcha-squash-prs-empilhadas.md) — `dist/` versionado agrava; resolver com `merge -s ours` DEPOIS de provar a ancestralidade
- [⚠️ GOTCHA: ServiceNow devolve 200 vazio sem permissão](gotcha-servicenow-tabela-inacessivel.md) — integração fica VERDE coletando nada; as notas do Orquestra ficaram 0 desde sempre
- [⚠️ GOTCHA: `docker compose` sem `--env-file .env.dev` derruba o SQL Server do DEV](gotcha-compose-sem-env-file-dev.md) — recria o container com a senha default, `unhealthy` em loop; o dado está intacto, NÃO apagar o volume
- [⚠️ GOTCHA: `docker cp` sobre symlink sobrescreve o ALVO](gotcha-docker-cp-symlink.md) — matou o busybox do sshd-amostra do DEV; recuperar copiando o binário da imagem, sem recriar o container
- [⚠️ GOTCHA: `tsc --noEmit` não checa nada](gotcha-tsc-noemit-nao-checa.md) — o tsconfig raiz do template Vite tem `"files": []` e o comando sai 0 sem olhar arquivo; o verificador é `tsc -b`
- [⚠️ GOTCHA: regex com escape duplo](gotcha-regex-escape-duplo.md) — `/\\d/` nunca casa e passa tsc+lint+build

## Orquestra (sge_app)
- [Orquestra (sge_app)](orquestra-sge-app.md) — repo carlosdev-joy/sge_app em /opt/orquestra-dev; React 19 + FastAPI/SQL Server + Airflow; ⚠️ REGRA: as orientações também vivem no repo em `.claude/` — sincronizar a cada marco
- [Spec Parâmetros dos jobs DataStage](orquestra-spec-parametros-job-datastage.md) — 🏁 SPEC CONCLUÍDA 2026-09-10 (F1–F6 = PRs #376–#381, última `d3c1cbb`); ⏳ deploy em produção PENDENTE (107–109 na 6c, `dags/` + restart do worker, `api/` + `dist/`, `ORQUESTRA_CONN_KEY`); DEV já com 106–109
- [Spec Maestro — chat de parâmetros DataStage](orquestra-spec-maestro-parametros.md) — 🏁 SPEC CONCLUÍDA 2026-09-10: F1–F4 (PRs #382–#385) + complemento F5 (PR #387 `03bc523`) mergeados; ⏳ deploy em produção PENDENTE (roteiro em `docs/release-notes/maestro.md`); DEV sem provedor de IA
- [Spec Notificação por e-mail](orquestra-spec-notificacao-email.md) — ✅ F1 (#388), F2 (#389) e F3 (#390) MERGEADAS; 🔧 **F4 em PR** (docs + 2 defeitos de código que a revisão da DOC achou); ⏳ deploy conjunto pendente: 111 na 6c, restart do worker, recriar API+worker (env novo), **regerar as DAGs**
- [Spec Utilitários de arquivos](orquestra-spec-utilitarios-arquivos.md) — 🏁 CONCLUÍDA e ✅ EM PRODUÇÃO (deploy confirmado 2026-09-07); F1–F7 = PRs #356–#363; extensão download/upload em spec própria
- [Spec Lineage automático via ISX](orquestra-spec-lineage-isx.md) — 🏁 SPEC FECHADA 2026-09-08 (F1–F5 = PRs #369–#374 + #375 `6889e67`); ⏳ deploy conjunto EM ANDAMENTO pelo usuário (roteiro em `docs/release-notes/lineage-isx.md`); gotchas e pendências no tópico
- [Spec Lineage ISX: jobs fora de Jobs/](orquestra-spec-lineage-isx-pasta-raiz.md) — 📋 RASCUNHO 2026-09-08, aguarda aprovação; ⚠️ `validar_pasta` exige `Jobs` em 3 lugares e o workaround por SQL NÃO funciona
- [Spec Utilitários: transferência (download/upload)](orquestra-spec-utilitarios-transferencia.md) — 🏁 CONCLUÍDA e ✅ EM PRODUÇÃO 2026-09-07 (F1–F5 = PRs #364–#368); conferências pós-deploy da release note não confirmadas item a item; gotchas no tópico
- [⚠️ GOTCHA: NVARCHAR conta UTF-16](gotcha-nvarchar-utf16.md) — `len()`/`[:n]` deixam emoji estourar a coluna; auditoria best-effort SOME em silêncio; medir/cortar com `utf16_len`/`cortar_utf16`
- [⚠️ REGRA: dev testa, produção manda](orquestra-dev-testa-producao-manda.md) — padrões de produção Caixa (deploy offline/6c, degradação, LDAP) valem sempre
- [⚠️ Os 8 modos de falso verde](orquestra-modos-de-falso-verde.md) — catálogo pago com defeitos reais nas 12 fases
- [Porte do módulo de Chamados](orquestra-porte-chamados-producao.md) — 🏁 SPEC FECHADA 2026-08-28: F0–F6 mergeadas (PRs #338–#344); traz para o git o que foi feito direto no servidor; smoke em `scripts/smoke_chamados.sh`
- [Chamados: tabela, copiar nº, anotações e solicitante](orquestra-chamados-tabela-copiar-notas.md) — 🏁 PRs #338–#343 EM PRODUÇÃO 2026-08-28; ⚠️ nginx.conf de prod está À FRENTE do repo — responder **n** para `config/` no deploy
- [Migrations idempotentes](orquestra-migrations-idempotentes.md) — regra do repo: toda migration roda 2×; teste trava as 100; a 010 era a única quebrada
- [Triagem de chamados com IA](orquestra-chamados-triagem-ia.md) — 🤖 F1–F4 mergeadas (PRs #322–#324); deploy PARCIAL (`dags/` + restart do worker pendentes); ⚠️ credencial de produção em claro no repo `sge`
- [Spec RITM × SCTASK](orquestra-spec-chamados-ritm-sctask.md) — ✅ ENTREGUE pela F5 do porte; PR #325 fechada 2026-08-29 (só o campo `registros` ficou de fora)
- [Claude Code offline no servidor](orquestra-claude-code-offline.md) — 📦 PR #321 FECHADA 2026-08-29, mas a branch `chore/claude-code-offline` guarda o código; pendente release, rede e autenticação
- [🏁 MARCO: o trem foi para produção](orquestra-deploy-trem-producao.md) — 2026-08-12: migrations 067→087 e corrida de malha LIGADA
- [Spec da corrida de malha](orquestra-spec-corrida-malha.md) — 🏁 F1–F12 em produção (PRs #277–#288)
- [Ajustes malha + inventário DAGs](orquestra-ajustes-malha-inventario.md) — ✅ PRs #293–#296 em produção; ⚖️ inversão D26/27
- [Nó Aguarde](orquestra-no-aguarde.md) — junção de pernas paralelas; F1–F4 em produção; ⚠️ smoke §8.1 sem confirmação
- [⚠️ GOTCHA: factory_log órfão em RUNNING](orquestra-factory-log-orfao.md) — geração que falha vira "timeout" mudo; corrigido na PR #234
- [⚠️ GOTCHA: schedule_type novo em 3 lugares](orquestra-agendamento-sob-demanda.md) — 'on_demand' virava cron 06:00; pipelines antigos precisam ser REGERADOS
- [⚠️ Nome de job DataStage: case-sensitive](orquestra-nome-job-datastage.md) — DS distingue caixa, SQL Server não; PR #269
- [Spec Chamados ServiceNow](orquestra-spec-chamados-servicenow.md) — 🏁 módulo EM PRODUÇÃO; PR #297 fechada 2026-08-29 como documento histórico
- [Spec Operar ciclo fechado](orquestra-spec-ciclo-fechado.md) — ✅ F0 mergeada (PR #303); **deploy pendente** (etapa 5, `dags/`)
- [Spec Reset à força da malha](orquestra-spec-malha-reset-forca.md) — 📋 rascunho na PR #301; pendente §8
- [Operação no nível de etapa](orquestra-reexecucao-nivel-etapa.md) — ✅ F1–F5 em produção; resta F6 e a revisão adversarial de fecho
- [⚠️ Malha: data de referência única](orquestra-malha-data-unica.md) — incidente Carga_Vida; F1–F5 em produção; script de reset em docs/forcar-reset-ciclo-malha.sql
- [Republicar pipelines da malha](orquestra-republicar-malha.md) — ✅ em produção; ⚠️ a SP de pendentes é GLOBAL
- [Malha componentes (F10–F15)](orquestra-malha-componentes.md) — 🏁 completa e aceita (PRs #250–#257)
- [⚠️ Dependências entre pipelines](orquestra-dependencias-pipelines.md) — Control-M + malha; F1–F9 em produção; ⚠️ fio solto: `sp_pendentes_criar` sem `depends_on`
- [⚠️ GOTCHA: worker cacheia dags/utils](orquestra-worker-cacheia-dags-utils.md) — mudança só em `dags/utils/` exige restart do worker; task VERDE com código antigo
- [⚠️ GOTCHA: índice filtrado × QUOTED_IDENTIFIER](orquestra-indice-filtrado-quoted-identifier.md) — falha no sqlcmd (Msg 1934) e quebra todo DML pelo sqlcmd
- [⚠️ GOTCHA: proxy só no orquestra-api, não no worker](orquestra-proxy-worker-vs-api.md) — sonda passa e DAG morre; solução = rota na config
- [⚠️ GOTCHA: RBAC_RECURSOS é uma 2ª lista à mão](orquestra-rbac-recursos-lista-dupla.md) — tela só no NAV vira permissão sem interruptor; PR #310 com teste anti-drift
- [⚠️ GOTCHA: permissão nova exige relogin](orquestra-permissao-nova-exige-relogin.md) — permissões vivem no localStorage e só atualizam no login
- [⚠️ GOTCHA: placeholder SQL por árvore](orquestra-placeholder-pyodbc-pymssql.md) — `dags/` usa `%s`, `api/` usa `?`; trocar dá zero gravação com task VERDE
- [⚠️ Grafia dupla de pipeline_name](orquestra-grafia-pipeline-name.md) — SQL CI × dict Python; PR #236 em produção
- [Ícones do canvas de Etapas](orquestra-icones-canvas.md) — PRs #237/#238/#249 em produção
- [Supervisão DataStage](orquestra-supervisao-ds-spec.md) — ✅ spec encerrada, F1–F7 em produção; o "sucesso falso" é RECURSIVO; GOTCHA: `hint` clipado → usar prop `ajuda`
- [Fluxo/Etapas](orquestra-fluxo-etapas.md) — roadmap em 6 ondas; tudo até PR #184 em produção; smokes pendentes
- [Etapas: busca sem filtro + tabela ajustável](orquestra-etapas-lista-tabela.md) — PR #355, ⏳ deploy do `dist/`; hook de colunas arrastáveis REUTILIZÁVEL; ⚠️ `localStorage` lança em janela privada
- [Análise UX Orquestra x Caixa](orquestra-caixa-ux-analise.md) — migração p/ DS nativo completa; pendente o smoke §7
- [Chat dos assistentes: markdown cru](orquestra-caixa-chat-markdown.md) — ✅ PR #326 mergeada, deploy pendente; ⚠️ jsPDF é WinAnsi
- [Caixa Seguro POC](orquestra-caixa-seguro-poc.md) — 🏁 em produção; home com Workflow de 8 cards lendo o PIO e busca real ([[project-pio]]); ⚠️ a ordem dos blocos da home é decisão do usuário — ver [regra](regra-nao-mudar-ordem-da-tela.md)
- [Projeto PIO](project-pio.md) — 🏁 EM PRODUÇÃO 2026-09-01: os 8 cards do Workflow leem dado real (PRs #346/#348–#354); ⚠️ a `PIO_AGG` tem várias linhas por card e os cards 4–8 usam outro vocabulário de colunas
- [Cópia de Dados](orquestra-copia-dados.md) — código em produção, mas ⚠️ pendências de INFRA sem confirmação
- [Finalização Manual](orquestra-finalizacao-manual.md) — tela /finalizacao (PR #163); deploy.sh ganhou a etapa 6c
- [Inventário de Consumidores](orquestra-inventario-consumidores.md) — tela /inventario; incidente NUM_CPF_CNPJ
