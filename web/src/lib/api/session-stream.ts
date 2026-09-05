/** EventSource cannot expose HTTP status: close it, check the session once, then fall back. */
export class SessionStreamRecovery {
  private pending: Promise<void> | null = null;
  private disposed = false;

  constructor(
    private checkSession: () => Promise<boolean>,
    private fallback: () => void
  ) {}

  recover(close: () => void): Promise<void> {
    close();
    if (this.disposed) return Promise.resolve();
    if (this.pending) return this.pending;
    const pending = (async (): Promise<void> => {
      try {
        if ((await this.checkSession()) && !this.disposed) this.fallback();
      } catch {
        /* Unconfirmed authority never enables polling or reconnect. */
      }
    })();
    this.pending = pending;
    void pending.finally(() => {
      if (this.pending === pending) this.pending = null;
    });
    return pending;
  }

  dispose(): void {
    this.disposed = true;
  }
}
