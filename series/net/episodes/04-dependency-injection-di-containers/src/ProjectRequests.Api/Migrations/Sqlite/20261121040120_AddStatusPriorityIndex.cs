using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace ProjectRequests.Api.Migrations.Sqlite
{
    /// <inheritdoc />
    public partial class AddStatusPriorityIndex : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateIndex(
                name: "IX_ProjectRequests_Status_Priority",
                table: "ProjectRequests",
                columns: new[] { "Status", "Priority" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_ProjectRequests_Status_Priority",
                table: "ProjectRequests");
        }
    }
}
