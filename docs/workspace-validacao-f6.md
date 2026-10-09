# F6 — piloto e consolidação do workspace

Rodada autorizada em 09/10/2026 após DEV 2.12.0. Candidato funcional: `211289ff774053ee1ad1ba7816a483fe564e4c69` (PR484). A entrega F6 registra evidências e a migration149 de versão **2.12.1**, sem alterar UI, API, contratos, permissões ou motor. Os hashes das fontes e do dist continuam os mesmos do candidato funcional.

**Resultado: rodada de validação concluída com pendências. Aceite integral da spec não atingido.** A paridade exigida em F5 permanece incompleta e há dois desvios de desempenho. Não é autorização nem comprovação de produção/Caixa. O usuário pediu os ajustes após esta rodada; nenhuma funcionalidade ausente foi implementada silenciosamente.

## Matriz de evidências

| Gate | Resultado | Evidência e limite |
|---|---|---|
| Regressão Python | PASS contra base | 7.202 passaram (base7.201; a migration149 adiciona um caso), 51 skips, as mesmas 8 falhas conhecidas; nenhuma nova. |
| .NET + SQL real | PASS | 76 testes sem skips; bancos/logins efêmeros próprios. Dois usuários distintos, expiração, fence, revisão, conflito, rollback/auditoria e hashes reais. |
| Criação isolada | PASS DEV | Draft não cria cadastro ativo nem DAG. Transferência entre duas sessões, save estrangeiro e revisão antiga recusados. As duas sessões DEV são da mesma conta; usuários diferentes são comprovados na bancada SQL. |
| Publicação/recuperação | PASS DEV | Duas versões imutáveis, mesma intenção retorna mesma operação; save durante intenção pendente recusado. Adaptador reiniciado durante projetado/gerando; operação conclui uma vez, hash SQL/DAG/versão/gate conferidos e um log de fábrica. Não é reboot total. |
| Executar/log/reprocessar | PASS DEV | SQL SELECT1 real, logAirflow só da bancada, runid/conf preservados, comandos idênticos simultâneos devolvem mesma corrida; comando diferente recusado; reprocessamento da versão atual passa e da antiga é recusado após publicar SELECT2. Histórico mantém v1. |
| Publicar com execução | PASS com limite | Durante comando reservado com DAG pausado: validação informa execution_active e publish422, sem projeção. Depois DAG liberado e execução concluída. Execução já running é coberta no SQL real isolado, não por espera artificial no DEV. |
| Conexão inválida | PASS DEV | Draft próprio300etapas usa conexão deliberadamente inexistente; diagnóstico identifica Etapa_000, publish422 e nenhum cadastro ativo. Draft descartado. |
| Negativas de permissão | PASS | Anônimo401 e Basic sem autoridade de execução401 no DEV; matriz operacional403/flags/permissões combinadas nos testes .NET. Sem afirmar teste de todos perfis reais no cliente. |
| Navegação/browser | PASS | 16 verificações sintéticas (desktop/mobile ×claro/escuro, contexto, histórico, logs como texto, menus/capabilities) +6 em browser DEV com bancada própria. Organizar/salvar altera sólayout; drafts descartados. |
| Falha upstream/legado | PASS DEV | Apenas workspace-api parado; proxy502/503/504 e legado health, versão e /v2/200. Mesmo serviço reiniciado e ready200. Não parou banco/volumes; não comprova alta disponibilidade. |
| Falhas de UI | PASS isolado | 4 cenários: contexto503 com retorno à lista, diagnóstico inválido, falha de save conserva layout local/requer retomar lease e salva após recuperação, consulta por teclado sem gravação. |
| Piloto desligado | PASS isolado | Fixture browser mantém menus antigos quando contextualNavigation=false; testes .NET de flag e lista de usuários. Flag global DEV não foi desligada. |
| Fluxos grandes | PASS estrutural | 50/100/300nós, arestas mantidas após save, nenhuma exceção JS; fixture não substitui DataStage/InformationServer. |
| API p95<500ms | PASS medido | 30 leituras sequenciais por endpoint: capabilities13,9ms, draft30040,9ms, contexto30045,5ms via proxyDEV local. Sem plano real SQL/contagem N+1. |
| Canvas local | PASS/FAIL | 300nós: pronto1055ms, LCP1080ms, CLS0,0013; interação p95**239ms**, meta200ms. Interação é tempo até dois frames após seleção, não INP de campo. |
| Bundle<300KB gzip | FAIL | JS inicial compartilhado835.275bytes gzip; chunkworkspace15.671bytes. Tamanho total efetivo da rota supera orçamento. Baseline herdado; não foi otimizado nesta rodada. |
| Offline .NET | PASS componente | 68NuGet com hashes/lock,133checksums, build e reconstrução consumidora --network none/--pull=false/--no-cache;73pass/3skip SQL, compensados pelos76SQLreais. save/load e runtime conferidos. |
| Paridade funcional antiga | FAIL | [Inventário detalhado](workspace-paridade-f6.md). PreservaçãoJSON não equivale aos formulários e destinos de gravação. |
| Caixa/DataStage real/INP de campo/SQL IO | NÃO EXERCITADO | Necessita ambiente/fontes específicos. Não usar smoke SQL sintético para certificar integração externa ou desempenho do cliente. |

