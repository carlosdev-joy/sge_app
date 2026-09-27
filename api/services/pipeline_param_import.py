"""Prévia somente-leitura de parâmetros DS; nunca retorna stdout ou secrets."""
import re
import shlex
import threading
import time

from services import job_params as jp
from services import ssh_datastage as ssh

_SLOTS = threading.BoundedSemaphore(2)
MAX_JOBS = 5
MAX_PARAMS = 100
MAX_BYTES = 262144
TIMEOUT = 45


class ImportErrorDS(ValueError):
    pass


class ImportBusy(ImportErrorDS):
    pass


def validar_pedido(project, jobs):
    if not isinstance(project, str) or len(project) > 128 or not jp.NOME_RE.fullmatch(project):
        raise ImportErrorDS('Projeto inválido.')
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= MAX_JOBS:
        raise ImportErrorDS('Informe de 1 a 5 jobs de origem.')
    if any(not isinstance(j, str) or len(j) > 128 or not jp.NOME_RE.fullmatch(j) for j in jobs):
        raise ImportErrorDS('Nome de job inválido.')
    if len(set(jobs)) != len(jobs):
        raise ImportErrorDS('Não repita jobs de origem.')
    return project, jobs


def parse_paraminfo(text, name, project, job):
    """Lê rótulos conhecidos; nunca confunde Current/Original com Default Value.

    Formatos não reconhecidos interrompem a prévia, sem inventar tipo/valor.
    Encrypted elimina todos os valores retornados pelo CLI, inclusive prompt.
    """
    campos = {}
    for line in text.splitlines():
        if not line.strip() or re.fullmatch(r'\s*Status code\s*=\s*0\s*', line, re.I):
            continue
        if not re.match(r'^\s*(Parameter|Parameter Name|Param Name|Name|Prompt|Type|Default Value|Help Text|Current Value|Original Default Value)\s*:', line, re.I):
            raise ImportErrorDS('Saída DataStage não reconhecida ou multilinha; importação cancelada.')
        m = re.match(r'^\s*(Type|Default Value|Help Text)\s*:\s?(.*)$', line, re.I)
        if m:
            key = m[1].lower()
            if key in campos:
                raise ImportErrorDS('Saída DataStage ambígua; importação cancelada.')
            campos[key] = m[2]
    tipo = re.sub(r'\s*\(\d+\)\s*$', '', campos.get('type', '')).strip()
    tipos = {t.lower(): t for t in jp.DS_PARAM_TYPES}
    tipo = tipos.get(tipo.lower())
    if tipo is None:
        raise ImportErrorDS('Tipo DataStage não reconhecido; confira a versão do comando com o administrador.')
    encrypted = tipo == 'Encrypted'
    if not encrypted and 'default value' not in campos:
        raise ImportErrorDS('Default Value não identificado; importação cancelada.')
    value = '' if encrypted else campos['default value']
    if len(value) > 16000 or '\x00' in value:
        raise ImportErrorDS('Default fora dos limites de importação.')
    item = dict(param_name=name, param_type=tipo, param_source='fixo',
                param_value=value, param_destino='datastage', param_procedencia='datastage',
                param_import_project=project, param_import_job=job, param_descricao=None,
                tem_valor=False)
    # Mesmo contrato do editor; referências DS não resolvidas exigem edição.
    _, erros = jp.normalizar_item(item)
    aviso = ('Valor protegido: informe-o no editor antes de salvar.' if encrypted else
             'Default exige ajuste antes de salvar.' if erros else None)
    return dict(item, aviso=aviso)


def _executar(client, args, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ImportErrorDS('Tempo limite da importação atingido; selecione menos jobs.')
    home = ssh.DS_DSHOME.rstrip('/')
    cmd = ('source ' + shlex.quote(home + '/dsenv') + ' >/dev/null 2>&1 && ' +
           ' '.join(shlex.quote(a) for a in [home + '/bin/dsjob', *args]))
    stdin, stdout, stderr = client.exec_command(cmd, timeout=min(remaining, 15))
    channel = stdout.channel
    out, err = bytearray(), bytearray()
    try:
        while True:
            if time.monotonic() >= deadline:
                raise ImportErrorDS('Tempo limite da importação atingido.')
            if channel.recv_ready():
                out.extend(channel.recv(8192))
            if channel.recv_stderr_ready():
                err.extend(channel.recv_stderr(8192))
            if len(out) + len(err) > MAX_BYTES:
                raise ImportErrorDS('Saída DataStage excedeu o limite de importação.')
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            time.sleep(.01)
        if channel.recv_exit_status() != 0:
            raise ImportErrorDS('DataStage não concluiu a consulta. Confira o projeto e os jobs de origem.')
        # Alguns ambientes imprimem código DS mesmo com retorno shell zero.
        if any(int(c) != 0 for c in re.findall(rb'Status code\s*=\s*(-?\d+)', out + err, re.I)):
            raise ImportErrorDS('DataStage retornou erro na consulta dos parâmetros.')
        return out.decode('utf-8', errors='strict')
    finally:
        channel.close()
        stdin.close(); stdout.close(); stderr.close()


def prever(project, jobs):
    project, jobs = validar_pedido(project, jobs)
    if not ssh.ssh_configured():
        raise ImportErrorDS('A conexão DataStage não está disponível. Solicite configuração ao administrador.')
    if not _SLOTS.acquire(blocking=False):
        raise ImportBusy('Há importações em andamento. Tente novamente em instantes.')
    client = None
    try:
        deadline = time.monotonic() + TIMEOUT
        client = ssh._conectar()
        itens, avisos = [], []
        for job in jobs:
            nomes = _executar(client, ['-lparams', project, job], deadline)
            vistos = set()
            for line in nomes.splitlines():
                name = line.strip()
                if not name or name.lower() == '<none>' or re.fullmatch(r'Status code\s*=\s*0', name, re.I):
                    continue
                if not jp.NOME_RE.fullmatch(name) or len(name) > jp.LIMITE_NOME:
                    avisos.append(f'{job}: um parâmetro usa nome ainda não suportado pelo catálogo.')
                    continue
                if name in vistos:
                    continue
                vistos.add(name)
                if len(itens) >= MAX_PARAMS:
                    raise ImportErrorDS('Limite de 100 parâmetros por consulta; selecione menos jobs.')
                text = _executar(client, ['-paraminfo', project, job, name], deadline)
                itens.append(parse_paraminfo(text, name, project, job))
        return {'parametros': itens, 'avisos': list(dict.fromkeys(avisos))}
    except ImportErrorDS:
        raise
    except Exception:
        raise ImportErrorDS('Não foi possível consultar o DataStage. Verifique a conexão com o administrador.') from None
    finally:
        try:
            if client is not None:
                client.close()
        finally:
            _SLOTS.release()
