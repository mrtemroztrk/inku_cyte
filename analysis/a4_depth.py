#!/usr/bin/env python3
"""A4 — Derinlik: T hücreleri organoidin neresinde duruyor?

z-yığını 17 düzlem; **z adımı hiçbir dosyada kayıtlı değil** ve odak kuyu başına
ayarlandığı için **z00 mutlak bir yükseklik değil**. Bu iki sınır analizin şeklini
belirliyor:

* Katman numarası kuyular arasında doğrudan karşılaştırılmaz. Bu yüzden her kuyu
  kendi **tümör tepesine hizalanıp** göreli derinlik profili çıkarılıyor.
* Mutlak mikron cinsinden derinlik verilmiyor; katman indeksi ve katman payları
  veriliyor. Mikron isteniyorsa tarama protokolündeki z adımıyla çarpılır.

Asıl soru — "T hücresi yalnız yüzeyde mi kaldı, derine indi mi" — bu kısıtlar
altında yanıtlanabilir, çünkü hem tümörün hem T hücresinin derinlik dağılımı aynı
z ekseninde ölçülüyor; ikisi arasındaki **kayma** kalibrasyon gerektirmiyor.

Çıktı: analysis/out/a4_depth/
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import (COCULTURE_COLOR, COCULTURE_ORDER, DIV, INK, INK2, MUTED, SEQ,
                    SERIES, auc, boot_ci, finish, load, mwu_p, outdir, qc_wells,
                    strip, timeseries, write_summary)
import matplotlib.pyplot as plt

OUT = outdir("a4_depth")
NZ = 17
CHNAME = {"green": "tümör (green)", "orange": "T hücresi (orange)", "nir": "ölü (NIR)"}
CHCOL = {"green": SERIES[5], "orange": SERIES[1], "nir": SERIES[0]}


def zprofile(d: pd.DataFrame, ch: str, inside: bool = False) -> np.ndarray:
    """Havuzlanmış z profili: gruptaki tüm kuyuların katman alanları toplanıp
    normalize edilir."""
    suf = "_in" if inside else ""
    v = np.array([d[f"{ch}_area_by_z{suf}_{z}"].sum() for z in range(NZ)], float)
    s = v.sum()
    return v / s if s > 0 else v


def aligned_profile(d: pd.DataFrame, ch: str, ref: str = "green") -> np.ndarray:
    """Her kuyuyu kendi `ref` kanalının tepe katmanına hizalayıp ortalama profil.
    z00 mutlak yükseklik olmadığı için kuyular arası tek geçerli hizalama bu."""
    acc = np.zeros(2 * NZ - 1)
    n = 0
    for _, r in d.iterrows():
        v = np.array([r[f"{ch}_area_by_z_{z}"] for z in range(NZ)], float)
        rf = np.array([r[f"{ref}_area_by_z_{z}"] for z in range(NZ)], float)
        if v.sum() <= 0 or rf.sum() <= 0:
            continue
        peak = int(np.argmax(rf))
        out = np.zeros(2 * NZ - 1)
        out[NZ - 1 - peak: 2 * NZ - 1 - peak] = v / v.sum()
        acc += out
        n += 1
    return acc / n if n else acc


def main():
    df = load()
    exc = qc_wells(df)
    df = df[~df.well.isin(exc) & (df.compound != "Dye")]
    last = df[df.t == df.t.max()]
    tp = last[last.t_added]
    lines: list[str] = []

    # ---------------------------------------------- 1. kanal başına derinlik
    lines += ["## 1. Kanallar derinlikte nerede", ""]
    rows = []
    for ch in ("green", "orange", "nir"):
        p = zprofile(last, ch)
        mz = last[f"{ch}_mean_z"].dropna()
        conc = last[f"{ch}_z_conc3"].dropna()
        rows.append({"channel": ch, "mean_z": mz.median(), "sd_z": last[f"{ch}_sd_z"].median(),
                     "top3_share": conc.median(), "peak_layer": int(np.argmax(p))})
        lines.append(f"- **{CHNAME[ch]}**: ağırlık merkezi z{mz.median():.1f}, "
                     f"katman başına yayılım {last[f'{ch}_sd_z'].median():.1f} katman, "
                     f"en yoğun 3 katmanın toplam sinyaldeki payı "
                     f"**%{conc.median()*100:.0f}**")
    pd.DataFrame(rows).to_csv(OUT / "channel_depth.csv", index=False)
    cg = last.green_z_conc3.median()
    co = last.orange_z_conc3.median()
    lines += ["",
              "Pay ne kadar yüksekse sinyal o kadar ince bir dilime sıkışmış demektir. "
              "17 katmana eşit yayılmış bir sinyalde bu pay %18 olurdu.",
              "",
              f"**Buradaki asıl bulgu tümör ile T hücresi arasındaki fark:** tümör "
              f"sinyali derinliğe yayılmış (en yoğun 3 katman %{cg*100:.0f}), T hücresi "
              f"sinyali çok daha ince bir dilime sıkışmış (%{co*100:.0f}, AUC "
              f"{auc(last.orange_z_conc3, last.green_z_conc3):.2f}). Tümör kütlesi "
              "17 katmanın çoğuna dağılırken T hücreleri tek bir düzlemde duruyor — "
              "derinlemesine nüfuz eden bir dağılımın beklenen görüntüsü bu değil."]

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.5))
    ax = axes[0]
    for ch in ("green", "orange", "nir"):
        ax.plot(range(NZ), zprofile(last, ch) * 100, color=CHCOL[ch], label=CHNAME[ch],
                marker="o", ms=4)
    ax.set_xlabel("z katmanı (mutlak yükseklik değil)")
    ax.set_ylabel("katmanın toplam sinyaldeki payı %")
    ax.set_title("Ham katman dağılımı, 4. gün")
    ax.legend(fontsize=7)

    ax = axes[1]
    x = np.arange(-(NZ - 1), NZ)
    for ch in ("green", "orange", "nir"):
        ax.plot(x, aligned_profile(last, ch) * 100, color=CHCOL[ch], label=CHNAME[ch],
                marker="o", ms=3)
    ax.axvline(0, color=INK2, lw=1)
    ax.set_xlim(-8, 8)
    ax.set_xlabel("tümör tepesine göre katman (0 = tümörün en yoğun katmanı)")
    ax.set_ylabel("pay %")
    ax.set_title("Tümör tepesine hizalanmış profil")
    ax.legend(fontsize=7)

    ax = axes[2]
    for i, cc in enumerate(COCULTURE_ORDER):
        d = tp[tp.coculture == cc]
        if d.empty:
            continue
        ax.plot(x, aligned_profile(d, "orange") * 100, color=COCULTURE_COLOR[cc],
                label=cc, marker="o", ms=3)
    ax.axvline(0, color=INK2, lw=1)
    ax.set_xlim(-8, 8)
    ax.set_xlabel("tümör tepesine göre katman")
    ax.set_ylabel("T hücresi payı %")
    ax.set_title("T hücresi derinliği, ko-kültüre göre")
    ax.legend(fontsize=7)
    finish(fig, OUT / "depth_profiles.png",
           "z adımı dosyalarda kayıtlı değil; eksen katman indeksi, mikron değil.")

    # ------------------------------------------- 2. tümöre göre göreli kayma
    lines += ["", "## 2. T hücreleri tümöre göre daha yüzeyde mi?", ""]
    d = tp.dropna(subset=["orange_mean_z", "green_mean_z"]).copy()
    d["dz"] = d.orange_mean_z - d.green_mean_z
    lo, hi = boot_ci(d.dz)
    from scipy.stats import wilcoxon
    try:
        pw = float(wilcoxon(d.dz).pvalue)
    except ValueError:
        pw = np.nan
    lines += [
        f"T eklenen {len(d)} kuyuda T hücresi ağırlık merkezi ile tümör ağırlık "
        f"merkezi arasındaki fark medyan **{d.dz.median():+.2f} katman** "
        f"(%95 GA {lo:+.2f}…{hi:+.2f}; Wilcoxon p = {pw:.2g}).",
        "",
        f"Negatif değer T hücrelerinin tümörden daha küçük z indislerinde durduğu "
        f"anlamına gelir. {int((d.dz < 0).sum())}/{len(d)} kuyuda kayma negatif — "
        "yön tutarlı ve Wilcoxon testi sıfırdan farkı destekliyor, ama medyanın güven "
        f"aralığı ({lo:+.2f}…{hi:+.2f}) geniş: **kaymanın varlığı sağlam, büyüklüğü "
        "değil.**",
        "",
        "Kaymanın işaretini mutlak derinliğe çevirmek için taramanın yönü (z00 kuyunun "
        "tabanı mı yüzeyi mi) bilinmeli; bu bilgi dosyalarda yok. Yani \"T hücreleri "
        "organoidin üstünde mi altında mı\" sorusu **tarama protokolü olmadan "
        "yanıtlanamaz** — ölçülen şey yalnızca ayrı bir düzlemde durdukları.",
    ]
    dead = last.dropna(subset=["nir_mean_z", "green_mean_z"]).copy()
    dead["dz"] = dead.nir_mean_z - dead.green_mean_z
    lines += ["",
              f"Aynı ölçüm ölü hücreler için: {dead.dz.median():+.2f} katman "
              f"({len(dead)} kuyu). Ölü sinyali "
              f"{'tümörle aynı derinlikte' if abs(dead.dz.median()) < 0.8 else 'tümörden farklı bir derinlikte'} "
              "yoğunlaşıyor."]

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.4))
    ax = axes[0]
    strip(ax, [(cc.replace("PDA+", "+"), d[d.coculture == cc].dz)
               for cc in COCULTURE_ORDER],
          colors=[COCULTURE_COLOR[c] for c in COCULTURE_ORDER], hline=0,
          hlabel="tümörle aynı katman")
    ax.set_ylabel("T hücresi z − tümör z (katman)")
    ax.set_title("T hücresinin tümöre göre derinlik kayması")

    ax = axes[1]
    ax.scatter(tp.green_mean_z, tp.orange_mean_z, s=22, color=SERIES[1],
               edgecolors="none", label="T eklendi")
    n_ = last[~last.t_added]
    ax.scatter(n_.green_mean_z, n_.orange_mean_z, s=22, color=MUTED, alpha=0.6,
               edgecolors="none", label="T yok")
    lim = [min(last.green_mean_z.min(), last.orange_mean_z.min()),
           max(last.green_mean_z.max(), last.orange_mean_z.max())]
    ax.plot(lim, lim, color=INK2, ls="--", lw=1)
    ax.set_xlabel("tümör ağırlık merkezi (katman)")
    ax.set_ylabel("orange ağırlık merkezi (katman)")
    ax.set_title("Kuyu başına derinlik eşleşmesi")
    ax.legend(fontsize=7)

    ax = axes[2]
    for i, ch in enumerate(("green", "orange", "nir")):
        g = df.groupby("day")[f"{ch}_z_conc3"].median()
        ax.plot(g.index, g.values * 100, color=CHCOL[ch], label=CHNAME[ch])
    ax.set_ylabel("en yoğun 3 katmanın payı %")
    ax.set_xlabel("gün")
    ax.set_title("Derinlikte yoğunlaşmanın zaman seyri")
    ax.legend(fontsize=7)
    finish(fig, OUT / "relative_depth.png",
           "Katman indeksi kuyular arası mutlak değil; kuyu içi farklar geçerlidir.")

    # ------------------------------------ 3. derinliğe göre infiltrasyon
    lines += ["", "## 3. İnfiltrasyon derinlikle değişiyor mu?", "",
              "Her z katmanında ayrı ayrı: o katmandaki orange sinyalinin ne kadarı "
              "organoid teritoryasının içinde? Teritorya 2B bir ayak izi olduğu için "
              "bu, \"organoidin üstünden mi geçiyor yoksa içine mi giriyor\" sorusunu "
              "katman katman ayırır.", ""]
    rows = []
    for ch in ("green", "orange", "nir"):
        tot = np.array([tp[f"{ch}_area_by_z_{z}"].sum() for z in range(NZ)], float)
        ins = np.array([tp[f"{ch}_area_by_z_in_{z}"].sum() for z in range(NZ)], float)
        with np.errstate(invalid="ignore", divide="ignore"):
            frac = np.where(tot > 0, ins / tot, np.nan)
        rows.append(pd.Series(frac, name=ch))
    zf = pd.concat(rows, axis=1)
    zf.index.name = "z"
    zf.to_csv(OUT / "inside_fraction_by_z.csv")

    org_frac = tp.bf_terr_frac.median()
    lines += [f"Karşılaştırma tabanı: bu kuyularda teritorya alanın medyan "
              f"%{org_frac*100:.0f}'ini kaplıyor, yani rastgele dağılmış bir sinyal "
              f"her katmanda %{org_frac*100:.0f} \"içeride\" çıkardı.", ""]
    o_in = zf["orange"].to_numpy()
    g_in = zf["green"].to_numpy()
    zpk = int(np.nanargmax([tp[f"green_area_by_z_{z}"].sum() for z in range(NZ)]))
    # profilin z ile eğilimi: katman indeksiyle sıra korelasyonu
    ok = np.isfinite(o_in)
    rho_z = pd.Series(o_in[ok]).corr(pd.Series(np.arange(NZ)[ok]), method="spearman")
    swing = np.nanmax(o_in) / max(np.nanmin(o_in), 1e-9)
    lines += [f"Orange için içeride kalan pay katmanlar arasında "
              f"%{np.nanmin(o_in)*100:.0f} ile %{np.nanmax(o_in)*100:.0f} arasında "
              f"değişiyor ({swing:.2f}× salınım); tümörün en yoğun olduğu katmanda "
              f"(z{zpk}) %{o_in[zpk]*100:.0f}. Karşılaştırma için green'in aynı "
              f"katmandaki içeride kalan payı %{g_in[zpk]*100:.0f}.",
              "",
              (f"Profil katman indeksiyle {'artıyor' if rho_z > 0 else 'azalıyor'} "
               f"(ρ = {rho_z:+.2f}): T hücrelerinin organoidle örtüşmesi derinliğe "
               "bağlı, tek bir sayıyla özetlenemez.") if abs(rho_z) > 0.5 else
              (f"Profil katman indeksiyle belirgin bir eğilim göstermiyor "
               f"(ρ = {rho_z:+.2f}) ve salınım rastgele beklentinin etrafında kalıyor: "
               "**T hücresi ile organoid arasındaki konum farkı derinlikte değil, "
               "yatay düzlemde.** Yani organoid içi/dışı ayrımı için MIP yeterli, "
               "z ekseni ek bilgi taşımıyor.")]

    fig, axes = plt.subplots(1, 2, figsize=(11, 3.5))
    ax = axes[0]
    for ch in ("green", "orange", "nir"):
        ax.plot(range(NZ), zf[ch] * 100, color=CHCOL[ch], label=CHNAME[ch], marker="o", ms=4)
    ax.axhline(org_frac * 100, color=MUTED, ls="--", lw=1)
    ax.text(NZ - 0.5, org_frac * 100, " rastgele beklenti", ha="right", va="bottom",
            fontsize=7, color=MUTED)
    ax.set_xlabel("z katmanı")
    ax.set_ylabel("organoid teritoryası içindeki pay %")
    ax.set_title("Katman katman organoid içi pay (T+ kuyular, 4. gün)")
    ax.legend(fontsize=7)

    ax = axes[1]
    m = np.full((len(COCULTURE_ORDER), NZ), np.nan)
    for i, cc in enumerate(COCULTURE_ORDER):
        d2 = tp[tp.coculture == cc]
        if d2.empty:
            continue
        m[i] = aligned_profile(d2, "orange") [NZ - 1 - 6: NZ - 1 + 11][:NZ]
    im = ax.imshow(m * 100, cmap=SEQ, aspect="auto")
    ax.set_yticks(range(len(COCULTURE_ORDER)), COCULTURE_ORDER, fontsize=7)
    ax.set_xticks(range(0, NZ, 2), [str(v) for v in range(-6, 11, 2)], fontsize=7)
    ax.set_xlabel("tümör tepesine göre katman")
    ax.set_title("T hücresi derinlik dağılımı")
    ax.grid(False)
    cb = ax.figure.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.set_label("pay %", fontsize=8)
    cb.outline.set_visible(False)
    finish(fig, OUT / "depth_infiltration.png",
           "\"İçeride\" = brightfield organoid teritoryasının 2B ayak izi.")

    # -------------------------------------- 4. 2B ve 3B ölçümler tutuyor mu
    lines += ["", "## 4. 2B projeksiyon 3B'yi temsil ediyor mu?", ""]
    a2 = tp.orange_frac_in_organoid.dropna()
    a3 = tp.orange_vox_in_organoid_frac.dropna()
    j = tp.dropna(subset=["orange_frac_in_organoid", "orange_vox_in_organoid_frac"])
    rho = j.orange_frac_in_organoid.corr(j.orange_vox_in_organoid_frac, method="spearman")
    lines += [
        f"MIP üzerinden ölçülen \"organoid içi pay\" ile tüm voksellerden ölçülen "
        f"pay arasındaki sıra korelasyonu **{rho:.3f}** (medyanlar "
        f"%{a2.median()*100:.1f} ve %{a3.median()*100:.1f}).",
        "",
        ("İkisi aynı sıralamayı veriyor: MIP tabanlı ölçümler bu veri için 3B "
         "ölçümlerin yerine geçebilir. Bu önemli, çünkü MIP ölçümü çok daha ucuz "
         "ve odak dışı sise karşı daha dayanıklı.") if rho > 0.9 else
        ("İkisi belirgin biçimde ayrışıyor — projeksiyon derinlikteki farkları "
         "gizliyor, 3B ölçüm ayrı bilgi taşıyor."),
    ]
    fig, ax = plt.subplots(figsize=(4.6, 3.6))
    ax.scatter(j.orange_frac_in_organoid * 100, j.orange_vox_in_organoid_frac * 100,
               s=24, color=SERIES[1], edgecolors="none")
    lim = [0, max(a2.max(), a3.max()) * 100]
    ax.plot(lim, lim, color=MUTED, ls="--", lw=1)
    ax.set_xlabel("MIP'ten organoid içi pay %")
    ax.set_ylabel("voksellerden organoid içi pay %")
    ax.set_title(f"2B ve 3B ölçüm (ρ = {rho:.2f})")
    finish(fig, OUT / "mip_vs_voxel.png")

    lines += ["", "## Sınırlar", "",
              "- **z adımı bilinmiyor.** Katman indeksi mikrona çevrilemedi; tüm "
              "derinlik sayıları katman biriminde.",
              "- **z00 mutlak değil.** Odak kuyu başına ayarlandığı için kuyular arası "
              "karşılaştırmalar yalnızca hizalanmış (göreli) profillerde geçerli.",
              "- **Eksenel çözünürlük düşük.** 2,798 µm/px bir 4× objektif demek "
              "(NA ≈ 0,13); her düzlemde odak dışı sis var, dekonvolüsyon uygulanmadı. "
              "Beklenen şey derinlik *dilimleri*, ince 3B yapı değil.",
              "- **Teritorya 2B.** Katman katman \"içeride\" payı, 2B ayak izine göre "
              "hesaplanır; gerçek bir 3B kapsanma testi değildir."]

    write_summary(OUT / "summary.md", "A4 — Derinlik ve 3B dağılım", lines)


if __name__ == "__main__":
    main()
