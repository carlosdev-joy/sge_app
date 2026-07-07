import { Maximize2, Plus } from 'lucide-react'
import { Button } from '../ui/Button'
import { Hint } from '../ui/Hint'
import { Input, Select, Textarea } from '../ui/Input'

// ─────────────────────────────────────────────────────────────────────────────
// FONTE ÚNICA de campos por TIPO de etapa (datastage | shell | python | storedproc).
//
// Este componente concentra TODA a regra de "quais campos cada tipo de etapa
// tem" e como validá-los. É reusado pela Lista (JobFormModal em Jobs.tsx) e
// pelo painel lateral do Fluxo (PainelEtapa no FluxoEditor). Qualquer campo
// novo adicionado num tipo aqui vale automaticamente nas duas telas.
//
// NÃO renderiza job_name / ordem / tipo / "depende de" — isso fica no consumidor.
// A decisão (job_type='decisao') também NÃO entra aqui: é tratada no Fluxo.
// ─────────────────────────────────────────────────────────────────────────────

// Tipos de dado de parâmetro de stored procedure — mesma lista do wizard.
export const PARAM_TYPES = ['VARCHAR', 'INT', 'DATE', 'DATETIME', 'DECIMAL', 'BIT'] as const

export interface JobParam {
  id?: string
  param_name: string
  param_type: string
  param_value: string
}

export type JobFieldsType = 'datastage' | 'shell' | 'python' | 'storedproc' | 'http'

// ── Nó Python v2 — modo de execução ─────────────────────────────────────────
// 'arquivo' (script já existente no servidor) e 'codigo' (código embutido,
// publicado no servidor a cada execução) rodam VIA SSH no Servidor SSH do job;
// 'modulo' é o modo LEGADO (job_command importado dentro do worker do Airflow).
export type PythonModo = 'arquivo' | 'codigo' | 'modulo'

// Draft LOCAL do nó python: guarda TODOS os campos de TODOS os modos — trocar
// de modo não perde o que foi digitado nem vaza valor entre campos. O payload
// envia apenas o modo ativo (pythonToApi); 'modulo' vira `python: null`.
export interface PythonDraft {
  modo: PythonModo
  script_path: string
  destino_dir: string
  arquivo: string
  codigo: string
  interpretador: string
}

// Formato da API (campo `python` do nó) — null/ausente = modo legado 'modulo'.
export interface PythonNodeApi {
  modo: 'arquivo' | 'codigo'
  script_path?: string
  destino_dir?: string
  arquivo?: string
  codigo?: string
  interpretador?: string
}

export function defaultPythonDraft(modo: PythonModo): PythonDraft {
  return { modo, script_path: '', destino_dir: '', arquivo: '', codigo: '', interpretador: '' }
}

// GET → draft: null/ausente = legado 'modulo' (pré-seleciona o modo certo).
export function pythonFromApi(p: PythonNodeApi | null | undefined): PythonDraft {
  if (!p || (p.modo !== 'arquivo' && p.modo !== 'codigo')) return defaultPythonDraft('modulo')
  return {
    modo: p.modo,
    script_path: p.script_path ?? '',
    destino_dir: p.destino_dir ?? '',
    arquivo: p.arquivo ?? '',
    codigo: p.codigo ?? '',
    interpretador: p.interpretador ?? '',
  }
}

// Draft → payload: SÓ os campos do modo ativo (o backend normaliza de novo);
// 'modulo' = null. Em nós python a chave `python` deve ir SEMPRE no payload
// (mesmo null) — é a presença da chave que permite voltar ao legado.
export function pythonToApi(d: PythonDraft | undefined): PythonNodeApi | null {
  if (!d || d.modo === 'modulo') return null
  const interp = d.interpretador.trim()
  const opt = interp ? { interpretador: interp } : {}
  if (d.modo === 'arquivo') return { modo: 'arquivo', script_path: d.script_path.trim(), ...opt }
  return { modo: 'codigo', destino_dir: d.destino_dir.trim(), arquivo: d.arquivo.trim(), codigo: d.codigo, ...opt }
}

export interface JobTypeFieldsValue {
  job_type: JobFieldsType
  job_command: string
  ssh_conn_id: string
  verbose_log: boolean
  mssql_conn_id: string
  mssql_database: string
  params: JobParam[]
  // Nó python v2 — draft local (todos os modos). Ausente = legado 'modulo'.
  python?: PythonDraft
}

