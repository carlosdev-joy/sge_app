> Estado consolidado em 12/10/2026: Informatica em leitura; Databricks com duas tentativas reais, a segunda Succeeded em17s, três tarefas e notebook fictício; Control-M com cinco tours guiados e nenhum motor real. Relatos de histórico vazio e acesso pendente são da rodada inicial. A expansão para Malha foi solicitada depois da SPEC Pipeline. Leia o guia do agente para distinguir evidência e proposta.

# Inventário e cobertura

Data da rodada: 12/10/2026, America/Sao_Paulo. Foco inicial confirmado pelo usuário: **Data Integration e os serviços que compõem seu uso, especialmente Monitor**. Databricks e Control-M foram acrescentados depois, com glossário e fechamento premium. Databricks Free Edition foi aberto pelo usuário e observado; Control-M ainda não tem sessão prática.

## Identidade das fontes

| Fonte | Identidade e uso | Tipo de evidência |
|---|---|---|
| Referência UX | `docs/ux-pipeline-profissional` em `52c0c589a3cf8f3dc5d7ee7c110a85416fd8fd85` | Requisito documental |
| Implementação atual disponível | `origin/develop` em `92d14d596c95212d10bd30c3085edde4ce7c6b83` | Inspeção de código; sem certificação do servidor |
| Base citada na matriz antiga | `df1a81caa3ef5400877bf3ab2f798011552143b2` | Baseline histórico, não HEAD atual |
| Informatica | Data Integration e Monitor/CDI, sessão autenticada existente | Observação direta da UI; organização e objetos anonimizados |
| REA | CLI `rea-agents` 6.4.0; registro Codex e skill alinhados na verificação desta sessão | Diagnóstico local, sem conexão CDP ativa |
| Databricks | Free Edition, catálogo e job demonstrativo autorizado ORQ_UX_DEMO; documentos oficiais | Observação direta DB-001…010 parcial, sem execução; complementos documentais |
| ADF/Control-M | Documentos oficiais descritos no registro de fontes | Documentação; não observação de sessão privada |

O clone foi mantido em checkout detached para leitura; `git status --short` sem mudanças de produto. Os originais da SPEC e do protótipo não foram editados. A ausência de confirmação de SHA no servidor DEV significa que “presente no código” não equivale a “funcionando para todos os usuários”.

## Documentos lidos na ordem solicitada

1. `docs/spec-ux-pipeline-profissional.md`: arquitetura, limites, cinco destinos, F1–F6 e aceites.
2. `docs/design/pipeline-experiencia.md`: composição, tokens, painel, teclado, estados e responsividade.
3. `docs/matriz-paridade-pipeline.md`: onze tipos, oito agendas, permissões, sessão, publicação, versões e operação.
4. `docs/mockups/pipeline-workspace/README.md`: quatro mockups e seus limites.

Os caminhos estão presentes na revisão documental. A correção do Shell está em **`docs/prototypes/pipeline-workspace/VALIDACAO.md`**, com `evidence/17-shell-corrigido.jpg`; ela não aparece no README dos mockups. Essa diferença de localização foi registrada, sem inventar conteúdo.

Também foram conferidos `docs/spec-pipeline-workspace-dotnet.md`, `docs/spec-workspace-paridade-complemento.md`, `docs/workspace-homologacao-f9.md`, README/VALIDACAO/fontes do protótipo portátil, mockups 01/02/03/04, a captura Shell e `docs/ux-pipeline-progresso.md` no develop. As instruções locais consultadas incluem `CLAUDE.md`, regras frontend/backend e `docs/ui-temas-cores.md`. Detalhes de leitura integral, hashes e referências externas ausentes estão no [manifesto](../evidencias/manifesto-fontes-orquestra.md).

Conflitos históricos foram resolvidos pela decisão mais recente: Montagem e Execução são abas principais; edição de etapas exclusivamente pelo Fluxo/Montagem; Configuração edita o pipeline. A opção de lista de etapas da SPEC antiga não prevalece sobre a decisão atual. O mockup 03 de Malha continua referência futura, separada deste workspace.

## Conexão e método

