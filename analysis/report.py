#!/usr/bin/env python3
"""Altı analizin özetlerini ve figürlerini tek bir HTML rapora birleştirir.

Figürler data URI olarak gömülür — rapor tek dosya, dışarıya bağımlılığı yok.

  python3 analysis/report.py            # → analysis/out/rapor.html
"""
from __future__ import annotations

import base64
import html
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

SECTIONS = [
    ("a1_qc", "A1", "Kalite ve boyama kapsamı",
     "Hangi kuyular yorumlanabilir, green organoidlerin kaçını boyuyor",
     "bf"),
    ("a2_infiltration", "A2", "T hücresi infiltrasyonu",
     "Organoide ne kadar T hücresi giriyor", "orange"),
    ("a3_labelfree", "A3", "Boyasız ayrım",
     "T hücresi ile makrofaj boya olmadan ayırt edilebilir mi", "bf"),
    ("a4_depth", "A4", "Derinlik ve 3B dağılım",
     "T hücreleri organoidin neresinde duruyor", "orange"),
    ("a5_death", "A5", "Ölüm: kim ve neden",
     "Hangi hücre tipi ölüyor, neye bağlanabilir", "nir"),
    ("a6_growth", "A6", "Büyüme ve ilaç yanıtı",
     "Organoid nasıl büyüdü, bileşikler ne yaptı", "green"),
]

# Her bölümün başına konan tek cümlelik cevap ve yanıtlanamayan soru.
# Bunlar summary.md'lerdeki ölçümlerden elle özetlendi; sayılar orada.
VERDICT = {
    "a1_qc": ("88 kuyudan 84'ü kullanılabilir, ama <b>green organoidlerin yalnızca "
              "bir azınlığını boyuyor</b> — BF'de görülen organoidlerin medyan %15'inde "
              "green sinyali var, PDA'nın tek başına olduğu kuyularda %10.",
              "Boyanmamış organoid ile tümör olmayan BF nesnesi (CAF/makrofaj kümesi, "
              "döküntü) birbirinden ayrılamıyor."),
    "a2_infiltration": ("T hücreleri organoid sınırının <b>hemen dışında yığılıyor, "
                        "içeri girmiyor</b>. Zenginleşme medyanı 0,79 (rastgele = 1,0) "
                        "ve dört ko-kültürün dördünde de T'siz eşdeğerinin altında.",
                        "Bileşiklerin infiltrasyona etkisi ölçülemedi — bileşik başına "
                        "3–4 kuyu var."),
    "a3_labelfree": ("<b>Piksel düzeyinde ayrım bu veriyle yapılamaz</b>; makrofajın "
                     "işaretleyicisi yok ve 2,798 µm/px'te bir T hücresi ~2,5 piksel. "
                     "Kuyu düzeyinde makrofaj varlığı BF'den zayıf (AUC 0,74), T hücresi "
                     "varlığı iyi (AUC 0,88) kestiriliyor.",
                     "\"Organoide kaç makrofaj girdi\" — makrofaja özgü bir işaretleyici "
                     "olmadan ölçülemez."),
    "a4_depth": ("T hücresi sinyali <b>tümörden çok daha ince bir dilime sıkışmış</b> "
                 "(en yoğun 3 katman %66 vs %41) ve tümör kütlesinden ayrı bir katmanda "
                 "duruyor (medyan −1,2 katman, 18/27 kuyuda aynı yönde).",
                 "Mutlak derinlik: z adımı ve tarama yönü hiçbir dosyada kayıtlı değil."),
    "a5_death": ("T'siz kuyularda ölü sinyalinin %50'si tümörle örtüşüyor; T eklenince "
                 "bu %28'e düşüyor ve <b>tümör ölüm indeksi eşleşmiş karşılaştırmaların "
                 "12/15'inde azalıyor</b> — beklenenin tersi bir yön.",
                 "Ölümün nedeni: örtüşme kimin öldüğünü söyler, niçin öldüğünü söylemez."),
    "a6_growth": ("Kuyular 4 günde <b>tek bir sıkı kütleye toplanıyor</b> (en büyük "
                  "nesnenin payı 0,36 → 0,86) ve toplanma arttıkça T hücresi dışlanıyor "
                  "(ρ = −0,63). CAF ve CAF+MAC büyümeyi anlamlı biçimde yavaşlatıyor.",
                  "Bileşiklerin büyümeye etkisi yön veriyor ama anlamlılığa ulaşmıyor."),
}

