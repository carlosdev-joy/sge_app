# Fluxo de desenvolvimento do Orquestra

## Integração e entrega — DEV antes da main (decisão de 27/09/2026)

Esta regra substitui o fluxo antigo de integrar a spec diretamente na `main`.

1. Criar as branches de fase/feature a partir de `origin/develop`. Cada fase mantém sua PR e revisão adversarial.
2. Após QA, integrar por PR na `develop` e publicar o candidato em DEV (`/opt/orquestra-dev`, branch `develop`). A autorização de executar a spec inclui sua integração e deploy em DEV, salvo restrição expressa do usuário.
3. Toda entrega inclui migration idempotente de versão em `sql/migrations/`: registra em Admin → Versões e sincroniza `app_version`/`app_release_name`. Funcionalidade nova incrementa o segundo número e zera o terceiro; correção pequena incrementa o terceiro. Não basta atualizar documentação ou package.json.
4. Fazer backup, aplicar migrations pendentes (incluindo a de versão), atualizar API, UI e DAGs e reiniciar os serviços que carregam código alterado. No DEV, todo compose usa os dois arquivos e `--env-file .env.dev`; não recriar banco/volumes nem usar `up` global.
5. Validar o commit publicado no DEV: saúde, login, versão visível, migrations sem pendências e smoke funcional da entrega. Registrar evidências e limites. Corrigir regressões em novas PRs para `develop` e repetir as verificações afetadas.
6. Somente com DEV validado, abrir PR `develop` → `main`, identificando o SHA validado. A promoção para `main` exige autorização explícita do usuário; desenvolvimento/deploy em DEV não autoriza produção. Se entrar código novo, revalidar o candidato antes de promover.
7. Produção/Caixa usa `main` e autorização própria de deploy. A validação com dataset real/DataStage ocorre exclusivamente na Caixa; simulações em DEV não a substituem.

A spec de parâmetros/Valida Arquivo já havia sido integrada à main antes desta decisão. Inicializar develop a partir desse estado não desfaz esses merges; o novo fluxo vale para as próximas integrações, incluindo a correção da migration de versão.
