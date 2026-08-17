#!/usr/bin/env python3
"""A6 — Büyüme, morfoloji ve ilaç yanıtı.

İnfiltrasyonu yorumlayabilmek için önce organoidin kendisinin ne yaptığını bilmek
gerekiyor: büyüdü mü, tek bir sıkı sferoide mi toplandı yoksa dağınık mı kaldı,
bileşikler bunu değiştirdi mi. A2'deki en güçlü bulgu — sıkı organoidlerin T
hücresini dışlaması — doğrudan buraya bağlanıyor.

Üç ayrı ölçüm ekseni:

    kütle       BF teritorya oranı ve green alan oranı — ne kadar madde var
    toplanma    en büyük nesnenin toplam içindeki payı ve doluluk — dağınık mı sıkı mı
    boyut       organoid başına eşdeğer çap dağılımı

Büyüme hızı, kuyu başına log(ölçüm) ~ gün doğrusal uyumunun eğimi olarak
hesaplanıyor (gün başına kat artış).

Çıktı: analysis/out/a6_growth/
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import (UM_PER_PX, COCULTURE_COLOR, COCULTURE_ORDER, COMPOUND_ORDER, DIV, INK,
                    INK2, MUTED, SEQ, SERIES, auc, bh_fdr, boot_ci, cliffs_delta,
                    finish, load, load_organoids, mwu_p, outdir, plate_grid,
                    qc_wells, strip, timeseries, write_summary)
import matplotlib.pyplot as plt

OUT = outdir("a6_growth")


def growth_rate(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Kuyu başına log-doğrusal eğim → gün başına kat değişim."""
    rows = []
    for w, d in df.groupby("well"):
        d = d.sort_values("day")
        y = d[col].to_numpy(float)
        x = d.day.to_numpy(float)
        ok = np.isfinite(y) & (y > 0)
        if ok.sum() < 5:
            continue
        b = np.polyfit(x[ok], np.log(y[ok]), 1)[0]
        rows.append({"well": w, "coculture": d.coculture.iloc[0],
                     "compound": d.compound.iloc[0], "has_tcells": d.has_tcells.iloc[0],
                     "rate": b, "fold_per_day": float(np.exp(b)),
                     "start": y[ok][0], "end": y[ok][-1],
                     "fold_total": y[ok][-1] / y[ok][0]})
    return pd.DataFrame(rows)


