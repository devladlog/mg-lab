# DEVLADLOG SQL #2 — Database Design & Normalization

We take a flat spreadsheet export of course bookings (16 rows of fictional **Contoso Training** data, a repeating
group of courses in each row, customer and company details copied everywhere) and turn it into a
**third-normal-form** SQL Server schema, with evidence at every step:

1. **1NF** — split the repeating group (`SQL101|SQL201`) into one row per booking line: 23 lines, key
   `(BookingRef, CourseCode)`.
2. **Dependencies** — check what the business says determines what (`CourseCode -> Title`, `Company -> City`...)
   against the data. Two dependencies are broken in the export: Contoso is in *Porto* and *Oporto*, and PBI200 is
   *Modeling* and *Modelling*. Normalizing found two data bugs before a single table existed.
3. **3NF** — five tables (`Company`, `Customer`, `Course`, `Booking`, `BookingLine`), the conflicts resolved by an
   explicit, printed rule (latest booking wins), and a **lossless join** check: joining the tables back gives the
   1NF rows again.
4. **T-SQL** — the schema with primary, unique, foreign key and check constraints, indexes on the foreign keys, and a
   view that rebuilds the flat report on demand. Six bad writes are each rejected by the right constraint.

| Path | What it is |
|---|---|
| [`data/bookings_flat.csv`](data/bookings_flat.csv) | The flat export: 16 rows, 10 columns, 4 pipe-separated list columns |
| [`src/normalize.py`](src/normalize.py) | `to_1nf`, `fd_violations`, `candidate_keys`, `check_design`, `resolve`, `normalize`, `rebuild`, `to_tsql`; `python src/normalize.py` prints the design report |
| [`data/normalized/`](data/normalized) | The five 3NF tables as CSV (generated) |
| [`src/sql/00-create-database.sql`](src/sql/00-create-database.sql) | SQL Server only: creates `ContosoTraining` |
| [`src/sql/01-schema.sql`](src/sql/01-schema.sql) | Schema `Training`: 5 tables, constraints, FK indexes, view `vBookingLines`. Re-runnable |
| [`src/sql/02-data.sql`](src/sql/02-data.sql) | Data script **generated** by `normalize.py --write-sql` (parents first, `IDENTITY_INSERT` for the surrogate keys) |
| [`src/sql/q01…q03*.sql`](src/sql) | The rebuilt export (view), list price vs price paid, one `UPDATE` that fixes a city everywhere (rolled back) |
| [`src/sql/04-should-fail.sql`](src/sql/04-should-fail.sql) | Six writes that must be rejected: duplicate email, unknown company, unknown course, duplicate line, negative price, delete a booked course |
| [`src/tsql_runner.py`](src/tsql_runner.py) | Loads the schema, runs the queries vs `expected/`, runs the six rejections; `duckdb` (default) or `sqlserver` |
| [`expected/`](expected) | Expected result of each query |
| [`tests/test_design.py`](tests/test_design.py) | 28 pytest tests |

## Run it locally (no SQL Server needed)

```bash
pip install -r requirements.txt
python3 src/normalize.py                     # the design report (dependencies, conflicts, decisions, lossless: True)
python3 src/tsql_runner.py                   # 3/3 queries match expected/, 6/6 constraint checks behaved on duckdb
python3 -m pytest tests -q                   # 28 passed
```

Locally, the T-SQL runs on **DuckDB** after being parsed with sqlglot's T-SQL dialect and transpiled (Docker isn't
available in the build container). We used DuckDB rather than SQLite because the design uses a schema
(`Training.`), which SQLite doesn't have. Regenerate the data script and CSVs after changing the export:
`python3 src/normalize.py --write-sql src/sql/02-data.sql --write-csv data/normalized` (a test fails if
`02-data.sql` is stale).

## Run it on SQL Server 2022

On the shared lab VM **CON-SQL01** (SQL Server 2022 Developer, `10.50.0.30,1433`, see `series/LAB.md`):

```powershell
# run src/sql/00-create-database.sql against master on 10.50.0.30,1433, then (password typed, never stored):
$pw = Read-Host -AsSecureString 'sa password'
$env:SQL_CONNECTION_STRING = "Server=10.50.0.30,1433;Database=ContosoTraining;UID=sa;PWD=$([Net.NetworkCredential]::new('', $pw).Password);Encrypt=yes;TrustServerCertificate=yes"
python src/tsql_runner.py --engine sqlserver --setup     # expect 3/3 and 6/6 on sqlserver
```

