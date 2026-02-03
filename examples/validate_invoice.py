# Check UBL-2.1 schema compliance
# python validate_invoice.py invoices/INV-2025-001.xml UBL-2.1/schemas/UBL-Invoice-2.1.xsd

# Then check business rules (schematronics) / EN16931  compliance via Java, or at:
# - https://ecosio.com/en/peppol-and-xml-document-validator/
# - https://app.b2brouter.net/en/validation
# Another approach is with Phive. See https://github.com/phax/peppol
# phive validate -s ./schemas/PEPPOL-BIS-3.0 -i invoice.xml

import sys
import peppol_invoicing as invoicing

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python validate_invoice.py <invoice.xml> <UBL-Invoice-2.1.xsd>")
        sys.exit(1)

    xml_path = sys.argv[1]
    schema_path = sys.argv[2]
    succeeded, errors = invoicing.validate_invoice(xml_path, schema_path)
    if succeeded:
        print(f"✅ {xml_path} is valid against {schema_path}")
    else:
        print(f"❌ Validation errors in {xml_path}:")
        for e in errors:
          print(f"  {e}")
