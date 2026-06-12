import os
import shutil
import subprocess
import sys


def _find_soffice():
    """Return the soffice executable path, or None if not found."""
    # Check PATH first (works if user has set it up, or on Linux with system package)
    if shutil.which('soffice'):
        return 'soffice'

    # Platform-specific default install locations
    if sys.platform == 'darwin':
        candidates = [
            '/Applications/LibreOffice.app/Contents/MacOS/soffice',
            '/opt/homebrew/bin/soffice',
        ]
    elif sys.platform == 'win32':
        candidates = [
            r'C:\Program Files\LibreOffice\program\soffice.exe',
            r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
        ]
    else:
        candidates = []

    for path in candidates:
        if os.path.isfile(path):
            return path

    return None


def convert_docx_to_pdf(docx_filepath, pdf_filepath=None):
    """
    Converts a DOCX file to PDF using LibreOffice (headless mode).

    Args:
        docx_filepath: The path to the DOCX file.
        pdf_filepath: The desired path for the output PDF file.
                      If None, the PDF will be created in the same directory
                      as the DOCX file with the same name but a .pdf extension.

    Returns:
        True if the conversion was successful, False otherwise.
    """
    if not os.path.exists(docx_filepath):
        print(f"Error: DOCX file not found at {docx_filepath}")
        return False

    if pdf_filepath is None:
        pdf_filepath = os.path.splitext(docx_filepath)[0] + ".pdf"

    soffice = _find_soffice()
    if not soffice:
        print("Error: LibreOffice not found. Install it from https://www.libreoffice.org "
              "and ensure 'soffice' is in your PATH.")
        return False

    outdir = os.path.dirname(os.path.abspath(pdf_filepath))
    # LibreOffice always names the output after the input basename
    expected_output = os.path.join(outdir, os.path.splitext(os.path.basename(docx_filepath))[0] + ".pdf")

    try:
        cmd = [soffice, '--headless', '--convert-to', 'pdf', '--outdir', outdir, docx_filepath]
        subprocess.run(cmd, check=True, capture_output=True)

        # Rename if LibreOffice's chosen name differs from the requested pdf_filepath
        if os.path.abspath(expected_output) != os.path.abspath(pdf_filepath):
            os.rename(expected_output, pdf_filepath)

        print(f"✅ Successfully converted {docx_filepath} to {pdf_filepath}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error during conversion: {e}")
        print(f"Stderr: {e.stderr.decode()}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during DOCX-to-PDF conversion: {e}")
        return False

# Example Usage:
# if convert_docx_to_pdf("invoice.docx", "invoice.pdf"):
#     print("Conversion complete.")
# else:
#     print("Conversion failed.")
