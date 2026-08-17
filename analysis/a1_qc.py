#!/usr/bin/env python3
"""A1 — Kalite kontrolü ve boyama kapsamı.

İki soru:

1. **Hangi kuyular yorumlanabilir?** Yapı, aydınlatma ve konfluens açısından her
   kuyu-zaman noktası bayraklanır. Bir kuyu zaman noktalarının çoğunda ölümcül
   bayrak taşıyorsa dışlama listesine girer; sonraki analizler
   `excluded_wells.csv`'yi okur. Dışlama listesi kasten dar tutuldu — yanlış bir
   QC ölçütü, en ilginç kuyuları (hızlı büyüyen, sıkı sferoid oluşturanlar)
   sistematik olarak eleyebiliyor.

2. **Green tüm organoidleri boyuyor mu?** Brightfield'da görülen organoidlerin
   yüzde kaçında green sinyali var? Bu, "yeşil = tümör" varsayımının ne kadar
   eksik olduğunu doğrudan ölçer ve green tabanlı her sayımın alt sınırını verir.

Çıktı: analysis/out/a1_qc/
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import (UM_PER_PX, COCULTURE_COLOR, COCULTURE_ORDER, DIV, GRID, INK, INK2, MUTED,
                    SEQ, SERIES, STATUS, boot_ci, finish, load, load_organoids,
                    outdir, plate_grid, strip, timeseries, write_summary)
import matplotlib.pyplot as plt

OUT = outdir("a1_qc")

# QC eşikleri — plaka genelindeki dağılımdan seçildi, mutlak bir standarttan değil.
#
# BF Laplace varyansı burada bir *odak* ölçüsü değil: kuyu büyüdükçe yükseliyor
# (kütleyle sıra korelasyonu 0,83; B04'te 4 günde 639 → 2809). Yani "kuyunun kendi
# en iyisine göre düşük" ölçütü hızlı büyüyen kuyuların erken karelerini bayraklar,
# bulanık kareleri değil. Bunun yerine **mutlak taban** kullanılıyor: bu değerin
# altındaki kareler yapısız bir alan gösteriyor (odak dışı ya da gerçekten boş) ve
# morfoloji ölçülemiyor.
STRUCT_MIN = 30.0       # Laplace varyansı; plaka 1. yüzdeliği ≈ 9, 5. yüzdeliği ≈ 62
FLOOR_OFF_MAX = 5.0     # gri seviye; zemin 128'den bu kadar saparsa aydınlatma anormal
CONFLUENT_MAX = 0.90    # teritorya bu oranı geçerse "içeride/dışarıda" anlamsız


def main():
    df = load()
    org = load_organoids()
    lines: list[str] = []

    # ---------------------------------------------------------------- 1. QC
    df = df.copy()
    df["flag_nostruct"] = df.bf_focus < STRUCT_MIN
    df["flag_floor"] = df.bf_floor_offset.abs() > FLOOR_OFF_MAX
    df["flag_confluent"] = df.bf_terr_frac > CONFLUENT_MAX
    flags = ["flag_nostruct", "flag_floor", "flag_confluent"]
    fatal = ["flag_nostruct", "flag_floor"]
    df["flag_any"] = df[flags].any(axis=1)
    df["flag_fatal"] = df[fatal].any(axis=1)

    per_well = df.groupby("well").agg(
        n=("t", "size"), **{f: (f, "mean") for f in flags + ["flag_any", "flag_fatal"]},
        focus_med=("bf_focus", "median"), floor_off=("bf_floor_offset", "median"),
        terr=("bf_terr_frac", "median"), bgdrift=("orange_bg_drift", "median"),
        coculture=("coculture", "first"), compound=("compound", "first"),
        tcells=("has_tcells", "first")).reset_index()
    # Bir kuyu zaman noktalarının yarısından çoğunda ölümcül bayraklıysa dışlanır.
    per_well["excluded"] = per_well.flag_fatal > 0.5
    per_well["reason"] = per_well.apply(
        lambda r: ",".join(f[5:] for f in fatal if r[f] > 0.5) or "", axis=1)
    per_well.to_csv(OUT / "well_qc.csv", index=False)
    exc = per_well[per_well.excluded]
    exc[["well", "reason", "coculture", "compound"]].to_csv(
        OUT / "excluded_wells.csv", index=False)

    n_ex = len(exc)
    conf = per_well[per_well.flag_confluent > 0.5]
    lines += [
        "## 1. Kullanılabilirlik",
        "",
        f"88 görüntülenen kuyudan **{n_ex} tanesi** dışlandı. Dışlama ölçütü dar "
        "tutuldu: yalnızca görüntünün kendisini kullanılamaz kılan iki bayrak "
        "(odak ve aydınlatma) dışlama sebebi. Konfluens ölçümü bozmaz, yalnızca "
        "konum ölçümlerini anlamsızlaştırır; ayrı işaretlenir.",
        "",
        "| bayrak | ne demek | dışlar mı | bayraklı kuyu | bayraklı kare |",
        "|---|---|---|---|---|",
    ]
    names = {"flag_nostruct": (f"BF yapı puanı < {STRUCT_MIN:.0f} — yapısız alan "
                               "(odak dışı ya da boş)", "evet"),
             "flag_floor": (f"BF zemini 128'den >{FLOOR_OFF_MAX:.0f} gri seviye sapmış", "evet"),
             "flag_confluent": (f"BF teritoryası alanın >%{CONFLUENT_MAX*100:.0f}'ini kaplıyor",
                                "hayır — konum ölçümü geçersiz")}
    for f in flags:
        d, ex_ = names[f]
        lines.append(f"| `{f[5:]}` | {d} | {ex_} | {int((per_well[f] > 0.5).sum())} | "
                     f"{int(df[f].sum())} / {len(df)} |")
    if n_ex:
        lines += ["", "Dışlananlar: " + ", ".join(
            f"**{r.well}** ({r.reason})" for r in exc.itertuples())]
    if len(conf):
        lines += ["", "Konfluent (içeride/dışarıda ayrımı anlamsız): " +
                  ", ".join(f"**{r.well}**" for r in conf.itertuples())]
    lines += ["",
              "BF yapı puanı (Laplace varyansı) bir **odak ölçüsü değil**: kuyu "
              f"büyüdükçe yükseliyor (kütleyle sıra korelasyonu "
              f"{df.bf_focus.corr(df.bf_terr_frac, method='spearman'):.2f}). "
              "Bu yüzden \"kuyunun kendi en iyisine göre düşük\" gibi göreli bir "
              "ölçüt hızlı büyüyen kuyuların erken karelerini bayraklardı — o ölçüt "
              "kullanılmadı; yerine mutlak bir taban kondu.",
              "",
              f"Orange arkaplanı z boyunca medyan {per_well.bgdrift.median():.2f} birim "
              f"kayıyor (en yüksek {per_well.bgdrift.max():.2f}). Bu kayma bir kusur "
              "değil — z boyunca odak dışı sis miktarı değişir — ve düzlem başına "
              "medyan çıkarıldığı için ölçümlere geçmiyor; buraya yalnızca kayıt "
              "için yazıldı."]

    # Dye kolonları ayrı bir gözlem: bunlar boya kontrolü, biyolojik karşılaştırma değil
    dye = df[df.compound == "Dye"]
    nondye = df[df.compound != "Dye"]
    lines += ["",
              f"Dye kontrol kuyuları (kolon 10–12, {dye.well.nunique()} kuyu) BF'de "
              f"medyan {dye.bf_terr_frac.median()*100:.1f}% teritorya gösteriyor; "
              f"diğer kuyularda bu {nondye.bf_terr_frac.median()*100:.1f}%. "
              f"Yapı puanı medyanı {dye.bf_focus.median():.0f} vs {nondye.bf_focus.median():.0f}. "
              "Bu kolonlar belirgin biçimde odak dışı ve seyrek — boya kontrolü olarak "
              "kullanılabilirler ama morfoloji karşılaştırmasına girmemeliler."]

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.4))
    plate_grid(axes[0], per_well.set_index("well").focus_med.to_dict(),
               "BF yapı puanı (medyan)", cmap=SEQ, fmt="{:.0f}", label="Laplace varyansı")
    plate_grid(axes[1], per_well.set_index("well").terr.to_dict(),
               "BF teritorya payı (medyan)", cmap=SEQ, fmt="{:.2f}", label="alan oranı")
    plate_grid(axes[2], per_well.set_index("well").flag_any.to_dict(),
               "bayraklı kare oranı", cmap=SEQ, vmin=0, vmax=1, fmt="{:.1f}",
               label="oran")
    fig.suptitle("Plaka QC — kolon 9 görüntülenmedi", x=0.02, ha="left", weight="bold")
    finish(fig, OUT / "qc_plate.png",
           "Yapı puanı = BF Laplace varyansı; kütleyle birlikte artar, odak ölçüsü değil. Kolon 10–12 Dye kontrolleri.")

    # ---------------------------------------------- 2. green boyama kapsamı
    last = df[df.t == df.t.max()]
    ok = last[~last.well.isin(exc.well)]
    lines += ["", "## 2. Green tüm organoidleri boyamıyor", ""]

    cov = ok.green_pos_organoid_frac_001.dropna()
    lines += [
        f"Son zaman noktasında, QC'den geçen {len(ok)} kuyuda brightfield'da ayırt "
        f"edilen organoidlerin medyan **%{cov.median()*100:.0f}**'inde green sinyali var "
        f"(kapsama >%1 eşiği; çeyrekler %{cov.quantile(.25)*100:.0f}–"
        f"%{cov.quantile(.75)*100:.0f}). Yani BF'de organoid olarak görülen "
        f"nesnelerin çoğunluğunun green kanalında karşılığı yok.",
        "",
        "Bunun iki olası nedeni var ve veri ikisini ayırmıyor:",
        "",
        "1. **Boyama eksik** — organoid var, boya girmemiş.",
        "2. **BF nesnesi tümör değil** — CAF/makrofaj kümesi, döküntü veya ölü madde "
        "de BF'de koyu görünür ve green ile boyanmaz.",
        "",
        "İkisini ayıran gözlem: PDA'nın tek başına olduğu kuyularda BF nesnelerinin "
        "yalnızca bir kısmı green-pozitif olmalıydı ancak *tüm* nesneler tümör olmalı. "
        "Ölçüm:",
    ]
    for cc in COCULTURE_ORDER:
        d = ok[ok.coculture == cc]
        if d.empty:
            continue
        v = d.green_pos_organoid_frac_001.dropna()
        lines.append(f"- **{cc}** ({len(d)} kuyu): green-pozitif organoid oranı medyan "
                     f"%{v.median()*100:.0f}, organoid başına medyan green kapsaması "
                     f"%{d.organoid_med_green_cov.median()*100:.1f}")
    pda = ok[ok.coculture == "PDA"].green_pos_organoid_frac_001.dropna()
    lines += ["",
              f"PDA-tek kuyularda ({len(pda)} kuyu) bile oran "
              f"%{pda.median()*100:.0f} — orada tümör dışı "
              "hücre tipi yok, dolayısıyla eksikliğin **en azından bir kısmı gerçekten "
              "boyanmamış organoid**. Green kanalına dayanan her tümör sayımı bu kadar "
              "eksik sayıyor demektir; tümör kütlesi için BF teritoryası, boyanma durumu "
              "için green kullanılmalı."]

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    ax = axes[0]
    strip(ax, [(cc, ok[ok.coculture == cc].green_pos_organoid_frac_001.dropna() * 100)
               for cc in COCULTURE_ORDER],
          colors=[COCULTURE_COLOR[c] for c in COCULTURE_ORDER])
    ax.set_ylabel("green-pozitif organoid %")
    ax.set_title("BF organoidlerinin kaçı green-pozitif")
    ax.set_ylim(0, 100)
    ax.tick_params(axis="x", labelrotation=20)

    ax = axes[1]
    timeseries(ax, df[~df.well.isin(exc.well)], "green_pos_organoid_frac_001",
               "coculture", COCULTURE_ORDER, COCULTURE_COLOR)
    ax.set_ylabel("green-pozitif organoid oranı")
    ax.set_title("Zaman içinde boyama kapsamı")
    ax.legend(loc="upper left", ncols=2)

    ax = axes[2]
    o = org[(org.t == org.t.max()) & (~org.well.isin(exc.well))]
    bins = np.geomspace(max(o.eq_diam_px.min(), 8), o.eq_diam_px.max(), 18)
    o = o.assign(b=pd.cut(o.eq_diam_px, bins))
    g = o.groupby("b", observed=True).agg(pos=("green_cov", lambda s: (s > 0.01).mean()),
                                          n=("green_cov", "size"))
    mid = np.sqrt(bins[:-1] * bins[1:])[: len(g)]
    ax.plot(mid, g.pos.values * 100, color=SERIES[0], marker="o", ms=5)
    ax.set_xscale("log")
    ax.set_xlabel("organoid eşdeğer çapı (piksel)")
    ax.set_ylabel("green-pozitif %")
    ax.set_title("Küçük organoidler daha sık boyasız")
    ax.set_ylim(0, 100)
    finish(fig, OUT / "staining_coverage.png",
           "Green-pozitif = organoidin alanının >%1'i green eşiğinin üstünde. "
           "Son zaman noktası; QC'den geçen kuyular.")

    lo_px, hi_px = 36.0, 71.0          # eşikler piksel cinsinden sabit
    small = o[o.eq_diam_px < lo_px]
    big = o[o.eq_diam_px >= hi_px]
    lines += ["",
              f"Boyutla ilişki net: <{lo_px:.0f} px ({lo_px*UM_PER_PX:.0f} µm) "
              f"organoidlerin %{(small.green_cov>0.01).mean()*100:.0f}'i, "
              f"≥{hi_px:.0f} px ({hi_px*UM_PER_PX:.0f} µm) olanların "
              f"%{(big.green_cov>0.01).mean()*100:.0f}'i green-pozitif "
              f"({len(small)} ve {len(big)} organoid). Küçük nesnelerin bir bölümü "
              "muhtemelen tek hücre/döküntü; büyük olanlarda bile kayıp sıfır değil."]

    # ------------------------------------------------- 3. eşik duyarlılığı
    lines += ["", "## 3. Eşik duyarlılığı", ""]
    r = []
    for ch in ("green", "orange", "nir"):
        a = ok[f"{ch}_area_frac"]
        pos = a > 0                       # NIR bazı kuyularda tümüyle boş
        # kat değişim kuyu başına hesaplanıp medyanı alınır (medyanların oranı değil)
        flo = (ok.loc[pos, f"{ch}_area_frac_lo"] / a[pos]).median()
        fhi = (ok.loc[pos, f"{ch}_area_frac_hi"] / a[pos]).median()
        r.append((ch, a.median(), int(pos.sum()), flo, fhi,
                  a.corr(ok[f"{ch}_area_frac_lo"], method="spearman"),
                  a.corr(ok[f"{ch}_area_frac_hi"], method="spearman")))
    lines += ["Eşik ×0,67 ve ×1,67 kaydırıldığında alan oranı değişiyor ama kuyu "
              "**sıralaması** korunuyor — karşılaştırmalar eşik seçimine dayanıklı:",
              "", "| kanal | alan oranı (ana eşik) | sinyalli kuyu | ×0,67'de kaç kat | "
              "×1,67'de kaç kat | sıra kor. (düşük) | (yüksek) |",
              "|---|---|---|---|---|---|---|"]
    for ch, m, npos, flo, fhi, rlo, rhi in r:
        lines.append(f"| {ch} | {m*100:.3f}% | {npos}/{len(ok)} | {flo:.2f}× | "
                     f"{fhi:.2f}× | {rlo:.3f} | {rhi:.3f} |")

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4))
    for ax, ch in zip(axes, ("green", "orange", "nir")):
        ax.scatter(ok[f"{ch}_area_frac"] * 100, ok[f"{ch}_area_frac_lo"] * 100,
                   s=18, color=SERIES[0], alpha=0.7, label="eşik ×0,67",
                   edgecolors="none")
        ax.scatter(ok[f"{ch}_area_frac"] * 100, ok[f"{ch}_area_frac_hi"] * 100,
                   s=18, color=SERIES[1], alpha=0.7, label="eşik ×1,67",
                   edgecolors="none")
        lim = [max(ok[f"{ch}_area_frac"].min() * 100, 1e-3),
               ok[f"{ch}_area_frac_lo"].max() * 100]
        ax.plot(lim, lim, color=MUTED, ls="--", lw=1)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("alan oranı % (ana eşik)")
        ax.set_title(ch)
        if ch == "green":
            ax.set_ylabel("alan oranı % (kaydırılmış)")
            ax.legend(loc="upper left")
    finish(fig, OUT / "threshold_sensitivity.png",
           "Noktalar kuyular (son zaman noktası). Kesik çizgi = birebir.")

    # ----------------------------------------------------- 4. arkaplan kayması
    lines += ["", "## 4. Arkaplan ve pozlama kayması", "",
              "Floresan kanalların arkaplanı kuyudan kuyuya ve zaman içinde kayıyor; "
              "bu yüzden tüm ölçümler düzlem başına medyan çıkarıldıktan sonra yapıldı. "
              "Kalan kayma:"]
    for ch in ("green", "orange", "nir"):
        b = ok[f"{ch}_bg_med"]
        lines.append(f"- **{ch}**: kuyular arası arkaplan {b.min():.1f}–{b.max():.1f} "
                     f"(medyan {b.median():.1f}); z boyunca kayma medyanı "
                     f"{ok[f'{ch}_bg_drift'].median():.2f} birim")

    fig, axes = plt.subplots(1, 4, figsize=(14, 3.2))
    for i, ch in enumerate(("green", "orange", "nir")):
        ax = axes[i]
        g = df.groupby("day")[f"{ch}_bg_med"]
        ax.plot(g.median().index, g.median().values, color=SERIES[i])
        ax.fill_between(g.median().index, g.quantile(.25), g.quantile(.75),
                        color=SERIES[i], alpha=0.13, linewidth=0)
        ax.set_ylabel(f"{ch} arkaplanı (ham birim)")
        ax.set_xlabel("gün")
        ax.set_title(f"{ch} arkaplanı")
    ax = axes[3]
    g = df.groupby("day").bf_focus.median()
    ax.plot(g.index, g.values, color=SERIES[0])
    ax.fill_between(g.index, df.groupby("day").bf_focus.quantile(.25),
                    df.groupby("day").bf_focus.quantile(.75), color=SERIES[0],
                    alpha=0.13, linewidth=0)
    ax.set_ylabel("BF yapı puanı")
    ax.set_xlabel("gün")
    ax.set_title("Yapı puanının zaman seyri (plaka medyanı)")
    finish(fig, OUT / "background_drift.png")

    write_summary(OUT / "summary.md", "A1 — Kalite kontrolü ve boyama kapsamı", lines)


if __name__ == "__main__":
    main()
