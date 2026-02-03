import os
import subprocess

def convert_docx_to_pdf(docx_filepath, pdf_filepath=None):
    """
    Converts a DOCX file to PDF using LibreOffice (headless mode).

    Args:
        docx_filepath: The path to the DOCX file.
        pdf_filepath: The desired path for the output PDF file.
                      If None, the PDF will be created in the same directory
                      as the DOCX file, with the same name but a .pdf extension.

    Returns:
        True if the conversion was successful, False otherwise.
    """

    if not os.path.exists(docx_filepath):
        print(f"Error: DOCX file not found at {docx_filepath}")
        return False

    if pdf_filepath is None:
        pdf_filepath = os.path.splitext(docx_filepath)[0] + ".pdf"

    try:
        # Construct the LibreOffice command
        cmd = [
            'soffice',  # LibreOffice command-line executable
            '--headless',  # Run in headless mode (no GUI)
            '--convert-to', 'pdf',  # Specify PDF as the output format
            '--outdir', os.path.dirname(pdf_filepath), # Output directory
            docx_filepath  # Input DOCX file
        ]

        # Execute the command using subprocess
        subprocess.run(cmd, check=True, capture_output=True)

        print(f"✅ Successfully converted {docx_filepath} to {pdf_filepath}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error during conversion: {e}")
        print(f"Stderr: {e.stderr.decode()}")  # Print error output
        return False
    except FileNotFoundError:
        print("Error: LibreOffice 'soffice' command not found. Make sure LibreOffice is installed and in your PATH.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False

# Example Usage:

if __name__ == '__main__':
    docx_file = "full_width_table.docx"  #  Ensure file exists
    pdf_file = "full_width_table.pdf"     # Optional: Specify output PDF path

    if convert_docx_to_pdf(docx_file, pdf_file):
        print("Conversion complete.")
    else:
        print("Conversion failed.")