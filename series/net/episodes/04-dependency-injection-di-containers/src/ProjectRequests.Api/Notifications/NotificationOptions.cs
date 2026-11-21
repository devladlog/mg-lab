using System.ComponentModel.DataAnnotations;

namespace ProjectRequests.Api.Notifications;

/// <summary>
/// "Notifications" section. Validated with data annotations + <see cref="Validate"/> at startup
/// (ValidateOnStart): a bad setting stops the app on deploy, not at 3 a.m. when the first digest runs.
/// </summary>
public sealed class NotificationOptions : IValidatableObject
{
    public const string Section = "Notifications";

    /// <summary>Key of the <see cref="INotificationChannel"/> to use: "log" or "webhook".</summary>
    [Required, AllowedValues("log", "webhook")]
    public string Channel { get; set; } = "log";

    /// <summary>Required when <see cref="Channel"/> is "webhook". HTTPS only.</summary>
    public Uri? WebhookUrl { get; set; }

    /// <summary>Requests still Submitted after this many days go into the digest (0 = all, for demos).</summary>
    [Range(0, 90)]
    public int StaleAfterDays { get; set; } = 3;

    /// <summary>How often the background worker sends the digest.</summary>
    [Range(typeof(TimeSpan), "00:00:30", "7.00:00:00")]
    public TimeSpan DigestInterval { get; set; } = TimeSpan.FromHours(24);

    public bool DigestEnabled { get; set; } = true;

    public IEnumerable<ValidationResult> Validate(ValidationContext validationContext)
    {
        if (Channel == "webhook" && WebhookUrl is not { IsAbsoluteUri: true, Scheme: "https" })
            yield return new ValidationResult(
                "Notifications:WebhookUrl must be an absolute https URL when Channel is 'webhook'.",
                [nameof(WebhookUrl)]);
    }
}
