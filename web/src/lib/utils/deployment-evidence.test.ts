import { describe, expect, it } from 'vitest';

import type { DeepReadiness } from '$lib/types/api';
import { deploymentEvidence } from './deployment-evidence';

function report(patch: Partial<DeepReadiness> = {}): DeepReadiness {
  return {
    build_manifest: {
      status: 'pass',
      present: true,
      source_revision: '47ca1079bb5db3d1e93b172402c5edeeb04f998c',
      source_revision_status: 'pass',
      facts: {}
    },
    database: {
      ok: true,
      revision: '0015_xhs_creator_notes',
      expected_revision: '0015_xhs_creator_notes',
      revision_current: true
    },
    continuations: { bili_delay_seconds: 300, xhs_delay_seconds: 0 },
    ...patch
  } as DeepReadiness;
}

describe('deployment evidence projection', () => {
  it('shows one exact source revision, current migration, and both continuation policies', () => {
    expect(deploymentEvidence(report())).toEqual({
      sourceRevision: '47ca1079bb5db3d1e93b172402c5edeeb04f998c',
      sourceRevisionStatus: 'pass',
      databaseRevision: '0015_xhs_creator_notes',
      expectedDatabaseRevision: '0015_xhs_creator_notes',
      databaseRevisionStatus: 'pass',
      biliContinuation: '300 秒',
      xhsContinuation: '普通周期（快速续跑关闭）'
    });
  });

  it('keeps an older known migration visible but marks the mismatch', () => {
    const evidence = deploymentEvidence(
      report({
        database: {
          ok: false,
          revision: '0014_bili_delivery_baseline',
          expected_revision: '0015_xhs_creator_notes',
          revision_current: false
        }
      })
    );
    expect(evidence.databaseRevision).toBe('0014_bili_delivery_baseline');
    expect(evidence.expectedDatabaseRevision).toBe('0015_xhs_creator_notes');
    expect(evidence.databaseRevisionStatus).toBe('fail');
  });

  it('never renders malformed backend values or promotes inconsistent provenance', () => {
    const evidence = deploymentEvidence(
      report({
        build_manifest: {
          status: 'fail',
          present: true,
          source_revision: 'DO_NOT_RENDER_PRIVATE_REVISION',
          source_revision_status: 'pass',
          facts: {}
        },
        database: {
          ok: false,
          revision: 'DO_NOT_RENDER_PRIVATE_MIGRATION',
          expected_revision: 'DO_NOT_RENDER_PRIVATE_EXPECTED',
          revision_current: true
        },
        continuations: { bili_delay_seconds: 1, xhs_delay_seconds: Number.MAX_SAFE_INTEGER }
      })
    );
    expect(evidence).toEqual({
      sourceRevision: '无效',
      sourceRevisionStatus: 'fail',
      databaseRevision: '未识别',
      expectedDatabaseRevision: '未识别',
      databaseRevisionStatus: 'fail',
      biliContinuation: '不可用',
      xhsContinuation: '不可用'
    });
    expect(JSON.stringify(evidence)).not.toContain('DO_NOT_RENDER');
  });

  it('renders absent legacy evidence as not run without inventing values', () => {
    expect(deploymentEvidence(null)).toEqual({
      sourceRevision: '未记录',
      sourceRevisionStatus: 'not_run',
      databaseRevision: '未识别',
      expectedDatabaseRevision: '未识别',
      databaseRevisionStatus: 'not_run',
      biliContinuation: '不可用',
      xhsContinuation: '不可用'
    });
  });

  it('accepts a legacy response without the additive provenance and continuation fields', () => {
    const legacy = report();
    delete legacy.build_manifest.source_revision;
    delete legacy.build_manifest.source_revision_status;
    delete legacy.continuations;

    expect(deploymentEvidence(legacy)).toMatchObject({
      sourceRevision: '未记录',
      sourceRevisionStatus: 'not_run',
      biliContinuation: '不可用',
      xhsContinuation: '不可用'
    });
  });
});
