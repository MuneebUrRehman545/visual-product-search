"""Script to generate realistic messy query image variations for model evaluation with updated CSV schema."""

import csv
from pathlib import Path
import random
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import fetch_all_products

EVALUATION_DIR = PROJECT_ROOT / "data" / "evaluation"
QUERIES_DIR = EVALUATION_DIR / "queries"
GROUND_TRUTH_FILE = EVALUATION_DIR / "ground_truth.csv"


def apply_different_angle(image: Image.Image) -> Image.Image:
    """Apply rotation angle variation."""
    angle = random.choice([-25, -15, -8, 8, 15, 25])
    return image.rotate(angle, expand=True, fillcolor=(240, 240, 240))


def apply_different_crop(image: Image.Image) -> Image.Image:
    """Apply tight or off-center cropping."""
    w, h = image.size
    crop_w = int(w * random.uniform(0.65, 0.85))
    crop_h = int(h * random.uniform(0.65, 0.85))
    left = random.randint(0, max(1, w - crop_w))
    top = random.randint(0, max(1, h - crop_h))
    return image.crop((left, top, left + crop_w, top + crop_h))


def apply_changed_lighting(image: Image.Image) -> Image.Image:
    """Simulate bright sunlight or dark shadow lighting shifts."""
    brightness = random.choice([0.45, 0.6, 1.4, 1.65])
    contrast = random.choice([0.7, 1.35, 1.6])
    img = ImageEnhance.Brightness(image).enhance(brightness)
    return ImageEnhance.Contrast(img).enhance(contrast)


def apply_changed_background(image: Image.Image) -> Image.Image:
    """Simulate placing the product on a new colored background with margin."""
    w, h = image.size
    margin = int(max(w, h) * 0.2)
    bg_color = random.choice([
        (220, 215, 205),
        (40, 45, 50),
        (180, 200, 220),
        (245, 245, 240),
    ])
    new_bg = Image.new("RGB", (w + margin * 2, h + margin * 2), bg_color)
    new_bg.paste(image, (margin, margin))
    return new_bg


def apply_partially_covered(image: Image.Image) -> Image.Image:
    """Simulate partial occlusion (item covered by sticky note/object)."""
    img = image.copy()
    draw = ImageDraw.Draw(img)
    w, h = img.size
    box_w = int(w * random.uniform(0.25, 0.45))
    box_h = int(h * random.uniform(0.25, 0.45))
    left = random.randint(0, max(1, w - box_w))
    top = random.randint(0, max(1, h - box_h))
    cover_color = random.choice([(255, 240, 150), (120, 120, 120), (200, 50, 50), (30, 30, 30)])
    draw.rectangle([left, top, left + box_w, top + box_h], fill=cover_color)
    return img


def apply_phone_camera(image: Image.Image) -> Image.Image:
    """Simulate mobile phone camera photo (blur, noise, tint)."""
    img = image.copy()
    img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.8, 1.5)))
    r, g, b = img.split()
    r = ImageEnhance.Brightness(r).enhance(1.1)
    b = ImageEnhance.Brightness(b).enhance(0.9)
    img = Image.merge("RGB", (r, g, b))
    arr = np.array(img).astype(np.float32)
    noise = np.random.normal(0, 8, arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


VARIATIONS = [
    ("different_angle", apply_different_angle),
    ("different_crop", apply_different_crop),
    ("changed_lighting", apply_changed_lighting),
    ("changed_background", apply_changed_background),
    ("partially_covered", apply_partially_covered),
    ("phone_camera", apply_phone_camera),
]


def main() -> None:
    random.seed(42)
    np.random.seed(42)

    print("Fetching catalog products from SQLite...")
    products = fetch_all_products()
    if not products:
        print("Error: No products found in database.", file=sys.stderr)
        sys.exit(1)

    QUERIES_DIR.mkdir(parents=True, exist_ok=True)

    # Clean existing query files
    for existing_file in QUERIES_DIR.glob("*"):
        if existing_file.is_file():
            existing_file.unlink()

    selected_products = products[:25]
    print(f"Generating 25 messy query variations for {len(selected_products)} catalog products...")

    rows = []

    for idx, prod in enumerate(selected_products, start=1):
        src_path = Path(prod["image_path"])
        if not src_path.exists():
            print(f"Warning: Missing source image {src_path}", file=sys.stderr)
            continue

        try:
            with Image.open(src_path) as orig_img:
                orig_img = orig_img.convert("RGB")
                variation_type, transform_fn = VARIATIONS[(idx - 1) % len(VARIATIONS)]
                messy_img = transform_fn(orig_img)

                query_filename = f"query_{idx:03d}.jpg"
                dst_path = QUERIES_DIR / query_filename
                messy_img.save(dst_path, quality=90)

                relevant_ids = str(prod["id"])
                if idx == 3 and len(products) >= 26:
                    relevant_ids = f"{prod['id']}|26"

                rows.append(
                    {
                        "query_filename": query_filename,
                        "relevant_product_ids": relevant_ids,
                        "variation": variation_type,
                    }
                )
                print(f"  [{idx}/25] Generated {query_filename} ({variation_type}) -> Relevant IDs: {relevant_ids}")

        except Exception as e:
            print(f"Error processing {src_path}: {e}", file=sys.stderr)

    fieldnames = [
        "query_filename",
        "relevant_product_ids",
        "variation",
    ]
    with open(GROUND_TRUTH_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved {len(rows)} ground truth records to: {GROUND_TRUTH_FILE}")
    print(f"Query images saved inside: {QUERIES_DIR}")


if __name__ == "__main__":
    main()
