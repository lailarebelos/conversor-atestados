"""Gera as imagens do programa: recursos/icone.ico e recursos/abertura.png (tela de abertura do .exe).

Uso: python recursos/gerar_imagens.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

AQUI = Path(__file__).resolve().parent
AZUL = (31, 111, 178, 255)
AZUL_CLARO = (199, 221, 242, 255)
BRANCO = (255, 255, 255, 255)
VERDE = (21, 128, 61, 255)
CINZA = (91, 107, 124, 255)


def desenhar_icone(t: int = 512) -> Image.Image:
    img = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, t - 1, t - 1), radius=t // 6, fill=AZUL)
    w, h = t * 0.50, t * 0.64  # folha com o canto dobrado
    x0, y0 = (t - w) / 2 - t * 0.03, (t - h) / 2
    dobra = w * 0.30
    d.polygon([(x0, y0), (x0 + w - dobra, y0), (x0 + w, y0 + dobra), (x0 + w, y0 + h), (x0, y0 + h)], fill=BRANCO)
    d.polygon([(x0 + w - dobra, y0), (x0 + w - dobra, y0 + dobra), (x0 + w, y0 + dobra)], fill=AZUL_CLARO)
    for i, fim in enumerate((0.80, 0.80, 0.55)):
        y = y0 + h * (0.40 + i * 0.15)
        d.rounded_rectangle((x0 + w * 0.15, y, x0 + w * fim, y + h * 0.065), radius=t // 80, fill=AZUL_CLARO)
    r = t * 0.17  # selo verde com a seta de exportação
    cx, cy = x0 + w + t * 0.02, y0 + h - t * 0.04
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=VERDE, outline=BRANCO, width=max(t // 64, 1))
    s = r * 0.5
    d.line([(cx, cy - s), (cx, cy + s * 0.7)], fill=BRANCO, width=max(int(t * 0.035), 2))
    d.polygon([(cx - s * 0.75, cy + s * 0.05), (cx + s * 0.75, cy + s * 0.05), (cx, cy + s * 0.95)], fill=BRANCO)
    return img


def _fonte(nome: str, tamanho: int):
    try:
        return ImageFont.truetype(nome, tamanho)
    except OSError:
        return ImageFont.load_default(tamanho)


def desenhar_abertura() -> Image.Image:
    img = Image.new("RGB", (640, 240), (245, 247, 250))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 639, 239), outline=AZUL[:3], width=3)
    img.paste(desenhar_icone(144), (44, 48), desenhar_icone(144))
    d.text((220, 62), "Conversor de Atestados", font=_fonte("segoeuib.ttf", 30), fill=(31, 41, 51))
    d.text((222, 112), "Abrindo… isso leva alguns segundos.", font=_fonte("segoeui.ttf", 19), fill=CINZA[:3])
    d.text((222, 146), "Não precisa clicar de novo.", font=_fonte("segoeui.ttf", 19), fill=CINZA[:3])
    return img


if __name__ == "__main__":
    desenhar_icone().save(AQUI / "icone.ico",
                          sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    desenhar_abertura().save(AQUI / "abertura.png")
    print("imagens gravadas em", AQUI)
