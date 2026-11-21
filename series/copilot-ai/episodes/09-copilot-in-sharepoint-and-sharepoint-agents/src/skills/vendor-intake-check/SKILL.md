---
name: vendor-intake-check
description: "Checks vendor requests in this library against the Contoso Vendor Onboarding Policy and logs problems in the Vendor intake issues list. Use when someone asks to check, review or validate a vendor request."
---

# Vendor intake check

Use this skill on the vendor request documents the user selected in the library (or, if nothing is selected, on the
documents in the current folder).

For each document:

1. Find the four things the policy requires in a request: the vendor name, a category (hosting, printing, travel,
   security or other), the estimated yearly cost in euros, and a short business justification.
2. Work out the approver from the estimated yearly cost:
   - below 5,000 euros: team lead
   - 5,000 to 24,999 euros: procurement manager
   - 25,000 euros and above: finance director, after a security review
3. If the request is split into smaller parts to stay below a tier, treat it as one request and say so.
4. A request without a justification is returned to the requester: say that the 10 working day clock has not started.

Report the result as a short table: document, what is missing, approver. Then add one row for every document with a
problem to the list named Vendor intake issues. Create the list with the columns Document, Problem and Approver if it
does not exist. Do not change the documents, and do not invent values that are not in the document.
