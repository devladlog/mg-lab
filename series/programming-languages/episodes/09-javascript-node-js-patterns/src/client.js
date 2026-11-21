import { setTimeout as sleep } from "node:timers/promises";
import { ApiError } from "#src/errors.js";

const RETRYABLE_STATUS = new Set([429, 502, 503, 504]);

/**
 * Approvals client on the built-in fetch.
 * Every call has a deadline (AbortSignal.timeout) and also stops when the caller's signal aborts (AbortSignal.any).
 * Transient failures are retried with exponential backoff and jitter; a caller abort is never retried.
 */
export class ApprovalsClient {
  /** @param {string} baseUrl */
  constructor(baseUrl, { timeoutMs = 2000, retries = 2, baseDelayMs = 100, random = Math.random, wait = sleep } = {}) {
    this.baseUrl = baseUrl;
    this.timeoutMs = timeoutMs;
    this.retries = retries;
    this.baseDelayMs = baseDelayMs;
    this.random = random;
    this.wait = wait;
  }

  async approversFor(department, { signal } = {}) {
    for (let attempt = 0; ; attempt++) {
      try {
        return await this.#once(department, signal);
      } catch (error) {
        const final = !(error instanceof ApiError) || !error.retryable || attempt >= this.retries;
        if (final) throw error;
        // Full jitter: a random delay up to base * 2^attempt, so a burst of retries does not arrive in lock-step.
        await this.wait(Math.floor(this.random() * this.baseDelayMs * 2 ** attempt), { signal });
      }
    }
  }

  async #once(department, callerSignal) {
    const deadline = AbortSignal.timeout(this.timeoutMs);
    const signal = callerSignal ? AbortSignal.any([callerSignal, deadline]) : deadline;
    let response;
    try {
      response = await fetch(`${this.baseUrl}/approvers/${encodeURIComponent(department)}`, { signal });
    } catch (error) {
      if (callerSignal?.aborted) throw error;                         // the caller cancelled: not our failure
      if (deadline.aborted) throw new ApiError(`timeout after ${this.timeoutMs} ms`, { retryable: true, cause: error });
      // fetch hides the real reason in error.cause (ECONNREFUSED, ECONNRESET, ...)
      const reason = error.cause?.code ?? error.message;
      throw new ApiError(`network error: ${reason}`, { retryable: true, cause: error });
    }
    if (response.ok) return await response.json();
    throw new ApiError(`approvals API answered ${response.status}`, { status: response.status, retryable: RETRYABLE_STATUS.has(response.status) });
  }
}
