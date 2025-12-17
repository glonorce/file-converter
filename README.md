# DocuForge: Intelligent PDF to Markdown Converter
*(Türkçe açıklama aşağıdadır / Scroll down for English)*

---

# 🇹🇷 DocuForge: Akıllı PDF Dönüştürücü

**DocuForge**, PDF belgelerini modern ve yapay zeka dostu **Markdown** formatına dönüştüren, yüksek performanslı bir araçtır. Özellikle Türkçe ve İngilizce için geliştirdiğimiz **"Akıllı Dil Uzmanı" (Healer Engine)** sayesinde, PDF'lerdeki bozuk metinleri (örn: "v e" -> "ve", "t he" -> "the") otomatik olarak onarır.

**Kendi Kendini İyileştiren Motor (Auto-OCR):** Eğer bir sayfada `G ü ç` gibi bozuk font kodlaması tespit edilirse, sistem o sayfayı otomatik olarak OCR (Görsel Okuma) moduna alır ve sorunu %100 düzeltir.

## 💡 Neden Markdown?

*   **Yapay Zeka (AI) İçin:** ChatGPT veya Claude gibi modellere PDF yerine Markdown verirseniz, dokümanı **%100 doğrulukla** anlarlar.
*   **GitHub İçin:** Değişiklikleri satır satır takip edebilirsiniz.
*   **Temiz Okuma:** Gereksiz boşluklardan, headers ve footers gibi tekrarlayan metinlerden arınmış, saf bilgi içerir.
*   **🔒 %100 Gizlilik:** Tüm işlemler bilgisayarınızda (Local) gerçekleşir. Belgeleriniz asla internete yüklenmez.

## � Neden DocuForge?

Cloud tabanlı LLM servisleri (ChatGPT, Claude vb.) PDF işlemede şu sorunları yaşar:
- **Gizlilik:** Belgeleriniz üçüncü taraf sunuculara yüklenir
- **Maliyet:** Sayfa/token başına ücretlendirme
- **Limitler:** Yüksek sayfalı dosyalarda context window sorunu
- **Hız:** API rate limitleri ve kuyruk bekleme süreleri

**DocuForge bu sorunları çözer:**
- ✅ **%100 Yerel İşlem** - Verileriniz asla bilgisayarınızdan çıkmaz
- ✅ **Sınırsız & Ücretsiz** - Binlerce sayfa, sıfır maliyet
- ✅ **Paralel İşlem** - Çoklu PDF'leri aynı anda dönüştürün
- ✅ **Akıllı OCR** - Bozuk fontları otomatik algılar ve düzeltir
- ✅ **Türkçe Optimizasyonu** - Healer motoru Türkçe karakterleri (ş, ğ, ı, ü, ö, ç) akıllıca onarır

## �📦 Kurulum (Adım Adım)

Bu araç güçlü motorlar (OCR, Tablo okuyucu) kullanır. Lütfen sırasıyla uygulayın:

### 1. Hazırlık ve İndirme
Önce komut satırında (Terminal/PowerShell) projenin kurulacağı klasöre gidin (örn: Masaüstü).

```powershell
# 1. Projeyi İndirin
git clone https://github.com/glonorce/file-converter.git
cd file-converter

# 2. Sanal Ortamı (Virtual Environment) Kurun
python -m venv .venv

# 3. Gerekli Kütüphaneleri Yükleyin
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Harici Araçlar (Scoop ile)
Windows için **Scoop** kullanarak gerekli motorları tek komutla kurun:

```powershell
# Scoop yüklü değilse:
iwr -useb get.scoop.sh | iex

# Gerekli araçlar:
scoop bucket add extras
scoop install poppler tesseract ghostscript
```

> **Not:** Windows için optimize edilmiştir. Mac veya Linux kullanıcıları benzer araçları (Poppler, Tesseract) manuel kurarak (`brew install` veya `apt-get install`) kullanabilir.


## 💻 Kullanım

Kurulum bittikten sonra aracı her çalıştırmak istediğinizde şu iki adımı uygulayın. Sihirbaz sizi yönlendirecektir:

```powershell
# 1. Ortamı Hazırla (Her seferinde yapın)
.\.venv\Scripts\Activate.ps1

