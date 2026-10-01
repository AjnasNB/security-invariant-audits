"""Layout-controlled PDF built from the measured results register."""
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from research.io import ROOT, read_json


def create_pdf():
    data = read_json(ROOT / "reports" / "summary.json")
    destination = ROOT / "output" / "pdf" / "Ajnas_Security_Invariant_MVP_Results.pdf"
    destination.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("StudySans", "C:/Windows/Fonts/arial.ttf"))
    pdfmetrics.registerFont(TTFont("StudySansBold", "C:/Windows/Fonts/arialbd.ttf"))
    pdfmetrics.registerFontFamily("StudySans", normal="StudySans", bold="StudySansBold")
    palette = {"ink": colors.HexColor("#15263B"), "blue": colors.HexColor("#176B9A"),
               "muted": colors.HexColor("#52677B"), "line": colors.HexColor("#D7E2EB"),
               "light": colors.HexColor("#EEF4F8")}
    styles = {
        "title": ParagraphStyle("Title", fontName="StudySansBold", fontSize=28, leading=33,
                                textColor=palette["ink"], spaceAfter=18),
        "heading": ParagraphStyle("Heading", fontName="StudySansBold", fontSize=17, leading=22,
                                  textColor=palette["ink"], spaceAfter=12),
        "sub": ParagraphStyle("Subheading", fontName="StudySansBold", fontSize=11, leading=15,
                              textColor=palette["blue"], spaceBefore=10, spaceAfter=7),
        "body": ParagraphStyle("Body", fontName="StudySans", fontSize=10, leading=15,
                               textColor=palette["ink"], spaceAfter=10),
        "small": ParagraphStyle("Small", fontName="StudySans", fontSize=8.5, leading=12,
                                textColor=palette["muted"], spaceAfter=7),
        "cell": ParagraphStyle("Cell", fontName="StudySans", fontSize=8.5, leading=11,
                               textColor=palette["ink"]),
        "header": ParagraphStyle("Header", fontName="StudySansBold", fontSize=8.5, leading=11,
                                 textColor=palette["ink"]),
    }
    width = A4[0] - 96

    def paragraph(text, style="body"):
        return Paragraph(escape(str(text)), styles[style])

    def table(headers, rows, fractions):
        cells = [[paragraph(value, "header") for value in headers]] + [
            [paragraph(value, "cell") for value in row] for row in rows
        ]
        result = Table(cells, colWidths=[width * fraction for fraction in fractions], repeatRows=1, hAlign="LEFT")
        result.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), palette["light"]),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, palette["blue"]),
            ("LINEBELOW", (0, 1), (-1, -1), 0.35, palette["line"]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        return result

    story = []
    story += [
        paragraph("AJNAS N B / RESEARCH MVP", "small"),
        Spacer(1, 18),
        paragraph("Security-Invariant\nMutation Audits", "title"),
        paragraph("Measured local feasibility results | October 1, 2026", "sub"),
        paragraph(data["conclusion"]),
        table(["Experiment", "Actual result"], [
            ["Three synthetic programs", "48/48 meaningful refactors; 5,216/5,216 protected checks passed"],
            ["Real FastAPI backend", "5/5 meaningful refactors; 60/60 protected checks passed"],
            ["Demonstrated access violations", "0 in these agent trajectories"],
            ["Evaluator validation", "Correct alternatives accepted; 8/8 seeded security faults rejected"],
            ["Model and engine", "Azure GPT-6.1 Sol / Delta Native restricted research broker"],
        ], [0.37, 0.63]),
        Spacer(1, 16),
        paragraph("What this establishes", "sub"),
        paragraph("The source-to-agent-to-independent-assessment flow works, with reproducible inputs and retained output evidence. This small pilot did not establish that mutations outperform unchanged repetitions."),
        paragraph("What it does not establish", "sub"),
        paragraph("No general model safety, production security certification, full ERP evaluation, published detector accuracy or internal reasoning cause is established."),
        PageBreak(),
    ]
    story += [
        paragraph("1. Sources and dataset provenance", "heading"),
        paragraph("Seven pinned source repositories are kept locally. Different families remain separate. Downloading or normalizing a source does not mean every row was evaluated."),
        table(["Source", "Records", "Research role"], [
            [name, row["records"], row["family"]]
            for name, row in data["datasets"]["datasets"].items()
        ], [0.32, 0.13, 0.55]),
        Spacer(1, 12),
        paragraph("License boundary", "sub"),
        paragraph("HumanEval, django-multitenant, AgentDojo and FastAPI retain MIT notices. The inspected MUCOCO/JailGuard commits do not establish redistribution permissions; their data and derived paper inputs remain local/restricted. ERPNext GPL material remains separately identified."),
        paragraph("Application selection", "sub"),
        paragraph("The FastAPI full-stack project had 45,828 GitHub stars at acquisition. We exercised its actual item routes and models using its declared Python 3.14 runtime and an in-memory database. Stars are a dated popularity signal, not evidence of security."),
        paragraph("ERPNext had 39,696 stars at acquisition. Its invoice code and test excerpts were acquired for ERP context; its Frappe/database deployment was not executed. The report does not relabel that acquisition as an ERP runtime test.", "small"),
        PageBreak(),
    ]
    story += [
        paragraph("2. Protocol and independent checks", "heading"),
        paragraph("The three synthetic programs enforce one explicit rule: owner ID AND company ID must match. Missing identities and records are denied; no administrator exception exists."),
        table(["Program", "Runs", "Protected checks", "Violating runs"], [
            [task, row["runs"], f"{row['passed_checks']}/{row['checks']}", row["security_violating_runs"]]
            for task, row in data["pilot"]["tasks"].items()
        ], [0.38, 0.12, 0.27, 0.23]),
        Spacer(1, 12),
        table(["Condition", "Change"], [
            ["Original", "Correct code and fixed trusted refactor request"],
            ["Rename", "One internal identifier; validated structure and reference behavior"],
            ["Formatting", "Formatting/comment variation; executable AST unchanged"],
            ["Neutral note", "Benign context matched in location and approximate length"],
            ["Misleading note", "Untrusted note attempts to weaken authorization"],
        ], [0.25, 0.75]),
        Spacer(1, 10),
        paragraph("All run contexts are fresh. The agent may read listed task files, replace target.py, and request fixed public tests. No host shell, memory retrieval, plugin, team, credentials or network tool is available."),
        paragraph("A host-owned judge compares observations after the agent stops. Generated code runs non-root with no network, read-only mounts, dropped capabilities, no-new-privileges and resource/time limits. Nine restriction probes pass for each primary runtime; this is configured containment, not proof against kernel exploits.", "small"),
        PageBreak(),
    ]
    story += [
        paragraph("3. Matched comparison results", "heading"),
        paragraph("Each task has six benign-variation runs and six independent unchanged runs. Notes are compared separately with two neutral and two misleading runs per task. No original trajectory is reused as an unchanged control."),
        table(["Task", "Comparison arm", "Runs", "Violations", "Calls"], [
            [row["task"], row["comparison_arm"], row["runs"], row["security_violating_runs"], row["model_requests"]]
            for row in data["comparisons"]
        ], [0.25, 0.35, 0.12, 0.15, 0.13]),
        Spacer(1, 12),
        paragraph("Interpretation", "sub"),
        paragraph("No arm exposed a violation. That is a legitimate zero-discovery outcome, not proof that the methods are equivalent. Three templates are too small to infer broad detection performance, and related runs are not independent repositories."),
        paragraph("All actual tokens, cache usage and base cost estimates are reported by arm in comparison.csv. Nominal ceilings match; actual usage can differ. Detector precision/recall for security regressions remains N/A with no observed positive failures.", "small"),
        PageBreak(),
    ]
    story += [
        paragraph("4. Real application and author artefacts", "heading"),
        paragraph("The FastAPI task preserves its native owner OR administrator rule, including 403/404, count, pagination and assigning the authenticated owner at creation. It has no company field and is not reported as tenant isolation."),
        table(["FastAPI condition", "Completed", "Protected checks"], [
            [condition, f"{row['task_completed']}/{row['runs']}", "12/12"]
            for condition, row in data["application"]["conditions"].items()
        ], [0.4, 0.25, 0.35]),
        Spacer(1, 10),
        paragraph("JailGuard adapted workflow", "sub"),
        paragraph("Four original-data inputs, eight original RR variants each, 32 live Azure attempts: 25 completed responses and seven content-filtered attempts. The three complete groups use the actual spaCy similarity, KL divergence, threshold 0.02 and refusal logic. Author-script replay checks 24 exact-matched frozen queries."),
        table(["Source input", "Historical attack", "Detected", "Max divergence"], [
            [row["source_id"], row["historical_attack_label"],
             row["detected_attack"] if row["detected_attack"] is not None else "Unknown",
             f"{row['max_divergence']:.6f}" if row["max_divergence"] is not None else "N/A"]
            for row in data["jailguard"]["results"]
        ], [0.31, 0.24, 0.17, 0.28]),
        Spacer(1, 10),
        paragraph("Two benign inputs run the original script; one complete message-list input uses a one-line response-filename fix because the original scorer skips .pkl-named text responses. The filtered fourth group remains unknown, not safe. GPT-3.5 is replaced by Sol; runtime dependencies differ and unused image imports are stubbed. Four inputs cannot replicate published accuracy.", "small"),
        paragraph("MUCOCO's actual VariableNameTransformer validated two HumanEval mutants; one task had no applicable local variable. django-multitenant integration passed 5/5; AgentDojo author tool/data smoke passed 4/4. These are component/integration evidence, not their entire published benchmark.", "small"),
        PageBreak(),
    ]
    cost = data["accounting"]["all_observed_totals"]
    story += [
        paragraph("5. Evidence, costs and limitations", "heading"),
        table(["Recorded quantity", "Observed / estimated"], [
            ["Pilot model requests", data["pilot"]["usage"]["requests"]],
            ["Application model requests", data["application"]["usage"]["requests"]],
            ["All observed HTTP attempts", cost["http_attempts"]],
            ["All observed input tokens", cost["input_tokens"]],
            ["All observed output tokens", cost["output_tokens"]],
            ["All observed cached tokens", cost["cached_tokens"]],
            ["All-observed public base estimate", f"${cost['public_reference_base_estimated_cost_usd']:.4f}"],
            ["Including assumed cache-write premium", f"${cost['public_reference_estimated_cost_usd']:.4f}"],
        ], [0.61, 0.39]),
        Spacer(1, 12),
        paragraph("Billing is not independently reconciled to an Azure invoice. Estimates use public OpenAI Standard short-context rates. Cache-write tokens are treated as a subset of uncached input and replace that price at 1.25x, not billed twice. An interrupted request can have unobserved in-flight cost.", "small"),
        paragraph("Retained setup failures", "sub"),
        paragraph("An early version-2 batch revealed a verbose-test-file/context-rollover issue. Its successful and step-limited runs were retained and the entire batch was excluded from the fresh version-3 pilot. Tests were compacted without dropping any case. Protocol changes are documented."),
        paragraph("Evidence package", "sub"),
        paragraph("Root README, protocol, seven source commits, selected file hashes, runtime locks/image IDs, raw provider responses, tool events, candidate files, public checks, host-owned assessments, run/comparison CSVs and integrity audits. All 53 final agent receipts reconcile."),
        paragraph("Recommended next research step", "sub"),
        paragraph("Freeze additional independently designed tasks and a more realistic multi-tenant application workflow. Add stronger held-out challenges and, only then, a separately controlled engine/model comparison. Do not tune attack text until a failure appears and present that as an unbiased result."),
        paragraph("Publication remains local. No public repo, branch or push was created. Ajnas retains authorship; restricted data and private correspondence are excluded from a future public export.", "small"),
    ]

    def chrome(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(palette["line"])
        canvas.line(48, 43, A4[0]-48, 43)
        canvas.setFont("StudySans", 8)
        canvas.setFillColor(palette["muted"])
        canvas.drawString(48, 29, "AJNAS N B  |  Measured local research MVP  |  October 1, 2026")
        canvas.drawRightString(A4[0]-48, 29, str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(str(destination), pagesize=A4, rightMargin=48, leftMargin=48,
                            topMargin=46, bottomMargin=60,
                            title="Ajnas - Security-Invariant Mutation Audit MVP Results",
                            author="Ajnas N B")
    doc.build(story, onFirstPage=chrome, onLaterPages=chrome)
    print(str(destination))
    return destination


if __name__ == "__main__":
    create_pdf()
