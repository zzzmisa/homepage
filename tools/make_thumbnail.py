#!/usr/bin/env python3
"""アプリアイコンからホームページ掲載用サムネイルを生成するCLIツール。

アイコンのドミナントカラー（主要色）を抽出し、その色相のクリーンな
パステル背景（縦方向の淡いグラデーション）の中央に、角丸化した
アイコンを影付きで載せる。単一色相なので濁った色にならない。

使い方:
    python3 tools/make_thumbnail.py <icon> <output> [options]

例:
    python3 tools/make_thumbnail.py app_icon.png static/images/chibireco.png

背景をアイコンのぼかし画像にしたい場合は --bg-style blur を指定する。
"""

import argparse
import colorsys
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

# マスクや影のエッジを滑らかにするための内部拡大率
SUPERSAMPLE = 4


def parse_size(value: str) -> tuple[int, int]:
    try:
        w, h = value.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise argparse.ArgumentTypeError(f"サイズは 900x600 の形式で指定してください: {value!r}")


def dominant_hue(icon: Image.Image) -> float:
    """アイコンの主要色の色相 (0-1) を返す。彩度の高い色を優先する。"""
    im = icon.convert("RGB").resize((64, 64), Image.LANCZOS)
    q = im.quantize(colors=16, method=Image.MEDIANCUT)
    palette = q.getpalette()
    best_hue, best_score = 0.0, -1.0
    for count, idx in q.getcolors():
        r, g, b = palette[idx * 3 : idx * 3 + 3]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        # 白・黒・グレーに近い色は背景色として使わない
        if s < 0.12 or v < 0.25:
            continue
        score = count * (s**1.2) * (0.3 + 0.7 * v)
        if score > best_score:
            best_hue, best_score = h, score
    return best_hue


def make_tint_background(icon: Image.Image, size: tuple[int, int], sat: float) -> Image.Image:
    """ドミナント色相のクリーンなパステル縦グラデーション背景を返す。"""
    w, h = size
    hue = dominant_hue(icon)
    top = colorsys.hsv_to_rgb(hue, sat * 0.7, 1.0)
    bottom = colorsys.hsv_to_rgb(hue, min(1.0, sat * 1.3), 0.97)
    grad = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / (h - 1)
        grad.putpixel(
            (0, y),
            tuple(round((top[i] * (1 - t) + bottom[i] * t) * 255) for i in range(3)),
        )
    return grad.resize((w, h), Image.BILINEAR)


def make_blur_background(
    icon: Image.Image, size: tuple[int, int], blur: float, brightness: float, lighten: float, saturation: float
) -> Image.Image:
    """アイコンを cover でリサイズ → ぼかし → 彩度/明度調整 → 白ブレンドした背景を返す。"""
    w, h = size
    scale = max(w / icon.width, h / icon.height)
    scaled = icon.resize((round(icon.width * scale), round(icon.height * scale)), Image.LANCZOS)
    left = (scaled.width - w) // 2
    top = (scaled.height - h) // 2
    bg = scaled.crop((left, top, left + w, top + h)).convert("RGB")
    bg = bg.filter(ImageFilter.GaussianBlur(blur))
    bg = ImageEnhance.Color(bg).enhance(saturation)
    bg = ImageEnhance.Brightness(bg).enhance(brightness)
    if lighten > 0:
        bg = Image.blend(bg, Image.new("RGB", (w, h), (255, 255, 255)), lighten)
    return bg


