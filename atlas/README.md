# atlas/ — kuyu başına 3B görünüm, figürler ve kanıt sayfaları

Bu klasör, ölçüm sonuçlarını **açılıp bakılabilir hâle** getiriyor. Her kuyu için
tek bir HTML dosyası üretiliyor; çift tıklayınca açılıyor, sunucu gerekmiyor,
internet gerekmiyor.

Sayfalardaki metin İngilizce, çünkü çıktı dergiye ve ortak yazarlara gidiyor.
Koddaki yorumlar depo genelindeki gibi Türkçe.

## Çalıştırma

```bash
python3 atlas/build.py --all --jobs 7    # ölçüm + sayfalar        ~30 dk (bir kez)
python3 atlas/thumbs.py --all --jobs 7   # kanıt küçük resimleri   ~15 dk (bir kez)
python3 atlas/check.py  --all --jobs 7   # segmentasyon kanıt sayfaları ~5 dk
python3 atlas/build.py --pages           # sayfaları yeniden üret  saniyeler
xdg-open atlas/site/index.html
```

Ölçüm bir kez yapılır ve `atlas/cache/` altına yazılır. Metni, figürü, birimi
değiştirmek istediğinizde yalnızca `--pages` çalıştırmak yeter — 30 dakikalık
ölçüm tekrar etmez.

Denetim:

```bash
python3 atlas/calib.py               # hücre sayısı kalibrasyonu ve testleri
python3 atlas/palette_check.py       # renklerin renk körlüğü denetimi
python3 atlas/selftest.py            # üretilen sayfalarda kırık bir şey var mı
python3 atlas/selftest.py --vs-analysis   # sayılar analysis/ hattıyla aynı mı
```

## Dört tür sayfa

| dosya | ne gösterir |
|---|---|
| `site/index.html` | 96 kuyuluk plaka. Seçtiğiniz ölçüye göre renkli; bir kuyuya tıklayınca sayfası açılır. |
| `site/<kuyu>.html` | O kuyunun 3B görünümü, dört figür, dört tablo, ve her sayının nereden geldiğini anlatan yöntem bölümü. |
| `site/groups.html` | Kuyular arası karşılaştırma: yedi figür, altı istatistik tablosu. Makaleye giren figürler bunlar. |
| `site/check/<kuyu>.html` | **Kanıt sayfası.** Solda ham fotoğraf, üstünde ölçülen maskenin sınırı; sağda aynı katmanın 3B karşılığı. z'de gezinirken ikisi birlikte hareket eder. |

## 3B görünümde gezinme

Blender'daki gibi:

| | |
|---|---|
| sürükle | döndür |
| shift+sürükle veya orta tuş | kaydır |
| tekerlek | yakınlaştır (imlecin olduğu yere doğru) |
| çift tık | başa dön |
| `1` `3` `7` `9` | önden, sağdan, tepeden, alttan |

Yukarıdaki çubuktan **katman dilimleme** açılıyor: aşağıdan yukarı inşa etme,
yukarıdan aşağı soyma, ya da tek katman. Oynat tuşu bunu animasyona çevirir.
Dilimlerken altta "görünen dilimde şu kadarı var" yazısı çıkar — göz yanılmasın
diye.

Bu denetimlerin hiçbiri ölçümü değiştirmiyor. Eşik, arkaplan çıkarma ve maskeler
çıkarım hattında plaka geneli sabit; kuyudan kuyuya değişen bir eşik kuyuları
karşılaştırılamaz hâle getirir. Bir sayının ne anlama geldiği yöntem bölümünde
yazıyor, kaydırıcıyla ayarlanmıyor.

## Kuyu sayfasındaki dört figür

Her figür tek bir soruyu yanıtlıyor:

| figür | soru |
|---|---|
| 1 — derinlikte sinyal | hangi z katmanında ne kadar var |
| 2 — kenara uzaklık | organoidin içinde mi, kenarında mı, dışında mı |
| 3 — derinlik × uzaklık | ikisi birden: hangi derinlikte, kenardan hangi uzaklıkta |
| 4 — zaman seyri | dört gün boyunca nasıl değişti |

Figür 1'de bir çubuğa tıklayınca iki şey oluyor: o katman 3B'de yalnız kalıyor ve
**o katmanın gerçek fotoğrafı** sayfada açılıyor. Yani "bu katmanda şu kadar var"
iddiası, sayfadan çıkmadan görüntüye karşı denetlenebiliyor.

Her figürün altında tablo görünümü ve SVG indirme var; tablolar CSV olarak iniyor,
3B sahne PNG (üç kat çözünürlükte) ve dört görünümlü panel olarak. Ekranda ne
varsa makaleye o gidiyor.

## Hücre sayısı: ne söylüyoruz, ne söylemiyoruz

