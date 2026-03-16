"""
AI-Powered TDS Spec Sheet Generator - Main Application
Converts vendor specifications into IKIO company-branded Technical Data Sheets

Usage:
    python main.py convert vendor_spec.pdf [output.pdf]
    python main.py webapp
    python main.py demo
    python main.py --help
"""
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import asdict

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich import print as rprint

from config import (
    OPENAI_API_KEY, OUTPUT_DIR, COMPANY_CONFIG,
    AI_PROVIDER, GROQ_API_KEY, GEMINI_API_KEY,
    get_active_provider_info
)

# Initialize
app = typer.Typer(
    name="tds-generator",
    help="AI-Powered TDS Generator - Convert vendor specs to IKIO branded TDS",
    add_completion=False
)
console = Console()


def print_banner():
    """Print application banner"""
    banner = """
╔══════════════════════════════════════════════════════════════════╗
║           AI-POWERED TDS SPEC SHEET GENERATOR                    ║
║          Convert Vendor Specs to IKIO Company Template           ║
║                                                                  ║
║   🆓 FREE AI: Groq | Gemini | Ollama | 🎨 IKIO Branding          ║
╚══════════════════════════════════════════════════════════════════╝
    """
    console.print(Panel(banner, style="bold blue"))


def show_extracted_preview(tds_data):
    """Display a preview of extracted specifications"""
    table = Table(title="Extracted Specifications Preview", show_header=True, header_style="bold cyan")
    table.add_column("Category", style="dim", width=20)
    table.add_column("Details", width=50)
    
    table.add_row("Product Name", tds_data.product_name)
    table.add_row("Series", tds_data.product_series or "Not found")
    
    # Features
    features_preview = ", ".join(tds_data.features[:3]) + "..." if len(tds_data.features) > 3 else ", ".join(tds_data.features)
    table.add_row("Features", features_preview or "Not found")
    
    # Applications
    apps_preview = ", ".join(tds_data.applications[:3]) + "..." if len(tds_data.applications) > 3 else ", ".join(tds_data.applications)
    table.add_row("Applications", apps_preview or "Not found")
    
    # Specs summary
    if tds_data.spec_tables:
        specs_count = sum(len(t.rows) for t in tds_data.spec_tables)
        table.add_row("Specifications", f"{specs_count} items extracted")
    
    # Certifications
    table.add_row("Certifications", ", ".join(tds_data.certifications[:5]) or "None found")
    
    console.print(table)


