using System;
using Microsoft.Xrm.Sdk;

namespace MGLab.Plugins
{
    /// <summary>
    /// Pure business rules for mgl_projectrequest. No Dataverse calls, so every rule is unit-testable.
    /// </summary>
    public static class ProjectRequestRules
    {
        public const string Budget = "mgl_budget";
        public const string Priority = "mgl_priority";
        public const string Status = "mgl_requeststatus";
        public const string Department = "mgl_departmentid";
        public const string DueDate = "mgl_duedate";

        public const int PriorityHigh = 105000002;
        public const int StatusApproved = 105000002;
        public const decimal HighBudgetThreshold = 50000m;

        /// <summary>
        /// Applies the rules to <paramref name="target"/> (the columns being saved).
        /// <paramref name="preImage"/> holds the current row on Update, null on Create.
        /// <paramref name="today"/> is injected so tests don't depend on the clock.
        /// Note: "budget can't be negative" is NOT here — the column's minimum value already enforces it.
        /// </summary>
        public static void Apply(Entity target, Entity preImage, ITracingService tracing, DateTime today)
        {
            // Rule 1 — a due date being set can't be in the past.
            if (target.Contains(DueDate) && target[DueDate] is DateTime due && due.Date < today.Date)
                throw new InvalidPluginExecutionException($"Due date can't be in the past ({due:yyyy-MM-dd}).");

            var budget = Read<Money>(target, preImage, Budget)?.Value;

            // Rule 2 — big budgets are always High priority.
            if (budget >= HighBudgetThreshold && Read<OptionSetValue>(target, preImage, Priority)?.Value != PriorityHigh)
            {
                target[Priority] = new OptionSetValue(PriorityHigh);
                tracing.Trace($"Budget {budget:N0} >= {HighBudgetThreshold:N0}: priority set to High.");
            }

            // Rule 3 — only requests with a department can be approved.
            var status = Read<OptionSetValue>(target, preImage, Status)?.Value;
            if (status == StatusApproved && Read<EntityReference>(target, preImage, Department) == null)
                throw new InvalidPluginExecutionException("A request needs a department before it can be approved.");
        }

        /// <summary>Value being saved wins; otherwise the current value from the pre-image.</summary>
        private static T Read<T>(Entity target, Entity preImage, string column) where T : class
        {
            if (target.Contains(column)) return target[column] as T;
            return preImage != null && preImage.Contains(column) ? preImage[column] as T : null;
        }
    }
}
