# simple script for creating an invoice for a single customer
# This should be duplicated and modified for any other clients.
import copy
import os
import sys
from datetime import date
from dateutil.relativedelta import relativedelta

import peppol_invoicing as invoicing
from peppol_invoicing import CYAN, RESET

INVOICE_PATH = "invoices"

## Seller data (invoice issuer)
seller_company_no = '0123456749' # VALID BE company number (checksum == 46)
seller_vat = f"BE{seller_company_no}"
seller_data = {
    'name': 'My Company',
    # seller's address
    'street': 'Avenue du l''Empereur 1', 'city': 'Brussels', 'postal_code': '1000', 'country_code': 'BE', # other possible info: building_name, floor, suite, state
    'vat': seller_vat,
    'legal_registration_id': seller_company_no, # For BT-30; required if VAT omitted
    # seller bank account numbers for receiving payments
    'iban':  'BE1234567891234', 'bic': 'BICCODE',
    # Alternative seller account numbers for a US bank account
    # 'ach_account': '123456789', 'ach_routing': '111222333', 'ach_bank_name': 'Bank of America',
    'contact_email': 'info@mycompany.be',
    # Peppol endpoint
    'endpoint': f"0208:{seller_company_no}" # Correct scheme for BE company number
}

## Buyer Data (invoice recipient)
buyer_company_no = '0987654394' # Valid BE company number (checksum == 21)
buyer_country_code = 'BE'
buyer_vat = f"{buyer_country_code}{buyer_company_no}"  # ASSUMES the relevant country uses the same company and VAT numbers (for BE, it's true)
buyer_endpoint = f"0208:{buyer_company_no}"
buyer_data = {
    'name': 'My Client',
    # buyer's address; same fields available
    'street': 'Avenue Franklin Roosevelt 100', 'suite': 'Suite 6F', 'city': 'Bruxelles', 'postal_code': '1080', 'country_code': buyer_country_code,
    # Company numbers (vat for EU, EIN for US, at most one may be provided). VAT is required for EU countries.
    'vat': 'BE987654321',
    #'ein': '123456789',
    'endpoint': buyer_endpoint, # or None, if not on peppol (eg, most non-EU)
    # 'contact_email': 'finance_contact@myclient.com',
    'legal_registration_id': None,
}

## Reference contract data for services performed
contract_data = {
    'contract_id': 'AGR-2020-01-01',
    'contract_issue_date': '2020-01-01',
    'currency': 'EUR',
    'hourly_rate': 25,
    'work_description': "Consulting Services",
    'max_royalty_pct': 15,
    'monthly_retainer': 200
}

