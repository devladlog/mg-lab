const HIGH_FROM = 50_000;
const BOARD_FROM = 250_000;

export function priorityOf(budget) {
  if (budget >= BOARD_FROM) return "Board";
  if (budget >= HIGH_FROM) return "High";
  return "Standard";
}

function totals(lines) {
  const byDepartment = {};
  for (const line of lines) {
    const t = (byDepartment[line.department] ??= { count: 0, budget: 0 });
    t.count++;
    t.budget += line.budget;
  }
  return byDepartment;
}

/**
 * The first version, written the way it usually is: it works, the tests are green, and it is slow.
 * Three habits hide in it: a linear search for duplicates, a deep copy through JSON, and a new
 * number formatter (through toLocaleString) for every row.
 */
export function buildReportSlow(requests) {
  const lines = [];
  const duplicates = [];
  const seen = [];
  for (const request of requests) {
    if (seen.some((s) => s.code === request.code)) {
      duplicates.push(request.code);
      continue;
    }
    seen.push(request);
    const line = JSON.parse(JSON.stringify(request));
    line.budgetText = request.budget.toLocaleString("en-IE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
    line.priority = priorityOf(request.budget);
    lines.push(line);
  }
  return { lines, duplicates, byDepartment: totals(lines) };
}

const euro = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });

/** Same output as buildReportSlow: a Set for duplicates, one shared formatter, no copy through JSON. */
export function buildReportFast(requests) {
  const lines = [];
  const duplicates = [];
  const seen = new Set();
  for (const request of requests) {
    if (seen.has(request.code)) {
      duplicates.push(request.code);
      continue;
    }
    seen.add(request.code);
    lines.push({ ...request, budgetText: euro.format(request.budget), priority: priorityOf(request.budget) });
  }
  return { lines, duplicates, byDepartment: totals(lines) };
}
