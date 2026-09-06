import { readFileSync } from 'node:fs';
import { describe, expect, it, vi } from 'vitest';
import { api, ApiError } from './client';
import {
  LogCenterController,
  initialLogFilters,
  logAction,
  logDiagnosticArtifact,
  logFailure,
  logErrorType,
  logIdentityLink,
  logPhase,
  logQuery,
  logStream,
  logSummary,
  type LogEvent,
  type LogFilters
} from './log-center';

const OP = '11111111-1111-4111-8111-111111111111';
const OTHER = '22222222-2222-4222-8222-222222222222';
const WRITER = '33333333-3333-4333-8333-333333333333';
const AT = '2026-09-06T04:10:11.123456Z';
const SECRET = 'SENTINEL-cookie-SQL-C:/private/path?token=secret';
function event(sequence = 1, operation_id = OP): LogEvent {
  return {
    schema_version: 1,
    timestamp: AT,
    writer_id: WRITER,
    sequence,
    event_code: 'login_stage',
    module: 'login',
    level: 'info',
    phase: 'qr_locate',
    action: 'wait_selector',
    outcome: 'started',
    operation_id
  };
}
function outputEvent(message = 'ERROR Playwright browser navigation failed', sequence = 10): LogEvent {
  return {
    ...event(sequence),
    event_code: 'process_output',
    module: 'crawler',
    phase: 'upstream_execution',
    action: 'execute',
    outcome: 'running',
    stream: 'upstream',
    message
  };
}
function page(events = [event()], next_cursor: string | null = null) {
  return {
    events,
    next_cursor,
    coverage: {
      order: 'segment_ascending',
      global_time_order: false,
      bounded: true,
      scan_limited: false,
      corrupt_records: 0,
      truncated_segments: 0,
      unavailable_segments: 0,
      omitted_segment_tails: 2,
      retention_may_have_removed: true
    }
  };
}
function status() {
  return {
    health: 'ok',
    queued: 0,
    accepted: 1,
    written: 1,
    dropped: 0,
    invalid: 0,
    segment_max_bytes: 1048576,
    total_max_bytes: 10485760,
    retention_days: 7,
    storage_bytes: 200,
    managed_segments: 1,
    active_segments: 1,
    scope: 'process_counters_shared_storage',
    last_error: null,
    writer_running: true,
    drained: true,
    shutdown_complete: false
  };
}
function trace(id = OP) {
  return {
    schema_version: 1,
    generated_at: AT,
    operation: {
      id,
      kind: 'account-login',
      state: 'running',
      phase: 'authenticating',
      runner_status: null,
      correlation_id: OTHER,
      requested_at: AT,
      started_at: AT,
      finished_at: null,
      revision: 1,
      target_type: 'account',
      target_id: OTHER
    },
    subjects: [{ id: OTHER, type: 'login_session', role: 'execution' }],
    subjects_truncated: false,
    control_events: [
      {
        sequence: 1,
        at: AT,
        event_code: 'operation_started',
        phase: 'starting',
        level: 'info',
        from_state: 'queued',
        to_state: 'running'
      }
    ],
    control_events_truncated: false,
    login_stage_evidence: 'available_in_page',
    logs: page([event(1, id)])
  };
}
function diagnostic(id = OP) {
  return {
    diagnostic_schema_version: 1,
    project: { name: 'media-sync', version: '0.2.0' },
    upstreams: { MediaCrawler: 'a'.repeat(40), 'bili-sync-up': 'b'.repeat(40) },
    trace: trace(id),
    logging: status(),
    limitations: ['bounded_retained_page', 'no_raw_output_or_credentials', 'not_live_qualification']
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function setup() {
  const request = vi.fn(),
    publish = vi.fn();
  const controller = new LogCenterController(publish, request as typeof api);
  return { request, publish, controller };
}
function responds(
  request: ReturnType<typeof vi.fn>,
  events = [event()],
  cursor: string | null = null,
  id?: string
) {
  request.mockResolvedValueOnce(page(events, cursor)).mockResolvedValueOnce(status());
  if (id) request.mockResolvedValueOnce(trace(id));
}

describe('log filter query boundary', () => {
  it('treats undefined select/text bindings and blank fields as omitted', () => {
    expect(
      logQuery({ platform: undefined, level: undefined, module: '', operation_id: undefined, since: '' })
    ).toBe('/api/v1/logs?limit=100');
  });
  it('encodes cursor content as one opaque same-origin query value', () => {
    const cursor = 'abc+/=?&operation_id=OTHER#fragment';
    const url = new URL(logQuery({ operation_id: OP, module: 'login' }, cursor), 'https://local.invalid');
    expect(url.pathname).toBe('/api/v1/logs');
    expect(url.searchParams.get('operation_id')).toBe(OP);
    expect(url.searchParams.get('cursor')).toBe(cursor);
    expect(url.hash).toBe('');
  });
  it('converts explicit offset times to UTC without losing microseconds', () => {
    const url = new URL(
      logQuery({ since: '2026-09-06T12:10:11.123456+08:00', until: AT }),
      'https://local.invalid'
    );
    expect(url.searchParams.get('since')).toBe(AT);
    expect(url.searchParams.get('until')).toBe(AT);
  });
  it('converts datetime-local values using the browser local timezone', () => {
    const value = '2026-09-06T12:10';
    expect(new URL(logQuery({ since: value }), 'https://local.invalid').searchParams.get('since')).toBe(
      new Date(value).toISOString().slice(0, -1) + '000Z'
    );
  });
  it.each([
    '2026',
    '09/06/2026',
    '2026-02-30T12:00',
    '2026-00-06T12:00',
    '2026-09-06T24:00',
    '2026-09-06T12:60',
    '2026-09-06T12:10:60Z',
    '2026-09-06T12:10:11.1234567Z',
    SECRET
  ])('rejects noncanonical or nonexistent time %s', (since) => {
    expect(() => logQuery({ since })).toThrow('log_query_invalid');
  });
  it('rejects inverted ranges including distinct sub-millisecond times', () => {
    expect(() => logQuery({ since: '2026-09-06T04:10:11.123457Z', until: AT })).toThrow('log_query_invalid');
  });
  it.each([
    { operation_id: SECRET },
    { module: SECRET },
    { platform: 'all' },
    { level: 'trace' },
    { since: null },
    { operation_id: 1 },
    { raw_cookie: SECRET }
  ])('rejects unsafe filters before transport %j', (filters) => {
    expect(() => logQuery(filters as LogFilters)).toThrow('log_query_invalid');
  });
  it('round-trips supported deep-link filters and only retains allowlisted form values', () => {
    const params = new URLSearchParams({
      operation_id: OP,
      subscription_id: OTHER,
      module: 'login',
      level: 'warning',
      platform: 'bili',
      since: AT,
      until: '2026-09-06T04:11:12.000000Z',
      account_id: SECRET,
      token: SECRET
    });
    const initial = initialLogFilters(params);
    const selected = new URL(logQuery(initial), 'https://local.invalid').searchParams;
    expect(initial.operation_id).toBe(OP);
    expect(initial.subscription_id).toBe(OTHER);
    expect(initial.module).toBe('login');
    expect(selected.get('since')).toBe(AT);
    expect(JSON.stringify(initial)).not.toContain(SECRET);
  });
  it('creates only validated same-page identity links', () => {
    expect(logIdentityLink('job_id', OP)).toBe(`/logs?job_id=${OP}`);
    for (const [key, value] of [
      ['job_id', SECRET],
      ['correlation_id', OP],
      ['asset_id', OP],
      ['constructor', OP]
    ])
      expect(logIdentityLink(key, value)).toBeNull();
  });
});

describe('log controller lifecycle and retained pages', () => {
  it('retains validated process messages, stream summaries and explicit drop reasons', async () => {
    const { controller, request } = setup();
    const output = outputEvent();
    const summary: LogEvent = {
      ...event(11),
      event_code: 'process_output_summary',
      module: 'crawler',
      stream: 'stdout_protocol',
      action: 'finish',
      outcome: 'completed',
      count: 3,
      bytes: 120
    };
    const dropped: LogEvent = {
      ...event(12),
      event_code: 'process_output_dropped',
      module: 'crawler',
      stream: 'upstream',
      action: 'drop',
      outcome: 'skipped',
      error_type: 'policy_filtered',
      count: 2
    };
    responds(request, [output, summary, dropped]);

    await controller.load();

    expect(controller.view.events).toEqual([output, summary, dropped]);
    expect(logSummary(controller.view.events[0])).toContain('Playwright browser navigation failed');
    expect(logSummary(controller.view.events[1])).toContain('只保存统计');
    expect(logSummary(controller.view.events[2])).toContain('页面/作品正文');
    expect(logStream('upstream')).toBe('上游进程输出');
    expect(logErrorType('policy_filtered')).toBe('安全策略过滤');
  });
  it('loads safe rows and exact trace, including omission and writer health fields', async () => {
    const { controller, request } = setup();
    responds(request, [event()], 'next', OP);
    await controller.load({ operation_id: OP });
    expect(request.mock.calls.map(([url]) => url)).toEqual([
      logQuery({ operation_id: OP }),
      '/api/v1/logs/status',
      `/api/v1/logs/operations/${OP}`
    ]);
    expect(request.mock.calls.every(([, init]) => init.signal instanceof AbortSignal)).toBe(true);
    expect(controller.view.events).toEqual([event()]);
    expect(controller.view.trace?.operation.id).toBe(OP);
    expect(controller.view.coverage?.omitted_segment_tails).toBe(2);
    expect(controller.view.status?.writer_running).toBe(true);
    expect(controller.view.status?.shutdown_complete).toBe(false);
  });
  it('snapshots filters before await and suppresses duplicate busy loads', async () => {
    const { controller, request } = setup();
    const pending = deferred<ReturnType<typeof page>>();
    request.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(status());
    const filters: LogFilters = { module: 'login' };
    const loading = controller.load(filters);
    await controller.load({ module: 'login' });
    filters.module = 'download';
    pending.resolve(page());
    await loading;
    expect(request).toHaveBeenCalledTimes(2);
    expect(controller.view.filters.module).toBe('login');
  });
  it.each(['success', 'error'])('supersedes an old route and ignores its late %s', async (outcome) => {
    const { controller, request } = setup();
    const pending = deferred<ReturnType<typeof page>>();
    request
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce(status())
      .mockResolvedValueOnce(trace(OP));
    const first = controller.load({ operation_id: OP });
    responds(request, [event(2, OTHER)], null, OTHER);
    await controller.load({ operation_id: OTHER });
    expect(request.mock.calls[0][1].signal.aborted).toBe(true);
    if (outcome === 'success') pending.resolve(page());
    else pending.reject(new Error(SECRET));
    await first;
    expect(controller.view.filters.operation_id).toBe(OTHER);
    expect(controller.view.events[0].operation_id).toBe(OTHER);
    expect(controller.view.error).toBe('');
  });
  it('never publishes late completion or starts another load after disposal', async () => {
    const { controller, request, publish } = setup();
    const pending = deferred<ReturnType<typeof page>>();
    request.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(status());
    const loading = controller.load();
    controller.dispose();
    const count = publish.mock.calls.length;
    pending.resolve(page());
    await loading;
    await controller.load();
    expect(publish).toHaveBeenCalledTimes(count);
    expect(request).toHaveBeenCalledTimes(2);
    expect(request.mock.calls[0][1].signal.aborted).toBe(true);
  });
  it('deduplicates writer/sequence across pages but keeps distinct writers', async () => {
    const { controller, request } = setup();
    responds(request, [event()], 'cursor-one');
    await controller.load();
    responds(request, [event(), event(2), { ...event(), writer_id: OTHER }]);
    await controller.load(controller.view.filters, true);
    expect(controller.view.events).toHaveLength(3);
    expect(controller.view.coverage?.omitted_segment_tails).toBe(4);
    expect(request.mock.calls[2][0]).toBe(logQuery({}, 'cursor-one'));
  });
  it('keeps an empty matching page pageable when scan coverage has more segments', async () => {
    const { controller, request } = setup();
    responds(request, [], 'next');
    await controller.load();
    responds(request);
    await controller.load(controller.view.filters, true);
    expect(controller.view.events).toHaveLength(1);
    expect(request).toHaveBeenCalledTimes(4);
  });
  it('rejects a mismatched filter on pagination without clearing the previous page', async () => {
    const { controller, request } = setup();
    responds(request, [event()], 'cursor');
    await controller.load({ module: 'login' });
    await controller.load({ module: 'download' }, true);
    expect(request).toHaveBeenCalledTimes(2);
    expect(controller.view.events).toEqual([event()]);
    expect(controller.view.filters).toEqual({ module: 'login' });
    expect(controller.view.error).toContain('筛选条件无效');
  });
  it('retains results after stale cursor, disables continuation and never auto-replays', async () => {
    const { controller, request } = setup();
    responds(request, [event()], 'cursor');
    await controller.load();
    request
      .mockRejectedValueOnce(new ApiError(409, 'log_cursor_stale', { raw: SECRET }))
      .mockResolvedValueOnce(status());
    await controller.load(controller.view.filters, true);
    await controller.load(controller.view.filters, true);
    expect(request).toHaveBeenCalledTimes(4);
    expect(controller.view.events).toEqual([event()]);
    expect(controller.view.nextCursor).toBeNull();
    expect(controller.view.error).toContain('未自动重放');
    expect(controller.view.error).not.toContain(SECRET);
    responds(request);
    await controller.load();
    expect(controller.view.error).toBe('');
  });
  it('keeps the prior operation and page if the next trace is wrong-identity', async () => {
    const { controller, request } = setup();
    responds(request, [event()], null, OP);
    await controller.load({ operation_id: OP });
    request
      .mockResolvedValueOnce(page([event(1, OTHER)]))
      .mockResolvedValueOnce(status())
      .mockResolvedValueOnce(trace(OP));
    await controller.load({ operation_id: OTHER });
    expect(controller.view.filters.operation_id).toBe(OP);
    expect(controller.view.trace?.operation.id).toBe(OP);
    expect(controller.view.events).toEqual([event()]);
    expect(controller.view.error).toContain('身份校验');
  });
  it('caps display at 2000 and never issues a further continuation request', async () => {
    const { controller, request } = setup();
    for (let index = 0; index < 10; index++) {
      responds(
        request,
        Array.from({ length: 200 }, (_, n) => event(index * 200 + n + 1)),
        `cursor-${index}`
      );
      await controller.load({}, index > 0);
    }
    await controller.load({}, true);
    expect(controller.view.events).toHaveLength(2000);
    expect(request).toHaveBeenCalledTimes(20);
  });
});

describe('diagnostic artifact and UI safety', () => {
  it('accepts fixed whole-line redaction but rejects unsafe process-output messages and streams', () => {
    const safe = diagnostic();
    safe.trace.logs.events = [outputEvent('[REDACTED]')];
    expect(JSON.parse(logDiagnosticArtifact(safe, OP).text).trace.logs.events[0].message).toBe('[REDACTED]');

    for (const message of [
      "ERROR cookies: [{'name':'SESSDATA','value':'sentinel'}]",
      'ERROR Set-Cookie: sid=sentinel',
      'ERROR Authorization: Bearer sentinel',
      'ERROR storage_state={"cookies":[]}',
      'ERROR data:image/png;base64,c2VudGluZWw=',
      'ERROR qrcode=c2VudGluZWw=',
      'ERROR https://cdn.invalid/video?token=sentinel#private',
      String.raw`ERROR C:\Users\private\profile`,
      'ERROR /home/private/profile/state.json',
      'ERROR {"title":"a work says login error"}',
      'ERROR ["a work says login error"]',
      'ERROR <div>a work says login error</div>',
      'ERROR content=a work says login error',
      'the creator caption says login error'
    ]) {
      const value = diagnostic();
      value.trace.logs.events = [outputEvent(message)];
      expect(() => logDiagnosticArtifact(value, OP)).toThrow('log_response_invalid');
    }
    const wrongStream = diagnostic();
    wrongStream.trace.logs.events = [{ ...outputEvent(), stream: 'stderr' }];
    expect(() => logDiagnosticArtifact(wrongStream, OP)).toThrow('log_response_invalid');
  });
  it('downloads only an exact-operation bounded projection', () => {
    const artifact = logDiagnosticArtifact(diagnostic(), OP);
    expect(artifact.filename).toBe(`media-sync-diagnostic-${OP}.json`);
    const result = JSON.parse(artifact.text);
    expect(result.trace.operation.id).toBe(OP);
    expect(result.trace.logs.events).toEqual([event()]);
    expect(result.upstreams.MediaCrawler).toBe('a'.repeat(40));
    expect(result.trace.logs.coverage.omitted_segment_tails).toBe(2);
  });
  it('rebuilds every nested field and excludes arbitrary error text, paths and secrets', () => {
    const input = diagnostic();
    const dirty = {
      ...input,
      raw_cookie: SECRET,
      limitations: [SECRET],
      project: { ...input.project, version: SECRET, path: SECRET },
      upstreams: { MediaCrawler: SECRET, 'bili-sync-up': SECRET },
      logging: { ...status(), last_error: SECRET, scope: SECRET, raw: SECRET },
      trace: {
        ...trace(),
        raw: SECRET,
        authentication_authority: SECRET,
        operation: { ...trace().operation, kind: SECRET, phase: SECRET, runner_status: SECRET, raw: SECRET },
        subjects: [{ id: OP, type: SECRET, role: SECRET }],
        control_events: [{ ...trace().control_events[0], phase: SECRET, event_code: SECRET, raw: SECRET }],
        logs: page([
          { ...event(), phase: SECRET, source_frame: SECRET, error_type: SECRET, raw: SECRET } as LogEvent
        ])
      }
    };
    expect(logDiagnosticArtifact(dirty, OP).text).not.toContain(SECRET);
    expect(logDiagnosticArtifact(dirty, OP).text).not.toContain('raw_cookie');
  });
  it('does not export opaque transport cursors but retains whether more evidence exists', () => {
    const value = diagnostic();
    value.trace.logs.next_cursor = SECRET;
    const artifact = logDiagnosticArtifact(value, OP);
    expect(artifact.text).not.toContain(SECRET);
    expect(JSON.parse(artifact.text).trace.logs).toMatchObject({
      next_cursor: null,
      has_more_retained_events: true
    });
    expect(JSON.parse(artifact.text).limitations).toContain('continuation_cursor_omitted');
  });
  it.each([null, [], SECRET, {}, { ...diagnostic(), diagnostic_schema_version: 2 }])(
    'rejects malformed root %j',
    (value) => {
      expect(() => logDiagnosticArtifact(value, OP)).toThrow('log_response_invalid');
    }
  );
  it('rejects wrong operation identity and mixed-operation embedded logs', () => {
    expect(() => logDiagnosticArtifact(diagnostic(OTHER), OP)).toThrow('log_response_invalid');
    const value = diagnostic();
    value.trace.logs.events.push(event(2, OTHER));
    expect(() => logDiagnosticArtifact(value, OP)).toThrow('log_response_invalid');
    expect(() => logDiagnosticArtifact(diagnostic(), SECRET)).toThrow('log_response_invalid');
  });
  it('rejects unbounded events or control timeline arrays', () => {
    const value = diagnostic();
    value.trace.logs.events = Array.from({ length: 201 }, (_, index) => event(index + 1));
    expect(() => logDiagnosticArtifact(value, OP)).toThrow('log_response_invalid');
    value.trace.logs.events = [];
    value.trace.control_events = Array.from({ length: 201 }, () => trace().control_events[0]);
    expect(() => logDiagnosticArtifact(value, OP)).toThrow('log_response_invalid');
  });
  it.each([
    new Error(SECRET),
    new ApiError(500, SECRET, { raw: SECRET }),
    new ApiError(500, '__proto__', null)
  ])('never reflects raw request errors', (error) => {
    expect(typeof logFailure(error)).toBe('string');
    expect(logFailure(error)).not.toContain(SECRET);
  });
  it('unknown label keys never expose prototype fields or raw text', () => {
    for (const value of [SECRET, '__proto__', 'constructor']) {
      expect(logPhase(value)).toBe('其它受控阶段');
      expect(logAction(value)).toBe('其它受控动作');
      expect(logSummary({ ...event(), event_code: value })).toBe('受控组件事件');
    }
    expect(logSummary({ ...event(), event_code: 'command_started' })).toContain('本地命令');
  });
  it('page guards browser download lifecycle and supports same-route identity navigation', () => {
    const source = readFileSync(new URL('../../routes/logs/+page.svelte', import.meta.url), 'utf8');
    expect(source).toContain('logDiagnosticArtifact(result.value, id)');
    expect(source).toContain('downloadGate.cancel()');
    expect(source).toContain('URL.revokeObjectURL(downloadUrl)');
    expect(source).toContain('$page.url.search !== routeQuery');
    expect(source).toContain('logIdentityLink(key, event[key as keyof typeof event])');
    expect(source).toContain('logStream(event.stream)');
    expect(source).toContain('logErrorType(event.error_type)');
    expect(source).toContain('event.count');
    expect(source).toContain('event.bytes');
    expect(source).toContain('bind:value={filters.subscription_id}');
    expect(source).toContain('omitted_segment_tails');
    expect(source).toContain('shutdown_complete');
    expect(source).not.toContain('JSON.stringify(result.value');
    expect(source).not.toContain('{@html');
    expect(source).not.toContain('localStorage');
  });
});
