@echo off
python -m pip install -r requirements.txt
pyinstaller --noconfirm --clean --onefile --windowed --name InvoiceSplitter invoice_splitter.py
pause
