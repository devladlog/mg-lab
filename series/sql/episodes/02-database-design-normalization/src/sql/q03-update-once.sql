-- q03: the update anomaly is gone. Contoso moves to Matosinhos: ONE row changes,
-- and every booking line of every Contoso customer shows the new city.
-- Wrapped in a transaction that is rolled back, so the demo leaves the data as loaded.
BEGIN TRANSACTION;

UPDATE Training.Company SET City = N'Matosinhos' WHERE CompanyName = N'Contoso Ltd';

SELECT Company, CompanyCity,
       COUNT(DISTINCT BookingRef) AS Bookings,
       COUNT(*)                   AS BookingLines
FROM Training.vBookingLines
GROUP BY Company, CompanyCity
ORDER BY Company;

ROLLBACK TRANSACTION;
