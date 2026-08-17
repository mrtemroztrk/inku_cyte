#!/usr/bin/env python3
"""Atlas'ı kurar: ölçüm → kuyu başına tek, kendi kendine yeten HTML.

    python3 atlas/build.py --check              # tek kuyu, hızlı deneme
    python3 atlas/build.py --measure --jobs 7   # tüm plaka ölçülür (~10 dk)
    python3 atlas/build.py --pages              # ölçümden sayfaları üretir (saniyeler)
    python3 atlas/build.py --all --jobs 7       # ikisi

Ölçüm `atlas/cache/wells/<kuyu>.json`'a yazılır ve yeniden çalıştırmada oradan
okunur (`--force` ile sıfırlanır). Sayfalar `atlas/site/` altına çıkar; hiçbir
dış dosyaya bağlı değiller, çift tıklayınca açılırlar.

Sayfalarda gösterilen her türetilmiş sayı burada, Python'da hesaplanır — tarayıcı
yalnızca çizer. Böylece bir figürdeki değerin nereden geldiği tek bir yerde okunur.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "analysis"))

import extract as E            # noqa: E402
import calib                   # noqa: E402
import measure as M            # noqa: E402
import page as P               # noqa: E402

CACHE = HERE / "cache" / "wells"
SITE = HERE / "site"
EXCLUDED_CSV = ROOT / "analysis" / "out" / "a1_qc" / "excluded_wells.csv"


# --------------------------------------------------------------------- meta
def plate_meta() -> dict:
    pm = pd.read_csv(E.DATA / "plate_map.csv")
    tp = pd.read_csv(E.DATA / "timepoints.csv")
    excluded = set(pd.read_csv(EXCLUDED_CSV).well) if EXCLUDED_CSV.is_file() else set()

    wells = {}
    for r in pm.itertuples():
        w = f"{str(r.well)[0]}{int(str(r.well)[1:]):02d}"
        if str(r.imaged).strip().lower() != "yes":
            continue                                   # sütun 9 görüntülenmedi
        wells[w] = {
            "well": w, "row": str(r.well)[0], "col": int(str(r.well)[1:]),
            "coculture": r.coculture, "compound": r.compound,
            "concentration": (None if pd.isna(r.concentration) else float(r.concentration)),
            "has_tcells": bool(not pd.isna(r.t_cells)),
            "has_macrophages": bool(not pd.isna(r.macrophages)),
            "has_cafs": bool(not pd.isna(r.cafs)),
            "excluded": w in excluded,
        }
    stamps = E.timepoints()
    hours = list(tp.hours_from_start)
    times = [{"t": i, "stamp": s, "hours": round(float(h), 1)}
             for i, (s, h) in enumerate(zip(stamps, hours))]
    return {"wells": wells, "times": times, "excluded": sorted(excluded)}


def imaged_wells() -> list[str]:
    return sorted(w for w in E.all_wells())


# ------------------------------------------------------------------- türetme
def derive(frames: list[dict], cal: dict) -> None:
    """Ölçülen sinyalden raporlanacak büyüklükleri türetir; frames yerinde güncellenir.

    Birincil büyüklük her zaman **ölçülen** olandır: sinyal alanı (mm²) ve voksel
    sayısı. Hücre sayısı türetilmiş bir tahmindir, ayrı alanlarda tutulur ve
    sayfada her zaman "≈" ile işaretlenir.

    Hücre sayma mantığındaki tuzak ve nasıl kapatıldığı
    ---------------------------------------------------
    Kalibrasyon (90,8 µm²/hücre) **MIP alanı** üzerinde tanımlı: z boyunca
    maksimum projeksiyonun maskesi. Katman başına alanlar bundan farklı bir
    büyüklük — toplamları MIP alanını aşar, çünkü 4× objektifin odak derinliği
    onlarca mikron ve aynı hücre birkaç katmanda görünür (bu kuyularda toplam
    tipik olarak MIP alanının 3–5 katı). Katman alanını global ölçeğe bölmek bu
    yüzden hücre sayısını kat kat şişirirdi.

    Katman başına hücre bu nedenle **kuyu toplamının dağıtılmasıdır**:

        hücre(z) = N_toplam × alan(z) / Σ alan(z)

    yani katman payları toplamı tam olarak N_toplam'a eşittir. Bu, bağımsız bir
    ölçüm değil, toplamın z ekseninde dağılımıdır ve figür altyazısında böyle
    yazar. Dönüşüm katsayısı kare başına değişir (`layer_cell_per_mm2`).

    Bant (uzaklık) profilinde böyle bir sorun yok: bantlar MIP maskesinden
    hesaplanıyor, bant alanlarının toplamı MIP alanına birebir eşit, dolayısıyla
    global ölçek doğrudan uygulanabilir.

    Tümör hücreye çevrilmez — kalibrasyon reddedildi (imkânsız hücre boyutu).
    Hacim µm²·katman olarak verilir: z adımı kayıtlı olmadığı için µm³ verilemez,
    z adımıyla çarpılınca µm³ olur.
    """
    per_cell = cal["tcell"]["um2_per_cell"]
    um = calib.UM_PER_PX
    px_mm2 = um ** 2 / 1e6

    for f in frames:
        d = {}
        # --- ölçülen: kanal başına MIP sinyal alanı
        o, g, nr = (f["totals"][c] for c in ("orange", "green", "nir"))
        d["tcell_mm2"] = o["area_mm2"]
        d["tumour_mm2"] = g["area_mm2"]
        d["dead_mm2"] = nr["area_mm2"]
        d["organoid_mm2"] = f["bf"]["terr_mm2"]
        d["tumour_vol_um2layer"] = round(g["vox"] * um ** 2, 0)
        d["tcell_vol_um2layer"] = round(o["vox"] * um ** 2, 0)

        # --- ölçülen: katman başına alan (MIP değil, düzlem maskeleri)
        for key, ch in (("tumour", "green"), ("tcell", "orange"), ("dead", "nir")):
            z = np.asarray(f["by_z"][ch], float)
            d[f"{key}_area_by_z_mm2"] = [round(v * px_mm2, 6) for v in z]
        for key, ch in (("tumour", "green"), ("tcell", "orange"), ("dead", "nir")):
            b = np.asarray(f["bands"][ch]["px"], float)
            d[f"{key}_area_by_band_mm2"] = [round(v * px_mm2, 6) for v in b]

        # --- türetilmiş: hücre sayısı (yalnız T hücresi; tümör reddedildi)
        n_t = o["area_mm2"] * 1e6 / per_cell
        d["tcells"] = round(n_t, 1)
        d["tcells_in_terr"] = (round(n_t * o["frac_in_terr"], 1)
                               if o["frac_in_terr"] is not None else None)
        # bant profili MIP maskesinden geliyor → global ölçek doğrudan geçerli
        d["tcells_by_band"] = [round(v * 1e6 / per_cell, 1)
                               for v in d["tcell_area_by_band_mm2"]]
        # katman profili için dağıtım katsayısı (yukarıdaki gerekçe)
        z_sum = float(np.sum(d["tcell_area_by_z_mm2"]))
        d["layer_cell_per_mm2"] = round(n_t / z_sum, 2) if z_sum > 0 else 0.0
        d["tcells_by_z"] = [round(v * d["layer_cell_per_mm2"], 1)
                            for v in d["tcell_area_by_z_mm2"]]
        # katman alanlarının MIP alanına oranı: odak dışı yayılmanın büyüklüğü,
        # sayfada açıkça raporlanır
        d["z_overcount"] = (round(z_sum / o["area_mm2"], 2)
                            if o["area_mm2"] > 0 else None)
        f["derived"] = d


def well_payload(well: str, meta: dict, cal: dict, force: bool = False) -> dict:
    """Bir kuyunun tüm zaman noktalarını ölçer (veya önbellekten okur).

    Önbellek **yalnızca ölçümü** tutar; türetilmiş büyüklükler (hücre sayısı,
    birim çevrimleri) sayfa üretilirken hesaplanır. Böylece birim kararı
    değiştiğinde 30 dakikalık yeniden ölçüm gerekmiyor — `--pages` yetiyor.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    fp = CACHE / f"{well}.json"
    if fp.is_file() and not force:
        return json.loads(fp.read_text())

    frames = [M.measure_frame(well, t["stamp"], t["t"]) for t in meta["times"]]
    pay = {"well": well, "meta": meta["wells"][well], "times": meta["times"],
           "frames": frames,
           "um_per_px": calib.UM_PER_PX, "voxel_um": round(calib.UM_PER_PX * M.BIN_VOX, 3)}
    fp.write_text(json.dumps(pay, ensure_ascii=False, separators=(",", ":")))
    return pay