# 2. Seçenek: Klasik Terminal
python -m docuforge.main convert

# 3. Seçenek: Web Arayüzü 🌐
python -m docuforge.main web
```

Sihirbaz başladığında sizden **PDF Klasörü**, **Çıktı Yeri** ve **Gelişmiş Seçenekler** için onay isteyecektir.

### 🌐 Web Arayüzü Özellikleri
- **MD Görüntüleme:** İşlem biten dosyalarda 👁 butonuna tıklayarak Markdown'ı tarayıcıda görüntüleyin
- **HTML İndirme:** Görüntüleme sayfasında "HTML İndir" butonu ile stillenmiş HTML olarak kaydedin

> **İpucu:** Tüm mevcut komutları görmek için: `python -m docuforge.main --help`

## 🛠️ Ayarlar ve İpuçları

*   **Parallel Workers:** İşlemci çekirdeklerinize göre otomatik önerilir. (Manuel komutta varsayılan: 4).
*   **Gelişmiş Seçenekler (Varsayılan: KAPALI):**
    *   **OCR:** Sadece taranmış/resim şeklindeki sayfalar için açın (Otomatik devreye girer).
    *   **Tables:** Tabloları analiz eder.
    *   **Images:** Resimleri ayıklar (Açıksa klasör oluşturur, kapalıysa oluşturmaz).
    *   **Charts (Beta):** Grafikleri ayıklar (Düzensiz çalışabilir, deneyseldir).
    *   **Recursive Mode (CLI):** Alt klasörleri de tarar ve aynı klasör yapısını çıktıda oluşturur.
    *   **Header Sensitivity (0.6):** Sayfa numarası/kitap adı gibi tekrarlayan metinleri silme hassasiyetidir. (0.6 = %60 tekrar ediyorsa sil).
    *   **Removable Tags:** PDF'den silinmesini istediğiniz metinleri (filigran, watermark vb.) kalıcı listeye ekleyin. CLI veya Web arayüzünden yönetilebilir.

## 🧠 Geliştirme Yaklaşımı: AI Orkestrasyonu

Bu proje, sadece kod yazmak değil, modern **Sistem Mühendisliği** ve **Yapay Zeka Yönetimi (AI Orchestration)** becerilerinin bir ürünüdür.

*   **Mimari & Mantık (GÖKSEL ÖZKAN):** Projenin "Healer" (Dil düzeltme) algoritması, parçalama (chunking) stratejisi ve hata yönetimi mimarisi insan zekasıyla tasarlanmıştır.
*   **Kodlama (AI):** Tasarlanan bu karmaşık mimari, AI araçları yönlendirilerek kodlanmıştır.


### 👤 Proje Lideri
**GÖKSEL ÖZKAN**
- *System Architecture Design & AI Orchestration*
- *Project Lead*

## ⚠️ Bilinen Sınırlamalar

- **Karmaşık Tablolar:** 10+ sütunlu, birleştirilmiş hücreli veya renk kodlu (heat-map) tablolar tam doğrulukla çıkarılamayabilir.
- **Font Encoding Sorunları:** Bazı PDF'lerde Türkçe karakterler (ş, ğ, ı, ü, ö, ç) yanlış kodlanmış olabilir. Healer çoğu hatayı düzeltir. (Yeni Auto-OCR özelliği bu sorunu büyük ölçüde çözmektedir).
- **Öneri:** Kritik dokümanlar için çıktıyı manuel kontrol edin.

---

# EN DocuForge: Intelligent PDF to Markdown Engine

**DocuForge** is a high-performance tool designed to convert PDFs into clean, structured **Markdown**. It features a specialized **"Healer Engine"** that intelligently reinforces broken text (e.g., "t he" -> "the") based on the language context (TR/EN).

**Self-Healing Engine (Auto-OCR):** If the system detects broken font encoding (e.g. `P o w e r`), it automatically switches to OCR mode for that specific page, ensuring 100% accurate extraction.

## 💡 Why Markdown?

*   **For AI & LLMs:** Sending Markdown to models like GPT-4 ensures **100% context accuracy** compared to raw PDFs.
*   **For Version Control:** Track document changes line-by-line on GitHub.
*   **For Clarity:** Strips away layout artifacts, repetitive headers, and footers.
*   **🔒 100% Privacy:** All processing happens locally. No files are uploaded to the cloud.

## � Why DocuForge?

Cloud-based LLM services (ChatGPT, Claude, etc.) face these issues when processing PDFs:
- **Privacy:** Your documents are uploaded to third-party servers
- **Cost:** Per-page or per-token pricing
- **Limits:** Context window issues with large documents
- **Speed:** API rate limits and queue delays

**DocuForge solves these problems:**
- ✅ **100% Local Processing** - Your data never leaves your machine
- ✅ **Unlimited & Free** - Thousands of pages, zero cost
- ✅ **Parallel Processing** - Convert multiple PDFs simultaneously
- ✅ **Smart OCR** - Auto-detects and fixes broken fonts
- ✅ **Language Optimized** - Healer engine repairs Turkish characters (ş, ğ, ı, ü, ö, ç)

## �📦 Installation

### 1. Setup & Clone
Navigate to your desired folder first.

```powershell
# 1. Clone Repository
git clone https://github.com/glonorce/file-converter.git
cd file-converter

