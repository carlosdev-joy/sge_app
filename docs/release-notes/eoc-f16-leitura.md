# EOC-F16 — incremento contrato e leitura

Contrato e schema aditivo inerte da Malha versionada. Consulta autenticada por UUID exato ou ID da corrida; histórico sem vínculo é legacy_unversioned. Autoria/opt-in/ativação/restore ainda indisponíveis, F16 não encerrada.

## Deploy DEV

Backup COPY_ONLY/CHECKSUM/VERIFYONLY antes de migrations195/196. Aplicar195 schema e196 versão2.35.0; reiniciar somente API, publicar dist compilada por último. Sem dependência/env/DAG novos, sem restart de worker. Reaplicar migrations não duplica dados. Ausência de195 retorna503nominal. Sem backfill.

## Smoke

Confirmar versão/Admin/schema sem pendências e saúde/assets. Fixture própria inativa: capability legacy_unversioned/auth401/UUIDinválido422; corrida antiga não resolve cadastro atual. Criar referências próprias exatas em transação SQL e comprovar leitura do UUID e membro; verificar corrida vinculada preserva UUID/hash e não substitui por versão efetiva. Limpar fixtures e revogar sessão401. Não executar pipelines nem enviar comunicação de negócio.

## Pendências da fase

Próximo incremento: guardas de todos escritores legados/API/DAG/guardiã, opt-in explícito, publicação atômica, snapshot exato concorrente, restore cria draft. Não avançar phase17 até aceite técnico integralF16. Gates humanos/externos anteriores seguem Backlog192.
