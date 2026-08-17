# inc_t_cell — T hücresi infiltrasyonu, Incucyte zaman serisi

PDA 30364 tümör organoidleri, CAF ve/veya makrofajla birlikte kültüre edilmiş,
T hücresi eklenmiş ya da eklenmemiş, KRAS ve SRC inhibitörleriyle muamele
edilmiş. Incucyte'ta dört gün boyunca görüntülendi.

Bu depo o görüntülerden sayı çıkarıyor ve o sayıları bakılabilir hâle getiriyor.

| | |
|---|---|
| Plaka | 96 kuyu; **88'i görüntülendi** (sütun 9 görüntülenmedi) |
| Zaman | 13 nokta, ~8 saat aralık, toplam 96 saat |
| Kanallar | brightfield (1 düzlem), green, orange, NIR (her biri 17 z düzlemi) |
| Kanal → içerik | green = tümör, orange = T hücresi, NIR = ölü hücre |
| Görüntü | 1040 × 1408 px, 2,798 µm/px (Incucyte 4×) |
| Toplam | 59 488 tif, 44 GB |

## Üç klasör, üç iş

| klasör | ne yapar | nereden başlanır |
|---|---|---|
| **`data/inc_tests/`** | Ham veri, plaka haritası ve dosya listesi. Dokunulmadı. | [`data/inc_tests/README.md`](data/inc_tests/README.md) |
| **`analysis/`** | Piksel tabanlı ölçüm ve altı ayrı analiz. Her analiz kendi sorusunu yanıtlar, kendi klasörüne yazar. | [`analysis/README.md`](analysis/README.md) |
| **`atlas/`** | Sonuçları açılıp bakılabilir hâle getirir: kuyu başına 3B görünüm, figürler, tablolar ve segmentasyon kanıt sayfaları. | [`atlas/README.md`](atlas/README.md) |
| `viewer/` | Ham görüntüleri kanalları üst üste bindirerek inceleyen yerel uygulama. | [`viewer/README.md`](viewer/README.md) |

Aceleniz varsa: `atlas/site/index.html` dosyasını tarayıcıda açın.

## Kurulum ve çalıştırma

Bağımlılıklar: `numpy scipy scikit-image pandas tifffile matplotlib pillow`
(ayrıca `viewer/` için `fastapi uvicorn`).

```bash
# 1. ölçüm — bir kez, ~20 dk
python3 analysis/extract.py --flat
python3 analysis/extract.py --all --jobs 7

# 2. analizler — sırayla, a1 dışlama listesini üretir
python3 analysis/a1_qc.py
python3 analysis/a2_infiltration.py
python3 analysis/a3_labelfree.py
python3 analysis/a4_depth.py
python3 analysis/a5_death.py
python3 analysis/a6_growth.py

# 3. atlas — 3B görünüm, figürler, kanıt sayfaları
python3 atlas/build.py  --all --jobs 7
python3 atlas/thumbs.py --all --jobs 7
python3 atlas/check.py  --all --jobs 7
xdg-open atlas/site/index.html
```

## Bu veriden çıkarılabilenler ve çıkarılamayanlar

Bu bölüm depo genelinde geçerli; ayrıntılar klasör README'lerinde.

**Çıkarılabilir.** Kanal başına sinyal alanı ve hacmi; organoid kütlesi
(brightfield'dan, boyadan bağımsız); bir popülasyonun organoidin içinde mi
dışında mı olduğu ve kenardan ne kadar uzakta durduğu; derinlik dağılımı; bunların
dört gün boyunca nasıl değiştiği; ve gruplar arası karşılaştırmalar.

**T hücresi sayısı tahmin edilebilir.** Ekim sayısı biliniyor (5000/kuyu), bundan
90,8 µm²/hücre ölçeği kalibre edildi ve üç testten geçti — en önemlisi, ölçek
hücre başına 10,8 µm eşdeğer çap öngörüyor, ki bu bir T hücresinin gerçek boyutu.
Bu sayılar her yerde `≈` ile yazılıyor.

**Tümör hücre sayısı çıkarılamaz.** Aynı hesap 2000 PDA hücresi için bir T
hücresinden küçük bir hücre boyutu veriyor, yani imkânsız: green kanalı
organoidlerin çoğunu boyamıyor. Tümör alan ve hacim olarak raporlanıyor.

**Makrofaj ve CAF görüntüde bulunamaz.** Floresan işaretleyicileri yok; hangi
kuyuda oldukları yalnızca plaka haritasından biliniyor.

**Mutlak derinlik ve µm³ hacim verilemez.** z adımı hiçbir dosyada kayıtlı değil —
TIFF etiketlerinde optik alan yok, plaka XML'inde de yok. Derinlik katman indeksi
olarak veriliyor; hacimler `µm²·katman` olarak, z adımıyla çarpılınca µm³ oluyor.

**Piksel boyutu doğrulanmadı.** 2,798 µm/px değeri cihazın kendi alan etiketinden
(2,91 × 3,94 mm) geri hesaplandı. Boyutsuz ölçüler (oran, zenginleşme, pay) bu
değerden bağımsız; µm ve mm² cinsinden her şey ona bağlı.

## Ölçüm neden piksel tabanlı, nesne tabanlı değil

2,798 µm/px'te bir T hücresi yaklaşık 2,5 piksel. Tek hücre segmentasyonu bu
ölçekte güvenilir değil: eşik biraz kaydırılınca nesne sayısı katlanarak değişiyor.
Doğrudan ölçüldü — T hücresi eklenen ve eklenmeyen kuyular arasındaki bağlı bileşen
farkı 1155, beklenen 5000; yani her nesne ortalama 4,3 hücre içeriyor.

Alan oranları çok daha kararlı: eşik 0,67 ve 1,67 katına kaydırıldığında kuyu
sıralamasının sıra korelasyonu 0,93–0,98 arasında kalıyor. Bu yüzden bütün ana
ölçüler eşik üstü piksel/voksel alanı ve bunlardan türeyen oranlar.

## Eşikler neden kuyuya uyarlanmıyor

Kuyuya uyarlanan bir eşik her kuyuyu farklı ölçekler ve kuyular karşılaştırılamaz
hâle gelir. Bütün eşikler plaka geneli sabit. Bunun bedeli, bazı kuyularda eşiğin
cömert bazılarında cimri kalmasıdır — bu yüzden `atlas/site/check/` altındaki
kanıt sayfaları var: ham görüntü ile ölçülen maskenin sınırı yan yana duruyor ve
eşiğin nerede durduğu gözle denetlenebiliyor.