The SQL Server path was exercised here up to the network (driver loaded, connection refused: no server). **The first
real run on SQL Server is part of the demo** ([demo.md](demo.md)).

## What we learned / gotchas

- **Data can suggest a key; it can't prove one.** In 23 rows, 16 column pairs happen to be unique, including
  nonsense like `(CustomerName, ListPrice)`. The key `(BookingRef, CourseCode)` comes from the business rule
  ("a booking lists each course once"), and the composite primary key enforces it (test #4 in `04-should-fail.sql`).
- **Normalizing is where data bugs surface.** The export can hold two cities for one company because the city is
  copied into every row (the *update anomaly*). Splitting it out forces a decision. The script makes that decision
  visible (`decision: ... kept 'Porto' (latest booking), 1 row(s) changed`) instead of silently picking one. In a
  real migration, a person signs those decisions off.
- **Not every repeated value is redundancy.** `ListPrice` depends on the course, so it moves to `Course`.
  `PricePaid` depends on the whole key (this booking, this course: discounts), so it stays on `BookingLine`. Change a
  list price tomorrow and past bookings keep what was actually paid (`q02`: 425.00 of discounts).
- **A FOREIGN KEY doesn't create an index** (Learn says so explicitly). The schema indexes `Customer.CompanyId`,
  `Booking.CustomerId` and `BookingLine.CourseCode`; `BookingLine.BookingRef` is already the first column of the
  primary key.
- **Surrogate or natural key?** `CourseCode` and `BookingRef` are stable business codes, so they are the keys.
  Emails change, so `Customer` gets an `IDENTITY` key and the email is a `UNIQUE` constraint.
- **Denormalize on read, not on write.** The view `Training.vBookingLines` gives reporting the flat shape back; the
  tables keep one fact in one place. Learn's normalization module notes the trade-off: more joins for reads,
  denormalized models for read-heavy warehouses.
- **Engine differences in the local harness** (the `.sql` files are plain T-SQL):
  - DuckDB has no `IDENTITY` and no `SET IDENTITY_INSERT`: the harness turns `IDENTITY(1,1)` into a sequence default
    (starting at 1000) and skips `IDENTITY_INSERT`.
  - sqlglot adds `NULLS FIRST` to key column lists to mimic SQL Server sort order; DuckDB rejects it in a
    `PRIMARY KEY (...)` or `CREATE INDEX`, so the harness removes it there.
  - DuckDB returns a status row for `UPDATE` and `ROLLBACK`; the runner only keeps results of statements that are
    queries.
  - Error messages differ: DuckDB doesn't name the constraint, SQL Server does (for example
    a message of the form `Violation of ... constraint 'UQ_Customer_Email'. Cannot insert duplicate key in object ...`). The demo shows the SQL Server messages.

## References

- [Describe normalization (1NF, 2NF, 3NF, denormalization) — Microsoft Learn training](https://learn.microsoft.com/training/modules/explore-performance-based-design/2-describe-normalization)
- [Primary and foreign key constraints (FKs aren't indexed automatically, NO ACTION)](https://learn.microsoft.com/sql/relational-databases/tables/primary-and-foreign-key-constraints)
- [Unique constraints and check constraints](https://learn.microsoft.com/sql/relational-databases/tables/unique-constraints-and-check-constraints)
- [CREATE TABLE (Transact-SQL)](https://learn.microsoft.com/sql/t-sql/statements/create-table-transact-sql)
- [MSSQL_ENG002627: Violation of ... constraint](https://learn.microsoft.com/sql/relational-databases/replication/mssql-eng002627)
- [Understand star schema: normalization vs denormalization](https://learn.microsoft.com/power-bi/guidance/star-schema#normalization-vs-denormalization)
- [mssql-python driver](https://learn.microsoft.com/sql/connect/python/mssql-python/python-sql-driver-mssql-python)
- [Run SQL Server Linux container images with Docker](https://learn.microsoft.com/sql/linux/install-upgrade/quickstart-install-docker)
- Blog: [Database Design & Normalization — Complete Guide](https://www.devladlog.com/articles/sql/2025-07-20-database-design-normalization-complete-guide-2025/)
