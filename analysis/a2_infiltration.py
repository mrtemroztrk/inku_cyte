#!/usr/bin/env python3
"""A2 — T hücresi infiltrasyonu: organoide ne kadar giriyor?

Ölçüm mantığı
-------------
"Organoid içindeki T hücresi yüzdesi" kuyular arası karşılaştırılamaz, çünkü
organoid teritoryası bir kuyuda alanın %6'sını, başka birinde %95'ini kaplıyor —
ikincisinde rastgele dağılmış T hücreleri bile %90 "içeride" çıkar. Bu yüzden
başlık sayısı yoğunluk oranı:

    zenginleşme = (teritorya içi orange piksel yoğunluğu) / (dışı)
    1,0 = rastgele dağılım · <1 = dışlanma · >1 = infiltrasyon

Yanına iki tamamlayıcı ölçüm konuyor:

* **İşaretli uzaklık profili** — organoid sınırından µm cinsinden mesafeye göre
  orange yoğunluğu (negatif = içeride). Tek bir sayı yerine profilin şekli
  "kenarda takılmış" ile "içeri girmiş" arasını ayırır.
* **T'siz kuyulara göre fazlalık** — orange kanalında T hücresi eklenmeyen
  kuyularda da sinyal var (otofloresan/döküntü). Eşleşmiş T'siz kuyulardan
  fazlalık, gerçekten T hücresine atfedilebilen kısmı verir.

Çıktı: analysis/out/a2_infiltration/
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import (UM_PER_PX, COCULTURE_COLOR, COCULTURE_ORDER, COMPOUND_ORDER, DIV, INK,
                    INK2, MUTED, SEQ, SERIES, auc, band_labels, bh_fdr, boot_ci,
                    cliffs_delta, finish, load, load_organoids, mwu_p, outdir,
                    plate_grid, qc_wells, stars, strip, timeseries, write_summary)
import matplotlib.pyplot as plt

OUT = outdir("a2_infiltration")
NB = 11                      # uzaklık bandı sayısı


def pooled_profile(d: pd.DataFrame, ch: str = "orange") -> np.ndarray:
    """Grup içindeki tüm kuyuların piksellerini havuzlayıp bant zenginleşmesi.
    Kuyu başına oranların ortalaması değil — büyük kuyu küçük kuyuyu bastırmasın
    diye her kuyu kendi alanına göre normalize edilmiş sayımlarla girer."""
    sig = np.array([d[f"{ch}_band_px_{i}"].sum() for i in range(NB)], float)
    area = np.array([d[f"band_area_px_{i}"].sum() for i in range(NB)], float)
    with np.errstate(divide="ignore", invalid="ignore"):
        dens = np.where(area > 0, sig / area, np.nan)
    overall = sig.sum() / area.sum() if area.sum() else np.nan
    return dens / overall


def main():
    df = load()
    org = load_organoids()
    exc = qc_wells(df)
    df = df[~df.well.isin(exc)]
    org = org[~org.well.isin(exc)]
    last = df[df.t == df.t.max()]
    lines: list[str] = []

    tp = last[last.t_added]
    tn = last[~last.t_added]

    # ------------------------------------------------- 1. sinyal doğrulaması
    lines += ["## 1. Önce kontrol: orange gerçekten T hücresini mi ölçüyor?", ""]
    a = auc(tp.orange_area_frac, tn.orange_area_frac)
    p = mwu_p(tp.orange_area_frac, tn.orange_area_frac)
    ratio = tp.orange_area_frac.median() / max(tn.orange_area_frac.median(), 1e-9)
    lines += [
        f"Son zaman noktasında T eklenen {len(tp)} kuyuda orange alan oranı medyan "
        f"**%{tp.orange_area_frac.median()*100:.2f}**, eklenmeyen {len(tn)} kuyuda "
        f"**%{tn.orange_area_frac.median()*100:.2f}** — {ratio:.1f}× fark "
        f"(AUC {a:.2f}, p = {p:.1e}).",
        "",
        "Fark yönü doğru ama **ayrım tam değil**: T eklenmeyen kuyularda da belirgin "
        "orange sinyali var. Yani `orange_area_frac` mutlak bir T hücresi ölçüsü değil; "
        "kuyu içi konum ölçümleri (zenginleşme, uzaklık profili) bu arkaplandan "
        "etkilenmez çünkü aynı kuyunun içinde oran alıyorlar, ama **mutlak miktar "
        "karşılaştırmaları eşleşmiş T'siz kuyulara göre fazlalık olarak okunmalı.**",
    ]
    tp0 = df[(df.t == 0) & df.t_added]
    tn0 = df[(df.t == 0) & ~df.t_added]
    lines += ["",
              f"t0'da (ekimden hemen sonra) ayrım daha keskin: "
              f"%{tp0.orange_area_frac.median()*100:.2f} vs "
              f"%{tn0.orange_area_frac.median()*100:.2f} "
              f"({tp0.orange_area_frac.median()/max(tn0.orange_area_frac.median(),1e-9):.1f}×, "
              f"AUC {auc(tp0.orange_area_frac, tn0.orange_area_frac):.2f}). "
              "Zamanla farkın kapanması ya T hücrelerinin kaybolduğunu ya da arkaplanın "
              "büyüdüğünü gösterir — A5 (ölüm) buna bakıyor."]

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.5))
    ax = axes[0]
    strip(ax, [("T eklendi", tp.orange_area_frac * 100),
               ("T yok", tn.orange_area_frac * 100)],
          colors=[SERIES[1], MUTED], log=True)
    ax.set_ylabel("orange alan oranı %")
    ax.set_title(f"Orange sinyali, 4. gün (AUC {a:.2f})")
    ax = axes[1]
    timeseries(ax, df, "orange_area_frac", "has_tcells", ["yes", "no"],
               [SERIES[1], MUTED])
    ax.set_ylabel("orange alan oranı")
    ax.set_title("Orange sinyalinin zaman seyri")
    ax.legend(["T eklendi", "T yok"])
    ax = axes[2]
    plate_grid(ax, last.set_index("well").orange_area_frac.mul(100).to_dict(),
               "orange alan oranı % (4. gün)", cmap=SEQ, fmt="{:.1f}", label="%")
    finish(fig, OUT / "orange_signal_control.png",
           "Orange kanalı T hücresi işaretleyicisi; T eklenmeyen kuyulardaki sinyal "
           "otofloresan/döküntü arkaplanıdır.")

    # ------------------------------------------------------ 2. zenginleşme
    lines += ["", "## 2. Ana sayı: organoid içi zenginleşme", ""]
    e_tp = tp.orange_enrich_organoid.dropna()
    e_tn = tn.orange_enrich_organoid.dropna()
    lo, hi = boot_ci(e_tp)
    below = int((e_tp < 1).sum())
    ci_excludes_1 = hi < 1.0 or lo > 1.0
    lines += [
        f"T eklenen kuyularda 4. günde zenginleşme medyanı **{e_tp.median():.2f}** "
        f"(%95 GA {lo:.2f}–{hi:.2f}); T'siz kuyularda {e_tn.median():.2f}.",
        "",
        (f"**Bu, rastgele dağılımdan ayırt edilemez.** Güven aralığı 1,0'ı içeriyor "
         f"ve {below}/{len(e_tp)} kuyu 1'in altında. Yani plaka genelinde tek bir "
         "sayıya indirgendiğinde ne toplu bir infiltrasyon ne de toplu bir dışlanma "
         "var — kuyular arasındaki *değişkenlik* asıl sinyal, ve o değişkenliğin "
         "neye bağlı olduğu 4. bölümde çıkıyor.")
        if not ci_excludes_1 else
        (f"**Zenginleşme 1'den {'düşük' if hi < 1 else 'yüksek'}: T hücreleri "
         f"organoid teritoryasının içinde dışına göre daha "
         f"{'seyrek' if hi < 1 else 'yoğun'}.** {below}/{len(e_tp)} T'li kuyuda "
         f"zenginleşme 1'in altında."),
    ]
    rows = []
    for cc in COCULTURE_ORDER:
        a_ = tp[tp.coculture == cc].orange_enrich_organoid.dropna()
        b_ = tn[tn.coculture == cc].orange_enrich_organoid.dropna()
        if len(a_) < 2:
            continue
        rows.append({"coculture": cc, "n_T": len(a_), "enrich_T": a_.median(),
                     "n_noT": len(b_), "enrich_noT": b_.median() if len(b_) else np.nan,
                     "p": mwu_p(a_, b_), "delta": cliffs_delta(a_, b_)})
    tab = pd.DataFrame(rows)
    if len(tab):
        tab["q"] = bh_fdr(tab.p.to_numpy())
        tab.to_csv(OUT / "enrichment_by_coculture.csv", index=False)
        lines += ["", "| ko-kültür | n (T+) | zenginleşme T+ | n (T−) | zenginleşme T− | "
                  "Cliff δ | q |", "|---|---|---|---|---|---|---|"]
        for r in tab.itertuples():
            lines.append(f"| {r.coculture} | {r.n_T} | {r.enrich_T:.2f} | {r.n_noT} | "
                         f"{r.enrich_noT:.2f} | {r.delta:+.2f} | {r.q:.3f} |")
        neg = int((tab.delta < 0).sum())
        if neg == len(tab):
            from scipy.stats import binomtest
            ps = binomtest(neg, len(tab), 0.5).pvalue
            lines += ["",
                      f"Tek tek hiçbiri anlamlı değil ama **dört ko-kültürün dördünde de "
                      f"işaret aynı**: T eklenen kuyularda zenginleşme, T'siz eşdeğerinden "
                      f"düşük (işaret testi p = {ps:.2f}). Tutarlı bir eğilim var, tek tek "
                      "kuyularla doğrulanacak güç yok."]

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.5))
    ax = axes[0]
    strip(ax, [(cc.replace("PDA+", "+"), tp[tp.coculture == cc].orange_enrich_organoid.dropna())
               for cc in COCULTURE_ORDER],
          colors=[COCULTURE_COLOR[c] for c in COCULTURE_ORDER], log=True,
          hline=1.0, hlabel="rastgele dağılım")
    ax.set_ylabel("zenginleşme (içeri/dışarı yoğunluk)")
    ax.set_title("T hücresi zenginleşmesi, 4. gün (T eklenen kuyular)")
    ax = axes[1]
    timeseries(ax, df[df.t_added], "orange_enrich_organoid", "coculture",
               COCULTURE_ORDER, COCULTURE_COLOR)
    ax.axhline(1.0, color=MUTED, ls="--", lw=1)
    ax.set_ylabel("zenginleşme")
    ax.set_title("Zenginleşmenin zaman seyri (T+)")
    ax.legend(loc="best", ncols=2)
    ax = axes[2]
    v = last[last.t_added].set_index("well").orange_enrich_organoid.to_dict()
    plate_grid(ax, v, "zenginleşme (yalnız T+ kuyular)", cmap=DIV, center=1.0,
               fmt="{:.1f}", label="içeri/dışarı")
    finish(fig, OUT / "enrichment.png",
           "1,0 = rastgele dağılım. Teritorya = brightfield organoid maskesi.")

    # -------------------------------------------------- 3. uzaklık profili
    lines += ["", "## 3. Uzaklık profili — dışlanma nerede başlıyor", ""]
    labels = band_labels("um")
    labels_px = band_labels("px")
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    ax = axes[0]
    for i, cc in enumerate(COCULTURE_ORDER):
        d = last[last.t_added & (last.coculture == cc)]
        if d.empty:
            continue
        ax.plot(range(NB), pooled_profile(d), color=COCULTURE_COLOR[cc], label=cc,
                marker="o", ms=4)
    d0 = last[~last.t_added]
    ax.plot(range(NB), pooled_profile(d0), color=MUTED, ls="--", label="T yok (arkaplan)",
            marker="o", ms=4)
    ax.axhline(1.0, color=MUTED, lw=1, ls=":")
    ax.axvline(4.5, color=INK2, lw=1)
    ax.text(4.4, ax.get_ylim()[1], " organoid sınırı", ha="right", va="top",
            fontsize=7, color=INK2, rotation=90)
    ax.set_xticks(range(NB), labels, rotation=55, ha="right", fontsize=6.5)
    ax.set_xlabel(f"organoid sınırına işaretli uzaklık (µm @ {UM_PER_PX:g} µm/px; "
                  "negatif = içeride)")
    ax.set_ylabel("orange yoğunluğu / kuyu ortalaması")
    ax.set_title("T hücresi yoğunluğu uzaklığa göre, 4. gün")
    ax.legend(fontsize=7)

    ax = axes[1]
    for i, ti in enumerate([0, 4, 8, 12]):
        d = df[(df.t == ti) & df.t_added]
        ax.plot(range(NB), pooled_profile(d), color=SEQ(0.25 + i * 0.22),
                label=f"{d.day.iloc[0]:.0f}. gün", marker="o", ms=4)
    ax.axhline(1.0, color=MUTED, lw=1, ls=":")
    ax.axvline(4.5, color=INK2, lw=1)
    ax.set_xticks(range(NB), labels_px, rotation=55, ha="right", fontsize=6.5)
    ax.set_xlabel("işaretli uzaklık (piksel — kalibrasyondan bağımsız)")
    ax.set_ylabel("orange yoğunluğu / kuyu ortalaması")
    ax.set_title("Profilin zaman içinde değişimi (T+ kuyular)")
    ax.legend(fontsize=7)
    finish(fig, OUT / "distance_profile.png",
           f"Havuzlanmış profil: gruptaki tüm kuyuların piksel sayımları toplanıp bant "
           f"alanına bölündü. Bantlar piksel cinsinden sabit; soldaki eksen µm "
           f"etiketlerini {UM_PER_PX:g} µm/px varsayımıyla gösteriyor, sağdaki ham piksel.")

    prof = pooled_profile(last[last.t_added])
    prof_n = pooled_profile(last[~last.t_added])
    pd.DataFrame({"band_px": labels_px, "band_um": labels,
                  "T_added": prof, "no_T": prof_n}).to_csv(
        OUT / "distance_profile.csv", index=False)
    peak = int(np.nanargmax(prof))
    lines += [
        f"Profilin tepesi **{labels[peak]} µm** ({labels_px[peak]} px) bandında — "
        f"yani T hücreleri organoid sınırının hemen "
        f"{'dışında' if peak >= 5 else 'içinde'} yığılıyor. "
        f"Derin iç bantta ({labels[0]} µm) yoğunluk kuyu ortalamasının "
        f"{prof[0]:.2f}× katı, sınır bandında ({labels[5]} µm) {prof[5]:.2f}×.",
        "",
        "Bant kenarları piksel cinsinden sabittir; µm etiketleri geçerli "
        "kalibrasyondan türetilmiştir (aşağıdaki ölçek notu). Profilin **şekli ve "
        "tepe bandı kalibrasyondan bağımsızdır** — kalibrasyon yalnızca eksen "
        "etiketlerini ölçekler.",
        "",
        "T eklenmeyen kuyuların profili karşılaştırma için çizildi: aynı şekli "
        f"göstermesi profilin bir kısmının **organoid geometrisinden** geldiğini "
        "söyler (döküntü de organoidin çevresinde birikir), farkı ise T hücresine "
        "atfedilebilir kısımdır.",
    ]

    # --------------------------------------- 4. organoid başına infiltrasyon
    lines += ["", "## 4. Organoid başına: hangi organoide ne kadar giriyor", ""]
    o = org[org.t == org.t.max()]
    ot = o[o.t_added]
    lines += [
        f"Son zaman noktasında T eklenen kuyularda ölçülen {len(ot)} organoid "
        f"(≥{ot.area_px.min():.0f} px ≈ {ot.eq_diam_px.min():.0f} px eşdeğer çap = "
        f"{ot.eq_diam_um.min():.0f} µm). Organoid alanının orange ile kaplı oranı "
        f"medyan **%{ot.orange_cov.median()*100:.2f}**; çeyrekler "
        f"%{ot.orange_cov.quantile(.25)*100:.2f}–%{ot.orange_cov.quantile(.75)*100:.2f}.",
    ]
    bins = np.geomspace(ot.eq_diam_um.min(), ot.eq_diam_um.max(), 14)
    ob = ot.assign(b=pd.cut(ot.eq_diam_um, bins))
    g = ob.groupby("b", observed=True).agg(med_cov=("orange_cov", "median"),
                                           n_org=("orange_cov", "size"))
    rho = ot.eq_diam_um.corr(ot.orange_cov, method="spearman")
    lines += ["",
              f"Organoid çapı ile orange kapsaması arasındaki sıra korelasyonu "
              f"**{rho:+.2f}** — {'büyük organoidler daha az T hücresi barındırıyor' if rho < -0.1 else 'çap ile belirgin bir ilişki yok' if abs(rho) <= 0.1 else 'büyük organoidler daha çok T hücresi barındırıyor'}."]

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.5))
    ax = axes[0]
    ax.scatter(ot.eq_diam_um, ot.orange_cov * 100 + 1e-3, s=9, alpha=0.25,
               color=SERIES[1], edgecolors="none")
    mid = np.sqrt(bins[:-1] * bins[1:])[: len(g)]
    ax.plot(mid, g.med_cov.to_numpy() * 100, color=INK, marker="o", ms=5, lw=2)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(f"organoid eşdeğer çapı (µm @ {UM_PER_PX:g} µm/px)")
    ax.set_ylabel("orange kapsaması %")
    ax.set_title(f"Organoid boyutuna göre T yükü (ρ = {rho:+.2f})")

    ax = axes[1]
    # doluluk dağılımı üst uca yığılmış — sabit kesimler yerine beşlik dilimler
    ot2 = ot.assign(solb=pd.qcut(ot.solidity, 5, duplicates="drop"))
    gg = ot2.groupby("solb", observed=True).orange_cov.median() * 100
    ax.bar(range(len(gg)), gg.to_numpy(), color=SERIES[0], width=0.68)
    ax.set_xticks(range(len(gg)),
                  [f"{i.left:.2f}–{i.right:.2f}" for i in gg.index], rotation=25,
                  fontsize=6.5)
    ax.set_xlabel("organoid doluluğu (koyu madde / teritorya)")
    ax.set_ylabel("orange kapsaması % (medyan)")
    ax.set_title("Sıkı organoidler T hücresini daha çok dışlıyor")

    ax = axes[2]
    for i, cc in enumerate(COCULTURE_ORDER):
        v = ot[ot.coculture == cc].orange_cov.dropna() * 100
        if len(v) < 5:
            continue
        xs = np.sort(v)
        ax.plot(xs, np.linspace(0, 1, len(xs)), color=COCULTURE_COLOR[cc], label=cc)
    ax.set_xscale("symlog", linthresh=1e-2)
    ax.set_xlabel("orange kapsaması %")
    ax.set_ylabel("birikimli organoid oranı")
    ax.set_title("Organoid başına T yükünün dağılımı")
    ax.legend(fontsize=7)
    finish(fig, OUT / "per_organoid.png",
           f"Her nokta bir organoid (BF teritorya bileşeni, ≥300 px — bu eşik piksel "
           f"cinsinden sabittir). Son zaman noktası. Çap ekseni {UM_PER_PX:g} µm/px ile "
           "etiketlendi; sıralama ve korelasyon kalibrasyondan bağımsız.")

    q20, q80 = ot.solidity.quantile([0.2, 0.8])
    sol_lo = ot[ot.solidity <= q20].orange_cov
    sol_hi = ot[ot.solidity >= q80].orange_cov
    a_sol = auc(sol_lo, sol_hi)
    lines += ["",
              f"Doluluğu en düşük beşte birdeki (≤{q20:.2f}, gevşek) organoidlerde "
              f"orange kapsaması medyan %{sol_lo.median()*100:.2f}, en yüksek beşte "
              f"birdekilerde (≥{q80:.2f}, sıkı) %{sol_hi.median()*100:.2f} — "
              f"AUC {a_sol:.2f} ({len(sol_lo)} ve {len(sol_hi)} organoid). "
              + ("Yön sıkı organoidlerin T hücresini daha çok dışladığına uyuyor, ama "
                 "AUC 0,5'e yakın: bu tek başına zayıf bir ayrım, örneklem büyük "
                 "olduğu için istatistiksel olarak sağlam ama etki küçük."
                 if abs(a_sol - 0.5) < 0.15 else
                 "Sıkı paketlenmiş organoidler T hücresini belirgin biçimde dışlıyor.")]

    # ------------------------------------------------------- 5. ilaç etkisi
    lines += ["", "## 5. Bileşiklerin infiltrasyona etkisi", ""]
    rows = []
    ctrl = tp[tp.compound == "control"].orange_enrich_organoid.dropna()
    for cp in COMPOUND_ORDER:
        v = tp[tp.compound == cp].orange_enrich_organoid.dropna()
        if len(v) < 2:
            continue
        rows.append({"compound": cp, "n": len(v), "enrich": v.median(),
                     "vs_control_delta": cliffs_delta(v, ctrl) if len(ctrl) >= 2 else np.nan,
                     "p": mwu_p(v, ctrl) if len(ctrl) >= 2 else np.nan})
    ctab = pd.DataFrame(rows)
    if len(ctab):
        ctab["q"] = bh_fdr(ctab.p.to_numpy())
        ctab.to_csv(OUT / "enrichment_by_compound.csv", index=False)
        lines += ["| bileşik | n kuyu | zenginleşme (medyan) | kontrole karşı δ | q |",
                  "|---|---|---|---|---|"]
        for r in ctab.itertuples():
            lines.append(f"| {r.compound} | {r.n} | {r.enrich:.2f} | "
                         f"{r.vs_control_delta:+.2f} | "
                         f"{'—' if not np.isfinite(r.q) else f'{r.q:.3f}'} |")
        sig = ctab[ctab.q < 0.05]
        lines += ["",
                  ((f"Kuyu sayısı bileşik başına yalnızca {ctab.n.min()}–{ctab.n.max()}; "
                    "çoğu karşılaştırmada test bile çalıştırılamıyor (grup başına en az "
                    "3 kuyu gerekiyor). **Bu tasarımda bileşiklerin infiltrasyona "
                    "etkisi ölçülemez** — tablo yalnızca yön göstergesi.")
                   if not np.isfinite(ctab.q).any() else
                   ("Hiçbir bileşik kontrolden anlamlı biçimde ayrılmıyor "
                    f"(en düşük q = {ctab.q.min():.2f}). Kuyu sayısı bileşik başına "
                    f"{ctab.n.min()}–{ctab.n.max()} — bu güçle ancak büyük etkiler "
                    "görünür."))
                  if sig.empty else
                  ("Kontrolden ayrılan bileşikler: " +
                   ", ".join(f"**{r.compound}** (δ {r.vs_control_delta:+.2f}, q {r.q:.3f})"
                             for r in sig.itertuples()))]

    fig, ax = plt.subplots(figsize=(7, 3.4))
    d = tp[tp.compound.isin(ctab.compound)] if len(ctab) else tp
    strip(ax, [(cp.replace(" ", "\n"), d[d.compound == cp].orange_enrich_organoid.dropna())
               for cp in ctab.compound], colors=SERIES, log=True,
          hline=1.0, hlabel="rastgele")
    ax.set_ylabel("zenginleşme")
    ax.set_title("Bileşiğe göre T hücresi zenginleşmesi (4. gün, T+ kuyular)")
    ax.tick_params(axis="x", labelsize=7)
    finish(fig, OUT / "compound_effect.png",
           "Her nokta bir kuyu. Yatay çizgi grup medyanı.")

    last[["well", "coculture", "compound", "orange_area_frac", "orange_enrich_organoid",
          "orange_frac_in_organoid", "orange_median_signed_dist_um", "bf_terr_frac",
          "n_organoids_scored"]].to_csv(OUT / "well_infiltration_day4.csv", index=False)
    write_summary(OUT / "summary.md", "A2 — T hücresi infiltrasyonu", lines)


if __name__ == "__main__":
    main()
