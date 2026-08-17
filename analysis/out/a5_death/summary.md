# A5 — Ölüm: kim ve neden

## 1. Ölüm sinyalinin büyüklüğü ve zamanlaması

NIR alan oranı 4. günde medyan **%0.088** (çeyrekler %0.017–%0.215, aralık %0.0000–%2.325).

Kanal çok seyrek — plaka genelinde piksellerin binde birinden azı eşik üstünde. Bu, kuyu başına ölçümün gürültülü olduğu anlamına gelir; aşağıdaki karşılaştırmalarda kuyular gruplanarak okunmalı, tek kuyu farkları yorumlanmamalı.

Zaman seyrinde plaka medyanı **1.7. günde** tepe yapıyor, sonra düşüyor: %0.237 (0. gün) → %0.267 (tepe) → %0.088 (4. gün).

**Ölü hücre sinyalinin azalması, ölümün azaldığı anlamına gelmez.** NIR birikmiş ölü maddeyi ölçer; sinyalin düşmesi ölü hücrelerin ortamdan kaldırıldığını (fagositoz, parçalanma, yüzeyden ayrılma) ya da boyanın soluklaştığını gösterir. Bu yüzden bu bölümdeki tüm karşılaştırmalar **aynı zaman noktası içinde** yapılıyor; zaman eksenindeki mutlak değişim kendi başına yorumlanmamalı.

## 2. Ölen kim?

NIR sinyalinin hangi kanalla örtüştüğü (medyan pay):

| grup | n | tümör üstünde | T hücresi üstünde | ikisinde | hiçbirinde |
|---|---|---|---|---|---|
| T eklendi | 27 | %28 | %3 | %0 | %48 |
| T yok | 36 | %50 | %1 | %0 | %47 |

T hücresi eklenmeyen kuyularda ölü sinyalinin %50'i tümör sinyaliyle örtüşüyor — orada ölen çoğunlukla tümör hücresi. T eklenen kuyularda tümörle örtüşen pay %28'e düşerken, orange ile örtüşen pay %1'den %3'e çıkıyor: **eklenen T hücrelerinin kayda değer bir kısmı ölüyor.**

Uyarı: bu paylar kütleyle karışır — bir kuyuda çok tümör sinyali varsa NIR'ın onunla örtüşme olasılığı zaten yüksektir. Kütleden arınmış ölçü aşağıdaki ölüm indeksi.

## 3. T hücresi tümör ölümünü artırıyor mu?

Eşleşmemiş bakışta: T eklenen kuyularda tümör ölüm indeksi medyan **0.0087**, eklenmeyenlerde **0.0262** (AUC 0.35, p = 0.04).

Ko-kültür × bileşik eşleşmesi içinde 15 karşılaştırma yapıldı; bunların **3 tanesinde** T eklenmiş kuyu daha yüksek, **12 tanesinde** daha düşük tümör ölüm indeksi gösterdi (medyan log2 oran -1.95, yani 0.26×; işaret testi p = 0.035).

**Yön beklenenin tersi.** T hücresi eklenen kuyularda tümör ölüm indeksi eşleşmiş T'siz kuyulardan sistematik olarak *düşük*. Sitotoksisite beklenen bir kurulumda bu ters sonucun birkaç olası açıklaması var ve veri aralarında seçim yapmıyor:

1. **Ölçü kütleye bölünüyor.** Ölüm indeksi NIR∩green'i green alanına bölüyor. Aynı eşleşmeler bölünmemiş NIR alan oranıyla tekrarlandığında 12/15 karşılaştırma yine T'li kuyuda daha düşük çıkıyor (medyan 0.42×), ve green alanı T'li ve T'siz kuyular arasında ayırt edilemiyor (AUC 0.44). **Bölme bu sonucu üretmiyor.**
2. **Ölü madde temizleniyor.** NIR birikmiş ölümü ölçer; ölü hücreler ortamdan kaldırılırsa sinyal düşer. A3'te makrofajlı kuyularda hem NIR hem orange'ın düşmesi bu mekanizmayla uyumlu.
3. **Gerçekten daha az ölüm.** Bu kurulumda T hücrelerinin tümörü öldürmediği, hatta organoide hiç ulaşmadığı (A2: sınırda yığılma, içeride seyrekleşme) sonucuyla tutarlı bir olasılık.

