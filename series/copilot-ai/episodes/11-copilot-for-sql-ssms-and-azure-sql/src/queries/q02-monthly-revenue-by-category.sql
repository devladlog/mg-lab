-- q02: "Revenue per month and product category" (the Reporting view the Copilot user may read).
SELECT MonthStart, Category, Revenue
FROM Reporting.MonthlyRevenue
ORDER BY MonthStart, Category;
