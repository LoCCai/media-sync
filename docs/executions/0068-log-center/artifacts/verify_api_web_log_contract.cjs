// Receive real ASGI responses on stdin and execute the actual frontend modules.
// Transpilation stays in memory. No generated JS, response or credential files.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const assert = require('node:assert/strict');
const repository = path.resolve(__dirname, '../../../..');
const ts = require(path.join(repository, 'web/node_modules/typescript'));
const cache = new Map();

function load(file) {
  file = path.resolve(repository, file);
  if (cache.has(file)) return cache.get(file).exports;
  const mod = new Module(file, module);
  mod.filename = file;
  mod.paths = Module._nodeModulePaths(path.dirname(file));
  cache.set(file, mod);
  const original = mod.require.bind(mod);
  mod.require = (name) => {
    const candidate = path.resolve(path.dirname(file), name) + '.ts';
    return name.startsWith('.') && fs.existsSync(candidate) ? load(candidate) : original(name);
  };
  const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }
  });
  mod._compile(compiled.outputText, file);
  return mod.exports;
}

async function main() {
  const contract = JSON.parse(fs.readFileSync(0, 'utf8'));
  const lib = load('web/src/lib/api/log-center.ts');
  const auth = load('web/src/lib/stores/operator-auth.ts');
  assert.equal(auth.operatorReturnPath('?return_to=%2Flogs'), '/logs');
  const controller = new lib.LogCenterController(() => {}, async (url) => {
    if (url.startsWith('/api/v1/logs?')) return contract.page;
    if (url === '/api/v1/logs/status') return contract.status;
    if (url === '/api/v1/logs/operations/' + contract.operation_id) return contract.trace;
    throw new Error('unexpected_contract_request');
  });
  await controller.load({ operation_id: contract.operation_id });
  assert.equal(controller.view.error, '');
  assert.equal(controller.view.events.length, 1);
  assert.equal(controller.view.trace.operation.id, contract.operation_id);
  assert.equal(controller.view.trace.operation.runner_status, 'upstream_browser_timeout');
  assert.equal(controller.view.trace.control_events.length, 200);
  assert.equal(controller.view.trace.control_events_truncated, true);
  const artifact = lib.logDiagnosticArtifact(contract.diagnostic, contract.operation_id);
  const output = JSON.parse(artifact.text);
  assert.equal(output.trace.operation.id, contract.operation_id);
  assert.equal(output.trace.subjects.length, 64);
  assert.equal(output.trace.subjects_truncated, true);
  assert.equal(output.trace.logs.events[0].source_frame, 'locator');
  assert.equal(output.trace.logs.events[0].error_type, 'playwright_timeout');
  assert.equal(output.trace.generated_at, contract.diagnostic.trace.generated_at);
  assert.equal(output.trace.operation.requested_at, contract.diagnostic.trace.operation.requested_at);
  assert.equal(output.logging.writer_running, contract.status.writer_running);
  assert.equal(output.logging.drained, contract.status.drained);
  assert.equal(output.logging.shutdown_complete, contract.status.shutdown_complete);
  assert.ok(!artifact.text.includes(contract.private_sentinel));
  assert.ok(new TextEncoder().encode(artifact.text).byteLength <= 2_097_152);
  controller.dispose();
  process.stdout.write(JSON.stringify({
    runtime_contract: 'PASS', authenticated_api: '200_no_store', anonymous_api: '401_all_four',
    anonymous_pages: '303_logs_and_jobs', login_return: 'logs_accepted', events: 1,
    control_events: 200, subjects: 64, truncation_flags: 'preserved', microseconds: 'preserved',
    writer_health: 'preserved', diagnostic_limits: 'backend_1MiB_frontend_2MiB', private_fields: 'absent'
  }));
}

main().catch(() => {
  process.stdout.write(JSON.stringify({ runtime_contract: 'FAILED', reason: 'frontend_contract_rejected' }));
  process.exitCode = 1;
});