export interface ConnOpt { conn_id: string; host?: string }

export interface JobTypeFieldsProps {
  value: JobTypeFieldsValue
  onChange: (patch: Partial<JobTypeFieldsValue>) => void
  sshConns: ConnOpt[]
  mssqlConns: ConnOpt[]
  dbServer: string | null
  dbDatabases: string[]
  compact?: boolean   // layout denso p/ o painel lateral do Fluxo (fontes/spacing menores)
  // Maximiza o dock (modo focado) — usado pelo editor de código do nó python.
  onMaximizar?: () => void
}

// ── Label / placeholder do campo de comando, por tipo ────────────────────────

export function jobCommandLabel(t: JobFieldsType): string {
  return t === 'datastage' ? 'Nome do job DataStage'
    : t === 'storedproc' ? 'Procedure (ex: dbo.sp_nome)'
    : t === 'python' ? 'Módulo / Path'
    : t === 'http' ? 'URL (http/https)'
    : 'Comando / Path'
}

export function jobCommandPlaceholder(t: JobFieldsType): string {
  return t === 'datastage' ? 'ex: BiCvp.job_name'
    : t === 'shell' ? 'ex: /opt/scripts/run.sh'
    : t === 'python' ? 'ex: scripts.modulo.run'
    : t === 'http' ? 'ex: https://servidor/api/disparo'
    : 'ex: dbo.sp_procedure'
}

