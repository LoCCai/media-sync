import type { Job } from '$lib/types/api';
import { isSchedulerJobId } from '../utils/scheduler-job-diagnostics';
import { LatestRequestGate } from './client';

export const JOB_DETAIL_UNAVAILABLE = '暂时无法确认本 Job 的详情，请刷新任务列表后重试。';

type JobDetailResult =
  | { kind: 'superseded' }
  | { kind: 'failed'; message: string }
  | { kind: 'fulfilled'; job: Job };

/** Scope a Job detail read to its exact requested identity and current UI lifetime. */
export class SchedulerJobDetailReader {
  private readonly gate = new LatestRequestGate();

  constructor(private readonly readJob: (id: string, signal: AbortSignal) => Promise<Job>) {}

  async read(id: string): Promise<JobDetailResult> {
    if (!isSchedulerJobId(id)) {
      this.invalidate();
      return { kind: 'failed', message: JOB_DETAIL_UNAVAILABLE };
    }
    const result = await this.gate.run((signal) => this.readJob(id, signal));
    if (result.status === 'superseded') return { kind: 'superseded' };
    if (
      result.status === 'rejected' ||
      !result.value ||
      typeof result.value !== 'object' ||
      Array.isArray(result.value) ||
      result.value.job_id !== id
    ) {
      return { kind: 'failed', message: JOB_DETAIL_UNAVAILABLE };
    }
    return { kind: 'fulfilled', job: result.value };
  }

  invalidate(): void {
    this.gate.cancel();
  }
}
