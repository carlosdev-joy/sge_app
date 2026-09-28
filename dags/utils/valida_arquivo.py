"""Contrato puro espelhado no worker: nenhuma leitura remota, segredo ou efeito."""
import json
import posixpath
import re
import uuid

TIPOS_ALVO = {'datastage', 'shell', 'python', 'storedproc', 'http', 'decisao', 'notificacao', 'sql', 'aguarde', 'email'}
LIMITE_ENTRADAS = 100
MAX_CONTAGEM = 9223372036854775807


def texto(value, nome, limite):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{nome}: informe um texto não vazio.')
    value = value.strip()
    if len(value.encode('utf-16-le')) // 2 > limite or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f'{nome}: tamanho ou caracteres inválidos.')
    return value


def caminho(value):
    value = texto(value, 'Diretório', 2000)
    if not value.startswith('/') or '..' in value.split('/'):
        raise ValueError('Diretório deve ser absoluto e não conter .. .')
    return posixpath.normpath(value)


def diretorio(entrada, catalogo):
    # Literal explícito tem precedência, mesmo se houver referência preenchida.
    if entrada.get('diretorio_literal'):
        return caminho(entrada['diretorio_literal'])
    p = next((p for p in catalogo if p['param_name'] == entrada.get('param_name')), None)
    if not p or p.get('param_type') not in ('String', 'Pathname') or p.get('param_source') != 'fixo':
        raise ValueError('Diretório exige referência String/Pathname fixa e sem segredo.')
    return caminho(p.get('param_value'))


def normalizar(raw, catalogo):
    if not isinstance(raw, dict):
        raise ValueError('Configuração do validador deve ser um objeto.')
    ssh = texto(raw.get('ssh_conn_id'), 'Conexão SSH', 100)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', ssh):
        raise ValueError('Identificador de conexão SSH inválido.')
    timeout = raw.get('timeout_segundos', 60)
    if type(timeout) is not int or not 1 <= timeout <= 600:
        raise ValueError('Timeout deve ser inteiro entre 1 e 600 segundos.')
    entradas = raw.get('entradas')
    if not isinstance(entradas, list) or not 1 <= len(entradas) <= LIMITE_ENTRADAS:
        raise ValueError('Informe entre 1 e 100 entradas.')
    out=[]; ids=set()
    for index, item in enumerate(entradas):
        if not isinstance(item, dict):
            raise ValueError(f'Entrada {index+1}: objeto inválido.')
        try:
            eid=str(uuid.UUID(str(item.get('entrada_id'))))
        except (ValueError, AttributeError):
            raise ValueError(f'Entrada {index+1}: identificador UUID obrigatório.') from None
        if eid in ids:
            raise ValueError('Identificador de entrada repetido.')
        ids.add(eid)
        tipo=item.get('tipo')
        if tipo not in ('arquivo','dataset'):
            raise ValueError('Tipo deve ser arquivo ou dataset.')
        arquivo=texto(item.get('arquivo'),'Nome do arquivo',300)
        if arquivo in ('.','..') or '/' in arquivo or '\\' in arquivo or len(arquivo.encode())>255:
            raise ValueError('Informe apenas o nome real do arquivo, com extensão e caixa originais.')
        header=item.get('ignorar_cabecalho',False)
        if type(header) is not bool or (header and tipo=='dataset'):
            raise ValueError('Ignorar cabeçalho só é permitido para arquivo de texto.')
        ausente=item.get('se_nao_existe','falhar'); vazio=item.get('se_zero_linhas','falhar')
        if ausente not in ('pular','falhar') or vazio not in ('pular','falhar','executar'):
            raise ValueError('Política de ausência/vazio inválida; erro técnico sempre falha.')
        literal=item.get('diretorio_literal') or ''
        if not isinstance(literal,str):raise ValueError('Diretório literal inválido.')
        pname=item.get('param_name') or None
        if pname is not None:pname=texto(pname,'Parâmetro',128)
        entry=dict(entrada_id=eid,ordem=index,tipo=tipo,arquivo=arquivo,
                   diretorio_literal=caminho(literal) if literal.strip() else '',param_name=pname,
                   alvo=texto(item.get('alvo'),'Destino',200),se_nao_existe=ausente,se_zero_linhas=vazio,
                   ignorar_cabecalho=header)
        diretorio(entry,catalogo)
        out.append(entry)
    return dict(ssh_conn_id=ssh,timeout_segundos=timeout,entradas=out)


