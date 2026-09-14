# Spec: Seletores de placeholders e orientação SQL → E-mail — Orquestra
Data: 2026-09-14 · Status: em execução (F2)

## 1. Visão
Permitir inserir os marcadores disponíveis diretamente nos campos de composição do e-mail, tanto nos modelos quanto no nó. Explicar na própria configuração como o resultado do SQL chega ao e-mail, evitando que uma prévia com dados fictícios seja confundida com a execução real.

## 2. Escopo
**IN:**
- Lista de inserção no assunto sugerido e corpo dos modelos, no assunto e corpo livre do nó e no nome do anexo.
- Catálogo com descrição, exemplo e disponibilidade por campo; inserção na posição do cursor, preservando seleção e foco.
- Marcadores atuais: pipeline, job, data, odate, linhas, status, inicio, duracao, execution_id, tabela e tabela:NOME_DO_NO.
- No nó, oferecer os qualificadores reais dos SQL imediatamente anteriores. Nos modelos reutilizáveis, permitir informar o nome e explicar que a disponibilidade depende do fluxo que usar o modelo.
- Orientação sobre conexão, SELECT, execução, publicação do fluxo, vizinhança direta e diagnóstico pelos logs.
- Avisos sobre tabela sem origem direta e qualificador incompatível, inclusive quando o corpo vem de modelo carregado.

**OUT (explícito):**
- Atravessar automaticamente Decisão ou outros nós para buscar SQL distante; isso altera a regra atual de execução e exige decisão própria.
- Criar variáveis arbitrárias a partir dos aliases das colunas SQL.
- Interpolar nome/descrição do modelo, identificação do nó, destinatários e raiz do anexo: esses campos não são interpolados pelo operador atual. Não oferecer marcadores que sairiam literais nesses campos.
- Tabela em nome de arquivo, anexação automática CSV, alteração dos limites do resultado ou envio de e-mails reais durante testes.
- Alterar produção ou afirmar a causa da execução relatada sem identificar pipeline/run e consultar evidências.

## 3. Arquitetura proposta
- React 19/Vite/Tailwind, mantendo componentes e tokens atuais.
- Reusar a inserção de `ui-react/src/components/ui/PlaceholderPicker.tsx`; criar um seletor específico para e-mail se necessário para listar descrições sem alterar outros consumidores.
- Catálogo compartilhado a partir de `components/etapas/fluxoTypes.ts` e `previaEmailDados.ts`, com compatibilidade por campo. Conferir contrato com `dags/utils/email_operator.py` e validadores API/worker.
- Integrar em `components/admin/EmailModelos.tsx` e `components/etapas/paineis/PainelEmail.tsx`.
- Passar o contexto de nós/dependências do editor de fluxo ao painel para gerar `tabela:<nome real>`; usar nomes de jobs usados na publicação, não títulos inventados.
- Acrescentar orientação em `components/etapas/paineis/PainelSql.tsx`.
- Backend FastAPI/SQL Server, `api/routers/email.py` e `api/services/email_modelos.py`: contrato de persistência preservado.
- Orquestração: manter `dags/etl_dag_factory.py`, `dags/utils/sql_node.py` e `email_operator.py` com a regra de vizinhos imediatos. Tabela no corpo é HTML ou texto; no assunto é resumo; não integra o mapa do anexo.
- Modelo selecionado: editar o corpo no cadastro de modelos; o assunto sugerido não substitui retroativamente o assunto de nós existentes.

## 4. Modelo de dados
Sem tabelas, colunas, migrations ou dependências novas. Os marcadores continuam gravados nos textos existentes. Nomes SQL são derivados do grafo e não persistidos em catálogo paralelo.

## 5. Fases
### F1 — Inserção nos campos de composição
- Entregável: listas no assunto/corpo do modelo, assunto/corpo livre do nó e nome do anexo, com catálogo e exemplos compartilhados.
- No anexo, excluir tabela e qualificadores de tabela, além de data/inicio (formatam barras incompatíveis com nome de arquivo); orientar odate. Nos modelos, oferecer qualificador com nome informado e explicação de dependência do fluxo.
- Aceite: inserir no meio do texto ou substituir seleção funciona; teclado/foco preservados; assunto continua disponível com modelo selecionado; prévia distingue exemplo de dado real; salvar/reabrir preserva texto.
- Validação: TypeScript `tsc -b`, ESLint comparado com main (zero novos), build/dist atualizados, pytest comparado com main e smoke dos campos nos dois temas. Testar inserção em input/textarea com seleção e compatibilidade do catálogo com runtime.
- Revisão adversarial multi-agente antes da PR. PR: `feat: adiciona seletores de marcadores na composição de e-mails`.

