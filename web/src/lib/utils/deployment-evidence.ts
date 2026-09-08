import type { CheckState, DeepReadiness } from '$lib/types/api';

const SOURCE_REVISION = /^[0-9a-f]{40}$/;
const DATABASE_REVISION = /^[0-9]{4}_[a-z0-9_]{1,63}$/;

export interface DeploymentEvidence {
  sourceRevision: string;
  sourceRevisionStatus: CheckState;
  databaseRevision: string;
  expectedDatabaseRevision: string;
  databaseRevisionStatus: CheckState;
  biliContinuation: string;
  xhsContinuation: string;
}

function safeDatabaseRevision(value: unknown): string | null {
  return typeof value === 'string' && DATABASE_REVISION.test(value) ? value : null;
}

function continuationLabel(value: unknown): string {
  if (
    typeof value !== 'number' ||
    !Number.isSafeInteger(value) ||
    (value !== 0 && (value < 60 || value > 604_800))
  )
    return '不可用';
  return value === 0 ? '普通周期（快速续跑关闭）' : `${value} 秒`;
}

/** Fail closed so unexpected backend text never becomes diagnostic UI content. */
export function deploymentEvidence(report: DeepReadiness | null): DeploymentEvidence {
  const source = report?.build_manifest.source_revision;
  const declaredSourceStatus = report?.build_manifest.source_revision_status ?? 'not_run';
  const sourceValid = typeof source === 'string' && SOURCE_REVISION.test(source);
  const safeSource = sourceValid ? source : null;
  const sourceRevisionStatus: CheckState =
    declaredSourceStatus === 'pass' && sourceValid
      ? 'pass'
      : declaredSourceStatus === 'fail' || (declaredSourceStatus === 'pass' && !sourceValid)
        ? 'fail'
        : 'not_run';

  const current = safeDatabaseRevision(report?.database.revision);
  const expected = safeDatabaseRevision(report?.database.expected_revision);
  const databaseRevisionStatus: CheckState =
    report === null
      ? 'not_run'
      : report.database.revision_current === true && current !== null && current === expected
        ? 'pass'
        : 'fail';

  return {
    sourceRevision:
      sourceRevisionStatus === 'pass' && safeSource !== null
        ? safeSource
        : sourceRevisionStatus === 'fail'
          ? '无效'
          : '未记录',
    sourceRevisionStatus,
    databaseRevision: current ?? '未识别',
    expectedDatabaseRevision: expected ?? '未识别',
    databaseRevisionStatus,
    biliContinuation: continuationLabel(report?.continuations?.bili_delay_seconds),
    xhsContinuation: continuationLabel(report?.continuations?.xhs_delay_seconds)
  };
}