FIG_CAPTION = {
    "qc_plate.png": "Plaka genelinde yapı puanı, BF teritorya payı ve bayraklı kare oranı.",
    "staining_coverage.png": "Green-pozitif organoid oranı: ko-kültüre, zamana ve organoid boyutuna göre.",
    "threshold_sensitivity.png": "Eşik ×0,67 ve ×1,67 kaydırıldığında kuyu sıralaması korunuyor.",
    "background_drift.png": "Kanal arkaplanlarının ve BF yapı puanının zaman seyri.",
    "orange_signal_control.png": "Orange kanalının T hücresi eklemesiyle ilişkisi — ölçümün geçerlilik kontrolü.",
    "enrichment.png": "Organoid içi/dışı yoğunluk oranı: ko-kültüre, zamana ve kuyuya göre.",
    "distance_profile.png": "Organoid sınırına işaretli uzaklığa göre T hücresi yoğunluğu.",
    "per_organoid.png": "Organoid başına T yükü: boyuta, doluluğa ve ko-kültüre göre.",
    "compound_effect.png": "Bileşiğe göre dağılım.",
    "classification.png": "Kuyu düzeyinde sınıflandırılabilirlik ve en bilgilendirici ölçümler.",
    "macrophage_indirect.png": "Makrofaj varlığının organoid morfolojisine dolaylı etkisi.",
    "depth_profiles.png": "Ham ve tümör tepesine hizalanmış katman dağılımları.",
    "relative_depth.png": "T hücresinin tümöre göre derinlik kayması.",
    "depth_infiltration.png": "Katman katman organoid teritoryası içindeki pay.",
    "mip_vs_voxel.png": "Projeksiyon tabanlı ve voksel tabanlı ölçümün karşılaştırması.",
    "death_overview.png": "Ölü hücre sinyalinin büyüklüğü, zaman seyri ve plaka dağılımı.",
    "attribution.png": "Ölü sinyalinin hangi kanalla örtüştüğü ve kütleye bölünmüş ölüm indeksi.",
    "tcell_effect.png": "Eşleşmiş koşullarda T hücresi eklemenin ölüme etkisi.",
    "death_location.png": "Ölümün organoide göre konumu ve organoid başına dağılımı.",
    "growth.png": "Kütle artışı ve ko-kültüre göre büyüme hızı.",
    "aggregation.png": "Toplanmanın zaman seyri ve T hücresi dışlanmasıyla ilişkisi.",
    "size_distribution.png": "Organoid boyut dağılımı ve sayısının zaman içindeki değişimi.",
    "compound_growth.png": "Bileşiğe göre büyüme hızı ve kütle eğrileri.",
}

FIG_ORDER = {
    "a1_qc": ["qc_plate.png", "staining_coverage.png", "threshold_sensitivity.png",
              "background_drift.png"],
    "a2_infiltration": ["orange_signal_control.png", "enrichment.png",
                        "distance_profile.png", "per_organoid.png", "compound_effect.png"],
    "a3_labelfree": ["classification.png", "macrophage_indirect.png"],
    "a4_depth": ["depth_profiles.png", "relative_depth.png", "depth_infiltration.png",
                 "mip_vs_voxel.png"],
    "a5_death": ["death_overview.png", "attribution.png", "tcell_effect.png",
                 "compound_effect.png", "death_location.png"],
    "a6_growth": ["growth.png", "aggregation.png", "size_distribution.png",
                  "compound_growth.png"],
}


# ------------------------------------------------------------------ markdown
def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


def md(text: str) -> str:
    """Özetlerde kullanılan alt küme: başlık, tablo, liste, paragraf, yatay çizgi."""
    out: list[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        if ln.startswith("---"):
            out.append("<hr>")
            i += 1
        elif ln.startswith("#"):
            lvl = len(ln) - len(ln.lstrip("#"))
            txt = ln.lstrip("#").strip()
            tag = {1: "h2", 2: "h3", 3: "h4"}.get(lvl, "h4")
            out.append(f"<{tag}>{inline(txt)}</{tag}>")
            i += 1
        elif ln.lstrip().startswith(("- ", "* ")) or re.match(r"^\s*\d+\.\s", ln):
            ordered = bool(re.match(r"^\s*\d+\.\s", ln))
            tag = "ol" if ordered else "ul"
            items = []
            while i < len(lines) and (lines[i].lstrip().startswith(("- ", "* "))
                                      or re.match(r"^\s*\d+\.\s", lines[i])):
                items.append(re.sub(r"^\s*(?:[-*]\s|\d+\.\s)", "", lines[i]))
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items)
                       + f"</{tag}>")
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
            cells = [c for c in cells if not all(set(x) <= set("-: ") for x in c)]
            if not cells:
                continue
            head, body = cells[0], cells[1:]
            t = ["<div class='tw'><table><thead><tr>"]
            t += [f"<th>{inline(c)}</th>" for c in head]
            t.append("</tr></thead><tbody>")
            for r in body:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table></div>")
            out.append("".join(t))
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not lines[i].startswith(
                    ("|", "#", "---")) and not lines[i].lstrip().startswith(("- ", "* ")) \
                    and not re.match(r"^\s*\d+\.\s", lines[i]):
                para.append(lines[i].strip())
                i += 1
            out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out)


