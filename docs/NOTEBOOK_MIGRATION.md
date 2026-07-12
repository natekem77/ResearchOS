# Notebook Migration

Existing markdown/plain-text experiment notebooks are preserved.

Migration behavior:
- Existing `content` remains available for backward compatibility.
- The backend exposes `structured_content` as Quill Delta JSON.
- Markdown headings and bullet lists are converted conservatively.
- Links are preserved as link attributes when they appear as URL spans.
- Original source is preserved through `original_format`, `original_content`, and migration metadata.
- Migration is idempotent: reading a notebook repeatedly should not duplicate headings or rewrite content.

Unknown or unsupported formatting remains plain text rather than being guessed.
