# e-INVOICE sending and validation.
# requires  lxml requests

# to submit via PEPPOL need API Key or access credentials for an Access Point. May need Java-based Oxalis or Domibus.
# can test with PEPPOL Test reciever 0088:9915:peppoltest::receiver (or self in "test mode")

# Real endpoints include: PEPPOL AP like Billit, Pagero, or Advalvas
# try https://nymus.be/en/peppol-api/
# or  https://www.scrada.be/en/peppol/

import os
import sys
import requests
from lxml import etree

from . import utils as _utils

# ----------- CONFIG ----------------
PEPPOL_ENDPOINT_URL = "https://your-access-point.example.com/as4"  # Replace with your AP
PEPPOL_API_KEY = "your_api_key"  # Or use certificate-based auth
# ----------------------------------


def send_invoice(xml_path):
    print(f"📡 Sending invoice to PEPPOL AP: {PEPPOL_ENDPOINT_URL}")
    with open(xml_path, "rb") as f:
        files = {"file": (os.path.basename(xml_path), f, "application/xml")}
        headers = {
            "Authorization": f"Bearer {PEPPOL_API_KEY}",
            "Accept": "application/json"
        }
        response = requests.post(PEPPOL_ENDPOINT_URL, files=files, headers=headers)

    if response.status_code == 200:
        print("✅ Invoice successfully sent via PEPPOL!")
    else:
        print(f"❌ Failed to send invoice: {response.status_code}:\n{response.text}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python peppol_invoice_sender.py <path_to_invoice.xml> <path_to_UBL-Invoice-2.1.xsd>")
        sys.exit(1)

    xml_path = sys.argv[1]
    xsd_path = sys.argv[2]
    _utils.validate_invoice(xml_path, xsd_path)
    send_invoice(xml_path)
