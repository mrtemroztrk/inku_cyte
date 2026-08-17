# analysis/ — nicel analiz hattı

`data/inc_tests` (88 kuyu × 13 zaman × 4 kanal) için piksel tabanlı ölçüm ve altı
ayrı analiz. Her analiz kendi sorusunu yanıtlar, kendi klasörüne yazar ve tek
başına okunabilir — `viewer/`'dan bağımsızdır.

## Çalıştırma

```bash
python3 analysis/scale.py                      # ölçek denetimi (birimler nereden geliyor)
python3 analysis/extract.py --flat             # bir kez: aydınlatma referansı
python3 analysis/extract.py --check            # 8 kuyuya hızlı bakış
python3 analysis/extract.py --all --jobs 7     # tüm plaka, ~18 dk

python3 analysis/a1_qc.py                      # önce bu: dışlama listesini üretir
python3 analysis/a2_infiltration.py
python3 analysis/a3_labelfree.py
python3 analysis/a4_depth.py
python3 analysis/a5_death.py
python3 analysis/a6_growth.py
```

`a1` dışındakiler `a1`'in yazdığı `out/a1_qc/excluded_wells.csv`'yi okur, o yüzden
sırayla çalıştırılmalı. Bağımlılıklar: numpy, scipy, scikit-image, pandas,
tifffile, matplotlib.

## Neden piksel, neden nesne değil

2,798 µm/px'te bir T hücresi ~2,5 piksel. Tek hücre segmentasyonu bu ölçekte
güvenilir değil; eşik biraz kaydırılınca nesne sayısı katlanarak değişiyor. Alan
oranları çok daha kararlı: eşik ×0,67 ve ×1,67 kaydırıldığında kuyu sıralamasının
sıra korelasyonu 0,93–0,98 arasında kalıyor (A1 §3). Bu yüzden bütün ana ölçüler
**eşik üstü piksel/voksel alanı** ve bunlardan türeyen oranlar. Nesne sayıları
çıkarılıyor ama ikincil.

## Organoid maskesi brightfield'dan

Green kanalı organoidlerin hepsini boyamıyor — BF'de net görünen organoidlerin
büyük kısmının green karşılığı yok (A1 §2, PDA-tek kuyularda bile). Dolayısıyla
"organoid nerede" sorusu BF'den, "ne kadarı boyanmış" sorusu green'den yanıtlanır.
BF ile floresan z-yığınları hizalı (faz korelasyonu kayması ≤ 1 px, 4 kuyuda
ölçüldü), yani BF maskesi floresan kanallara doğrudan uygulanabiliyor.

İki maske üretiliyor:

| maske | tanım | kullanım |
|---|---|---|
| `fine` | düzleştirilmiş BF'de zeminden ≥ 8 gri seviye koyu, açma + küçük nesne atma | doluluk ölçüsü |
| `terr` | `fine`'ın 31 px kapaması + delik doldurma | organoid **teritoryası**: içeride/dışarıda, uzaklık bantları, organoid başına tablo |

Eşik **plaka geneli sabit**, kuyuya uyarlanmıyor — uyarlanan eşik her kuyuyu
farklı ölçekler ve kuyular karşılaştırılamaz hâle gelir. Zemin, yumuşatılmış
görüntünün histogram tepesi (ham histogramda gürültülü zemin yayılıp tepe koyu bir
sferoide kayabiliyor). Vinyet, plaka genelinde t0'da hesaplanan aydınlatma
referansıyla düzeltiliyor (`bf_flat.npy`; ~4,6 gri seviye, eşiğin yarısı kadar).

**Sınır:** bu maske "hücresel madde" ile "tümör organoidi" arasında ayrım yapmaz.
CAF/makrofaj kümeleri, döküntü ve ölü madde de BF'de koyu görünür. "Organoid"
sayıları bu yüzden üst sınırdır.

## Birimler

Ayrıntı ve denetim: `analysis/scale.py` (`python3 analysis/scale.py`).

| büyüklük | birim | varsayıma dayanıyor mu |
|---|---|---|
| alan oranı, zenginleşme, AUC, korelasyon, katman payı | boyutsuz | **hayır** |
| alan, çap (px) | piksel | **hayır** |
| alan, çap (µm, µm², mm²) | µm türevi | evet — 2,798 µm/px, doğrulanmadı |
| derinlik | z katman indeksi | z adımı bilinmiyor, µm verilmiyor |
| floresan yoğunluğu | keyfi birim (a.u.) | kanallar arası karşılaştırılamaz |

