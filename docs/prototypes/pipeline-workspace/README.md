# ORQUESTRA — protótipo navegável de Pipeline

Data: 11/10/2026. Escopo: validação de UX (F1), anterior à implementação no DEV.

O usuário autorizou a preparação deste protótipo para aproximar o produto dos mockups aprovados. **Não é a nova interface já implantada.** Todos os dados, recursos, versões, perfis, estados, tempos e logs são fictícios. Não há chamadas ao DEV, backend, motor de execução, serviço de IA ou serviços de mensagens. O estado vive na memória desta aba; recarregar restaura o exemplo.

## Abrir

Baixe `pipeline-workspace.html` e abra em um navegador moderno. Essa cópia contém tudo e funciona sem instalação, build ou servidor. A página do arquivo no GitHub exibe o código; é necessário baixar o arquivo para interagir.

Para desenvolvimento do protótipo, use os arquivos separados `index.html`, `styles.css`, `model.js` e `app.js`. Opcionalmente execute `node server.cjs` nesta pasta e abra `http://127.0.0.1:8767`. O servidor fica limitado ao computador local. Atualize a cópia portátil com `node build.cjs` após alterações.

## Roteiro de validação com o usuário

1. Na montagem inicial de **Cobrança diária**, selecionar e renomear uma etapa. Abrir Configuração e retornar ao Fluxo: a edição permanece no mesmo rascunho.
2. Abrir a biblioteca pelo botão **Etapas**, adicionar uma etapa e definir dependências nos detalhes. Tentar uma dependência circular: deve ser recusada. Arrastar para organizar. Remover e desfazer (Ctrl+Z).
3. Verificar que Visão geral resume finalidade e agenda sem duplicar formulários. Configuração concentra Identificação, Agenda e dependências, Parâmetros, Execução, Notificações e Documentação.
4. Salvar o rascunho; a versão 2.4 continua preservada. Publicar abre uma revisão explícita e cria uma versão simulada. Em Versões, comparar e copiar uma versão para o rascunho.
5. Em Fluxo → Execução, executar a simulação. Verificar dependências em espera, ramos de extração em paralelo, execução azul e conclusão verde com marca de verificação.
6. Após terminar, selecionar **Falha na qualidade** e iniciar nova simulação. A etapa de qualidade falha e a entrega fica bloqueada. Selecionar a etapa e tentar novamente. Em Tentativas, consultar os dois resultados; em Logs, consultar registros fictícios.
7. Experimentar **Espera por capacidade** (4 segundos fictícios) e **Entrega pulada**. São demonstrações de estados, sem estimativa de fila ou recomendação real de horário.
8. Simular desconexão durante uma execução: congelar os estados e suspender animações até reconectar. O motor fictício continua em segundo plano, como uma corrida real poderia continuar sem o navegador.
9. No seletor de perfil, experimentar Consulta (leitura) e Sustentação (execução/investigação). O controle de acesso é ilustrativo e não constitui segurança de backend.
10. Abrir Pipelines → Criar pipeline, informar nome e domínio, conferir identificador sugerido e entrar em um fluxo vazio. O rascunho aparece no catálogo antes da publicação.

## Direção visual

Referências: `../../mockups/pipeline-workspace/02-pipeline-montagem.png`, `01-pipeline-execucao.png` e `04-criar-pipeline.png`. O grafo domina a tela, com azul de ação, branco nas áreas de trabalho e cabeçalho azul escuro. A biblioteca e o inspetor podem ser recolhidos; a biblioteca começa recolhida até 1360 px para dar espaço ao fluxo. Em celular, o grafo permite rolagem própria e os detalhes aparecem abaixo. Tipografia de sistema, sem fontes ou bibliotecas externas. Ícones deste protótipo são provisórios; a implementação deve usar o conjunto do design system.

## Limites explícitos e passagem ao dev

Este arquivo é uma referência de comportamento e composição. O produto continua em React; os componentes deverão ser adaptados à base existente e ao backend .NET. Não copiar o estado em memória, os perfis demonstrativos ou o motor de simulação para o produto.

Não estão implementados neste protótipo: lease/fence e colaboração multiusuário real, salvamento durável, publicação/reconciliação efetiva de DAG, auditoria, autenticação, integrações com jobs, processamento Python/PySpark, paginação de grandes históricos, logs reais, pan de grafos extensos, rotas profundas, ajuda por IA, malhas e monitores. O aviso de pessoa editando demonstra a visibilidade proposta; não prova um bloqueio real.

Usar como contrato de produto a [especificação](../../spec-ux-pipeline-profissional.md) e o [design de experiência](../../design/pipeline-experiencia.md). O protótipo não substitui esses critérios. A aprovação visual e os ajustes encontrados devem ser registrados antes de implementar as telas no DEV.

## Verificação

`node --check app.js`, `node --check model.js` e `node model.test.cjs` verificam sintaxe e a máquina de estados: dependências, ciclo, espera por capacidade, falha, retomada, histórico de tentativas, ramo pulado e isolamento da versão executada em relação ao rascunho.

A evidência dos testes visuais e do roteiro está em `VALIDACAO.md`. Capturas em `evidence/` documentam o protótipo; não substituem os mockups originais nem representam o DEV.
