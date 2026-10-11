# Paridade do workspace — F7A e continuidade

Usuário autorizou encerrar pontos de paridade, desempenho e homologação, seguindo spec existente e referência01/02. Spec original docs/spec-pipeline-workspace-dotnet.md continua autoridade; docs/spec-workspace-paridade-complemento.md organiza F7A–D/F8/F9. Edição somente no Fluxo; não reintroduzir Etapas/lista. Continuidade inclui develop/DEV, não main/produção.

F7A na branch feat/workspace-paridade-f7a, base085261e9 (DEV2.12.6). Candidato2.13.0 migration155: reutiliza JobTypeFields nos cinco tipos DataStage/Shell/Python/Stored Procedure/HTTP. Editor expandido usa staging aplicar/cancelar, catálogo conexões/bancos (SSH também em DS/Python módulo, conforme publicação existente), parâmetros/preview/defaults do próprio draft. Aplicar não salva cadastro ativo; persistência pelo PUTdraft. lazy mantém módulo extenso fora do carregamento direto do inspector.

Preserva extras legacyJob/configuration/params e Python; se trocar Python para módulo descartaria extras, recusa aplicar. Refs Encrypted excluídas dos inputs/preview/IA e mantidas por referência; novos segredos seguros dependem F7C. Guards atuais node/lease/revision/fence e expiresAt direto, campos readonly quando perde edição. Maestro/import contexto desligados até integração draft adequada nas fases seguintes.

Evidências privadas /root/orquestra-f7a-evidencias. QA/segurança manual aprovados; pytest7228pass/8baselinefail/51skip, focados167pass, lint74assinaturas/74basezeroNEW, tsc-b/VitebuildPASS. Baseline isolado gitarchive tem23skips extras de testes dependentes de.git, mesmas8falhas; comparar falhas pornome. Navegador tipos/save/reload/params/Python e cinco larguras/temas; negativa lease passou; revisão visual pediu rótulos explícitos, implementados e recaptura em fechamento ao escrever este snapshot.

Não há novo deploy/merge confirmado neste snapshot. Entrega final, SHA, smoke e demais limites são definidos pelo registro compartilhado final. Pendências: F7B seis painéis/previews, F7C cadastro/parâmetros/segredos/import/ordem, F7Dlineage/Maestro; F8bundle/canvas; F9matriz completa. Ensaios reais DataStage/InformationServer da Caixa não são fixtures DEV.

## F7B candidato em implementação

Branch feat/workspace-paridade-f7b, base28f6dd09 (DEV2.13.0/F7A PR491 concluída conforme registro compartilhado). Candidato2.14.0 migration156, seis painéis especializados em modal DS com staging local e definição inteira protegida por referência/lease/revision/fence. Casos/arestas decisão atômicos, conexão das pontas ao Aguarde validada; campos extras preservados (anexo/casos de conversão recusam descarte). Painéis antigos mantêm comportamento sem flagworkspace.

Novo POST /workspace-adapter/valida-arquivo/preview é autenticado e estático: grafo/catálogo do rascunho recebidos, sem DB/SSH/arquivo/escrita. Somente String/Pathname fixos sem secretReference; preview não substitui ensaio Caixa. SQL/Decisão/Arquivo correlacionam resultados/erros à configuração e sessão atuais.

Evidências /root/orquestra-f7b-evidencias: primeirofull7236pass/8mesmasfalhas51skip, baseisolada7205pass8falhas74skip (.git ausente acrescenta23skip); testes focados10pass com dois negativos adicionados após coleta da primeirafull. Lintbase74/candidato73zeroNEW. Build inicialPASS; rodada browser/negativos e revisão final em andamento. Nenhuma nova PR/deploy confirmado neste snapshot. Registro compartilhado final terá precedência.