Tif üstverisinde kalibrasyon **yok** (XResolution tam 72 dpi yer tutucu; plaka
XML'inde optik bilgi yok; cihaz kompozitinde gömülü ölçek çubuğu yok). Kullanılan
2,798 µm/px değeri cihaz arayüzünün alan etiketinden geri hesaplandı ve
doğrulanmadı. Gerçek değer biliniyorsa `INC_UM_PER_PX=... python3 analysis/aN_*.py`
— yeniden çıkarım gerekmez, µm kolonları piksel ölçümlerinden yeniden ölçeklenir.

## Analizler

| betik | soru | ana çıktı |
|---|---|---|
| `a1_qc.py` | Hangi kuyular yorumlanabilir? Green organoidlerin kaçını boyuyor? | `excluded_wells.csv`, boyama kapsamı |
| `a2_infiltration.py` | T hücresi organoide ne kadar giriyor? | zenginleşme, işaretli uzaklık profili, organoid başına yük |
| `a3_labelfree.py` | Boyasız T hücresi/makrofaj ayrımı mümkün mü? | çapraz doğrulanmış AUC, makrofaj kanal etkisi |
| `a4_depth.py` | T hücresi derinlikte nerede? | hizalanmış z profilleri, göreli kayma |
| `a5_death.py` | Kim öldü, neden? | ölüm atfı, ölüm indeksi, eşleşmiş etkiler |
| `a6_growth.py` | Organoid nasıl büyüdü, ilaçlar ne yaptı? | büyüme hızı, toplanma, doz karşılaştırması |

Her klasörde `summary.md` (bulgular + sınırlar), figürler ve ham CSV'ler var.

## İstatistik

Kuyu sayıları küçük (koşul başına 2–17), o yüzden:

- **Kutu grafiği yok** — her kuyu nokta olarak çizilir, medyan çizgiyle gösterilir.
- **Parametrik test yok** — Mann-Whitney AUC ve Cliff δ etki büyüklüğü olarak,
  Mann-Whitney U p-değeri olarak; medyan güven aralıkları önyükleme (2000 tekrar).
- **Çoklu karşılaştırma** Benjamini-Hochberg ile düzeltilir (`q` kolonu).
- **Eşleşmiş karşılaştırma** tercih edilir: ko-kültür hem ölümü hem T dağılımını
  bağımsız olarak etkilediği için sabit tutulur.
- Bir yön tutarlı ama tek tek anlamlı değilse **işaret testi** raporlanır.

Özetlerdeki yorum cümleleri ölçülen etki büyüklüğüne bağlı olarak üretilir; veri
değişirse cümle de değişir, elle yazılmış sonuç yoktur.

## Çıkarılan ölçümler

`viewer/cache/features/` altında:

- `features.csv` — kuyu × zaman başına 424 kolon (1144 satır)
- `organoids.csv` — organoid başına satır (≥300 px teritorya bileşeni)
- `{well}_t{nn}.json` — örnek başına ham kayıt (z profilleri, bantlar dahil)
- `bf_flat.npy` — aydınlatma referansı

Başlıca kolon aileleri:

| önek | ne |
|---|---|
| `bf_terr_frac`, `bf_fine_frac`, `bf_solidity`, `bf_largest_frac` | BF kütlesi, doluluk, toplanma |
| `bf_particles`, `bf_particle_*` | tek hücre boyutlu koyu nesneler (etiketsiz) |
| `{ch}_area_frac`, `_int_*`, `_p99` | kanal başına alan ve yoğunluk |
| `{ch}_area_frac_lo/_hi` | eşik ×0,67 / ×1,67 — duyarlılık kontrolü |
| `{ch}_area_by_z_*`, `_area_by_z_in_*`, `_mean_z`, `_z_conc3` | derinlik |
| `{ch}_frac_in_organoid`, `_enrich_organoid` | teritorya içi/dışı |
| `{ch}_band_px_*`, `band_area_px_*`, `{ch}_band_enrich_*` | işaretli uzaklık profili |
| `nir_on_green/orange/both/neither_frac` | ölüm atfı |
| `death_index_tumour`, `death_index_tcell` | kütleye bölünmüş ölüm |
| `green_pos_organoid_frac_*` | green-pozitif organoid oranı |

## Bu hattın yanıtlayamadığı sorular

- **Organoide kaç makrofaj girdi.** Makrofajın floresan işaretleyicisi yok;
  görüntüde tümörden ayırt edilemiyor. A3 dolaylı ölçüm sunuyor ama bu bir cevap
  değil, bir üst sınır.
- **Tek hücre düzeyinde T hücresi/makrofaj ayrımı.** Doğrulama etiketi yok ve
  çözünürlük (~2,5 px/T hücresi) morfolojik ayrıma yetmiyor.
- **Mutlak derinlik.** z adımı ve tarama yönü kayıtlı değil.
- **Mutlak hücre sayısı.** Alan oranları hücre sayısına çevrilemiyor.