def load_derived(well: str, cal: dict, with_thumbs: bool = False) -> dict | None:
    """Önbellekteki ölçümü okur ve türetilmiş büyüklükleri ekler.

    `with_thumbs` verilirse kanıt küçük resimleri de eklenir (varsa): sayfada bir
    katmana tıklandığında o katmanın gerçek fotoğrafı açılsın diye.
    """
    fp = CACHE / f"{well}.json"
    if not fp.is_file():
        return None
    pay = json.loads(fp.read_text())
    derive(pay["frames"], cal)
    pay["calibration"] = cal
    if with_thumbs:
        import thumbs
        th = thumbs.load(well)
        if th:
            pay["thumbs"] = th
    return pay


def _job(a):
    well, meta, cal, force = a
    t0 = time.time()
    try:
        pay = well_payload(well, meta, cal, force)
        return well, len(json.dumps(pay)), time.time() - t0, None
    except Exception as exc:                                   # noqa: BLE001
        return well, 0, time.time() - t0, f"{type(exc).__name__}: {exc}"


# ------------------------------------------------------------------- özetler
def plate_summary(meta: dict, cal: dict) -> dict:
    """Plaka sayfası için kuyu başına birkaç sayı — ölçüm önbelleğinden okunur."""
    rows = []
    for w in sorted(meta["wells"]):
        pay = load_derived(w, cal)
        if pay is None:
            continue
        last = pay["frames"][-1]
        first = pay["frames"][0]
        m = pay["meta"]
        rows.append({
            **{k: m[k] for k in ("well", "row", "col", "coculture", "compound",
                                 "concentration", "has_tcells", "excluded")},
            "organoid_mm2": last["derived"]["organoid_mm2"],
            "growth": (round(last["derived"]["organoid_mm2"] / first["derived"]["organoid_mm2"], 2)
                       if first["derived"]["organoid_mm2"] > 0 else None),
            "tcells": last["derived"]["tcells"],
            "t_enrich": last["totals"]["orange"]["enrich_terr"],
            "dead_mm2": last["derived"]["dead_mm2"],
            "dome_dominant": bool(last["dome"] and last["dome"]["dominant"]),
            "dome_r90_um": (last["dome"] or {}).get("r90_um"),
        })
    return {"wells": rows, "times": meta["times"], "calibration": cal,
            "excluded": meta["excluded"]}