def data_uri(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


CSS = """
:root{
  --ground:#fbfbfa; --panel:#ffffff; --sunk:#f3f4f2;
  --ink:#15181c; --ink-2:#4b5158; --ink-3:#7b828a;
  --line:#e2e4e1; --line-2:#cfd2ce;
  --accent:#c4551f;            /* orange kanal — çalışmanın öznesi */
  --ch-bf:#6a7078; --ch-green:#1b8a4b; --ch-orange:#c4551f; --ch-nir:#8a3a63;
  --good:#1b8a4b; --warn:#a8730b; --stop:#b3392f;
  --serif:"Iowan Old Style","Charter","Bitstream Charter","Sitka Text",Cambria,Georgia,serif;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#101317; --panel:#171b20; --sunk:#1c2126;
    --ink:#e9ebee; --ink-2:#b0b7bf; --ink-3:#828a93;
    --line:#272d34; --line-2:#39414a;
    --accent:#e07b45;
    --ch-bf:#98a1ab; --ch-green:#3fb571; --ch-orange:#e07b45; --ch-nir:#d4749f;
    --good:#3fb571; --warn:#d3a03a; --stop:#e0736a;
  }
}
:root[data-theme="dark"]{
  --ground:#101317; --panel:#171b20; --sunk:#1c2126;
  --ink:#e9ebee; --ink-2:#b0b7bf; --ink-3:#828a93;
  --line:#272d34; --line-2:#39414a;
  --accent:#e07b45;
  --ch-bf:#98a1ab; --ch-green:#3fb571; --ch-orange:#e07b45; --ch-nir:#d4749f;
  --good:#3fb571; --warn:#d3a03a; --stop:#e0736a;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--sans); font-size:16px; line-height:1.62;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1120px;margin:0 auto;padding:0 24px 96px}
.measure{max-width:70ch}

/* ---- başlık ---- */
header.top{border-bottom:1px solid var(--line);margin-bottom:40px;padding:56px 0 32px}
.eyebrow{font-family:var(--mono);font-size:11.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--ink-3);margin:0 0 14px}
h1{font-family:var(--serif);font-weight:600;font-size:clamp(30px,4.2vw,46px);
  line-height:1.14;letter-spacing:-.012em;margin:0 0 16px;text-wrap:balance}
.lede{font-size:17.5px;color:var(--ink-2);margin:0;max-width:68ch}
.facts{display:flex;flex-wrap:wrap;gap:0;margin-top:32px;
  border:1px solid var(--line);border-radius:3px;overflow:hidden}
.fact{flex:1 1 150px;padding:13px 16px;border-right:1px solid var(--line);background:var(--panel)}
.fact:last-child{border-right:0}
.fact b{display:block;font-family:var(--mono);font-size:19px;font-variant-numeric:tabular-nums;
  color:var(--ink);letter-spacing:-.01em}
.fact span{font-size:12px;color:var(--ink-3)}

/* ---- gezinme ---- */
nav.toc{position:sticky;top:0;z-index:5;background:var(--ground);
  border-bottom:1px solid var(--line);margin-bottom:8px}
nav.toc ol{list-style:none;display:flex;flex-wrap:wrap;gap:2px;margin:0;padding:9px 0}
nav.toc a{font-family:var(--mono);font-size:12px;text-decoration:none;color:var(--ink-2);
  padding:5px 9px;border-radius:3px;display:block}
nav.toc a:hover{background:var(--sunk);color:var(--ink)}
nav.toc a:focus-visible{outline:2px solid var(--accent);outline-offset:1px}

/* ---- bölüm ---- */
section.an{padding-top:52px;scroll-margin-top:56px}
.an-head{display:flex;gap:16px;align-items:baseline;border-top:2px solid var(--rule,var(--line-2));
  padding-top:14px}
.an-num{font-family:var(--mono);font-size:12.5px;letter-spacing:.1em;color:var(--rule,var(--ink-3));
  flex:0 0 auto;padding-top:5px}
h2{font-family:var(--serif);font-weight:600;font-size:27px;line-height:1.2;margin:0;
  letter-spacing:-.008em}
.an-q{font-size:14px;color:var(--ink-3);margin:3px 0 0}

.verdict{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--rule,var(--accent));
  border-radius:3px;padding:16px 20px;margin:22px 0 8px;max-width:78ch}
.verdict .k{font-family:var(--mono);font-size:10.5px;letter-spacing:.13em;text-transform:uppercase;
  color:var(--ink-3);display:block;margin-bottom:6px}
.verdict p{margin:0;font-size:16.5px}
.cantsay{margin:12px 0 0;padding:12px 20px;background:var(--sunk);border-radius:3px;
  max-width:78ch;font-size:14.5px;color:var(--ink-2)}
.cantsay .k{font-family:var(--mono);font-size:10.5px;letter-spacing:.13em;text-transform:uppercase;
  color:var(--stop);display:block;margin-bottom:4px}

/* ---- gövde ---- */
.body h3{font-family:var(--serif);font-weight:600;font-size:19.5px;margin:38px 0 10px;
  letter-spacing:-.005em}
.body h4{font-size:15px;margin:26px 0 8px}
.body p,.body ul,.body ol{max-width:70ch}
.body p{margin:0 0 14px}
.body ul,.body ol{margin:0 0 16px;padding-left:22px}
.body li{margin-bottom:6px}
.body hr{display:none}
.body h2{display:none}      /* dosya başlığı bölüm başlığıyla çakışıyor */
code{font-family:var(--mono);font-size:.88em;background:var(--sunk);
  padding:1px 5px;border-radius:3px;color:var(--ink-2)}
strong{font-weight:650;color:var(--ink)}

/* ---- tablo ---- */
.tw{overflow-x:auto;margin:0 0 20px;border:1px solid var(--line);border-radius:3px;
  background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:13.5px;
  font-variant-numeric:tabular-nums}
th,td{padding:8px 13px;text-align:left;border-bottom:1px solid var(--line);
  white-space:nowrap}
th{font-family:var(--mono);font-size:11px;letter-spacing:.05em;text-transform:uppercase;
  color:var(--ink-3);font-weight:500;background:var(--sunk)}
tbody tr:last-child td{border-bottom:0}
td:first-child{color:var(--ink)}
td{color:var(--ink-2)}

/* ---- figür ---- */
figure{margin:26px 0 30px}
figure img{width:100%;height:auto;display:block;border:1px solid var(--line);
  border-radius:3px;background:#fbfbfa}
figcaption{font-family:var(--mono);font-size:11.5px;color:var(--ink-3);
  margin-top:8px;line-height:1.5;max-width:80ch}

/* ---- kanal rozetleri ---- */
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:26px 0 0;padding:0;list-style:none}
.chip{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);font-size:11.5px;
  border:1px solid var(--line);border-radius:99px;padding:4px 11px 4px 8px;color:var(--ink-2);
  background:var(--panel)}
.dot{width:8px;height:8px;border-radius:50%;flex:0 0 auto}

/* ---- alt ---- */
footer{margin-top:72px;padding-top:22px;border-top:1px solid var(--line);
  font-size:13.5px;color:var(--ink-3)}
footer p{max-width:76ch}
footer code{font-size:12.5px}
@media (max-width:640px){
  .an-head{flex-direction:column;gap:4px}
  th,td{white-space:normal}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""


def build() -> str:
    parts: list[str] = []
    parts.append("<title>T hücresi infiltrasyonu — nicel analiz</title>")
    parts.append(f"<style>{CSS}</style>")
    parts.append("<div class='wrap'>")

    parts.append("""
<header class="top">
  <p class="eyebrow">PDA 30364 · 96 kuyu · 13 zaman noktası · 4 gün</p>
  <h1>T hücresi organoide giriyor mu?</h1>
  <p class="lede">Incucyte zaman serisinin piksel tabanlı niceliği. Altı ayrı soru,
  altı ayrı analiz: her biri ne ölçüldüğünü, ne çıktığını ve bu veriyle neyin
  <em>söylenemeyeceğini</em> ayrı ayrı yazıyor.</p>
  <div class="facts">
    <div class="fact"><b>88</b><span>görüntülenen kuyu</span></div>
    <div class="fact"><b>1144</b><span>kuyu × zaman ölçümü</span></div>
    <div class="fact"><b>59 488</b><span>tif dosyası</span></div>
    <div class="fact"><b>4</b><span>dışlanan kuyu</span></div>
    <div class="fact"><b>0,79</b><span>T zenginleşmesi (rastgele = 1,0)</span></div>
  </div>
  <ul class="chips">
    <li class="chip"><span class="dot" style="background:var(--ch-bf)"></span>brightfield — organoid maskesi</li>
    <li class="chip"><span class="dot" style="background:var(--ch-green)"></span>green — tümör (PDA)</li>
    <li class="chip"><span class="dot" style="background:var(--ch-orange)"></span>orange — T hücresi</li>
    <li class="chip"><span class="dot" style="background:var(--ch-nir)"></span>NIR — ölü hücre</li>
  </ul>
</header>""")

    parts.append("<nav class='toc'><ol>")
    for slug, num, title, _, _ in SECTIONS:
        parts.append(f"<li><a href='#{slug}'>{num} · {html.escape(title)}</a></li>")
    parts.append("</ol></nav>")

    for slug, num, title, question, ch in SECTIONS:
        d = OUT / slug
        smd = d / "summary.md"
        if not smd.is_file():
            continue
        rule = {"bf": "var(--ch-bf)", "green": "var(--ch-green)",
                "orange": "var(--ch-orange)", "nir": "var(--ch-nir)"}[ch]
        parts.append(f"<section class='an' id='{slug}' style='--rule:{rule}'>")
        parts.append(f"<div class='an-head'><div class='an-num'>{num}</div><div>"
                     f"<h2>{html.escape(title)}</h2>"
                     f"<p class='an-q'>{html.escape(question)}</p></div></div>")
        ans, cant = VERDICT.get(slug, ("", ""))
        if ans:
            parts.append(f"<div class='verdict'><span class='k'>Sonuç</span>"
                         f"<p>{ans}</p></div>")
        if cant:
            parts.append(f"<div class='cantsay'><span class='k'>Bu veriyle "
                         f"yanıtlanamaz</span>{cant}</div>")

        text = smd.read_text()
        body = md(text)
        # figürleri gövdenin sonuna, sırasıyla
        figs = []
        for name in FIG_ORDER.get(slug, []):
            p = d / name
            if p.is_file():
                cap = FIG_CAPTION.get(name, "")
                figs.append(f"<figure><img alt='{html.escape(cap)}' "
                            f"src='{data_uri(p)}'>"
                            f"<figcaption>{html.escape(cap)}</figcaption></figure>")
        parts.append(f"<div class='body'>{body}</div>")
        parts.append("".join(figs))
        parts.append("</section>")

    parts.append("""
<footer>
  <p><strong>Nasıl üretildi.</strong> <code>analysis/extract.py</code> her kuyu-zaman
  noktası için brightfield organoid maskesi ve üç floresan kanalın eşik üstü
  alanlarını çıkarır (1144 örnek, 424 ölçüm); <code>analysis/a1…a6</code> bu tablodan
  altı ayrı analizi üretir. Her bölümün ham CSV'leri ve figürleri
  <code>analysis/out/&lt;bölüm&gt;/</code> altında; yöntem ve sınırlar
  <code>analysis/README.md</code>'de.</p>
  <p><strong>Ölçek.</strong> Tif üstverisinde kalibrasyon yok (XResolution = tam 72 dpi
  yer tutucu; plaka XML'inde optik bilgi yok). Kullanılan 2,798 µm/px değeri cihaz
  arayüzünün alan etiketinden geri hesaplandı ve <em>doğrulanmadı</em>. Oranlar,
  AUC'ler, korelasyonlar ve alan payları bu değerden bağımsızdır; yalnızca µm/µm²
  etiketleri doğrusal ölçeklenir. <strong>z adımı bilinmiyor</strong> — derinlik
  yalnızca katman indeksi olarak verildi, µm ya da µm³ hiç üretilmedi.</p>
  <p><strong>İstatistik.</strong> Koşul başına 2–17 kuyu. Parametrik test
  kullanılmadı: etki büyüklüğü Mann-Whitney AUC ve Cliff δ, p-değeri Mann-Whitney U,
  çoklu karşılaştırma Benjamini-Hochberg (<code>q</code>). Güven aralıkları önyükleme
  ile (2000 tekrar).</p>
</footer>""")
    parts.append("</div>")
    return "\n".join(parts)


if __name__ == "__main__":
    dst = OUT / "rapor.html"
    dst.write_text(build())
    print(f"→ {dst}  ({dst.stat().st_size/1e6:.1f} MB)")
