---
name: testes-automatizados
description: Estratégia e execução de testes automatizados por stack — pytest/FastAPI (Orquestra), tsc+eslint+build no front React, Playwright para E2E, smokes pós-deploy e teste seguro de workflows n8n. Use quando o usuário pedir para testar, criar testes, validar uma feature, escrever teste de regressão, rodar a suíte, comparar com baseline ou montar smokes ("test", "testing", "unit test", "E2E", "regression", "coverage", "smoke test"). Aplica-se a projetos web (Orquestra, LC Decorações, NexxaFarma), apps e automações (n8n LC Segurança). Inclui a técnica obrigatória de baseline: zero falhas/erros NOVOS vs HEAD, nunca zero absoluto.
---

# Testes Automatizados — estratégia por stack

Regra central deste ambiente: **o critério de aprovação é sempre relativo ao baseline do HEAD, nunca absoluto**. Exemplo histórico do Orquestra: suíte com centenas de testes e ~5 falhas pré-existentes de auth do ambiente (o número deriva — meça o baseline na hora); o lint tem erros herdados. "Passou" = zero falhas NOVAS e zero erros NOVOS.

## Quando usar
- Antes de abrir PR de qualquer fase (F1..Fn) — teste novo entra NA MESMA PR do código.
- Ao corrigir bug: reproduzir em teste ANTES de corrigir (regressão primeiro, fix depois).
- Ao planejar feature na spec: definir a pirâmide de testes daquela feature.
- Pós-deploy: montar/executar checklist de smokes estilo a–f.
- Ao validar workflow n8n sem tocar produção.

## Processo

1. **Definir a pirâmide na spec** (junto com `gerador-spec`): para cada fase, listar (a) testes unitários/pytest de lógica nova, (b) o que tsc/eslint/build cobrem no front, (c) se há fluxo crítico que justifica E2E Playwright, (d) itens de smoke pós-deploy. Fluxo crítico = login, submissão de job, cópia de dados, publicação de DAG, pagamento/OTP.
2. **Capturar baseline no HEAD** antes de escrever código (ou com o working tree sujo, via stash):
   ```bash
   git stash -u
   cd /opt/orquestra-dev && python3 -m pytest -q 2>&1 | tail -3   # anotar: N passed, M failed
   npx tsc --noEmit 2>&1 | wc -l                                  # anotar contagem de erros
   npx eslint . 2>&1 | tail -2                                    # anotar errors/warnings
   git stash pop
   ```
   Guardar os números. Sem baseline anotado, não há como afirmar "zero erros novos".
3. **Escrever testes com o código**:
   - **Backend Orquestra**: pytest na raiz (`pytest.ini` com `testpaths=tests`), rodar `python3 -m pytest -q` de `/opt/orquestra-dev`. Testes de endpoint usam TestClient do FastAPI; mockar pyodbc/SQL Server — não depender do banco real no unitário.
   - **Front React**: não há suíte de unit tests de front no Orquestra — a validação é `tsc --noEmit` + `eslint` + `npm run build` (build OBRIGATÓRIO: lightningcss e rolldown pegam erros que tsc não pega). `dist/` é commitada — buildar antes do commit final.
   - **Next.js (LC Decorações/NexxaFarma)**: `tsc` + `eslint` + `next build`; lógica de negócio em lib/ ganha teste unitário se houver runner configurado no repo (verificar package.json antes de assumir).
4. **Regressão de bug**: escrever o teste que falha reproduzindo o bug reportado → confirmar que falha → aplicar o fix → confirmar que passa. O teste fica na PR com nome descritivo (`test_regressao_<issue>`).
5. **Rodar no working tree e comparar** com os números do passo 2. Qualquer falha/erro que não existia no HEAD é bloqueante — mesmo que pareça "flaky", investigar antes de descartar.
6. **E2E Playwright** (só fluxo crítico): teste headless contra ambiente local (`docker compose up` do Orquestra ou `next dev`), nunca contra produção. Selectors por role/testid, não por classe Tailwind (tokens mudam).
7. **Smokes pós-deploy**: gerar checklist a–f de itens VERIFICÁVEIS NA TELA (ex.: "a) abrir /fluxos e criar nó shell; b) renomear etapa e salvar; c) republicar DAG python…"). Entregar ao usuário para execução manual — ele valida na produção, não o agente.
8. **n8n**: validar com `n8n_validate_workflow`, testar nó isolado ou execução manual controlada via `n8n_test_workflow`. NUNCA disparar webhook de produção nem ativar workflow para "ver se funciona" — são 33+ workflows ativos de clientes reais.