### F2 — Origem da tabela e ajuda de configuração
- Entregável: qualificadores dos SQL reais diretamente anteriores, avisos contextuais e instruções nos painéis SQL/E-mail; manual atualizado.
- Aceite: SQL → E-mail oferece o nome correto; dois SQL oferecem ambos e explicam a ambiguidade de tabela sem qualificador; SQL → Decisão → E-mail informa a limitação sem afirmar disponibilidade; renomear/religar nó atualiza a lista; modelos com marcador incompatível geram aviso quando carregados; falha de carregamento não é apresentada como ausência comprovada de SQL.
- Avisos não reescrevem os textos salvos nem mudam ligações/condições do fluxo. Ajudas mostram republicação e restart necessários para instalações antigas.
- Validação: `tsc -b`, ESLint e pytest comparados com main, build/dist, testes do contexto com zero/um/dois SQL e nó intermediário, smoke de criação/edição nos dois temas.
- Revisão adversarial multi-agente antes da PR. PR: `feat: orienta a origem das tabelas nos nós de e-mail`.

## 6. Riscos e mitigações
| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | Lista divergir do mapa do worker | Marcadores chegam literais | Catálogo compartilhado e verificação de contrato por campo |
| 2 | Perder cursor ao clicar na lista | Conteúdo inserido no local errado | Preservar seleção, devolver foco e testar substituição |
| 3 | Modelo reutilizado em outro fluxo | Qualificador aponta para nó inexistente | Aviso contextual no nó e descrição no modelo |
| 4 | Instalação antiga ou DAG não republicada | Tabela ausente apesar de UI nova | Orientação de deploy e logs; não confundir prévia com execução |
| 5 | Adicionar ligação SQL para contornar Decisão | Condição de envio alterada | Não modificar grafo automaticamente; avaliar ramo da execução relatada |

## 7. Smoke pós-deploy
a) Criar e editar modelo; inserir marcador no assunto e corpo e conferir persistência.
b) Inserir no assunto do nó com modelo selecionado; confirmar que permanece no assunto correto.
c) No corpo livre HTML/texto, inserir tabela e conferir prévia explicitamente ilustrativa.
d) No nome de anexo, inserir odate; confirmar que tabela não é oferecida.
e) Montar SQL → E-mail com `SELECT 'Teste' AS Descricao, 123 AS Quantidade`; publicar e executar em ambiente de teste autorizado. Conferir publicação XCom e renderização sem precisar enviar para destinatários reais.
f) Dois SQL → E-mail: conferir os dois nomes e o aviso para tabela genérica.
g) SQL → Decisão → E-mail: conferir aviso de vizinhança direta; preservar a condição do ramo.
h) Renomear SQL e verificar atualização da lista/aviso sobre token antigo; conferir claro/escuro e teclado.

## 8. Pendências e decisões em aberto
- Spec aprovada pelo usuário em 2026-09-14. F1 mergeada na PR #415; F2 em implementação.
- Identificar pipeline, execução e ambiente do caso de tabela vazia; consultar log SQL, log E-mail e DAG publicada.
- Se a execução depender de SQL → Decisão → E-mail, avaliar separadamente suporte a ancestrais; a proposta atual documenta a limitação existente.

## Referência operacional atual
O SQL publica automaticamente colunas/linhas em XCom `tabela` na execução real; não existe parâmetro manual de ligação. A primeira célula continua como escalar da Decisão. O e-mail lê essa chave dos vizinhos imediatos na mesma corrida. Um único resultado permite `{tabela}`; com vários, usar `{tabela:NOME_DO_NO}` com nome exato.

O corpo selecionado vem do modelo em tempo de envio. Portanto o marcador deve estar no modelo quando o nó usa modelo, ou no corpo livre caso contrário. `{linhas}` não representa a contagem da tabela SQL: usa `rows_out` de jobs anteriores.

Para o recurso antigo funcionar após deploy: atualizar `dags/`, reiniciar o worker e republicar os pipelines SQL; seguir `docs/release-notes/email-tabela-sql.md` para a release completa. A prévia SQL não publica XCom. Um SELECT deve devolver colunas e linhas pela conexão/banco do runtime. Limite mostrado: 50 linhas e 15 colunas.

Diagnóstico: marcador literal pode indicar operador antigo ou nome incorreto; `(sem resultado)` pode indicar falta de origem direta, DAG antiga, falha SQL/publicação ou ambiguidade; cabeçalho com aviso de zero linhas indica resultado SQL vazio. Confirmar nos logs `[SQL NODE] ... tabela:` e `[EMAIL] tabela de ...`, sem concluir apenas pela aparência do e-mail.
