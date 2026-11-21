If(
    Topic.EstimatedAnnualCost >= 25000,
    "Finance director, after a security review",
    If(
        Topic.EstimatedAnnualCost >= 5000,
        "Procurement manager",
        "Team lead"
    )
)
