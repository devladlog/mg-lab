-- q04: gaps and islands - streaks of consecutive login days per user.
-- Consecutive dates minus their row number give the same anchor date, so each streak is one group.
-- DISTINCT first: two logins on the same day would break the trick (see test_islands_need_distinct_days).
WITH days AS (
    SELECT DISTINCT UserName, CAST(LoginAt AS date) AS LoginDate
    FROM App.Logins
),
grouped AS (
    SELECT UserName, LoginDate,
           DATEADD(day, -ROW_NUMBER() OVER (PARTITION BY UserName ORDER BY LoginDate), LoginDate) AS Anchor
    FROM days
)
SELECT UserName,
       MIN(LoginDate) AS StreakStart,
       MAX(LoginDate) AS StreakEnd,
       COUNT(*)       AS Days
FROM grouped
GROUP BY UserName, Anchor
ORDER BY UserName, StreakStart;
