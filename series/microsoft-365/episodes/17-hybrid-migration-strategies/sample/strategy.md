# Migration plan

## Migration path

Source **Exchange2007**, 800 mailboxes, pace AllAtOnce, users managed on-premises: False -> **Staged**.

- 800 mailboxes is 150 or more: use staged migration, which moves a limited number of users at a time.
- Note: Exchange 2003 and 2007 are out of support (April 2014 and April 2017 per Learn).
- Note: Staged and hybrid migrations require directory synchronization first (run the directory check in this episode).
- Note: A staged migration CSV holds at most 2,000 rows; use one CSV per batch.


