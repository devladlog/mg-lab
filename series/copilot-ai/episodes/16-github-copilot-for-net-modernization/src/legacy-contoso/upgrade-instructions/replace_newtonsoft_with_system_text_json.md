# Replace Newtonsoft.Json with System.Text.Json

## Detect
- If a project references `Newtonsoft.Json` (in `packages.config` or as a `PackageReference`) and calls `JsonConvert`, then migrate that project with the steps below.
- If a project only references `Newtonsoft.Json` through another package, then leave it alone and report it.

## Steps
1. If `JsonConvert.SerializeObject` or `DeserializeObject` is called with `JsonSerializerSettings`, then create one `static readonly JsonSerializerOptions` built with `JsonSerializerDefaults.Web`. Do not use the parameterless options: they are case-sensitive, do not read numbers from strings and write PascalCase names.
2. If the settings use `CamelCasePropertyNamesContractResolver`, then `JsonSerializerDefaults.Web` already gives camelCase names.
3. If the settings use `NullValueHandling.Ignore`, then set `DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull`.
4. If the settings add `StringEnumConverter`, then add `new JsonStringEnumConverter()` to `Converters`.
5. If `DeserializeObject` can receive an empty or whitespace string, then return `null` before calling `JsonSerializer.Deserialize`. Newtonsoft returns null for empty input; System.Text.Json throws.
6. Replace the `using Newtonsoft.Json...` lines with `using System.Text.Json;` and `using System.Text.Json.Serialization;`.
7. Remove the `Newtonsoft.Json` package reference, restore, build, and run the tests of the project.

## Example (from a real local edit of `QuoteSerializer.cs`)
```diff
-using Newtonsoft.Json;
-using Newtonsoft.Json.Converters;
-using Newtonsoft.Json.Serialization;
+using System.Text.Json;
+using System.Text.Json.Serialization;
 
-        private static readonly JsonSerializerSettings Settings = new JsonSerializerSettings
-        {
-            ContractResolver = new CamelCasePropertyNamesContractResolver(),
-            NullValueHandling = NullValueHandling.Ignore,
-            Converters = { new StringEnumConverter() }
-        };
+    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
+    {
+        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
+        Converters = { new JsonStringEnumConverter() }
+    };
 
-            return JsonConvert.DeserializeObject<Quote>(json, Settings);
+        if (string.IsNullOrWhiteSpace(json)) return null;
+        return JsonSerializer.Deserialize<Quote>(json, Options);
```
