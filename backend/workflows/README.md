# Custom ComfyUI workflows (optional)

The engine builds standard workflows in code (`app/providers/comfyui.py`). To use your own graph
(for example FLUX.2 Klein, a GGUF loader for 8 GB cards, an IP-Adapter for stronger character
consistency, or a different Wan variant):

1. Build and test the graph in ComfyUI.
2. Menu → **Export (API)** / "Save (API format)".
3. Save it here with one of these names:

| File | Used for | Placeholders you can use |
|---|---|---|
| `image.json` | text-to-image | `{{prompt}}` `{{negative}}` `{{width}}` `{{height}}` `{{seed}}` |
| `image_img2img.json` | image from a character reference | same + `{{init_image}}` `{{denoise}}` |
| `wan_i2v.json` | image-to-video | `{{image}}` `{{prompt}}` `{{negative}}` `{{width}}` `{{height}}` `{{length}}` `{{seed}}` `{{fps}}` |
| `music.json` | background music | `{{tags}}` `{{seconds}}` `{{seed}}` |

Put a placeholder in quotes where a value goes, e.g. `"seed": "{{seed}}"` or `"text": "{{prompt}}"`.
Numbers are inserted as numbers and text as properly escaped strings.
The graph must contain a save node (SaveImage / SaveVideo / SaveAudio) so the engine can download the result.
