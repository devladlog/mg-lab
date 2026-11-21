-- 04-should-fail.sql - every batch here must be REJECTED by a constraint. Run them one at a time.
-- tsql_runner.py --constraints runs each batch, expects an error, and checks that nothing changed.

-- 1. The same email twice (UNIQUE): one customer, one row.
INSERT INTO Training.Customer (Email, FullName, CompanyId)
VALUES (N'alex.demo@contoso.example', N'Alex Duplicate', 2);
GO
-- 2. A customer for a company that doesn't exist (FOREIGN KEY).
INSERT INTO Training.Customer (Email, FullName, CompanyId)
VALUES (N'new.person@unknown.example', N'New Person', 99);
GO
-- 3. A booking line for a course that doesn't exist (FOREIGN KEY).
INSERT INTO Training.BookingLine (BookingRef, CourseCode, PricePaid)
VALUES ('B1002', 'XX999', 100.00);
GO
-- 4. The same course twice in one booking (composite PRIMARY KEY).
INSERT INTO Training.BookingLine (BookingRef, CourseCode, PricePaid)
VALUES ('B1001', 'SQL101', 450.00);
GO
-- 5. A negative price (CHECK).
INSERT INTO Training.BookingLine (BookingRef, CourseCode, PricePaid)
VALUES ('B1002', 'SQL101', -10.00);
GO
-- 6. Deleting a course that has bookings (FOREIGN KEY, default NO ACTION).
DELETE FROM Training.Course WHERE CourseCode = 'SQL101';
GO
