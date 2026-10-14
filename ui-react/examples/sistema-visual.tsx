// Amostra de desenvolvimento: componentes reais, dados sintéticos, nenhuma API.
import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { CheckCircle, AlertTriangle, XCircle, Info } from 'lucide-react'
import '../src/index.css'
import { Button } from '../src/components/ui/Button'
import { Input, Select, Textarea } from '../src/components/ui/Input'
import { Badge } from '../src/components/ui/Badge'
import { Banner } from '../src/components/ui/Banner'
import { Checkbox } from '../src/components/ui/Checkbox'
import { Switch } from '../src/components/ui/Switch'
import { RadioGroup, RadioItem } from '../src/components/ui/RadioGroup'
import { Tabs } from '../src/components/ui/Tabs'
import { Modal } from '../src/components/ui/Modal'
import { Sheet } from '../src/components/ui/Sheet'
import { DropdownMenu } from '../src/components/ui/DropdownMenu'
import { ToastContainer, toast } from '../src/components/ui/Toast'
import { Autocomplete } from '../src/components/ui/Autocomplete'
import { Skeleton } from '../src/components/ui/Skeleton'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../src/components/ui/Table'
import { applyTheme, getTheme, initTheme } from '../src/lib/theme'
import { applyDensity, getDensity, initDensity, type Density } from '../src/lib/density'