F7B fechamento local: pytestfinal4 7239pass/8mesmasfalhas51skip, lint74base73finalzeroNEW, finaltsc-b/VitePASS; QA/securitymanualsemachadosabertos; browser14cenáriosincluindonósnovos/JSONincompatível/lease/consulta,36recapturas solicitadaspelorevisorindependente. Finishship/documenterdelta; backupDEVverificado. ConfiguraçãoJSONincompatívelpreservadaemconsulta commotivoexplícito. EntregaDEV/PR/SHAcontinuampendentesnestesnapshot, registrofinal teráprecedência.


## F7B entregue / F7C candidato
F7B PR492 integrada em develop b22cbdf2bac71098ccdeacf2fc9e305adce80a1c, DEV2.14.0/migration156, backup e22smokesPASS; registro final2026-10-11-workspace-paridade-f7b-dev-final-codex.md tem precedência sobre snapshots candidatos acima.

F7C branch feat/workspace-paridade-f7c, baseb22cbdf2. Candidato2.15.0 migrations157/158. Catálogo compartilhado com tipos/origens/destinos/descrições/importação e vínculos locais; governança rica, notificações/dataref, política sem movimento; importação guiada e execution_order sem alterar layout. Segredo write-only cifrado fora do snapshot, UUID vinculado a draft/pipeline/job/param e sessão/revisão/lease/fence. .NET valida ref antes de save; projeção autentica HMAC sem decifrar. Vault imutável; baseline legado por versão, captura SERIALIZABLE com hash comprovado, importação no mesmo txn, restore sem prova em consulta. Não há GC nesta entrega.

Gates locais7283PASS8falhasidênticasbase51skip,91Pythonfoco,77SQL0skipincluiconcorrência/restauração/reexec157; lint73base73candidatezeroNEW, governançafinal0msgs, fontes0NUL (NULgeradodistjáexistenabase); build6tsc-b/VitePASS. Browser8+2sintéticos, númerosretidosdigitação/save/reload, cancel/late-secret semaplicar. QA corrigiu representação numérica; revisõesfinaisaprovadas. BackupDEVverificadoantesdeploy. Evidências /root/orquestra-f7c-evidencias.

Nenhuma PR/deployC confirmada neste snapshot; registrofinal teráprecedência. PendênciasF7Dlineage/Maestro,F8performance,F9matriz. DataStage/InformationServerCaixa real não equivale a fixturesDEV; main/produção separadas.

Delta final C: destinatários do fluxo editados em linhas, persistidos em JSON array compatível com SQL e validados por formato/domínios Admin; horários novos/alterados usam régua24h. Valores legados incompatíveis preservados quando inalterados. Gatesfinal3/browserfinal6 e revisão visualship. SmokeDEV ainda pendente.


## F7C entregue / início F7D
F7C PR493 mergeada em develop e3a44bc958d251c1830cc8685ea2cbb590596ac7, DEV2.15.0/migrations157–158. Smoke95 requisições/verificações incluindo polling, 3publicações S1→S2→restoreS1; fixture inativa sem draft/comando ativo. Backup verificado; imagem offline e rebuild consumidor sem rede aprovados. Grants restritos corrigidos após helper inicial falhar antes da troca de imagem; recuperação e smoke PASS. Registro final2026-10-11-workspace-paridade-f7c-dev-final-codex.md prevalece sobre estados candidatos acima.
F7D branch feat/workspace-paridade-f7d basee3a44bc9. Desenho de contrato anexado à spec complemento antes do código: lineage capturado por marcador imutável, hash compatível com operações antigas, histórico desconhecido em consulta; Maestro existente contextualizado ao draft. Implementação e gates ainda pendentes. F8/F9 e ensaios externos seguem pendentes; sem main/produção.

## F7D candidato validado — 2026-10-11
Lineage capturado por nó com contrato hash1, compatibilidade hash0 e restore histórico sem captura em consulta. Maestro usa contexto draft com fence/revision, propostas locais e filtro estrutural de credenciais. SQL78PASS0skip;pytest7325PASS8conhecidas51skip/0NEW;297focados;lint73/73/0NEW;build4PASS;fontes0NUL;browser7+teclado;reviewer ship e documenter preserve incumbente. PR/offline/DEV ainda pendentes, sem declaração de deploy. F8/F9 continuam.
