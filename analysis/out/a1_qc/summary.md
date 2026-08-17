# A1 — Kalite kontrolü ve boyama kapsamı

## 1. Kullanılabilirlik

88 görüntülenen kuyudan **4 tanesi** dışlandı. Dışlama ölçütü dar tutuldu: yalnızca görüntünün kendisini kullanılamaz kılan iki bayrak (odak ve aydınlatma) dışlama sebebi. Konfluens ölçümü bozmaz, yalnızca konum ölçümlerini anlamsızlaştırır; ayrı işaretlenir.

| bayrak | ne demek | dışlar mı | bayraklı kuyu | bayraklı kare |
|---|---|---|---|---|
| `nostruct` | BF yapı puanı < 30 — yapısız alan (odak dışı ya da boş) | evet | 3 | 35 / 1144 |
| `floor` | BF zemini 128'den >5 gri seviye sapmış | evet | 1 | 37 / 1144 |
| `confluent` | BF teritoryası alanın >%90'ini kaplıyor | hayır — konum ölçümü geçersiz | 1 | 33 / 1144 |

Dışlananlar: **A10** (nostruct), **A11** (nostruct), **B10** (nostruct), **D03** (floor)

Konfluent (içeride/dışarıda ayrımı anlamsız): **D03**

BF yapı puanı (Laplace varyansı) bir **odak ölçüsü değil**: kuyu büyüdükçe yükseliyor (kütleyle sıra korelasyonu 0.83). Bu yüzden "kuyunun kendi en iyisine göre düşük" gibi göreli bir ölçüt hızlı büyüyen kuyuların erken karelerini bayraklardı — o ölçüt kullanılmadı; yerine mutlak bir taban kondu.

Orange arkaplanı z boyunca medyan 8.37 birim kayıyor (en yüksek 35.95). Bu kayma bir kusur değil — z boyunca odak dışı sis miktarı değişir — ve düzlem başına medyan çıkarıldığı için ölçümlere geçmiyor; buraya yalnızca kayıt için yazıldı.

Dye kontrol kuyuları (kolon 10–12, 24 kuyu) BF'de medyan 4.6% teritorya gösteriyor; diğer kuyularda bu 33.7%. Yapı puanı medyanı 148 vs 360. Bu kolonlar belirgin biçimde odak dışı ve seyrek — boya kontrolü olarak kullanılabilirler ama morfoloji karşılaştırmasına girmemeliler.

## 2. Green tüm organoidleri boyamıyor

Son zaman noktasında, QC'den geçen 84 kuyuda brightfield'da ayırt edilen organoidlerin medyan **%15**'inde green sinyali var (kapsama >%1 eşiği; çeyrekler %6–%41). Yani BF'de organoid olarak görülen nesnelerin çoğunluğunun green kanalında karşılığı yok.

Bunun iki olası nedeni var ve veri ikisini ayırmıyor:

1. **Boyama eksik** — organoid var, boya girmemiş.
2. **BF nesnesi tümör değil** — CAF/makrofaj kümesi, döküntü veya ölü madde de BF'de koyu görünür ve green ile boyanmaz.

İkisini ayıran gözlem: PDA'nın tek başına olduğu kuyularda BF nesnelerinin yalnızca bir kısmı green-pozitif olmalıydı ancak *tüm* nesneler tümör olmalı. Ölçüm:
- **PDA** (16 kuyu): green-pozitif organoid oranı medyan %10, organoid başına medyan green kapsaması %0.0
- **PDA+CAF** (22 kuyu): green-pozitif organoid oranı medyan %10, organoid başına medyan green kapsaması %0.0
- **PDA+MAC** (22 kuyu): green-pozitif organoid oranı medyan %45, organoid başına medyan green kapsaması %0.4
- **PDA+CAF+MAC** (24 kuyu): green-pozitif organoid oranı medyan %10, organoid başına medyan green kapsaması %0.0

PDA-tek kuyularda (16 kuyu) bile oran %10 — orada tümör dışı hücre tipi yok, dolayısıyla eksikliğin **en azından bir kısmı gerçekten boyanmamış organoid**. Green kanalına dayanan her tümör sayımı bu kadar eksik sayıyor demektir; tümör kütlesi için BF teritoryası, boyanma durumu için green kullanılmalı.

Boyutla ilişki net: <36 px (101 µm) organoidlerin %11'i, ≥71 px (199 µm) olanların %44'i green-pozitif (1245 ve 563 organoid). Küçük nesnelerin bir bölümü muhtemelen tek hücre/döküntü; büyük olanlarda bile kayıp sıfır değil.

## 3. Eşik duyarlılığı

Eşik ×0,67 ve ×1,67 kaydırıldığında alan oranı değişiyor ama kuyu **sıralaması** korunuyor — karşılaştırmalar eşik seçimine dayanıklı:

| kanal | alan oranı (ana eşik) | sinyalli kuyu | ×0,67'de kaç kat | ×1,67'de kaç kat | sıra kor. (düşük) | (yüksek) |
|---|---|---|---|---|---|---|
| green | 2.202% | 84/84 | 1.67× | 0.41× | 0.985 | 0.978 |
| orange | 0.819% | 83/84 | 1.43× | 0.60× | 0.982 | 0.988 |
| nir | 0.032% | 63/84 | 0.89× | 0.09× | 1.000 | 0.973 |

## 4. Arkaplan ve pozlama kayması

Floresan kanalların arkaplanı kuyudan kuyuya ve zaman içinde kayıyor; bu yüzden tüm ölçümler düzlem başına medyan çıkarıldıktan sonra yapıldı. Kalan kayma:
- **green**: kuyular arası arkaplan 0.3–1.0 (medyan 0.7); z boyunca kayma medyanı 0.42 birim
- **orange**: kuyular arası arkaplan 0.8–69.4 (medyan 17.6); z boyunca kayma medyanı 9.19 birim
- **nir**: kuyular arası arkaplan 0.0–0.0 (medyan 0.0); z boyunca kayma medyanı 0.00 birim

---

### Birimler ve ölçek

Ölçek: **2.798 µm/px**. Tif üstverisinde kalibrasyon yok (XResolution = tam 72 dpi yer tutucu, plaka XML'inde optik bilgi yok); kullanılan değerin kaynağı cihaz arayüzünün alan etiketi 2,91 × 3,94 mm ÷ 1040 × 1408 px ve **doğrulanmadı**. Piksel cinsinden verilen her sayı bu varsayımdan bağımsızdır; µm/µm²/mm² etiketleri kalibrasyonla doğrusal ölçeklenir ve hiçbir oran, AUC ya da korelasyonu etkilemez. Farklı bir değer için `INC_UM_PER_PX=...`. **z adımı bilinmiyor**; derinlik yalnızca katman indeksi olarak verildi.
