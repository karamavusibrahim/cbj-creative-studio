# crop a tall screenshot into readable slices: python3 scripts/crop.py <png> <slice height>
import sys
from PIL import Image
p, h = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1600
im = Image.open(p)
name = p.rsplit("/", 1)[-1][:-4]
for i, y in enumerate(range(0, im.height, h)):
    im.crop((0, y, im.width, min(im.height, y + h))).save(f"/tmp/qa/{name}-{i}.png")
    print(f"/tmp/qa/{name}-{i}.png")
