# Future Freeform Canvas

Mundi notebooks currently use an infinite vertical rich document. Images and files live in the document flow as typed embeds, not as arbitrary objects on a two-dimensional canvas.

Future freeform mode should be implemented as a separate notebook block or notebook mode so spatial coordinates do not leak into ordinary Quill text operations.

## Object Model

Future canvas objects should support:

- `object_id`
- `object_type`
- `attachment_id`
- `x`
- `y`
- `width`
- `height`
- `rotation`
- `z_index`
- `locked`
- `caption`
- `created_at`
- `updated_at`

## Interaction Modes

- Write mode: normal notebook editing and inline embeds.
- Arrange mode: move, resize, align, lock, and layer canvas objects.
- Draw mode: ink, Apple Pencil, shapes, arrows, lasso selection, and annotations.

The current image controls intentionally stay within the vertical document flow. They support resizing, alignment, captions, alt text, preview, removal from the document, and Move Up / Move Down relocation, but they do not claim free-positioned placement.
