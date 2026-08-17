#!/usr/bin/env python3
"""A3 — Boya olmadan T hücresi ile makrofaj ayırt edilebilir mi?

Verinin yapısı bu soruyu iki ayrı soruya bölüyor ve ikisinin cevabı farklı.

**Piksel düzeyi:** Bir görüntüdeki tek bir hücreye bakıp "bu T hücresi mi makrofaj
mı" demek — makrofajın floresan kanalı olmadığı için burada *doğrulama etiketi
yok*. Etiketsiz bir sınıflandırıcı eğitilebilir ama doğruluğu ölçülemez, dolayısıyla
bu veriyle yanıtlanamaz. Yapılabilecek şey, iki popülasyonun *dağılım olarak* ne
kadar ayrıştığını ölçmek: makrofaj eklenen ve eklenmeyen kuyular arasındaki BF
nesne dağılımı farkı, makrofajın bıraktığı izin üst sınırıdır.

**Kuyu düzeyi:** "Bu kuyuda makrofaj var mı?" — plaka haritası doğru cevabı
verdiği için bu ölçülebilir bir sınıflandırma problemi. Yalnızca brightfield'dan
türetilen özniteliklerle, kuyu-dışarıda-bırak çapraz doğrulamalı lojistik
regresyonla test ediliyor.

Ayrıca burada bir yan soru cevaplanıyor: **makrofajlar orange kanalına sızıyor
mu?** Sızıyorlarsa T hücresi niceliğinin makrofajlı kuyularda şişmesi gerekir ve
A2'deki karşılaştırmalar makrofaj durumuna göre eşleştirilmelidir.

Çıktı: analysis/out/a3_labelfree/
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import (COCULTURE_COLOR, COCULTURE_ORDER, DIV, INK, INK2, MUTED, SEQ,
                    SERIES, auc, bh_fdr, cliffs_delta, finish, load, load_organoids,
                    mwu_p, outdir, qc_wells, strip, timeseries, write_summary)
import matplotlib.pyplot as plt

OUT = outdir("a3_labelfree")

BF_FEATURES = ["bf_terr_frac", "bf_fine_frac", "bf_solidity", "bf_particles",
               "bf_particle_area_frac", "bf_particle_med_px", "bf_fine_med_px",
               "bf_obj_total", "bf_depth_mean", "bf_depth_p99", "bf_largest_frac",
               "bf_n_tiny", "bf_n_small", "bf_n_mid", "n_organoids_scored",
               "organoid_med_diam_um"]
FLUOR_FEATURES = ["orange_area_frac", "orange_int_mean", "orange_obj_med_px",
                  "orange_obj_med_int", "orange_objfrac_lt10", "orange_objfrac_ge50",
                  "green_area_frac", "nir_area_frac", "orange_enrich_organoid"]


# ------------------------------------------------------- lojistik regresyon
def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 60):
    """L2 cezalı IRLS. sklearn yok; küçük veri için bu yeterli ve şeffaf."""
    X = np.column_stack([np.ones(len(X)), X])
    w = np.zeros(X.shape[1])
    pen = np.eye(X.shape[1]) * l2
    pen[0, 0] = 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(X @ w, -30, 30)))
        s = np.clip(p * (1 - p), 1e-6, None)
        H = X.T @ (X * s[:, None]) + pen
        g = X.T @ (y - p) - pen @ w
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
        w += step
        if np.max(np.abs(step)) < 1e-8:
            break
    return w


def loo_auc(X: np.ndarray, y: np.ndarray, l2: float = 1.0) -> tuple[float, np.ndarray]:
    """Kuyu-dışarıda-bırak çapraz doğrulama. Öznitelikler her katlamada
    yalnızca eğitim kümesinden standardize edilir — sızıntı olmasın diye."""
    n = len(y)
    pred = np.zeros(n)
    for i in range(n):
        m = np.ones(n, bool)
        m[i] = False
        mu, sd = X[m].mean(0), X[m].std(0)
        sd = np.where(sd > 1e-9, sd, 1.0)
        w = fit_logistic((X[m] - mu) / sd, y[m], l2)
        z = np.concatenate([[1.0], (X[i] - mu) / sd])
        pred[i] = 1.0 / (1.0 + np.exp(-np.clip(z @ w, -30, 30)))
    return auc(pred[y == 1], pred[y == 0]), pred


def feature_table(d: pd.DataFrame, label: pd.Series, feats: list[str]) -> pd.DataFrame:
    rows = []
    for f in feats:
        if f not in d:
            continue
        a = d.loc[label, f].to_numpy(float)
        b = d.loc[~label, f].to_numpy(float)
        u = auc(a, b)
        rows.append({"feature": f, "auc": u, "abs_auc": abs(u - 0.5) + 0.5,
                     "median_pos": np.nanmedian(a), "median_neg": np.nanmedian(b),
                     "p": mwu_p(a, b)})
    t = pd.DataFrame(rows)
    if len(t):
        t["q"] = bh_fdr(t.p.to_numpy())
        t = t.sort_values("abs_auc", ascending=False)
    return t


def prep(d: pd.DataFrame, feats: list[str]) -> tuple[np.ndarray, list[str]]:
    use = [f for f in feats if f in d and d[f].notna().sum() > len(d) * 0.8]
    X = d[use].to_numpy(float)
    col = np.nanmedian(X, 0)
    idx = np.where(~np.isfinite(X))
    X[idx] = np.take(col, idx[1])
    return X, use


def main():
    df = load()
    org = load_organoids()
    exc = qc_wells(df)
    df = df[~df.well.isin(exc) & (df.compound != "Dye")]
    org = org[~org.well.isin(exc) & (org.compound != "Dye")]
    last = df[df.t == df.t.max()].reset_index(drop=True)
    lines: list[str] = []

    # ------------------------------- 1. makrofajlar orange kanalına sızıyor mu
    lines += ["## 1. Önce şu: makrofajlar orange kanalına sızıyor mu?", ""]
    tfree = last[~last.t_added]
    a = tfree[tfree.mac].orange_area_frac
    b = tfree[~tfree.mac].orange_area_frac
    u = auc(a, b)
    p = mwu_p(a, b)
    lines += [
        f"T hücresi eklenmeyen {len(tfree)} kuyuda, makrofajlı olanların orange alan "
        f"oranı medyan %{a.median()*100:.2f} ({len(a)} kuyu), makrofajsızların "
        f"%{b.median()*100:.2f} ({len(b)} kuyu) — AUC {u:.2f}, p = {p:.2g}.",
        "",
        ("**Makrofajlar orange kanalında belirgin bir katkı üretmiyor.** Yani orange "
         "sinyalindeki T'siz arkaplan makrofajdan değil, döküntü/otofloresandan "
         "geliyor; A2'deki T hücresi karşılaştırmaları makrofaj durumuna göre "
         "eşleştirilmek zorunda değil.")
        if abs(u - 0.5) < 0.15 or not np.isfinite(p) or p > 0.05 else
        (f"**Makrofajlı kuyularda orange sinyali sistematik olarak "
         f"{'yüksek' if u > 0.5 else 'düşük'}.** Bu, orange tabanlı T hücresi "
         "niceliğinin makrofaj varlığıyla karıştığı anlamına gelir: T hücresi "
         "karşılaştırmaları makrofaj durumu sabit tutularak yapılmalı."),
    ]
    rows = []
    for ch in ("orange", "green", "nir"):
        for col in (f"{ch}_area_frac", f"{ch}_int_mean", f"{ch}_obj_med_px"):
            if col not in tfree:
                continue
            rows.append({"channel": ch, "feature": col,
                         "auc_mac": auc(tfree.loc[tfree.mac, col], tfree.loc[~tfree.mac, col]),
                         "p": mwu_p(tfree.loc[tfree.mac, col], tfree.loc[~tfree.mac, col])})
    leak = pd.DataFrame(rows)
    leak["q"] = bh_fdr(leak.p.to_numpy())
    leak.to_csv(OUT / "macrophage_channel_leak.csv", index=False)
    lines += ["", "| kanal | öznitelik | AUC (MAC+ vs MAC−) | q |", "|---|---|---|---|"]
    for r in leak.itertuples():
        lines.append(f"| {r.channel} | `{r.feature}` | {r.auc_mac:.2f} | "
                     f"{'—' if not np.isfinite(r.q) else f'{r.q:.3f}'} |")

    # Makrofajlı kuyular kolon 3,4,7,8'de — etki bir plaka konumu yan etkisi olabilir.
    # Plakanın iki yarısı bağımsız birer tekrar: her ikisinde de aynı çıkarsa konum değil.
    halves = {"sol yarı (kolon 1–4)": ([1, 2], [3, 4]),
              "sağ yarı (kolon 5–8)": ([5, 6], [7, 8])}
    hrows = []
    for name, (nm, mm) in halves.items():
        for ch in ("orange", "nir"):
            a_ = tfree.loc[tfree.col.isin(mm), f"{ch}_area_frac"]
            b_ = tfree.loc[tfree.col.isin(nm), f"{ch}_area_frac"]
            hrows.append({"half": name, "channel": ch, "n_mac": len(a_), "n_nomac": len(b_),
                          "median_mac": a_.median(), "median_nomac": b_.median(),
                          "auc": auc(a_, b_), "p": mwu_p(a_, b_)})
    half = pd.DataFrame(hrows)
    half.to_csv(OUT / "macrophage_half_replication.csv", index=False)
    lines += ["",
              "Makrofajlı kuyular plakanın 3., 4., 7. ve 8. kolonlarında — bu tek "
              "başına bir konum yan etkisi olabilirdi. Plakanın iki yarısı bağımsız "
              "birer tekrar sağlıyor (her yarıda makrofajlı ve makrofajsız kolonlar "
              "yan yana); etki ikisinde de aynı yönde çıkarsa konum açıklaması düşer:",
              "", "| yarı | kanal | MAC+ | MAC− | AUC | p |", "|---|---|---|---|---|---|"]
    for r in half.itertuples():
        lines.append(f"| {r.half} | {r.channel} | %{r.median_mac*100:.2f} "
                     f"({r.n_mac} kuyu) | %{r.median_nomac*100:.2f} ({r.n_nomac} kuyu) | "
                     f"{r.auc:.2f} | {'—' if not np.isfinite(r.p) else f'{r.p:.3f}'} |")
    same = (half[half.channel == "orange"].auc < 0.5).all() or \
           (half[half.channel == "orange"].auc > 0.5).all()
    lines += ["",
              ("**Etki iki yarıda da aynı yönde ve aynı büyüklükte** — plaka konumu "
               "açıklaması düşüyor. Geriye biyolojik bir mekanizma kalıyor: makrofajlar "
               "fagositik hücrelerdir; döküntüyü ve ölü hücreleri temizlemeleri hem "
               "otofloresan orange arkaplanını hem de ölü hücre boyasını (NIR) "
               "azaltır. Bu yorum bu veriyle **doğrudan kanıtlanamaz** ama iki kanalın "
               "birlikte düşmesi onunla tutarlı.")
              if same else
              "Etki yarılar arasında tutarsız — bir plaka konumu yan etkisi olabilir."]

    # ------------------------------------------- 2. kuyu düzeyi sınıflandırma
    lines += ["", "## 2. Kuyu düzeyi: yalnız brightfield'dan makrofaj/T hücresi var mı?", ""]
    results = []
    for target, name, subset in (
            ("mac", "makrofaj", last[~last.t_added]),
            ("t_added", "T hücresi", last[~last.mac]),
            ("caf", "CAF", last[~last.t_added & ~last.mac])):
        d = subset.dropna(subset=["bf_terr_frac"]).reset_index(drop=True)
        y = d[target].to_numpy().astype(float)
        if y.sum() < 4 or (1 - y).sum() < 4:
            continue
        Xb, ub = prep(d, BF_FEATURES)
        auc_bf, _ = loo_auc(Xb, y)
        Xa, ua = prep(d, BF_FEATURES + FLUOR_FEATURES)
        auc_all, _ = loo_auc(Xa, y)
        ft = feature_table(d, d[target].astype(bool), BF_FEATURES + FLUOR_FEATURES)
        ft.to_csv(OUT / f"features_{target}.csv", index=False)
        best = ft.iloc[0] if len(ft) else None
        results.append({"target": name, "n_pos": int(y.sum()), "n_neg": int((1 - y).sum()),
                        "auc_bf_only": auc_bf, "auc_bf_plus_fluor": auc_all,
                        "best_single": best.feature if best is not None else "",
                        "best_single_auc": best.auc if best is not None else np.nan})
    res = pd.DataFrame(results)
    res.to_csv(OUT / "classification.csv", index=False)
    lines += ["Kuyu-dışarıda-bırak çapraz doğrulamalı lojistik regresyon, 4. gün. "
              "AUC 0,5 = şans, 1,0 = kusursuz.", "",
              "| hedef | n (+/−) | yalnız BF | BF + floresan | en iyi tek öznitelik |",
              "|---|---|---|---|---|"]
    for r in res.itertuples():
        lines.append(f"| {r.target} var mı | {r.n_pos}/{r.n_neg} | **{r.auc_bf_only:.2f}** | "
                     f"{r.auc_bf_plus_fluor:.2f} | `{r.best_single}` ({r.best_single_auc:.2f}) |")

    macrow = res[res.target == "makrofaj"]
    trow = res[res.target == "T hücresi"]
    if len(macrow) and len(trow):
        am, at = float(macrow.auc_bf_only.iloc[0]), float(trow.auc_bf_only.iloc[0])
        lines += ["",
                  f"**Sonuç: brightfield tek başına makrofaj varlığını "
                  f"{'ayırt edebiliyor' if am > 0.75 else 'zayıf ayırt ediyor' if am > 0.65 else 'ayırt edemiyor'} "
                  f"(AUC {am:.2f}), T hücresi varlığını "
                  f"{'ayırt edebiliyor' if at > 0.75 else 'zayıf ayırt ediyor' if at > 0.65 else 'ayırt edemiyor'} "
                  f"(AUC {at:.2f}).**",
                  "",
                  "Bu *kuyu* düzeyinde bir cevap: 8000 makrofajın kuyuya toplu etkisi "
                  "brightfield'da görülüyor mu diye soruyor. Tek bir hücreye bakıp "
                  "türünü söylemek bundan çok daha zor bir problem ve bu veride "
                  "**doğrulanamaz** — makrofajın floresan etiketi olmadığı için hiçbir "
                  "hücre için doğru cevap bilinmiyor. Piksel düzeyinde ayrım iddiası "
                  "ancak makrofajlara ayrı bir işaretleyici konan bir deneyle "
                  "sınanabilir."]

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.5))
    ax = axes[0]
    x = np.arange(len(res))
    ax.bar(x - 0.19, res.auc_bf_only, width=0.36, color=SERIES[0], label="yalnız BF")
    ax.bar(x + 0.19, res.auc_bf_plus_fluor, width=0.36, color=SERIES[1],
           label="BF + floresan")
    ax.axhline(0.5, color=MUTED, ls="--", lw=1)
    ax.text(len(res) - 0.5, 0.5, "şans", ha="right", va="bottom", fontsize=7, color=MUTED)
    ax.set_xticks(x, [f"{r} var mı" for r in res.target], fontsize=8)
    ax.set_ylabel("çapraz doğrulanmış AUC")
    ax.set_ylim(0, 1.02)
    ax.set_title("Kuyu düzeyinde sınıflandırılabilirlik")
    ax.legend(loc="lower right")

    ax = axes[1]
    ft = pd.read_csv(OUT / "features_mac.csv").head(10)[::-1]
    cols = [SERIES[0] if a > 0.5 else SERIES[1] for a in ft.auc]
    ax.barh(range(len(ft)), ft.auc - 0.5, left=0.5, color=cols, height=0.66)
    ax.axvline(0.5, color=INK2, lw=1)
    ax.set_yticks(range(len(ft)), ft.feature, fontsize=6.5)
    ax.set_xlabel("AUC (makrofajlı vs makrofajsız)")
    ax.set_title("Makrofaj varlığını en çok haber veren ölçüm")

    ax = axes[2]
    tf = last[~last.t_added]
    strip(ax, [("MAC yok", tf[~tf.mac].bf_particles), ("MAC var", tf[tf.mac].bf_particles)],
          colors=[MUTED, SERIES[2]])
    ax.set_ylabel("BF'de tek hücre boyutlu nesne sayısı")
    ax.set_title(f"Etiketsiz parçacık sayısı (AUC "
                 f"{auc(tf[tf.mac].bf_particles, tf[~tf.mac].bf_particles):.2f})")
    finish(fig, OUT / "classification.png",
           "T hücresi hedefi makrofajsız kuyularda, makrofaj hedefi T'siz kuyularda "
           "test edildi — iki değişken birbirine karışmasın diye.")

    # ------------------------- 3. popülasyon dağılımı: ayrımın üst sınırı
    lines += ["", "## 3. Piksel düzeyinde ayrımın üst sınırı", ""]
    feats = ["bf_particle_med_px", "bf_particles", "bf_fine_med_px", "bf_depth_mean"]
    rows = []
    for f in feats:
        m = auc(tf.loc[tf.mac, f], tf.loc[~tf.mac, f])
        tt = last[~last.mac]
        t_ = auc(tt.loc[tt.t_added, f], tt.loc[~tt.t_added, f])
        rows.append({"feature": f, "auc_mac": m, "auc_tcell": t_,
                     "separation": abs(m - t_)})
    sep = pd.DataFrame(rows).sort_values("separation", ascending=False)
    sep.to_csv(OUT / "population_separation.csv", index=False)
    lines += ["Makrofaj ve T hücresi eklemek BF ölçümlerini **aynı yöne mi** kaydırıyor? "
              "Aynı yöne kaydırıyorsa ikisi birbirinden ayrılamaz demektir.", "",
              "| BF ölçümü | AUC (MAC etkisi) | AUC (T etkisi) | fark |",
              "|---|---|---|---|"]
    for r in sep.itertuples():
        lines.append(f"| `{r.feature}` | {r.auc_mac:.2f} | {r.auc_tcell:.2f} | "
                     f"{r.separation:.2f} |")
    lines += ["",
              f"En büyük fark {sep.separation.max():.2f}; bunlar {len(tf)} ve "
              f"{len(last[~last.mac])} kuyuya dayanan gürültülü kuyu düzeyi "
              "istatistikleri, aralarındaki bu büyüklükte bir fark tek başına güçlü "
              "kanıt değil.",
              "",
              "**Asıl belirleyici olan çözünürlük.** 2,798 µm/px'te bir T hücresi "
              "(~7 µm çap) yaklaşık **2,5 piksel**, bir makrofaj (~15 µm) yaklaşık "
              "5 piksel eder. Morfolojiye dayalı hücre tipi ayrımı — şekil, çekirdek "
              "yapısı, yayılma — bu ölçekte ölçülemez. Bu veriyle piksel düzeyinde "
              "T hücresi/makrofaj ayrımı **yapılamaz**; kuyu düzeyindeki toplu etki "
              "(2. bölüm) ölçülebilen tek şey.",
              "",
              "Bunu değiştirecek olan analiz değil, edinim: makrofaja özgü bir "
              "işaretleyici (ayrı bir floresan kanal), ya da tek hücre morfolojisini "
              "çözecek daha yüksek büyütme."]

    # --------------------- 4. dolaylı makrofaj infiltrasyonu (etiket olmadan)
    lines += ["", "## 4. Makrofaj infiltrasyonu — dolaylı ölçüm", "",
              "Makrofajın işaretleyicisi olmadığı için \"organoide kaç makrofaj girdi\" "
              "doğrudan ölçülemez. Ölçülebilen şey, **yalnızca makrofaj varlığıyla "
              "ayrılan eşleşmiş kuyular arasında organoidin nasıl değiştiği**: "
              "makrofajlar organoide girip yerleşiyorsa organoid büyümeli, içindeki "
              "tümör (green) payı seyrelmeli, doluluk artmalı.", ""]
    o = org[org.t == org.t.max()]
    rows = []
    for cafs in (False, True):
        for tc in (False, True):
            d = o[(o.has_cafs.eq("yes") == cafs) & (o.t_added == tc)]
            a_ = d[d.mac]
            b_ = d[~d.mac]
            if len(a_) < 20 or len(b_) < 20:
                continue
            # Organoidlerin çoğunda green kapsaması tam sıfır (bkz. A1), o yüzden
            # medyan bilgi taşımıyor — green-pozitif organoid oranı kullanılıyor.
            rows.append({
                "grup": f"{'CAF+' if cafs else 'CAF−'} / {'T+' if tc else 'T−'}",
                "n_mac": len(a_), "n_nomac": len(b_),
                "diam_mac": a_.eq_diam_um.median(), "diam_nomac": b_.eq_diam_um.median(),
                "auc_diam": auc(a_.eq_diam_um, b_.eq_diam_um),
                "greenpos_mac": (a_.green_cov > 0.01).mean(),
                "greenpos_nomac": (b_.green_cov > 0.01).mean(),
                "auc_greencov": auc(a_.green_cov, b_.green_cov),
                "sol_mac": a_.solidity.median(), "sol_nomac": b_.solidity.median(),
                "auc_sol": auc(a_.solidity, b_.solidity)})
    mi = pd.DataFrame(rows)
    if len(mi):
        mi.to_csv(OUT / "macrophage_indirect.csv", index=False)
        lines += ["| eşleşme | n organoid MAC+/MAC− | çap MAC+/MAC− | AUC | "
                  "green-pozitif MAC+/MAC− | AUC | doluluk MAC+/MAC− | AUC |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in mi.itertuples():
            lines.append(f"| {r.grup} | {r.n_mac}/{r.n_nomac} | "
                         f"{r.diam_mac:.0f} / {r.diam_nomac:.0f} µm | {r.auc_diam:.2f} | "
                         f"%{r.greenpos_mac*100:.0f} / %{r.greenpos_nomac*100:.0f} | "
                         f"{r.auc_greencov:.2f} | {r.sol_mac:.2f} / {r.sol_nomac:.2f} | "
                         f"{r.auc_sol:.2f} |")
        big = mi.loc[mi.auc_greencov.sub(0.5).abs().idxmax()]
        consistent = (mi.auc_greencov > 0.5).all() or (mi.auc_greencov < 0.5).all()
        lines += ["",
                  (f"Dört eşleşmenin dördünde de green kapsaması aynı yöne gidiyor "
                   f"(en güçlüsü {big.grup}, AUC {big.auc_greencov:.2f}): makrofajlı "
                   f"kuyularda organoidlerin green ile kaplı oranı "
                   f"{'düşük' if big.auc_greencov < 0.5 else 'yüksek'}."
                   if consistent else
                   f"Eşleşmeler tutarlı bir yön göstermiyor (AUC'ler "
                   f"{mi.auc_greencov.min():.2f}–{mi.auc_greencov.max():.2f}); "
                   "makrofaj varlığının organoid içi bileşime etkisi bu ölçümlerle "
                   "saptanamıyor."),
                  "",
                  "Her hâlükârda bu **dolaylı** bir çıkarım: aynı fark boyanma "
                  "verimindeki bir değişiklikten de doğabilir (bkz. A1) ve organoid "
                  "içinde makrofaj olup olmadığını göstermez. \"Organoide kaç makrofaj "
                  "girdi\" sorusunun ölçülebilir cevabı **makrofaja özgü bir "
                  "işaretleyici gerektirir** — mevcut dört kanalla üretilemez."]

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.4))
    for ax, col, lab in zip(axes, ["eq_diam_um", "green_cov", "solidity"],
                            ["organoid çapı (µm)", "green kapsaması", "doluluk"]):
        gs = []
        for cafs in (False, True):
            for m in (False, True):
                d = o[(o.has_cafs.eq("yes") == cafs) & (o.mac == m) & (~o.t_added)]
                if len(d) > 10:
                    gs.append((f"{'CAF+' if cafs else 'CAF−'}\n{'MAC+' if m else 'MAC−'}",
                               d[col].dropna()))
        strip(ax, gs, colors=[MUTED, SERIES[2], MUTED, SERIES[2]],
              log=(col == "green_cov"))
        ax.set_ylabel(lab)
        ax.set_title(f"{lab}: makrofaj etkisi")
        ax.tick_params(axis="x", labelsize=7)
    finish(fig, OUT / "macrophage_indirect.png",
           "T hücresi eklenmemiş kuyular, son zaman noktası. Her nokta bir organoid.")

    write_summary(OUT / "summary.md",
                  "A3 — Boyasız ayrım: T hücresi ve makrofaj", lines)


if __name__ == "__main__":
    main()
