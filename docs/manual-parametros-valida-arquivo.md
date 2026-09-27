# Parâmetros de pipeline e Valida Arquivo

Este guia descreve a implementação preparada nas fases F1–F6. Disponibilidade no ambiente depende de merge, implantação e validação assistida. A integração DataStage real ainda precisa ser certificada **somente no ambiente Caixa**.

## Preparar parâmetros reutilizáveis

No cadastro de Pipelines, abra **Parâmetros Globais**, entre Agendamento e Notificações. “Global” significa compartilhado dentro daquele pipeline.

1. Cadastre nome, tipo e valor na seção DataStage ou Orquestra. Parâmetros Orquestra não são enviados ao DataStage.
2. Para consultar defaults DataStage, escolha o projeto e até cinco jobs. Confira a prévia, escolha a origem quando houver conflito e confirme cada substituição. Aplicar a prévia altera o formulário; **Salvar pipeline** persiste. Cancelar não grava.
3. Valores próprios não são substituídos silenciosamente pela reimportação. Encrypted permanece cifrado/mascarado; não cole segredos em diretórios, descrições ou evidências.
4. No nó DataStage, vincule o nome declarado pelo job a um parâmetro DS. Em Python, o caminho do modo ativo pode usar String/Pathname fixo. Um valor direto preenchido no nó prevalece sobre a referência.

A importação depende da versão e do formato de saída do `dsjob` instalado. Formato não reconhecido é erro, não lista vazia nem confirmação de compatibilidade.

## Montar a validação no canvas

1. Abra o fluxo e arraste **Valida Arquivo**, na categoria Fluxo. Escolha nome, conexão SSH e prazo de 1 a 600 segundos por entrada.
2. Adicione de 1 a 100 arquivos. Escolha Arquivo de texto ou Dataset DataStage e informe o nome real, incluindo extensão e caixa.
3. Selecione um parâmetro String/Pathname fixo para o diretório, ou informe um diretório absoluto diretamente. O diretório direto tem prioridade, mesmo que o parâmetro continue selecionado. A alteração não reconfigura o produtor ou o consumidor do arquivo.
4. Escolha o destino controlado e conecte-o depois do validador. Os dez tipos existentes são aceitos: DataStage, Shell, Python, Stored Proc, HTTP, Decisão, Notificação, SQL, Aguarde e E-mail. Outro validador não é destino direto.
5. Em texto, marque **Pular a primeira linha (cabeçalho)** quando necessário. É uma linha física, não um registro CSV interpretado. Última linha sem quebra final conta; arquivo vazio ou só com cabeçalho resulta em zero. Dataset não oferece cabeçalho.
6. Defina as políticas abaixo. As setas de reordenação mudam a ordem das verificações; as conexões definem a ordem dos jobs. Para execução sequencial, conecte um destino após o outro. Para paralelismo, desenhe os ramos desejados.
7. Use **Conferir impacto**. Confira caminho resolvido, origem, destino, nós posteriores e convergências. A prévia não lê o servidor, não confirma existência nem executa jobs. Qualquer edição torna a prévia anterior desatualizada.
8. Clique **Salvar fluxo**. Erros mantêm o preenchimento. Mudanças estruturais solicitam publicação da DAG; alterações só de valores/políticas passam a valer em novas execuções sem republicação.

| Situação observada | Escolha do usuário / comportamento |
|---|---|
| Arquivo ausente | Falhar e bloquear destinos, ou pular o destino |
| Zero registros considerados | Falhar, pular o destino ou liberá-lo |
| Com registros | Liberar o destino, respeitando suas demais dependências |
| Erro técnico | Sempre falhar e bloquear todos os destinos daquele validador |
| Várias entradas para o mesmo destino | Todas precisam liberar; pular impede execução; qualquer falha bloqueia os destinos do validador |

SSH, permissão, timeout, leitura interrompida, binário incompatível ou resumo DataStage desconhecido são erros técnicos. Não equivalem a arquivo ausente ou vazio. As entradas restantes após interrupção ficam **não avaliadas**.

## Encerrar sem movimento

Sem selecionar um nó, veja o painel do pipeline: **Quando todos os destinos forem pulados**. Escolha se deseja liberar pipelines dependentes e enviar notificação. Clique **Salvar política**, botão próprio desta seção. Essa ação não salva alterações pendentes do canvas.

O histórico sempre é mantido. A execução pode concluir sem movimento mesmo que trabalho a montante tenha ocorrido. Uma decisão que desviou o fluxo sem avaliar arquivos resulta em **sem execução dos destinos**, não em falta de dados. Falha técnica nunca libera dependentes. Notificação habilitada indica intenção; não prova entrega do aviso.

## Acompanhar e retomar

No modo de execução do canvas, escolha a corrida e abra **Validação de arquivos**. Consulte tentativa, revisão original, arquivo/caminho original, linhas físicas e consideradas, motivo e decisão. **Liberado para executar** não significa executado: confira o estado real da etapa no canvas.

O histórico é consultado pelo identificador da corrida, inclusive após remover o validador do cadastro atual. Sem diagnóstico disponível, a tela informa o problema; não presume sucesso.

Retomar preserva a configuração e a política originais. Para usar uma alteração, mantenha a falha anterior no histórico e inicie uma nova execução do zero. Corrida antiga sem snapshot não recebe valores atuais silenciosamente. Mudanças estruturais podem ser recusadas enquanto houver corrida retomável; conclua/cancele conforme o processo de operação ou use outro pipeline.

## Resolver problemas de edição

- **Outra pessoa alterou a revisão:** confira a alteração e recarregue antes de salvar; não repita o envio da revisão antiga.
- **Destino removido:** escolha outro destino válido ou remova a entrada antes de salvar. Grafo e configurações são gravados juntos.
- **Renomear:** alvo referenciado precisa ter suas referências removidas e salvas antes do rename. Validador já salvo deve ser recriado com o novo nome. Essa limitação protege as referências e não autoriza apagar histórico.
- **Migration ausente:** solicite aplicação do conjunto 130–133 e código compatível ao administrador. Não crie nós manualmente no banco.
- **Parâmetro não listado:** só String/Pathname fixo e sem segredo pode fornecer diretório. Confira tipo, origem e disponibilidade do catálogo.

## Limites conhecidos

Arquivos texto: até 2 GiB por entrada, linhas físicas, sem interpretação CSV multilinha; UTF-16/binário recusados. Dataset: leitura de metadados `orchadmin describe -d -l`, até 64 KiB de saída; exige total explícito reconhecido. O parser precisa ser certificado com saída sanitizada da versão Caixa antes do uso operacional.

Não há limpeza automática, garantia de frescor, comprovação de origem por corrida ou controle de concorrência de arquivos compartilhados. Esses itens estão no Backlog (migration 128). O comportamento de limpeza e criação diária informado pelo usuário é premissa do caso inicial, não certificação da ferramenta.
