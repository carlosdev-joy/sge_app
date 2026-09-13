# Header ORQ F3 — histórico de versões

Baseline main8e18e74 (PR409 mergeada). Troca branding residual por constantes
ORQ e assinatura institucional de Logo.tsx, sem alterar assets ou o componente.
Consulta autenticada /versao e cache ['versao'] permanecem compartilhados.

Diálogo recebe role/aria-modal/aria-labelledby, botões com tipo explícito,
nome acessível no X e áreas de toque adequadas. Reutiliza useOverlay/trapTabKey
já existentes: foco inicial, ciclo Tab, Escape da camada superior e retorno de
foco. Perfil foca seu trigger antes de abrir, pois o item de versão desmonta.
Backdrop fecha o diálogo pelo handler próprio. Sem reescrever a timeline.

## Verificação

Regressão reproduzida antes: histórico sem semântica de diálogo.
Smoke scripts/smoke_orq_header_changelog.py verifica branding, consulta com token,
cache compartilhado, fallback sem registros, texto com tags como texto, foco,
Tab/Shift+Tab, Escape, X/Fechar e sobreposição com a busca global. Viewports
1440×850,768×650,360×640,320×568,667×375 nos dois temas.
Regressão integrada com os smokes F1/F2 e login por altura.
Build TypeScript/Vite, lint/pytest comparados ao baseline, revisão adversarial.

## Limites, segurança e deploy

Somente ChangelogModal e callback de abertura no perfil; sem modificação em
Login, Sidebar, NAV/RBAC, consulta/ordenação de versões, dados pessoais ou APIs.
Entradas do histórico continuam texto React; nenhuma interpolação HTML nova.
Nenhuma dependência, migration ou asset novo. Frontend dist versionado.
Conferência manual no DEV: abrir versão pelo perfil, ler histórico, Tab entre
botões, fechar com Escape/X/Fechar e conferir retorno de foco; repetir no celular.
Produção pendente do fluxo de deploy. Merge desta fase depende de autorização.

Resultados: TypeScript/Vite OK; ESLint193 antes/depois sem novas ocorrências;
pytest5405 passed/50 skipped/mesmas8falhas. Smokes F1,F2,F3 e login por altura
aprovados no bundle final. Revisão adversarial aprovada. Capturas em320×568 e
667×375 inspecionadas. Consulta autenticada/cache/fallback e sobreposição da
busca global verificados pelo smoke. Sem alteração nos arquivos do login.
