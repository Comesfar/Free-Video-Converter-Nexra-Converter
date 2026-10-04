# 🎬 Nexra Video Compressor

<p align="center">
  <img src="icon.png" width="128" height="128" alt="Nexra Video Compressor Logo" />
</p>

<p align="center">
  <b>Videolarınızı istediğiniz MB boyutuna (Discord, WhatsApp, E-posta vb.) kaliteden ödün vermeden düşüren modern, açık kaynaklı masaüstü aracı.</b><br/>
  <i>Piyasadaki ücretli, filigran basan ve kuyrukta bekleten sitelere son!</i>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-0078D6?style=flat-square&logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/GPU%20Acceleration-NVIDIA%20NVENC-76B900?style=flat-square&logo=nvidia" alt="NVIDIA NVENC" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License" />
</p>

---

## ✨ Öne Çıkan Özellikler

* **🚫 Sıfır Filigran & Reklam:** Videolarınıza asla filigran (watermark) veya logo basmaz.
* **🎯 Kesin Hedef MB Tutarlılığı (2-Pass Akıllı Motor):**
  * **8 MB / 10 MB / 20 MB / 25 MB** gibi hazır Discord/WhatsApp şablonları veya dilediğiniz özel boyut (örn. `14.5 MB`).
  * %4 konteyner güvenlik tamponu ile dosyanız asla sınırı aşıp reddedilmez.
* **⚡ NVIDIA NVENC Donanım Hızlandırma (GPU):**
  * Render yükü doğrudan GPU'ya aktarılır; 300–600 FPS ile dakikalar sürecek sıkıştırmayı **saniyeler içinde** tamamlar.
* **✂️ Video Kırpma & Kesme (Trim):**
  * Uzun kayıtlardan istediğiniz bölümü seçip (`00:00:15 - 00:00:45` gibi) sadece o kısmı hedef boyuta sıkıştırabilirsiniz.
* **🖱️ Windows Sağ Tık Menüsü:**
  * Herhangi bir videoya sağ tıklayıp tek tıkla doğrudan `Nexra ile Aç` veya `Discord (25 MB)` olarak sıkıştırma başlatabilirsiniz.
* **🖼️ Otomatik Video Küçük Resmi (Thumbnail):**
  * Yüklenen videodan anlık görsel önizleme oluşturulur.
* **📁 Toplu Video Sıkıştırma (Batch Mode):**
  * Birden fazla videoyu kuyruğa ekleyip tek tıkla sırayla sıkıştırma.
* **🔒 %100 Çevrimdışı & Güvenli:**
  * Videolarınız hiçbir harici sunucuya gitmez, her şey tamamen kendi bilgisayarınızda yerel çalışır.

---

## 🚀 Kaynak Koddan Çalıştırma (Geliştiriciler İçin)

Python kurulu sistemde çalıştırmak için:

```bash
# 1. Depoyu klonlayın
git clone https://github.com/Comesfar/Free-Video-Converter-Nexra-Converter.git
cd Free-Video-Converter-Nexra-Converter

# 2. Gerekli kütüphaneleri yükleyin
pip install -r requirements.txt

# 3. Uygulamayı başlatın
python main.py
```

---

## 📦 Kendi `.exe` Dosyanızı Derleme

Projeyi tek parça bağımsız bir `.exe` haline getirmek için:

```bash
pyinstaller --noconfirm --onefile --windowed --icon="icon.ico" --name="Nexra Video Compressor" --add-data="icon.ico;." --add-data="icon.png;." --add-binary="ffmpeg.exe;." --collect-all customtkinter --collect-all windnd main.py
```

Derlenen dosya `dist/Nexra Video Compressor.exe` konumunda oluşacaktır.

---

## 📄 Lisans
Bu proje **[MIT Lisansı](LICENSE)** ile lisanslanmıştır. Tamamen ücretsiz ve açık kaynaklıdır.
