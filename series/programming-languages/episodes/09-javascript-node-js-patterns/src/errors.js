/** One problem in one CSV row. Carries the row number and the field, so the message is usable on its own. */
export class RowError extends Error {
  constructor(row, field, message, options) {
    super(`row ${row}: ${field}: ${message}`, options);
    this.name = "RowError";
    this.row = row;
    this.field = field;
  }
}

/** A failed call to the approvals API. `status` is 0 for timeouts and network errors. The original error is `cause`. */
export class ApiError extends Error {
  constructor(message, { status = 0, retryable = false, cause } = {}) {
    super(message, { cause });
    this.name = "ApiError";
    this.status = status;
    this.retryable = retryable;
  }
}