## Checklist (antes de declarar a fase testada)
- [ ] Baseline do HEAD anotado (pytest passed/failed, contagem tsc, contagem eslint)
- [ ] Teste novo cobrindo a lógica da fase, na mesma PR
- [ ] Bug corrigido tem teste de regressão que falhava antes do fix
- [ ] `python3 -m pytest -q`: zero falhas NOVAS vs baseline (as 5 de auth pré-existentes não contam)
- [ ] `tsc --noEmit` e `eslint`: zero erros NOVOS vs baseline
- [ ] `npm run build` passou e `dist/` atualizada foi commitada (Orquestra)
- [ ] Fluxo crítico novo tem E2E Playwright OU justificativa explícita de por que não
- [ ] Checklist de smokes a–f escrito e entregue ao usuário
- [ ] n8n: workflow validado sem execução em produção

## Integrações
- **gerador-spec**: a pirâmide de testes por fase entra na spec (docs/spec-<feature>.md) — invocar/alinhar ao especificar.
- **verify**: usar após implementar para exercitar o fluxo de ponta a ponta de verdade, não só rodar a suíte.
- **code-review**: parte da revisão adversarial multi-agente pré-PR do usuário — rodar sempre antes de abrir PR; testes não substituem a revisão (ela já pegou bugs que suíte nenhuma pegaria: overlay branco por especificidade CSS, `overflow-hidden` matando `position:sticky`).
- **seguranca**: se a feature toca auth, secrets ou entrada de usuário, os testes devem incluir os casos do threat model (authz negativa: usuário SEM permissão recebe 403).
- **n8n** + **n8n-mcp-skills:using-n8n-mcp-skills**: todo teste de workflow n8n passa por elas (validação, execução isolada, interpretação de erros) — não reinventar.
- **performance**: se o teste é de latência/carga, medir antes e depois via essa skill, não improvisar benchmark.

## Armadilhas conhecidas deste ambiente
- **As 5 falhas de auth do Orquestra são do ambiente, não do código.** Quem esquece o baseline "conserta" teste que não está quebrado ou, pior, declara a suíte quebrada e trava a entrega.
- **tsc limpo ≠ build limpo**: lightningcss já quebrou por comentário CSS com `*/` interno; rolldown tem erros próprios. Build é etapa de teste, não formalidade.
- **`dist/` é commitada**: rodar os testes/build e esquecer de commitar a dist gera produção divergente do código revisado.
- **pip offline no deploy**: dependência de teste nova (ex.: playwright, pytest plugin) usada dentro do container exige wheel em `api/wheels/` versionada no git — se roda só na máquina de dev, documentar isso.
- **Migrations na etapa 6c do deploy.sh**: teste que depende de coluna/tabela nova só passa em produção se a migration T-SQL idempotente estiver em `sql/migrations` — já houve deploy sem migration aplicada (era manual antes do PR #164).
- **`err.status` vs `err.message` no apiFetch**: testes de tratamento de erro do front devem assertar o campo certo — bug real já pego em revisão.
- **VARCHAR estourando** (cópia de dados, NUM_CPF_CNPJ com zeros à esquerda): testes de ETL/bulk precisam de caso com largura máxima e zeros à esquerda, não só happy path.
- **n8n queue-mode com alias `redis` na LCNet**: execução de teste que depende de fila pode se comportar diferente do editor — validar pelo resultado da execução, não pelo preview do nó.

## O que NÃO fazer
- NÃO buscar "0 failed" absoluto no Orquestra — o alvo é zero falhas novas vs baseline.
- NÃO abrir PR com "testes depois" — teste da fase entra na mesma PR, sempre.
- NÃO corrigir bug sem antes reproduzi-lo em teste.
- NÃO disparar webhook de produção nem ativar/desativar workflow n8n como forma de teste.
- NÃO rodar E2E contra produção, nem seedar/limpar dados em banco de produção por teste.
- NÃO pular o `npm run build` porque "tsc passou".
- NÃO executar os smokes pós-deploy no lugar do usuário nem marcá-los como feitos — ele executa e confirma.
- NÃO mergear: o usuário sempre autoriza o merge da PR.
