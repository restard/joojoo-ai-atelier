#!/usr/bin/env python3
"""
スライド自動生成エンジン v3
背景画像 + コンテンツ -> 完成スライド。テキスト・画像配置はすべて自動。
9つのレイアウト型をサポート。
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

# ---- フォント ----
SERIF_BLACK = "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"
SERIF_MED   = "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"
SERIF_REG   = "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"
SANS_REG    = "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc"
JP_INDEX = 0
SLIDE_ASPECT = 16 / 9

# スーパーサンプリング倍率（ジャギ対策：高解像度で描画して最後に縮小）
SUPERSAMPLE = 2
# 全スライド共通の出力解像度（背景サイズに依らず統一）
OUTPUT_W, OUTPUT_H = 1920, 1080

def load_background(bg_path, target_aspect=SLIDE_ASPECT):
    img = Image.open(bg_path).convert("RGB")
    W, H = img.size
    aspect = W / H
    if abs(aspect - target_aspect) < 1e-3:
        return img
    if aspect > target_aspect:
        new_w = int(H * target_aspect)
        left = (W - new_w) // 2
        img = img.crop((left, 0, left + new_w, H))
    else:
        new_h = int(W / target_aspect)
        top = (H - new_h) // 2
        img = img.crop((0, top, W, top + new_h))
    return img

def _prepare_canvas(bg_path):
    """背景を読み込み、OUTPUT_SIZE×SUPERSAMPLE の解像度に拡大。"""
    img = load_background(bg_path)
    render_w, render_h = OUTPUT_W * SUPERSAMPLE, OUTPUT_H * SUPERSAMPLE
    img = img.resize((render_w, render_h), Image.LANCZOS)
    return img, OUTPUT_W, OUTPUT_H

def _save_canvas(img, output_path, W_out, H_out, quality=95):
    """スーパーサンプリング解像度から OUTPUT_SIZE に縮小して保存。"""
    img = img.resize((W_out, H_out), Image.LANCZOS)
    img.save(output_path, quality=quality)

def font(path, size, index=JP_INDEX):
    return ImageFont.truetype(path, size, index=index)

# ---- 配色 ----
INK_DARK  = (58, 36, 23)
INK_MID   = (107, 79, 58)
LIGHT     = (247, 242, 232)

# ===== 共通ヘルパー =====
def text_size(draw, txt, fnt, tracking=0):
    if tracking == 0:
        b = draw.textbbox((0, 0), txt, font=fnt)
        return b[2]-b[0], b[3]-b[1]
    w, h = 0, 0
    for ch in txt:
        b = draw.textbbox((0, 0), ch, font=fnt)
        w += (b[2]-b[0]) + tracking
        h = max(h, b[3]-b[1])
    return w-tracking, h

def draw_tracked(draw, xy, txt, fnt, fill, tracking=0, center_x=None, shadow=None):
    x, y = xy
    if center_x is not None:
        w, _ = text_size(draw, txt, fnt, tracking)
        x = center_x - w/2
    for ch in txt:
        if shadow:
            draw.text((x+shadow[0], y+shadow[1]), ch, font=fnt, fill=shadow[2])
        draw.text((x, y), ch, font=fnt, fill=fill)
        b = draw.textbbox((0, 0), ch, font=fnt)
        x += (b[2]-b[0]) + tracking

def draw_centered(draw, txt, fnt, fill, cx, y, shadow=None):
    w, _ = text_size(draw, txt, fnt)
    if shadow:
        draw.text((cx-w/2+shadow[0], y+shadow[1]), txt, font=fnt, fill=shadow[2])
    draw.text((cx-w/2, y), txt, font=fnt, fill=fill)

def wrap_text(draw, txt, fnt, max_w):
    """日本語を含む短文を、文字単位で指定幅に収める。"""
    lines, cur = [], ""
    for ch in txt:
        test = cur + ch
        if cur and text_size(draw, test, fnt)[0] > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines

def draw_centered_lines(draw, lines, fnt, fill, cx, y, line_h):
    for ln in lines:
        draw_centered(draw, ln, fnt, fill, cx, y)
        y += line_h
    return y

def apply_text_scrim(img, y_top, y_bottom, max_alpha=135, feather=140):
    """テキスト帯の背後を暗くして可読性を確保（写真上テキスト用）"""
    W, H = img.size
    ys = np.arange(H, dtype=float)
    a = np.full(H, float(max_alpha))
    above = ys < y_top
    below = ys > y_bottom
    a[above] = max_alpha * np.clip(1-(y_top-ys[above])/feather, 0, 1)
    a[below] = max_alpha * np.clip(1-(ys[below]-y_bottom)/feather, 0, 1)
    mask = Image.fromarray(np.tile(a[:,None],(1,W)).astype('uint8'), 'L')
    black = Image.new('RGB', (W,H), (0,0,0))
    return Image.composite(black, img, mask)

def paste_photo_plain(base, photo, cx, cy, target_w):
    """フレーム・シャドーなしで写真を配置（3-2の方針）"""
    ratio = photo.height / photo.width
    pw, ph = target_w, int(target_w * ratio)
    photo = photo.resize((pw, ph), Image.LANCZOS)
    x, y = int(cx - pw/2), int(cy - ph/2)
    if photo.mode == 'RGBA':
        base.paste(photo, (x, y), photo)
    else:
        base.paste(photo.convert('RGB'), (x, y))

def paste_photo_cover(base, photo_path, box):
    """写真を指定ボックスいっぱいに中央クロップして配置する。"""
    photo = Image.open(photo_path).convert("RGB")
    x1, y1, x2, y2 = [int(v) for v in box]
    bw, bh = x2 - x1, y2 - y1
    scale = max(bw / photo.width, bh / photo.height)
    nw, nh = int(photo.width * scale), int(photo.height * scale)
    photo = photo.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - bw) // 2, (nh - bh) // 2
    photo = photo.crop((left, top, left + bw, top + bh))
    base.paste(photo, (x1, y1))

def paste_photo_cover_image(base, photo, box):
    """読み込み済み写真を指定ボックスいっぱいに中央クロップして配置する。"""
    x1, y1, x2, y2 = [int(v) for v in box]
    bw, bh = x2 - x1, y2 - y1
    photo = photo.convert("RGB")
    scale = max(bw / photo.width, bh / photo.height)
    nw, nh = int(photo.width * scale), int(photo.height * scale)
    photo = photo.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - bw) // 2, (nh - bh) // 2
    photo = photo.crop((left, top, left + bw, top + bh))
    base.paste(photo, (x1, y1))

def paste_image_contain(base, image_path, box, fill=(252, 249, 242)):
    """画像全体が見切れないように、指定ボックス内へ収めて配置する。"""
    photo = Image.open(image_path).convert("RGB")
    x1, y1, x2, y2 = [int(v) for v in box]
    bw, bh = x2 - x1, y2 - y1
    scale = min(bw / photo.width, bh / photo.height)
    nw, nh = int(photo.width * scale), int(photo.height * scale)
    photo = photo.resize((nw, nh), Image.LANCZOS)
    card = Image.new("RGB", (bw, bh), fill)
    card.paste(photo, ((bw - nw) // 2, (bh - nh) // 2))
    base.paste(card, (x1, y1))

def make_placeholder(w, h, label, color=(170, 150, 132)):
    """テスト用の写真プレースホルダー"""
    ph = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(ph)
    f = font(SANS_REG, int(min(w,h)*0.10))
    tw, th = text_size(d, label, f)
    d.text(((w-tw)/2, (h-th)/2-th*0.3), label, font=f, fill=(240,235,228))
    return ph

def detect_light_card_center_x(img, fallback_cx):
    """表紙背景の明るいカード領域をざっくり検出し、その中心xを返す。"""
    arr = np.asarray(img.convert("RGB"))
    h, w = arr.shape[:2]
    crop = arr[int(h * 0.12):int(h * 0.88)]
    brightness = crop.mean(axis=2)
    # 暖色の夕暮れ背景ではカード面も暗めに出るため、少し低めの明度で拾う。
    col = (brightness > 150).mean(axis=0)
    xs = np.where(col > 0.55)[0]
    if len(xs) < w * 0.25:
        return fallback_cx

    # 最大の連続区間だけをカード候補にする。
    breaks = np.where(np.diff(xs) > 1)[0]
    starts = np.r_[0, breaks + 1]
    ends = np.r_[breaks, len(xs) - 1]
    segments = [(xs[s], xs[e]) for s, e in zip(starts, ends)]
    left, right = max(segments, key=lambda seg: seg[1] - seg[0])
    if right - left < w * 0.25:
        return fallback_cx
    return (left + right) / 2

# ===== 型A：表紙 =====
def render_cover(bg_path, output_path, content, safe_zone=(0.20,0.16,0.80,0.84)):
    img, W_out, H_out = _prepare_canvas(bg_path)
    W, H = img.size
    draw = ImageDraw.Draw(img)
    sz_t, sz_b = H*safe_zone[1], H*safe_zone[3]
    fallback_cx = W*(safe_zone[0]+safe_zone[2])/2
    cx = detect_light_card_center_x(img, fallback_cx)
    title_sz, eyebrow_sz = int(W*0.058), int(W*0.022)
    subtitle_sz, presenter_sz = int(W*0.021), int(W*0.016)
    f_title = font(SERIF_BLACK, title_sz)
    f_eye   = font(SERIF_REG, eyebrow_sz)
    f_sub   = font(SERIF_MED, subtitle_sz)
    f_pre   = font(SANS_REG, presenter_sz)
    gap_s, gap_m = int(H*0.028), int(H*0.040)
    line_h = int(title_sz*1.18)
    tlines = content['title']
    block_h = eyebrow_sz+gap_s + line_h*len(tlines)+gap_m + subtitle_sz
    y = sz_t + ((sz_b-sz_t)-block_h)*0.40
    draw_tracked(draw,(0,y),content['eyebrow'],f_eye,INK_MID,
                 tracking=int(eyebrow_sz*0.18),center_x=cx)
    y += eyebrow_sz+gap_s
    for ln in tlines:
        draw_centered(draw,ln,f_title,INK_DARK,cx,y); y += line_h
    y += gap_m-(line_h-title_sz)
    draw_centered(draw,content['subtitle'],f_sub,INK_MID,cx,y)
    py = sz_b-presenter_sz*1.6
    draw_tracked(draw,(0,py),content['presenter'],f_pre,INK_MID,
                 tracking=int(presenter_sz*0.10),center_x=cx)
    _save_canvas(img, output_path, W_out, H_out)
    print(f"[A 表紙]      {output_path}")

# ===== 型B：リスト =====
def render_list(bg_path, output_path, content, safe_zone=(0.20,0.16,0.80,0.84)):
    img, W_out, H_out = _prepare_canvas(bg_path)
    W, H = img.size
    draw = ImageDraw.Draw(img)
    sz_t, sz_b = H*safe_zone[1], H*safe_zone[3]
    cx = W*(safe_zone[0]+safe_zone[2])/2
    heading_sz, eyebrow_sz, item_sz = int(W*0.040), int(W*0.018), int(W*0.024)
    f_head = font(SERIF_BLACK, heading_sz)
    f_eye  = font(SERIF_REG, eyebrow_sz)
    f_item = font(SERIF_MED, item_sz)
    gap_s, gap_m = int(H*0.022), int(H*0.055)
    item_h = int(item_sz*1.95)
    items = content['items']
    has_eye = bool(content.get('eyebrow'))
    block_h = (eyebrow_sz+gap_s if has_eye else 0)+heading_sz+gap_m+item_h*len(items)
    y = sz_t + ((sz_b-sz_t)-block_h)*0.42
    if has_eye:
        draw_tracked(draw,(0,y),content['eyebrow'],f_eye,INK_MID,
                     tracking=int(eyebrow_sz*0.22),center_x=cx)
        y += eyebrow_sz+gap_s
    draw_centered(draw,content['heading'],f_head,INK_DARK,cx,y)
    y += heading_sz+gap_m
    num_col = text_size(draw,"0.",f_item)[0]+int(item_sz*0.5)
    widest = max(text_size(draw,it,f_item)[0] for it in items)
    bx = cx-(num_col+widest)/2
    for i,it in enumerate(items,1):
        draw.text((bx,y),f"{i}.",font=f_item,fill=INK_DARK)
        draw.text((bx+num_col,y),it,font=f_item,fill=INK_MID)
        y += item_h
    _save_canvas(img, output_path, W_out, H_out)
    print(f"[B リスト]    {output_path}")

# ===== 型C：ステートメント =====
def render_statement(bg_path, output_path, content, safe_zone=(0.20,0.16,0.80,0.84)):
    img, W_out, H_out = _prepare_canvas(bg_path)
    W, H = img.size
    draw = ImageDraw.Draw(img)
    sz_t, sz_b = H*safe_zone[1], H*safe_zone[3]
    cx = W*(safe_zone[0]+safe_zone[2])/2
    msg_sz, eyebrow_sz = int(W*0.036), int(W*0.019)
    f_msg = font(SERIF_MED, msg_sz)
    f_eye = font(SERIF_REG, eyebrow_sz)
    gap_m, line_h = int(H*0.050), int(msg_sz*1.55)
    lines = content['lines']
    has_eye = bool(content.get('eyebrow'))
    block_h = (eyebrow_sz+gap_m if has_eye else 0)+line_h*len(lines)
    y = sz_t + ((sz_b-sz_t)-block_h)/2
    if has_eye:
        draw_tracked(draw,(0,y),content['eyebrow'],f_eye,INK_MID,
                     tracking=int(eyebrow_sz*0.20),center_x=cx)
        y += eyebrow_sz+gap_m
    for ln in lines:
        draw_centered(draw,ln,f_msg,INK_DARK,cx,y); y += line_h
    _save_canvas(img, output_path, W_out, H_out)
    print(f"[C 宣言]      {output_path}")

# ===== 型D：メッセージ over 画像 =====
def render_message_over_image(bg_path, output_path, content, safe_zone=(0.10,0.16,0.90,0.84)):
    img, W_out, H_out = _prepare_canvas(bg_path)
    W, H = img.size
    msg_sz, eyebrow_sz = int(W*0.044), int(W*0.020)
    f_msg = font(SERIF_MED, msg_sz)
    f_eye = font(SERIF_REG, eyebrow_sz)
    gap_m, line_h = int(H*0.045), int(msg_sz*1.50)
    lines = content['lines']
    has_eye = bool(content.get('eyebrow'))
    block_h = (eyebrow_sz+gap_m if has_eye else 0)+line_h*len(lines)
    sz_t, sz_b = H*safe_zone[1], H*safe_zone[3]
    y0 = sz_t + ((sz_b-sz_t)-block_h)/2
    img = apply_text_scrim(img, y0-int(H*0.05), y0+block_h+int(H*0.05),
                           max_alpha=155, feather=int(170*SUPERSAMPLE))
    draw = ImageDraw.Draw(img)
    cx = W*(safe_zone[0]+safe_zone[2])/2
    sh = (int(3*SUPERSAMPLE), int(3*SUPERSAMPLE), (0,0,0))
    y = y0
    if has_eye:
        draw_tracked(draw,(0,y),content['eyebrow'],f_eye,LIGHT,
                     tracking=int(eyebrow_sz*0.22),center_x=cx,shadow=sh)
        y += eyebrow_sz+gap_m
    for ln in lines:
        draw_centered(draw,ln,f_msg,LIGHT,cx,y,shadow=sh); y += line_h
    _save_canvas(img, output_path, W_out, H_out)
    print(f"[D 画像上文]  {output_path}")

# ===== 型E：複数画像＋キャプション =====
def render_multi_image(bg_path, output_path, content, safe_zone=(0.12,0.15,0.88,0.80)):
    img, W_out, H_out = _prepare_canvas(bg_path)
    W, H = img.size
    draw = ImageDraw.Draw(img)
    sz_l, sz_r = W*safe_zone[0], W*safe_zone[2]
    sz_t, sz_b = H*safe_zone[1], H*safe_zone[3]
    cx = (sz_l+sz_r)/2
    heading_sz, caption_sz = int(W*0.036), int(W*0.019)
    f_head = font(SERIF_BLACK, heading_sz)
    f_cap  = font(SERIF_MED, caption_sz)
    items = content['items']
    n = len(items)
    gap_head, gap_cap = int(H*0.045), int(H*0.045)
    photo_zone_top = sz_t + heading_sz + gap_head
    caption_zone_h = caption_sz + gap_cap
    photo_zone_bot = sz_b - caption_zone_h
    photo_zone_h = photo_zone_bot - photo_zone_top
    slot_w = (sz_r-sz_l)/n
    photo_h = photo_zone_h
    photo_w = min(slot_w * 0.78, photo_h * 0.72)
    draw_centered(draw, content['heading'], f_head, INK_DARK, cx, sz_t)
    photo_cy = photo_zone_top + photo_zone_h/2
    for i, it in enumerate(items):
        if n == 2:
            inner_gap = W * 0.095
            offset = (photo_w + inner_gap) / 2
            slot_cx = cx + (-offset if i == 0 else offset)
        else:
            slot_cx = sz_l + slot_w*(i+0.5)
        photo = Image.open(it['image'])
        box = (
            slot_cx - photo_w/2,
            photo_cy - photo_h/2,
            slot_cx + photo_w/2,
            photo_cy + photo_h/2,
        )
        paste_photo_cover_image(img, photo, box)
        d2 = ImageDraw.Draw(img)
        cap_y = photo_zone_bot + gap_cap*0.35
        draw_centered(d2, it['caption'], f_cap, INK_DARK, slot_cx, cap_y)
    _save_canvas(img, output_path, W_out, H_out)
    print(f"[E 複数画像]  {output_path}")

# ===== 型J：コンテンツ配置 =====
def render_content(bg_path, output_path, content, safe_zone=(0.12,0.14,0.88,0.84)):
    img, W_out, H_out = _prepare_canvas(bg_path)
    W, H = img.size
    draw = ImageDraw.Draw(img)
    sz_l, sz_r = W*safe_zone[0], W*safe_zone[2]
    sz_t, sz_b = H*safe_zone[1], H*safe_zone[3]
    cx = (sz_l + sz_r) / 2

    title = content.get("title")
    subtitle = content.get("subtitle")
    columns = int(content.get("columns") or 1)
    items = content.get("items", [])
    if columns < 1 or columns > 4:
        raise ValueError("content.columns は1〜4で指定してください")
    if not items:
        raise ValueError("content.items が必要です")

    title_sz, sub_sz, caption_sz = int(W*0.036), int(W*0.020), int(W*0.016)
    f_title = font(SERIF_BLACK, title_sz)
    f_sub = font(SERIF_MED, sub_sz)
    f_cap = font(SERIF_MED, caption_sz)

    y = sz_t
    if title:
        draw_centered(draw, title, f_title, INK_DARK, cx, y)
        y += title_sz + int(H*0.020)
    if subtitle:
        draw_centered(draw, subtitle, f_sub, INK_MID, cx, y)
        y += sub_sz + int(H*0.045)
    elif title:
        y += int(H*0.030)

    if not title and not subtitle:
        y = sz_t

    gap = int(W * (0.030 if columns >= 3 else 0.050))
    caption_h = caption_sz + int(H*0.020) if any(it.get("caption") for it in items) else 0
    area_h = sz_b - y - caption_h
    area_w = sz_r - sz_l

    if columns == 1:
        box = (sz_l, y, sz_r, y + area_h)
        paste_image_contain(img, items[0]["image"], box)
        if items[0].get("caption"):
            draw_centered(draw, items[0]["caption"], f_cap, INK_MID, cx, y + area_h + int(H*0.018))
    else:
        col_w = (area_w - gap*(columns-1)) / columns
        for i in range(columns):
            if i >= len(items):
                break
            x1 = sz_l + i * (col_w + gap)
            x2 = x1 + col_w
            box = (x1, y, x2, y + area_h)
            paste_photo_cover(img, items[i]["image"], box)
            if items[i].get("caption"):
                draw_centered(draw, items[i]["caption"], f_cap, INK_MID,
                              (x1+x2)/2, y + area_h + int(H*0.018))

    _save_canvas(img, output_path, W_out, H_out)
    print(f"[J Content]   {output_path}")

# ===== 型H：before/after =====
def render_before_after(bg_path, output_path, content, safe_zone=(0.10,0.15,0.90,0.84)):
    img, W_out, H_out = _prepare_canvas(bg_path)
    W, H = img.size
    draw = ImageDraw.Draw(img)
    sz_l, sz_r = W*safe_zone[0], W*safe_zone[2]
    sz_t, sz_b = H*safe_zone[1], H*safe_zone[3]
    cx = (sz_l + sz_r) / 2

    heading_sz, eyebrow_sz = int(W*0.036), int(W*0.018)
    label_sz, caption_sz = int(W*0.017), int(W*0.018)
    f_head = font(SERIF_BLACK, heading_sz)
    f_eye = font(SERIF_REG, eyebrow_sz)
    f_label = font(SANS_REG, label_sz)
    f_caption = font(SERIF_MED, caption_sz)

    pairs = content.get("pairs", [])
    if not pairs:
        raise ValueError("before_after には content.pairs が必要です")

    y = sz_t
    if content.get("eyebrow"):
        draw_tracked(draw, (0, y), content["eyebrow"], f_eye, INK_MID,
                     tracking=int(eyebrow_sz*0.22), center_x=cx)
        y += eyebrow_sz + int(H*0.025)
    if content.get("heading"):
        draw_centered(draw, content["heading"], f_head, INK_DARK, cx, y)
        y += heading_sz + int(H*0.040)

    n = len(pairs)
    row_gap = int(H * (0.040 if n == 1 else 0.030))
    label_gap = int(H * 0.015)
    caption_gap = int(H * 0.016)
    label_h = label_sz
    has_caption = any(p.get("caption") for p in pairs)
    caption_h = caption_sz if has_caption else 0
    available_h = sz_b - y
    row_h = (available_h - row_gap*(n-1)) / n
    photo_h = row_h - label_h - label_gap - (caption_h + caption_gap if has_caption else 0)
    photo_h = max(photo_h, H*0.16)

    col_gap = int(W * 0.045)
    max_photo_w = ((sz_r - sz_l) - col_gap) / 2
    photo_w = min(max_photo_w, photo_h * 1.34)
    photo_h = min(photo_h, photo_w * 0.78)
    pair_w = photo_w*2 + col_gap
    before_x1 = cx - pair_w/2
    after_x1 = before_x1 + photo_w + col_gap

    before_label = content.get("before_label", "Before")
    after_label = content.get("after_label", "After")

    for pair in pairs:
        row_center_y = y + row_h/2
        row_caption_h = caption_h if pair.get("caption") else 0
        total_h = label_h + label_gap + photo_h + (caption_gap + row_caption_h if row_caption_h else 0)
        label_y = row_center_y - total_h/2
        photo_y1 = label_y + label_h + label_gap
        before_box = (before_x1, photo_y1, before_x1 + photo_w, photo_y1 + photo_h)
        after_box = (after_x1, photo_y1, after_x1 + photo_w, photo_y1 + photo_h)

        draw_centered(draw, pair.get("before_label", before_label), f_label,
                      INK_DARK, before_x1 + photo_w/2, label_y)
        draw_centered(draw, pair.get("after_label", after_label), f_label,
                      INK_DARK, after_x1 + photo_w/2, label_y)

        before_image = pair.get("before_image") or pair.get("before")
        after_image = pair.get("after_image") or pair.get("after")
        if not before_image or not after_image:
            raise ValueError("before_after の各 pair には before_image/after_image が必要です")
        paste_photo_cover(img, before_image, before_box)
        paste_photo_cover(img, after_image, after_box)

        if pair.get("caption"):
            cap_y = photo_y1 + photo_h + caption_gap
            draw_centered(draw, pair["caption"], f_caption, INK_MID, cx, cap_y)
        y += row_h + row_gap

    _save_canvas(img, output_path, W_out, H_out)
    print(f"[H Before/After] {output_path}")

# ===== 型I：3カラム =====
def render_three_column(bg_path, output_path, content, safe_zone=(0.17,0.16,0.83,0.84)):
    img, W_out, H_out = _prepare_canvas(bg_path)
    W, H = img.size
    draw = ImageDraw.Draw(img)
    sz_l, sz_r = W*safe_zone[0], W*safe_zone[2]
    sz_t, sz_b = H*safe_zone[1], H*safe_zone[3]
    cx = (sz_l + sz_r) / 2

    heading_sz, eyebrow_sz = int(W*0.036), int(W*0.018)
    col_title_sz, body_sz = int(W*0.022), int(W*0.016)
    f_head = font(SERIF_BLACK, heading_sz)
    f_eye = font(SERIF_REG, eyebrow_sz)
    f_col = font(SERIF_BLACK, col_title_sz)
    f_body = font(SERIF_MED, body_sz)

    columns = content.get("columns", [])
    if len(columns) != 3:
        raise ValueError("three_column には content.columns が3件必要です")

    y = sz_t
    if content.get("eyebrow"):
        draw_tracked(draw, (0, y), content["eyebrow"], f_eye, INK_MID,
                     tracking=int(eyebrow_sz*0.22), center_x=cx)
        y += eyebrow_sz + int(H*0.026)
    if content.get("heading"):
        draw_centered(draw, content["heading"], f_head, INK_DARK, cx, y)
        y += heading_sz + int(H*0.060)

    gap = int(W * 0.050)
    col_w = ((sz_r - sz_l) - gap*2) / 3
    col_top = y
    title_line_h = int(col_title_sz * 1.35)
    body_line_h = int(body_sz * 1.55)
    title_gap = int(H * 0.040)
    max_text_w = col_w * 0.82

    title_blocks, body_blocks = [], []
    max_title_h = 0
    for col in columns:
        title_lines = wrap_text(draw, col.get("title", ""), f_col, max_text_w)
        body = col.get("body", col.get("text", ""))
        body_lines = body if isinstance(body, list) else wrap_text(draw, body, f_body, max_text_w)
        title_blocks.append(title_lines)
        body_blocks.append(body_lines)
        max_title_h = max(max_title_h, len(title_lines) * title_line_h)

    body_y = col_top + max_title_h + title_gap
    for i, col in enumerate(columns):
        col_l = sz_l + i * (col_w + gap)
        col_cx = col_l + col_w/2
        title_y = col_top + (max_title_h - len(title_blocks[i]) * title_line_h) / 2
        draw_centered_lines(draw, title_blocks[i], f_col, INK_DARK, col_cx, title_y, title_line_h)

        body_lines = body_blocks[i]
        available_body_h = sz_b - body_y
        body_block_h = len(body_lines) * body_line_h
        adjusted_body_y = body_y + max(0, (available_body_h - body_block_h) * 0.18)
        draw_centered_lines(draw, body_lines, f_body, INK_MID, col_cx, adjusted_body_y, body_line_h)

    _save_canvas(img, output_path, W_out, H_out)
    print(f"[I 3カラム]   {output_path}")

# ===== 型L：プロセス =====
def render_process(bg_path, output_path, content, safe_zone=(0.13,0.15,0.87,0.84)):
    img, W_out, H_out = _prepare_canvas(bg_path)
    W, H = img.size
    draw = ImageDraw.Draw(img)
    sz_l, sz_r = W*safe_zone[0], W*safe_zone[2]
    sz_t, sz_b = H*safe_zone[1], H*safe_zone[3]
    cx = (sz_l + sz_r) / 2

    eyebrow_sz, title_sz = int(W*0.018), int(W*0.038)
    label_sz, step_title_sz, body_sz = int(W*0.019), int(W*0.027), int(W*0.017)
    f_eye = font(SERIF_REG, eyebrow_sz)
    f_title = font(SERIF_BLACK, title_sz)
    f_label = font(SANS_REG, label_sz)
    f_step_title = font(SERIF_BLACK, step_title_sz)
    f_body = font(SERIF_MED, body_sz)

    y = sz_t
    if content.get("eyebrow"):
        draw_tracked(draw, (0, y), content["eyebrow"], f_eye, INK_MID,
                     tracking=int(eyebrow_sz*0.22), center_x=cx)
        y += eyebrow_sz + int(H*0.026)
    draw_centered(draw, content.get("title") or content.get("heading", ""), f_title, INK_DARK, cx, y)
    y += title_sz + int(H*0.065)

    steps = content.get("steps", [])
    if not steps:
        raise ValueError("process.steps が必要です")

    columns = min(int(content.get("columns") or len(steps)), len(steps))
    gap = int(W * 0.035)
    card_w = ((sz_r - sz_l) - gap*(columns-1)) / columns
    card_h = sz_b - y
    body_line_h = int(body_sz * 1.55)

    for i, step in enumerate(steps[:columns]):
        x1 = sz_l + i * (card_w + gap)
        x2 = x1 + card_w
        card_cx = (x1 + x2) / 2
        label = step.get("label", f"STEP {i+1}")
        title = step.get("title", "")
        body = step.get("body") or []
        if isinstance(body, str):
            body = [body]

        card = Image.new("RGBA", (int(card_w), int(card_h)), (252, 249, 242, 218))
        shadow = Image.new("RGBA", (int(card_w + 24*SUPERSAMPLE), int(card_h + 24*SUPERSAMPLE)), (0,0,0,0))
        sd = ImageDraw.Draw(shadow)
        sd.rectangle([10*SUPERSAMPLE, 10*SUPERSAMPLE, 10*SUPERSAMPLE+card.width, 10*SUPERSAMPLE+card.height], fill=(40, 25, 15, 42))
        shadow = shadow.filter(ImageFilter.GaussianBlur(8*SUPERSAMPLE))
        img.paste(shadow, (int(x1 - 8*SUPERSAMPLE), int(y - 2*SUPERSAMPLE)), shadow)
        img.paste(card, (int(x1), int(y)), card)

        ty = y + int(H*0.052)
        draw_tracked(draw, (0, ty), label, f_label, INK_MID,
                     tracking=int(label_sz*0.10), center_x=card_cx)
        ty += label_sz + int(H*0.035)
        draw_centered(draw, title, f_step_title, INK_DARK, card_cx, ty)
        ty += step_title_sz + int(H*0.046)

        body_lines = []
        for line in body:
            body_lines.extend(wrap_text(draw, line, f_body, card_w * 0.72))
        draw_centered_lines(draw, body_lines, f_body, INK_MID, card_cx, ty, body_line_h)

    _save_canvas(img, output_path, W_out, H_out)
    print(f"[L Process]   {output_path}")

# ===== 型F：人物写真＋テキスト =====
def render_person_text(bg_path, output_path, content, safe_zone=(0.12,0.16,0.88,0.84)):
    img, W_out, H_out = _prepare_canvas(bg_path)
    W, H = img.size
    sz_l, sz_r = W*safe_zone[0], W*safe_zone[2]
    sz_t, sz_b = H*safe_zone[1], H*safe_zone[3]
    side = content.get('side','left')
    person = Image.open(content['person_image'])
    photo_ratio = person.height / person.width
    max_photo_h = (sz_b - sz_t) * 0.96
    photo_w = int(min(W*0.30, max_photo_h / photo_ratio))
    draw = ImageDraw.Draw(img)
    msg_sz, eyebrow_sz = int(W*0.034), int(W*0.019)
    f_msg = font(SERIF_MED, msg_sz)
    f_eye = font(SERIF_REG, eyebrow_sz)
    lines = content['lines']
    text_w = max(
        [text_size(draw, ln, f_msg)[0] for ln in lines] +
        ([text_size(draw, content['eyebrow'], f_eye, tracking=int(eyebrow_sz*0.20))[0]]
         if content.get('eyebrow') else [])
    )
    gap_x = W * 0.045
    if side == 'left':
        photo_cx = sz_l + photo_w*0.72
        text_cx = photo_cx + photo_w/2 + gap_x + text_w/2
        text_cx = min(text_cx, sz_r - text_w/2)
    else:
        photo_cx = sz_r - photo_w*0.72
        text_cx = photo_cx - photo_w/2 - gap_x - text_w/2
        text_cx = max(text_cx, sz_l + text_w/2)
    photo_cy = (sz_t+sz_b)/2
    paste_photo_plain(img, person, photo_cx, photo_cy, photo_w)
    gap_m, line_h = int(H*0.045), int(msg_sz*1.5)
    has_eye = bool(content.get('eyebrow'))
    block_h = (eyebrow_sz+gap_m if has_eye else 0)+line_h*len(lines)
    y = (sz_t+sz_b)/2 - block_h/2
    if has_eye:
        draw_tracked(draw,(0,y),content['eyebrow'],f_eye,INK_MID,
                     tracking=int(eyebrow_sz*0.20),center_x=text_cx)
        y += eyebrow_sz+gap_m
    for ln in lines:
        draw_centered(draw,ln,f_msg,INK_DARK,text_cx,y); y += line_h
    _save_canvas(img, output_path, W_out, H_out)
    print(f"[F 人物＋文]  {output_path}")

# ===== 型G：CTA／QR =====
def render_cta(bg_path, output_path, content, safe_zone=(0.20,0.14,0.80,0.86)):
    import qrcode
    img, W_out, H_out = _prepare_canvas(bg_path)
    W, H = img.size
    draw = ImageDraw.Draw(img)
    sz_t, sz_b = H*safe_zone[1], H*safe_zone[3]
    cx = W*(safe_zone[0]+safe_zone[2])/2
    heading_sz, sub_sz = int(W*0.044), int(W*0.022)
    f_head = font(SERIF_BLACK, heading_sz)
    f_sub  = font(SERIF_MED, sub_sz)
    has_sub = bool(content.get('subtext'))
    qr = qrcode.QRCode(box_size=10*SUPERSAMPLE, border=2)
    qr.add_data(content['qr_data'])
    qr.make()
    qr_img = qr.make_image(fill_color=(58,36,23), back_color=(252,249,242)).convert("RGB")
    qr_size = int(W*0.20)
    qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS)
    pad = int(qr_size*0.12)
    card = Image.new("RGB",(qr_size+pad*2, qr_size+pad*2),(252,249,242))
    card.paste(qr_img,(pad,pad))
    gap_s, gap_l = int(H*0.030), int(H*0.055)
    block_h = heading_sz + (gap_s+sub_sz if has_sub else 0) + gap_l + card.height
    y = sz_t + ((sz_b-sz_t)-block_h)/2
    draw_centered(draw,content['heading'],f_head,INK_DARK,cx,y)
    y += heading_sz
    if has_sub:
        y += gap_s
        draw_centered(draw,content['subtext'],f_sub,INK_MID,cx,y)
        y += sub_sz
    y += gap_l
    sp = SUPERSAMPLE
    shadow = Image.new("RGBA",(card.width+50*sp,card.height+50*sp),(0,0,0,0))
    sd = ImageDraw.Draw(shadow)
    sd.rectangle([25*sp,25*sp,25*sp+card.width,25*sp+card.height],fill=(40,25,15,90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12*sp))
    img.paste(shadow,(int(cx-shadow.width/2)+6*sp,int(y)+8*sp),shadow)
    img.paste(card,(int(cx-card.width/2),int(y)))
    _save_canvas(img, output_path, W_out, H_out)
    print(f"[G CTA/QR]    {output_path}")

# ===== 型K：オファー =====
def render_offer(bg_path, output_path, content, safe_zone=(0.14,0.14,0.86,0.86)):
    img, W_out, H_out = _prepare_canvas(bg_path)
    W, H = img.size
    draw = ImageDraw.Draw(img)
    sz_l, sz_r = W*safe_zone[0], W*safe_zone[2]
    sz_t, sz_b = H*safe_zone[1], H*safe_zone[3]
    cx = (sz_l + sz_r) / 2

    label_sz, title_sz, name_sz, price_sz, body_sz = (
        int(W*0.018), int(W*0.043), int(W*0.026), int(W*0.034), int(W*0.019)
    )
    f_label = font(SANS_REG, label_sz)
    f_title = font(SERIF_BLACK, title_sz)
    f_name = font(SERIF_MED, name_sz)
    f_price = font(SERIF_BLACK, price_sz)
    f_body = font(SERIF_MED, body_sz)

    label = content.get("label")
    title = content.get("title", "")
    offer_name = content.get("offer_name")
    price = content.get("price")
    body = content.get("body") or []
    if isinstance(body, str):
        body = [body]

    block_lines = []
    if label:
        block_lines.append(("label", label))
    block_lines.append(("title", title))
    if offer_name:
        block_lines.append(("name", offer_name))
    if price:
        block_lines.append(("price", price))

    line_gap = int(H * 0.030)
    body_line_h = int(body_sz * 1.75)
    block_h = 0
    for kind, _ in block_lines:
        block_h += {"label": label_sz, "title": title_sz, "name": name_sz, "price": price_sz}[kind]
        block_h += line_gap
    block_h += len(body) * body_line_h

    y = sz_t + ((sz_b - sz_t) - block_h) * 0.46
    for kind, text in block_lines:
        if kind == "label":
            draw_tracked(draw, (0, y), text, f_label, INK_MID,
                         tracking=int(label_sz*0.12), center_x=cx)
            y += label_sz + line_gap
        elif kind == "title":
            draw_centered(draw, text, f_title, INK_DARK, cx, y)
            y += title_sz + line_gap
        elif kind == "name":
            draw_centered(draw, text, f_name, INK_MID, cx, y)
            y += name_sz + line_gap
        elif kind == "price":
            draw_centered(draw, text, f_price, INK_DARK, cx, y)
            y += price_sz + line_gap

    for line in body:
        for wrapped in wrap_text(draw, line, f_body, (sz_r - sz_l) * 0.78):
            draw_centered(draw, wrapped, f_body, INK_MID, cx, y)
            y += body_line_h

    _save_canvas(img, output_path, W_out, H_out)
    print(f"[K Offer]     {output_path}")


if __name__ == "__main__":
    BG = '/mnt/user-data/uploads/ChatGPT_Image_May_20__2026__09_24_23_AM.png'
    LOUNGE = '/mnt/user-data/uploads/1779224302556_image.png'

    render_cover(BG, 'slide_A_cover.png', {
        'eyebrow':'2026 Planning flight',
        'title':['未来を旅する','プランニング会'],
        'subtitle':'ーわたしの2026年へ出発する120分ー',
        'presenter':'Presented By : HITOMI TANIUCHI',
    })
    render_list(BG, 'slide_B_list.png', {
        'eyebrow':"TODAY'S JOURNEY",
        'heading':'本日の旅のしおり',
        'items':['オープニング','Wish List','Life Vision',
                 '1 Year Vision','谷内瞳 2026年の行動','参加者様へのプレゼント'],
    })
    render_statement(BG, 'slide_C_statement.png', {
        'eyebrow':'Have a good time!',
        'lines':['今日という時間が','あなたの2026年への','出発点になりますように'],
    })
    render_message_over_image(LOUNGE, 'slide_D_overimage.png', {
        'eyebrow':'Welcome to 2026 Journey',
        'lines':['私たちは','３つの選択肢があります'],
    })
    p1 = make_placeholder(640, 800, '写真 1', (150,128,110))
    p2 = make_placeholder(640, 800, '写真 2', (138,118,100))
    p1.save('_ph1.png'); p2.save('_ph2.png')
    render_multi_image(BG, 'slide_E_multiimage.png', {
        'heading':'こんなこともやってます',
        'items':[
            {'image':'_ph1.png','caption':'毎朝7:45〜 モーニングフライト'},
            {'image':'_ph2.png','caption':'個別プロデュース 等'},
        ],
    })
    pf = make_placeholder(700, 980, '人物写真', (146,124,108))
    pf.save('_phperson.png')
    render_person_text(BG, 'slide_F_person.png', {
        'person_image':'_phperson.png',
        'side':'left',
        'eyebrow':'Take off into 2026 Journey',
        'lines':['それを踏まえて','谷内瞳の2026年','宣言します'],
    })
    render_cta(BG, 'slide_G_cta.png', {
        'heading':'作戦会議 30分',
        'subtext':'お申込みは3日以内！',
        'qr_data':'https://example.com/booking',
    })
    print("--- 全7型 生成完了 ---")
