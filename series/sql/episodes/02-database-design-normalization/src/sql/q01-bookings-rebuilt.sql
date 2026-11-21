-- q01: the flat export, rebuilt from the five tables. Same 23 lines as the 1NF step (after the two fixes).
SELECT BookingRef, BookingDate, CustomerEmail, CustomerName, Company, CompanyCity,
       CourseCode, CourseTitle, ListPrice, PricePaid
FROM Training.vBookingLines
ORDER BY BookingRef, CourseCode;