def grafo(jobs):
    if not isinstance(jobs,list) or len(jobs)>500:
        raise ValueError('Grafo inválido ou acima de 500 nós.')
    por_nome={}; filhos={}; pais={}
    for j in jobs:
        if not isinstance(j,dict):raise ValueError('Nó inválido.')
        name=texto(j.get('job_name'),'Nome do nó',200)
        if name in por_nome:raise ValueError('Nome de nó repetido.')
        if not isinstance(j.get('job_type'), str):raise ValueError('Tipo de nó inválido.')
        por_nome[name]=j;filhos[name]=set();pais[name]=set()
    for name,j in por_nome.items():
        deps=j.get('depends_on_jobs') or []
        if isinstance(deps,str):deps=[d.strip() for d in deps.split(',') if d.strip()]
        if not isinstance(deps,list) or any(not isinstance(d,str) for d in deps):raise ValueError('Dependências inválidas.')
        for d in deps:
            if d not in por_nome or d==name:raise ValueError('Dependência inexistente ou do próprio nó.')
            filhos[d].add(name);pais[name].add(d)
    for name,j in por_nome.items():
        if j['job_type'] != 'decisao':continue
        cond=j.get('condition')
        if cond is None:
            raw_cond=j.get('condition_json') or '{}'
            if not isinstance(raw_cond,str):raise ValueError('JSON da condição inválido.')
            cond=json.loads(raw_cond)
        if not isinstance(cond,dict):raise ValueError('Condição de decisão inválida.')
        grupos=[cond.get(k) or [] for k in ('ramo_verdadeiro','ramo_falso','ramo_senao')]
        casos=cond.get('casos') or []
        if not isinstance(casos,list):raise ValueError('Casos da decisão inválidos.')
        for caso in casos:
            if not isinstance(caso,dict):raise ValueError('Caso da decisão inválido.')
            grupos.append(caso.get('ramo') or [])
        for grupo in grupos:
            if not isinstance(grupo,list):raise ValueError('Ramos da decisão devem ser listas.')
            for destino in grupo:
                if not isinstance(destino,str) or destino not in por_nome or destino==name:
                    raise ValueError('Destino da decisão inválido.')
                filhos[name].add(destino);pais[destino].add(name)
    pendentes={n:set(p) for n,p in pais.items()}; fila=[n for n,p in pendentes.items() if not p]; visitados=set()
    while fila:
        n=fila.pop();visitados.add(n)
        for f in filhos[n]:
            pendentes[f].discard(n)
            if not pendentes[f]:fila.append(f)
    if len(visitados)!=len(por_nome):raise ValueError('O grafo contém um ciclo.')
    return por_nome,filhos,pais


def descendentes(filhos, no):
    seen=set(); fila=list(filhos[no])
    while fila:
        n=fila.pop()
        if n not in seen:seen.add(n);fila.extend(filhos[n])
    return seen


def impacto(config, jobs, no, catalogo):
    nomes,filhos,pais=grafo(jobs)
    if no not in nomes:raise ValueError('Validador não está no grafo informado.')
    depois=descendentes(filhos,no);out=[]
    for e in config['entradas']:
        alvo=e['alvo']
        if alvo not in depois or nomes[alvo].get('job_type') not in TIPOS_ALVO:
            raise ValueError('Cada destino deve estar depois do validador e ter tipo suportado.')
        transitivos=descendentes(filhos,alvo)
        convergencias=sorted(n for n in transitivos | {alvo} if len(pais[n])>1)
        path=posixpath.join(diretorio(e,catalogo),e['arquivo'])
        out.append(dict(entrada_id=e['entrada_id'],caminho=path,
                        origem='valor direto' if e['diretorio_literal'] else e['param_name'],
                        alvo=alvo,dependentes_transitivos=sorted(transitivos),convergencias=convergencias,
                        cenarios={estado:decidir(e,estado,1 if estado=='dados' else 0 if estado=='vazio' else None)['decisao']
                                  for estado in ('ausente','vazio','dados','erro_tecnico')}))
    return dict(entradas=out,combinacao='Todas as entradas de um destino devem liberar; pular impede a execução e qualquer falha bloqueia todos os destinos deste validador.',
                contagem='Arquivos de texto: linhas físicas; não interpreta registros CSV multilinha.',
                aviso='Prévia de configuração; não lê o servidor nem confirma existência ou execução dos destinos.')