initTheme(); initDensity()
const LONG = 'PIPE_VALIDACAO_DO_PROCESSAMENTO_DIARIO_COM_NOME_LONGO_SEM_ESPACOS_PARA_TESTAR_LEITURA_E_ACOES'
const suggestions = async (query: string) => [LONG, 'PIPE_EXEMPLO'].filter(x => x.includes(query.toUpperCase()))
export function Sample() {
  const [theme, setTheme] = useState(getTheme)
  const [density, setDensity] = useState(getDensity)
  const [active, setActive] = useState('montagem')
  const [modal, setModal] = useState(false)
  const [sheet, setSheet] = useState(false)
  const [name, setName] = useState('')
  const [choice, setChoice] = useState('primeiro')
  const [selected, setSelected] = useState(false)
  return <main className="mx-auto max-w-6xl p-4 md:p-6 text-sm">
    <h1 className="ui-title">Sistema visual comum</h1>
    <p className="ui-help mt-2">Amostra de desenvolvimento com conteúdo sintético. Nenhuma execução ou comunicação externa.</p>
    <div className="my-6 flex flex-wrap items-end gap-4">
      <Select label="Tema" value={theme} onChange={e => { const next = e.target.value === 'dark' ? 'dark' : 'light'; applyTheme(next); setTheme(next) }}><option value="light">Claro</option><option value="dark">Escuro</option></Select>
      <Select label="Densidade" value={density} onChange={e => { const next = e.target.value as Density; applyDensity(next); setDensity(next) }}><option value="comfortable">Confortável</option><option value="compact">Compacta</option></Select>
      <Button variant="secondary" onClick={() => { applyDensity('comfortable'); setDensity('comfortable') }}>Restaurar densidade</Button>
    </div>
    <h2 className="ui-section-title mb-3">Ações e estados</h2>
    <div className="flex flex-wrap gap-3 mb-6">
      <Button>Salvar rascunho</Button><Button variant="secondary">Validar</Button><Button variant="ghost">Voltar</Button><Button variant="danger">Excluir</Button><Button disabled>Indisponível</Button><Button loading>Salvando rascunho</Button><Button size="sm">Ação pequena</Button><Button size="lg">Ação grande</Button>
      <DropdownMenu trigger="Mais ações" items={[{ label: 'Mostrar comunicação', onSelect: () => toast.info('Comunicação da amostra, sem envio externo.') }, { label: 'Ação indisponível', disabled: true, onSelect: () => {} }]} />
    </div>
    <div className="mb-6 flex flex-wrap gap-3">
      <Badge value="SUCCESS"><CheckCircle size={14} aria-hidden /> Sucesso</Badge><Badge value="WARNING"><AlertTriangle size={14} aria-hidden /> Warning</Badge><Badge value="FAILED"><XCircle size={14} aria-hidden /> Falha</Badge><Badge value="RUNNING"><Info size={14} aria-hidden /> Em execução</Badge><Badge value="PENDING">Aguardando dependência</Badge><Badge>{LONG}</Badge>
    </div>
    <Tabs tabs={[{ id: 'montagem', label: 'Montagem' }, { id: 'execucao', label: 'Execução', badge: 2, badgeTom: 'neutro' }, { id: 'configuracao', label: 'Configuração', badge: 1 }]} active={active} onChange={setActive} />
    <section className="my-6 grid min-w-0 gap-6 md:grid-cols-2">
      <div className="ui-field-group min-w-0">
        <h2 className="ui-section-title">Configuração</h2>
        <Input label="Nome do pipeline" defaultValue={LONG} ajuda="Nome completo disponível por seleção e teclado." aria-describedby="extra-description" />
        <p id="extra-description" className="ui-help">Descrição adicional fornecida pelo consumidor.</p>
        <Input label="Responsável" placeholder="Informe o responsável" error="Selecione um responsável cadastrado para continuar." ajuda="Ajuda permanece associada junto ao erro." />
        <Select label="Agendamento" defaultValue="demanda"><option value="demanda">Sob demanda</option><option value="mensal">Mensal com descrição longa de calendário</option></Select>
        <Textarea label="Descrição" defaultValue={LONG} rows={3} />
        <Input label="Somente leitura" value="Configuração publicada" readOnly />
        <Input label="Campo indisponível" value="Sem permissão de edição" disabled />
        <Autocomplete label="Localizar pipeline" value={name} onChange={setName} fetchSuggestions={suggestions} />
      </div>
      <div className="ui-field-group min-w-0">
        <h2 className="ui-section-title">Seleção e feedback</h2>
        <Checkbox label={LONG} checked={selected} onChange={e => setSelected(e.target.checked)} />
        <Switch label="Mostrar comunicações" />
        <RadioGroup label="Preferência de exemplo" value={choice} onValueChange={setChoice}><RadioItem value="primeiro" label="Primeira opção" /><RadioItem value="segundo" label="Segunda opção" /></RadioGroup>
        <Banner tom="info" icone={<Info size={16} aria-hidden />}>Modo consulta — a edição está indisponível.</Banner>
        <Banner tom="alerta" icone={<AlertTriangle size={16} aria-hidden />}>Alterações ainda não salvas.</Banner>
        <Banner tom="erro" icone={<XCircle size={16} aria-hidden />} acao={<Button size="sm" variant="secondary">Tentar novamente</Button>}>Não foi possível carregar. O rascunho foi conservado.</Banner>
        <Banner tom="sucesso" icone={<CheckCircle size={16} aria-hidden />}>Rascunho salvo.</Banner>
        <p className="ui-help">Nenhum resultado para o filtro. Limpe o filtro para procurar novamente.</p><Skeleton className="h-10 w-full" />
        <div className="flex flex-wrap gap-3"><Button variant="secondary" onClick={() => setModal(true)}>Abrir confirmação</Button><Button variant="secondary" onClick={() => setSheet(true)}>Abrir propriedades</Button><Button onClick={() => toast.success('Rascunho da amostra salvo. Nenhuma alteração no servidor.')}>Mostrar notificação</Button></div>
      </div>
    </section>
    <h2 className="ui-section-title mb-3">Tabela e nomes longos</h2>
    <Table><TableHeader><TableRow><TableHead>Pipeline</TableHead><TableHead>Estado</TableHead><TableHead>Duração</TableHead></TableRow></TableHeader><TableBody>{[LONG, 'PIPE_EXEMPLO'].map(x => <TableRow key={x}><TableCell>{x}</TableCell><TableCell><Badge value="SUCCESS">Sucesso</Badge></TableCell><TableCell className="tabular-nums">00:01:42</TableCell></TableRow>)}</TableBody></Table>
    <Modal open={modal} onClose={() => setModal(false)} title={'Confirmar exclusão de ' + LONG}><p className="mb-4 break-words">Esta é uma confirmação de demonstração, sem operação no servidor.</p><div className="flex flex-wrap gap-3"><Button variant="secondary" onClick={() => setModal(false)}>Cancelar</Button><Button variant="danger" onClick={() => setModal(false)}>Confirmar exclusão</Button></div></Modal>
    <Sheet open={sheet} onClose={() => setSheet(false)} title={'Propriedades de ' + LONG}><Input label="Nome" defaultValue={LONG} /><Button className="mt-4" onClick={() => setSheet(false)}>Concluir</Button></Sheet>
    <ToastContainer />
  </main>
}
createRoot(document.getElementById('root')!).render(<StrictMode><Sample /></StrictMode>)