Ayırt etmenin yolu ölçüm değil tasarım: bilinen bir öldürücü (pozitif kontrol) ve T hücresi olmayan ama makrofaj olan bir eşleşme, hangi mekanizmanın işlediğini gösterir.

## 4. Bileşikler ölümü artırıyor mu?

Kontrol kuyularında tümör ölüm indeksi medyan 0.0445 (17 kuyu).

| bileşik | n | ölüm indeksi | kontrole karşı δ | q |
|---|---|---|---|---|
| kras low | 12 | 0.0158 | -0.20 | 0.789 |
| kras high | 3 | 0.0370 | -0.02 | 1.000 |
| Src low | 8 | 0.0119 | -0.10 | 0.985 |
| Src high | 4 | 0.0056 | -0.29 | 0.789 |
| low kras+Src | 15 | 0.0261 | +0.05 | 0.985 |
| high kras+Src | 4 | 0.0194 | -0.32 | 0.789 |

Hiçbir bileşik kontrolden anlamlı ayrılmıyor (en düşük q = 0.79).

## 5. Ölüm nerede oluyor?

Ölü sinyalinin medyan **%33**'i organoid teritoryasının içinde; teritorya alanın %36'ini kaplıyor. Zenginleşme 0.94× — ölüm organoid içi ve dışı arasında dengeli dağılmış.

Organoid başına (2721 organoid, 4. gün) NIR kapsamasının sıra korelasyonları: çapla **+0.32**, green kapsamasıyla **+0.34**, orange kapsamasıyla **+0.14**.

Üçü de pozitif ama büyüklükleri farklı: ölüm en çok **organoidin kendi boyutu ve tümör içeriğiyle** ilişkili (ρ +0.32 ve +0.34), T hücresi yüküyle ilişki bunların yarısı kadar (+0.14). 2721 organoidle bu korelasyonların hepsi istatistiksel olarak sıfırdan farklı, ama hiçbiri nedensellik göstermez: büyük organoidde hem daha çok hücre hem daha çok ölüm olması beklenir, T hücresi ve ölü boyası da organoid çevresinde aynı bölgelerde birikiyor olabilir.

## Nedene dair ne söylenebilir, ne söylenemez

- Örtüşme **ölenin kim olduğunu** söyler, **neden öldüğünü** söylemez. Yoğun bölgelerde bir NIR noktası hem tümöre hem T hücresine değebilir (`ikisi` sütunu).
- T hücresi eklemenin etkisi yalnızca eşleşmiş koşullarda okunmalı; ko-kültür bileşimi hem ölümü hem T dağılımını bağımsız olarak etkiliyor.
- NIR çok seyrek bir kanal; kuyu başına birkaç yüz piksel. Grup medyanları anlamlı, tek kuyu farkları değil.
- NIR **anlık ölüm hızı değil, o an ortamda duran ölü madde** ölçer. Sinyal hem ölümle artar hem temizlenmeyle azalır; plaka medyanının 1.7. günden sonra düşmesi bunun doğrudan kanıtı. Zaman eksenindeki değişim tek başına ölüm hızı olarak okunamaz.

---

### Birimler ve ölçek

Ölçek: **2.798 µm/px**. Tif üstverisinde kalibrasyon yok (XResolution = tam 72 dpi yer tutucu, plaka XML'inde optik bilgi yok); kullanılan değerin kaynağı cihaz arayüzünün alan etiketi 2,91 × 3,94 mm ÷ 1040 × 1408 px ve **doğrulanmadı**. Piksel cinsinden verilen her sayı bu varsayımdan bağımsızdır; µm/µm²/mm² etiketleri kalibrasyonla doğrusal ölçeklenir ve hiçbir oran, AUC ya da korelasyonu etkilemez. Farklı bir değer için `INC_UM_PER_PX=...`. **z adımı bilinmiyor**; derinlik yalnızca katman indeksi olarak verildi.
