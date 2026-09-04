/** Return the focus target needed to keep Tab navigation inside a modal. */
export function trappedFocusTarget(
  currentIndex: number,
  focusableCount: number,
  backwards: boolean
): number | null {
  if (focusableCount <= 0) return null;
  if (currentIndex < 0) return backwards ? focusableCount - 1 : 0;
  if (backwards && currentIndex === 0) return focusableCount - 1;
  if (!backwards && currentIndex === focusableCount - 1) return 0;
  return null;
}
