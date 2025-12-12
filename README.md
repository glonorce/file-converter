# DocuForge: Intelligent PDF to Markdown Converter
*(Türkçe açıklama aşağıdadır / Scroll down for English)*

---

# 🇹🇷 DocuForge: Akıllı PDF Dönüştürücü

**DocuForge**, PDF belgelerini modern ve yapay zeka dostu **Markdown** formatına dönüştüren, yüksek performanslı bir araçtır. Özellikle Türkçe ve İngilizce için geliştirdiğimiz **"Akıllı Dil Uzmanı" (Healer Engine)** sayesinde, PDF'lerdeki bozuk metinleri (örn: "v e" -> "ve", "t he" -> "the") otomatik olarak onarır.

## 💡 Neden Markdown?

*   **Yapay Zeka (AI) İçin:** ChatGPT veya Claude gibi modellere PDF yerine Markdown verirseniz, dokümanı **%100 doğrulukla** anlarlar.
*   **GitHub İçin:** Değişiklikleri satır satır takip edebilirsiniz.
*   **Temiz Okuma:** Sayfa numaraları ve gereksiz boşluklardan arınmış, saf bilgi içerir.

## 📦 Kurulum (Adım Adım)

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

## 💻 Kullanım

Kurulum bittikten sonra aracı her çalıştırmak istediğinizde şu iki adımı uygulayın. Sihirbaz sizi yönlendirecektir:

```powershell
# 1. Ortamı Hazırla (Her seferinde yapın)
.\.venv\Scripts\Activate.ps1

# 2. Aracı Başlat
python -m docuforge.main
```

Sihirbaz başladığında sizden **PDF Klasörü**, **Çıktı Yeri** ve **Gelişmiş Seçenekler** için onay isteyecektir.

## 🛠️ Ayarlar ve İpuçları

*   **Parallel Workers (Varsayılan: 4):** Bilgisayarınızın aynı anda kaç dosya işleyeceğini belirler. Güçlü PC'lerde 8 yapılabilir.
*   **Gelişmiş Seçenekler (Varsayılan: KAPALI):**
    *   **OCR:** Sadece taranmış/resim şeklindeki sayfalar için açın (Otomatik devreye girer).
    *   **Tables:** Tabloları analiz eder.
    *   **Images:** Resimleri ayıklar (Açıksa klasör oluşturur, kapalıysa oluşturmaz).
    *   **Header Sensitivity (0.6):** Sayfa numarası/kitap adı gibi tekrarlayan metinleri silme hassasiyetidir. (0.6 = %60 tekrar ediyorsa sil).

## 🧠 Geliştirme Yaklaşımı: AI Orkestrasyonu

Bu proje, sadece kod yazmak değil, modern **Sistem Mühendisliği** ve **Yapay Zeka Yönetimi (AI Orchestration)** becerilerinin bir ürünüdür.

*   **Mimari & Mantık (GÖKSEL ÖZKAN):** Projenin "Healer" (Dil düzeltme) algoritması, parçalama (chunking) stratejisi ve hata yönetimi mimarisi insan zekasıyla tasarlanmıştır.
*   **Kodlama (AI):** Tasarlanan bu karmaşık mimari, AI araçları yönlendirilerek kodlanmıştır.

### 👤 Proje Lideri
**GÖKSEL ÖZKAN**
- *System Architecture Design & AI Orchestration*
- *Project Lead*

---

# 🇬🇧 DocuForge: Intelligent PDF to Markdown Engine

**DocuForge** is a high-performance tool designed to convert PDFs into clean, structured **Markdown**. It features a specialized **"Healer Engine"** that intelligently reinforces broken text (e.g., "t he" -> "the") based on the language context (TR/EN).

## 💡 Why Markdown?

*   **For AI & LLMs:** Sending Markdown to models like GPT-4 ensures **100% context accuracy** compared to raw PDFs.
*   **For Version Control:** Track document changes line-by-line on GitHub.
*   **For Clarity:** Strips away layout artifacts, headers, and footers.

## 📦 Installation

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

## 💻 Usage

Whenever you want to run the tool, follow this simple workflow. The interactive wizard will handle the rest.

```powershell
# 1. Activate Environment
.\.venv\Scripts\Activate.ps1

# 2. Start Tool
python -m docuforge.main
```

The wizard will ask for your **Input Directory**, **Output Path**, and **Advanced Options**.

## 🛠️ Settings & Tips

*   **Parallel Workers (Default: 4):** How many files to process at once. Increase to 8+ on powerful CPUs.
*   **Advanced Options (Default: OFF):**
    *   **OCR:** Enables text recognition for scanned pages.
    *   **Tables:** Extracts data tables.
    *   **Images:** Extracts embedded images (Creates folder only if found).
    *   **Header Sensitivity (0.6):** Controls removal of repeated text (headers/footers). 0.6 means "remove if present on 60% of pages".

## 🧠 Development Philosophy: AI Orchestration

This project demonstrates the power of **Prompt Engineering** and **System Architecture**. It is not just "AI-generated code" but a human-architected system.

*   **Architecture & Logic:** The "Healer" algorithms, chunking strategies, and robust error handling were designed by the human engineer.
*   **Implementation:** The code execution was handled by AI under strict architectural guidance.

## 👤 Author / Yazar

**GÖKSEL ÖZKAN**
- *System Architecture Design & AI Orchestration*
- *Project Lead*