O endpoint solicitado `http://127.0.0.1:19222` recusou a conexão. A própria CLI REA retornou `provider_unavailable / endpoint_unreachable` ao listar alvos. O inventário das ferramentas desta conversa não continha REA MCP. A instalação local e o registro válido não provam conexão do servidor nesta sessão.

O inventário de navegador disponível mostrou a aba autenticada no navegador integrado do Codex, não um Chrome CDP dedicado. Após o usuário autorizar o uso da sessão aberta, foi usada a conexão de navegador para ler DOM/acessibilidade, observar pixels e navegar. REA não foi atribuído a cliques, inspeções ou capturas que não realizou. Não se escolheu um endpoint alternativo por adivinhação nem se exportou autenticação para outro navegador.

Os registros UI-001…UI-021 e DB-001…DB-012 são resumos sanitizados de tela/ação/resultado. As capturas Informatica foram retiradas da entrega após revisão: a API ignorou o deslocamento solicitado e preservou identificação de organização/asset. Suas evidências permanecem textuais, sem esses dados. As imagens Databricks mostram apenas a demonstração fictícia autorizada, sem conta/workspace/ID; não mostram necessariamente todo o canvas. Não existem dumps de DOM, cookies, armazenamento, scripts de negócio, logs, IDs de execução, HAR ou corpos de requisição no pacote.

## Cobertura A–G

| Área | Percursos e evidências | Coberto diretamente | Não certificado / motivo |
|---|---|---|---|
| A. Estrutura/navegação | UI-001…005,014,015,018…020 | Home, serviço CDI, Explore, projetos/tipos/tags, busca por nome/descrição, filtros/ordenação, página de dependências e retornos por asset aberto | Tags não aplicadas; edição concorrente/rascunhos/versões e restrição RBAC não ensaiadas |
| B. Construção visual | UI-006,008…011 | Biblioteca, canvas, dois ramos paralelos, Start/End, seleção, zoom e recolhimento de propriedades; três larguras | Adição/drag/Delete/conexões/organização não executados para evitar modificar o asset; fluxo grande/minimap não certificado |
| C. Propriedades | UI-007,020 | Inspector muda com seleção; abas General/Data Task/Input Fields/Events/Error Handling; Mapping Task separa resumo, conexões, agenda e notificações em seções | Valores, expressões, conexões reais e validação de campos não copiados nem alterados; modo Edit da Mapping Task não aberto |
| D. Desenvolvimento | UI-006,008,015,018,021 | Save desabilitado em leitura, Publish/Run/Validation e Unpublish visíveis; New Asset cancelado; Escape retorna foco | Save/validar/publicar/concorrência/dirty/restore não acionados. Presença de botão não prova operação nem autorização de backend |
| E. Agenda/dependências | UI-007,019,020; DOC-INF01/02 | Uses/Used By, vazio de dependentes, presença de Task Schedule e políticas de erro no inspector | Editor completo de calendário, fuso, retry, timeout e agenda de taskflow não ensaiados. Informação complementar é documental |
| F. Operação | UI-012,013,016,017 | My Jobs vazio; Monitor CDI com Running/All Jobs, paginação/filtros, subtarefas, detalhe Current Run e instância suspensa; ações visíveis | Logs/downloads/parâmetros sensíveis não lidos; nenhuma execução/retry/stop; transições, tentativas e comparação entre corridas não observadas |
| G. Qualidade | UI-006…011,015,021 | Hierarquia, seleção distinta, painel recolhível, recorte 1440/947/390, Escape e retorno de foco, nomes truncados e rótulos técnicos de acessibilidade | Contraste/teclado integral/leitor de tela/desempenho cronometrado/modo escuro não auditados. Documento sem overflow global não significa canvas utilizável |

Nenhuma porcentagem de cobertura foi calculada: as áreas têm granularidades diferentes e há limites de segurança e de acesso. As telas visitadas não encerram todos os cenários da área.

## Inventário de telas e estado do recorte

