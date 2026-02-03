# Peppol-Compatible invoicing

[TODO: General description]

If you are a freelancer charging by the hour, this may be all you need to create compliant invoices for sending on PEPPOL. You'll still need to register as an endpoint, but there are ways to do this for free. As such using this software may dramatically reduce your overhead costs.

## Invoice generation

This project contains code to generate digital invoices.

Invoices are created in two forms: DOCX/PDF and XML for machine-processing and submission via PEPPOL.

1. Human readable DOCX/PDF invoices are generated with `docx_invoice.py`. These are based upon document templates in the templates/ subdirectory. By template, we simply mean that they contain certain snippets of text that will be automatically replaced, like [CLIENT_NAME] and [SUBTOTAL]. The conversion from DOCX to PDF requirees LibreOffice to be installed (in addition to the libraries we use).
2. Machine readable XML invoices (for potential submission via PEPPOL) are generated with `en16931_invoice.py`. These are compliant with Belgian regulations and suitable for billing Belgian customers. PDFs of humam-readable invoices can optionally be embedded into the XML.

This latter XML style of invoice is required to be used for B2B work with Belgian customers from 1 January 2026. It is encouraged to be sent via PEPPOL but that is apparently not required. Such invoices can also be sent to non-BE customers, for example by email, but XML invoices are not required for customers outside of Belgium.

Typically a script should be created for each customer, which generates the invoices for that customer.

- `invoice_myclient.py` does this for the 'My Client' customer, which can serve as an example for other customers.
  In this high-level script, details of the customer, the seller ('My Company'), and the relevant contract are defined. Some aspects of the seller may vary by buyer (such as payment details).

  This example script works very simply. You provide the number of hours to be invoiced, and (optionally) the total copyright royalties to be charged, and the invoice is created in both forms, the PDF is embedded in the XML, and the XML is (partly) validated. The invoice number is inferred from previous invoices, the date is today, and the billing period is also inferred from the date.

  Usage:
  ```bash
  python3 invoice_myclient.py <hours_worked> [delivery_royalty_percent]
  ```

All invoices are placed in the `invoices/` subdirectory.
Final PEPPOL/UBL/EN16931 validation (including against business rules) can be done online:

- <https://ecosio.com/en/peppol-and-xml-document-validator/>
- <https://app.b2brouter.net/en/validation>

`peppol_invoice_sending.py` contains code for sending the XML invoices via PEPPOL. This is untested and uses a hypothetical PEPPOL endpoint. Here is some open source [peppol code in Java](https://github.com/phax/peppol).

Invoices can also be validated manually via `validate_invoice.py`.

The invoicing code should handle VAT properly for non-EU and Belgian customers (though you should still check!), but non-BE EU customers may not yet be correct. Only labor items (and copyright royalties) are currently supported.

Unusual customer street addresses (like PO Boxes) may need code changes to work perfectly.

#### Requirements and usage:

pip install peppol_invoice_gen
[libreoffice](https://www.libreoffice.org/download/download/) must be installed for PDF generation.


## Notes

### Reimbursements of costs

Need to be careful here, it's not so simple as in non-VAT countries. In the EU, they generally seem to want you to charge VAT on these. The software does not yet support anything here. In most cases you'd want to re-charge the fees with a markup, and then it is subject to VAT. Eg: "Travel expenses: flight and lodging reimbursement per agreement": Price, including markup, subject to normal VAT, quantity 1 (unit code C62).

If it is a pure disbursement on the behalf of the client, this could be marked as out of VAT scope. The VAT category ID code would be O, percent 0.0. This is apparently heavily scrutinized in Belgium and you must have documentation showing the client is the legal debtor (the invoice is issued to the client).

In deciding which is applicable, the key question is who is the beneficiary. Only if the client is the legal owner and direct user of the reibursable service can it be charged as out of scope, presuming you made the payment on their behalf.

In either case, multiple small costs can be regrouped into one "Reimbursible expenses" line. It may be useful to attach supporting documents/receipts.
```xml
<cac:AdditionalDocumentReference>
  <cbc:ID>RECEIPT-123</cbc:ID>
  <cbc:DocumentType>Reimbursement Receipt</cbc:DocumentType>
  <cac:Attachment>
    <cbc:EmbeddedDocumentBinaryObject mimeCode="application/pdf" filename="receipt.pdf" encodingCode="Base64">
      JVBERi0xLjQK... (PDF content)
    </cbc:EmbeddedDocumentBinaryObject>
  </cac:Attachment>
</cac:AdditionalDocumentReference>
```