using System;
using Microsoft.Xrm.Sdk;
using Xunit;
using static MGLab.Plugins.ProjectRequestRules;

namespace MGLab.Plugins.Tests
{
    public class ProjectRequestValidationPluginTests
    {
        private const int PriorityLow = 105000000;
        private const int StatusNew = 105000000;

        private static Entity Request(Action<Entity> set = null)
        {
            var e = new Entity("mgl_projectrequest", Guid.NewGuid());
            set?.Invoke(e);
            return e;
        }

        private static void Run(PluginTestContext ctx, string message, Entity target, Entity preImage = null) =>
            new ProjectRequestValidationPlugin().Execute(ctx.Build(message, target, preImage));

        [Fact]
        public void Create_with_past_due_date_is_blocked()
        {
            var target = Request(e => e[DueDate] = DateTime.UtcNow.Date.AddDays(-1));
            var ex = Assert.Throws<InvalidPluginExecutionException>(() => Run(new PluginTestContext(), "Create", target));
            Assert.StartsWith("Due date can't be in the past", ex.Message);
        }

        [Fact]
        public void Rules_use_the_injected_date()
        {
            var target = new Entity("mgl_projectrequest") { [DueDate] = new DateTime(2026, 12, 1) };
            ProjectRequestRules.Apply(target, null, new Moq.Mock<ITracingService>().Object, new DateTime(2026, 11, 30)); // no exception
            Assert.Throws<InvalidPluginExecutionException>(() =>
                ProjectRequestRules.Apply(target, null, new Moq.Mock<ITracingService>().Object, new DateTime(2026, 12, 2)));
        }

        [Fact]
        public void Create_with_big_budget_sets_priority_high()
        {
            var ctx = new PluginTestContext();
            var target = Request(e => { e[Budget] = new Money(75000); e[Priority] = new OptionSetValue(PriorityLow); });

            Run(ctx, "Create", target);

            Assert.Equal(PriorityHigh, target.GetAttributeValue<OptionSetValue>(Priority).Value);
            Assert.Contains(ctx.Traces, t => t.Contains("priority set to High"));
        }

        [Fact]
        public void Create_with_small_budget_keeps_priority()
        {
            var target = Request(e => { e[Budget] = new Money(12000); e[Priority] = new OptionSetValue(PriorityLow); });
            Run(new PluginTestContext(), "Create", target);
            Assert.Equal(PriorityLow, target.GetAttributeValue<OptionSetValue>(Priority).Value);
        }

        [Fact]
        public void Approving_without_department_is_blocked()
        {
            var target = Request(e => e[Status] = new OptionSetValue(StatusApproved));
            var pre = Request(e => e[Status] = new OptionSetValue(StatusNew));

            var ex = Assert.Throws<InvalidPluginExecutionException>(() => Run(new PluginTestContext(), "Update", target, pre));
            Assert.Contains("department", ex.Message);
        }

        [Fact]
        public void Approving_uses_department_from_pre_image()
        {
            var target = Request(e => e[Status] = new OptionSetValue(StatusApproved));
            var pre = Request(e => e[Department] = new EntityReference("mgl_department", Guid.NewGuid()));

            Run(new PluginTestContext(), "Update", target, pre); // no exception
        }

        [Fact]
        public void Update_raising_budget_uses_pre_image_priority()
        {
            var target = Request(e => e[Budget] = new Money(60000));
            var pre = Request(e => { e[Budget] = new Money(1000); e[Priority] = new OptionSetValue(PriorityHigh); });

            Run(new PluginTestContext(), "Update", target, pre);

            Assert.False(target.Contains(Priority)); // already High: nothing extra to write
        }

        [Fact]
        public void Other_tables_are_ignored()
        {
            var target = new Entity("account", Guid.NewGuid()) { [DueDate] = new DateTime(2000, 1, 1) };
            Run(new PluginTestContext(), "Create", target); // no exception
        }

        [Fact]
        public void Unexpected_errors_are_wrapped_and_traced()
        {
            var ctx = new PluginTestContext { BrokenPreImages = true }; // simulates a platform/config problem
            var target = Request(e => e[Status] = new OptionSetValue(StatusApproved));

            var ex = Assert.Throws<InvalidPluginExecutionException>(() => Run(ctx, "Update", target));

            Assert.Contains("See the plug-in trace log", ex.Message);
            Assert.IsType<NullReferenceException>(ex.InnerException);
            Assert.Contains(ctx.Traces, t => t.StartsWith("Unexpected error"));
        }
    }
}
