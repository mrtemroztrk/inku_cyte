#!/usr/bin/env python3
"""Üretilen sayfaların denetimi — tarayıcı açmadan yakalanabilecek her şey.

Bu dosya bir güvence değil, bir ağ: sayfayı gerçekten açıp bakmanın yerine
geçmez, ama sessizce boş kalan bir figürün ya da yanlış yazılmış bir id'nin
oraya kadar gitmesini engeller.

    python3 atlas/selftest.py               # atlas/site içindeki tüm sayfalar
    python3 atlas/selftest.py B04.html
    python3 atlas/selftest.py --vs-analysis # ölçümü analysis/ hattına karşı denetle
"""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import esprima

SITE = Path(__file__).resolve().parent / "site"


class Collect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.classes: set[str] = set()
        self.data: set[tuple[str, str]] = set()
        self.scripts: list[str] = []
        self._in_script = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        for c in (a.get("class") or "").split():
            self.classes.add(c)
        for k, v in a.items():
            if k.startswith("data-"):
                self.data.add((k, v or ""))
        if tag == "script":
            self._in_script = True
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "script" and self._in_script:
            self.scripts.append("".join(self._buf))
            self._in_script = False

    def handle_data(self, d):
        if self._in_script:
            self._buf.append(d)


def check(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    errs: list[str] = []
    p = Collect()
    p.feed(src)

    # 1. gömülü veri geçerli JSON mı. Atamalar `window.X={…};` biçiminde ve tek
    #    satırda yazılıyor; JSON çözücü fazlalıkta durduğu için sınırı o veriyor.
    for var in ("DATA", "SUMM", "GROUPS", "CHECK", "VOX", "THEME"):
        i = src.find(f"window.{var}=")
        if i < 0:
            continue
        raw = src[i + len(f"window.{var}="):]
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw)
        except Exception as exc:                                   # noqa: BLE001
            errs.append(f"window.{var} JSON olarak çözülemiyor: {exc}")
            continue
        if var == "DATA":
            errs += check_payload(obj)

    # 2. JS sözdizimi
    for i, s in enumerate(p.scripts):
        if not s.strip() or s.strip().startswith("window."):
            continue
        try:
            esprima.parseScript(s)
        except Exception as exc:                                   # noqa: BLE001
            errs.append(f"script[{i}] sözdizimi: {exc}")

    # 3. JS'in aradığı her id/selector belgede var mı
    js = "\n".join(p.scripts)
    for sel in set(re.findall(r'getElementById\("([^"]+)"\)', js)) | \
               set(re.findall(r'\$\("#([^"]+)"\)', js)) | \
               set(re.findall(r'querySelector\("#([^"]+)"\)', js)):
        base = sel.split(" ")[0]
        if base not in p.ids and not base.startswith(("q_", "fig_", "tbl_")):
            errs.append(f'JS #{sel} arıyor, belgede yok')
    # 4. JS'in beklediği data-* öznitelikleri
    for attr in set(re.findall(r'querySelectorAll\("\[data-([a-z]+)\]"\)', js)):
        if not any(k == f"data-{attr}" for k, _ in p.data):
            errs.append(f"[data-{attr}] seçiliyor ama belgede yok")

    # 5. şablon kaçağı — yalnızca <script> dışındaki gövdede. Script içindeki
    #    `${…}` JS şablon değişkenidir, Python'dan kaçmış bir alan değil.
    body = re.sub(r"<script\b.*?</script>", "", src, flags=re.S)
    body = re.sub(r"<style\b.*?</style>", "", body, flags=re.S)
    for m in set(re.findall(r"(?<!\$)\{[a-z_][a-z_0-9]*\}", body)):
        errs.append(f"biçimlenmemiş şablon alanı kalmış: {m}")
    return errs


