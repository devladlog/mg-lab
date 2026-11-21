const DEPARTMENTS = ["IT", "Operations", "Marketing", "HR", "Sales"];

/** Small seeded generator (mulberry32): the same seed gives the same data on every machine. */
export function seeded(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * `count` fictional Contoso project requests. About 2 % repeat an earlier code (the duplicates the report must find).
 * Budgets are whole euros, 1,000 to 400,000.
 */
export function generateRequests(count, seed = 2026) {
  const random = seeded(seed);
  const requests = [];
  for (let i = 0; i < count; i++) {
    const isDuplicate = i > 0 && random() < 0.02;
    const n = isDuplicate ? Math.floor(random() * i) : i;
    requests.push({
      code: `PR-${String(2026 + (n % 3))}-${String(n).padStart(6, "0")}`,
      title: `Request ${n}`,
      department: DEPARTMENTS[Math.floor(random() * DEPARTMENTS.length)],
      budget: 1000 + Math.floor(random() * 399_000),
      submitted: `2026-${String(1 + Math.floor(random() * 12)).padStart(2, "0")}-${String(1 + Math.floor(random() * 28)).padStart(2, "0")}`,
    });
  }
  return requests;
}