## Desempenho bruto do canvas

Build de produção local, Chromium desktop sem limitaçãoCPU, APIs/fluxo sintéticos. Amostras de seleção:25 por tamanho; carga fria de página por caso, não campanha estatística de LCP.

| Nós | Canvas pronto(ms) | LCP(ms) | Seleção p95(ms) | CLS |
|---|---:|---:|---:|---:|
|50|802|816|103|0,0018|
|100|858|884|114|0,0017|
|300|1055|1080|239|0,0013|

## Ajustes priorizados para a próxima rodada

1. Agendas hourly_n/biweekly recusadas pelo adaptador e lineage sem edição/projeção no draft.
2. Formulários especializados, parâmetros globais/etapa, tipos/origens/vínculos/importação e configuração rica do pipeline.
3. Prévia ValidaArquivo bloqueada no pipeline gerido e percurso Maestro→draft sem aplicação.
4. Bundle compartilhado e interação300nós; medir antes/depois ao otimizar. Logs mobile com runid longo têm overflow no contêiner interno já registrado na rodada de referência, apesar da largura do documento passar.

Reprocessamento de corrida antiga e cascata são restrições de integridade explícitas; sua eventual ampliação exige decisão, não correção automática. SQL/decisão preview sem identidade de pipeline e conversa Maestro continuam acessíveis; não generalizar o bloqueio de ValidaArquivo.

## Fontes e reprodução

Evidências locais `/root/orquestra-f6-evidencias/`: `pytest-baseline.txt`, `dotnet-sql-tests.txt`, `smoke-dev.json`, `browser-validation.json`, `browser-dev.json`, `browser-negative.json`, `failure-recovery.json`, `performance-api.json`, `performance-browser.json`, `eslint-comparison.json`, `offline-validation.json`. Artefatos e helpers privados ficam fora do Git; nenhum token, env, logcliente ou credencial faz parte do relatório. O inventário tem revisão adversarial independente, com evidência por fonte.

Reprodução offline do componente .NET: seguir [roteiro DEV/offline](dev-workspace-dotnet.md), gerar `scripts/package_workspace_offline.py` em diretório novo, conferir SHA256SUMS e reconstruir Dockerfile.consumer sem rede. Pacote final regenerado com migration149 a partir de123f582ee3fd7797c8a1d67ebc903a7ac2703f60;133checksums conferidos e consumidor novo reconstruído sem rede. Esse commit contém todas as fontes e a migration; o commit seguinte atualiza somente os registros dessa reconstrução. Imagemoffline3301e0027aaa, consumidor943fd3b535a9; não se afirma determinismo binário. Não é pacote integral para instalar Airflow/FastAPI/SQL Server do zero: bases Docker precisam ser transportadas, infraestrutura e dependências Python existentes continuam pelo roteiro de deploy. Nenhuma dependência nova nesta fase. Não ficaram drafts nem comandos ativos do prefixo próprio F6 (consulta SQL ao término). TypeScript/build passaram, dist idêntico, lint75assinaturas herdadas/zero novas. ChecagemNUL: lineageIsx.ts já contém NUL em develop e está byte a byte idêntico; nenhum novo neste delta.

Ajustes dos roteiros durante o ensaio: WAITFOR foi recusado corretamente pelo validador SQL; o caso passou a SELECT1 com DAG pausado. Publicar com execução reservada devolve422 por diagnóstico execution_active, enquanto o gate SQL concorrente pode devolver409. A primeira medição de validate recebeu503 durante o reinício deliberado e foi repetida após ready. Não houve alteração de produto para fazer esses testes passarem.

Recuperação: antes de reiniciar, conferir DEV/branch/compose e operações persistidas; reiniciar somente adaptador afetado; aguardar health/ready; consultar operação pela mesma operationId e conferir version/hash/pending. Nunca limpar tabelas de intenção ou publicar uma segunda intenção para substituir uma ainda pendente. Falha do serviço .NET deve manter o legado atendendo; start no mesmo workspace-api, sem recreate de banco/volumes. Backups por roteiro existente; rollback funcional não foi ensaiado com produção nem dados reais.
