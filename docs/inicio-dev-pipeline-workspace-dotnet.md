# Início no DEV do workspace de Pipeline
Data: 2026-10-09 · Entrega: inspeção e preparação da F1
Este roteiro prepara o plano de implementação. Não é código de produto nem confirmação de que o DEV foi validado.

## Documentação de entrada
Ler CLAUDE.md, docs/fluxo-desenvolvimento.md, docs/spec-pipeline-workspace-dotnet.md e docs/continuidade-pipeline-workspace-dotnet.md na branch docs/pipeline-workspace-dotnet.
O usuário autorizou a continuidade. Escopo inicial: React existente, base de gestão .NET, Pipeline com Etapas/Fluxos internos; motores existentes preservados.

## 1 Conferir checkout ativo sem trocar branch
Executar por SSH no host DEV confirmado:
```bash
cd /opt/orquestra-dev
git status --short
git branch --show-current
git rev-parse HEAD
git remote get-url origin
git log -5 --oneline
```
Inspecionar localmente a URL do remoto; se contiver credencial, não copiá-la para relatórios. Não usar reset, checkout ou limpeza no checkout servido. Registrar alterações existentes e autor conhecido, sem sobrescrevê-las.

## 2 Preparar cópia isolada
Após conferir remoto e obter os refs por fetch, criar worktree de feature a partir de origin/develop, fora da pasta servida. Seguir a skill de worktrees e instruções do servidor. Não reutilizar branch de outro trabalho e não copiar .env automaticamente.
Trazer os dois documentos e este roteiro da branch documental para a feature; documentação não obriga a servir sua branch no DEV.
Mockups do pacote são referência visual, não implementação nem fonte de métricas.

## 3 Conferir ferramentas e capacidade sem instalar
```bash
command -v dotnet
command -v node
command -v npm
command -v docker
dotnet --info
node --version
npm --version
docker version
free -h
df -h /opt/orquestra-dev
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'
```
Ausência de ferramenta é resultado da inspeção; não implica instalar automaticamente. Não imprimir ambiente, .env, docker inspect completo ou logs com segredos.
A disponibilidade de SDK no servidor e o formato de distribuição offline definem o target .NET antes do scaffold.

## 4 Inventário funcional e segurança
Inspecionar App.tsx, lib/nav.ts, pages/Jobs.tsx, pages/Fluxos.tsx, pages/Pipelines.tsx, FluxoEditor.tsx e JobTypeFields.tsx.
Produzir tabela com ação atual, rota/API, dados gravados, permissão, destino no workspace e teste de paridade.
Cobrir criar/editar/inativar/reordenar etapas, parâmetros por tipo, lineage, importação, execução, pausa/retomada quando existentes, logs e todos os nós disponíveis.
Inspecionar api/deps.py, auth e schema de sessão para registrar algoritmo do token, expiração/revogação e RBAC. Não copiar tokens ou credenciais.
Mapear todas as gravações do editor: nenhuma pode atingir configuração publicada enquanto o usuário trabalha em rascunho.

## 5 Contratos e baseline
No worktree, registrar resultados dos checks prescritos no repositório: pytest, tsc -b, lint e build. Build apenas na cópia isolada; registrar skips e falhas preexistentes por arquivo/regra/caso.
Inspecionar schemas reais usando credencial autorizada local, sem expor valores. Conferir collation, identificadores, migrations aplicadas e próximos números livres.
Mapear dado de execução disponível: previsto, dependência liberada, fila, início, fim, motor, pool e tentativa. Ausente permanece ausente; não inferir capacidade de 50 pipelines a partir de concorrência de tarefas.
Criar fixtures anonimizadas para sessão, permissões e fluxos SQL/Python/DataStage simulado.

## 6 Plano executável da F1
Escrever docs/superpowers/plans/2026-10-09-pipeline-workspace-f1.md após inspeção, com caminhos, assinaturas, testes e comandos reais.
Tarefas da F1: contrato do fluxo e capacidades; solução .NET modular; compatibilidade de sessão/RBAC; saúde/readiness; proxy DEV exclusivo /orquestra/workspace/*; testes de degradação; documentação de instalação offline.
Não criar tabelas de rascunho nem retirar menus antes das fases correspondentes.
Testes mínimos: token inválido/expirado/revogado, usuário inativo, ação negada, perfis acumulados, SQL indisponível, .NET indisponível e módulos legados ainda funcionando.
Antes de código, apresentar o plano para revisão conforme writing-plans. Execução recomendada: implementação sequencial nesta sessão do servidor, com revisão adversarial independente antes de cada PR, conforme projeto.

## 7 Evidências de saída
Registrar commit base, estado do checkout, ferramentas, capacidade observada, inventário funcional, contratos reais, baseline e limitações.
Marcar cada item como verificado, indisponível ou não executado. Não substituir teste real por memória histórica.
Quando F1 for implementada: PR para develop, revisão adversarial, migration de versão se houver entrega funcional, deploy seletivo e smoke. Main e produção exigem autorização própria.

## Critério de passagem
O plano F1 só está pronto quando identifica versão .NET distribuível, autenticação equivalente, roteamento sem colisão, preservação de RBAC e isolamento do trabalho. Acesso SSH ainda precisa ser informado ou a sessão deve ser aberta diretamente no servidor.

## Referências visuais versionadas
Os quatro mockups aprovados estão em docs/mockups/pipeline-workspace/ na branch docs/pipeline-workspace-dotnet. Ler o README e abrir os PNGs antes de implementar a interface. Transportar essa pasta para o worktree de feature junto com a documentação. As imagens definem a direção visual; os contratos e permissões desta especificação definem o comportamento.
