-- q02: list price lives on Course, the price actually paid on BookingLine. Both are needed:
-- the discount is the difference, and changing a list price tomorrow mustn't rewrite past bookings.
SELECT c.CourseCode, c.Title,
       COUNT(*)                     AS Lines,
       SUM(c.ListPrice)             AS AtListPrice,
       SUM(bl.PricePaid)            AS Paid,
       SUM(c.ListPrice - bl.PricePaid) AS Discount
FROM Training.BookingLine AS bl
JOIN Training.Course AS c ON c.CourseCode = bl.CourseCode
GROUP BY c.CourseCode, c.Title
ORDER BY c.CourseCode;
