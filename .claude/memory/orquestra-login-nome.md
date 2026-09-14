# Título do login — 2026-09-14

- Pedido: trocar “Entrar no ORQ” por “Entrar no ORQUESTRA”.
- Branch: `fix/login-nome-orquestra`; mudança em `ui-react/src/pages/Login.tsx`, com `dist/` recompilada.
- Validação: TypeScript e build OK; lint 193 achados antes/depois, zero novos; pytest 5427 passed, 50 skipped e mesmas 8 falhas antes/depois.
- Revisão adversarial sem defeitos. Smoke Chromium passou em 1440/768/360/320, claro/escuro; título quebra naturalmente em duas linhas no celular.
- Pendente: autorização de merge e deploy do front. Conferir o título após deploy.
