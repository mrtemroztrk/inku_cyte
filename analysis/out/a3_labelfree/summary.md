# A3 — Boyasız ayrım: T hücresi ve makrofaj

## 1. Önce şu: makrofajlar orange kanalına sızıyor mu?

T hücresi eklenmeyen 36 kuyuda, makrofajlı olanların orange alan oranı medyan %0.20 (18 kuyu), makrofajsızların %0.69 (18 kuyu) — AUC 0.07, p = 1e-05.

**Makrofajlı kuyularda orange sinyali sistematik olarak düşük.** Bu, orange tabanlı T hücresi niceliğinin makrofaj varlığıyla karıştığı anlamına gelir: T hücresi karşılaştırmaları makrofaj durumu sabit tutularak yapılmalı.

| kanal | öznitelik | AUC (MAC+ vs MAC−) | q |
|---|---|---|---|
| orange | `orange_area_frac` | 0.07 | 0.000 |
| orange | `orange_int_mean` | 0.23 | 0.010 |
| orange | `orange_obj_med_px` | 0.29 | 0.049 |
| green | `green_area_frac` | 0.60 | 0.359 |
| green | `green_int_mean` | 0.39 | 0.336 |
| green | `green_obj_med_px` | 0.47 | 0.739 |
| nir | `nir_area_frac` | 0.14 | 0.001 |
| nir | `nir_int_mean` | 0.07 | 0.000 |
| nir | `nir_obj_med_px` | 0.21 | 0.006 |

Makrofajlı kuyular plakanın 3., 4., 7. ve 8. kolonlarında — bu tek başına bir konum yan etkisi olabilirdi. Plakanın iki yarısı bağımsız birer tekrar sağlıyor (her yarıda makrofajlı ve makrofajsız kolonlar yan yana); etki ikisinde de aynı yönde çıkarsa konum açıklaması düşer:

| yarı | kanal | MAC+ | MAC− | AUC | p |
|---|---|---|---|---|---|
| sol yarı (kolon 1–4) | orange | %0.22 (6 kuyu) | %0.76 (8 kuyu) | 0.00 | 0.001 |
| sol yarı (kolon 1–4) | nir | %0.01 (6 kuyu) | %0.24 (8 kuyu) | 0.19 | 0.059 |
| sağ yarı (kolon 5–8) | orange | %0.20 (12 kuyu) | %0.61 (10 kuyu) | 0.10 | 0.002 |
| sağ yarı (kolon 5–8) | nir | %0.05 (12 kuyu) | %0.18 (10 kuyu) | 0.15 | 0.006 |

**Etki iki yarıda da aynı yönde ve aynı büyüklükte** — plaka konumu açıklaması düşüyor. Geriye biyolojik bir mekanizma kalıyor: makrofajlar fagositik hücrelerdir; döküntüyü ve ölü hücreleri temizlemeleri hem otofloresan orange arkaplanını hem de ölü hücre boyasını (NIR) azaltır. Bu yorum bu veriyle **doğrudan kanıtlanamaz** ama iki kanalın birlikte düşmesi onunla tutarlı.

## 2. Kuyu düzeyi: yalnız brightfield'dan makrofaj/T hücresi var mı?

Kuyu-dışarıda-bırak çapraz doğrulamalı lojistik regresyon, 4. gün. AUC 0,5 = şans, 1,0 = kusursuz.

| hedef | n (+/−) | yalnız BF | BF + floresan | en iyi tek öznitelik |
|---|---|---|---|---|
| makrofaj var mı | 18/18 | **0.74** | 0.90 | `orange_area_frac` (0.07) |
| T hücresi var mı | 14/18 | **0.88** | 1.00 | `orange_area_frac` (1.00) |
| CAF var mı | 9/9 | **1.00** | 1.00 | `bf_terr_frac` (1.00) |

**Sonuç: brightfield tek başına makrofaj varlığını zayıf ayırt ediyor (AUC 0.74), T hücresi varlığını ayırt edebiliyor (AUC 0.88).**

Bu *kuyu* düzeyinde bir cevap: 8000 makrofajın kuyuya toplu etkisi brightfield'da görülüyor mu diye soruyor. Tek bir hücreye bakıp türünü söylemek bundan çok daha zor bir problem ve bu veride **doğrulanamaz** — makrofajın floresan etiketi olmadığı için hiçbir hücre için doğru cevap bilinmiyor. Piksel düzeyinde ayrım iddiası ancak makrofajlara ayrı bir işaretleyici konan bir deneyle sınanabilir.