def check_payload(d: dict) -> list[str]:
    """Sayfanın çizeceği alanlar gerçekten dolu mu."""
    e: list[str] = []
    need = ("well", "meta", "times", "frames", "calibration", "voxel_um", "band_labels")
    for k in need:
        if k not in d:
            e.append(f"DATA.{k} yok")
    if e:
        return e
    if len(d["frames"]) != len(d["times"]):
        e.append(f"kare sayısı {len(d['frames'])} ≠ zaman noktası {len(d['times'])}")
    nb = len(d["band_labels"])
    for f in d["frames"]:
        tag = f"t{f['t']:02d}"
        for k in ("vox", "derived", "by_z", "zband", "bands", "totals", "grid",
                  "terr_map", "terr_shape", "band_area_mm2"):
            if k not in f:
                e.append(f"{tag}: {k} yok")
        if "derived" not in f:
            continue
        dv = f["derived"]
        nz = f["grid"]["nz"]
        for k in ("tcells_by_z", "tumour_area_by_z_mm2", "dead_area_by_z_mm2"):
            if len(dv[k]) != nz:
                e.append(f"{tag}: {k} uzunluğu {len(dv[k])} ≠ {nz} katman")
        if len(dv["tcells_by_band"]) != nb:
            e.append(f"{tag}: tcells_by_band {len(dv['tcells_by_band'])} ≠ {nb} bant")
        if len(f["band_area_mm2"]) != nb:
            e.append(f"{tag}: band_area_mm2 {len(f['band_area_mm2'])} ≠ {nb} bant")
        for ch in ("green", "orange", "nir"):
            if len(f["bands"][ch]["enrich"]) != nb:
                e.append(f"{tag}/{ch}: bant sayısı tutmuyor")
            if len(f["zband"][ch]) != nz:
                e.append(f"{tag}/{ch}: zband satır sayısı {len(f['zband'][ch])} ≠ {nz}")
            elif any(len(r) != nb for r in f["zband"][ch]):
                e.append(f"{tag}/{ch}: zband sütun sayısı tutmuyor")
            if not f["vox"].get(ch):
                e.append(f"{tag}/{ch}: voksel paketi boş")
        # ölçüm ile türetme tutarlılığı: paylar toplamı toplam sayıya eşit olmalı
        tot = dv["tcells"]
        s_z, s_b = sum(dv["tcells_by_z"]), sum(dv["tcells_by_band"])
        for name, s in (("katman", s_z), ("bant", s_b)):
            if tot > 0 and abs(s - tot) / tot > 0.02:
                e.append(f"{tag}: T hücresi {name} dağılımı toplamı {s:.0f} ≠ {tot:.0f}")
    return e


def check_against_analysis() -> list[str]:
    """Atlas ölçümü `analysis/` hattıyla aynı sayıyı veriyor mu.

    Aynı eşikler ve aynı maskeler kullanıldığı için bu bir tercih değil, bir
    zorunluluk: iki yerde iki farklı sayı çıkıyorsa biri yanlıştır. Bu kontrol
    bir kez gerçek bir hata yakaladı — zenginleşme, oran yuvarlandıktan sonra
    hesaplanıyordu ve küçük oranlarda %60'ı aşan bağıl hata veriyordu.
    """
    import pandas as pd

    root = Path(__file__).resolve().parent.parent
    feat = root / "viewer" / "cache" / "features" / "features.csv"
    cache = Path(__file__).resolve().parent / "cache" / "wells"
    if not feat.is_file() or not any(cache.glob("*.json")):
        return []

    f = pd.read_csv(feat).set_index(["well", "t"])
    errs, n = [], 0
    for fp in sorted(cache.glob("*.json")):
        pay = json.loads(fp.read_text())
        for fr in pay["frames"]:
            key = (pay["well"], fr["t"])
            if key not in f.index:
                continue
            ref = f.loc[key]
            n += 1
            pairs = [("bf_terr_frac", fr["bf"]["terr_frac"], 1e-9)]
            for ch in ("green", "orange", "nir"):
                pairs += [(f"{ch}_area_frac", fr["totals"][ch]["area_frac"], 1e-9),
                          (f"{ch}_enrich_organoid", fr["totals"][ch]["enrich_terr"], 2e-3)]
            for col, got, tol in pairs:
                exp = ref[col]
                if got is None or pd.isna(exp):
                    continue
                if abs(float(got) - float(exp)) > tol:
                    errs.append(f"{key[0]} t{key[1]:02d} {col}: atlas {got} ≠ analiz {exp}")
    if errs:
        errs = errs[:10] + ([f"… {len(errs) - 10} sapma daha"] if len(errs) > 10 else [])
    print(f"\n{n} örnek `analysis/` hattına karşı denetlendi — "
          f"{'✓ hepsi eşit' if not errs else '✗ sapma var'}")
    return errs


def main() -> None:
    if "--vs-analysis" in sys.argv:
        e = check_against_analysis()
        for x in e:
            print("   ", x)
        sys.exit(1 if e else 0)

    targets = ([SITE / a for a in sys.argv[1:]] if len(sys.argv) > 1
               else sorted(SITE.glob("*.html")) + sorted(SITE.glob("check/*.html")))
    if not targets:
        raise SystemExit("atlas/site altında sayfa yok — önce: python3 atlas/build.py --all")
    bad = 0
    for p in targets:
        errs = check(p)
        mb = p.stat().st_size / 1e6
        if errs:
            bad += 1
            print(f"✗ {p.relative_to(SITE)}  ({mb:.2f} MB)")
            for x in errs[:12]:
                print(f"    {x}")
            if len(errs) > 12:
                print(f"    … {len(errs) - 12} sorun daha")
        else:
            print(f"✓ {p.relative_to(SITE)}  ({mb:.2f} MB)")
    print(f"\n{len(targets) - bad}/{len(targets)} sayfa temiz")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
