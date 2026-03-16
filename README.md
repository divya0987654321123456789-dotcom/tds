# AI-Powered TDS Spec Sheet Generator

🆓 **Automatically convert vendor specification sheets into IKIO company-branded Technical Data Sheets using FREE AI providers!**

## 🌟 Features

- **FREE AI Options**: Groq, Google Gemini, or Ollama (local) - no paid API required!
- **AI Vision Extraction**: Intelligently reads and understands vendor PDFs
- **Smart Data Mapping**: Automatically categorizes and standardizes specifications
- **IKIO Branding**: Generates professional PDFs matching the Exiona template format
- **Multi-Variant Support**: Handles products with multiple wattages (480W/600W, etc.)
- **Web Interface**: Easy drag-and-drop conversion via Streamlit app
- **Batch Processing**: Convert multiple vendor specs at once

## 🆓 FREE AI Providers

| Provider | Vision | Speed | Setup |
|----------|--------|-------|-------|
| **Groq** | ❌ | ⚡ Fastest | [Get FREE Key](https://console.groq.com/keys) |
| **Gemini** | ✅ | 🚀 Fast | [Get FREE Key](https://aistudio.google.com/apikey) |
| **Ollama** | ✅ | 💻 Local | [Install](https://ollama.ai) - No key needed! |

## 📋 Prerequisites

- Python 3.8 or higher
- One of the FREE AI providers configured

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd mycode
pip install -r requirements.txt
```

### 2. Configure AI Provider

Copy `env.example` to `.env` and add your FREE API key:

```bash
# For Groq (fastest, text-only)
AI_PROVIDER=groq
GROQ_API_KEY=gsk_your_free_key_here

# OR for Gemini (with vision support)
AI_PROVIDER=gemini
GEMINI_API_KEY=your_free_gemini_key_here

# OR for Ollama (local, no key needed)
AI_PROVIDER=ollama
# Then run: ollama pull llama3.2 && ollama pull llava
```

### 3. Run the Generator

**Option A: Web Interface (Recommended)**
```bash
python main.py webapp
```
Opens a browser-based interface for easy PDF upload and conversion.

**Option B: Command Line**
```bash
python main.py convert vendor_spec.pdf
```

**Option C: Demo Mode**
```bash
python main.py demo
```
Generates a sample Exiona Stadium Flood Light TDS.

## 💻 Usage Examples

### Convert with Groq (Fastest)
```bash
python main.py convert "vendor_spec.pdf" --provider groq
```

### Convert with Gemini (Vision Support)
```bash
python main.py convert "vendor_spec.pdf" --provider gemini
```

### Convert with Ollama (Local, Free)
```bash
# First, make sure Ollama is running
ollama serve

# Then convert
python main.py convert "vendor_spec.pdf" --provider ollama
```

### Batch Convert Directory
```bash
python main.py batch "vendor_pdfs/" --provider groq
```

### View Configuration
```bash
python main.py config
```

## 🏗️ Architecture

```
mycode/
├── main.py                 # CLI application entry point
├── app.py                  # Streamlit web interface
├── config.py               # Configuration and branding settings
├── ai_client.py            # FREE AI provider clients (Groq, Gemini, Ollama)
├── ai_vision_processor.py  # PDF extraction with AI
├── data_mapper.py          # Vendor → IKIO data transformation
├── pdf_generator.py        # TDS PDF generation (ReportLab)
├── requirements.txt        # Python dependencies
├── env.example             # Configuration template
├── output/                 # Generated TDS files
└── vendor_input/           # Upload vendor specs here
```

## 📄 TDS Template Format

The generated TDS matches the Exiona template with:

### Page 1: Product Overview
- Product name and series
- Product description
- Key features (bullet points)
- Application areas
- Dimension diagrams
- Mounting options
- Packaging information

### Page 2: Technical Specifications
- Full specification table with multiple variants
- Electrical specifications
- Optical specifications
- Environmental ratings
- Ordering information with part number structure

### Page 3: Additional Information
- Beam angle diagrams
- Accessories (sold separately)
- Wiring diagrams
- Certifications

## 🎨 Customization

### Company Branding

Edit `config.py` to customize:

```python
COMPANY_CONFIG = {
    "name": "IKIO LED LIGHTING",
    "website": "www.kioledlighting.com",
    "email": "info@kioledlighting.com",
    "colors": {
        "primary": "#003366",
        "accent": "#0066CC",
    }
}
```

## 📊 Supported Specification Categories

| Category | Examples |
|----------|----------|
| **Electrical** | Power, Voltage, Power Factor, Surge Protection, THD |
| **Optical** | Lumens, Efficacy, CCT, CRI, Beam Angle |
| **Physical** | Dimensions, Weight, Housing Material, Lens |
| **Environmental** | IP Rating, IK Rating, Operating Temperature |
| **Lifespan** | Average Life Hours, Warranty |
| **Components** | LED Chip, Driver, Power Supply |

## 🔧 Troubleshooting

### "No AI provider configured"
Configure one of the FREE options in your `.env` file:
- Get FREE Groq key: https://console.groq.com/keys
- Get FREE Gemini key: https://aistudio.google.com/apikey
- Or install Ollama: https://ollama.ai

### "Ollama not running"
```bash
# Start Ollama server
ollama serve

# Pull required models
ollama pull llama3.2
ollama pull llava  # For vision
```

### "Groq doesn't support vision"
Groq is text-only. For best results with vendor PDFs containing images/diagrams:
- Use `--provider gemini` for Gemini with vision
- Or use `--provider ollama` for local LLaVA vision

### "Missing dependencies"
```bash
pip install -r requirements.txt
```

## 📈 Workflow

```
┌─────────────────┐
│ Vendor PDF      │
│ (Spec Sheet)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ FREE AI         │ ← Groq/Gemini/Ollama
│ Extraction      │   analyzes PDF content
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Data Mapper     │ ← Standardizes specs to IKIO format
│ (Normalization) │   categorizes, cleans, validates
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ PDF Generator   │ ← Creates branded TDS document
│ (ReportLab)     │   header, tables, diagrams, footer
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ IKIO TDS PDF    │
│ (Output)        │
└─────────────────┘
```

## 🤝 Support

For issues or feature requests, contact the development team.

## 📄 License

Internal use only - IKIO LED Lighting

---

Made with ❤️ for IKIO LED Lighting | Powered by FREE AI! 🆓
