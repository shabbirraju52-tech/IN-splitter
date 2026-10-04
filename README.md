# Invoice Splitter

Windows GUI program for splitting invoice PDFs.

## Detection

- Invoice number: `INV-000367`, `INV 000367`, `INVOICE NO`, etc.
- Customer: text following `Bill To:`
- Uses native PDF text extraction first.
- Falls back to OCR for scanned/image-only PDFs.
- Combines multiple pages with the same invoice number and customer.
- Creates filenames such as:

`INV-000367_Ensign International Energy Services Pvt. Ltd.pdf`

## Build

The GitHub Actions workflow builds a Windows one-file EXE and bundles Tesseract OCR.

1. Upload this project to GitHub.
2. Open Actions.
3. Select `Build Invoice Splitter Windows EXE`.
4. Click `Run workflow`.
5. Download the `InvoiceSplitter-Windows` artifact.

The supplied sample invoice contains invoice number INV-000367 and Bill To customer
Ensign International Energy Services Pvt. Ltd.
