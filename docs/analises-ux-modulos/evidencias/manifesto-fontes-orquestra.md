# Manifesto de leitura — referências do Pipeline

Origem documental: `origin/docs/ux-pipeline-profissional`, SHA completo `52c0c589a3cf8f3dc5d7ee7c110a85416fd8fd85`, consultado em `work/sge-reference`. Exportação disponível em `work/ux-reference` (pasta sem `.git`). Base atual do produto auditada separadamente: develop `92d14d596c95212d10bd30c3085edde4ce7c6b83`. Não misturar os dois estados.

## Fontes lidas

- Em ordem: `docs/spec-ux-pipeline-profissional.md`, `docs/design/pipeline-experiencia.md`, `docs/matriz-paridade-pipeline.md`, `docs/mockups/pipeline-workspace/README.md`, via git show da origem documental.
- Integralmente, incluindo continuidade/fechamento, da exportação documental: `docs/spec-pipeline-workspace-dotnet.md` (blob `396de8f0f31e36e02441a8d585c08a8c4fb57681`), `docs/spec-workspace-paridade-complemento.md` (blob `89dbbee76f0b4aa7fab5ae535e4e626abeb02967`) e `docs/workspace-homologacao-f9.md` (blob `8032492ab0b057ef912ac7c04ea7c142357bc981`). A leitura foi parcelada para recuperar trechos truncados, incluindo seção 9 da original e contratos F7B/F7C/F7D, medições F8 e fechamento F9 do complemento.
- Protótipo: `docs/prototypes/pipeline-workspace/README.md` e `VALIDACAO.md` completos; `index.html`, `model.js`, `app.js` completos (435 linhas de app, leitura em três partes), `build.cjs`, `server.cjs`, `model.test.cjs`. HTML portátil `pipeline-workspace.html` inspecionado no início/fim e verificado conter literalmente os fontes completos app/model/CSS. Não executei build nem suíte. Blobs app `ec19eac686261e7ba5f8a19946761b1c7d50e08d`, model `489cf9fffb0da615bd880786857426cb6b7aa6a3`, portátil `0888b26bbb093af71c1e18dd98d8a1fbca2ae6f1`; hash-object dos exportados coincide com árvore documental.
- Atual develop: `CLAUDE.md`, regras frontend/backend, spec UX/progresso, memória UX, regra do backlog, complemento/paridade/homologação e fontes detalhadas em `work/dev-audit.md`. Essas leituras fundamentam classificação atual; documentos da exportação fundamentam direção histórica.

## Capturas e Shell

Existência verificada de todas as 17 capturas referidas em VALIDACAO: 01 montagem, 02 execução, 03 concluída, 04 falha, 05 retomada, 06 criação, 07 desktop1440, 08 mobile390, 09 tablet947, 10 capacidade, 11 entrega pulada, 12 montagem abas, 13 execução abas, 14 histórico integrado, 15 agenda real, 16 mobile abas, 17 Shell corrigido. Nenhuma ausência de arquivo encontrado.

VALIDACAO distingue 01–11 como primeira versão histórica, 12–16 revisão com cinco abas e 17 correção Shell. Capture 17 foi aberta e inspecionada neste complemento: biblioteca e etapa Shell aparecem com ícone de altura normal e inspector SSH/comando; cinco abas sem segunda faixa de modos. A fonte `app.js:78` usa `type-icon kind-${kind}` e o CSS reserva `.shell` para estrutura. A colisão anterior de classe não deve virar requisito/regressão presumida do produto. VALIDACAO relata Shell52px/ícones28px; isso é medição histórica, não remedição nesta auditoria.

01–16 tiveram existência e associação documental conferidas; não foram abertas visualmente por este subagente. Mockups01/02/03/04 foram inspecionados pelo root, conforme sua mensagem, não por mim. Nada foi alegado como novo teste de navegador.

## Conflitos históricos resolvidos pela decisão vigente

1. Original seção2 oferece abas Visão geral/Fluxo/Execuções/Parâmetros/Versões e lista interna de etapas. Seu próprio último parágrafo, Continuidade autorizada, e complemento §§2/8 dizem que PR490 retira Etapas/lista e concentra edição no Fluxo. A decisão posterior da spec UX/matriz prevalece: Visão geral/Montagem/Execução/Configuração/Versões; etapas editadas somente Montagem; histórico/logs dentro Execução, sem segunda faixa. Não reintroduzir lista editável/menu concorrente com base em parágrafo antigo.
2. Original diz estrutura .NET ainda não criada e runtime a fixar; isso descreve baseline 6e711e54 de 09/10. Código develop atual possui estrutura e contratos .NET. Não transformar previsão histórica em pendência atual.
3. Original/complemento/homologação chamam destino Fluxo e componentes WorkspaceRunProperties/FluxoEditor runtime. Current develop já usa WorkspaceCanvas comum + WorkspaceRunInspector/F5; a matriz de preservação mantém capacidades, não exige reintroduzir renderer antigo.
4. Protótipo README diz anterior à implementação e VALIDACAO aprovação UX pendente. É estado daquela entrega documental; não anula implementações F3/F4/F5 presentes no HEAD. Protótipo não prova persistência, lease, RBAC ou integração atual.
5. Protótipo contém owner/fuso/timeout/concurrency50 ilustrativos, comparação rascunho×versão e simulador genérico. Matriz exige campos adicionais especificados separadamente e preservar comparação entre duas versões; não enviar novas chaves nem copiar limites/simulações como contratos reais.
6. F9 fecha DEV2.17.1 para fundação técnica, mas declara DataStage/InformationServer/Caixa/IA/INP campo/SQLIO externos. Isso não fecha F6 de aceite UX atual nem certifica ambientes externos.
7. F1–F6 original, F7A–F9 complemento e F1–F6 UX são séries distintas. Identificar spec + fase sempre, para não propor novo trabalho sobre numeração já ocupada.
8. Original seção9 ordena Pipeline→Malha→Monitor operacional→estratégico→assistente→Academy. São próximos produtos com specs próprias; mockup03 da Malha não amplia Pipeline. 50 worker slots não prova50pipelines; nada autoriza reescrever motores/stack.

## Ausências e limites

- Nenhuma fonte local acima ausente. `work/ux-reference` não é checkout Git; origem comprovada por ref/blob de `work/sge-reference`.
- Links externos da spec (documentação IBM de designer, Databricks monitor e BMC monitoramento) não foram lidos por este subagente; root deve ler se usar afirmações derivadas deles. Nenhuma organização/nome de cliente de material externo foi copiado.
- Evidências de servidor `/root/orquestra-f9-...` mencionadas nos documentos não estão nesta exportação; não acessadas. São relatos históricos com SHA funcional `22045507efde12118d19ba5aac03bf455ce7c7b4`.
- Backlog vivo `dbo.etl_backlog`, DEV, upstreams/catálogos, runtime nativo e piloto não acessados. Nenhuma nova suíte, job, escrita de API ou alteração de código; apenas este manifesto e notas de auditoria em work.