def main():
    df = load()
    org = load_organoids()
    exc = qc_wells(df)
    df = df[~df.well.isin(exc) & (df.compound != "Dye")]
    org = org[~org.well.isin(exc) & (org.compound != "Dye")]
    first, last = df[df.t == 0], df[df.t == df.t.max()]
    lines: list[str] = []

    # ------------------------------------------------------------ 1. kütle
    lines += ["## 1. Organoidler büyüdü mü?", ""]
    gr = growth_rate(df, "bf_terr_frac")
    gr.to_csv(OUT / "growth_rate_bf.csv", index=False)
    grg = growth_rate(df, "green_area_frac")
    grg.to_csv(OUT / "growth_rate_green.csv", index=False)
    lines += [
        f"BF teritorya oranı 4 günde medyan **{last.bf_terr_frac.median()/max(first.bf_terr_frac.median(),1e-9):.2f}×** "
        f"arttı (%{first.bf_terr_frac.median()*100:.1f} → %{last.bf_terr_frac.median()*100:.1f}). "
        f"Kuyu başına log-doğrusal büyüme hızı medyan **{gr.fold_per_day.median():.2f}×/gün** "
        f"({len(gr)} kuyu, çeyrekler {gr.fold_per_day.quantile(.25):.2f}–"
        f"{gr.fold_per_day.quantile(.75):.2f}).",
        "",
        f"Green alan oranı aynı sürede {last.green_area_frac.median()/max(first.green_area_frac.median(),1e-9):.2f}× "
        f"değişti ({grg.fold_per_day.median():.2f}×/gün). İki ölçünün ayrışması "
        "beklenir: BF tüm hücresel maddeyi görür, green yalnız boyanmış tümörü "
        "(bkz. A1).",
    ]
    rows = []
    for cc in COCULTURE_ORDER:
        g = gr[gr.coculture == cc]
        if len(g) < 3:
            continue
        base = gr[gr.coculture == "PDA"].fold_per_day
        rows.append({"coculture": cc, "n": len(g), "fold_per_day": g.fold_per_day.median(),
                     "delta_vs_PDA": cliffs_delta(g.fold_per_day, base),
                     "p": mwu_p(g.fold_per_day, base)})
    ct = pd.DataFrame(rows)
    if len(ct):
        ct["q"] = bh_fdr(ct.p.to_numpy())
        ct.to_csv(OUT / "growth_by_coculture.csv", index=False)
        lines += ["", "| ko-kültür | n kuyu | büyüme (×/gün) | PDA'ya karşı δ | q |",
                  "|---|---|---|---|---|"]
        for r in ct.itertuples():
            lines.append(f"| {r.coculture} | {r.n} | {r.fold_per_day:.2f} | "
                         f"{r.delta_vs_PDA:+.2f} | "
                         f"{'—' if not np.isfinite(r.q) else f'{r.q:.3f}'} |")

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.5))
    ax = axes[0]
    timeseries(ax, df, "bf_terr_frac", "coculture", COCULTURE_ORDER, COCULTURE_COLOR)
    ax.set_ylabel("BF teritorya oranı")
    ax.set_title("Kütle artışı (brightfield)")
    ax.legend(fontsize=7, ncols=2)
    ax = axes[1]
    timeseries(ax, df, "green_area_frac", "coculture", COCULTURE_ORDER, COCULTURE_COLOR)
    ax.set_ylabel("green alan oranı")
    ax.set_title("Boyanmış tümör sinyali")
    ax.legend(fontsize=7, ncols=2)
    ax = axes[2]
    strip(ax, [(cc.replace("PDA+", "+"), gr[gr.coculture == cc].fold_per_day)
               for cc in COCULTURE_ORDER],
          colors=[COCULTURE_COLOR[c] for c in COCULTURE_ORDER], hline=1.0,
          hlabel="değişim yok")
    ax.set_ylabel("büyüme (×/gün)")
    ax.set_title("Ko-kültüre göre büyüme hızı")
    finish(fig, OUT / "growth.png",
           "Bant = kuyular arası çeyrekler arası aralık. Dye kolonları hariç.")

    # -------------------------------------------------------- 2. toplanma
    lines += ["", "## 2. Dağınık mı, tek sferoid mi?", ""]
    lines += [
        f"En büyük nesnenin toplam BF maddesindeki payı 4. günde medyan "
        f"**{last.bf_largest_frac.median():.2f}** (t0'da "
        f"{first.bf_largest_frac.median():.2f}); doluluk "
        f"{last.bf_solidity.median():.2f}.",
        "",
        f"{int((last.bf_largest_frac > 0.8).sum())}/{len(last)} kuyu tek bir baskın "
        f"kütleye toplanmış (pay > 0,8), {int((last.bf_largest_frac < 0.4).sum())} kuyu "
        f"dağınık kalmış (< 0,4). Bu ayrım A2'deki dışlanma bulgusunun temeli: "
        "T hücresi zenginleşmesi toplanma derecesiyle ters gidiyor.",
    ]
    j = last.dropna(subset=["bf_largest_frac", "orange_enrich_organoid"])
    jt = j[j.t_added]
    rho = jt.bf_largest_frac.corr(jt.orange_enrich_organoid, method="spearman")
    rho2 = jt.bf_solidity.corr(jt.orange_enrich_organoid, method="spearman")
    lines += ["",
              f"T eklenen kuyularda toplanma ile T zenginleşmesi arasındaki sıra "
              f"korelasyonu **{rho:+.2f}**, doluluk ile **{rho2:+.2f}** "
              f"({len(jt)} kuyu). "
              f"{'Toplandıkça T hücresi dışlanıyor.' if rho < -0.2 else 'Belirgin bir ilişki yok.'}"]

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.5))
    ax = axes[0]
    timeseries(ax, df, "bf_largest_frac", "coculture", COCULTURE_ORDER, COCULTURE_COLOR)
    ax.set_ylabel("en büyük nesnenin payı")
    ax.set_title("Toplanmanın zaman seyri")
    ax.legend(fontsize=7, ncols=2)
    ax = axes[1]
    ax.scatter(jt.bf_largest_frac, jt.orange_enrich_organoid, s=26,
               color=[COCULTURE_COLOR.get(c, MUTED) for c in jt.coculture],
               edgecolors="none")
    ax.axhline(1.0, color=MUTED, ls="--", lw=1)
    ax.set_yscale("log")
    ax.set_xlabel("en büyük nesnenin payı (toplanma)")
    ax.set_ylabel("T hücresi zenginleşmesi")
    ax.set_title(f"Toplanma ve dışlanma (ρ = {rho:+.2f})")
    for cc in COCULTURE_ORDER:
        ax.scatter([], [], color=COCULTURE_COLOR[cc], label=cc, s=26)
    ax.legend(fontsize=6.5)
    ax = axes[2]
    plate_grid(ax, last.set_index("well").bf_largest_frac.to_dict(),
               "toplanma, 4. gün", cmap=SEQ, vmin=0, vmax=1, fmt="{:.1f}",
               label="en büyük nesnenin payı")
    finish(fig, OUT / "aggregation.png")

    # ----------------------------------------------------------- 3. boyut
    lines += ["", "## 3. Organoid boyut dağılımı", ""]
    o0 = org[org.t == 0]
    o1 = org[org.t == org.t.max()]
    lines += [
        f"t0'da ölçülen {len(o0)} organoidin medyan eşdeğer çapı "
        f"**{o0.eq_diam_px.median():.0f} px** ({o0.eq_diam_um.median():.0f} µm), "
        f"4. günde {len(o1)} organoid için **{o1.eq_diam_px.median():.0f} px** "
        f"({o1.eq_diam_um.median():.0f} µm). Üst uç (p95) "
        f"{o0.eq_diam_px.quantile(.95):.0f} → {o1.eq_diam_px.quantile(.95):.0f} px "
        f"({o0.eq_diam_um.quantile(.95):.0f} → {o1.eq_diam_um.quantile(.95):.0f} µm).",
        "",
        "Sayının düşmesi ve çapın büyümesi birlikte okunmalı: ayrı organoidler "
        "birleşerek daha az ama daha büyük nesne bırakıyor.",
    ]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.4))
    ax = axes[0]
    bins = np.geomspace(org.eq_diam_px.min(), org.eq_diam_px.max(), 30)
    for i, (lab, d) in enumerate((("0. gün", o0), ("4. gün", o1))):
        ax.hist(d.eq_diam_px, bins=bins, histtype="step", density=True,
                color=[MUTED, SERIES[0]][i], lw=2, label=lab)
    ax.set_xscale("log")
    ax.set_xlabel("eşdeğer çap (piksel — kalibrasyondan bağımsız)")
    ax.set_ylabel("yoğunluk")
    ax.set_title("Organoid boyut dağılımı")
    ax.legend(fontsize=7)
    ax = axes[1]
    timeseries(ax, df, "organoid_med_diam_um", "coculture", COCULTURE_ORDER,
               COCULTURE_COLOR)
    ax.set_ylabel(f"medyan organoid çapı (µm @ {UM_PER_PX:g} µm/px)")
    ax.set_title("Çapın zaman seyri")
    ax.legend(fontsize=7, ncols=2)
    ax = axes[2]
    timeseries(ax, df, "n_organoids_scored", "coculture", COCULTURE_ORDER,
               COCULTURE_COLOR)
    ax.set_ylabel("ölçülen organoid sayısı")
    ax.set_title("Organoid sayısı")
    ax.legend(fontsize=7, ncols=2)
    finish(fig, OUT / "size_distribution.png",
           "Yalnızca ≥300 px (≈55 µm) teritorya bileşenleri sayıldı.")

    # ------------------------------------------------------ 4. ilaç yanıtı
    lines += ["", "## 4. Bileşikler büyümeyi durdurdu mu?", ""]
    rows = []
    base = gr[gr.compound == "control"].fold_per_day
    for cp in COMPOUND_ORDER:
        g = gr[gr.compound == cp]
        if len(g) < 2 or cp == "Dye":
            continue
        rows.append({"compound": cp, "n": len(g), "fold_per_day": g.fold_per_day.median(),
                     "delta_vs_control": cliffs_delta(g.fold_per_day, base) if cp != "control" else 0.0,
                     "p": mwu_p(g.fold_per_day, base) if cp != "control" else np.nan})
    dt = pd.DataFrame(rows)
    if len(dt):
        dt["q"] = bh_fdr(dt.p.to_numpy())
        dt.to_csv(OUT / "growth_by_compound.csv", index=False)
        lines += ["| bileşik | n kuyu | büyüme (×/gün) | kontrole karşı δ | q |",
                  "|---|---|---|---|---|"]
        for r in dt.itertuples():
            lines.append(f"| {r.compound} | {r.n} | {r.fold_per_day:.2f} | "
                         f"{r.delta_vs_control:+.2f} | "
                         f"{'—' if not np.isfinite(r.q) else f'{r.q:.3f}'} |")
        sig = dt[(dt.q < 0.05) & (dt.compound != "control")]
        lines += ["",
                  ("Hiçbir bileşik kontrolden anlamlı ayrılmıyor "
                   f"(en düşük q = {dt.q.min():.2f}). Bileşik başına "
                   f"{dt.n.min()}–{dt.n.max()} kuyu var; bu güçle ancak büyük etkiler "
                   "görünür.") if sig.empty else
                  ("Büyümesi kontrolden ayrılan bileşikler: " + ", ".join(
                      f"**{r.compound}** ({r.fold_per_day:.2f}×/gün, δ "
                      f"{r.delta_vs_control:+.2f}, q {r.q:.3f})" for r in sig.itertuples()))]
        dose = [("KRAS", "kras low", "kras high"), ("Src", "Src low", "Src high"),
                ("KRAS+Src", "low kras+Src", "high kras+Src")]
        dl = []
        for name, lo, hi in dose:
            a = gr[gr.compound == lo].fold_per_day
            b = gr[gr.compound == hi].fold_per_day
            if len(a) and len(b):
                dl.append(f"**{name}**: düşük doz {a.median():.2f}×/gün ({len(a)} kuyu), "
                          f"yüksek doz {b.median():.2f}×/gün ({len(b)} kuyu)")
        if dl:
            lines += ["", "Doz karşılaştırması (doz-yanıt beklenir):", ""] + \
                     [f"- {x}" for x in dl]

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 3.5))
    ax = axes[0]
    order = list(dt.compound) if len(dt) else []
    strip(ax, [(cp.replace(" ", "\n"), gr[gr.compound == cp].fold_per_day)
               for cp in order],
          colors=[MUTED] + SERIES, hline=1.0, hlabel="değişim yok")
    ax.set_ylabel("büyüme (×/gün)")
    ax.set_title("Bileşiğe göre büyüme hızı")
    ax.tick_params(axis="x", labelsize=7)
    ax = axes[1]
    for i, cp in enumerate(order[:6]):
        d = df[df.compound == cp]
        g = d.groupby("day").bf_terr_frac.median()
        ax.plot(g.index, g.values, color=(MUTED if cp == "control" else SERIES[i % 8]),
                label=cp, lw=2.4 if cp == "control" else 2)
    ax.set_ylabel("BF teritorya oranı")
    ax.set_xlabel("gün")
    ax.set_title("Kütle eğrileri, bileşiğe göre")
    ax.legend(fontsize=7, ncols=2)
    finish(fig, OUT / "compound_growth.png")

    gr.to_csv(OUT / "growth_rate_bf.csv", index=False)
    write_summary(OUT / "summary.md", "A6 — Büyüme, morfoloji ve ilaç yanıtı", lines)


if __name__ == "__main__":
    main()
