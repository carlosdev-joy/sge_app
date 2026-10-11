const assert = require('node:assert/strict');
const { validate, newRun, advance, retry } = require('./model.js');
const pipeline = { config: { name: 'Teste', id: 'TESTE' }, nodes: [
  { id: 'a', name: 'Origem', job: 'origem', kind: 'source', duration: 1, deps: [] },
  { id: 'b', name: 'Qualidade', job: 'qualidade', kind: 'quality', duration: 1, deps: ['a'] },
  { id: 'c', name: 'Entrega', job: 'entrega', kind: 'delivery', duration: 1, deps: ['b'] }
] };
assert.deepEqual(validate(pipeline), []);
const invalidPolicy = structuredClone(pipeline); invalidPolicy.config.concurrency = '0';
assert.match(validate(invalidPolicy)[0].message, /execuções simultâneas/);
const cycle = structuredClone(pipeline); cycle.nodes[0].deps = ['c'];
assert.match(validate(cycle)[0].message, /ciclo/);
const version = { number: '1.0', snapshot: pipeline };
const failure = newRun(version, 'failure', 0, 1);
advance(failure, 0); assert.equal(failure.tasks.b.state, 'dependencies');
advance(failure, 1000); assert.equal(failure.tasks.a.state, 'success');
advance(failure, 2000); assert.equal(failure.tasks.b.state, 'failed'); assert.equal(failure.tasks.c.state, 'blocked');
assert.equal(retry(failure, 'a'), false); assert.equal(retry(failure, 'b'), true);
advance(failure, 2000); advance(failure, 3000); advance(failure, 4000);
assert.equal(failure.status, 'success'); assert.equal(failure.tasks.b.attempt, 2); assert.equal(failure.tasks.b.history.length, 2);
const capacity = newRun(version, 'capacity', 0, 2);
advance(capacity, 0); assert.equal(capacity.tasks.a.state, 'capacity');
advance(capacity, 3999); assert.equal(capacity.tasks.a.state, 'capacity');
advance(capacity, 4000); assert.equal(capacity.tasks.a.state, 'running');
const skip = newRun(version, 'skip', 0, 3);
advance(skip, 0); advance(skip, 1000); advance(skip, 2000);
assert.equal(skip.tasks.c.state, 'skipped'); assert.equal(skip.status, 'success');
pipeline.nodes[0].name = 'Alterado no rascunho';
assert.equal(skip.snapshot.nodes[0].name, 'Origem');
console.log('OK: dependências, ciclos, capacidade, falha, retomada, tentativas, ramo pulado e snapshot imutável.');
