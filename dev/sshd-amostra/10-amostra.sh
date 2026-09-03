#!/bin/sh
# dev/sshd-amostra/10-amostra.sh — árvore de amostra do servidor de arquivos de DEV.
#
# A VPS não tem servidor DataStage. O container `sshd-amostra`
# (docker-compose.dev.yaml) faz o papel dele SÓ para o SFTP da tela Utilitários
# (spec docs/spec-utilitarios-arquivos.md). Este script roda no arranque do
# container (linuxserver: /custom-cont-init.d) e monta, uma única vez, os casos
# que a spec manda provar ao vivo:
#
#   /dados/bi                       raiz 1 (cadastrar no Admin)
#     2026/cargas/carga_utf8.txt    texto UTF-8 com acento
#     consulta.sql                  texto simples
#     logs/grande.log               ~5 MB — acima do teto padrão (2 MB)
#     imagem.bin                    binário (NUL) → 415
#     .oculto.txt                   oculto (o navegador esconde por padrão)
#     link_fora -> /fora            symlink para FORA das raízes → 403
#   /dados/param                    raiz 2
#     parametros_latin1.param       Latin-1 com "ação" (bytes E7 E3)
#     sem_acesso/                   pasta root:700 — "existe, mas não é legível"
#   /fora/segredo.txt               fora de qualquer raiz (não pode aparecer)
#
# Nada disto vai para o git: o container gera tudo. `docker compose stop/start`
# preserva; só `down` apaga (e o script remonta no próximo `up`).
set -eu

MARCA=/dados/.amostra-pronta
if [ -f "$MARCA" ]; then
    echo "[amostra] árvore já montada — nada a fazer"
    exit 0
fi

BI=/dados/bi
PARAM=/dados/param
FORA=/fora

mkdir -p "$BI/2026/cargas" "$BI/logs" "$PARAM" "$FORA"

printf 'linha 1: carga diária\nlinha 2: ação concluída com sucesso\nlinha 3: fim\n' \
    > "$BI/2026/cargas/carga_utf8.txt"
printf 'SELECT 1 AS x;\n' > "$BI/consulta.sql"

# Latin-1: "ação" = a \347 \343 o (octal de E7 E3). Não passa pelo UTF-8 estrito.
printf 'PARAM_ORIGEM=/dados/bi\nDESCRICAO=a\347\343o de carga\nLIMITE=100\n' \
    > "$PARAM/parametros_latin1.param"

# Binário: NUL logo no começo.
printf '\000\000BIN\000' > "$BI/imagem.bin"
head -c 4096 /dev/urandom >> "$BI/imagem.bin"

printf 'segredo local — oculto\n' > "$BI/.oculto.txt"

# ~5 MB de log numerado (60.000 linhas × ~85 bytes).
awk 'BEGIN { for (i = 1; i <= 60000; i++)
    printf "2026-09-03 00:%02d:%02d linha %06d do log de exemplo para exercitar o teto de tamanho\n", (i/60)%60, i%60, i }' \
    > "$BI/logs/grande.log"

printf 'isto NÃO pode aparecer pela tela\n' > "$FORA/segredo.txt"
ln -sfn "$FORA" "$BI/link_fora"

# O usuário SSH (uid 1000) é dono das raízes: a F4 grava aqui.
chown -R 1000:1000 /dados
chmod -R u+rwX,go+rX /dados
chmod 755 "$FORA"; chmod 644 "$FORA/segredo.txt"

# Pasta que existe mas o usuário SSH não consegue listar (botão Testar do Admin).
mkdir -p "$PARAM/sem_acesso"
chown root:root "$PARAM/sem_acesso"
chmod 700 "$PARAM/sem_acesso"

touch "$MARCA"
echo "[amostra] árvore montada em /dados (raízes: $BI e $PARAM) e $FORA"