@app.command()
def convert(
    input_pdf: str = typer.Argument(
        ...,
        help="Path to the vendor specification PDF"
    ),
    output_pdf: Optional[str] = typer.Option(
        None,
        "--output", "-o",
        help="Output PDF path (default: auto-generated in output folder)"
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key", "-k",
        help="API key for the AI provider"
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider", "-p",
        help="AI provider: groq, gemini, ollama, openai"
    ),
    preview: bool = typer.Option(
        True,
        "--preview/--no-preview",
        help="Show preview of extracted data"
    ),
    save_json: bool = typer.Option(
        False,
        "--save-json",
        help="Save extracted data as JSON file"
    )
):
    """
    Convert a vendor specification PDF to IKIO branded TDS.
    
    Uses FREE AI providers: Groq, Google Gemini, or Ollama (local).
    
    Examples:
        python main.py convert vendor_spec.pdf
        python main.py convert vendor_spec.pdf --provider gemini
        python main.py convert vendor_spec.pdf -o my_tds.pdf
    """
    print_banner()
    
    # Validate input
    input_path = Path(input_pdf)
    if not input_path.exists():
        console.print(f"[red]Error: Input file not found: {input_pdf}[/red]")
        raise typer.Exit(1)
    
    # Setup output path
    if output_pdf:
        output_path = Path(output_pdf)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_name = f"TDS_{input_path.stem}_{timestamp}.pdf"
        output_path = OUTPUT_DIR / output_name
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Get provider info
    provider_info = get_active_provider_info()
    effective_provider = provider or AI_PROVIDER
    
    console.print(f"\n[cyan]Input:[/cyan] {input_path.name}")
    console.print(f"[cyan]Output:[/cyan] {output_path}")
    console.print(f"[cyan]AI Provider:[/cyan] {effective_provider.upper()} {'(FREE!)' if provider_info['free'] else '(Paid)'}")
    console.print(f"[cyan]Vision Support:[/cyan] {'Yes' if provider_info['vision'] else 'No (text-only)'}")
    console.print()
    
    # Import processors
    from ai_vision_processor import process_vendor_spec
    from data_mapper import map_vendor_to_tds
    from pdf_generator import generate_tds
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        
        # Step 1: Extract from PDF using AI
        task1 = progress.add_task(f"[cyan]Extracting with {effective_provider.upper()}...", total=100)
        
        try:
            vendor_data = process_vendor_spec(str(input_path), api_key=api_key, provider=effective_provider)
            progress.update(task1, completed=100)
        except Exception as e:
            console.print(f"[red]Error extracting PDF: {e}[/red]")
            console.print("\n[yellow]Troubleshooting:[/yellow]")
            console.print("  • Groq: Get FREE key at https://console.groq.com/keys")
            console.print("  • Gemini: Get FREE key at https://aistudio.google.com/apikey")
            console.print("  • Ollama: Install from https://ollama.ai (no key needed)")
            raise typer.Exit(1)
        
        # Step 2: Map to IKIO format
        task2 = progress.add_task("[cyan]Mapping to IKIO format...", total=100)
        
        try:
            tds_data = map_vendor_to_tds(vendor_data)
            progress.update(task2, completed=100)
        except Exception as e:
            console.print(f"[red]Error mapping specifications: {e}[/red]")
            raise typer.Exit(1)
        
        # Step 3: Generate TDS PDF
        task3 = progress.add_task("[cyan]Generating TDS PDF...", total=100)
        
        try:
            result_path = generate_tds(tds_data, str(output_path))
            progress.update(task3, completed=100)
        except Exception as e:
            console.print(f"[red]Error generating PDF: {e}[/red]")
            raise typer.Exit(1)
    
    # Show preview if requested
    if preview:
        console.print()
        show_extracted_preview(tds_data)
    
    # Save JSON if requested
    if save_json:
        json_path = output_path.with_suffix('.json')
        
        # Convert to serializable dict
        def make_serializable(obj):
            if hasattr(obj, '__dict__'):
                return {k: make_serializable(v) for k, v in obj.__dict__.items() 
                       if not k.startswith('_') and not callable(v)}
            elif isinstance(obj, list):
                return [make_serializable(i) for i in obj]
            elif isinstance(obj, dict):
                return {k: make_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, bytes):
                return f"<bytes: {len(obj)} bytes>"
            else:
                return obj
        
        with open(json_path, 'w') as f:
            json.dump(make_serializable(tds_data), f, indent=2, default=str)
        console.print(f"\n[green]JSON data saved:[/green] {json_path}")
    
    # Success message
    console.print(Panel(
        f"[bold green]✓ TDS Generated Successfully![/bold green]\n\n"
        f"Output: [cyan]{result_path}[/cyan]\n"
        f"Product: [yellow]{tds_data.product_name}[/yellow]\n"
        f"Pages: {tds_data.page_count}\n"
        f"Specs: {sum(len(t.rows) for t in tds_data.spec_tables)} items",
        title="Complete",
        border_style="green"
    ))
    
    return result_path


@app.command()
def webapp():
    """
    Launch the web interface for TDS generation.
    
    Opens a Streamlit web app in your browser for easy drag-and-drop
    conversion of vendor spec sheets.
    """
    print_banner()
    console.print("[cyan]Starting web application...[/cyan]")
    console.print("[yellow]Opening browser at http://localhost:8501[/yellow]")
    
    import subprocess
    subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"])


