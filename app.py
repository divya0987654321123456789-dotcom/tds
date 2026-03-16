"""
AI-Powered TDS Generator Web Application
Streamlit-based UI for converting vendor spec sheets to IKIO branded TDS
"""
import streamlit as st
import tempfile
import os
from pathlib import Path
from datetime import datetime
import json
import base64

# Page configuration
st.set_page_config(
    page_title="IKIO TDS Generator",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for IKIO branding
st.markdown("""
<style>
    /* Main header styling */
    .main-header {
        background: linear-gradient(135deg, #003366 0%, #0066CC 100%);
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        color: white;
    }
    
    .main-header h1 {
        color: white;
        margin: 0;
        font-size: 2.5rem;
    }
    
    .main-header p {
        color: #E0E0E0;
        margin: 0.5rem 0 0 0;
    }
    
    /* Card styling */
    .info-card {
        background: #F8F9FA;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #003366;
        margin: 1rem 0;
    }
    
    /* Status indicators */
    .status-success {
        background: #D4EDDA;
        border-left-color: #28A745;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    
    .status-error {
        background: #F8D7DA;
        border-left-color: #DC3545;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    
    .status-info {
        background: #D1ECF1;
        border-left-color: #17A2B8;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(135deg, #003366 0%, #0066CC 100%);
        color: white;
        border: none;
        padding: 0.75rem 2rem;
        font-size: 1rem;
        border-radius: 5px;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        background: linear-gradient(135deg, #002244 0%, #0055AA 100%);
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    
    /* File uploader */
    .uploadedFile {
        border: 2px dashed #003366;
        border-radius: 10px;
    }
    
    /* Progress section */
    .progress-step {
        display: flex;
        align-items: center;
        padding: 0.5rem;
        margin: 0.25rem 0;
    }
    
    .progress-step.completed {
        color: #28A745;
    }
    
    .progress-step.in-progress {
        color: #0066CC;
        font-weight: bold;
    }
    
    /* Spec preview */
    .spec-preview {
        background: white;
        border: 1px solid #DEE2E6;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    .spec-label {
        color: #666;
        font-size: 0.85rem;
    }
    
    .spec-value {
        color: #003366;
        font-weight: bold;
        font-size: 1rem;
    }
    
    /* Sidebar styling */
    .sidebar .sidebar-content {
        background: #F8F9FA;
    }
    
    /* Hide streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


def load_processor_modules():
    """Dynamically load processor modules"""
    try:
        from ai_vision_processor import process_vendor_spec, VendorSpecData
        from data_mapper import map_vendor_to_tds, IKIOTDSData, TDSSpecificationTable
        from pdf_generator import generate_tds
        from config import (
            OUTPUT_DIR, AI_PROVIDER, 
            GROQ_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY,
            get_active_provider_info
        )
        
        # Try to load enhanced processor (docTR-based)
        try:
            from enhanced_processor import process_enhanced
            enhanced_available = True
        except ImportError:
            process_enhanced = None
            enhanced_available = False
        
        return True, {
            'process_vendor_spec': process_vendor_spec,
            'process_enhanced': process_enhanced,
            'enhanced_available': enhanced_available,
            'map_vendor_to_tds': map_vendor_to_tds,
            'generate_tds': generate_tds,
            'IKIOTDSData': IKIOTDSData,
            'TDSSpecificationTable': TDSSpecificationTable,
            'OUTPUT_DIR': OUTPUT_DIR,
            'AI_PROVIDER': AI_PROVIDER,
            'GROQ_API_KEY': GROQ_API_KEY,
            'GEMINI_API_KEY': GEMINI_API_KEY,
            'OPENAI_API_KEY': OPENAI_API_KEY,
            'get_active_provider_info': get_active_provider_info
        }
    except ImportError as e:
        return False, str(e)


def main():
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>💡 IKIO TDS Generator</h1>
        <p>AI-Powered Technical Data Sheet Converter</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Load modules
    modules_loaded, modules = load_processor_modules()
    
    if not modules_loaded:
        st.error(f"Failed to load modules: {modules}")
        st.info("Please ensure all dependencies are installed: `pip install -r requirements.txt`")
        return
    
    # Sidebar
    with st.sidebar:
        st.image("https://via.placeholder.com/200x60/003366/FFFFFF?text=IKIO+LED", use_container_width=True)
        st.markdown("---")
        
        st.header("🆓 AI Provider (FREE!)")
        
        # Provider selection
        provider_options = {
            "groq": "Groq (Fast, FREE)",
            "gemini": "Google Gemini (Vision, FREE)", 
            "ollama": "Ollama (Local, FREE)",
            "openai": "OpenAI (Paid)"
        }
        
        selected_provider = st.selectbox(
            "Select Provider",
            options=list(provider_options.keys()),
            format_func=lambda x: provider_options[x],
            index=list(provider_options.keys()).index(modules['AI_PROVIDER'])
        )
        
        # API Key based on provider
        api_key = ""
        if selected_provider == "groq":
            api_key = st.text_input(
                "Groq API Key",
                value=modules['GROQ_API_KEY'] or "",
                type="password",
                help="Get FREE key at console.groq.com"
            )
            if not api_key:
                st.info("🔗 [Get FREE Groq Key](https://console.groq.com/keys)")
        elif selected_provider == "gemini":
            api_key = st.text_input(
                "Gemini API Key",
                value=modules['GEMINI_API_KEY'] or "",
                type="password",
                help="Get FREE key at aistudio.google.com"
            )
            if not api_key:
                st.info("🔗 [Get FREE Gemini Key](https://aistudio.google.com/apikey)")
        elif selected_provider == "ollama":
            st.success("✓ No API key needed!")
            st.info("Install Ollama from ollama.ai")
            api_key = "local"
        elif selected_provider == "openai":
            api_key = st.text_input(
                "OpenAI API Key",
                value=modules['OPENAI_API_KEY'] or "",
                type="password"
            )
        
        if api_key or selected_provider == "ollama":
            st.success("✓ Ready to process!")
        else:
            st.warning("⚠️ API key required")
    
    # Main content area
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📄 Upload Vendor Spec Sheet")
        
        uploaded_file = st.file_uploader(
            "Drop your vendor PDF here",
            type=['pdf'],
            help="Upload the vendor specification sheet to convert"
        )
        
        if uploaded_file:
            st.markdown(f"""
            <div class="info-card">
                <strong>📎 File:</strong> {uploaded_file.name}<br>
                <strong>📏 Size:</strong> {uploaded_file.size / 1024:.1f} KB
            </div>
            """, unsafe_allow_html=True)
    
    with col2:
        st.header("🎯 Output Options")
        
        product_name_override = st.text_input(
            "Product Name (optional)",
            placeholder="Leave empty to auto-detect",
            help="Override the auto-detected product name"
        )
        
        include_images = st.checkbox("Include dimension diagrams", value=True)
        include_ordering = st.checkbox("Include ordering information", value=True)
        
        # Processing mode selection
        st.markdown("---")
        st.subheader("🧠 Processing Mode")
        
        if modules['enhanced_available']:
            processing_mode = st.radio(
                "Select extraction method:",
                options=["enhanced", "standard"],
                format_func=lambda x: {
                    "enhanced": "🚀 Enhanced (DocTR + AI) - Recommended",
                    "standard": "📄 Standard (AI Only)"
                }[x],
                help="Enhanced mode uses deep learning OCR for better accuracy"
            )
            if processing_mode == "enhanced":
                st.success("✅ Using DocTR deep learning for OCR + AI for semantic analysis")
        else:
            processing_mode = "standard"
            st.info("💡 Install python-doctr for enhanced processing: pip install python-doctr[torch]")
    
    # Process button
    st.markdown("---")
    
    if uploaded_file and (api_key or selected_provider == "ollama"):
        if st.button("🧠 Analyze & Prefill Form", use_container_width=True):
            analyze_pdf(uploaded_file, api_key if api_key != "local" else None, modules, 
                       product_name_override, selected_provider, processing_mode)
    elif uploaded_file:
        st.warning(f"Please enter your {selected_provider.title()} API key to proceed")
    else:
        st.info("Upload a vendor spec sheet PDF to get started")
    
    # Prefilled form from AI extraction
    if "tds_data" in st.session_state:
        st.markdown("---")
        st.header("📋 Review & Edit (Prefilled by AI)")
        render_prefill_form(modules)

    # Show recent conversions
    show_recent_conversions(modules['OUTPUT_DIR'])


def analyze_pdf(uploaded_file, api_key, modules, product_name_override, provider="groq", processing_mode="standard"):
    """Analyze the uploaded PDF and prefill the form"""
    
    progress_container = st.container()
    
    with progress_container:
        mode_label = "Enhanced (DocTR + AI)" if processing_mode == "enhanced" else provider.upper()
        st.markdown(f"### 🔄 Processing with {mode_label}...")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Step 1: Save uploaded file temporarily
        status_text.text("📥 Saving uploaded file...")
        progress_bar.progress(10)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name
        
        try:
            # Step 2: Extract data using selected mode
            if processing_mode == "enhanced" and modules['process_enhanced']:
                status_text.text("🧠 Deep Learning OCR + AI Analysis...")
                progress_bar.progress(20)
                
                # Use enhanced processor (DocTR + AI)
                vendor_data = modules['process_enhanced'](tmp_path, provider=provider, api_key=api_key)
                progress_bar.progress(50)
            else:
                status_text.text(f"🤖 {provider.upper()} analyzing PDF...")
                progress_bar.progress(30)
                
                # Use standard AI-only processor
                vendor_data = modules['process_vendor_spec'](tmp_path, api_key=api_key, provider=provider)
            
            # Step 3: Map to IKIO format
            status_text.text("🔄 Converting to IKIO format...")
            progress_bar.progress(60)
            
            tds_data = modules['map_vendor_to_tds'](vendor_data)
            
            # Apply overrides
            if product_name_override:
                tds_data.product_name = product_name_override
            
            # Step 4: Save prefilled data into session
            progress_bar.progress(90)
            st.session_state["tds_data"] = tds_data

            progress_bar.progress(100)
            status_text.text("✅ Analysis complete! Review the prefilled form below.")
        
        except Exception as e:
            st.markdown(f"""
            <div class="status-error">
                <h4>❌ Error Processing PDF</h4>
                <p>{str(e)}</p>
            </div>
            """, unsafe_allow_html=True)
            
            st.exception(e)
        
        finally:
            # Cleanup temp file
            try:
                os.unlink(tmp_path)
            except:
                pass


def render_prefill_form(modules):
    """Render the prefilled form and generate PDF on submit."""
    tds_data = st.session_state["tds_data"]

    product_name = st.text_input("Product Name", value=tds_data.product_name or "")
    product_category = st.text_input("Product Category", value=tds_data.product_category or "")
    model_number = st.text_input("Model Number / SKU", value=tds_data.model_number or "")
    product_description = st.text_area("Product Description", value=tds_data.product_description or "", height=120)

    features_text = st.text_area(
        "Features (one per line)",
        value="\n".join(tds_data.features or []),
        height=120
    )
    applications_text = st.text_area(
        "Applications (one per line)",
        value="\n".join(tds_data.applications or []),
        height=100
    )
    certifications_text = st.text_area(
        "Certifications (comma separated)",
        value=", ".join(tds_data.certifications or []),
        height=60
    )
    warranty = st.text_input("Warranty", value=tds_data.warranty or "")

    st.markdown("**Key Specs (optional)**")
    col_a, col_b = st.columns(2)
    with col_a:
        wattage = st.text_input("Power / Wattage", value=tds_data.wattage or "")
        input_voltage = st.text_input("Voltage", value=tds_data.input_voltage or "")
        cct = st.text_input("CCT", value=tds_data.cct or "")
        cri = st.text_input("CRI", value=tds_data.cri or "")
    with col_b:
        lumens = st.text_input("Lumens", value=tds_data.lumens or "")
        efficacy = st.text_input("Efficacy", value=tds_data.efficacy or "")
        ip_rating = st.text_input("IP Rating", value=tds_data.ip_rating or "")
        ik_rating = st.text_input("IK Rating", value=tds_data.ik_rating or "")

    if st.button("📄 Generate PDF from Form", use_container_width=True):
        updated = modules['IKIOTDSData'](
            product_name=product_name,
            product_category=product_category,
            model_number=model_number,
            product_description=product_description,
            features=[f.strip() for f in features_text.splitlines() if f.strip()],
            applications=[a.strip() for a in applications_text.splitlines() if a.strip()],
            certifications=[c.strip() for c in certifications_text.split(",") if c.strip()],
            warranty=warranty,
            wattage=wattage,
            input_voltage=input_voltage,
            cct=cct,
            cri=cri,
            lumens=lumens,
            efficacy=efficacy,
            ip_rating=ip_rating,
            ik_rating=ik_rating,
            spec_tables=tds_data.spec_tables,
            extracted_images=tds_data.extracted_images,
            dimension_diagram_data=tds_data.dimension_diagram_data,
            beam_angle_diagrams=tds_data.beam_angle_diagrams,
            accessories=tds_data.accessories,
            accessories_sold_separately=tds_data.accessories_sold_separately,
            accessories_included=tds_data.accessories_included,
            notes=tds_data.notes
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c for c in updated.product_name if c.isalnum() or c in " -_").strip()
        safe_name = safe_name.replace(" ", "_")[:30]
        output_filename = f"TDS_{safe_name}_{timestamp}.pdf"
        output_path = str(modules['OUTPUT_DIR'] / output_filename)

        result_path = modules['generate_tds'](updated, output_path)

        st.markdown("""
        <div class="status-success">
            <h4>✅ TDS Generated Successfully!</h4>
        </div>
        """, unsafe_allow_html=True)

        with open(result_path, 'rb') as f:
            pdf_bytes = f.read()

        st.download_button(
            label="📥 Download TDS PDF",
            data=pdf_bytes,
            file_name=output_filename,
            mime="application/pdf",
            use_container_width=True
        )


def show_recent_conversions(output_dir):
    """Show recently generated TDS files"""
    st.markdown("---")
    st.header("📁 Recent Conversions")
    
    try:
        pdf_files = sorted(
            Path(output_dir).glob("*.pdf"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )[:5]
        
        if pdf_files:
            for pdf_file in pdf_files:
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.text(pdf_file.name)
                with col2:
                    mod_time = datetime.fromtimestamp(pdf_file.stat().st_mtime)
                    st.text(mod_time.strftime("%Y-%m-%d %H:%M"))
                with col3:
                    with open(pdf_file, 'rb') as f:
                        st.download_button(
                            "⬇️",
                            data=f.read(),
                            file_name=pdf_file.name,
                            mime="application/pdf",
                            key=str(pdf_file)
                        )
        else:
            st.info("No recent conversions found")
    except Exception as e:
        st.error(f"Could not load recent files: {e}")


if __name__ == "__main__":
    main()

