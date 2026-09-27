# Parâmetros Globais — F2a

O cadastro de pipeline passa a ter cinco passos: Identificação, Agendamento,
Parâmetros Globais, Notificações e Revisão. Os defaults DataStage saem de
Configurações Avançadas e ficam junto ao catálogo Orquestra.

## Uso

- Cadastre parâmetros nas seções DataStage e Orquestra; nomes são únicos no catálogo.
- DataStage continua herdando defaults por nome declarado no job. Valores locais da
  etapa têm prioridade. Parâmetros Orquestra não são enviados ao DataStage.
- Consulte até cinco jobs do projeto selecionado. A prévia mostra candidatos por
  nome e origem. Escolha uma origem e confirme explicitamente a substituição de
  um parâmetro existente. Descartar não grava; aplicar altera apenas o formulário.
- Salvar pipeline persiste o catálogo v2 e seus metadados. Reimportação não é
  sincronização automática.
- Encrypted nunca vem do CLI para a tela: informe o valor no editor. Segredos
  existentes continuam mascarados e preservados quando não alterados.
- Referências nos campos dos nós DataStage/Python são F2b. O nó Valida Arquivo
  pertence às fases seguintes, ainda indisponíveis.

## Limites e erros

Consulta limitada a cinco jobs, 100 parâmetros, 256 KiB por comando, prazo de
45 segundos para processamento após início da conexão e duas consultas
simultâneas por processo API. A conexão SSH tem seus próprios timeouts.
Formato desconhecido, multilinha não reconhecida, código de erro ou falha SSH
interrompem a prévia com mensagem sanitizada. Não se importa saída bruta.

Nomes de origem seguem a régua persistida do catálogo: letra/underscore no início,
letras/números/underscore e no máximo um ponto entre segmentos. Nomes fora dessa
régua são recusados antes da consulta. Parâmetros de ambiente não entram
nesta importação. Não há suporte genérico a outputs localizados.

## Deploy

Publicar API e ui-react/dist juntos. Exige migration 129 da F1 e demais migrations
anteriores pelo fluxo normal da etapa 6c. Não há nova migration ou dependência.
Nenhuma alteração em dags/utils: esta F2a não exige reiniciar worker por código.
A API deve acessar a conexão SSH DataStage já configurada e ter permissão para
dsjob -lparams e -paraminfo. Nenhum job é executado pela importação.

Sem publicação nesta sessão. Antes de habilitar operacionalmente a importação,
validar com saída real sanitizada da versão DataStage instalada: parâmetro String,
tipo numérico, default vazio, Encrypted e Parameter Set quando aplicável.
A bancada local usa dublês e não certifica extração real.

## Smoke após deploy

1. Abrir pipeline com defaults anteriores; conferir valores e guardar sem mudanças.
2. Criar parâmetro ORQ; reabrir e confirmar destino, sem aparecer no contrato DS v1.
3. Consultar job real sanitizado; comparar tipos/defaults com o Designer.
4. Simular conflito com valor personalizado; descartar e conferir preservação.
5. Substituir explicitamente; salvar e reabrir conferindo origem e valor.
6. Confirmar que Encrypted não aparece em resposta, seletor, revisão ou logs.
7. Usuário sem acao_editar recebe 403; projeto não habilitado é recusado.
8. Com 129 ausente/incompleta, catálogo informa erro e salvar outros campos não o apaga.