@app.command()
def batch(
    input_dir: str = typer.Argument(..., help="Directory containing vendor PDFs"),
    output_dir: Optional[str] = typer.Option(
        None,
        "--output-dir", "-o",
        help="Output directory for generated TDS files"
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key", "-k",
        help="API key for AI provider"
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider", "-p",
        help="AI provider: groq, gemini, ollama, openai"
    )
):
    """
    Process multiple vendor PDFs in batch mode.
    
    Converts all PDF files in the input directory to IKIO branded TDS.
    Uses FREE AI providers: Groq, Gemini, or Ollama.
    """
    print_banner()
    
    input_path = Path(input_dir)
    if not input_path.exists() or not input_path.is_dir():
        console.print(f"[red]Error: Directory not found: {input_dir}[/red]")
        raise typer.Exit(1)
    
    pdf_files = list(input_path.glob("*.pdf"))
    if not pdf_files:
        console.print(f"[yellow]No PDF files found in {input_dir}[/yellow]")
        raise typer.Exit(0)
    
    output_path = Path(output_dir) if output_dir else OUTPUT_DIR / "batch"
    output_path.mkdir(parents=True, exist_ok=True)
    
    effective_provider = provider or AI_PROVIDER
    
    console.print(f"[cyan]Found {len(pdf_files)} PDF files to process[/cyan]")
    console.print(f"[cyan]Using AI Provider: {effective_provider.upper()}[/cyan]\n")
    
    # Import processors
    from ai_vision_processor import process_vendor_spec
    from data_mapper import map_vendor_to_tds
    from pdf_generator import generate_tds
    
    results = []
    
    for i, pdf_file in enumerate(pdf_files, 1):
        console.print(f"[{i}/{len(pdf_files)}] Processing: {pdf_file.name}")
        
        try:
            # Extract
            vendor_data = process_vendor_spec(str(pdf_file), api_key=api_key, provider=effective_provider)
            
            # Map
            tds_data = map_vendor_to_tds(vendor_data)
            
            # Generate
            output_file = output_path / f"TDS_{pdf_file.stem}.pdf"
            result = generate_tds(tds_data, str(output_file))
            
            console.print(f"    [green]✓ Generated: {output_file.name}[/green]")
            results.append((pdf_file.name, "Success", output_file.name))
            
        except Exception as e:
            console.print(f"    [red]✗ Error: {e}[/red]")
            results.append((pdf_file.name, "Failed", str(e)))
    
    # Summary
    console.print("\n" + "="*60)
    console.print("[bold]Batch Processing Complete[/bold]")
    success = sum(1 for _, status, _ in results if status == "Success")
    console.print(f"  Successful: {success}/{len(results)}")
    console.print(f"  Output directory: {output_path}")


