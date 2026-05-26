#!/usr/bin/env python3
"""
デッキ組み立てパイプライン
================================================================
deck spec(JSON) を読み込み、型ごとに背景プールから選択し、
slide_render.py の9型レンダラーで描画、PPTXにまとめる。

実行時に画像生成APIは呼ばない（背景はプールから「選ぶ」だけ）。
= 即時・追加コストゼロ・世界観は事前検品済み。

使い方:
  python build_deck.py specs/deck_taniuchi.json
  python build_deck.py specs/deck_taniuchi.json --color terracotta
"""
import argparse, json, os
from slide_render import (
    render_cover, render_list, render_statement, render_message_over_image,
    render_multi_image, render_before_after, render_three_column,
    render_person_text, render_cta, render_content, render_offer,
    render_process,
)
from pptx import Presentation
from pptx.util import Inches

ROOT_DIR = os.path.dirname(__file__)
MESSAGE_FALLBACKS = [
    os.path.join(ROOT_DIR, "assets", "message1.webp"),
    os.path.join(ROOT_DIR, "assets", "message2.webp"),
]

# 型名 → レンダラー関数
RENDERERS = {
    "cover":       render_cover,
    "list":        render_list,
    "statement":   render_statement,
    "message":     render_message_over_image,
    "multi_image": render_multi_image,
    "before_after": render_before_after,
    "three_column": render_three_column,
    "content":     render_content,
    "process":     render_process,
    "offer":       render_offer,
    "person":      render_person_text,
    "cta":         render_cta,
}

BACKGROUND_ALIASES = {
    "before_after": "multi_image",
    "three_column": "statement",
    "content": "multi_image",
    "process": "statement",
    "offer": "cta",
}

# message スライド用の一時背景（assets 内の webp）
MESSAGE_FALLBACKS = [
    "assets/message1.webp",
    "assets/message2.webp",
]


class BackgroundPool:
    """色×型ごとの背景プール。連続重複を避けて1枚ずつ選択する。"""
    def __init__(self, pool_dir):
        self.pool, self.idx = {}, {}
        self.pool_dir = pool_dir
        known_types = sorted(
            set(RENDERERS) | set(BACKGROUND_ALIASES.values()),
            key=len,
            reverse=True,
        )
        for color in os.listdir(pool_dir):
            color_path = os.path.join(pool_dir, color)
            if not os.path.isdir(color_path):
                continue
            for f in sorted(os.listdir(color_path)):
                if not f.lower().endswith((".png", ".jpg", ".jpeg")):
                    continue
                stem = os.path.splitext(f)[0]
                slide_type = next(
                    (t for t in known_types if stem == t or stem.startswith(f"{t}_")),
                    None,
                )
                if not slide_type:
                    continue
                self.pool.setdefault(color, {}).setdefault(slide_type, []).append(os.path.join(color_path, f))
        for color, by_type in self.pool.items():
            for slide_type, imgs in by_type.items():
                imgs.sort()
                self.idx[(color, slide_type)] = 0

    def has(self, slide_type, color):
        return (
            (color in self.pool and slide_type in self.pool[color])
            or ("default" in self.pool and slide_type in self.pool["default"])
        )

    def pick(self, slide_type, color):
        if not self.has(slide_type, color):
            raise ValueError(
                f"背景プールに色 '{color}'・型 '{slide_type}' がありません"
                f"（{self.pool_dir}/{color}/{slide_type}.png を確認）"
            )
        actual_color = color if color in self.pool and slide_type in self.pool[color] else "default"
        imgs = self.pool[actual_color][slide_type]
        key = (actual_color, slide_type)
        img = imgs[self.idx[key] % len(imgs)]
        self.idx[key] += 1
        return img


def resolve_bg_type(stype, pool, color):
    if pool.has(stype, color):
        return stype
    return BACKGROUND_ALIASES.get(stype, stype)

def normalize_slide(stype, content):
    return stype, content


def build_deck(spec_path, pool_dir="backgrounds", output_pptx=None, work_dir="_slides", color="terracotta"):
    os.makedirs(work_dir, exist_ok=True)
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)

    title = spec.get("deck_title", "deck")
    pool = BackgroundPool(pool_dir)
    default_color = spec.get("color", color)
    output_pptx = output_pptx or f"{title}_{default_color}.pptx"
    slides = spec["slides"]
    print(f"=== 「{title}」 {len(slides)}枚を組み立て（default color: {default_color}）===")

    pngs = []
    message_idx = 0
    valid_message_fallbacks = [p for p in MESSAGE_FALLBACKS if os.path.exists(p)]
    for i, sl in enumerate(slides, 1):
        stype = sl["type"]
        stype, content = normalize_slide(stype, sl["content"])
        slide_color = sl.get("color", default_color)
        if stype not in RENDERERS:
            raise ValueError(f"スライド{i}: 未知の型 '{stype}'")
        # 背景：明示指定があればそれ、なければプールから選択
        if stype == "message":
            if sl.get("background"):
                bg = sl["background"]
            elif pool.has("message", slide_color):
                bg = pool.pick("message", slide_color)
            elif valid_message_fallbacks:
                bg = valid_message_fallbacks[message_idx % len(valid_message_fallbacks)]
                message_idx += 1
            else:
                bg = pool.pick("statement", slide_color)
        else:
            bg_type = resolve_bg_type(stype, pool, slide_color)
            bg = sl.get("background") or pool.pick(bg_type, slide_color)
        out = os.path.join(work_dir, f"slide_{i:02d}.png")
        print(f"  slide {i:02d}: type={stype}, color={slide_color}, bg={bg}")
        RENDERERS[stype](bg, out, content)
        pngs.append(out)

    # --- PPTX化（16:9・各スライドにフルブリードで画像を配置）---
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]   # 空白レイアウト
    for png in pngs:
        s = prs.slides.add_slide(blank)
        s.shapes.add_picture(png, 0, 0,
                             width=prs.slide_width, height=prs.slide_height)
    prs.save(output_pptx)
    print(f"=== 完了: {output_pptx}（{len(pngs)}枚）===")
    return output_pptx


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", nargs="?", default="specs/deck_taniuchi.json")
    ap.add_argument("--color", default="terracotta",
                    help="背景色プール。terracotta / cream / deep_green など")
    ap.add_argument("--pool-dir", default="backgrounds")
    ap.add_argument("--output", default=None)
    ap.add_argument("--work-dir", default="_slides")
    args = ap.parse_args()
    build_deck(args.spec, pool_dir=args.pool_dir, output_pptx=args.output,
               work_dir=args.work_dir, color=args.color)
