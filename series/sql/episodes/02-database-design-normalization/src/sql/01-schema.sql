-- 01-schema.sql - the third-normal-form design for Contoso Training bookings.
-- Every non-key column depends on the key, the whole key, and nothing but the key:
--   Company(CompanyId)    -> name, city            Customer(CustomerId) -> email, name, company
--   Course(CourseCode)    -> title, list price     Booking(BookingRef)  -> date, customer
--   BookingLine(BookingRef, CourseCode) -> price paid
-- Re-runnable: drops and recreates everything in the Training schema.

DROP VIEW IF EXISTS Training.vBookingLines;
DROP TABLE IF EXISTS Training.BookingLine;
DROP TABLE IF EXISTS Training.Booking;
DROP TABLE IF EXISTS Training.Customer;
DROP TABLE IF EXISTS Training.Company;
DROP TABLE IF EXISTS Training.Course;
DROP SCHEMA IF EXISTS Training;
GO
CREATE SCHEMA Training;
GO

CREATE TABLE Training.Company (
    CompanyId   int IDENTITY(1,1) NOT NULL CONSTRAINT PK_Company PRIMARY KEY,
    CompanyName nvarchar(100)     NOT NULL CONSTRAINT UQ_Company_Name UNIQUE,
    City        nvarchar(60)      NOT NULL
);

CREATE TABLE Training.Customer (
    CustomerId int IDENTITY(1,1) NOT NULL CONSTRAINT PK_Customer PRIMARY KEY,
    Email      nvarchar(254)     NOT NULL CONSTRAINT UQ_Customer_Email UNIQUE,   -- natural key, but it can change
    FullName   nvarchar(100)     NOT NULL,
    CompanyId  int               NOT NULL CONSTRAINT FK_Customer_Company REFERENCES Training.Company (CompanyId)
);

CREATE TABLE Training.Course (
    CourseCode varchar(10)   NOT NULL CONSTRAINT PK_Course PRIMARY KEY,         -- stable business code
    Title      nvarchar(100) NOT NULL,
    ListPrice  decimal(10,2) NOT NULL CONSTRAINT CK_Course_ListPrice CHECK (ListPrice >= 0)
);

CREATE TABLE Training.Booking (
    BookingRef  varchar(10) NOT NULL CONSTRAINT PK_Booking PRIMARY KEY,
    BookingDate date        NOT NULL,
    CustomerId  int         NOT NULL CONSTRAINT FK_Booking_Customer REFERENCES Training.Customer (CustomerId)
);

CREATE TABLE Training.BookingLine (
    BookingRef varchar(10)   NOT NULL CONSTRAINT FK_BookingLine_Booking REFERENCES Training.Booking (BookingRef),
    CourseCode varchar(10)   NOT NULL CONSTRAINT FK_BookingLine_Course REFERENCES Training.Course (CourseCode),
    PricePaid  decimal(10,2) NOT NULL CONSTRAINT CK_BookingLine_PricePaid CHECK (PricePaid >= 0),
    CONSTRAINT PK_BookingLine PRIMARY KEY (BookingRef, CourseCode)
);

-- A FOREIGN KEY doesn't create an index. BookingLine(BookingRef) is covered by the primary key's first column;
-- the other foreign keys get their own.
CREATE INDEX IX_Customer_CompanyId     ON Training.Customer (CompanyId);
CREATE INDEX IX_Booking_CustomerId     ON Training.Booking (CustomerId);
CREATE INDEX IX_BookingLine_CourseCode ON Training.BookingLine (CourseCode);
GO

-- The flat report, rebuilt on demand: denormalize when you read, not when you store.
CREATE VIEW Training.vBookingLines
AS
SELECT b.BookingRef, b.BookingDate,
       cu.Email AS CustomerEmail, cu.FullName AS CustomerName,
       co.CompanyName AS Company, co.City AS CompanyCity,
       bl.CourseCode, c.Title AS CourseTitle, c.ListPrice, bl.PricePaid
FROM Training.BookingLine AS bl
JOIN Training.Booking  AS b  ON b.BookingRef  = bl.BookingRef
JOIN Training.Customer AS cu ON cu.CustomerId = b.CustomerId
JOIN Training.Company  AS co ON co.CompanyId  = cu.CompanyId
JOIN Training.Course   AS c  ON c.CourseCode  = bl.CourseCode;
GO
