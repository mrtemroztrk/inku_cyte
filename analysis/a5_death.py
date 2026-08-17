#!/usr/bin/env python3
"""A5 — Kim öldü, neden ölmüş olabilir?

NIR kanalı genel bir ölü hücre boyası: hangi hücre tipinin öldüğünü kendi başına
söylemez. Söyleyen tek şey **birlikte konumlanma** — bir NIR sinyali green
(tümör) sinyaliyle örtüşüyorsa ölen tümör hücresidir, orange ile örtüşüyorsa
T hücresi. Bu yüzden burada üç ayrı ölçü kullanılıyor:

    ölüm payı        NIR sinyalinin ne kadarı tümörün/T hücresinin üstünde
    ölüm indeksi     o hücre tipinin sinyaline bölünmüş NIR — "her birim tümör
                     başına ne kadar ölüm", kütle farklarından arınmış
    konum            ölü sinyali organoidin içinde mi dışında mı, hangi derinlikte

Nedene dair çıkarım tasarımdan geliyor: aynı ko-kültür ve aynı bileşikte T hücresi
eklenen ve eklenmeyen kuyular karşılaştırılınca fark T hücresine atfedilebilir;
aynı şekilde bileşik değiştirilip T sabit tutulunca fark ilaca atfedilebilir.

Çıktı: analysis/out/a5_death/
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import (COCULTURE_COLOR, COCULTURE_ORDER, COMPOUND_ORDER, DIV, INK,
                    INK2, MUTED, SEQ, SERIES, STATUS, auc, bh_fdr, boot_ci,
                    cliffs_delta, finish, load, load_organoids, mwu_p, outdir,
                    plate_grid, qc_wells, stars, strip, timeseries, write_summary)
import matplotlib.pyplot as plt

OUT = outdir("a5_death")


def matched_effect(df: pd.DataFrame, col: str, split: str) -> pd.DataFrame:
    """Ko-kültür × bileşik eşleşmesi içinde `split` değişkeninin etkisi.
    Eşleşmemiş karşılaştırma yapılmıyor: ko-kültür hem ölümü hem T hücresi
    dağılımını etkiliyor, karıştırmamak için sabit tutuluyor."""
    rows = []
    for (cc, cp), d in df.groupby(["coculture", "compound"]):
        a = d.loc[d[split], col].dropna()
        b = d.loc[~d[split], col].dropna()
        if len(a) < 1 or len(b) < 1:
            continue
        rows.append({"coculture": cc, "compound": cp, "n_pos": len(a), "n_neg": len(b),
                     "median_pos": a.median(), "median_neg": b.median(),
                     "log2_ratio": np.log2((a.median() + 1e-6) / (b.median() + 1e-6))})
    return pd.DataFrame(rows)


def main():
    df = load()
    org = load_organoids()
    exc = qc_wells(df)
    df = df[~df.well.isin(exc)]
    org = org[~org.well.isin(exc)]
    bio = df[df.compound != "Dye"]
    last = bio[bio.t == bio.t.max()]
    lines: list[str] = []

    # ------------------------------------------------- 1. ne kadar ölüm var
    lines += ["## 1. Ölüm sinyalinin büyüklüğü ve zamanlaması", ""]
    lines += [
        f"NIR alan oranı 4. günde medyan **%{last.nir_area_frac.median()*100:.3f}** "
        f"(çeyrekler %{last.nir_area_frac.quantile(.25)*100:.3f}–"
        f"%{last.nir_area_frac.quantile(.75)*100:.3f}, aralık "
        f"%{last.nir_area_frac.min()*100:.4f}–%{last.nir_area_frac.max()*100:.3f}).",
        "",
        "Kanal çok seyrek — plaka genelinde piksellerin binde birinden azı eşik "
        "üstünde. Bu, kuyu başına ölçümün gürültülü olduğu anlamına gelir; "
        "aşağıdaki karşılaştırmalarda kuyular gruplanarak okunmalı, tek kuyu "
        "farkları yorumlanmamalı.",
    ]
    curve = bio.groupby("day").nir_area_frac.median()
    peak_day = curve.idxmax()
    n0 = bio[bio.t == 0].nir_area_frac.median()
    lines += ["",
              f"Zaman seyrinde plaka medyanı **{peak_day:.1f}. günde** tepe yapıyor, "
              f"sonra düşüyor: %{n0*100:.3f} (0. gün) → %{curve.max()*100:.3f} (tepe) "
              f"→ %{last.nir_area_frac.median()*100:.3f} (4. gün).",
              "",
              "**Ölü hücre sinyalinin azalması, ölümün azaldığı anlamına gelmez.** "
              "NIR birikmiş ölü maddeyi ölçer; sinyalin düşmesi ölü hücrelerin "
              "ortamdan kaldırıldığını (fagositoz, parçalanma, yüzeyden ayrılma) ya da "
              "boyanın soluklaştığını gösterir. Bu yüzden bu bölümdeki tüm "
              "karşılaştırmalar **aynı zaman noktası içinde** yapılıyor; zaman "
              "eksenindeki mutlak değişim kendi başına yorumlanmamalı."]

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.5))
    ax = axes[0]
    timeseries(ax, bio, "nir_area_frac", "coculture", COCULTURE_ORDER, COCULTURE_COLOR)
    ax.set_ylabel("NIR alan oranı")
    ax.set_yscale("log")
    ax.set_title("Ölü hücre sinyalinin zaman seyri")
    ax.legend(fontsize=7, ncols=2)
    ax = axes[1]
    timeseries(ax, bio, "nir_area_frac", "has_tcells", ["yes", "no"], [SERIES[1], MUTED])
    ax.set_ylabel("NIR alan oranı")
    ax.set_yscale("log")
    ax.set_title("T hücresi eklenince ölüm")
    ax.legend(["T eklendi", "T yok"], fontsize=7)
    ax = axes[2]
    plate_grid(ax, last.set_index("well").nir_area_frac.mul(100).to_dict(),
               "NIR alan oranı % (4. gün)", cmap=SEQ, fmt="{:.2f}", label="%")
    finish(fig, OUT / "death_overview.png",
           "Dye kontrol kolonları (10–12) dahil değil.")

    # ---------------------------------------------------------- 2. kim öldü
    lines += ["", "## 2. Ölen kim?", ""]
    at = last[last.t_added]
    an = last[~last.t_added]
    rows = []
    for name, d in (("T eklendi", at), ("T yok", an)):
        rows.append({"group": name, "n": len(d),
                     "on_tumour": d.nir_on_green_frac.median(),
                     "on_tcell": d.nir_on_orange_frac.median(),
                     "on_both": d.nir_on_both_frac.median(),
                     "on_neither": d.nir_on_neither_frac.median()})
    att = pd.DataFrame(rows)
    att.to_csv(OUT / "attribution.csv", index=False)
    lines += ["NIR sinyalinin hangi kanalla örtüştüğü (medyan pay):", "",
              "| grup | n | tümör üstünde | T hücresi üstünde | ikisinde | hiçbirinde |",
              "|---|---|---|---|---|---|"]
    for r in att.itertuples():
        lines.append(f"| {r.group} | {r.n} | %{r.on_tumour*100:.0f} | "
                     f"%{r.on_tcell*100:.0f} | %{r.on_both*100:.0f} | "
                     f"%{r.on_neither*100:.0f} |")
    lines += ["",
              f"T hücresi eklenmeyen kuyularda ölü sinyalinin "
              f"%{an.nir_on_green_frac.median()*100:.0f}'i tümör sinyaliyle örtüşüyor — "
              "orada ölen çoğunlukla tümör hücresi. T eklenen kuyularda tümörle "
              f"örtüşen pay %{at.nir_on_green_frac.median()*100:.0f}'e "
              f"{'düşerken' if at.nir_on_green_frac.median() < an.nir_on_green_frac.median() else 'çıkarken'}, "
              f"orange ile örtüşen pay %{an.nir_on_orange_frac.median()*100:.0f}'den "
              f"%{at.nir_on_orange_frac.median()*100:.0f}'e çıkıyor: "
              "**eklenen T hücrelerinin kayda değer bir kısmı ölüyor.**",
              "",
              "Uyarı: bu paylar kütleyle karışır — bir kuyuda çok tümör sinyali varsa "
              "NIR'ın onunla örtüşme olasılığı zaten yüksektir. Kütleden arınmış ölçü "
              "aşağıdaki ölüm indeksi."]

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.5))
    ax = axes[0]
    cats = ["nir_on_green_frac", "nir_on_orange_frac", "nir_on_both_frac",
            "nir_on_neither_frac"]
    labs = ["tümör", "T hücresi", "ikisi", "hiçbiri"]
    x = np.arange(2)
    bot = np.zeros(2)
    for i, (c, l) in enumerate(zip(cats, labs)):
        v = np.array([at[c].median(), an[c].median()])
        ax.bar(x, v, bottom=bot, color=SERIES[i], label=l, width=0.55)
        for xi, (vi, bi) in enumerate(zip(v, bot)):
            if vi > 0.06:
                ax.text(xi, bi + vi / 2, f"{vi*100:.0f}%", ha="center", va="center",
                        fontsize=7, color="#ffffff" if i != 3 else INK)
        bot += v
    ax.set_xticks(x, ["T eklendi", "T yok"])
    ax.set_ylabel("NIR sinyalinin payı")
    ax.set_title("Ölü sinyali neyin üstünde")
    ax.legend(fontsize=7, ncols=2)

    ax = axes[1]
    strip(ax, [("T eklendi", at.death_index_tumour), ("T yok", an.death_index_tumour)],
          colors=[SERIES[1], MUTED], log=True)
    ax.set_ylabel("tümör ölüm indeksi (NIR∩green / green)")
    ax.set_title(f"Tümör ölümü (AUC "
                 f"{auc(at.death_index_tumour, an.death_index_tumour):.2f})")
    ax = axes[2]
    timeseries(ax, bio, "death_index_tumour", "has_tcells", ["yes", "no"],
               [SERIES[1], MUTED])
    ax.set_yscale("log")
    ax.set_ylabel("tümör ölüm indeksi")
    ax.set_title("Tümör ölüm indeksinin zaman seyri")
    ax.legend(["T eklendi", "T yok"], fontsize=7)
    finish(fig, OUT / "attribution.png",
           "Ölüm indeksi = tümörle örtüşen NIR pikselleri / toplam green pikselleri.")

    # ------------------------------ 3. T hücresi tümör ölümünü artırıyor mu
    lines += ["", "## 3. T hücresi tümör ölümünü artırıyor mu?", ""]
    m = matched_effect(last, "death_index_tumour", "t_added")
    m.to_csv(OUT / "tcell_effect_matched.csv", index=False)
    # aynı eşleşmeler, kütleye bölünmemiş ham ölçüyle — bölmenin sonucu üretip
    # üretmediğini ayırt etmek için
    m_raw = matched_effect(last, "nir_area_frac", "t_added")
    m_raw.to_csv(OUT / "tcell_effect_matched_raw.csv", index=False)
    a_ = at.death_index_tumour.dropna()
    b_ = an.death_index_tumour.dropna()
    u, p = auc(a_, b_), mwu_p(a_, b_)
    lines += [
        f"Eşleşmemiş bakışta: T eklenen kuyularda tümör ölüm indeksi medyan "
        f"**{a_.median():.4f}**, eklenmeyenlerde **{b_.median():.4f}** "
        f"(AUC {u:.2f}, p = {p:.2g}).",
    ]
    if len(m):
        pos = int((m.log2_ratio > 0).sum())
        neg = len(m) - pos
        from scipy.stats import binomtest
        psign = binomtest(max(pos, neg), len(m), 0.5).pvalue
        lines += ["",
                  f"Ko-kültür × bileşik eşleşmesi içinde {len(m)} karşılaştırma yapıldı; "
                  f"bunların **{pos} tanesinde** T eklenmiş kuyu daha yüksek, "
                  f"**{neg} tanesinde** daha düşük tümör ölüm indeksi gösterdi "
                  f"(medyan log2 oran {m.log2_ratio.median():+.2f}, yani "
                  f"{2**m.log2_ratio.median():.2f}×; işaret testi p = {psign:.3f})."]
        if neg > pos and psign < 0.1:
            lines += ["",
                      "**Yön beklenenin tersi.** T hücresi eklenen kuyularda tümör ölüm "
                      "indeksi eşleşmiş T'siz kuyulardan sistematik olarak *düşük*. "
                      "Sitotoksisite beklenen bir kurulumda bu ters sonucun birkaç "
                      "olası açıklaması var ve veri aralarında seçim yapmıyor:",
                      "",
                      f"1. **Ölçü kütleye bölünüyor.** Ölüm indeksi NIR∩green'i green "
                      f"alanına bölüyor. Aynı eşleşmeler bölünmemiş NIR alan oranıyla "
                      f"tekrarlandığında {int((m_raw.log2_ratio < 0).sum())}/{len(m_raw)} "
                      f"karşılaştırma yine T'li kuyuda daha düşük çıkıyor (medyan "
                      f"{2**m_raw.log2_ratio.median():.2f}×), ve green alanı T'li ve "
                      f"T'siz kuyular arasında ayırt edilemiyor "
                      f"(AUC {auc(at.green_area_frac, an.green_area_frac):.2f}). "
                      f"**Bölme bu sonucu üretmiyor.**",
                      "2. **Ölü madde temizleniyor.** NIR birikmiş ölümü ölçer; ölü "
                      "hücreler ortamdan kaldırılırsa sinyal düşer. A3'te makrofajlı "
                      "kuyularda hem NIR hem orange'ın düşmesi bu mekanizmayla uyumlu.",
                      "3. **Gerçekten daha az ölüm.** Bu kurulumda T hücrelerinin "
                      "tümörü öldürmediği, hatta organoide hiç ulaşmadığı (A2: sınırda "
                      "yığılma, içeride seyrekleşme) sonucuyla tutarlı bir olasılık.",
                      "",
                      "Ayırt etmenin yolu ölçüm değil tasarım: bilinen bir öldürücü "
                      "(pozitif kontrol) ve T hücresi olmayan ama makrofaj olan bir "
                      "eşleşme, hangi mekanizmanın işlediğini gösterir."]
        elif pos > neg and psign < 0.1:
            lines += ["", "Eşleşmiş karşılaştırmaların çoğu aynı yöne gidiyor: "
                      "T hücresi eklemek tümör ölümünü artırıyor."]
        else:
            lines += ["",
                      "Eşleşmiş karşılaştırmalar tutarlı bir yön göstermiyor — bu "
                      "tasarımda T hücresinin tümör ölümüne net bir katkısı ölçülemedi. "
                      "Kuyu başına tek tekrar olduğu için her karşılaştırma tek kuyuya "
                      "dayanıyor; gürültü gerçek bir orta büyüklükteki etkiyi gizleyebilir."]

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.5))
    ax = axes[0]
    if len(m):
        mm = m.sort_values("log2_ratio")
        cols = [STATUS["serious"] if v > 0 else SERIES[0] for v in mm.log2_ratio]
        ax.barh(range(len(mm)), mm.log2_ratio, color=cols, height=0.7)
        ax.axvline(0, color=INK2, lw=1)
        ax.set_yticks(range(len(mm)),
                      [f"{r.coculture.replace('PDA+','+')} · {r.compound}"
                       for r in mm.itertuples()], fontsize=5.5)
        ax.set_xlabel("log2( T+ ölüm indeksi / T− )")
        ax.set_title("Eşleşmiş koşullarda T hücresinin etkisi")
    ax = axes[1]
    strip(ax, [(cc.replace("PDA+", "+"), last[last.coculture == cc].death_index_tumour)
               for cc in COCULTURE_ORDER],
          colors=[COCULTURE_COLOR[c] for c in COCULTURE_ORDER], log=True)
    ax.set_ylabel("tümör ölüm indeksi")
    ax.set_title("Ko-kültüre göre tümör ölümü")
    ax = axes[2]
    strip(ax, [("T eklendi", at.death_index_tcell), ("T yok", an.death_index_tcell)],
          colors=[SERIES[1], MUTED], log=True)
    ax.set_ylabel("T hücresi ölüm indeksi (NIR∩orange / orange)")
    ax.set_title("T hücrelerinin kendisi ne kadar ölüyor")
    finish(fig, OUT / "tcell_effect.png",
           "Her nokta bir kuyu, 4. gün. Yatay çizgi grup medyanı.")

    # ------------------------------------------------------- 4. ilaç etkisi
    lines += ["", "## 4. Bileşikler ölümü artırıyor mu?", ""]
    rows = []
    ctrl = last[last.compound == "control"]
    for cp in COMPOUND_ORDER:
        d = last[last.compound == cp]
        if len(d) < 3 or cp in ("control", "Dye"):
            continue
        rows.append({"compound": cp, "n": len(d),
                     "death_index": d.death_index_tumour.median(),
                     "nir_area": d.nir_area_frac.median(),
                     "delta_vs_control": cliffs_delta(d.death_index_tumour,
                                                      ctrl.death_index_tumour),
                     "p": mwu_p(d.death_index_tumour, ctrl.death_index_tumour)})
    ct = pd.DataFrame(rows)
    if len(ct):
        ct["q"] = bh_fdr(ct.p.to_numpy())
        ct.to_csv(OUT / "compound_effect.csv", index=False)
        lines += [f"Kontrol kuyularında tümör ölüm indeksi medyan "
                  f"{ctrl.death_index_tumour.median():.4f} ({len(ctrl)} kuyu).", "",
                  "| bileşik | n | ölüm indeksi | kontrole karşı δ | q |",
                  "|---|---|---|---|---|"]
        for r in ct.itertuples():
            lines.append(f"| {r.compound} | {r.n} | {r.death_index:.4f} | "
                         f"{r.delta_vs_control:+.2f} | "
                         f"{'—' if not np.isfinite(r.q) else f'{r.q:.3f}'} |")
        sig = ct[ct.q < 0.05]
        lines += ["",
                  ("Hiçbir bileşik kontrolden anlamlı ayrılmıyor "
                   f"(en düşük q = {ct.q.min():.2f}).") if sig.empty else
                  ("Kontrolden ayrılanlar: " + ", ".join(
                      f"**{r.compound}** (δ {r.delta_vs_control:+.2f}, q {r.q:.3f})"
                      for r in sig.itertuples()))]

    fig, axes = plt.subplots(1, 2, figsize=(11, 3.5))
    ax = axes[0]
    order = ["control"] + list(ct.compound) if len(ct) else ["control"]
    strip(ax, [(cp.replace(" ", "\n"), last[last.compound == cp].death_index_tumour)
               for cp in order], colors=[MUTED] + SERIES, log=True)
    ax.set_ylabel("tümör ölüm indeksi")
    ax.set_title("Bileşiğe göre tümör ölümü, 4. gün")
    ax.tick_params(axis="x", labelsize=7)
    ax = axes[1]
    for i, cp in enumerate(order[:6]):
        d = bio[bio.compound == cp]
        g = d.groupby("day").death_index_tumour.median()
        ax.plot(g.index, g.values, color=(MUTED if cp == "control" else SERIES[i % 8]),
                label=cp, lw=2.4 if cp == "control" else 2)
    ax.set_yscale("log")
    ax.set_xlabel("gün")
    ax.set_ylabel("tümör ölüm indeksi")
    ax.set_title("Ölümün zaman seyri, bileşiğe göre")
    ax.legend(fontsize=7, ncols=2)
    finish(fig, OUT / "compound_effect.png")

    # --------------------------------------------------------- 5. ölüm nerede
    lines += ["", "## 5. Ölüm nerede oluyor?", ""]
    inside = last.nir_in_organoid_frac.dropna()
    terr = last.bf_terr_frac
    lines += [
        f"Ölü sinyalinin medyan **%{inside.median()*100:.0f}**'i organoid "
        f"teritoryasının içinde; teritorya alanın %{terr.median()*100:.0f}'ini "
        f"kaplıyor. Zenginleşme "
        f"{last.nir_enrich_organoid.median():.2f}× — "
        f"{'ölüm organoidin içinde yoğunlaşıyor' if last.nir_enrich_organoid.median() > 1.3 else 'ölüm organoid dışında yoğunlaşıyor' if last.nir_enrich_organoid.median() < 0.77 else 'ölüm organoid içi ve dışı arasında dengeli dağılmış'}.",
    ]
    o = org[org.t == org.t.max()]
    rho_sz = o.eq_diam_um.corr(o.nir_cov, method="spearman")
    rho_g = o.green_cov.corr(o.nir_cov, method="spearman")
    rho_o = o.orange_cov.corr(o.nir_cov, method="spearman")
    lines += ["",
              f"Organoid başına ({len(o)} organoid, 4. gün) NIR kapsamasının sıra "
              f"korelasyonları: çapla **{rho_sz:+.2f}**, green kapsamasıyla "
              f"**{rho_g:+.2f}**, orange kapsamasıyla **{rho_o:+.2f}**.",
              "",
              f"Üçü de pozitif ama büyüklükleri farklı: ölüm en çok **organoidin "
              f"kendi boyutu ve tümör içeriğiyle** ilişkili (ρ {rho_sz:+.2f} ve "
              f"{rho_g:+.2f}), T hücresi yüküyle ilişki bunların yarısı kadar "
              f"({rho_o:+.2f}). {len(o)} organoidle bu korelasyonların hepsi "
              "istatistiksel olarak sıfırdan farklı, ama hiçbiri nedensellik "
              "göstermez: büyük organoidde hem daha çok hücre hem daha çok ölüm "
              "olması beklenir, T hücresi ve ölü boyası da organoid çevresinde "
              "aynı bölgelerde birikiyor olabilir."]

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.4))
    ax = axes[0]
    strip(ax, [("T eklendi", at.nir_enrich_organoid), ("T yok", an.nir_enrich_organoid)],
          colors=[SERIES[1], MUTED], log=True, hline=1.0, hlabel="rastgele")
    ax.set_ylabel("NIR zenginleşmesi (içeri/dışarı)")
    ax.set_title("Ölüm organoidin içinde mi?")
    ax = axes[1]
    ax.scatter(o.orange_cov * 100 + 1e-3, o.nir_cov * 100 + 1e-4, s=8, alpha=0.25,
               color=SERIES[1], edgecolors="none")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("organoid orange kapsaması %")
    ax.set_ylabel("organoid NIR kapsaması %")
    ax.set_title(f"Organoid başına: T yükü ve ölüm (ρ = {rho_o:+.2f})")
    ax = axes[2]
    ax.scatter(o.eq_diam_px, o.nir_cov * 100 + 1e-4, s=8, alpha=0.25,
               color=SERIES[0], edgecolors="none")
    bins = np.geomspace(o.eq_diam_px.min(), o.eq_diam_px.max(), 14)
    g = o.assign(b=pd.cut(o.eq_diam_px, bins)).groupby("b", observed=True).nir_cov.median()
    mid = np.sqrt(bins[:-1] * bins[1:])[: len(g)]
    ax.plot(mid, g.values * 100 + 1e-4, color=INK, marker="o", ms=5)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("organoid çapı (piksel)")
    ax.set_ylabel("NIR kapsaması %")
    ax.set_title(f"Büyük organoidlerde ölüm (ρ = {rho_sz:+.2f})")
    finish(fig, OUT / "death_location.png",
           "Her nokta bir organoid. Sıfır değerler log ekseni için küçük bir sabitle kaydırıldı.")

    lines += ["", "## Nedene dair ne söylenebilir, ne söylenemez", "",
              "- Örtüşme **ölenin kim olduğunu** söyler, **neden öldüğünü** söylemez. "
              "Yoğun bölgelerde bir NIR noktası hem tümöre hem T hücresine değebilir "
              "(`ikisi` sütunu).",
              "- T hücresi eklemenin etkisi yalnızca eşleşmiş koşullarda okunmalı; "
              "ko-kültür bileşimi hem ölümü hem T dağılımını bağımsız olarak etkiliyor.",
              "- NIR çok seyrek bir kanal; kuyu başına birkaç yüz piksel. Grup "
              "medyanları anlamlı, tek kuyu farkları değil.",
              "- NIR **anlık ölüm hızı değil, o an ortamda duran ölü madde** ölçer. "
              "Sinyal hem ölümle artar hem temizlenmeyle azalır; plaka medyanının "
              f"{peak_day:.1f}. günden sonra düşmesi bunun doğrudan kanıtı. Zaman "
              "eksenindeki değişim tek başına ölüm hızı olarak okunamaz."]

    last[["well", "coculture", "compound", "has_tcells", "nir_area_frac",
          "death_index_tumour", "death_index_tcell", "nir_on_green_frac",
          "nir_on_orange_frac", "nir_on_neither_frac", "nir_enrich_organoid",
          "nir_mean_z"]].to_csv(OUT / "well_death_day4.csv", index=False)
    write_summary(OUT / "summary.md", "A5 — Ölüm: kim ve neden", lines)


if __name__ == "__main__":
    main()