@app.command()
def demo():
    """
    Generate a demo TDS with sample data.
    
    Creates a TDS for the Exiona Stadium Flood Light to demonstrate
    the template format without requiring a vendor PDF.
    """
    print_banner()
    console.print("[cyan]Generating demo TDS (Exiona Stadium Flood Light)...[/cyan]\n")
    
    from data_mapper import (
        IKIOTDSData, TDSSpecificationTable, TDSSpecificationRow, 
        TDSOrderingInfo, TDSAccessory
    )
    from pdf_generator import generate_tds
    
    # Create Exiona-style demo data
    demo_data = IKIOTDSData(
        product_name="Exiona Stadium Flood Light",
        product_series="ESFL",
        product_description="Exiona Flood Light Series is designed for professional, high-mount lighting applications that demand power and precision. Engineered with durable aluminum housing and advanced optics, it ensures uniform brightness and glare control across wide outdoor areas. Adjustable modular design allows targeted lighting with excellent temperature stability and long lifespan. Compatible with intelligent control systems, Exiona delivers energy efficiency, reliability, and superior illumination quality, making it ideal for large sports fields, plazas, and event spaces requiring dependable performance.",
        features=[
            "Designed for high-mount applications ensuring wide coverage and targeted illumination.",
            "Superior temperature management guarantees consistent performance and extended lifespan.",
            "Adjustable light direction enhances precision and reduces unwanted glare.",
            "Intelligent control compatibility supports modern energy-saving systems.",
            "Rugged structure and weather protection ensure lasting reliability outdoors."
        ],
        applications=[
            "Soccer Fields", "Baseball Fields", "Rugby Fields", "Tennis Courts",
            "Squares", "Stadiums", "Exhibition Centers", "Outdoor Arenas",
            "Large Plazas", "Event Grounds"
        ],
        spec_tables=[
            TDSSpecificationTable(
                title="Technical Specifications",
                column_headers=["480W", "600W"],
                has_multiple_variants=True,
                rows=[
                    TDSSpecificationRow("Power", ["480W", "600W"]),
                    TDSSpecificationRow("Voltage", ["120-277V AC", "277-480V AC, 50/60 Hz"]),
                    TDSSpecificationRow("Power Factor", [">0.90", ""]),
                    TDSSpecificationRow("Surge Protection", ["20KV L-N, 20KV L/N-E", ""]),
                    TDSSpecificationRow("Lumens", ["62400lm", "78000lm"]),
                    TDSSpecificationRow("Efficacy", ["130lm/W", ""]),
                    TDSSpecificationRow("Color Temperature (CCT)", ["5000K (Optional: 3000K, 4000K)", ""]),
                    TDSSpecificationRow("Color Rendering Index (CRI)", ["70 (Optional: 80)", ""]),
                    TDSSpecificationRow("Beam Angle", ["12°", "30°"]),
                    TDSSpecificationRow("Dimmable Light Control", ["DMX Dimmable", ""]),
                    TDSSpecificationRow("Operating Temperature", ["-22°F ~ +122°F", ""]),
                    TDSSpecificationRow("Ingress Protection Rating (IP)", ["IP66", ""]),
                    TDSSpecificationRow("Impact Protection Rating (IK)", ["IK08", ""]),
                    TDSSpecificationRow("Average Life (Hours)", ["50,000", ""]),
                    TDSSpecificationRow("Warranty (Years)", ["5", ""]),
                    TDSSpecificationRow("LED Light Source", ["LED 3535", ""]),
                    TDSSpecificationRow("Housing", ["Aluminum Alloy (Powder coating)", ""]),
                    TDSSpecificationRow("Lens", ["Polycarbonate", ""]),
                    TDSSpecificationRow("Finish", ["Black", ""]),
                    TDSSpecificationRow("Power Supply", ["SOSEN", ""]),
                    TDSSpecificationRow("Effective Projected Area (EPA)", ["1.89ft²", ""]),
                ]
            )
        ],
        mounting_options=[
            TDSAccessory(name="Flood Mount"),
        ],
        packaging_weight="35.93",
        packaging_dimensions='22.44" x 21.65" x 18.11"',
        box_weight="41.22",
        ordering_info=TDSOrderingInfo(
            example_part_number="IK ESFL 480W-50K-4AV-BL 72D-304-20SP-PM-4D",
            components=[
                {"name": "BRAND", "code": "IK", "options": [{"code": "IK", "description": "IKIO"}]},
                {"name": "FAMILY", "code": "ESFL", "options": [{"code": "ESFL", "description": "Exiona Stadium Flood Light"}]},
                {"name": "POWER", "code": "W", "options": [{"code": "480", "description": "for 480W"}, {"code": "600", "description": "for 600W"}]},
                {"name": "CCT", "code": "K", "options": [{"code": "50", "description": "for 5000K"}]},
                {"name": "VOLTAGE", "code": "MV", "options": [{"code": "MV", "description": "for 120-277V"}]},
                {"name": "FINISH", "code": "BL", "options": [{"code": "BL", "description": "for Black"}]},
                {"name": "BEAM ANGLE", "code": "D", "options": [
                    {"code": "12D", "description": "for 12° Beam Angle"},
                    {"code": "30D", "description": "for 30° Beam Angle"},
                    {"code": "55D", "description": "for 55° Beam Angle"}
                ]},
            ]
        ),
        accessories_sold_separately=[
            TDSAccessory(name="Safety Rope"),
            TDSAccessory(name="PC Lens"),
            TDSAccessory(name="Visor"),
            TDSAccessory(name="Precision Aiming Device"),
        ],
        certifications=["CE", "RoHS", "UL", "DLC Premium", "FCC"],
        page_count=3
    )
    
    # Generate
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"DEMO_Exiona_TDS_{timestamp}.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    result = generate_tds(demo_data, str(output_path))
    
    console.print(Panel(
        f"[bold green]✓ Demo TDS Generated![/bold green]\n\n"
        f"Output: [cyan]{result}[/cyan]\n"
        f"Product: [yellow]Exiona Stadium Flood Light[/yellow]\n"
        f"This demonstrates the IKIO TDS template format.",
        title="Complete",
        border_style="green"
    ))