Bu en dikkat gerektiren kısım, o yüzden uzun anlatıyorum.

**Ölçülen şey sinyal alanıdır.** mm² cinsinden yazan her şey, eşiğin üstünde kalan
piksellerin alanıdır — doğrudan ölçüm. Hücre sayısı ise **türetilmiş tahmindir** ve
her yerde `≈` ile yazılır.

**T hücresi sayısı nereden çıkıyor.** Ekim sayıları biliniyor: T hücresi eklenen
kuyulara 5000 hücre konmuş. T'li ve T'siz kuyular arasındaki sinyal alanı farkı
5000'e bölününce **90,8 µm²/hücre** çıkıyor. Bu ölçeği kullanmadan önce üç testten
geçirdim:

1. Ölçek, hücre başına **10,8 µm eşdeğer çap** öngörüyor. Bir T hücresi 7–10 µm;
   2,798 µm/px'te floresan taşmasıyla birlikte beklenen değer tam olarak bu. Yani
   ölçek biyolojik olarak imkânsız bir hücre boyutu üretmiyor.
2. Dört ko-kültür grubu (PDA, +CAF, +MAC, +CAF+MAC) ölçeği **birbirinden bağımsız**
   olarak 84–102 µm² aralığında tekrarlıyor.
3. Kuyular arası dağılım dar (CV %20), medyanın güven aralığı ±%9.

