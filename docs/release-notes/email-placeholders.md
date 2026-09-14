# Seletores de placeholders e origem da tabela SQL — F1/F2

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

## F2 — Origem da tabela
O nó agora lista os SQL diretamente anteriores e oferece os marcadores com seus nomes reais. Não percorre Decisão ou outros nós intermediários. Renomear ou religar atualiza a lista, sem reescrever o assunto/corpo; uma opção removida fica desabilitada.

Os avisos consideram o corpo do modelo selecionado. Modelo indisponível é indicado como não verificado, sem analisar o corpo livre escondido. O painel SQL e a seção Tabela do SQL no e-mail explicam configuração, publicação e execução.

### Conferência adicional
g) SQL → E-mail: conferir nome real e inserir o marcador qualificado.
h) Dois SQL → E-mail: conferir ambos e aviso para tabela genérica.
i) SQL → Decisão → E-mail: conferir ausência de SQL direto e preservar condição do ramo.
j) Renomear SQL: conferir opção nova e aviso sobre marcador antigo; não houve reescrita automática.
k) Selecionar modelo com qualificador incompatível: conferir aviso do corpo efetivo; simular falha no catálogo e conferir mensagem de verificação indisponível.
l) Abrir a ajuda no nó SQL e os pré-requisitos no e-mail.

### Limitação anterior identificada na revisão
O operador de e-mail remove prefixos `log_end_` e `log_start_` dos nomes anteriores. Como SQL é uma task direta, um SQL com esses prefixos pode não ser localizado. F2 avisa quando esse nome é usado; adote um nome SQL sem esses prefixos e republique. Correção do operador fica registrada separadamente; este deploy continua apenas de front.
