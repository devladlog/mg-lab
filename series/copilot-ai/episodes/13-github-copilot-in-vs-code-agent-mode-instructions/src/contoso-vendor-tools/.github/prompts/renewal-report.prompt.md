---
name: renewal-report-prompt
description: Produce the vendor renewal report for a number of days ahead (Local harness prompt file)
argument-hint: '[days ahead]'
agent: agent
tools: ['execute']
---
Run `python -m vendor_tools.cli --within-days ${input:days:90}` and show the output unchanged.
Then list each vendor with its owner, soonest renewal first. Follow the rules in
[the project instructions](../copilot-instructions.md). Do not change any file.
