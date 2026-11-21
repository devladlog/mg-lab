---
name: renewal-report
description: Produce the Contoso vendor renewal report for a number of days ahead and list the vendors that need action. Use when asked for the renewal report or upcoming renewals.
argument-hint: '[days ahead]'
disable-model-invocation: true
---

# Renewal report

1. Run `python -m vendor_tools.cli --within-days <days>`; use 90 when no number is given.
2. Show the output unchanged in a code block.
3. Below it, list each vendor and its owner, soonest renewal first.
4. State which command you ran. Do not change any file.
