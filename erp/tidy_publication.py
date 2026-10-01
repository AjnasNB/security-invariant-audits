"""Normalize only the publishable historical HTML, preserving raw local evidence."""
from pathlib import Path


def main():
    source = Path(__file__).resolve().parents[1] / "reports" / "report.html"
    text = source.read_text(encoding="utf-8")
    source.write_text("\n".join(line.rstrip() for line in text.splitlines()) + "\n", encoding="utf-8")
    print("Historical HTML export whitespace normalized; original D:/SUTD evidence retained.")


if __name__ == "__main__":
    main()
