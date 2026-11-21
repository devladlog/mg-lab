using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.AspNetCore.Mvc;
using ProjectRequests.Perf.Api.Requests;

namespace ProjectRequests.Perf.Api.Json;

/// <summary>
/// Source-generated serializer metadata: no reflection at run time, less allocation, trimming/AOT-friendly.
/// The Web defaults (camelCase, case-insensitive) match what ASP.NET Core uses; enums go out as strings.
/// </summary>
[JsonSourceGenerationOptions(JsonSerializerDefaults.Web, UseStringEnumConverter = true)]
[JsonSerializable(typeof(RequestDto))]
[JsonSerializable(typeof(List<RequestDto>))]
[JsonSerializable(typeof(PagedResult<RequestDto>))]
[JsonSerializable(typeof(SummaryDto))]
[JsonSerializable(typeof(CreateRequest))]
[JsonSerializable(typeof(ProblemDetails))]
[JsonSerializable(typeof(HttpValidationProblemDetails))]
public partial class AppJsonContext : JsonSerializerContext;
