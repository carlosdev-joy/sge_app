---
name: gotcha-docker-cp-symlink
description: "⚠️ GOTCHA: `docker cp arquivo container:/caminho` quando /caminho é um SYMLINK sobrescreve o ALVO do link — no sshd-amostra do DEV o alvo era /bin/busybox e o container perdeu sh/ls/cat"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 55c7dc0b-089c-4e39-9b3c-c60297f1190c
  modified: 2026-09-11T03:06:23.220Z
---

Em 2026-09-11, `docker cp fake_sendmail.sh orquestra-dev-sshd-amostra:/usr/sbin/sendmail` sobrescreveu `/bin/busybox` (o `sendmail` da imagem `linuxserver/openssh-server` é um symlink para o busybox): todo comando do container (`sh`, `ls`, `cat`) sumiu ("exec: sh: executable file not found").

**Why:** o `docker cp` resolve o symlink de destino e grava no alvo, com a permissão do arquivo de origem (644). Num container baseado em busybox isso mata o sistema inteiro.

**How to apply:** antes de copiar por cima de um caminho, `ls -la` nele; se for link, remova o link por dentro (`sh -c 'rm -f /caminho && cp /tmp/x /caminho && chmod 755 /caminho'`) e copie para `/tmp` primeiro. **Recuperação sem recriar o container** (preserva arquivos enviados pelo usuário): `docker create --name tmp <mesma imagem>` → `docker cp -L tmp:/bin/busybox ./busybox` → `docker cp ./busybox <container>:/bin/busybox` (o modo 755 vem junto) → `docker rm tmp`. Lembrar também: `/tmp` de um container recriado por `up -d` some (o `/tmp/dev_sql` da API precisa de novo `docker cp sql`).
