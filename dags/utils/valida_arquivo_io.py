"""Leitura restrita: arquivo por SFTP; dataset por comando fixo, sem conteúdo em logs."""
import errno
import posixpath
import shlex
import stat
import time
import threading
from contextlib import contextmanager
from utils import valida_arquivo as va


class ErroTecnico(ValueError):pass


@contextmanager
def prazo_ssh(ssh, timeout):
    # Paramiko não limita event.wait() da negociação exec/subsystem por settimeout.
    # Fechar o transporte desperta essa espera e também bloqueios de leitura.
    vencido=threading.Event()
    def abortar():
        vencido.set()
        ssh.close()
    timer=threading.Timer(timeout,abortar);timer.daemon=True;timer.start()
    try:
        yield
        if vencido.is_set():raise ErroTecnico('Tempo limite SSH excedido.')
    finally:timer.cancel()


def _deadline(limite):
    if time.monotonic()>limite:raise ErroTecnico('Tempo limite de validação excedido.')


def contar_texto(sftp,path,timeout=60,max_bytes=2*1024**3):
    limite=time.monotonic()+timeout
    sftp.get_channel().settimeout(timeout)
    try:
        info=sftp.stat(path)
    except OSError as e:
        if e.errno==errno.ENOENT:return dict(estado='ausente',linhas_fisicas=None)
        raise ErroTecnico('Não foi possível verificar o arquivo.') from None
    if not stat.S_ISREG(info.st_mode):raise ErroTecnico('O caminho não é um arquivo regular.')
    if info.st_size>max_bytes:raise ErroTecnico('Arquivo excede o limite de leitura configurado.')
    count=0;total=0;last=b''
    try:
        with sftp.open(path,'rb') as f:
            while True:
                _deadline(limite)
                chunk=f.read(256*1024)
                if not chunk:break
                total+=len(chunk)
                if total>max_bytes:raise ErroTecnico('Limite de leitura excedido.')
                if b'\0' in chunk:raise ErroTecnico('Conteúdo binário ou UTF-16 não suportado como linhas físicas.')
                count+=chunk.count(b'\n');last=chunk[-1:]
        _deadline(limite)
    except Exception:
        # Arquivo desaparecido após stat também é erro, nunca ausência presumida.
        raise ErroTecnico('Falha durante leitura/contagem do arquivo.') from None
    if last and last!=b'\n':count+=1
    return dict(estado='presente',linhas_fisicas=count)


def comando_dataset(path,extras):
    # Estes caminhos pertencem à conexão administrativa do Airflow, não ao nó.
    dsenv=va.caminho(extras.get('valida_dsenv'))
    orchadmin=va.caminho(extras.get('valida_orchadmin'))
    apt=va.caminho(extras.get('valida_apt_config')) if extras.get('valida_apt_config') else None
    cmd='. '+shlex.quote(dsenv)+' >/dev/null 2>&1 && '
    if apt:cmd+='export APT_CONFIG_FILE='+shlex.quote(apt)+' && '
    return cmd+shlex.quote(orchadmin)+' describe -d -l '+shlex.quote(path)


def _executar_limitado(ssh,cmd,timeout):
    """Drena stdout/stderr juntos; teto e prazo cobrem comando e saída."""
    limite=time.monotonic()+timeout
    channel=ssh.get_transport().open_session(timeout=timeout)
    saida=bytearray();erro=bytearray()
    try:
        channel.settimeout(timeout);channel.exec_command(cmd)
        while True:
            _deadline(limite)
            if channel.recv_ready():saida.extend(channel.recv(8192))
            if channel.recv_stderr_ready():erro.extend(channel.recv_stderr(8192))
            if len(saida)+len(erro)>65536:raise ErroTecnico('Saída excede o limite de validação.')
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():break
            time.sleep(.01)
        status=channel.recv_exit_status()
        if status!=0:raise ErroTecnico('Comando DataStage falhou; ausência não pode ser inferida pelo código de saída.')
        return saida.decode('utf-8',errors='strict')
    except Exception:
        raise ErroTecnico('Falha técnica ao consultar metadados DataStage.') from None
    finally:channel.close()


def _avaliar_entrada(e,catalogo,ssh,extras,timeout):
    path=posixpath.join(va.diretorio(e,catalogo),e['arquivo'])
    sftp=ssh.open_sftp()
    try:
        if e['tipo']=='arquivo':
            result=contar_texto(sftp,path,timeout)
            if result['estado']=='ausente':return va.decidir(e,'ausente')
            fisicas=result['linhas_fisicas'];linhas=max(0,fisicas-int(e['ignorar_cabecalho']))
            return va.decidir(e,'dados' if linhas else 'vazio',linhas,fisicas)
        sftp.get_channel().settimeout(timeout)
        try:info=sftp.stat(path)
        except OSError as exc:
            if exc.errno==errno.ENOENT:return va.decidir(e,'ausente')
            raise ErroTecnico('Não foi possível verificar o descritor do dataset.') from None
        if not stat.S_ISREG(info.st_mode):raise ErroTecnico('Descritor não é arquivo regular.')
        linhas=va.parse_dataset(executar_limitado(ssh,comando_dataset(path,extras),timeout))
        return va.decidir(e,'dados' if linhas else 'vazio',linhas)
    finally:sftp.close()


def avaliar(config,catalogo,ssh,extras):
    resultados=[];interrompido=False
    for e in config['entradas']:
        if interrompido:
            resultados.append(va.decidir(e,'nao_avaliado'));continue
        try:resultados.append(avaliar_entrada(e,catalogo,ssh,extras,config['timeout_segundos']))
        except Exception:
            resultados.append(va.decidir(e,'erro_tecnico'));interrompido=True
    return dict(entradas=resultados,destinos=va.combinar(resultados),falhou=any(r['decisao']=='bloquear' for r in resultados))


def executar_limitado(ssh,cmd,timeout):
    with prazo_ssh(ssh,timeout):return _executar_limitado(ssh,cmd,timeout)


def avaliar_entrada(e,catalogo,ssh,extras,timeout):
    with prazo_ssh(ssh,timeout):return _avaliar_entrada(e,catalogo,ssh,extras,timeout)
