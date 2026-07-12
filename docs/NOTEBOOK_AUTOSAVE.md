# Notebook Autosave

Mundi notebooks support both manual Save and debounced autosave.

Behavior:
- Edits update local rich-document state immediately.
- Autosave is debounced to avoid saving on every keystroke.
- Manual Save remains visible.
- The client sends the current document version.
- The backend rejects stale saves with a conflict response.
- Recoverable failures preserve local edits.
- Leaving an experiment with unsaved changes prompts the user.

Save states shown in the UI include Saving, Saved/autosaved, and Error/conflict messages.
