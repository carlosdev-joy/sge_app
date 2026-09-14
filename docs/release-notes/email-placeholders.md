# Seletores de placeholders de e-mail — F1

Spec: `docs/spec-email-seletor-placeholders.md`.

## O que muda
- Modelos: listas de marcadores no assunto sugerido e corpo.
- Nó de e-mail: listas no assunto, corpo livre e nome do anexo. O assunto continua editável quando um modelo está selecionado.
- Cada marcador mostra explicação e exemplo ilustrativo. A inserção substitui a seleção ou entra na posição do cursor.
- Assunto/corpo permitem informar o nome exato para `{tabela:NOME_DO_NO}`. O SQL precisa ser vizinho direto; o qualificador não atravessa nós intermediários.
- O anexo oferece apenas marcadores compatíveis: `{data}` e `{inicio}` possuem barras, por isso a lista recomenda `{odate}`. Tabela não é um nome de arquivo.

## Deploy
Atualizar `ui-react/dist/`. Sem migrations, dependências ou alterações de backend/worker nesta fase. Para usar a tabela SQL em instalações antigas, seguir também `email-tabela-sql.md`: atualizar dags, reiniciar o worker e republicar pipelines.

## Conferência
a) Criar um modelo, inserir marcadores no assunto/corpo, salvar e reabrir.
b) No nó com modelo selecionado, inserir no assunto e verificar que o corpo continua vindo do modelo.
c) Selecionar Corpo livre e substituir um trecho selecionado por `{tabela}`.
d) Informar um nome SQL válido no seletor de tabela qualificada; conferir o token inserido.
e) No nome do anexo, inserir `{odate}`; conferir que tabela, data e inicio não são oferecidos.
f) Conferir foco, teclado e leitura nos temas claro e escuro.

## Próxima fase
F2 mostrará os nomes SQL derivados do grafo e avisos contextuais sobre origem ausente/ambígua. F1 permite digitar o qualificador e explica o pré-requisito, mas não valida se o nó existe no fluxo.
