import os
import re
import sys
import shutil
import threading
from pathlib import Path
from collections import OrderedDict

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import fitz
from PIL import Image, ImageOps, ImageEnhance
import pytesseract

APP_NAME = "Invoice Splitter"


def resource_path(*parts):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def configure_tesseract():
    bundled = resource_path("tesseract", "tesseract.exe")
    if bundled.exists():
        pytesseract.pytesseract.tesseract_cmd = str(bundled)
        tessdata = bundled.parent / "tessdata"
        if tessdata.exists():
            os.environ["TESSDATA_PREFIX"] = str(tessdata)
        return True

    candidates = [
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return True
    return False


def clean_filename(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value[:150] or "Unknown_Customer"


def normalize_text(value):
    value = value.replace("—", "-").replace("–", "-").replace("_", "-")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def extract_text_from_page(page):
    # Prefer native PDF text; this is much more reliable for digitally generated invoices.
    text = page.get_text("text").strip()
    if text:
        return normalize_text(text)

    # OCR fallback for scanned/image-only invoices.
    pix = page.get_pixmap(matrix=fitz.Matrix(2.4, 2.4), alpha=False)
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    image = ImageOps.grayscale(image)
    image = ImageEnhance.Contrast(image).enhance(1.8)
    image = ImageEnhance.Sharpness(image).enhance(1.5)
    return normalize_text(
        pytesseract.image_to_string(image, config="--psm 6", lang="eng+ara")
    )


def extract_invoice_number(text):
    patterns = [
        r"\bINV\s*[-#: ]?\s*0*(\d{3,})\b",
        r"\bINVOICE\s*(?:NO|NUMBER|#)?\s*[:#-]?\s*0*(\d{3,})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return f"INV-{int(match.group(1)):06d}"
    return None


def extract_customer(text):
    # Common format: Bill To: Customer Name
    match = re.search(
        r"\bBILL\s*TO\b\s*[:\-]?\s*(.+?)(?=\b(?:INVOICE\s*DATE|DUE\s*DATE|PO\s*NO|PO\s*NUMBER|VAT|TOTAL|SUB\s*TOTAL)\b|$)",
        text,
        re.I,
    )
    if match:
        value = match.group(1).strip(" :-")
        value = re.sub(
            r"\b(?:Invoice\s*Date|Due\s*Date|PO\s*(?:No|Number)|VAT|Total|Sub\s*Total)\b.*$",
            "",
            value,
            flags=re.I,
        ).strip(" :-")
        value = re.sub(r"\s+", " ", value)
        if value and len(value) >= 2:
            return value

    # Fallback: line immediately after Bill To.
    lines = [line.strip() for line in re.split(r"\n+", text) if line.strip()]
    for index, line in enumerate(lines):
        if re.fullmatch(r"BILL\s*TO\s*:?", line, re.I) and index + 1 < len(lines):
            return lines[index + 1]

    return "Unknown Customer"


def unique_path(path):
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def split_invoices(input_pdf, output_dir, progress_cb=None, log_cb=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(input_pdf)
    groups = OrderedDict()
    missing_counter = 0

    for index in range(len(doc)):
        page = doc[index]
        text = extract_text_from_page(page)

        invoice_no = extract_invoice_number(text)
        customer = extract_customer(text)

        if not invoice_no:
            missing_counter += 1
            key = (f"NO-INV-{missing_counter}", clean_filename(customer))
        else:
            key = (invoice_no, clean_filename(customer))

        groups.setdefault(key, []).append(index)

        if log_cb:
            log_cb(
                f"Page {index + 1}: "
                f"{invoice_no or 'NO-INVOICE-NO'} | {customer}"
            )

        if progress_cb:
            progress_cb((index + 1) / max(1, len(doc)) * 70)

    created = []

    for number, ((invoice_no, customer), pages) in enumerate(groups.items(), 1):
        output = output_dir / f"{invoice_no}_{customer}.pdf"
        output = unique_path(output)

        new_doc = fitz.open()
        for page_index in pages:
            new_doc.insert_pdf(doc, from_page=page_index, to_page=page_index)

        new_doc.save(output, garbage=4, deflate=True)
        new_doc.close()
        created.append(output)

        if progress_cb:
            progress_cb(70 + number / max(1, len(groups)) * 30)

    doc.close()
    return created


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("780x570")
        self.minsize(700, 500)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0)

        self.build_ui()

        self.tesseract_ok = configure_tesseract()
        if not self.tesseract_ok:
            self.status_var.set(
                "Tesseract OCR was not found. Use the bundled EXE build "
                "or install Tesseract OCR."
            )

    def build_ui(self):
        pad = {"padx": 16, "pady": 8}

        ttk.Label(
            self,
            text="Invoice Splitter",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w", **pad)

        ttk.Label(
            self,
            text=(
                "Split a PDF into one PDF per invoice number and Bill To customer. "
                "Duplicate invoice pages are combined."
            ),
        ).pack(anchor="w", padx=16)

        frame = ttk.Frame(self)
        frame.pack(fill="x", padx=16, pady=16)

        ttk.Label(frame, text="Input PDF:").grid(
            row=0, column=0, sticky="w", pady=8
        )
        ttk.Entry(frame, textvariable=self.input_var).grid(
            row=0, column=1, sticky="ew", padx=8
        )
        ttk.Button(frame, text="Browse…", command=self.browse_input).grid(
            row=0, column=2
        )

        ttk.Label(frame, text="Output folder:").grid(
            row=1, column=0, sticky="w", pady=8
        )
        ttk.Entry(frame, textvariable=self.output_var).grid(
            row=1, column=1, sticky="ew", padx=8
        )
        ttk.Button(frame, text="Browse…", command=self.browse_output).grid(
            row=1, column=2
        )

        frame.columnconfigure(1, weight=1)

        self.run_btn = ttk.Button(
            self, text="Split Invoices", command=self.start
        )
        self.run_btn.pack(anchor="w", padx=16, pady=4)

        ttk.Progressbar(
            self, variable=self.progress_var, maximum=100
        ).pack(fill="x", padx=16, pady=12)

        ttk.Label(self, textvariable=self.status_var).pack(
            anchor="w", padx=16
        )

        log_frame = ttk.LabelFrame(self, text="Processing log")
        log_frame.pack(fill="both", expand=True, padx=16, pady=12)

        self.log = tk.Text(log_frame, height=16, wrap="none")
        self.log.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scrollbar.set)

    def browse_input(self):
        filename = filedialog.askopenfilename(
            filetypes=[("PDF files", "*.pdf")]
        )
        if filename:
            self.input_var.set(filename)
            if not self.output_var.get():
                path = Path(filename)
                self.output_var.set(
                    str(path.with_name(path.stem + "_split"))
                )

    def browse_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_var.set(folder)

    def append_log(self, message):
        self.after(
            0,
            lambda: (
                self.log.insert("end", message + "\n"),
                self.log.see("end"),
            ),
        )

    def set_progress(self, value):
        self.after(0, lambda: self.progress_var.set(value))

    def start(self):
        input_path = Path(self.input_var.get())
        output_path = (
            Path(self.output_var.get())
            if self.output_var.get()
            else input_path.with_name(input_path.stem + "_split")
        )

        if not input_path.exists() or input_path.suffix.lower() != ".pdf":
            messagebox.showerror(
                APP_NAME, "Please select a valid PDF file."
            )
            return

        if not self.tesseract_ok:
            messagebox.showerror(
                APP_NAME,
                "OCR engine not found. Please use the bundled Windows EXE "
                "build or install Tesseract OCR.",
            )
            return

        self.run_btn.configure(state="disabled")
        self.log.delete("1.0", "end")
        self.progress_var.set(0)
        self.status_var.set("Processing…")

        threading.Thread(
            target=self.worker,
            args=(input_path, output_path),
            daemon=True,
        ).start()

    def worker(self, input_path, output_path):
        try:
            files = split_invoices(
                input_path,
                output_path,
                self.set_progress,
                self.append_log,
            )

            self.after(
                0,
                lambda: self.status_var.set(
                    f"Done — {len(files)} PDF(s) created in {output_path}"
                ),
            )
            self.after(
                0,
                lambda: messagebox.showinfo(
                    APP_NAME,
                    f"Done.\n\nCreated {len(files)} PDF(s).\n\n"
                    f"Output:\n{output_path}",
                ),
            )
        except Exception as exc:
            self.after(0, lambda: self.status_var.set("Failed"))
            self.after(
                0,
                lambda: messagebox.showerror(APP_NAME, str(exc)),
            )
        finally:
            self.after(
                0,
                lambda: self.run_btn.configure(state="normal"),
            )


if __name__ == "__main__":
    App().mainloop()