# ---------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--measure", action="store_true", help="plakayı ölç")
    ap.add_argument("--pages", action="store_true", help="sayfaları üret")
    ap.add_argument("--all", action="store_true", help="ikisi")
    ap.add_argument("--check", action="store_true", help="tek kuyu deneme (B04)")
    ap.add_argument("--wells", help="virgülle ayrılmış kuyu listesi")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 1))
    ap.add_argument("--force", action="store_true", help="önbelleği yok say")
    args = ap.parse_args()

    if not any([args.measure, args.pages, args.all, args.check, args.wells]):
        ap.print_help()
        return

    meta = plate_meta()
    cal = calib.load(refresh=args.force)
    if not cal["tcell"]["accepted"]:
        raise SystemExit("T hücresi kalibrasyonu doğrulama testlerini geçemedi — "
                         "atlas/calib.py çıktısına bakın.")

    if args.check:
        wells = ["B04"]
    elif args.wells:
        wells = [w.strip() for w in args.wells.split(",")]
    else:
        wells = imaged_wells()

    if args.measure or args.all or args.check or args.wells:
        todo = [w for w in wells if args.force or not (CACHE / f"{w}.json").is_file()]
        print(f"[ölçüm] {len(todo)}/{len(wells)} kuyu  ·  {args.jobs} iş  ·  "
              f"kuyu başına 13 zaman noktası")
        if todo:
            jobs = [(w, meta, cal, args.force) for w in todo]
            t0 = time.time()
            done = 0
            with ProcessPoolExecutor(max_workers=args.jobs) as ex:
                for well, size, dt, err in ex.map(_job, jobs):
                    done += 1
                    if err:
                        print(f"  ✗ {well}: {err}")
                    else:
                        eta = (time.time() - t0) / done * (len(todo) - done)
                        print(f"  {well}  {size / 1e6:.2f} MB  {dt:.0f}s"
                              f"   [{done}/{len(todo)}  ~{eta / 60:.0f} dk kaldı]", flush=True)
            print(f"[ölçüm] bitti, {(time.time() - t0) / 60:.1f} dk")

    if args.pages or args.all or args.check or args.wells:
        SITE.mkdir(parents=True, exist_ok=True)
        built = []
        for w in wells:
            pay = load_derived(w, cal, with_thumbs=True)
            if pay is None:
                continue
            out = SITE / f"{w}.html"
            out.write_text(P.well_page(pay), encoding="utf-8")
            built.append((w, out.stat().st_size))
        summ = plate_summary(meta, cal)
        (SITE / "index.html").write_text(P.index_page(summ), encoding="utf-8")
        tot = sum(s for _, s in built)
        print(f"[sayfa] {len(built)} kuyu + plaka  ·  toplam {tot / 1e6:.1f} MB  ·  "
              f"kuyu başına ort. {tot / max(len(built), 1) / 1e6:.2f} MB")

        # Grup karşılaştırmaları tüm kuyuları görmek zorunda; kısmi bir ölçümle
        # üretilirse istatistik yanıltıcı olur.
        if len(built) >= len(imaged_wells()):
            import figures
            import groups
            g = groups.build()
            (SITE / "groups.html").write_text(
                P.groups_page(g, figures.build_all(g)), encoding="utf-8")
            print(f"[sayfa] grup karşılaştırmaları: {g['n_wells']} kuyu "
                  f"({g['n_excluded']} QC dışı)")
        else:
            print(f"[sayfa] grup karşılaştırmaları atlandı — {len(built)}/"
                  f"{len(imaged_wells())} kuyu ölçülmüş")
        print(f"[sayfa] aç: {SITE / 'index.html'}")


if __name__ == "__main__":
    main()
