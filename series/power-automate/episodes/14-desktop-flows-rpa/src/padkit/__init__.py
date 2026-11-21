"""padkit: check a desktop flow (its copied text and its input/output contract) against the cloud flow that calls it.

What can be checked without Power Automate for desktop: that the cloud flow passes exactly the inputs the desktop flow
declares, reads only outputs it declares, that every output is assigned, and the few safety rules Learn documents.
It does NOT run the flow: UI automation needs a Windows session (see demo.md).
"""
