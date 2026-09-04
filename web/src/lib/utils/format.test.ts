import { describe, expect, it } from 'vitest';

import { formatBytes, intervalLabel, shortId, statusLabel, statusTone } from './format';

describe('console formatters', () => {
  it('formats stable status labels and tones', () => {
    expect(statusLabel('failed_retryable')).toBe('可重试');
    expect(statusTone('failed_retryable')).toBe('danger');
    expect(statusTone('authenticated')).toBe('success');
  });

  it('formats bounded identifiers, intervals, and byte counts', () => {
    expect(shortId('12345678-1234-1234-1234-123456789012')).toBe('12345678…');
    expect(intervalLabel(21_600)).toBe('6 小时');
    expect(formatBytes(1_048_576)).toBe('1.00 MB');
  });
});
