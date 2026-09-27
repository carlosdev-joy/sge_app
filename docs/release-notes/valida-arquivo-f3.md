# Valida Arquivo — F3

27/09/2026. Fundação backend preparada; nó ainda indisponível para criação/publicação. Depende de F2b (#457). Sem merge ou deploy.

## Contrato

Configuração por nó com conexão SSH, prazo e até 100 entradas estáveis UUID. Cada entrada guarda nome real (extensão e caixa preservadas), diretório direto ou parâmetro String/Pathname fixo, destino e políticas. Literal vence referência. Não usa nomes INS/UPD, não modifica arquivos nem presume frescor.

Ausência permite pular ou falhar. Vazio permite pular, falhar ou executar. Dados liberam o destino. Erro técnico bloqueia todos os destinos deste validador; entradas restantes ficam não avaliadas. Várias entradas para um destino combinam por AND. Decisão “liberar” não afirma que o destino executou.

Texto é contado por linhas físicas via SFTP: cabeçalho remove exatamente uma linha; última linha sem newline conta. Leitura em blocos, teto de 2 GiB e prazo de 1–600 s por entrada. Binário/UTF-16 são recusados; não interpreta CSV multilinha. Ausência é somente ENOENT no stat inicial; desaparecimento posterior, permissão, conexão ou timeout são falhas técnicas.

Dataset usa metadados via `orchadmin describe -d -l`, nunca dump de conteúdo. Parser exige um único total explícito `Total records: N` ou `Total rows: N` (também aceita `=`), inteiro não negativo BIGINT. **Esse contrato ainda não foi certificado com a versão DataStage instalada.** Formato não reconhecido falha; jamais inferir zero ou primeiro número de partição/data/bytes. A ativação operacional depende de smoke com saída sanitizada de datasets vazio/com dados.

Conexão Airflow fornece `valida_dsenv`, `valida_orchadmin` e, se necessário, `valida_apt_config` nos extras administrativos, como caminhos absolutos. Não há caminho de projeto fixo no produto. Quoting é obrigatório e negociação SSH também é interrompida pelo prazo, fechando transporte.

## API e persistência

Migration 131 cria cabeçalho `etl_valida_arquivo_no` (conexão, prazo, revisão e atualização) e entradas normalizadas `etl_valida_arquivo_config`. FKs prendem nó e destino ao mesmo pipeline. Revisão esperada e transação evitam sobrescrita concorrente; não há gravação parcial. A revisão pertence ao conjunto do nó, não a cada entrada isolada.

GET/PUT `/pipelines/{pipeline}/valida-arquivo/{task}` e POST no sufixo `/previa` exigem edição. Prévia é estática, aceita grafo do rascunho, mostra cenários, dependentes transitivos e convergências incluindo ramos binários/switch. Não consulta servidor e não prova existência do arquivo. PUT requer um nó do tipo correto já existente; sua criação permanece bloqueada até F5/F6. Sem migration, GET indica indisponibilidade e escrita/prévia respondem 503.

## Deploy e rollback

Aplicar migration 131 após130 pelo fluxo6c. Distribuir API e `dags/utils/valida_arquivo*.py`; reiniciar worker no deploy. Sem novas dependências/wheels ou alteração de UI. Não habilitar o tipo manualmente: faltam snapshot de políticas, diagnóstico durável e guardas, entregues nas próximas fases.

Rollback antes de ativação: reverter código, preservar tabelas e dados. Migrations são aditivas; não apagar configuração. Implementação ainda não altera o pipeline do caso inicial.
