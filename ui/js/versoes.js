/* ══ CHANGELOG / VERSÕES ══════════════════════════════════════════ */
const VERSAO_QUERY_DAG    = 'etl_versao_query';
const VERSAO_REGISTER_DAG = 'etl_versao_register';

function _renderMarkdown(text) {
  if (!text) return '';
  let html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // code blocks ```...```
    .replace(/```([\s\S]*?)```/g, '<pre style="background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:.65rem .9rem;overflow-x:auto;font-size:12px;line-height:1.6">$1</pre>')
    // inline code
    .replace(/`([^`]+)`/g, '<code style="background:var(--bg);padding:1px 5px;border-radius:4px;font-size:12px">$1</code>')
    // headers
    .replace(/^### (.+)$/gm, '<h4 style="margin:.9rem 0 .3rem;font-size:13px;font-weight:700">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 style="margin:1rem 0 .4rem;font-size:14px;font-weight:700">$1</h3>')
    .replace(/^# (.+)$/gm, '<h2 style="margin:1rem 0 .4rem;font-size:16px;font-weight:700">$1</h2>')
    // bold, italic
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // bullet lists
    .replace(/^[-*] (.+)$/gm, '<li style="margin:.2rem 0 .2rem 1rem">$1</li>')
    // paragraphs (double newlines)
    .replace(/\n\n/g, '</p><p style="margin:.5rem 0">')
    // single newlines
    .replace(/\n/g, '<br>');
  return '<div style="line-height:1.65;font-size:13px"><p style="margin:.5rem 0">' + html + '</p></div>';
}

async function openChangelog() {
  $('modal-changelog').classList.add('open');
  $('changelog-loading').style.display = '';
  $('changelog-list').style.display = 'none';
  $('changelog-list').innerHTML = '';

  if (!authHeader) {
    $('changelog-loading').textContent = 'Faça login para ver o histórico.';
    return;
  }

  try {
    const r = await fetch(ORQUESTRA_API + '/versao');
    if (!r.ok) { $('changelog-loading').textContent = 'Erro ao carregar: ' + r.status; return; }
    const payload = await r.json();
    const versions = (payload && payload.data) ? payload.data : [];

    $('changelog-loading').style.display = 'none';
    $('changelog-list').style.display = '';

    if (!versions.length) {
      $('changelog-list').innerHTML = '<div style="text-align:center;padding:2rem;color:var(--muted);font-size:13px">Nenhuma versão registrada ainda.</div>';
      return;
    }

    $('changelog-list').innerHTML = versions.map((v, i) => {
      const isFirst = i === 0;
      return `<div style="border:1px solid var(--border);border-radius:12px;margin-bottom:.75rem;overflow:hidden">
        <div onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'':'none';this.querySelector('.cl-arrow').textContent=this.nextElementSibling.style.display===''?'▲':'▼'"
          style="display:flex;align-items:center;gap:.75rem;padding:.75rem 1rem;cursor:pointer;background:var(--bg);user-select:none">
          <span style="background:var(--cvp-blue);color:#fff;font-size:11px;font-weight:700;padding:2px 9px;border-radius:999px;flex-shrink:0">v${v.versao || '?'}</span>
          <div style="flex:1">
            <div style="font-size:13px;font-weight:600">${v.titulo || '—'}</div>
            <div style="font-size:11px;color:var(--muted)">${(v.criado_em || '').substring(0,10)} · ${v.criado_por || 'admin'}</div>
          </div>
          <span class="cl-arrow" style="color:var(--muted);font-size:12px">${isFirst ? '▲' : '▼'}</span>
        </div>
        <div style="padding:.85rem 1.1rem;border-top:1px solid var(--border);display:${isFirst ? '' : 'none'}">
          ${v.descricao_md ? _renderMarkdown(v.descricao_md) : '<span style="color:var(--muted);font-size:12px">Sem descrição.</span>'}
        </div>
      </div>`;
    }).join('');
  } catch(e) {
    $('changelog-loading').textContent = 'Erro: ' + (e && e.message ? e.message : e);
  }
}

function closeChangelog() {
  $('modal-changelog').classList.remove('open');
}

/* ── Admin: Versões CRUD ──────────────────────────────────────── */
async function admLoadVersoes() {
  if (!authHeader) return;
  const st  = $('adm-versoes-status');
  const lst = $('adm-versoes-list');
  if (st)  st.textContent = 'Carregando...';
  if (lst) lst.innerHTML  = '';

  try {
    const r = await fetch(ORQUESTRA_API + '/versao');
    if (!r.ok) { if (st) st.textContent = 'Erro: ' + r.status; return; }
    const payload  = await r.json();
    const versions = (payload && payload.data) ? payload.data : [];
    if (st) st.textContent = '';

    if (!lst) return;
    if (!versions.length) {
      lst.innerHTML = '<div style="color:var(--muted);font-size:13px;padding:.5rem 0">Nenhuma versão registrada.</div>';
      return;
    }

    lst.innerHTML = '<table style="width:100%;border-collapse:collapse;font-size:13px">' +
      '<thead><tr style="border-bottom:2px solid var(--border)">' +
        '<th style="text-align:left;padding:.4rem .5rem;font-size:11px;color:var(--muted)">Versão</th>' +
        '<th style="text-align:left;padding:.4rem .5rem;font-size:11px;color:var(--muted)">Título</th>' +
        '<th style="text-align:left;padding:.4rem .5rem;font-size:11px;color:var(--muted)">Data</th>' +
        '<th style="text-align:left;padding:.4rem .5rem;font-size:11px;color:var(--muted)">Por</th>' +
        '<th style="padding:.4rem .5rem;font-size:11px;color:var(--muted)">Ações</th>' +
      '</tr></thead><tbody>' +
      versions.map(v =>
        `<tr style="border-bottom:1px solid var(--border)">
          <td style="padding:.5rem"><span style="background:var(--cvp-blue);color:#fff;font-size:11px;font-weight:700;padding:2px 7px;border-radius:999px">v${v.versao||'?'}</span></td>
          <td style="padding:.5rem">${v.titulo||'—'}</td>
          <td style="padding:.5rem;font-size:11px;color:var(--muted)">${(v.criado_em||'').substring(0,10)}</td>
          <td style="padding:.5rem;font-size:11px;color:var(--muted)">${v.criado_por||'admin'}</td>
          <td style="padding:.5rem;white-space:nowrap">
            <button class="btn-ghost btn-sm" style="font-size:11px;margin-right:4px" onclick="admEditVersao(${v.id},'${(v.versao||'').replace(/'/g,"\\'")}','${(v.titulo||'').replace(/'/g,"\\'")}',${JSON.stringify(v.descricao_md||'').replace(/</g,'&lt;')})">Editar</button>
            <button class="btn-ghost btn-sm" style="font-size:11px;color:var(--red)" onclick="admDeleteVersao(${v.id},'${(v.versao||'').replace(/'/g,"\\'")}')">Excluir</button>
          </td>
        </tr>`
      ).join('') + '</tbody></table>';
  } catch(e) {
    if (st) st.textContent = 'Erro: ' + (e && e.message ? e.message : e);
  }
}

function _versaoTabSwitch(tab) {
  const isEdit = tab === 'edit';
  const ta  = $('adm-versao-desc');
  const pv  = $('adm-versao-preview-box');
  const tEdit = $('adm-versao-tab-edit');
  const tPrev = $('adm-versao-tab-preview');
  if (!ta || !pv) return;
  if (isEdit) {
    ta.style.display  = '';
    pv.style.display  = 'none';
    if (tEdit) { tEdit.style.background = 'var(--cvp-blue)'; tEdit.style.color = '#fff'; }
    if (tPrev) { tPrev.style.background = 'var(--card)'; tPrev.style.color = 'var(--text)'; }
  } else {
    ta.style.display  = 'none';
    pv.style.display  = '';
    pv.innerHTML = ta.value.trim() ? _renderMarkdown(ta.value) : '<span style="color:var(--muted);font-size:12px">Nenhum conteúdo para visualizar.</span>';
    if (tEdit) { tEdit.style.background = 'var(--card)'; tEdit.style.color = 'var(--text)'; }
    if (tPrev) { tPrev.style.background = 'var(--cvp-blue)'; tPrev.style.color = '#fff'; }
  }
}

function _versaoLivePreview() {
  // Atualiza preview em background se já estiver visível
  const pv = $('adm-versao-preview-box');
  const ta = $('adm-versao-desc');
  if (pv && pv.style.display !== 'none' && ta) {
    pv.innerHTML = ta.value.trim() ? _renderMarkdown(ta.value) : '<span style="color:var(--muted);font-size:12px">Nenhum conteúdo para visualizar.</span>';
  }
}

function admOpenNewVersao() {
  if ($('adm-versao-form-title')) $('adm-versao-form-title').textContent = 'Nova Versão';
  if ($('adm-versao-edit-id'))    $('adm-versao-edit-id').value = '';
  if ($('adm-versao-num'))        $('adm-versao-num').value = '';
  if ($('adm-versao-titulo'))     $('adm-versao-titulo').value = '';
  if ($('adm-versao-desc'))       $('adm-versao-desc').value = '';
  if ($('adm-versao-msg'))        { $('adm-versao-msg').textContent = ''; $('adm-versao-msg').className = 'msg'; }
  if ($('adm-versao-form'))       $('adm-versao-form').style.display = '';
  try { $('adm-versao-num').focus(); } catch(e) {}
}

function admCloseVersaoForm() {
  if ($('adm-versao-form')) $('adm-versao-form').style.display = 'none';
  _versaoTabSwitch('edit'); // volta sempre para aba de edição
}

function admEditVersao(id, versao, titulo, descricaoJson) {
  let desc = '';
  try { desc = JSON.parse(descricaoJson); } catch(e) { desc = descricaoJson || ''; }
  if ($('adm-versao-form-title')) $('adm-versao-form-title').textContent = 'Editar Versão';
  if ($('adm-versao-edit-id'))    $('adm-versao-edit-id').value = id;
  if ($('adm-versao-num'))        $('adm-versao-num').value = versao;
  if ($('adm-versao-titulo'))     $('adm-versao-titulo').value = titulo;
  if ($('adm-versao-desc'))       $('adm-versao-desc').value = desc;
  if ($('adm-versao-msg'))        { $('adm-versao-msg').textContent = ''; $('adm-versao-msg').className = 'msg'; }
  if ($('adm-versao-form'))       $('adm-versao-form').style.display = '';
  try { $('adm-versao-num').focus(); } catch(e) {}
}

async function admSaveVersao() {
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }
  const editId  = $('adm-versao-edit-id') ? $('adm-versao-edit-id').value.trim() : '';
  const versao  = $('adm-versao-num')     ? $('adm-versao-num').value.trim()     : '';
  const titulo  = $('adm-versao-titulo')  ? $('adm-versao-titulo').value.trim()  : '';
  const desc    = $('adm-versao-desc')    ? $('adm-versao-desc').value.trim()    : '';
  const msg     = $('adm-versao-msg');
  if (msg) { msg.textContent = ''; msg.className = 'msg'; }

  if (!versao || !titulo) {
    if (msg) { msg.textContent = 'Versão e título são obrigatórios.'; msg.className = 'msg erro'; }
    return;
  }

  const action     = editId ? 'update' : 'create';
  const criado_por = window.__currentUser || 'admin';
  const conf = { action, versao, titulo, descricao_md: desc || null, criado_por };
  if (editId) conf.id = parseInt(editId);

  await triggerAndPoll(
    VERSAO_REGISTER_DAG, conf,
    action === 'update' ? 'Versão v' + versao : 'Nova versão v' + versao,
    null, null, null
  );
  admCloseVersaoForm();
  admLoadVersoes();
  // Sincroniza window.__appConfig e badge de versão no header
  if (window.__appConfig) {
    window.__appConfig.app_version     = versao;
    window.__appConfig.app_release_name = titulo;
  }
  _renderVersionBadge();
}

async function admDeleteVersao(id, versao) {
  if (!authHeader) return;
  if (!confirm('Excluir a versão v' + versao + '? Esta ação é irreversível.')) return;

  await triggerAndPoll(
    VERSAO_REGISTER_DAG,
    { action: 'delete', id: id, criado_por: window.__currentUser || 'admin' },
    'Excluir versão v' + versao,
    null, null, null
  );
  admLoadVersoes();
}
