# Verificação do protótipo de Pipeline

Executada em 11/10/2026, no navegador integrado do Codex. Ambiente exclusivamente local, com dados fictícios. Esta verificação confirma os cenários listados; a aprovação de UX pelo usuário ainda está pendente. Não confirma implementação no DEV, segurança multiusuário, publicação real ou desempenho do produto.

## Evidência observada

| Cenário | Resultado |
| --- | --- |
| Editar nome de etapa, trocar para Configuração e retornar | Alteração preservada no rascunho; cabeçalho informa alterações não salvas. |
| Alterar horário, salvar e publicar | Revisão 8 salva; versão 2.4 preservada; revisão de publicação cria versão simulada 2.5 em Versões. |
| Sucesso da execução | Fluxo percorre dependências e conclui 6/6 etapas; estados verdes e marcas de verificação. |
| Desconexão | Banner com último sinal, estados congelados e animação calculada como `none`; reconexão recupera andamento/conclusão. |
| Falha de qualidade | Qualidade falha, entrega bloqueada; detalhe explica motivo fictício e oferece tentar novamente. |
| Retomada da etapa | Conclusão 6/6; histórico mantém tentativa 1 com falha e tentativa 2 concluída. |
| Capacidade | Primeira etapa aguarda capacidade, com motivo e aviso de simulação por 4 segundos; a corrida depois conclui 6/6. |
| Entrega pulada | A etapa de entrega permanece Pulada por condição, sem início e sem tentativa; a corrida conclui com 5 etapas executadas e 1 pulada. |
| Consulta | Execução desabilitada; campos de configuração em leitura. |
| Sustentação | Execução habilitada; nome do pipeline permanece em leitura. |
| Criar Carga de clientes | Identificador sugerido `CARGA_DE_CLIENTES`; abre fluxo vazio; inclusão de primeira etapa funciona. |
| Rascunho antes de publicação | Catálogo mostra novo pipeline como Ainda não publicado, com responsável e revisão. |
| Desfazer etapa adicionada | Fluxo volta a vazio; validação informa adicionar a primeira etapa. |
| Dependência circular | Checkbox volta a desmarcado e aviso informa que criaria um ciclo. A automação de `check()` relata recusa de mudança, que neste cenário é o resultado esperado. |
| Arrastar e desfazer | Etapa consolidar muda de (420,172) para (458,223); desfazer restaura posição e rascunho sem alterações. |
| Desktop 1440 e largura padrão ~1280 | Canvas e detalhes acessíveis; biblioteca recolhida inicialmente na largura padrão para priorizar fluxo. |
| Largura 947 | Biblioteca e inspetor alternam; selecionar etapa volta a mostrar detalhes. |
| Celular 390 | Página sem transbordamento horizontal global; canvas com rolagem própria; configuração acessível. |
| HTML portátil | Arquivo gerado aberto no navegador com montagem, alternância dos painéis e execução funcionando. |
| Console | Sem erros/avisos de JavaScript na leitura realizada após execução e desconexão. |

O navegador limitou uma espera automatizada pela conclusão antes de o fluxo terminar. A observação posterior confirmou a conclusão em 12,3 segundos simulados, com 6/6 etapas. Esse limite da automação não foi tratado como sucesso antecipado.

## Verificação do modelo

Comandos de sintaxe e `node model.test.cjs` concluídos com código de saída 0. O teste cobre dependências, ciclo, política numérica inválida, espera por capacidade durante 4 segundos, falha e retomada, duas tentativas preservadas, entrega pulada e snapshot isolado do rascunho.

A espera por capacidade e a entrega pulada foram verificadas no modelo automatizado e no navegador; não se deve confundir isso com dados reais de ocupação de slots ou uma recomendação de agenda. A publicação foi verificada apenas na simulação local.

## Capturas

- `evidence/01-montagem.jpg`: montagem inicial na largura padrão.
- `evidence/02-execucao.jpg`: primeira etapa em execução.
- `evidence/03-concluida.jpg`: todas as etapas concluídas.
- `evidence/04-falha.jpg`: qualidade falhou e entrega está bloqueada.
- `evidence/05-retomada.jpg`: duas tentativas e conclusão após retomada.
- `evidence/06-criacao.jpg`: criação com nome e identificador sugerido.
- `evidence/07-desktop-1440.jpg`: biblioteca, canvas e inspetor.
- `evidence/08-mobile-390.jpg`: adaptação para celular.
- `evidence/09-tablet-947.jpg`: detalhes em largura intermediária.
- `evidence/10-capacidade.jpg`: etapa aguardando capacidade fictícia.
- `evidence/11-entrega-pulada.jpg`: entrega pulada sem execução ou tentativa.

Capturas registram momentos do protótipo, com cenários fictícios. Os mockups originais continuam em `docs/mockups/pipeline-workspace/`.

## Próxima validação

Pedir ao usuário que percorra criação, montagem, configuração e investigação, registrando ajustes por tela. Após aprovação, o dev no servidor deve adaptar componentes React existentes, ligar contratos .NET e estados do motor, aplicar RBAC/lease reais, testar regressões e comparar capturas do DEV com este protótipo e os mockups. Nenhuma dessas integrações foi implementada nesta etapa.