| Tela | Estado observado | Evidência |
|---|---|---|
| Home CDI | Entradas por intenção e assets recentes | UI-001 |
| Seletor de serviços | Serviço atual reconhecível; outros serviços apenas inventariados | UI-002 |
| Explore: Projects and Folders | Breadcrumb, localização, estado, busca/filtro/ordenação | UI-003 |
| Explore: Asset Types | Lista por tipos; entrada Taskflows | UI-004 |
| Explore: Taskflows | Busca demonstrativa por nome/descrição; paginação do catálogo | UI-005 |
| Taskflow designer | Canvas, biblioteca, propriedades, ações separadas | UI-006…011,018 |
| Dependências do taskflow | Uses e Used By, inclusive ausência de dependentes | UI-019 |
| Mapping Task / read | Seções de consulta; botão Edit não utilizado | UI-020 |
| New Asset | Seleção CDI/Orchestration; cancelamento e Escape | UI-015,021 |
| Templates CDI | Categorias e busca; nenhuma criação | UI-014 |
| My Jobs | Sem resultados nesta sessão, filtros e carimbo PDT | UI-012,013 |
| Monitor: Running Jobs CDI | Lista e drill-down de subtarefas | UI-016 |
| Monitor: All Jobs CDI | Histórico com filtros/paginação e detalhe de corrida | UI-017 |

Administrator, conexões administrativas, outros serviços, dados/scripts de negócio e ações mutantes ficaram fora da exploração. A presença de serviço no seletor não estabelece licença, acesso ou necessidade no Orquestra.

## Fases, backlog e limite de conclusão

F1 documental e F3/F4/F5 têm implementações/registros já ocupados. O develop contém o patch de corrida exata integrado, embora trechos de release notes ainda digam candidato. F2 permanece lacuna; F3/F5 aceites integrados e F6 piloto não foram encerrados nesta auditoria. A fonte [evidencias/fontes-dev.md](../evidencias/fontes-dev.md) lista arquivos/linhas.

O backlog canônico `dbo.etl_backlog` não foi acessado. Esta entrega não promete ausência de duplicatas e não reserva numeração de fase, migration ou versão. UX-01…UX-12 são itens de revisão local, a reconciliar antes de implementar.

## Acréscimo Databricks: cobertura parcial prática

DB-001/002/009 cobrem navegação, lista vazia, filtro nome/ID, escopo e opções de colunas. DB-003/004/005 cobrem criação/persistência autorizada de ORQ_UX_DEMO e duas tarefas de condição literal, com dependência do ramo true e Run if All succeeded. DB-006 cobre prévia de tipos de gatilho cancelada sem Save; DB-007 agrupa configurações/políticas; DB-008 mostra histórico vazio; DB-010 registra reabertura da demonstração salva.

Exceção de escrita expressa do usuário: somente criação da demonstração Databricks, sem execução, agenda ou dados externos. Nenhuma mutação Informatica foi autorizada ou realizada. Nenhuma permissão, política, preferência de colunas ou pagamento foi alterado. O aviso de não suporte a controle automatizado permaneceu visível; a navegação normal funcionou sem mudar detecção/proteções.

O [documento 10](../referencias/databricks/jornadas-e-execucoes.md) especifica percursos/limites. Logs/repair/tentativas/transições reais, concorrência, governança premium e responsividade não foram certificados. Free Edition não representa todos os recursos empresariais.

O pacote está preparado para revisão da rodada Informatica e autoria Databricks. O fechamento comparativo premium depende de Control-M prático, dos recortes operacionais ainda indisponíveis e dos ensaios reais do Orquestra identificados em 06 e 08.



## Atualização após autorização de execução e estudo da Malha

O estado atual inclui DB-011/012: primeira tentativa real falhou com tarefas puladas; segunda, com notebook fictício adicional, concluiu Succeeded em17s e mostrou total30. Graph/Timeline/List foram inspecionados. As declarações anteriores de histórico vazio/ausência de execução descrevem a rodada inicial. Repair/retry, carga e RBAC premium continuam não ensaiados.

Control-M CTM-006–010 inclui cinco tours guiados: Build a workflow, Error handling, Reference folder, Forecast e Self-Healing. As pendências anteriores de liberação estão resolvidas. Sem console operacional, nenhum job real Control-M foi executado. A nova proposta de composição, configuração, operação, recursos e governança está em [12-malha-conceitos-e-reestruturacao.md](../modulos/malhas/conceitos-e-reestruturacao.md); amplia o estudo, sem reclassificar recursos novos como SPEC Pipeline existente.
