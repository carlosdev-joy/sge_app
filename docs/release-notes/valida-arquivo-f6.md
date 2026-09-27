# F6 — Configuração e acompanhamento no canvas

A paleta Fluxo passa a oferecer **Valida Arquivo**. O painel permite escolher conexão SSH, tempo máximo, arquivos/datasets, diretório direto ou parâmetro, destinos e políticas por arquivo. A primeira linha pode ser ignorada em texto. A ordem das verificações é editável; a ordem dos jobs continua definida pelas conexões do canvas.

**Conferir impacto** mostra caminho resolvido, origem, destinos, dependentes transitivos, convergências e consequências de ausência/vazio/dados. É prévia estática: não consulta o servidor e perde validade quando o rascunho muda. Erro técnico sempre bloqueia todos os destinos do validador.

O fluxo e as configurações são gravados na mesma transação, com revisão esperada para evitar sobrescrever outra edição. Alterar apenas caminho, arquivo, formato, cabeçalho, ordem, timeout ou políticas do validador não solicita republicação. Alterar topologia, conexão, conjunto de entradas ou destinos exige publicação e respeita a proteção de corridas retomáveis. Configuração nova não modifica retry anterior.

Sem seleção de nó, o painel do pipeline contém **Quando todos os destinos forem pulados**, com botão próprio **Salvar política**. Liberação de pipelines dependentes e notificação são independentes; histórico nunca é opcional. Essa gravação vale para novas execuções e não salva o rascunho do canvas.

No modo de execução, **Validação de arquivos** apresenta conclusão, tentativas, revisão original, caminho original, contagens e motivos. “Liberado para executar” não significa que a etapa executou. O estado efetivo continua no canvas; o histórico é consultável mesmo após remover o validador do cadastro atual.

## Limites e recuperação

- Sem migrations 130–133, o salvamento de validadores é recusado explicitamente.
- Conflito de revisão: conservar o rascunho, conferir a alteração da outra pessoa e recarregar antes de salvar.
- Remover um destino exige atualizar suas referências no mesmo salvamento do canvas.
- Rotas antigas não criam nem convertem validadores. Rename de validador salvo ou alvo ainda referenciado é recusado; remova a referência e salve antes de renomear um alvo, ou recrie o validador com o nome desejado. Corrida ainda retomável pode impedir alteração estrutural.
- Arquivo de texto conta linhas físicas; não interpreta CSV multilinha. Dataset real e importação `dsjob` permanecem pendentes de certificação no ambiente Caixa.

## Deploy

F6 depende da cadeia F2a–F5, incluindo a correção SQL da F4 (#459) e a migration 133 da F5 (#460). Após merges autorizados: aplicar migrations pela etapa 6c, atualizar API, UI/dist e dags/utils como conjunto, reiniciar worker e publicar as DAGs alteradas. Sem novas dependências ou wheels. Nenhum deploy nesta entrega. Roteiro completo e rollback serão consolidados na F7.