# 2. Create Virtual Environment
python -m venv .venv

# 3. Install Dimensions
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. System Engines (via Scoop)
Use **Scoop** to install core dependencies easily:

```powershell
# Install Scoop (if needed):
iwr -useb get.scoop.sh | iex

# Install Dependencies:
scoop bucket add extras
scoop install poppler tesseract ghostscript
```

> **Note:** Optimized for Windows. Mac or Linux users can run the tool by manually installing dependencies (Poppler, Tesseract) using `brew` or `apt-get`.


## 💻 Usage

Whenever you want to run the tool, follow this simple workflow. The interactive wizard will handle the rest.

```powershell
# 1. Activate Environment
.\.venv\Scripts\Activate.ps1

# Option 2: Classic Terminal
python -m docuforge.main convert

# Option 3: Web Interface 🌐
python -m docuforge.main web
```

The wizard will ask for your **Input Directory**, **Output Path**, and **Advanced Options**.

### 🌐 Web Interface Features
- **MD Viewer:** Click the 👁 button on completed files to preview Markdown in browser
- **HTML Download:** Save as styled HTML using the "HTML Download" button in the preview

> **Tip:** To see all available commands: `python -m docuforge.main --help`

## 🛠️ Settings & Tips

*   **Parallel Workers:** Automatically optimized based on your CPU cores. (CLI default: 4).
*   **Advanced Options (Default: OFF):**
    *   **OCR:** Enables text recognition for scanned pages.
    *   **Tables:** Extracts data tables.
    *   **Images:** Extracts embedded images (Creates folder only if found).
    *   **Charts (Beta):** Extracts charts/graphs (Experimental, may be irregular).
    *   **Recursive Mode (CLI):** Scans subdirectories and preserves the folder structure in output.
    *   **Header Sensitivity (0.6):** Controls removal of repeated text (headers/footers). 0.6 means "remove if present on 60% of pages".
    *   **Removable Tags:** Add text patterns (watermarks, etc.) to a persistent blocklist. Manage via CLI or Web UI.

## 🧠 Development Philosophy: AI Orchestration

This project demonstrates the power of **Prompt Engineering** and **System Architecture**. It is not just "AI-generated code" but a human-architected system.

*   **Architecture & Logic:** The "Healer" algorithms, chunking strategies, and robust error handling were designed by the human engineer.
*   **Implementation:** The code execution was handled by AI under strict architectural guidance.

## ⚠️ Known Limitations

- **Complex Tables:** Tables with 10+ columns, merged cells, or color-coded (heat-map) styling may not extract with 100% accuracy.
- **Font Encoding Issues:** Some PDFs have improperly encoded Turkish characters (ş, ğ, ı, ü, ö, ç). The Healer corrects most errors. (This is now largely solved by the new Auto-OCR feature).
- **Recommendation:** Manually review the printout for critical documents.

## 👤 Author / Yazar

**GÖKSEL ÖZKAN**
- *System Architecture Design & AI Orchestration*
- *Project Lead*
