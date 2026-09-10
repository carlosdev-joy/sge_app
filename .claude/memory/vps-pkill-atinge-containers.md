---
name: vps-pkill-atinge-containers
description: Nunca usar pkill/killall por padrão de nome no host da VPS — atinge processos dentro dos containers de produção
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 84dac11c-163a-4354-908e-9875529af8ce
  modified: 2026-07-21T04:45:43.554Z
---

Na VPS (LCServer), os processos que rodam **dentro dos containers Docker** aparecem
na tabela de processos do **host**. Então `pkill -f "next-server"`, `pkill -f node`,
`killall node` e afins **matam também os processos das aplicações em produção**.

Aconteceu em 2026-07-21: ao encerrar um servidor Next local de teste com
`pkill -9 -f "next-server"`, derrubei junto os containers do **NexxaFarma**
(`app.lcseguranca.com`), do **LC Decorações** e do próprio **ConectAI**. O Swarm
reiniciou tudo sozinho (restart policy) e o downtime foi de segundos a ~1 min, mas
foi indisponibilidade real, causada por descuido.

**Why:** o padrão de nome não distingue o processo local do processo do container —
e o host enxerga os dois.

**How to apply:** ao subir processo de teste, **guardar o PID** e matar só ele:
```bash
nohup npm start > /tmp/.../server.log 2>&1 &
echo $! > /tmp/.../servidor.pid
# depois:
kill "$(cat /tmp/.../servidor.pid)"
```
Se precisar achar quem ocupa uma porta, usar `ss -ltnp | grep :3000` e conferir se o
PID pertence a um container antes de matar:
`grep -o 'docker-[a-f0-9]\{12\}' /proc/<pid>/cgroup` — se retornar algo, é container,
**não matar**. Depois de qualquer operação assim, conferir
`docker service ls` (tudo 1/1) e bater HTTP nos domínios.
