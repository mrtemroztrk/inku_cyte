#!/usr/bin/env python3
"""Atlas'ın görsel dili: renkler, yüzeyler, kanal adları.

Kanal renkleri neden mikroskop renkleri değil
---------------------------------------------
Alışılmış floresan üçlüsü (yeşil tümör, turuncu T hücresi, kırmızı ölü hücre)
denetimden geçemiyor (`python3 atlas/palette_check.py`):

    yeşil #008300 ↔ turuncu #eb6834   protan ΔE = 3,2   (taban 6,0)
    turuncu #eb6834 ↔ kırmızı #e34948  normal görüş ΔE = 7,1  (taban 15,0)

Yani kırmızı-kör bir okur tümör ile T hücresini ayıramıyor, ve turuncu ile
kırmızı tam renk görüşte bile ayrılmıyor. Erkek okurların ~%8'i için figür
okunamaz demektir; makaleye giren bir figürde bu bir kusurdur.

Kullanılan üçlü her iki modda da bütün eşikleri geçiyor (en kötü çift: protan
ΔE 12,6 açık / 9,4 koyu; normal görüş 24,6 / 24,6). Yeşil yerine deniz yeşili,
kırmızı yerine mor — yeşil/magenta ikamesinin mikroskopide yerleşik olmasıyla
aynı gerekçe. Renk yine de tek başına taşıyıcı değil: her seri doğrudan
etiketlenir ve tablo görünümü her figürde var.

Aynı şey her yerde aynı renk: 3B sahne ve figürler aynı hue'ları kullanır,
yalnızca zemine göre adımı değişir.
"""
from __future__ import annotations

# --- yüzeyler
SURFACE_FIG = "#fcfcfb"        # sayfa ve figür zemini
SURFACE_SCENE = "#0e1013"      # 3B sahne (floresan için koyu doğru olan)

INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8983"
RULE = "#e6e5e1"
RULE2 = "#d3d2cd"

# --- kanal kimliği
CHANNELS = ("green", "orange", "nir")

CH_LABEL = {"green": "tümör", "orange": "T hücresi", "nir": "ölü hücre"}
# Sayfa metni İngilizce (çıktı dergiye gidiyor); kod yorumları Türkçe kalıyor.
CH_LABEL_EN = {"green": "tumour", "orange": "T cells", "nir": "dead cells"}
CH_SOURCE = {"green": "Green_Zstacks", "orange": "Orange_Tcells", "nir": "NIR_deadCells"}
CH_UNIT = {"green": "mm² sinyal alanı", "orange": "≈ hücre", "nir": "mm² sinyal alanı"}

# doğrulanmış: dataviz referans paleti slot 3 (aqua), 2 (orange), 7 (violet)
CH_FIG = {"green": "#1baf7a", "orange": "#eb6834", "nir": "#4a3aa7"}
CH_SCENE = {"green": "#199e70", "orange": "#d95926", "nir": "#9085e9"}

# BF organoid teritoryası seri değil, bağlam katmanı — nötr.
TERR_FIG = "#b8b7b2"
TERR_SCENE = "#5a6270"

# sıralı ölçek (derinlik × uzaklık matrisi): tek hue, açık→koyu
SEQ = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
       "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]

# ıraksak ölçek (zenginleşme: 1,0 = rastgele, nötr orta nokta)
DIV_LO = ["#0d366b", "#184f95", "#256abf", "#3987e5", "#86b6ef", "#cde2fb"]
DIV_MID = "#f0efec"
DIV_HI = ["#f6c9c8", "#f0a6a5", "#e87b7a", "#e34948", "#c22e2d", "#9c1f1e"]

FONT = ('ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, '
        '"Helvetica Neue", Arial, sans-serif')
MONO = 'ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace'