@app.command()
def config():
    """
    Show current configuration settings.
    """
    print_banner()
    
    # Company info table
    table = Table(title="Company Configuration", show_header=True, header_style="bold cyan")
    table.add_column("Setting", style="dim")
    table.add_column("Value")
    
    table.add_row("Company Name", COMPANY_CONFIG['name'])
    table.add_row("Website", COMPANY_CONFIG['website'])
    table.add_row("Email", COMPANY_CONFIG['email'])
    table.add_row("Output Directory", str(OUTPUT_DIR))
    
    console.print(table)
    console.print()
    
    # AI Providers table
    ai_table = Table(title="AI Providers (FREE options available!)", show_header=True, header_style="bold green")
    ai_table.add_column("Provider", style="bold")
    ai_table.add_column("Status")
    ai_table.add_column("Vision")
    ai_table.add_column("Cost")
    
    ai_table.add_row(
        "Groq" + (" ← Active" if AI_PROVIDER == "groq" else ""),
        "[green]Configured ✓[/green]" if GROQ_API_KEY else "[yellow]Not set[/yellow]",
        "[red]No[/red]",
        "[green]FREE[/green]"
    )
    ai_table.add_row(
        "Gemini" + (" ← Active" if AI_PROVIDER == "gemini" else ""),
        "[green]Configured ✓[/green]" if GEMINI_API_KEY else "[yellow]Not set[/yellow]",
        "[green]Yes[/green]",
        "[green]FREE[/green]"
    )
    ai_table.add_row(
        "Ollama" + (" ← Active" if AI_PROVIDER == "ollama" else ""),
        "[green]Local (no key needed)[/green]",
        "[green]Yes (LLaVA)[/green]",
        "[green]FREE[/green]"
    )
    ai_table.add_row(
        "OpenAI" + (" ← Active" if AI_PROVIDER == "openai" else ""),
        "[green]Configured ✓[/green]" if OPENAI_API_KEY else "[yellow]Not set[/yellow]",
        "[green]Yes[/green]",
        "[yellow]Paid[/yellow]"
    )
    
    console.print(ai_table)
    console.print()
    
    provider_info = get_active_provider_info()
    console.print(f"[bold]Current Provider:[/bold] {provider_info['name']} ({provider_info['model']})")
    console.print()
    
    console.print("[bold green]🆓 Get FREE API Keys:[/bold green]")
    console.print("  • Groq:   https://console.groq.com/keys")
    console.print("  • Gemini: https://aistudio.google.com/apikey")
    console.print("  • Ollama: https://ollama.ai (local, no key needed)")


def main():
    """Main entry point"""
    app()


if __name__ == "__main__":
    main()
