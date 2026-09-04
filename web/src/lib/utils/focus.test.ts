import { describe, expect, it } from 'vitest';

import { trappedFocusTarget } from './focus';

describe('modal focus trapping', () => {
  it('moves focus into the modal when focus starts outside', () => {
    expect(trappedFocusTarget(-1, 3, false)).toBe(0);
    expect(trappedFocusTarget(-1, 3, true)).toBe(2);
  });

  it('wraps focus at both ends and leaves interior movement to the browser', () => {
    expect(trappedFocusTarget(0, 3, true)).toBe(2);
    expect(trappedFocusTarget(2, 3, false)).toBe(0);
    expect(trappedFocusTarget(1, 3, false)).toBeNull();
    expect(trappedFocusTarget(1, 3, true)).toBeNull();
  });

  it('has no target when a modal contains no focusable controls', () => {
    expect(trappedFocusTarget(-1, 0, false)).toBeNull();
  });
});