def generate_complete_invoice(hours_worked, delivery_royalties, template_path='templates/human_invoice_template.docx', term_days=30):
    """
    Generates Human-readable .docx invoice, converts it to PDF
    Then generates EN16931-compliant e-Invoice (in two copies, with and without the PDF embedded)

    Billing is based upon hours worked at the contract rate, plus any copyright royalties (in currency units)
    term_days is the number of days until the invoice is due for payment
    """

    if not os.path.exists(INVOICE_PATH):
        os.makedirs(INVOICE_PATH)

    invoice_id = invoicing.get_next_invoice_id(INVOICE_PATH)

    invoice_date = date.today()
    invoice_duedate = date.today() + relativedelta(days=term_days)
    docx_path = os.path.join(INVOICE_PATH, f"{invoice_id}.docx")
    pdf_path = os.path.join(INVOICE_PATH, f"{invoice_id}.pdf")
    xml_path = os.path.join(INVOICE_PATH, f"{invoice_id}.xml")
    xml_path_raw = os.path.join(INVOICE_PATH, f"{invoice_id}-raw.xml")  # no embedded PDF

    billable_month_start = invoicing.get_relevant_month()
    billable_month_text = billable_month_start.strftime('%B')  # %Y for year
    invoice_start_date = billable_month_start.isoformat(); invoice_end_date = (billable_month_start + relativedelta(months=1, days=-1)).isoformat()

    # coded for the XML machine-readable invoice
    invoice_data = {
        'invoice_number': invoice_id,
        'date': invoice_date.strftime('%Y-%m-%d'),
        'due_date': invoice_duedate.strftime('%Y-%m-%d'),
        'payment_terms_note': f"Payment due within {term_days} days.",
        'invoice_period_start_date': invoice_start_date, 'invoice_period_end_date': invoice_end_date,
        'invoice_period_description': f"Services thru {billable_month_text}",
        'items': [
            {'description': f"{contract_data['work_description']} thru {billable_month_text}", 'quantity': hours_worked,
             'unit_price': contract_data['hourly_rate'], 'unit_code': 'HUR'},
            {'description': f"Retainer for {billable_month_text}", 'unit_price': contract_data['monthly_retainer']}, # no quantity => lump sum
            {'description': f"Widgets", 'quantity': 12, 'unit_price': 35.50},
        ],
        'accent_fill_color': '#46a6af'
    }
    # include contract data like currency and contract ID for reference (not all fields are used)
    invoice_data |= contract_data

    # add royalties line if necessary
    if delivery_royalties > 0:
        if delivery_royalties > contract_data['hourly_rate'] * hours_worked * contract_data['max_royalty_pct'] / 100.0:
            print("Error: requested royalties exceed contract maximum")
            return

        invoice_data['items'].append(
            {'description': 'Copyright Licensing (lump sum for delivery)', 'quantity': 1, 'unit_price': delivery_royalties, 'unit_code': 'C62'}
        )

    # TODO: support reimbursements of costs (applicable for non-VAT clients, otherwise billed with VAT)

    # Determine VAT details for the buyer/seller country combination
    vat_details = invoicing.determine_vat_details(buyer_data['country_code'], seller_data['country_code'])
    vat_rate = float(vat_details['rate'])
    vat_category = vat_details['category_code']

    # data used for populating the human readable invoice, based on that for the XML version
    # Note that most of the seller company data is already in the document template
    doc_data = copy.deepcopy(invoice_data)  # allows us to make modifications

    # modifications for docx: add vat_pct per item (XML handles this internally) and clarify descriptions
    for item in doc_data['items']:
        item['vat_pct'] = vat_rate
        if item.get('unit_code', '') == 'HUR':
            item['description'] += " (hours)"

    # VAT-specific notes for the invoice
    terms_text = f"{'Copyright licensing and other t' if delivery_royalties > 0 else 'T'}erms are pursuant to agreement {contract_data['contract_id']}."
    if vat_category == 'O':
        vat_note = "This invoice is VAT exempt under Article 39 of the VAT Code. "
    elif vat_category == 'AE':
        vat_note = "VAT reverse charge under Article 196 of the VAT Directive. "
    else:
        vat_note = ""

    # additions
    doc_data |= {
        'client_name': buyer_data['name'],
        'client_address': invoicing.format_street_address(buyer_data, True),
        'client_vat_line': f"EIN: {invoicing.format_ein(buyer_data.get('ein', ''))}" if buyer_data.get('ein') else f"VAT #: {buyer_data.get('vat', 'n/a')}",
        'client_email': buyer_data.get('contact_email',''),
        'notes': vat_note + terms_text,
    }

    print(f"=== Billing {CYAN}{buyer_data['name']}{RESET} for the month of {CYAN}{billable_month_text}{RESET}, due {CYAN}{doc_data['due_date']}{RESET} ===")
    doc_params = {'table_header_fillcolor': invoice_data['accent_fill_color']} # see other modifiable style parameters in docx_invoice.py

    doc_totals = invoicing.fill_word_invoice(template_path, docx_path, doc_data, doc_params)
    if invoicing.convert_docx_to_pdf(docx_path, pdf_path):
        invoicing.generate_en16931_invoice(xml_path, invoice_data, seller_data, buyer_data, pdf_filename=pdf_path)
    else:
        print("❌ Error converting .docx to .pdf file. PDF will not be embedded into XML.")
        xml_path = xml_path_raw  # use this for further validation

    # generate without pdf in any case
    xml_totals = invoicing.generate_en16931_invoice(xml_path_raw, invoice_data, seller_data, buyer_data)

    # verify that the docx and XML invoices produced the same totals
    if doc_totals and xml_totals:
        for key in ('total_excl_vat', 'total_vat', 'total_incl_vat'):
            if abs(doc_totals[key] - xml_totals[key]) > 0.01:
                print(f"⚠️  WARNING: {key} mismatch between DOCX ({doc_totals[key]}) and XML ({xml_totals[key]})")

    # validate against UBL-2.1 schema. This enforces basic elements, but EN 16931 is stricter and PEPPOL has additional requirements.
    # (You need to use an online (or Java-based) check for those. See validate_invoice.py)
    schema_path = "UBL-2.1/schemas/UBL-Invoice-2.1.xsd"
    succeeded, errors = invoicing.validate_invoice(xml_path, schema_path)
    if succeeded:
        print(f"✅ {xml_path} is valid against UBL-2.1 standard. EN16931 and PEPPOL are unconfirmed.")
    else:
        print(f"❌ {xml_path} has validation errors against the UBL-2.1 standard:")
        for e in errors:
          print(f"  {e}")

    print("=== DONE ===")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print("Usage: python examples/example_invoice.py <hours_worked> [delivery_royalties (0)]")
        sys.exit(1)

    args = sys.argv[1:]
    royalties = 0.0
    if len(args) >= 2:
        royalties = float(args[1])

    generate_complete_invoice(float(args[0]), royalties)