**Tümör neden hücre olarak sayılmıyor.** Aynı hesabı 2000 PDA hücresi için
yaptığımda 8,9 µm eşdeğer çap çıkıyor — bir T hücresinden küçük, yani imkânsız.
Sebebi belli: green kanalı organoidlerin çoğunu boyamıyor (QC ölçümünde BF'de
görülen organoidlerin medyan %15'inde green sinyali var). Bu kalibrasyon
hesaplandı ve **reddedildi**; sayfada gösteriliyor ki reddin gerekçesi
denetlenebilsin.

**Nesne saymak neden işe yaramıyor.** T'li ve T'siz kuyular arasındaki bağlı
bileşen farkı 1155, beklenen 5000. Yani bu çözünürlükte her nesne ortalama 4,3
hücre içeriyor. Bütün ölçüler bu yüzden alan tabanlı.

**Katman başına hücre sayısındaki tuzak.** Kalibrasyon, z boyunca maksimum
projeksiyonun maskesi üzerinde tanımlı. Katman başına alanlar farklı bir büyüklük:
toplamları projeksiyon alanının 3–5 katı, çünkü 4× objektifin odak derinliği
onlarca mikron ve aynı hücre birkaç katmanda görünüyor. Katman alanını aynı ölçeğe
bölmek hücre sayısını kat kat şişirirdi. Bu yüzden katman başına hücre sayısı
**kuyu toplamının dağıtılmasıdır**: her katman, sinyal payı kadarını alır ve
katmanların toplamı tam olarak kuyu toplamına eşit olur. Sayfada ve tabloda böyle
yazıyor. Uzaklık bantlarında bu sorun yok — bantlar projeksiyon maskesinden
hesaplanıyor, alanları tam olarak projeksiyon alanına eşit, ölçek doğrudan
uygulanabiliyor.

## Dome — ve çoğu kuyuda neden yok

Dome, brightfield organoid teritoryasının **en büyük bağlı bileşenine** uyduruluyor.
Tüm teritoryaya uydurulsaydı dağınık döküntü ağırlık merkezini kadrajın ortasına
çeker ve yarıçap kuyunun değil kadrajın ölçüsü olurdu (B04'te 1689 µm yerine
1053 µm).

En büyük bileşen teritoryanın yarısından azını kaplıyorsa kuyu çok organoidlidir ve
"merkezden uzaklık" tanımlı bir büyüklük değildir; o kuyularda dome halkası
çizilmiyor. Ölçülen: B02 %97 ve B04 %86 tek kütle, ama B01 %16 ve A01 %26. Bu
yüzden birincil çerçeve dome değil, **organoid kenarına işaretli uzaklık** — her
iki durumda da çalışıyor.

## Birimler

| büyüklük | birim | neye dayanıyor |
|---|---|---|
| zenginleşme, pay, oran, AUC, Cliff δ | boyutsuz | **hiçbir şeye** |
| piksel ve voksel sayıları | sayı | **hiçbir şeye** |
| alan (mm², µm²), uzaklık (µm) | µm türevi | 2,798 µm/px — cihazın kendi alan etiketinden geri hesaplandı, **doğrulanmadı** |
| ≈ T hücresi sayısı | hücre | yukarıdaki kalibrasyon |
| sinyal hacmi | µm²·katman | z adımıyla çarpılınca µm³ olur |
| derinlik | z katman indeksi | z adımı hiçbir dosyada yok |

Piksel boyutunu değiştirmek isterseniz `INC_UM_PER_PX=... python3 atlas/build.py
--pages` — ölçüm tekrar edilmez.

### z adımı arandı, gerçekten yok

TIFF etiketlerinde tek bir optik alan yok (`XResolution` sabit 72 dpi yer tutucu,
`Software` dışında hiçbir cihaz alanı yok). `plate_map.PlateMap` XML'inde `z`,
`step`, `objective`, `plane`, `focus`, `micron` kelimelerinin **sıfır** geçişi var;
dosya yalnızca kuyu içeriği ve ekim yoğunluğu taşıyor.

Bu yüzden 3B'de XY ekseni gerçek ölçekli ve ölçek çubuğu taşıyor, **z ekseni ise
sıralı**: katmanlar eşit aralıklı çiziliyor, katman numaralarıyla etiketleniyor ve
µm iddia edilmiyor. Ayrımın görünür olması için z ekseninde bilerek ölçek çubuğu
yok. Ayrıca z00 mutlak bir yükseklik değil — odak kuyu başına ayarlanıyor, o yüzden
kuyular arasında dağılımın *şeklini* karşılaştırın, katman numarasını değil.

Değer tarama protokolünden bulunursa hacimler tek çarpanla µm³'e döner.

## Renkler denetlendi

Alışılmış yeşil/turuncu/kırmızı floresan üçlüsü kullanılmadı. Ölçüldüğünde
kalıyor: kırmızı-kör görüşte yeşil ile turuncu arasındaki fark ΔE 3,2 (taban 6,0),
turuncu ile kırmızı arasındaki fark normal görüşte bile ΔE 7,1 (taban 15,0). Yani
erkek okurların yaklaşık %8'i tümörü T hücresinden ayıramazdı. Kullanılan üçlü her
iki modda da bütün eşikleri geçiyor (`python3 atlas/palette_check.py`). Renk yine
de tek taşıyıcı değil: her seri doğrudan etiketli ve her figürün tablo görünümü
var.

## Dosyalar

| | |
|---|---|
| `calib.py` | hücre kalibrasyonu; doğrulama testleri ve reddedilenler |
| `measure.py` | kuyu-zaman başına 3B ölçüm; eşikler `analysis/extract.py`'den birebir |
| `build.py` | ölçümü koşturur, türetilmiş büyüklükleri hesaplar, sayfaları yazar |
| `groups.py` | kuyular arası karşılaştırma ve istatistik |
| `check.py` | segmentasyon kanıt sayfaları (tam çözünürlük) |
| `thumbs.py` | kuyu sayfasına gömülen kanıt küçük resimleri |
| `page.py` | HTML üretimi — burada hiçbir sayı hesaplanmaz, yalnızca yerleşim ve metin |
| `theme.py`, `palette_check.py` | renkler ve renk denetimi |
| `selftest.py` | üretilen sayfaların denetimi + `analysis/` hattıyla karşılaştırma |
| `templates/` | `app.css`, `scene.js` (WebGL), `figs.js`, `groups.js`, `well.js`, `check.js`, `index.js` |
| `cache/` | ölçüm ve küçük resim önbelleği — silinebilir, yeniden üretilir |
| `site/` | çıktı |

### `analysis/` ile ilişkisi

Eşikler, brightfield maskesi ve bant kenarları oradan birebir alınıyor, dolayısıyla
buradaki sayılar `analysis/out/` altındaki analizlerle aynı tanımı kullanıyor.
`selftest.py --vs-analysis` bunu her seferinde denetliyor: 1144 kuyu×zaman örneğinin
tamamında alan oranı, teritorya ve zenginleşme birebir eşit olmak zorunda. Bu
kontrol bir kez gerçek bir hata yakaladı — zenginleşme, oran yuvarlandıktan sonra
hesaplanıyordu ve küçük oranlarda %60'ı aşan bağıl hata veriyordu.

Atlas o analizlerin yerine geçmiyor. Onlar plaka geneli karşılaştırma ve istatistik
yapıyor; atlas tek kuyuyu uzamsal olarak açıyor ve figürleri dergiye hazır biçimde
üretiyor.

## Bu atlasın yanıtlayamadıkları

- **Makrofaj ve CAF nerede.** Floresan işaretleyicileri yok; görüntüde tümör
  hücrelerinden ayırt edilemiyorlar. Hangi kuyuda oldukları yalnızca plaka
  haritasından biliniyor.
- **Tümör hücre sayısı.** Yukarıda anlatıldı.
- **Mutlak derinlik ve µm³ hacim.** z adımı kayıtlı değil.
- **İnce 3B yapı.** 4× objektifin (NA ≈ 0,13) eksenel çözünürlüğü düşük; beklenen
  şey derinlik dilimleri. Her düzlemde odak dışı sis var, dekonvolüsyon
  uygulanmıyor.
