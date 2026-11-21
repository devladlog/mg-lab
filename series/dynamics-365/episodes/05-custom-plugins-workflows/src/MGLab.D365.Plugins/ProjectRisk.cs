using System;
using System.Collections.Generic;
using System.Globalization;

namespace MGLab.D365.Plugins
{
    /// <summary>What the rules need to know about one Project Request. No Dataverse types: easy to test.</summary>
    public sealed class RiskInput
    {
        public decimal? Budget { get; set; }
        public DateTime? DueDate { get; set; }
        public bool HasJustification { get; set; }
        public bool HasCustomerAccount { get; set; }
        /// <summary>Other active requests for the same customer account (this record excluded).</summary>
        public int OtherOpenRequests { get; set; }
    }

    public sealed class RiskResult
    {
        public RiskResult(int score, string level, IReadOnlyList<string> reasons)
        {
            Score = score;
            Level = level;
            Reasons = reasons;
        }

        public int Score { get; }
        public string Level { get; }
        public IReadOnlyList<string> Reasons { get; }

        /// <summary>One string for the custom API response (String, not StringArray: see README).</summary>
        public string ReasonsText => Reasons.Count == 0 ? "No risk factors" : string.Join("; ", Reasons);
    }

    /// <summary>
    /// The risk rules for a Project Request. Pure: no service calls, the clock is a parameter.
    /// Used by the custom API plug-in (on demand) and, through the API, by the async plug-in (keeps a column fresh).
    /// </summary>
    public static class ProjectRisk
    {
        public const decimal LargeBudget = 50000m;   // same threshold as the business rule (episode 3) and the BPF branch (episode 4)
        public const int SoonDays = 30;
        public const int CrowdedAccount = 2;
        public const int HighFrom = 70;
        public const int MediumFrom = 40;

        public static RiskResult Assess(RiskInput input, DateTime today)
        {
            if (input == null) throw new ArgumentNullException(nameof(input));
            var reasons = new List<string>();
            var score = 0;

            var large = input.Budget.HasValue && input.Budget.Value >= LargeBudget;
            if (large)
            {
                score += 30;
                reasons.Add($"Budget {Money(input.Budget.Value)} is at or over {Money(LargeBudget)}");
                if (!input.HasJustification)
                {
                    score += 25;
                    reasons.Add("No business justification for a large budget");
                }
            }

            if (!input.DueDate.HasValue)
            {
                score += 10;
                reasons.Add("No due date");
            }
            else
            {
                var days = (input.DueDate.Value.Date - today.Date).Days;
                if (days < 0)
                {
                    score += 30;
                    reasons.Add($"Due date passed {-days} day(s) ago");
                }
                else if (days <= SoonDays)
                {
                    score += 20;
                    reasons.Add($"Due in {days} day(s)");
                }
            }

            if (!input.HasCustomerAccount)
            {
                score += 10;
                reasons.Add("No customer account");
            }
            else if (input.OtherOpenRequests >= CrowdedAccount)
            {
                score += 15;
                reasons.Add($"Account has {input.OtherOpenRequests} other open requests");
            }

            score = Math.Min(score, 100);
            return new RiskResult(score, LevelFor(score), reasons);
        }

        /// <summary>
        /// A Date only column left on the default behavior (User local) stores a picked date as the user's
        /// midnight in UTC (Lisbon in summer: 23:00 the day before). Learn says to avoid that combination.
        /// Episode 1 now creates mgl_duedate with Date only behavior; this defensive read keeps older environments
        /// correct: take the nearest UTC midnight, right for any user between UTC-12 and UTC+12, a no-op for real
        /// Date only values.
        /// </summary>
        public static DateTime? NearestDate(DateTime? stored) =>
            stored.HasValue ? stored.Value.AddHours(12).Date : (DateTime?)null;

        public static string LevelFor(int score) =>
            score >= HighFrom ? "High" : score >= MediumFrom ? "Medium" : "Low";

        private static string Money(decimal value) =>
            value.ToString("#,##0", CultureInfo.InvariantCulture);
    }
}
