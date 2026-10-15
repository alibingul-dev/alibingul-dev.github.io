# Yeni araç kontrol listesi

Her araç bu listeyi geçmeden yayına girmez. Geçmezse araç haftayı atlar.

## Kurulum
- [ ] `_template/` klasörünü `/tools/<slug>/` olarak kopyala (slug: küçük harf, tire, Türkçe karakter yok).
- [ ] TR ve EN sayfada tüm `{{...}}` alanları dolduruldu; dosyada `{{` kalmadı.
- [ ] İki sayfada da `noindex` satırı silindi.
- [ ] Demo panel ve demo script gerçek araçla değiştirildi.
- [ ] `/tools/registry.json` dosyasına araç satırı eklendi (`status: "live"`).

## Kural
- [ ] Dış sunucuya istek yok (fonts, GoatCounter hariç). Dosya tarayıcıdan çıkmıyor.
- [ ] Telefon genişliğinde (360 px) yatay kaydırma yok.
- [ ] Açık ve koyu temada okunuyor.
- [ ] Hukuki/finansal sonuç üreten metin yok; varsa "bilgi amaçlıdır" notu var.

## Canlı test (Ali, perşembe)
- [ ] Gerçek dosyayla denendi: küçük, büyük, bozuk/yanlış tür.
- [ ] Çıktı dosyası açıldı ve beklenen sonucu verdi.
- [ ] TR ↔ EN dil bağlantısı karşılıklı çalışıyor.
- [ ] "yayınla" onayı verildi.
