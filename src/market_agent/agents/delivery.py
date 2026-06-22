from __future__ import annotations

import argparse
import os
import smtplib
import textwrap
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path


@dataclass(frozen=True)
class EmailConfig:
    host: str
    port: int
    username: str
    password: str
    sender: str
    recipient: str
    use_tls: bool = True


def write_text_pdf(title: str, lines: list[str], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pages = _paginate_lines(title, lines)
    objects: list[bytes] = [
        b"",
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    kids: list[str] = []
    for page_index, page_lines in enumerate(pages):
        page_obj = len(objects)
        content_obj = page_obj + 1
        kids.append(f"{page_obj} 0 R")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>".encode("ascii")
        )
        stream = _page_stream(page_lines, page_index + 1, len(pages))
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
    objects[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode("ascii")
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects[1:], start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    output_path.write_bytes(bytes(pdf))
    return output_path


def markdown_to_pdf(markdown_path: Path, pdf_path: Path) -> Path:
    text = markdown_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = "AI Investment Intelligence Platform - Autonomous Agent Report"
    return write_text_pdf(title, lines, pdf_path)


def send_pdf_email(config: EmailConfig, pdf_path: Path, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = config.sender
    message["To"] = config.recipient
    message["Subject"] = subject
    message.set_content(body)
    message.add_attachment(
        pdf_path.read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=pdf_path.name,
    )
    with smtplib.SMTP(config.host, config.port, timeout=30) as smtp:
        if config.use_tls:
            smtp.starttls()
        smtp.login(config.username, config.password)
        smtp.send_message(message)


def email_config_from_env() -> EmailConfig:
    required = {
        "SMTP_HOST": os.environ.get("SMTP_HOST", ""),
        "SMTP_USERNAME": os.environ.get("SMTP_USERNAME", ""),
        "SMTP_PASSWORD": os.environ.get("SMTP_PASSWORD", ""),
        "EMAIL_TO": os.environ.get("EMAIL_TO", ""),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f"Missing email configuration: {', '.join(missing)}")
    sender = os.environ.get("EMAIL_FROM") or required["SMTP_USERNAME"]
    return EmailConfig(
        host=required["SMTP_HOST"],
        port=int(os.environ.get("SMTP_PORT", "587")),
        username=required["SMTP_USERNAME"],
        password=required["SMTP_PASSWORD"],
        sender=sender,
        recipient=required["EMAIL_TO"],
        use_tls=os.environ.get("SMTP_USE_TLS", "true").lower() != "false",
    )


def _paginate_lines(title: str, lines: list[str]) -> list[list[str]]:
    wrapped: list[str] = [title, ""]
    for line in lines:
        stripped = line.strip()
        if not stripped:
            wrapped.append("")
            continue
        width = 78 if stripped.startswith(("-", "{", "}", '"')) else 70
        wrapped.extend(textwrap.wrap(stripped, width=width) or [""])
    page_size = 48
    return [wrapped[index : index + page_size] for index in range(0, len(wrapped), page_size)] or [[title]]


def _page_stream(lines: list[str], page_number: int, page_count: int) -> bytes:
    commands = ["BT", "/F1 10 Tf", "14 TL", "50 790 Td"]
    for line in lines:
        commands.append(f"({_pdf_escape(line)}) Tj")
        commands.append("T*")
    commands.extend(
        [
            "ET",
            "BT",
            "/F1 8 Tf",
            f"50 30 Td (Page {page_number} of {page_count}) Tj",
            "ET",
        ]
    )
    return "\n".join(commands).encode("latin-1", errors="replace")


def _pdf_escape(value: str) -> str:
    return value.encode("latin-1", errors="replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous report PDF/email delivery")
    parser.add_argument("--markdown", required=True)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--email", action="store_true")
    parser.add_argument("--subject", default="AI Investment Intelligence Platform Report")
    args = parser.parse_args()

    pdf_path = markdown_to_pdf(Path(args.markdown), Path(args.pdf))
    print(f"PDF: {pdf_path}")
    if args.email:
        send_pdf_email(
            email_config_from_env(),
            pdf_path,
            args.subject,
            "Attached is the latest AI Investment Intelligence Platform autonomous report PDF.",
        )
        print("Email sent")


if __name__ == "__main__":
    main()