// URL aceita para etapas http — espelha o allowlist do backend (_valid_http_url):
// http(s)://, sem espaço/aspas (o comando vira argumento do HttpCallOperator).
export const HTTP_URL_RE = /^https?:\/\/[^\s'"]+$/i

// Réguas do nó python v2 — espelham o backend (_PY_*_RE em api/routers/jobs.py):
// caminhos absolutos sem espaço/aspas (viram argumento de comando via SSH).
export const PY_SCRIPT_PATH_RE = /^\/[^\s'"]+\.py$/
export const PY_DIR_RE = /^\/[^\s'"]+$/
export const PY_ARQUIVO_RE = /^[A-Za-z0-9._-]+\.py$/
export const PY_INTERP_RE = /^[A-Za-z0-9._/-]+$/
// Módulo importável (modo legado): segmentos com pontos, sem path/extensão.
export const PY_MODULO_RE = /^[A-Za-z_]\w*(\.\w+)*$/

// ── Validação unificada (espelha as regras do wizard) ────────────────────────
// Retorna a lista de mensagens de erro (vazia = válido). Não valida nome/ordem,
// que pertencem ao consumidor.
export function jobTypeFieldsErrors(v: JobTypeFieldsValue): string[] {
  const errs: string[] = []
  if (v.job_type === 'shell' && !v.ssh_conn_id) {
    errs.push('Servidor SSH é obrigatório para etapas shell')
  }
  if (v.job_type === 'http' && !HTTP_URL_RE.test((v.job_command ?? '').trim())) {
    errs.push('Etapa http exige uma URL http(s) válida no campo URL')
  }
  if (v.job_type === 'python') {
    // Nó python v2 — mesma régua do backend (_validate_python_node). Draft
    // ausente = legado 'modulo' (nó antigo sem python_json).
    const py = v.python ?? defaultPythonDraft('modulo')
    if (py.modo === 'modulo') {
      const cmd = (v.job_command ?? '').trim()
      if (!cmd) errs.push('Módulo Python é obrigatório no modo legado (ex.: scripts.modulo.run)')
      else if (!PY_MODULO_RE.test(cmd)) {
        errs.push('Módulo Python inválido — caminho importável, com pontos (ex.: scripts.modulo.run)')
      }
    } else {
      if (!v.ssh_conn_id) {
        errs.push('Servidor SSH é obrigatório para o nó Python em modo '
          + (py.modo === 'arquivo' ? "'Script no servidor'" : "'Código embutido'"))
      }
      if (py.modo === 'arquivo') {
        if (!PY_SCRIPT_PATH_RE.test(py.script_path.trim())) {
          errs.push('Caminho do script inválido — absoluto, terminando em .py, sem espaço/aspas (ex.: /opt/scripts/carga.py)')
        }
      } else {
        if (!PY_DIR_RE.test(py.destino_dir.trim())) {
          errs.push('Diretório de destino inválido — absoluto, sem espaço/aspas (ex.: /opt/scripts)')
        }
        if (!PY_ARQUIVO_RE.test(py.arquivo.trim())) {
          errs.push('Nome do arquivo inválido — letras/números/._- terminando em .py')
        }
        if (!py.codigo.trim()) errs.push('Código Python vazio — cole o script no painel')
      }
      const interp = py.interpretador.trim()
      if (interp && !PY_INTERP_RE.test(interp)) {
        errs.push('Interpretador inválido (ex.: python3, /usr/bin/python3.11)')
      }
    }
  }
  if (v.job_type === 'storedproc') {
    if (!v.mssql_conn_id) errs.push('Conexão MSSQL é obrigatória para etapas storedproc')
    const vistos = new Set<string>()
    v.params.forEach((p, i) => {
      const nome = p.param_name.trim()
      if (!nome) errs.push(`Parâmetro #${i + 1} sem nome definido`)
      if (!p.param_type || !(PARAM_TYPES as readonly string[]).includes(p.param_type)) {
        errs.push(`Parâmetro #${i + 1} sem tipo de dado válido`)
      }
      const key = nome.replace(/^@/, '').toLowerCase()
      if (nome && vistos.has(key)) errs.push(`Parâmetro "${nome}" duplicado`)
      vistos.add(key)
    })
  }
  return errs
}

// ── Sub-editor de parâmetros de stored procedure ─────────────────────────────
// Reusável; controlado pelo valor `params` e por `onChange` do pai.

export interface JobParamsEditorProps {
  params: JobParam[]
  onChange: (params: JobParam[]) => void
  compact?: boolean
}

function genParamId() {
  return `p_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
}

export function JobParamsEditor({ params, onChange, compact }: JobParamsEditorProps) {
  const txt = compact ? 'text-xs' : 'text-sm'
  const inputCls = `bg-panel border text-ink rounded-md ${compact ? 'px-2 py-1 text-xs' : 'px-3 py-1.5 text-sm'} font-mono placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500`

  function addParam() {
    onChange([...params, { id: genParamId(), param_name: '', param_type: 'VARCHAR', param_value: '' }])
  }
  function removeParam(idx: number) {
    onChange(params.filter((_, i) => i !== idx))
  }
  function updateParam(idx: number, patch: Partial<JobParam>) {
    onChange(params.map((p, i) => i === idx ? { ...p, ...patch } : p))
  }

  return (
    <div className="flex flex-col gap-1.5">
      {params.map((p, idx) => (
        <div key={p.id ?? idx} className={`grid ${compact ? 'grid-cols-[1fr_90px_1fr_24px]' : 'grid-cols-[1fr_110px_1fr_28px]'} gap-1.5 items-start`}>
          <input
            type="text"
            value={p.param_name}
            onChange={e => updateParam(idx, { param_name: e.target.value })}
            placeholder="@nome_param"
            className={`${inputCls} ${!p.param_name.trim() ? 'border-red-500/60' : 'border-edge'}`}
          />
          <select
            value={p.param_type}
            onChange={e => updateParam(idx, { param_type: e.target.value })}
            className={`bg-panel border border-edge text-ink rounded-md ${compact ? 'px-1.5 py-1 text-xs' : 'px-2 py-1.5 text-sm'} focus:outline-none focus:ring-1 focus:ring-blue-500`}
          >
            {PARAM_TYPES.map(t => <option key={t}>{t}</option>)}
          </select>
          <input
            type="text"
            value={p.param_value}
            onChange={e => updateParam(idx, { param_value: e.target.value })}
            placeholder="valor fixo"
            className={`${inputCls} border-edge`}
          />
          <button
            type="button"
            onClick={() => removeParam(idx)}
            className={`text-dim hover:text-red-500 ${txt} justify-self-center pt-1`}
            title="Remover parâmetro"
          >✕</button>
        </div>
      ))}
      <Button size="sm" variant="ghost" onClick={addParam} className="self-start">
        <Plus size={compact ? 10 : 12} /> Adicionar parâmetro
      </Button>
    </div>
  )
}

// ── Componente principal ─────────────────────────────────────────────────────

export function JobTypeFields({
  value, onChange, sshConns, mssqlConns, dbServer, dbDatabases, compact, onMaximizar,
}: JobTypeFieldsProps) {
  const { job_type } = value

  // Densidade: o painel do Fluxo é estreito → fontes/paddings menores.
  const labelCls = `${compact ? 'text-[10px]' : 'text-xs'} text-dim font-medium`
  const fieldCls = `bg-panel border border-edge text-ink rounded-md ${compact ? 'px-2 py-1 text-xs' : 'px-3 py-1.5 text-sm'} placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500`
  const noteCls = `${compact ? 'text-[10px]' : 'text-[11px]'} text-dim/70`
  const gap = compact ? 'gap-2' : 'gap-4'

  return (
    <div className={`flex flex-col ${gap}`}>
      {/* python (v2) → seção própria: Modo de execução + campos por modo
          (substitui o campo genérico de comando; o módulo legado mora dentro). */}
      {job_type === 'python' ? (
        <PythonExecFields
          value={value}
          onChange={onChange}
          sshConns={sshConns}
          onMaximizar={onMaximizar}
          noteCls={noteCls}
        />
      ) : (
      /* Comando / nome / procedure — label e placeholder por tipo */
      <div className="flex flex-col gap-1">
        <label className={`${labelCls} flex items-center gap-1`}>
          {jobCommandLabel(job_type)}
          {job_type === 'http' && (
            <Hint texto={'Aceita apenas http:// ou https://, sem espaços nem aspas.\nA URL é chamada no runtime pelo HttpCallOperator (allowlist do backend).'} />
          )}
        </label>
        <input
          type="text"
          value={value.job_command}
          onChange={e => onChange({ job_command: e.target.value })}
          placeholder={jobCommandPlaceholder(job_type)}
          className={`${fieldCls} font-mono`}
        />
        {job_type === 'storedproc' && (
          <p className={noteCls}>
            Apenas o <strong>nome</strong> da procedure (ex.: <code>dbo.sp_nome</code>). O sistema
            adiciona o <code>EXEC</code> e os parâmetros automaticamente — <strong>não</strong> escreva
            “EXEC”. Sem parâmetros cadastrados, a proc é chamada sem nenhum parâmetro.
          </p>
        )}
      </div>
      )}

      {/* shell → conexão SSH (obrigatória) */}
      {job_type === 'shell' && (
        <div className="flex flex-col gap-1">
          <label className={`${labelCls} flex items-center gap-1`}>
            Servidor SSH (conexão Airflow) *
            <Hint texto={'Obrigatório para etapas shell: o comando/script roda via SSH neste servidor.\nAs conexões SSH são cadastradas no Airflow.'} />
          </label>
          <select
            value={value.ssh_conn_id}
            onChange={e => onChange({ ssh_conn_id: e.target.value })}
            className={fieldCls}
          >
            <option value="">Selecione a conexão SSH...</option>
            {sshConns.map(c => (
              <option key={c.conn_id} value={c.conn_id}>{c.conn_id}{c.host ? ` (${c.host})` : ''}</option>
            ))}
          </select>
        </div>
      )}

      {/* datastage → log detalhado (caixa âmbar) */}
      {job_type === 'datastage' && (
        <div className={`bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800/40 rounded-lg ${compact ? 'px-2.5 py-2' : 'px-3 py-3'}`}>
          <label className="flex items-start gap-2.5 cursor-pointer">
            <input
              type="checkbox"
              checked={value.verbose_log}
              onChange={e => onChange({ verbose_log: e.target.checked })}
              className="mt-0.5 accent-amber-400"
            />
            <div>
              <span className={`${compact ? 'text-xs' : 'text-sm'} text-ink font-medium`}>Log detalhado durante execução</span>
              <p className={`${compact ? 'text-[10px]' : 'text-xs'} text-dim mt-0.5`}>
                Registra o progresso dos jobs filhos a cada 5 min (jobs SEQUENCE).
                Útil para diagnosticar lentidão — desative após a investigação.
              </p>
            </div>
          </label>
        </div>
      )}

      {/* storedproc → conexão MSSQL (obrigatória) */}
      {job_type === 'storedproc' && (
        <div className="flex flex-col gap-1">
          <label className={`${labelCls} flex items-center gap-1`}>
            Conexão MSSQL *
            <Hint texto={'Obrigatória para storedproc: a proc roda neste servidor, com a credencial da conexão.'} />
          </label>
          <select
            value={value.mssql_conn_id}
            onChange={e => onChange({ mssql_conn_id: e.target.value })}
            className={fieldCls}
          >
            <option value="">Selecione a conexão...</option>
            {mssqlConns.map(c => (
              <option key={c.conn_id} value={c.conn_id}>{c.conn_id}{c.host ? ` (${c.host})` : ''}</option>
            ))}
          </select>
        </div>
      )}

      {/* storedproc → servidor / banco-alvo (opcional, mesmo servidor) */}
      {job_type === 'storedproc' && (
        <div className="flex flex-col gap-1">
          <label className={`${labelCls} flex items-center gap-1`}>
            Servidor / Banco {dbServer && <span className="text-dim/60 font-mono normal-case">({dbServer})</span>}
            <Hint texto={'Banco-alvo da proc, no MESMO servidor da conexão (vira EXEC [banco].schema.proc).\nVazio = banco padrão da conexão.'} />
          </label>
          <select
            value={value.mssql_database}
            onChange={e => onChange({ mssql_database: e.target.value })}
            className={fieldCls}
          >
            <option value="">Banco padrão da conexão</option>
            {dbDatabases.map(d => <option key={d} value={d}>{d}</option>)}
            {value.mssql_database && !dbDatabases.includes(value.mssql_database) && (
              <option value={value.mssql_database}>{value.mssql_database}</option>
            )}
          </select>
        </div>
      )}

      {/* storedproc → parâmetros (lista editável nome/tipo/valor) */}
      {job_type === 'storedproc' && (
        <div className="flex flex-col gap-1.5">
          <label className={`${labelCls} flex items-center gap-1.5`}>
            Parâmetros (opcional)
            <Hint texto={'Nome com ou sem @ (o @ é opcional) — sem nomes duplicados.\nTipos aceitos: VARCHAR, INT, DATE, DATETIME, DECIMAL e BIT.\nO valor fixo é passado à proc em cada execução.'} />
            {value.params.length > 0 && (
              <span className="bg-blue-100 text-blue-700 border border-blue-300 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-800/40 rounded-full px-1.5 py-0 text-[9px] font-bold">
                {value.params.length}
              </span>
            )}
          </label>
          <JobParamsEditor
            params={value.params}
            onChange={params => onChange({ params })}
            compact={compact}
          />
        </div>
      )}
    </div>
  )
}

// ── Nó python — Modo de execução + campos por modo (v2) ─────────────────────
// Um único nó python com 3 modos. Os drafts são SEGREGADOS por modo: o objeto
// `python` guarda todos os campos e a troca de modo não apaga nem vaza nada
// entre campos; o payload envia só o modo ativo (pythonToApi). O módulo legado
// continua sendo o job_command (fora do objeto python — python: null no save).
function PythonExecFields({ value, onChange, sshConns, onMaximizar, noteCls }: {
  value: JobTypeFieldsValue
  onChange: (patch: Partial<JobTypeFieldsValue>) => void
  sshConns: ConnOpt[]
  onMaximizar?: () => void
  noteCls: string
}) {
  const py = value.python ?? defaultPythonDraft('modulo')
  const patchPy = (p: Partial<PythonDraft>) => onChange({ python: { ...py, ...p } })

  // Servidor SSH do job — o MESMO campo do modo shell (ssh_conn_id do job);
  // obrigatório nos modos novos (é nele que o script roda).
  const sshSelect = (
    <Select
      label="Servidor SSH (conexão Airflow) *"
      hint={'Obrigatório nos modos "Script no servidor" e "Código embutido":\no script roda via SSH neste servidor. As conexões são cadastradas no Airflow.'}
      value={value.ssh_conn_id}
      onChange={e => onChange({ ssh_conn_id: e.target.value })}
    >
      <option value="">Selecione a conexão SSH...</option>
      {sshConns.map(c => (
        <option key={c.conn_id} value={c.conn_id}>{c.conn_id}{c.host ? ` (${c.host})` : ''}</option>
      ))}
      {/* Mantém a conexão salva visível mesmo se não estiver mais na lista */}
      {value.ssh_conn_id && !sshConns.some(c => c.conn_id === value.ssh_conn_id) && (
        <option value={value.ssh_conn_id}>{value.ssh_conn_id} (fora da lista)</option>
      )}
    </Select>
  )

  const interpInput = (
    <Input
      label="Interpretador (opcional)"
      hint={'Binário Python usado no servidor (vazio = python3).\nAceita caminho absoluto (ex.: /usr/bin/python3.11).'}
      value={py.interpretador}
      onChange={e => patchPy({ interpretador: e.target.value })}
      placeholder="python3"
      className="font-mono"
    />
  )

  return (
    <>
      {/* Modo de execução — PRIMEIRO campo da seção do tipo (full-width). */}
      <div className="flex flex-col gap-1">
        <Select
          label="Modo de execução"
          value={py.modo}
          onChange={e => patchPy({ modo: e.target.value as PythonModo })}
        >
          <option value="arquivo">Script no servidor</option>
          <option value="codigo">Código embutido</option>
          <option value="modulo">Módulo no worker (legado)</option>
        </Select>
        <p className={noteCls}>
          {py.modo === 'modulo'
            ? 'Roda dentro do worker do Airflow — não usa SSH.'
            : 'Roda via SSH no servidor selecionado.'}
        </p>
      </div>

      {/* modulo (legado) → módulo importável no worker (= job_command) */}
      {py.modo === 'modulo' && (
        <>
          <Input
            label="Módulo Python *"
            hint={'Módulo importável no ambiente do worker do Airflow (ex.: scripts.carga.run).\nNão roda via SSH.'}
            value={value.job_command}
            onChange={e => onChange({ job_command: e.target.value })}
            placeholder="scripts.modulo.run"
            className="font-mono"
          />
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800/40 dark:bg-amber-900/20 dark:text-amber-300">
            Modo mantido por compatibilidade. Para scripts novos, prefira “Script no servidor”.
          </p>
        </>
      )}

      {/* arquivo → col1: Servidor SSH · col2: caminho do script + interpretador */}
      {py.modo === 'arquivo' && (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex min-w-0 flex-col gap-3">{sshSelect}</div>
          <div className="flex min-w-0 flex-col gap-3">
            <Input
              label="Caminho do script (.py) *"
              hint={'Caminho absoluto do script já existente no servidor (ex.: /opt/scripts/carga.py).\nExecutado via SSH; exit ≠ 0 falha a etapa.'}
              value={py.script_path}
              onChange={e => patchPy({ script_path: e.target.value })}
              placeholder="/opt/scripts/carga.py"
              className="font-mono"
            />
            {interpInput}
          </div>
        </div>
      )}

      {/* codigo → col1: Servidor SSH + destino · col2: arquivo + interpretador;
          o código é SEMPRE full-width, abaixo do grid. */}
      {py.modo === 'codigo' && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex min-w-0 flex-col gap-3">
              {sshSelect}
              <Input
                label="Diretório de destino *"
                hint={'Diretório no servidor onde o arquivo será publicado (criado se não existir).\nO arquivo é sobrescrito a cada execução.'}
                value={py.destino_dir}
                onChange={e => patchPy({ destino_dir: e.target.value })}
                placeholder="/opt/scripts"
                className="font-mono"
              />
            </div>
            <div className="flex min-w-0 flex-col gap-3">
              <Input
                label="Nome do arquivo (.py) *"
                hint={'Nome do arquivo publicado no diretório de destino.\nLetras/números/._- terminando em .py (ex.: carga.py).'}
                value={py.arquivo}
                onChange={e => patchPy({ arquivo: e.target.value })}
                placeholder="carga.py"
                className="font-mono"
              />
              {interpInput}
            </div>
          </div>
          <div className="relative flex flex-col gap-1">
            {onMaximizar && (
              <button
                type="button"
                onClick={onMaximizar}
                title="Ampliar o painel (modo focado) para editar o código"
                className="absolute right-0 top-0 z-10 flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold text-dim hover:bg-edge/40 hover:text-ink"
              >
                <Maximize2 size={11} /> ampliar
              </button>
            )}
            <Textarea
              label="Código Python *"
              hint={'Salvo como <diretório>/<arquivo> e executado via SSH.\nSem versionamento — para scripts grandes prefira Git + "Script no servidor".'}
              value={py.codigo}
              onChange={e => patchPy({ codigo: e.target.value })}
              rows={12}
              placeholder={'# cole aqui o script Python\nimport sys\nprint("carga ok")'}
              className="font-mono text-xs"
            />
          </div>
        </>
      )}
    </>
  )
}
