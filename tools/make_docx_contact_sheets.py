from pathlib import Path
import math

from PIL import Image, ImageDraw


render_dir = Path("docs/spec_render")
pages = sorted(render_dir.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[1]))
thumbs = []
target_width = 360
row_height = 0

for page in pages:
    image = Image.open(page).convert("RGB")
    target_height = int(image.height * target_width / image.width)
    image = image.resize((target_width, target_height))
    canvas = Image.new("RGB", (target_width, target_height + 28), "white")
    canvas.paste(image, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, target_height + 6), page.stem, fill=(0, 0, 0))
    thumbs.append(canvas)
    row_height = max(row_height, canvas.height)

for chunk_index in range(0, len(thumbs), 12):
    chunk = thumbs[chunk_index : chunk_index + 12]
    columns = 3
    rows = math.ceil(len(chunk) / columns)
    sheet = Image.new("RGB", (columns * target_width, rows * row_height), (235, 238, 242))
    for index, thumb in enumerate(chunk):
        x = (index % columns) * target_width
        y = (index // columns) * row_height
        sheet.paste(thumb, (x, y))
    sheet.save(render_dir / f"contact-{chunk_index // 12 + 1}.png")
