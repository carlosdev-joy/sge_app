/* Modelo exclusivo de demonstração. Sem chamadas ao backend ou dados reais. */
(function (root) {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  function validate(pipeline) {
    const issues = [];
    const { config, nodes } = pipeline;
    if (!config.name.trim()) issues.push({ field: 'name', message: 'Informe o nome do pipeline.' });
    if (!/^[A-Z][A-Z0-9_]{2,59}$/.test(config.id)) issues.push({ field: 'id', message: 'Use um identificador com 3 a 60 letras maiúsculas, números ou _.' });
    if (!nodes.length) issues.push({ message: 'Adicione a primeira etapa ao fluxo.' });
    for (const [key, min, max] of [['concurrency', 1, 50], ['timeout', 1, 1440], ['retries', 0, 10]]) {
      const label = { concurrency: 'execuções simultâneas', timeout: 'tempo limite em minutos', retries: 'tentativas adicionais' }[key];
      if (config[key] != null && (!/^\d+$/.test(config[key]) || Number(config[key]) < min || Number(config[key]) > max)) issues.push({ field: key, message: `Revise ${label}: informe um número de ${min} a ${max}.` });
    }
    const ids = new Set(nodes.map(n => n.id));
    for (const node of nodes) {
      if (!node.name.trim()) issues.push({ node: node.id, message: 'Uma etapa precisa de nome.' });
      if (!node.job.trim()) issues.push({ node: node.id, message: `Selecione o recurso de ${node.name}.` });
      for (const [key, min, max] of [['timeout', 1, 1440], ['retries', 0, 10]]) if (node[key] != null && (!/^\d+$/.test(node[key]) || Number(node[key]) < min || Number(node[key]) > max)) issues.push({ node: node.id, message: `Revise o tratamento de falha de ${node.name}.` });
      for (const dep of node.deps) if (!ids.has(dep)) issues.push({ node: node.id, message: 'Dependência inexistente.' });
    }
    const visiting = new Set(), visited = new Set();
    function walk(id) {
      if (visiting.has(id)) return true;
      if (visited.has(id)) return false;
      visiting.add(id);
      const node = nodes.find(n => n.id === id);
      if (node && node.deps.some(walk)) return true;
      visiting.delete(id); visited.add(id); return false;
    }
    if (nodes.some(n => walk(n.id))) issues.push({ message: 'Há um ciclo nas dependências. Remova a ligação circular.' });
    return issues;
  }
  function newRun(version, scenario, now, serial) {
    return {
      id: `SIM-${String(serial).padStart(4, '0')}`, version: version.number,
      snapshot: clone(version.snapshot), scenario, started: now, finished: null, status: 'running',
      tasks: Object.fromEntries(version.snapshot.nodes.map(n => [n.id, {
        state: 'pending', attempt: 0, started: null, finished: null, history: [], logs: []
      }]))
    };
  }
  function advance(run, now) {
    if (run.status !== 'running') return run;
    const nodes = run.snapshot.nodes;
    for (const node of nodes) {
      const task = run.tasks[node.id];
      if (task.state === 'running' && now - task.started >= node.duration * 1000) {
        const failed = run.scenario === 'failure' && node.kind === 'quality' && task.attempt === 1;
        task.state = failed ? 'failed' : 'success'; task.finished = now;
        task.logs.push({ time: now, message: failed ? 'Falha simulada: regra de qualidade não atendida.' : 'Etapa concluída na simulação.' });
        task.history.push({ attempt: task.attempt, state: task.state, started: task.started, finished: now });
      }
    }
    for (const node of nodes) {
      const task = run.tasks[node.id];
      if (!['pending', 'dependencies', 'capacity'].includes(task.state)) continue;
      const deps = node.deps.map(id => run.tasks[id]?.state);
      if (deps.some(s => ['failed', 'blocked'].includes(s))) { task.state = 'blocked'; continue; }
      if (!deps.every(s => ['success', 'skipped'].includes(s))) { task.state = 'dependencies'; continue; }
      if (run.scenario === 'capacity' && now - run.started < 4000) { task.state = 'capacity'; continue; }
      if (run.scenario === 'skip' && node.kind === 'delivery') {
        task.state = 'skipped'; task.finished = now;
        task.logs.push({ time: now, message: 'Entrega pulada pela condição simulada.' }); continue;
      }
      task.state = 'running'; task.attempt += 1; task.started = now; task.finished = null;
      task.logs.push({ time: now, message: `Tentativa ${task.attempt} iniciada na simulação.` });
    }
    if (Object.values(run.tasks).every(t => ['success', 'failed', 'blocked', 'skipped'].includes(t.state))) {
      run.status = Object.values(run.tasks).some(t => t.state === 'failed') ? 'failed' : 'success';
      run.finished = now;
    }
    return run;
  }
  function retry(run, id) {
    const task = run.tasks[id];
    if (!task || task.state !== 'failed') return false;
    task.state = 'pending'; task.started = null; task.finished = null;
    for (const value of Object.values(run.tasks)) if (value.state === 'blocked') value.state = 'pending';
    run.status = 'running'; run.finished = null; return true;
  }
  const api = { clone, validate, newRun, advance, retry };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PipelineDemo = api;
})(typeof window !== 'undefined' ? window : globalThis);
