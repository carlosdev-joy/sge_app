# F6 — rodada completa de piloto e consolidação

Autorizada pelo usuário após DEV2.12.0/PR484: rodar F6 antes de ajustar funcionalidades ausentes. Base211289ff774053ee1ad1ba7816a483fe564e4c69. Esta fase testa e documenta; diferenças de paridade serão inventariadas, não transformadas em funcionalidades sem nova rodada de ajustes.

Gates: criação/salvar/validar/publicar/executar/log real em bancada sintética própria; dois editores, lease/fence/revisão; publicação idempotente e recuperação por restart; conflito durante execução; negativas de permissões; navegação antiga/piloto desligado; falha upstream sem interromper legado; desempenho API p95<500ms, interação<200ms, carregamento<2.5s, CLS<.1 e bundle<300KB gzip medidos e limites declarados; fluxos grandes100/300etapas em fixture; pacote offline verificado e reconstruído sem rede. SQL reais isolados; suite Python versus base; build/dist por último se fonte alterada.

Somente DEV e recursos sintéticos isolados, sem dados de clientes, DataStage real/Caixa ou promoção produção. Não aumentar concorrência global; testes de execução limitados a dois comandos próprios. Reiniciar apenas reconciliador/workspace necessários com verificação e recuperação; sem DB/volumes globais. Candidato identificado por SHA e relatório separa PASS, FAIL, não exercitado e limites.
