# 앱 아이콘 생성: python tools/make_icon.py → UsageWidget/Assets/app.ico (16~256px) + MSIX 로고 PNG
# 디자인: 어두운 둥근 사각형 + 사용률 막대 두 줄 (PiP 창 축소판)
import os
from PIL import Image, ImageDraw

S = 1024  # 크게 그린 뒤 축소 (안티앨리어싱)
BG, OK, WARN, TRACK = "#1d2230", "#2f9e5b", "#d98a12", "#3a4152"


def draw():
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((32, 32, S - 32, S - 32), radius=200, fill=BG)
    x0, x1, h = 190, S - 190, 150
    for y, frac, color in ((330, 0.62, OK), (560, 0.85, WARN)):
        d.rounded_rectangle((x0, y, x1, y + h), radius=h / 2, fill=TRACK)
        d.rounded_rectangle((x0, y, x0 + (x1 - x0) * frac, y + h), radius=h / 2, fill=color)
    return im


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "UsageWidget", "Assets", "app.ico")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    big = draw()
    big.resize((256, 256), Image.LANCZOS).save(out, sizes=[(s, s) for s in sizes])
    print("wrote", os.path.normpath(out))
    # MSIX/Store 로고 (Package.appxmanifest가 참조). ponytail: scale-100만, 흐릿하면 .scale-200 추가
    assets = os.path.dirname(out)
    for name, (w, h) in {"Square44x44Logo": (44, 44), "Square150x150Logo": (150, 150),
                         "Wide310x150Logo": (310, 150), "StoreLogo": (50, 50)}.items():
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        side = min(w, h)
        canvas.paste(big.resize((side, side), Image.LANCZOS), ((w - side) // 2, (h - side) // 2))
        canvas.save(os.path.join(assets, name + ".png"))
    print("wrote MSIX logos in", os.path.normpath(assets))
