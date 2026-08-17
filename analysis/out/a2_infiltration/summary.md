# A2 — T hücresi infiltrasyonu

## 1. Önce kontrol: orange gerçekten T hücresini mi ölçüyor?

Son zaman noktasında T eklenen 27 kuyuda orange alan oranı medyan **%1.71**, eklenmeyen 57 kuyuda **%0.63** — 2.7× fark (AUC 0.92, p = 8.8e-10).

Fark yönü doğru ama **ayrım tam değil**: T eklenmeyen kuyularda da belirgin orange sinyali var. Yani `orange_area_frac` mutlak bir T hücresi ölçüsü değil; kuyu içi konum ölçümleri (zenginleşme, uzaklık profili) bu arkaplandan etkilenmez çünkü aynı kuyunun içinde oran alıyorlar, ama **mutlak miktar karşılaştırmaları eşleşmiş T'siz kuyulara göre fazlalık olarak okunmalı.**

t0'da (ekimden hemen sonra) ayrım daha keskin: %5.15 vs %1.47 (3.5×, AUC 1.00). Zamanla farkın kapanması ya T hücrelerinin kaybolduğunu ya da arkaplanın büyüdüğünü gösterir — A5 (ölüm) buna bakıyor.

## 2. Ana sayı: organoid içi zenginleşme

T eklenen kuyularda 4. günde zenginleşme medyanı **0.79** (%95 GA 0.56–1.05); T'siz kuyularda 1.10.

**Bu, rastgele dağılımdan ayırt edilemez.** Güven aralığı 1,0'ı içeriyor ve 17/27 kuyu 1'in altında. Yani plaka genelinde tek bir sayıya indirgendiğinde ne toplu bir infiltrasyon ne de toplu bir dışlanma var — kuyular arasındaki *değişkenlik* asıl sinyal, ve o değişkenliğin neye bağlı olduğu 4. bölümde çıkıyor.

| ko-kültür | n (T+) | zenginleşme T+ | n (T−) | zenginleşme T− | Cliff δ | q |
|---|---|---|---|---|---|---|
| PDA | 7 | 1.01 | 9 | 1.16 | -0.49 | 0.448 |
| PDA+CAF | 7 | 0.67 | 15 | 1.16 | -0.33 | 0.474 |
| PDA+MAC | 6 | 0.66 | 15 | 0.89 | -0.02 | 0.970 |
| PDA+CAF+MAC | 7 | 0.73 | 17 | 1.08 | -0.18 | 0.712 |

Tek tek hiçbiri anlamlı değil ama **dört ko-kültürün dördünde de işaret aynı**: T eklenen kuyularda zenginleşme, T'siz eşdeğerinden düşük (işaret testi p = 0.12). Tutarlı bir eğilim var, tek tek kuyularla doğrulanacak güç yok.

## 3. Uzaklık profili — dışlanma nerede başlıyor

Profilin tepesi **0…20 µm** (0…7 px) bandında — yani T hücreleri organoid sınırının hemen dışında yığılıyor. Derin iç bantta (<-150 µm) yoğunluk kuyu ortalamasının 0.62× katı, sınır bandında (0…20 µm) 1.28×.

Bant kenarları piksel cinsinden sabittir; µm etiketleri geçerli kalibrasyondan türetilmiştir (aşağıdaki ölçek notu). Profilin **şekli ve tepe bandı kalibrasyondan bağımsızdır** — kalibrasyon yalnızca eksen etiketlerini ölçekler.

T eklenmeyen kuyuların profili karşılaştırma için çizildi: aynı şekli göstermesi profilin bir kısmının **organoid geometrisinden** geldiğini söyler (döküntü de organoidin çevresinde birikir), farkı ise T hücresine atfedilebilir kısımdır.

## 4. Organoid başına: hangi organoide ne kadar giriyor

Son zaman noktasında T eklenen kuyularda ölçülen 945 organoid (≥300 px ≈ 20 px eşdeğer çap = 55 µm). Organoid alanının orange ile kaplı oranı medyan **%0.40**; çeyrekler %0.00–%2.63.

Organoid çapı ile orange kapsaması arasındaki sıra korelasyonu **+0.34** — büyük organoidler daha çok T hücresi barındırıyor.

Doluluğu en düşük beşte birdeki (≤0.67, gevşek) organoidlerde orange kapsaması medyan %1.69, en yüksek beşte birdekilerde (≥0.97, sıkı) %0.00 — AUC 0.69 (190 ve 191 organoid). Sıkı paketlenmiş organoidler T hücresini belirgin biçimde dışlıyor.

## 5. Bileşiklerin infiltrasyona etkisi

| bileşik | n kuyu | zenginleşme (medyan) | kontrole karşı δ | q |
|---|---|---|---|---|
| control | 4 | 0.67 | +0.00 | 1.000 |
| kras low | 4 | 0.86 | +0.25 | 0.960 |
| kras high | 3 | 1.05 | +0.67 | 0.800 |
| Src low | 4 | 0.91 | +0.50 | 0.800 |
| Src high | 4 | 0.78 | +0.12 | 1.000 |
| low kras+Src | 4 | 0.53 | -0.25 | 0.960 |
| high kras+Src | 4 | 1.32 | +0.75 | 0.800 |

Hiçbir bileşik kontrolden anlamlı biçimde ayrılmıyor (en düşük q = 0.80). Kuyu sayısı bileşik başına 3–4 — bu güçle ancak büyük etkiler görünür.

---

### Birimler ve ölçek

Ölçek: **2.798 µm/px**. Tif üstverisinde kalibrasyon yok (XResolution = tam 72 dpi yer tutucu, plaka XML'inde optik bilgi yok); kullanılan değerin kaynağı cihaz arayüzünün alan etiketi 2,91 × 3,94 mm ÷ 1040 × 1408 px ve **doğrulanmadı**. Piksel cinsinden verilen her sayı bu varsayımdan bağımsızdır; µm/µm²/mm² etiketleri kalibrasyonla doğrusal ölçeklenir ve hiçbir oran, AUC ya da korelasyonu etkilemez. Farklı bir değer için `INC_UM_PER_PX=...`. **z adımı bilinmiyor**; derinlik yalnızca katman indeksi olarak verildi.
