"""Generate 3 crisp 9:16 (1080x1920) demo visual cards for Radhi Fruits / Kilang Pemasaran."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "resource" / "kilang_samples"
FONT_BOLD = ROOT_DIR / "resource" / "fonts" / "BeVietnamPro-Bold.ttf"
FONT_MEDIUM = ROOT_DIR / "resource" / "fonts" / "BeVietnamPro-Medium.ttf"

WIDTH = 1080
HEIGHT = 1920

CARDS = (
    {
        "filename": "radhi_fruits_1.png",
        "top_rgb": (17, 74, 48),
        "bottom_rgb": (217, 119, 6),
        "accent_rgb": (253, 224, 71),
        "badge": "SAMPEL VISUAL DEMO #1",
        "headline": ("RADHI FRUITS", "KEMAMAN"),
        "subline": "Stok Segar Harian • Terus Dari Kebun",
        "detail": "Durian Kampung • Musang King • Buah Bermusim",
    },
    {
        "filename": "radhi_fruits_2.png",
        "top_rgb": (120, 53, 15),
        "bottom_rgb": (22, 101, 52),
        "accent_rgb": (254, 240, 138),
        "badge": "SAMPEL VISUAL DEMO #2",
        "headline": ("ISI TEBAL,", "BAU HARUM PADU"),
        "subline": "Boleh Pilih & Semak Terus Di Kedai",
        "detail": "Jaminan Kualiti Segar • Sesuai Untuk Sekeluarga",
    },
    {
        "filename": "radhi_fruits_3.png",
        "top_rgb": (15, 23, 42),
        "bottom_rgb": (21, 128, 61),
        "accent_rgb": (134, 239, 172),
        "badge": "SAMPEL VISUAL DEMO #3",
        "headline": ("PICKUP & COD", "AREA KEMAMAN"),
        "subline": "WhatsApp Sekarang Untuk Tempahan Awal",
        "detail": "Stok Harian Terhad • Siapa Cepat Dia Dapat",
    },
)


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if path.is_file():
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _vertical_gradient(
    width: int, height: int, top: tuple[int, int, int], bottom: tuple[int, int, int]
) -> Image.Image:
    base = Image.new("RGB", (1, height))
    pixels = [
        (
            int(top[0] + (bottom[0] - top[0]) * (y / max(height - 1, 1))),
            int(top[1] + (bottom[1] - top[1]) * (y / max(height - 1, 1))),
            int(top[2] + (bottom[2] - top[2]) * (y / max(height - 1, 1))),
        )
        for y in range(height)
    ]
    base.putdata(pixels)
    return base.resize((width, height), resample=Image.Resampling.BILINEAR)


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (WIDTH - text_width) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return y + text_height


def generate_samples(output_dir: Path = OUTPUT_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    badge_font = _load_font(FONT_BOLD, 34)
    title_font = _load_font(FONT_BOLD, 88)
    sub_font = _load_font(FONT_MEDIUM, 38)
    detail_font = _load_font(FONT_MEDIUM, 34)

    created: list[Path] = []
    for index, card in enumerate(CARDS, start=1):
        img = _vertical_gradient(WIDTH, HEIGHT, card["top_rgb"], card["bottom_rgb"])
        draw = ImageDraw.Draw(img)

        # Decorative soft border rings to give gentle depth during Ken Burns zoom
        draw.rounded_rectangle(
            [(72, 180), (WIDTH - 72, HEIGHT - 280)],
            radius=48,
            outline=card["accent_rgb"],
            width=4,
        )
        draw.ellipse(
            [(WIDTH // 2 - 220, 420), (WIDTH // 2 + 220, 860)],
            outline=card["accent_rgb"],
            width=5,
        )
        draw.ellipse(
            [(WIDTH // 2 - 165, 475), (WIDTH // 2 + 165, 805)],
            fill=(255, 255, 255),
        )
        _draw_centered_text(draw, 595, f"0{index}", title_font, card["top_rgb"])

        _draw_centered_text(draw, 250, card["badge"], badge_font, card["accent_rgb"])

        cursor_y = 960
        for line in card["headline"]:
            cursor_y = _draw_centered_text(draw, cursor_y, line, title_font, (255, 255, 255))
            cursor_y += 20

        cursor_y += 30
        cursor_y = _draw_centered_text(draw, cursor_y, card["subline"], sub_font, card["accent_rgb"])
        cursor_y += 32
        _draw_centered_text(draw, cursor_y, card["detail"], detail_font, (241, 245, 249))

        out_path = output_dir / card["filename"]
        img.save(out_path, format="PNG", optimize=True)
        created.append(out_path)
    return created


if __name__ == "__main__":
    paths = generate_samples()
    for p in paths:
        print(f"Generated {p}")