## 3. Piksel düzeyinde ayrımın üst sınırı

Makrofaj ve T hücresi eklemek BF ölçümlerini **aynı yöne mi** kaydırıyor? Aynı yöne kaydırıyorsa ikisi birbirinden ayrılamaz demektir.

| BF ölçümü | AUC (MAC etkisi) | AUC (T etkisi) | fark |
|---|---|---|---|
| `bf_fine_med_px` | 0.48 | 0.79 | 0.31 |
| `bf_depth_mean` | 0.76 | 0.58 | 0.18 |
| `bf_particle_med_px` | 0.24 | 0.33 | 0.09 |
| `bf_particles` | 0.54 | 0.59 | 0.05 |

En büyük fark 0.31; bunlar 36 ve 32 kuyuya dayanan gürültülü kuyu düzeyi istatistikleri, aralarındaki bu büyüklükte bir fark tek başına güçlü kanıt değil.

**Asıl belirleyici olan çözünürlük.** 2,798 µm/px'te bir T hücresi (~7 µm çap) yaklaşık **2,5 piksel**, bir makrofaj (~15 µm) yaklaşık 5 piksel eder. Morfolojiye dayalı hücre tipi ayrımı — şekil, çekirdek yapısı, yayılma — bu ölçekte ölçülemez. Bu veriyle piksel düzeyinde T hücresi/makrofaj ayrımı **yapılamaz**; kuyu düzeyindeki toplu etki (2. bölüm) ölçülebilen tek şey.

Bunu değiştirecek olan analiz değil, edinim: makrofaja özgü bir işaretleyici (ayrı bir floresan kanal), ya da tek hücre morfolojisini çözecek daha yüksek büyütme.

## 4. Makrofaj infiltrasyonu — dolaylı ölçüm

Makrofajın işaretleyicisi olmadığı için "organoide kaç makrofaj girdi" doğrudan ölçülemez. Ölçülebilen şey, **yalnızca makrofaj varlığıyla ayrılan eşleşmiş kuyular arasında organoidin nasıl değiştiği**: makrofajlar organoide girip yerleşiyorsa organoid büyümeli, içindeki tümör (green) payı seyrelmeli, doluluk artmalı.

| eşleşme | n organoid MAC+/MAC− | çap MAC+/MAC− | AUC | green-pozitif MAC+/MAC− | AUC | doluluk MAC+/MAC− | AUC |
|---|---|---|---|---|---|---|---|
| CAF− / T− | 240/484 | 121 / 102 µm | 0.57 | %36 / %10 | 0.65 | 0.89 / 0.91 | 0.48 |
| CAF− / T+ | 115/440 | 110 / 124 µm | 0.49 | %28 / %26 | 0.49 | 0.79 / 0.84 | 0.46 |
| CAF+ / T− | 256/235 | 97 / 103 µm | 0.48 | %19 / %24 | 0.48 | 0.75 / 0.83 | 0.42 |
| CAF+ / T+ | 201/189 | 89 / 109 µm | 0.42 | %7 / %10 | 0.50 | 0.86 / 0.86 | 0.51 |

Eşleşmeler tutarlı bir yön göstermiyor (AUC'ler 0.48–0.65); makrofaj varlığının organoid içi bileşime etkisi bu ölçümlerle saptanamıyor.

Her hâlükârda bu **dolaylı** bir çıkarım: aynı fark boyanma verimindeki bir değişiklikten de doğabilir (bkz. A1) ve organoid içinde makrofaj olup olmadığını göstermez. "Organoide kaç makrofaj girdi" sorusunun ölçülebilir cevabı **makrofaja özgü bir işaretleyici gerektirir** — mevcut dört kanalla üretilemez.

---

### Birimler ve ölçek

Ölçek: **2.798 µm/px**. Tif üstverisinde kalibrasyon yok (XResolution = tam 72 dpi yer tutucu, plaka XML'inde optik bilgi yok); kullanılan değerin kaynağı cihaz arayüzünün alan etiketi 2,91 × 3,94 mm ÷ 1040 × 1408 px ve **doğrulanmadı**. Piksel cinsinden verilen her sayı bu varsayımdan bağımsızdır; µm/µm²/mm² etiketleri kalibrasyonla doğrusal ölçeklenir ve hiçbir oran, AUC ya da korelasyonu etkilemez. Farklı bir değer için `INC_UM_PER_PX=...`. **z adımı bilinmiyor**; derinlik yalnızca katman indeksi olarak verildi.