def apply_vignette(bg: Image.Image, strength: float) -> Image.Image:
    """縁をわずかに暗くして画面を引き締めるビネットを適用する。"""
    if strength <= 0:
        return bg
    w, h = bg.size
    # 小さい楕円グラデーションを拡大してなめらかなマスクを作る
    sw, sh = w // 8, h // 8
    small = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(small).ellipse(
        (round(-sw * 0.05), round(-sh * 0.05), round(sw * 1.05), round(sh * 1.05)), fill=255
    )
    mask = small.filter(ImageFilter.GaussianBlur(min(sw, sh) // 6)).resize((w, h), Image.LANCZOS)
    dark = ImageEnhance.Brightness(bg).enhance(1.0 - strength)
    return Image.composite(bg, dark, mask)


def rounded_icon(icon: Image.Image, icon_px: int, radius_ratio: float) -> Image.Image:
    """アイコンを icon_px 角にリサイズし、iOS風の角丸マスクを適用して返す。"""
    ss = icon_px * SUPERSAMPLE
    im = icon.convert("RGBA").resize((ss, ss), Image.LANCZOS)
    mask = Image.new("L", (ss, ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, ss - 1, ss - 1), radius=round(ss * radius_ratio), fill=255)
    im.putalpha(mask)
    return im.resize((icon_px, icon_px), Image.LANCZOS)


def add_keyline(fg: Image.Image, radius_ratio: float, opacity: int) -> Image.Image:
    """アイコンの輪郭に極細の暗いキーラインを描いてエッジを立たせる。"""
    if opacity <= 0:
        return fg
    px = fg.width
    ss = px * SUPERSAMPLE
    line = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    ImageDraw.Draw(line).rounded_rectangle(
        (0, 0, ss - 1, ss - 1),
        radius=round(ss * radius_ratio),
        outline=(20, 20, 30, opacity),
        width=SUPERSAMPLE,
    )
    return Image.alpha_composite(fg, line.resize((px, px), Image.LANCZOS))


def drop_shadow(icon_px: int, radius_ratio: float, blur: float, opacity: int, size: tuple[int, int], offset_y: int) -> Image.Image:
    """キャンバスサイズの影レイヤーを返す。"""
    w, h = size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shape = Image.new("L", (icon_px, icon_px), 0)
    ImageDraw.Draw(shape).rounded_rectangle(
        (0, 0, icon_px - 1, icon_px - 1), radius=round(icon_px * radius_ratio), fill=opacity
    )
    x = (w - icon_px) // 2
    y = (h - icon_px) // 2 + offset_y
    layer.paste(Image.new("RGBA", (icon_px, icon_px), (0, 0, 0, 255)), (x, y), shape)
    return layer.filter(ImageFilter.GaussianBlur(blur))


def generate(args: argparse.Namespace) -> None:
    icon = Image.open(args.icon)
    if icon.width != icon.height:
        print(f"警告: アイコンが正方形ではありません ({icon.width}x{icon.height})。中央を正方形に切り出します。", file=sys.stderr)
        side = min(icon.size)
        left = (icon.width - side) // 2
        top = (icon.height - side) // 2
        icon = icon.crop((left, top, left + side, top + side))

    w, h = args.size
    if args.bg_style == "tint":
        bg = make_tint_background(icon, args.size, args.tint_sat)
    else:
        bg = make_blur_background(
            icon, args.size, args.bg_blur, args.bg_brightness, args.bg_lighten, args.bg_saturation
        )
    canvas = apply_vignette(bg, args.vignette).convert("RGBA")

    icon_px = round(h * args.icon_scale)
    canvas = Image.alpha_composite(
        canvas, drop_shadow(icon_px, args.radius, args.shadow_blur, args.shadow_opacity, args.size, args.shadow_offset)
    )

    fg = add_keyline(rounded_icon(icon, icon_px, args.radius), args.radius, args.keyline)
    canvas.alpha_composite(fg, ((w - icon_px) // 2, (h - icon_px) // 2))

    out = canvas.convert("RGB")
    out.save(args.output)
    print(f"生成しました: {args.output} ({w}x{h})")


def main() -> None:
    parser = argparse.ArgumentParser(description="アプリアイコンからサムネイル画像を生成する")
    parser.add_argument("icon", help="アプリアイコン画像 (正方形PNG推奨)")
    parser.add_argument("output", help="出力先パス (.png / .jpg)")
    parser.add_argument("--size", type=parse_size, default=(900, 600), help="出力サイズ WxH (デフォルト: 900x600)")
    parser.add_argument("--icon-scale", type=float, default=0.72, help="アイコンの高さ比率 (デフォルト: 0.72)")
    parser.add_argument("--radius", type=float, default=0.2237, help="角丸半径のアイコン辺比率 (デフォルト: iOS風 0.2237)")
    parser.add_argument("--bg-style", choices=["tint", "blur"], default="tint", help="背景の種類 (デフォルト: tint)")
    parser.add_argument("--tint-sat", type=float, default=0.22, help="tint背景の彩度 (デフォルト: 0.22)")
    parser.add_argument("--bg-blur", type=float, default=60, help="blur背景のぼかし半径 (デフォルト: 60)")
    parser.add_argument("--bg-brightness", type=float, default=1.0, help="blur背景の明るさ倍率 (デフォルト: 1.0)")
    parser.add_argument("--bg-lighten", type=float, default=0.42, help="blur背景の白ブレンド率 0-1 (デフォルト: 0.42)")
    parser.add_argument("--bg-saturation", type=float, default=1.45, help="blur背景の白ブレンド前の彩度倍率 (デフォルト: 1.45)")
    parser.add_argument("--vignette", type=float, default=0.0, help="縁の減光率 0-1 (デフォルト: 0)")
    parser.add_argument("--keyline", type=int, default=45, help="アイコン輪郭線の不透明度 0-255 (デフォルト: 45)")
    parser.add_argument("--shadow-blur", type=float, default=12, help="影のぼかし半径 (デフォルト: 12)")
    parser.add_argument("--shadow-opacity", type=int, default=95, help="影の不透明度 0-255 (デフォルト: 95)")
    parser.add_argument("--shadow-offset", type=int, default=7, help="影の下方向オフセットpx (デフォルト: 7)")
    generate(parser.parse_args())


if __name__ == "__main__":
    main()
