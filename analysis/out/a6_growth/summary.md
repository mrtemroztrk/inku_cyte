# A6 — Büyüme, morfoloji ve ilaç yanıtı

## 1. Organoidler büyüdü mü?

BF teritorya oranı 4 günde medyan **1.47×** arttı (%24.6 → %36.1). Kuyu başına log-doğrusal büyüme hızı medyan **1.15×/gün** (63 kuyu, çeyrekler 1.02–1.31).

Green alan oranı aynı sürede 1.98× değişti (1.22×/gün). İki ölçünün ayrışması beklenir: BF tüm hücresel maddeyi görür, green yalnız boyanmış tümörü (bkz. A1).

| ko-kültür | n kuyu | büyüme (×/gün) | PDA'ya karşı δ | q |
|---|---|---|---|---|
| PDA | 16 | 1.31 | +0.00 | 1.000 |
| PDA+CAF | 16 | 1.10 | -0.73 | 0.001 |
| PDA+MAC | 15 | 1.22 | -0.42 | 0.067 |
| PDA+CAF+MAC | 16 | 0.89 | -0.96 | 0.000 |

## 2. Dağınık mı, tek sferoid mi?

En büyük nesnenin toplam BF maddesindeki payı 4. günde medyan **0.86** (t0'da 0.36); doluluk 0.77.

34/63 kuyu tek bir baskın kütleye toplanmış (pay > 0,8), 19 kuyu dağınık kalmış (< 0,4). Bu ayrım A2'deki dışlanma bulgusunun temeli: T hücresi zenginleşmesi toplanma derecesiyle ters gidiyor.

T eklenen kuyularda toplanma ile T zenginleşmesi arasındaki sıra korelasyonu **-0.63**, doluluk ile **+0.14** (27 kuyu). Toplandıkça T hücresi dışlanıyor.

## 3. Organoid boyut dağılımı

t0'da ölçülen 2730 organoidin medyan eşdeğer çapı **35 px** (97 µm), 4. günde 2160 organoid için **38 px** (106 µm). Üst uç (p95) 142 → 193 px (396 → 539 µm).

Sayının düşmesi ve çapın büyümesi birlikte okunmalı: ayrı organoidler birleşerek daha az ama daha büyük nesne bırakıyor.

## 4. Bileşikler büyümeyi durdurdu mu?

| bileşik | n kuyu | büyüme (×/gün) | kontrole karşı δ | q |
|---|---|---|---|---|
| control | 17 | 1.31 | +0.00 | — |
| kras low | 12 | 1.06 | -0.51 | 0.083 |
| kras high | 3 | 0.99 | -0.65 | 0.139 |
| Src low | 8 | 1.10 | -0.54 | 0.083 |
| Src high | 4 | 1.18 | -0.29 | 0.410 |
| low kras+Src | 15 | 1.13 | -0.43 | 0.083 |
| high kras+Src | 4 | 1.11 | -0.53 | 0.144 |

Hiçbir bileşik kontrolden anlamlı ayrılmıyor (en düşük q = 0.08). Bileşik başına 3–17 kuyu var; bu güçle ancak büyük etkiler görünür.

Doz karşılaştırması (doz-yanıt beklenir):

- **KRAS**: düşük doz 1.06×/gün (12 kuyu), yüksek doz 0.99×/gün (3 kuyu)
- **Src**: düşük doz 1.10×/gün (8 kuyu), yüksek doz 1.18×/gün (4 kuyu)
- **KRAS+Src**: düşük doz 1.13×/gün (15 kuyu), yüksek doz 1.11×/gün (4 kuyu)

---

### Birimler ve ölçek

Ölçek: **2.798 µm/px**. Tif üstverisinde kalibrasyon yok (XResolution = tam 72 dpi yer tutucu, plaka XML'inde optik bilgi yok); kullanılan değerin kaynağı cihaz arayüzünün alan etiketi 2,91 × 3,94 mm ÷ 1040 × 1408 px ve **doğrulanmadı**. Piksel cinsinden verilen her sayı bu varsayımdan bağımsızdır; µm/µm²/mm² etiketleri kalibrasyonla doğrusal ölçeklenir ve hiçbir oran, AUC ya da korelasyonu etkilemez. Farklı bir değer için `INC_UM_PER_PX=...`. **z adımı bilinmiyor**; derinlik yalnızca katman indeksi olarak verildi.
