# ORQUESTRA — Histórico de Versões

---

## v2.3.0 — Catálogo de Dados

### Catálogo de Dados — Governança
- Nova aba **Catálogo de Dados** dentro da tela de Governança, ao lado da visualização de Lineage
- Busque qualquer tabela ou objeto pelo nome e veja todos os pipelines que a utilizam, com indicação de direção (origem ou destino) e qual job específico faz o acesso
- Resultados em lista expansível por pipeline — mostra projeto, domínio e status ativo/inativo sem precisar abrir o detalhe
- Filtro por **direção**: busque onde o objeto é lido (origem), onde é gravado (destino) ou ambos
- Filtro por **banco de dados** para refinar a busca quando o mesmo nome existe em mais de um ambiente

### Análise de Impacto
- Botão **⚡ Impacto** responde à pergunta: "se essa tabela mudar, quais pipelines ativos serão afetados?"
- Mostra somente pipelines em produção que leem o objeto como origem — útil antes de qualquer mudança na estrutura de uma tabela

### Tabelas mais utilizadas
- Ranking automático dos objetos que aparecem no maior número de pipelines
- Exibe contagem separada de quantos pipelines leem e quantos gravam em cada tabela
- Clicar no nome de qualquer objeto do ranking preenche a busca e executa automaticamente

---

## v2.2.0 — Importação avançada, Agendamento e Última Execução

### Importar Sequence
- Domínio agora é obrigatório ao importar uma sequence
- Novo passo de configuração ao importar: escolha se o pipeline nasce ativo ou inativo, defina a data de início do agendamento e configure quais notificações Teams serão enviadas

### Agendamento
- Novo campo **Data de início** no cadastro de pipeline — permite definir quando o agendamento começa a executar, inclusive com data futura para adiar a primeira execução
- Campos de hora e minuto com visual maior e mais legível, sem corte de caracteres

### Última Execução
- A coluna **Última exec.** na tela de Pipelines agora é preenchida automaticamente sempre que um pipeline termina de rodar, sem necessidade de ação manual

---

## v2.1.0 — Reexecutar do Log e Dependência Circular

### Reexecutar a partir do Log
- Botão de reexecução direto em cada linha da tabela de logs — sem precisar sair da tela ou navegar para outra página
- Avisos claros quando o pipeline não existe ou já está em execução

### Dependência entre Pipelines — proteção contra ciclos
- Ao configurar o campo **Depende de**, o sistema valida em tempo real se a dependência cria um ciclo entre pipelines, impedindo configurações que travem o Airflow
- A validação acontece tanto na tela quanto no momento de salvar

### Visual das Ações
- Ícones menores e mais modernos na coluna de ações das tabelas, ocupando menos espaço
- Tags ao lado do Agendamento no formulário de cadastro, aproveitando melhor o espaço da tela

---

## v2.0.0 — Histórico de Alterações e Dependência entre Pipelines

### Histórico de Alterações (Audit Trail)
- Cada pipeline passou a ter um botão **Histórico** que exibe todas as mudanças feitas: qual campo foi alterado, o valor anterior, o novo valor, quem alterou e quando
- O registro é automático — qualquer edição salva gera uma entrada no histórico

### Dependência entre Pipelines
- Novo campo **Depende de** no cadastro de pipeline
- Quando configurado, o pipeline só inicia após o pipeline pai concluir com sucesso no mesmo dia
- A dependência é gerada automaticamente na DAG do Airflow ao regenerar

---

## v1.2.0 — Correções e Estabilidade

### Falhas recentes
- Corrigida divergência entre o contador de falhas no cabeçalho e os registros exibidos na tela de Logs — agora ambos usam o mesmo período de tempo

### Visualizador de logs
- Logs de execução agora exibem o conteúdo completo com rolagem horizontal, sem quebras indevidas de linha

### Execução de pipelines
- Corrigido comportamento do botão **Executar agora** que em alguns casos não disparava a execução corretamente
