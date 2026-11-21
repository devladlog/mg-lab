<!-- Fictional Contoso accounts-payable review policy for a demo. -->
# Contoso accounts payable: review queue rules

## Arithmetic mismatches
An invoice whose subtotal plus tax does not equal its total is never approved. Ask the supplier for a corrected
invoice and keep the original in the review queue.

## Low-confidence reads
When a value was read with low confidence, a person compares it with the scanned image before approval. The
assistant may propose the approval; a person confirms it.

## Approval limits
Accounts-payable staff approve invoices up to EUR 5,000.00. Above that, the finance manager approves in the
finance system; the assistant must not approve them.

## New suppliers
The first invoice from a new VAT number needs the supplier record to be verified by procurement before payment.

## Rejected invoices
Rejected invoices (duplicates, wrong customer) are not reopened from the review queue.
