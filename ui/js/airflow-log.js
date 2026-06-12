(function() {
  let _aflState = { pipeline: '', executionId: '', dagRunId: '', taskId: '', tryNum: 1 };

  window._showAirflowLogPicker = function(pipeline, executionId, project) {
    _aflState.pipeline    = pipeline;
    _aflState.executionId = executionId;
    _aflState.dagRunId    = _buildDagRunId(executionId);
    _aflState.tryNum      = 1;

    const sub = $('afl-subtitle');
    if (sub) sub.textContent = pipeline + ' · ' + executionId;

    // Buscar lista de jobs para esse execution via detail_mode
    _airflowLogShowPicker(pipeline, executionId);
    $('modal-airflow-log').classList.add('open');
  };

  window._airflowLogClose = function() {
    $('modal-airflow-log').classList.remove('open');
    const content = $('afl-content');
    if (content) content.textContent = '';
  };

  async function _airflowLogShowPicker(pipeline, executionId) {
    const loadEl = $('afl-loading');
    const selDiv = $('afl-job-selector');
    const selEl  = $('afl-job-select');
    if (loadEl) { loadEl.style.display = ''; loadEl.textContent = '⏳ Buscando tarefas...'; }
    if (selDiv) selDiv.style.display = 'none';

    try {
      // Buscar task instances via Airflow REST API
      const dagId    = _pipelineToDagId(pipeline);
      // Resolver dag_run_id real (runs manuais usam "manual__" ou ID customizado)
      const dagRunId = await _resolveAirflowDagRunId(dagId, executionId);
      _aflState.dagRunId = dagRunId; // persistir para _airflowLogFetch
      const resp = await fetch(
        '/api/v1/dags/' + encodeURIComponent(dagId) +
        '/dagRuns/' + encodeURIComponent(dagRunId) + '/taskInstances',
        { headers: { 'Authorization': _sysAuth() } }
      );
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      // Incluir TODAS as tasks de job (exceto helpers log_* e teams_*)
      // independente do estado (success, failed, warning, skipped)
      const tasks = (data.task_instances || [])
        .filter(t => !t.task_id.startsWith('log_') && !t.task_id.startsWith('teams_'))
        .sort((a, b) => {
          // Ordenar: FAILED primeiro, depois WARNING, depois demais
          const order = { failed: 0, upstream_failed: 1, warning: 2, success: 3, skipped: 4 };
          const oa = order[t.state] ?? 5, ob = order[b.state] ?? 5;
          return oa !== ob ? oa - ob : (a.task_id > b.task_id ? 1 : -1);
        });

      if (tasks.length === 0) throw new Error('Nenhuma task encontrada.');

      // Preencher select
      if (selEl) {
        selEl.innerHTML = tasks.map(t =>
          '<option value="' + t.task_id + '" data-try="' + (t.try_number || 1) + '">' +
          t.task_id + ' — ' + (t.state || '?') +
          '</option>'
        ).join('');
        // Selecionar a primeira task com estado != success para ir direto ao erro
        const failedTask = tasks.find(t => t.state === 'failed' || t.state === 'upstream_failed');
        if (failedTask) {
          selEl.value = failedTask.task_id;
        }
      }
      if (selDiv) selDiv.style.display = tasks.length > 1 ? '' : 'none';
      _airflowLogFetch();
    } catch(e) {
      if (loadEl) loadEl.textContent = '⚠ ' + e.message + ' — tente abrir o log diretamente no Airflow.';
    }
  }

  window._airflowLogFetch = async function() {
    const selEl   = $('afl-job-select');
    const loadEl  = $('afl-loading');
    const contEl  = $('afl-content');
    const copyBtn = $('afl-copy-btn');
    const linkEl  = $('afl-airflow-link');
    const cntEl   = $('afl-lines-count');

    if (!selEl || !selEl.value) return;
    const taskId = selEl.value;
    const opt    = selEl.selectedOptions[0];
    const tryNum = opt ? (parseInt(opt.dataset.try || '1', 10) || 1) : 1;
    _aflState.taskId = taskId;
    _aflState.tryNum = tryNum;

    if (loadEl) { loadEl.style.display = ''; loadEl.textContent = '⏳ Buscando log...'; }
    if (contEl) contEl.style.display = 'none';
    if (copyBtn) copyBtn.style.display = 'none';
    if (linkEl)  linkEl.style.display  = 'none';

    const dagId = _pipelineToDagId(_aflState.pipeline);

    // Resolver dag_run_id REAL (pode ser scheduled, manual, ou custom do ORQUESTRA)
    if (loadEl) loadEl.textContent = '⏳ Resolvendo execução no Airflow...';
    const dagRunId = await _resolveAirflowDagRunId(dagId, _aflState.executionId);
    _aflState.dagRunId = dagRunId; // atualizar para uso posterior

    // Link para o Airflow usando AIRFLOW_UI (igual ao padrão do restante do sistema)
    const airflowBase = (typeof AIRFLOW_UI !== 'undefined' ? AIRFLOW_UI : '');
    const airflowUrl  = airflowBase + '/dags/' + dagId +
      '/grid?dag_run_id=' + encodeURIComponent(dagRunId) +
      '&task_id=' + encodeURIComponent(taskId) + '&tab=logs';
    if (linkEl) { linkEl.href = airflowUrl; linkEl.style.display = ''; }

    if (loadEl) loadEl.textContent = '⏳ Buscando log...';

    try {
      const logResp = await fetch(
        '/api/v1/dags/' + encodeURIComponent(dagId) +
        '/dagRuns/' + encodeURIComponent(dagRunId) +
        '/taskInstances/' + encodeURIComponent(taskId) +
        '/logs/' + tryNum,
        { headers: { 'Authorization': _sysAuth(), 'Accept': 'text/plain' } }
      );
      if (!logResp.ok) throw new Error('HTTP ' + logResp.status);
      let text = await logResp.text();

      // Limpar marcadores de continuação do Airflow
      text = text.replace(/\r/g, '').replace(/[\x00-\x08\x0E-\x1F\x7F]|\x1b\[[0-9;]*[A-Za-z]/g, '');

      if (contEl) {
        contEl.textContent = text;
        contEl.style.display = '';
        // Colorir linhas de erro
        _colorizeLog(contEl);
      }
      if (loadEl) loadEl.style.display = 'none';
      if (copyBtn) copyBtn.style.display = '';
      const lines = text.split('\n').length;
      if (cntEl) cntEl.textContent = lines + ' linha(s)';
    } catch(e) {
      if (loadEl) loadEl.textContent = '⚠ Não foi possível buscar o log: ' + e.message;
    }
  };

  function _colorizeLog(el) {
    if (!el) return;
    const raw = el.textContent;
    const colored = raw.split('\n').map(line => {
      if (/error|exception|failed|traceback|critical/i.test(line))
        return '<span style="color:#ff7b72">' + _escHtml(line) + '</span>';
      if (/warning|warn/i.test(line))
        return '<span style="color:#e3b341">' + _escHtml(line) + '</span>';
      if (/success|completed|finished/i.test(line))
        return '<span style="color:#7ee787">' + _escHtml(line) + '</span>';
      if (/INFO/i.test(line))
        return '<span style="color:#79c0ff">' + _escHtml(line) + '</span>';
      return _escHtml(line);
    }).join('\n');
    el.innerHTML = colored;
  }

  function _escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  window._airflowLogCopy = function() {
    const contEl = $('afl-content');
    if (!contEl) return;
    const text = contEl.textContent || '';
    // navigator.clipboard só existe em HTTPS — usar execCommand como fallback (HTTP)
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text)
        .then(() => showToast('Log copiado.', false))
        .catch(() => _copyFallback(text));
    } else {
      _copyFallback(text);
    }
  };

  function _copyFallback(text) {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0;pointer-events:none';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      showToast(ok ? 'Log copiado.' : 'Não foi possível copiar.', !ok);
    } catch(e) {
      showToast('Copie manualmente: Ctrl+A no log.', true);
    }
  }


  // Resolve o dag_run_id REAL consultando a API do Airflow.
  // Busca as 50 runs mais recentes sem filtro de data e compara client-side,
  // evitando que filtros server-side do Airflow retornem runs de outras datas.
  async function _resolveAirflowDagRunId(dagId, executionId) {
    // Converter ts_nodash (20260602T130000) → ISO (2026-06-02T13:00:00+00:00)
    let isoStr = executionId;
    if (/^\d{8}T\d{6}$/.test(executionId)) {
      const y=executionId.slice(0,4), mo=executionId.slice(4,6), d=executionId.slice(6,8);
      const h=executionId.slice(9,11), mi=executionId.slice(11,13), s=executionId.slice(13,15);
      isoStr = y+'-'+mo+'-'+d+'T'+h+':'+mi+':'+s+'+00:00';
    }
    const targetMs = new Date(isoStr).getTime();
    const TEN_MIN  = 10 * 60 * 1000;
    try {
      const url = '/api/v1/dags/' + encodeURIComponent(dagId) +
        '/dagRuns?limit=50&order_by=-execution_date';
      const r = await fetch(url, { headers: { 'Authorization': _sysAuth() } });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const data = await r.json();
      const runs = data.dag_runs || [];
      // Correspondência client-side: aceita o run mais próximo dentro de ±10min
      let best = null, bestDelta = Infinity;
      for (const run of runs) {
        const runMs = new Date(run.execution_date).getTime();
        const delta = Math.abs(runMs - targetMs);
        if (delta < bestDelta) { bestDelta = delta; best = run; }
      }
      if (best && bestDelta <= TEN_MIN) {
        console.log('[ORQ] dag_run_id resolvido (delta=' + Math.round(bestDelta/1000) + 's):', best.dag_run_id);
        return best.dag_run_id;
      }
    } catch(e) {
      console.warn('[ORQ] _resolveAirflowDagRunId fallback:', e.message);
    }
    // Fallback: scheduled__ + ISO (funciona para runs agendados normais)
    return 'scheduled__' + isoStr;
  }

  function _buildDagRunId(executionId) {
    if (/^\d{8}T\d{6}$/.test(executionId)) {
      const y = executionId.slice(0,4), mo = executionId.slice(4,6), d = executionId.slice(6,8);
      const h = executionId.slice(9,11), mi = executionId.slice(11,13), s = executionId.slice(13,15);
      return 'scheduled__' + y + '-' + mo + '-' + d + 'T' + h + ':' + mi + ':' + s + '+00:00';
    }
    return executionId;
  }
  // Expor globalmente para que funções fora do IIFE possam usar
  window._buildDagRunId = _buildDagRunId;

  // Setter global — permite que funções fora do IIFE alimentem _aflState
  window._setAflState = function(pipeline, executionId, taskId) {
    _aflState.pipeline    = pipeline    || '';
    _aflState.executionId = executionId || '';
    _aflState.dagRunId    = _buildDagRunId(executionId || '');
    _aflState.taskId      = taskId      || '';
    _aflState.tryNum      = 1;
  };

  // Fechar ao clicar fora
  document.getElementById('modal-airflow-log').addEventListener('click', function(e) {
    if (e.target === this) _airflowLogClose();
  });
})();