def decidir(entrada, estado, linhas=None, linhas_fisicas=None):
    if estado not in ('ausente','vazio','dados','erro_tecnico','nao_avaliado'):
        raise ValueError('Estado desconhecido.')
    if estado in ('vazio','dados'):
        if type(linhas) is not int or not 0<=linhas<=MAX_CONTAGEM or (estado=='vazio') != (linhas==0):
            raise ValueError('Contagem incompatível com o estado.')
    else:linhas=None;linhas_fisicas=None
    politica=entrada['se_nao_existe'] if estado=='ausente' else entrada['se_zero_linhas'] if estado=='vazio' else None
    decisao='bloquear' if estado in ('erro_tecnico','nao_avaliado') or politica=='falhar' else 'pular' if politica=='pular' else 'liberar'
    return dict(entrada_id=entrada['entrada_id'],alvo=entrada['alvo'],estado=estado,linhas=linhas,
                linhas_fisicas=linhas_fisicas,decisao=decisao,motivo={'ausente':'Arquivo ausente','vazio':'Nenhuma linha considerada','dados':'Dados presentes','erro_tecnico':'Falha técnica ao verificar arquivo','nao_avaliado':'Não avaliado após interrupção'}[estado])


def combinar(resultados):
    bloqueado=any(r['decisao']=='bloquear' for r in resultados)
    saida={}
    for r in resultados:
        alvo=r['alvo']
        saida[alvo]='bloquear' if bloqueado else 'pular' if r['decisao']=='pular' or saida.get(alvo)=='pular' else 'liberar'
    return saida


def parse_dataset(saida):
    """Contrato estrito de resumo orchadmin; formato desconhecido NUNCA vira zero.

    Suporta dois formatos conhecidos do DataStage 11.7:
      - Bloco "Totals:" seguido de "  records : N" (formato real da versão instalada)
      - Linha única "Total records: N" ou "Total rows: N" (formato alternativo)
    Partições individuais, bytes, datas ou qualquer outro inteiro são ignorados.
    """
    if not isinstance(saida,str) or len(saida.encode())>65536:
        raise ValueError('Saída do dataset inválida ou excessiva.')
    totais=[]
    em_totals=False
    for linha in saida.splitlines():
        # Formato 1: bloco "Totals:" + "  records : N"
        if re.fullmatch(r'\s*Totals\s*:\s*',linha,re.I):
            em_totals=True;continue
        if em_totals:
            m=re.fullmatch(r'\s*records\s*:\s*([0-9]+)\s*',linha,re.I)
            if m:totais.append(int(m.group(1)));em_totals=False;continue
            # Qualquer linha não em branco encerra o bloco sem captura
            if linha.strip():em_totals=False
        # Formato 2: "Total records: N" ou "Total rows: N" em linha única
        m=re.fullmatch(r'\s*Total (?:records|rows)\s*[:=]\s*([0-9]+)\s*',linha,re.I)
        if m:totais.append(int(m.group(1)))
    if len(totais)!=1 or totais[0]>MAX_CONTAGEM:
        raise ValueError('Formato de contagem DataStage não reconhecido; certifique o parser com a versão instalada.')
    return totais[0]


def estrutura_validadores(configs):
    return sorted([[no,c['ssh_conn_id'],sorted([[e['entrada_id'],e['alvo']] for e in c['entradas']])]
                   for no,c in configs.items()],key=lambda x:x[0])
