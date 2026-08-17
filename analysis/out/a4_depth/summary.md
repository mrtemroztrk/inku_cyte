# A4 — Derinlik ve 3B dağılım

## 1. Kanallar derinlikte nerede

- **tümör (green)**: ağırlık merkezi z7.6, katman başına yayılım 3.0 katman, en yoğun 3 katmanın toplam sinyaldeki payı **%41**
- **T hücresi (orange)**: ağırlık merkezi z5.2, katman başına yayılım 3.4 katman, en yoğun 3 katmanın toplam sinyaldeki payı **%66**
- **ölü (NIR)**: ağırlık merkezi z6.6, katman başına yayılım 2.6 katman, en yoğun 3 katmanın toplam sinyaldeki payı **%61**

Pay ne kadar yüksekse sinyal o kadar ince bir dilime sıkışmış demektir. 17 katmana eşit yayılmış bir sinyalde bu pay %18 olurdu.

**Buradaki asıl bulgu tümör ile T hücresi arasındaki fark:** tümör sinyali derinliğe yayılmış (en yoğun 3 katman %41), T hücresi sinyali çok daha ince bir dilime sıkışmış (%66, AUC 0.74). Tümör kütlesi 17 katmanın çoğuna dağılırken T hücreleri tek bir düzlemde duruyor — derinlemesine nüfuz eden bir dağılımın beklenen görüntüsü bu değil.

## 2. T hücreleri tümöre göre daha yüzeyde mi?

T eklenen 27 kuyuda T hücresi ağırlık merkezi ile tümör ağırlık merkezi arasındaki fark medyan **-1.18 katman** (%95 GA -2.85…+0.14; Wilcoxon p = 0.0036).

Negatif değer T hücrelerinin tümörden daha küçük z indislerinde durduğu anlamına gelir. 18/27 kuyuda kayma negatif — yön tutarlı ve Wilcoxon testi sıfırdan farkı destekliyor, ama medyanın güven aralığı (-2.85…+0.14) geniş: **kaymanın varlığı sağlam, büyüklüğü değil.**

Kaymanın işaretini mutlak derinliğe çevirmek için taramanın yönü (z00 kuyunun tabanı mı yüzeyi mi) bilinmeli; bu bilgi dosyalarda yok. Yani "T hücreleri organoidin üstünde mi altında mı" sorusu **tarama protokolü olmadan yanıtlanamaz** — ölçülen şey yalnızca ayrı bir düzlemde durdukları.

Aynı ölçüm ölü hücreler için: -0.88 katman (62 kuyu). Ölü sinyali tümörden farklı bir derinlikte yoğunlaşıyor.

## 3. İnfiltrasyon derinlikle değişiyor mu?

Her z katmanında ayrı ayrı: o katmandaki orange sinyalinin ne kadarı organoid teritoryasının içinde? Teritorya 2B bir ayak izi olduğu için bu, "organoidin üstünden mi geçiyor yoksa içine mi giriyor" sorusunu katman katman ayırır.

Karşılaştırma tabanı: bu kuyularda teritorya alanın medyan %37'ini kaplıyor, yani rastgele dağılmış bir sinyal her katmanda %37 "içeride" çıkardı.

Orange için içeride kalan pay katmanlar arasında %29 ile %48 arasında değişiyor (1.63× salınım); tümörün en yoğun olduğu katmanda (z6) %38. Karşılaştırma için green'in aynı katmandaki içeride kalan payı %59.

Profil katman indeksiyle artıyor (ρ = +0.92): T hücrelerinin organoidle örtüşmesi derinliğe bağlı, tek bir sayıyla özetlenemez.

## 4. 2B projeksiyon 3B'yi temsil ediyor mu?

MIP üzerinden ölçülen "organoid içi pay" ile tüm voksellerden ölçülen pay arasındaki sıra korelasyonu **0.971** (medyanlar %33.3 ve %32.6).

İkisi aynı sıralamayı veriyor: MIP tabanlı ölçümler bu veri için 3B ölçümlerin yerine geçebilir. Bu önemli, çünkü MIP ölçümü çok daha ucuz ve odak dışı sise karşı daha dayanıklı.

## Sınırlar

- **z adımı bilinmiyor.** Katman indeksi mikrona çevrilemedi; tüm derinlik sayıları katman biriminde.
- **z00 mutlak değil.** Odak kuyu başına ayarlandığı için kuyular arası karşılaştırmalar yalnızca hizalanmış (göreli) profillerde geçerli.
- **Eksenel çözünürlük düşük.** 2,798 µm/px bir 4× objektif demek (NA ≈ 0,13); her düzlemde odak dışı sis var, dekonvolüsyon uygulanmadı. Beklenen şey derinlik *dilimleri*, ince 3B yapı değil.
- **Teritorya 2B.** Katman katman "içeride" payı, 2B ayak izine göre hesaplanır; gerçek bir 3B kapsanma testi değildir.

---

### Birimler ve ölçek

Ölçek: **2.798 µm/px**. Tif üstverisinde kalibrasyon yok (XResolution = tam 72 dpi yer tutucu, plaka XML'inde optik bilgi yok); kullanılan değerin kaynağı cihaz arayüzünün alan etiketi 2,91 × 3,94 mm ÷ 1040 × 1408 px ve **doğrulanmadı**. Piksel cinsinden verilen her sayı bu varsayımdan bağımsızdır; µm/µm²/mm² etiketleri kalibrasyonla doğrusal ölçeklenir ve hiçbir oran, AUC ya da korelasyonu etkilemez. Farklı bir değer için `INC_UM_PER_PX=...`. **z adımı bilinmiyor**; derinlik yalnızca katman indeksi olarak verildi.
