# Legacy Notebook Removal

The legacy experiment notebook body used plain text and Markdown-style updates. That path is removed from the experiment workspace so serialized Quill Delta JSON cannot be rendered as prose and images cannot be routed through a text-only editor.

Removed active UI paths:

- The temporary development `Insert Test Image` button.
- Visible controller/hash/raw-Delta diagnostics.
- The Voice tool's secondary transcript TextField that inserted text into notebook content outside the active Quill controller.

Remaining TextField usage is limited to non-notebook controls such as experiment title editing, attachment metadata, and link dialogs.

Tool panels may attach resources or update structured experiment data, but they do not maintain a separate editable notebook body. User-authored notes should be entered in the main rich notebook editor.
