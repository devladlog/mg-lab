If(
    Len(Topic.VendorName) < 2,
    "Tell me the vendor name.",
    If(
        Not(Or(
            Lower(Topic.Category) = "hosting",
            Lower(Topic.Category) = "printing",
            Lower(Topic.Category) = "travel",
            Lower(Topic.Category) = "security",
            Lower(Topic.Category) = "other"
        )),
        "The category must be hosting, printing, travel, security or other.",
        If(
            IsBlank(Topic.EstimatedAnnualCost) || Topic.EstimatedAnnualCost <= 0,
            "The estimated yearly cost must be a positive amount in euros.",
            If(
                Len(Topic.Justification) < 10,
                "Give a short business justification (at least a sentence).",
                ""
            )
        )
    )
)
