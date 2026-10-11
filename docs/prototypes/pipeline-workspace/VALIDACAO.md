# Verificação do protótipo de Pipeline

Executada em 11/10/2026, no navegador integrado do Codex. Ambiente exclusivamente local, com dados fictícios. Esta verificação confirma os cenários listados; a aprovação de UX pelo usuário ainda está pendente. Não confirma implementação no DEV, segurança multiusuário, publicação real ou desempenho do produto.

## Primeira versão — evidência histórica (navegação substituída pela revisão abaixo)

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


## Revisão: abas diretas e opções reais — 11/10/2026

Base de código inventariada: develop df1a81caa3ef5400877bf3ab2f798011552143b2. Nenhuma operação no DEV. A matriz em docs/matriz-paridade-pipeline.md diferencia capacidade existente, destino proposto e integração pendente.

| Verificação desta revisão | Resultado observado |
|---|---|
| Navegação principal do Pipeline | Cinco abas: Visão geral, Montagem, Execução, Configuração e Versões; zero faixas flow-toolbar/seletor de modos |
| Biblioteca real | 11 tipos adicionados individualmente; cada adição abre propriedades e eleva de 6 para 7 nós; desfazer restaura o fluxo |
| Agenda | Oito modalidades selecionáveis, com campos condicionais; Sob demanda sem horário automático |
| Governança | Inativação revela Motivo da inativação; flags sem movimento, SLA, pool e retries acessíveis no grupo próprio |
| Execução | Inicia pela aba própria, conclui 6/6; histórico abre em janela e Abrir execução retorna à corrida no canvas |
| Investigação | Logs da etapa sem sair de Execução; tentativas mantêm identidade da corrida e etapa |
| Falha e retomada | Falha na qualidade bloqueia entrega; nova tentativa conclui 6/6; tentativa 1 Falhou e tentativa 2 Concluída preservadas |
| Experiências | Consulta desabilita agenda e edição da etapa; Sustentação acessa investigação operacional |
| Larguras | 1440×960, 1280×800 e 390×844 sem transbordamento horizontal do documento; canvas móvel mantém rolagem própria |
| Ajuste ao canvas | Em 1440 px, canvas 740 px e largura rolável 740 px; frame ajustado 716 px; texto longo do comando contido no nó |
| Console | Sem erros ou avisos no trecho consultado após os cenários |
| Sintaxe/modelo | Verificações concluídas com saída 0; suíte do modelo preservada |

Capturas desta revisão: 12-montagem-abas.jpg, 13-execucao-abas.jpg, 14-historico-integrado.jpg, 15-agenda-real.jpg, 16-mobile-abas.jpg. As capturas 01–11 registram a primeira versão.

Não certificado: equivalência dos payloads reais, validações específicas completas, catálogos, importação, lineage, comparação entre versões, datas operacionais, reprocessamento/pausa remotos, valores protegidos, multiusuário, desempenho ou envio/execução real dos 11 tipos. O simulador genérico não interpreta as configurações dos componentes. A interface antiga só deverá ser substituída no DEV após a matriz de preservação ter implementação e evidência por capacidade.


### Correção do componente Shell
Reprodução no navegador: o item Shell tinha 842 px de altura, com min-height herdada de 824 px no ícone. Causa: classe shell usada simultaneamente no ícone de tipo e na estrutura da página. Correção: classes de ícones isoladas pelo prefixo kind-, preservando o estilo da estrutura. Nova medição: Shell 52 px, todos os 11 ícones da biblioteca 28 px, demais itens entre 52 e 67 px conforme quebra do texto. Inclusão do Shell no canvas e campos SSH/comando conferidos. Captura: evidence/17-shell-corrigido.jpg.
