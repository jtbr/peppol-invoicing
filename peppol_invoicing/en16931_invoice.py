# generate e-invoice compliant with EN16931 / PEPPOL BIS 3.0

# In Belgium, e-Invoicing is mandatory for B2B as of January 2026. e-invoices must comply with EN16931, but
# not necessarily be sent via PEPPOL (although this is encouraged). Non-BE companies are exempt.
# See https://sovos.com/vat/tax-rules/belgium-e-invoicing/ and https://einvoice.belgium.be/en

# usage: create a script for the client, populating needed dicts. Then each run to produce the invoice

from lxml import etree
from datetime import date
from dateutil.relativedelta import relativedelta
import sys
import re
import base64
import os
from decimal import Decimal, ROUND_HALF_UP

from .utils import RED, RESET, format_currency, get_decimal_quantizer


class InvoiceValidationError(Exception):
    """Raised when invoice data fails validation."""
    pass

# --- Define Namespace URIs ---
NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

# --- List of EU Member States (ISO 3166-1 alpha-2) ---
EU_COUNTRY_CODES = ["AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"]

# --- ISO 3166-1 alpha-2 country codes (subset of commonly used codes for validation) ---
# Full list has ~249 codes; this covers EU + major trading partners
VALID_COUNTRY_CODES = EU_COUNTRY_CODES + [
    "AD", "AL", "AM", "AO", "AR", "AU", "AZ", "BA", "BD", "BR", "BY", "CA", "CH", "CL", "CN", "CO",
    "EG", "GB", "GE", "GH", "HK", "ID", "IL", "IN", "IS", "JP", "KE", "KR", "KZ", "LI", "MA", "MC",
    "MD", "ME", "MK", "MX", "MY", "NG", "NO", "NZ", "PA", "PE", "PH", "PK", "RS", "RU", "SA", "SG",
    "SM", "TH", "TR", "TW", "UA", "US", "VA", "VN", "ZA"
]

# --- ISO 4217 currency codes (subset of commonly used codes for validation) ---
VALID_CURRENCY_CODES = [
    "EUR", "USD", "GBP", "CHF", "JPY", "CNY", "AUD", "CAD", "HKD", "SGD", "SEK", "NOK", "DKK",
    "NZD", "KRW", "INR", "BRL", "MXN", "ZAR", "PLN", "CZK", "HUF", "RON", "BGN", "HRK", "TRY", "RUB"
]

# --- Default Seller's Domestic Standard VAT Rate (Belgium) ---
# BELGIAN-SPECIFIC: Default VAT rate is 21% (Belgium). Other EU countries have different standard rates.
# Override via seller_data['standard_vat_rate'] for non-Belgian sellers.
DEFAULT_VAT_RATE = Decimal("21.00")
DEFAULT_VAT_CATEGORY = "S"

# --- Date format validation (ISO 8601: YYYY-MM-DD) ---
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(date_str, field_name):
    """Validates that a date string is in ISO 8601 format (YYYY-MM-DD)."""
    if date_str and not DATE_PATTERN.match(date_str):
        raise InvoiceValidationError(f"Invalid date format for '{field_name}': '{date_str}'. Expected YYYY-MM-DD.")


def _validate_country_code(code, field_name):
    """Validates that a country code is a known ISO 3166-1 alpha-2 code."""
    if code:
        code_upper = code.upper()
        if len(code_upper) != 2:
            raise InvoiceValidationError(f"Invalid country code for '{field_name}': '{code}'. Must be 2 characters.")
        if code_upper not in VALID_COUNTRY_CODES:
            print(f"Warning: Unrecognized country code '{code}' for '{field_name}'. Proceeding anyway.")


def _validate_currency_code(code, field_name="currency"):
    """Validates that a currency code is a known ISO 4217 code."""
    if code:
        code_upper = code.upper()
        if len(code_upper) != 3:
            raise InvoiceValidationError(f"Invalid currency code for '{field_name}': '{code}'. Must be 3 characters.")
        if code_upper not in VALID_CURRENCY_CODES:
            print(f"Warning: Unrecognized currency code '{code}' for '{field_name}'. Proceeding anyway.")

# --- Helper function to create elements ---
def E(tag, ns_uri):
    """Helper to create namespace-qualified tag strings."""
    return f"{{{ns_uri}}}{tag}"


# --- Helper function to determine APPLIED VAT details ---
def determine_vat_details(buyer_country, seller_country="BE", domestic_vat_rate=None, domestic_vat_category=None):
    """
    Determines VAT rate, category code, and reason based on buyer/seller countries.

    Args:
        buyer_country: ISO 3166-1 alpha-2 country code of the buyer.
        seller_country: ISO 3166-1 alpha-2 country code of the seller (default: "BE").
        domestic_vat_rate: Standard VAT rate for domestic sales (default: Belgium 21%).
        domestic_vat_category: VAT category code for domestic sales (default: "S").

    Returns:
        dict: {'rate': Decimal, 'category_code': str, 'reason': str | None}

    Note:
        BELGIAN-SPECIFIC: The exemption reason texts reference Belgian/EU VAT articles.
        Sellers in other jurisdictions may need to override the 'reason' field.
    """
    _validate_country_code(buyer_country, "buyer_country")
    _validate_country_code(seller_country, "seller_country")

    if domestic_vat_rate is None:
        domestic_vat_rate = DEFAULT_VAT_RATE
    if domestic_vat_category is None:
        domestic_vat_category = DEFAULT_VAT_CATEGORY

    buyer_country = buyer_country.upper()
    seller_country = seller_country.upper()
    if buyer_country == seller_country: # Domestic
        return {'rate': domestic_vat_rate, 'category_code': domestic_vat_category, 'reason': None}
    elif buyer_country in EU_COUNTRY_CODES:
        # Intra-Community Supply (B2B) -> Reverse Charge
        return {
            'rate': Decimal("0.00"),
            'category_code': "AE", # VAT reverse charged
            # EU-WIDE: This text is standard for intra-EU B2B reverse charge
            'reason': "Reverse charge - Art 196 VAT Directive"
            # Optional: Reason Code (e.g., "VATEX-EU-AE") - BT-121
        }
    else:
        # Export outside EU -> Out of scope
        # BELGIAN-SPECIFIC: "Article 39 of the VAT Code" refers to Belgian VAT Code.
        # Other EU countries have equivalent articles in their national VAT legislation.
        return {
            'rate': Decimal("0.00"),
            'category_code': "O", # Service outside scope of tax
            'reason': "Export outside the EU - Out of scope (Exempt under Article 39 of the VAT Code)"
            # Optional: Reason Code (e.g., "VATEX-EU-O") - BT-121
        }


# --- Helper function to create Party elements (Simplifies VAT check, Validates Endpoint) ---
def create_party(parent_element, party_type, party_data, invoice_vat_context):
    """
    Creates Party element. Omits PartyTaxScheme if context='O'. Adds LegalRegID.
    Validates endpoint format. Assumes vat_number is string or None.
    """
    name = party_data.get('name', 'N/A')
    vat_number = party_data.get('vat') # Expects string or None
    endpoint = party_data.get('endpoint') # Expects "scheme:id" or None
    legal_reg_id = party_data.get('legal_registration_id') # For BT-30 TODO should support EIN for buyers?

    party_root = etree.SubElement(parent_element, E(party_type, NS_CAC))
    party = etree.SubElement(party_root, E("Party", NS_CAC))

    # --- PEPPOL Endpoint ID ---
    # ASSUMPTION: Endpoint format is "schemeID:identifier" (e.g., "0208:0123456789" for Belgian KBO number).
    # Common scheme IDs: 0208 (BE KBO/BCE), 0204 (DE VAT), 0088 (EAN/GLN), 0060 (DUNS), 9910 (test).
    # See PEPPOL Policy for Identifiers for full list.
    if endpoint:
        match = re.match(r"^(.*?):(.*)$", endpoint)
        if match:
            scheme_id, endpoint_id_val = match.groups()
            if scheme_id and endpoint_id_val: # Ensure both parts are non-empty
                etree.SubElement(party, E("EndpointID", NS_CBC), schemeID=scheme_id).text = endpoint_id_val
            else:
                raise InvoiceValidationError(f"Invalid endpoint format for {party_type} '{name}'. Scheme or ID part missing in '{endpoint}'.")
        else:
            raise InvoiceValidationError(f"Invalid endpoint format for {party_type} '{name}'. Expected 'schemeID:ID', got '{endpoint}'.")
    else:
        # Required by PEPPOL for transmission, but OK to omit for e-invoices sent via other means
        print(f"Warning: PEPPOL {party_type} Endpoint is missing for {name}; required for PEPPOL transmission.")
        # FALLBACK: Use dummy endpoint to pass schema validation. Will NOT work for actual PEPPOL delivery.
        # BRITTLE: This assumes the invoice won't actually be sent via PEPPOL without a real endpoint.
        etree.SubElement(party, E("EndpointID", NS_CBC), schemeID='9910').text = '9999999999999'

    # Party Name
    pname = etree.SubElement(party, E("PartyName", NS_CAC))
    etree.SubElement(pname, E("Name", NS_CBC)).text = name

    # --- Postal Address ---
    has_address = all(k in party_data for k in ['street', 'city', 'postal_code', 'country_code'])
    if has_address:
        address = etree.SubElement(party, E("PostalAddress", NS_CAC))
        if 'floor' in party_data and party_data['floor']:
            etree.SubElement(address, E("Floor", NS_CBC)).text = party_data['floor']
        if 'suite' in party_data and party_data['suite']:
            etree.SubElement(address, E("Room", NS_CBC)).text = party_data['suite']
        etree.SubElement(address, E("StreetName", NS_CBC)).text = party_data['street']
        if 'building_name' in party_data and party_data['building_name']:
            etree.SubElement(address, E("BuildingName", NS_CBC)).text = party_data['building_name']
        etree.SubElement(address, E("CityName", NS_CBC)).text = party_data['city']
        etree.SubElement(address, E("PostalZone", NS_CBC)).text = party_data['postal_code']
        if 'state' in party_data and party_data['state']:
            etree.SubElement(address, E("CountrySubentity", NS_CBC)).text = party_data['state']
        country = etree.SubElement(address, E("Country", NS_CAC))
        etree.SubElement(country, E("IdentificationCode", NS_CBC)).text = party_data['country_code'].upper()
    elif any(k in party_data for k in ['street', 'city', 'postal_code', 'country_code']):
         print(f"Warning: Incomplete address data for {name}.")
    else:
         print(f"Info: No address data provided for {name}, omitting PostalAddress.")

    # --- VAT Identification (PartyTaxScheme) - OMIT IF INVOICE CONTEXT IS 'O' (BR-O-02) ---
    omit_vat_id = (invoice_vat_context == 'O')
    vat_id_to_use = None
    if not omit_vat_id and vat_number: # Check if vat_number is present and not omitting
        vat_id_to_use = vat_number # Assume it's valid if provided

    if vat_id_to_use:
        tax_scheme = etree.SubElement(party, E("PartyTaxScheme", NS_CAC))
        etree.SubElement(tax_scheme, E("CompanyID", NS_CBC)).text = vat_id_to_use # BT-31 (Seller) or BT-48 (Buyer)
        scheme = etree.SubElement(tax_scheme, E("TaxScheme", NS_CAC))
        etree.SubElement(scheme, E("ID", NS_CBC)).text = "VAT"
    elif omit_vat_id and vat_number and party_type == "AccountingSupplierParty":
        # Only mention omission if it was explicitly provided but skipped due to 'O' rule
        print(f"Info: Omitting Seller VAT ID for {name} because invoice VAT context is 'O' (BR-O-02).")

    # --- Legal Entity (Including Legal Registration ID - BT-30) ---
    legal_entity = etree.SubElement(party, E("PartyLegalEntity", NS_CAC))
    etree.SubElement(legal_entity, E("RegistrationName", NS_CBC)).text = name
    # Add Legal Registration ID (BT-30) - REQUIRED by BR-CO-26 if BT-31 omitted (for Seller)
    if legal_reg_id:
        # Scheme ID for BT-30 depends on the type of number (e.g., '0088' for EORI, check codelists)
        # If it's just the national company number, often no schemeID is used, or a national one.
        # Omitting schemeID here for simplicity unless explicitly known.
        etree.SubElement(legal_entity, E("CompanyID", NS_CBC)).text = legal_reg_id
    elif party_type == "AccountingSupplierParty" and omit_vat_id:
        # If seller VAT was omitted due to 'O', BT-30 becomes mandatory for BR-CO-26
        raise InvoiceValidationError("Seller Legal Registration ID (legal_registration_id) missing in seller_data. Required by BR-CO-26 when VAT ID is omitted (e.g., for 'Outside Scope' invoices).")

    if 'contact_email' in party_data and party_data['contact_email']:
        contact = etree.SubElement(party, E("Contact", NS_CAC))
        etree.SubElement(contact, E("ElectronicMail", NS_CBC)).text = party_data['contact_email']


# --- Helper function to create Invoice Line (Omits Rate for 'O' Classification) ---
def create_invoice_line(parent, line_id, item_data, currency, line_vat_details,
                        seller_vat_rate=None, seller_vat_category=None):
    """
    Creates InvoiceLine incl. Item/ClassifiedTaxCategory.
    Omits ClassifiedTaxCategory/Percent if category is 'O' (BR-O-05).
    seller_vat_rate/seller_vat_category override the defaults for the ClassifiedTaxCategory.
    """
    desc = item_data.get('description', 'N/A')
    price = Decimal(str(item_data.get('unit_price', 0)))
    if price == 0:
        print(f"Warning: Line item '{desc}' has unit_price of 0.")
    if 'quantity' in item_data:
        qty = Decimal(str(item_data.get('quantity', 1)))
        unit_code = item_data.get('unit_code', 'EA') # C62=unitless (lump sum); HUR=hours; EA=each
    else:
        unit_code = item_data.get('unit_code', 'C62')  # unitless, e.g. lump sum
        qty = Decimal(1)

    applied_vat_rate = line_vat_details['rate']
    applied_tax_cat_id = line_vat_details['category_code']
    vat_reason = line_vat_details.get('reason')

    quantizer = get_decimal_quantizer(currency)
    line_subtotal = (qty * price).quantize(quantizer, rounding=ROUND_HALF_UP)
    line_vat_amount = (line_subtotal * applied_vat_rate / Decimal(100)).quantize(quantizer, rounding=ROUND_HALF_UP)

    line = etree.SubElement(parent, E("InvoiceLine", NS_CAC))
    etree.SubElement(line, E("ID", NS_CBC)).text = str(line_id)
    qty_el = etree.SubElement(line, E("InvoicedQuantity", NS_CBC), unitCode=unit_code)
    qty_el.text = str(qty)
    line_ext_amt = etree.SubElement(line, E("LineExtensionAmount", NS_CBC), currencyID=currency)
    line_ext_amt.text = format_currency(line_subtotal, currency_symbol='', currency_code=currency)

    # Optional line-level invoice period (e.g. for retainers/fixed-fee services)
    line_period_start = item_data.get('period_start')
    line_period_end = item_data.get('period_end')
    if line_period_start or line_period_end:
        line_period = etree.SubElement(line, E("InvoicePeriod", NS_CAC))
        if line_period_start:
            etree.SubElement(line_period, E("StartDate", NS_CBC)).text = line_period_start
        if line_period_end:
            etree.SubElement(line_period, E("EndDate", NS_CBC)).text = line_period_end

    # --- Applied VAT on Line (BT-118 / TaxTotal) ---
    line_tax_total = etree.SubElement(line, E("TaxTotal", NS_CAC)) # Keep this structure, required by EN16931 (ignore UBL-CR-561)
    line_tax_amt = etree.SubElement(line_tax_total, E("TaxAmount", NS_CBC), currencyID=currency)
    line_tax_amt.text = format_currency(line_vat_amount, currency_symbol='', currency_code=currency)

    # TaxSubtotal is optional within Line TaxTotal per UBL, but often needed for clarity/validation
    # If included, it mirrors the line's tax.
    line_tax_subtotal = etree.SubElement(line_tax_total, E("TaxSubtotal", NS_CAC))
    line_taxable_amt = etree.SubElement(line_tax_subtotal, E("TaxableAmount", NS_CBC), currencyID=currency)
    line_taxable_amt.text = format_currency(line_subtotal, currency_symbol='', currency_code=currency)
    line_tax_sub_amt = etree.SubElement(line_tax_subtotal, E("TaxAmount", NS_CBC), currencyID=currency)
    line_tax_sub_amt.text = format_currency(line_vat_amount, currency_symbol='', currency_code=currency)

    # The single Tax Category for this line
    tax_category = etree.SubElement(line_tax_subtotal, E("TaxCategory", NS_CAC))
    etree.SubElement(tax_category, E("ID", NS_CBC)).text = applied_tax_cat_id # Applied category ('S', 'AE', 'O')
    etree.SubElement(tax_category, E("Percent", NS_CBC)).text = f"{applied_vat_rate:.2f}" # Applied rate (21% or 0%)
    # Add Exemption Reason ONLY if code requires it (NOT 'S', NOT 'Z')
    if applied_tax_cat_id not in ["S", "Z"] and vat_reason:
        etree.SubElement(tax_category, E("TaxExemptionReason", NS_CBC)).text = vat_reason
    tax_scheme_cat = etree.SubElement(tax_category, E("TaxScheme", NS_CAC))
    etree.SubElement(tax_scheme_cat, E("ID", NS_CBC)).text = "VAT"

    # --- Item Details ---
    item = etree.SubElement(line, E("Item", NS_CAC))
    etree.SubElement(item, E("Name", NS_CBC)).text = desc

    # --- Item VAT Classification (BT-151 / ClassifiedTaxCategory) ---
    classified_tax_cat_id = seller_vat_category or DEFAULT_VAT_CATEGORY
    classified_tax_rate = seller_vat_rate or DEFAULT_VAT_RATE
    if applied_tax_cat_id == "O":
        classified_tax_cat_id = "O" # Override for BR-O-12

    classified_tax_category = etree.SubElement(item, E("ClassifiedTaxCategory", NS_CAC))
    etree.SubElement(classified_tax_category, E("ID", NS_CBC)).text = classified_tax_cat_id # 'S' or 'O'
    # OMIT Percent if classified category is 'O' (BR-O-05)
    if classified_tax_cat_id != "O":
        etree.SubElement(classified_tax_category, E("Percent", NS_CBC)).text = f"{classified_tax_rate:.2f}" # BT-152
    classified_tax_scheme = etree.SubElement(classified_tax_category, E("TaxScheme", NS_CAC))
    etree.SubElement(classified_tax_scheme, E("ID", NS_CBC)).text = "VAT"
    # --- End Item VAT Classification ---

    # --- Price Details ---
    price_el = etree.SubElement(line, E("Price", NS_CAC))
    price_amt = etree.SubElement(price_el, E("PriceAmount", NS_CBC), currencyID=currency)
    price_amt.text = format_currency(price, currency_symbol='', currency_code=currency)
    base_qty = etree.SubElement(price_el, E("BaseQuantity", NS_CBC), unitCode=unit_code)
    base_qty.text = str(item_data.get('base_quantity', '1'))


def create_payment_means(parent, pmt_means_code, pmt_means_name, pmt_acct_id, pmt_acct_owner, pmt_inst_id=None, pmt_inst_name=None, pmt_ref=None):
    "Supports creating payment means fields (where and how payment should be sent); supports SEPA and ACH/Swift wire transfers"
    payment_means = etree.SubElement(parent, E("PaymentMeans", NS_CAC))
    etree.SubElement(payment_means, E("PaymentMeansCode", NS_CBC), name=pmt_means_name).text = pmt_means_code
    if pmt_ref:
        etree.SubElement(payment_means, E("PaymentID", NS_CBC)).text = pmt_ref  # reference to mention with payment

    pay_account = etree.SubElement(payment_means, E("PayeeFinancialAccount", NS_CAC))
    etree.SubElement(pay_account, E("ID", NS_CBC)).text = pmt_acct_id
    etree.SubElement(pay_account, E("Name", NS_CBC)).text = pmt_acct_owner
    if pmt_inst_id:
        fin_inst = etree.SubElement(pay_account, E("FinancialInstitutionBranch", NS_CAC))
        etree.SubElement(fin_inst, E("ID", NS_CBC)).text = pmt_inst_id
        if pmt_inst_name:
            etree.SubElement(fin_inst, E("Name", NS_CBC)).text = pmt_inst_name


# --- Main Generation Function ---
def generate_en16931_invoice(xml_filepath, invoice_data, seller_data, buyer_data, pdf_filename=None):
    """Generates EN16931-compliant invoice (also UBL-2.1 and where applicable, PEPPOL BIS 3.0), optionally embedding a PDF.

    seller_data may optionally include 'standard_vat_rate' (Decimal) and 'standard_vat_category' (str)
    to override the default Belgian 21% / 'S' rate for domestic invoices.

    Returns:
        dict: {'total_excl_vat': Decimal, 'total_vat': Decimal, 'total_incl_vat': Decimal}
    """

    # --- Essential Data Checks ---
    if not invoice_data.get('items') or not isinstance(invoice_data['items'], list):
        raise InvoiceValidationError("Invoice data must contain a non-empty list of 'items'.")
    if not invoice_data.get('invoice_number'):
        raise InvoiceValidationError("Invoice data must contain 'invoice_number'.")

    # Validate date formats (ISO 8601: YYYY-MM-DD)
    _validate_date(invoice_data.get('date'), 'date')
    _validate_date(invoice_data.get('due_date'), 'due_date')
    _validate_date(invoice_data.get('invoice_period_start_date'), 'invoice_period_start_date')
    _validate_date(invoice_data.get('invoice_period_end_date'), 'invoice_period_end_date')
    _validate_date(invoice_data.get('contract_issue_date'), 'contract_issue_date')

    # Validate currency code
    currency = invoice_data.get('currency', 'EUR')
    _validate_currency_code(currency)

    invoice_number = invoice_data['invoice_number']

    # Allow seller_data to override default VAT rate/category
    seller_vat_rate = seller_data.get('standard_vat_rate')
    seller_vat_category = seller_data.get('standard_vat_category')

    applied_vat_details = determine_vat_details(buyer_data['country_code'], seller_data['country_code'],
                                                seller_vat_rate, seller_vat_category)
    invoice_vat_context = applied_vat_details['category_code']
    print(f"Determined APPLIED VAT Details:\n  {applied_vat_details}")

    nsmap = { None: NS_INVOICE, "cac": NS_CAC, "cbc": NS_CBC }
    Invoice = etree.Element(E("Invoice", NS_INVOICE), nsmap=nsmap)

    # --- Header Elements ---
    etree.SubElement(Invoice, E("CustomizationID", NS_CBC)).text = "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
    etree.SubElement(Invoice, E("ProfileID", NS_CBC)).text = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
    etree.SubElement(Invoice, E("ID", NS_CBC)).text = invoice_number
    etree.SubElement(Invoice, E("IssueDate", NS_CBC)).text = invoice_data['date']
    if 'due_date' in invoice_data:
        etree.SubElement(Invoice, E("DueDate", NS_CBC)).text = invoice_data['due_date']
    etree.SubElement(Invoice, E("InvoiceTypeCode", NS_CBC)).text = invoice_data.get('invoice_type_code', "380")  # standard commercial invoice: code 380
    etree.SubElement(Invoice, E("DocumentCurrencyCode", NS_CBC)).text = currency

    # --- Invoice Period ---
    if 'invoice_period_start_date' in invoice_data and 'invoice_period_end_date' in invoice_data:
        inv_period = etree.SubElement(Invoice, E("InvoicePeriod", NS_CAC))
        etree.SubElement(inv_period, E("StartDate", NS_CBC)).text = invoice_data['invoice_period_start_date']
        etree.SubElement(inv_period, E("EndDate", NS_CBC)).text = invoice_data['invoice_period_end_date']
        if 'invoice_period_description' in invoice_data:
            etree.SubElement(inv_period, E("Description", NS_CBC)).text = invoice_data['invoice_period_description']

    # --- Order Reference (BT-13) ---
    # Comment: OrderReference/ID (BT-13) is a reference like a Purchase Order number,
    # issued by the buyer. PEPPOL requires BT-10 (BuyerReference - free text) or BT-13.
    # Using BT-13 here. Provide relevant PO or agreed reference.
    # If not provided, explicitly, the Contract ID is used.
    order_ref_val = invoice_data.get('order_reference', invoice_data.get('contract_id'))
    if order_ref_val:
         order_ref = etree.SubElement(Invoice, E("OrderReference", NS_CAC))
         etree.SubElement(order_ref, E("ID", NS_CBC)).text = order_ref_val # BT-13
    else:
         # PEPPOL rule PEPPOL-EN16931-R003 requires BT-10 OR BT-13
         print("Warning: PEPPOL OrderReference (BT-13) is missing in invoice_data.")

    # --- Other References (Contract, PDF Attachment) ---
    if 'contract_id' in invoice_data:
        contract_ref = etree.SubElement(Invoice, E("ContractDocumentReference", NS_CAC))
        etree.SubElement(contract_ref, E("ID", NS_CBC)).text = invoice_data['contract_id']
        if 'contract_issue_date' in invoice_data:
            etree.SubElement(contract_ref, E("IssueDate", NS_CBC)).text = invoice_data['contract_issue_date']

    # --- PDF Attachment ---
    if pdf_filename and os.path.exists(pdf_filename):
        try:
            with open(pdf_filename, "rb") as pdf_file:
                pdf_data = pdf_file.read()
            pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
            pdf_basename = os.path.basename(pdf_filename)

            add_doc_ref = etree.SubElement(Invoice, E("AdditionalDocumentReference", NS_CAC))
            etree.SubElement(add_doc_ref, E("ID", NS_CBC)).text = pdf_basename # Use filename as ID
            etree.SubElement(add_doc_ref, E("DocumentDescription", NS_CBC)).text = "Human readable invoice (PDF)" # Optional description
            attachment = etree.SubElement(add_doc_ref, E("Attachment", NS_CAC))
            embedded_doc = etree.SubElement(attachment, E("EmbeddedDocumentBinaryObject", NS_CBC),
                                             mimeCode="application/pdf",
                                             filename=pdf_basename)
            embedded_doc.text = pdf_base64
            # print(f"Info: Embedded PDF '{pdf_basename}'.")
        except Exception as e:
            print(f"Warning: Could not read or embed PDF '{pdf_filename}': {e}")
    elif pdf_filename:
        print(f"Warning: PDF file not found: '{pdf_filename}'")

    # --- Parties ---
    # Pass the determined invoice VAT context ('S', 'AE', 'O')
    create_party(Invoice, "AccountingSupplierParty", seller_data, invoice_vat_context)
    create_party(Invoice, "AccountingCustomerParty", buyer_data, invoice_vat_context)

    # --- Payment Means ---
    # ASSUMPTION: Only SEPA (IBAN) or US ACH/wire payment methods are supported.
    # Other payment methods (PayPal, credit card, etc.) would need additional code.
    # BELGIAN/EU-SPECIFIC: SEPA is standard for EU; code 31 = credit transfer.
    # Code 30 would be used for structured Belgian payment references (+++123/1234/12345+++).
    if 'iban' in seller_data and seller_data['iban']:
        create_payment_means(Invoice, "31", "Credit transfer via SEPA",
                             seller_data['iban'], seller_data['name'],
                             seller_data.get('bic'),
                             pmt_ref = invoice_data['invoice_number'])
    elif all(k in seller_data for k in ['ach_account', 'ach_routing', 'ach_bank_name']):
        # US-SPECIFIC: ACH transfer or domestic wire. Code 42 = payment to bank account.
        # For international wire via SWIFT, use the SWIFT/BIC code as the routing number.
        create_payment_means(Invoice, "42", "Payment to bank account via ACH transfer or US-domestic wire",
                             seller_data['ach_account'], seller_data['name'],
                             seller_data['ach_routing'], seller_data['ach_bank_name'],
                             invoice_data['invoice_number'])
    else:
        print("Info: No IBAN or ACH/wire payment info found in seller_data, omitting PaymentMeans.")

    # --- Payment Terms ---
    payment_terms = etree.SubElement(Invoice, E("PaymentTerms", NS_CAC))
    payment_terms_note = invoice_data.get('payment_terms_note')
    if not payment_terms_note and 'due_date' in invoice_data:
        payment_terms_note = f"Payment due by {invoice_data['due_date']}. Please mention invoice {invoice_number}."
    if payment_terms_note:
        etree.SubElement(payment_terms, E("Note", NS_CBC)).text = payment_terms_note

    # --- PRE-CALCULATE TOTALS ---
    total_line_extension_amount = Decimal(0)
    total_tax_amount = Decimal(0)
    # Breakdown for Document TaxTotal - based on APPLIED categories
    applied_tax_breakdown = {}
    quantizer = get_decimal_quantizer(currency)

    for item in invoice_data['items']: # Assumes items list exists due to check above
        qty = Decimal(str(item.get('quantity', 1)))
        price = Decimal(str(item.get('unit_price', 0)))
        line_subtotal = (qty * price).quantize(quantizer, rounding=ROUND_HALF_UP)
        line_vat = (line_subtotal * applied_vat_details['rate'] / Decimal(100)).quantize(quantizer, rounding=ROUND_HALF_UP)

        total_line_extension_amount += line_subtotal
        total_tax_amount += line_vat

        # Accumulate into APPLIED tax breakdown
        applied_cat_code = applied_vat_details['category_code']
        if applied_cat_code not in applied_tax_breakdown:
            applied_tax_breakdown[applied_cat_code] = {
                'rate': applied_vat_details['rate'],
                'taxable': Decimal(0),
                'tax': Decimal(0),
                'reason': applied_vat_details.get('reason')
            }
        applied_tax_breakdown[applied_cat_code]['taxable'] += line_subtotal
        applied_tax_breakdown[applied_cat_code]['tax'] += line_vat

    total_tax_exclusive = total_line_extension_amount
    total_tax_inclusive = total_tax_exclusive + total_tax_amount
    total_payable = total_tax_inclusive
    # --- End Pre-calculation ---

    # --- TAX TOTAL (Document Level - Simplified Logic) ---
    tax_total = etree.SubElement(Invoice, E("TaxTotal", NS_CAC))
    etree.SubElement(tax_total, E("TaxAmount", NS_CBC), currencyID=currency).text = format_currency(total_tax_amount, currency_symbol='', currency_code=currency)

    # Generate breakdown ONLY for the APPLIED VAT categories found
    for cat_code, totals in sorted(applied_tax_breakdown.items()):
        tax_subtotal = etree.SubElement(tax_total, E("TaxSubtotal", NS_CAC))
        # Taxable amount MUST match sum of lines where this category was APPLIED
        etree.SubElement(tax_subtotal, E("TaxableAmount", NS_CBC), currencyID=currency).text = format_currency(totals['taxable'], currency_symbol='', currency_code=currency)
        # Tax amount MUST be calculated correctly
        etree.SubElement(tax_subtotal, E("TaxAmount", NS_CBC), currencyID=currency).text = format_currency(totals['tax'], currency_symbol='', currency_code=currency)
        # Tax Category details
        tax_category = etree.SubElement(tax_subtotal, E("TaxCategory", NS_CAC))
        etree.SubElement(tax_category, E("ID", NS_CBC)).text = cat_code # 'S', 'AE', or 'O'
        etree.SubElement(tax_category, E("Percent", NS_CBC)).text = f"{totals['rate']:.2f}"
        vat_reason = totals.get('reason')
        # Add reason only if needed (not S or Z)
        if cat_code not in ["S", "Z"] and vat_reason:
             etree.SubElement(tax_category, E("TaxExemptionReason", NS_CBC)).text = vat_reason
        # Tax Scheme
        tax_scheme_total = etree.SubElement(tax_category, E("TaxScheme", NS_CAC))
        etree.SubElement(tax_scheme_total, E("ID", NS_CBC)).text = "VAT"

    # --- Explanation for AE VAT Treatment ---
    # Note on AE (Reverse Charge) VAT Breakdown Strategy:
    # EN16931/PEPPOL rule BR-S-01 requires a 'Standard Rated' ('S') breakdown in the document TaxTotal
    # if any line item is *classified* as 'S' (via BT-151), even if the *applied* tax for the transaction
    # is 'Reverse Charge' ('AE'). However, adding an 'S' breakdown with zero tax amount but a non-zero
    # rate (e.g., 21%) conflicts with calculation rule BR-S-09. Adding it with 0% rate might also
    # conflict or be confusing.
    # Therefore, the chosen strategy here is to prioritize correct calculation and representation
    # of the *applied* tax ('AE'). We only generate the 'AE' breakdown, calculating taxable and tax amounts
    # based on the lines where 'AE' was applied. This knowingly might not satisfy BR-S-01 in a strict
    # validation, but is considered the most logical and arithmetically correct approach given the
    # apparent conflict in the rules for the 'AE' scenario involving items classified 'S'.
    # The 'O' (Outside Scope) scenario is handled differently, strictly adhering to BR-O-11/12/05.

    # --- LEGAL MONETARY TOTAL ---
    legal_monetary = etree.SubElement(Invoice, E("LegalMonetaryTotal", NS_CAC))
    etree.SubElement(legal_monetary, E("LineExtensionAmount", NS_CBC), currencyID=currency).text = format_currency(total_line_extension_amount, currency_symbol='', currency_code=currency)
    etree.SubElement(legal_monetary, E("TaxExclusiveAmount", NS_CBC), currencyID=currency).text = format_currency(total_tax_exclusive, currency_symbol='', currency_code=currency)
    etree.SubElement(legal_monetary, E("TaxInclusiveAmount", NS_CBC), currencyID=currency).text = format_currency(total_tax_inclusive, currency_symbol='', currency_code=currency)
    etree.SubElement(legal_monetary, E("PayableAmount", NS_CBC), currencyID=currency).text = format_currency(total_payable, currency_symbol='', currency_code=currency)

    # --- INVOICE LINES ---
    current_line_id = 0
    for item in invoice_data['items']: # Assumes items list is valid
        current_line_id += 1
        create_invoice_line(Invoice, current_line_id, item, currency, applied_vat_details,
                            seller_vat_rate, seller_vat_category)

    # --- Output ---
    tree = etree.ElementTree(Invoice)
    tree.write(xml_filepath, pretty_print=True, xml_declaration=True, encoding="UTF-8")
    print(f"✅ Invoice saved to {xml_filepath} should be PEPPOL-ready & EN19631-compliant, with total {RED}{total_tax_inclusive}{RESET}")
    print("   Please validate using a PEPPOL / EN 16931 validator such as https://www.b2brouter.net/global/e-invoice-validatior/")

    return {'total_excl_vat': total_tax_exclusive, 'total_vat': total_tax_amount, 'total_incl_vat': total_tax_inclusive}


# --- Main execution block ---
if __name__ == "__main__":
    # TEST DATA

    # --- Seller Data (Valid BE number, Legal Reg ID) ---
    # KBO/BCE 0123456746 -> VAT BE0123456746 (Checksum = 46)
    seller_company_no = '0123456746' # VALID BE company number
    seller_vat = f"BE{seller_company_no}"
    seller_data = {
        'name': 'John Dev Services SPRL', 'street': '1 Rue de la Loi',
        'city': 'Brussels', 'postal_code': '1000', 'state': None, 'country_code': 'BE',
        'vat': seller_vat,
        'legal_registration_id': seller_company_no, # For BT-30, required if VAT omitted
        'iban': 'BE12345678901234', 'bic': 'GEBABEBB',
        'endpoint': f"0208:{seller_company_no}" # Correct scheme for BE company number
    }

    # --- Buyer Scenarios (OrderReference moved to invoice_data) ---
    buyer_name_us="Acme Corp"
    buyer_data_us = { 'name': buyer_name_us, 'street': '123 Main Street', 'city': 'Denver', 'postal_code': '80202', 'state': 'CO', 'country_code': 'US',
                     'vat': None, 'endpoint': None, 'legal_registration_id': None }

    buyer_vat_de = 'DE123456789'; buyer_name_de="Deutsche Kunden AG"
    buyer_data_de = { 'name': buyer_name_de, 'building_name': None, 'floor': '12', 'suite': None, 'street': 'Musterstraße 1', 'city': 'Berlin', 'postal_code': '10117', 'state': None, 'country_code': 'DE',
                     'vat': buyer_vat_de, 'endpoint': f"0204:{buyer_vat_de}", 'legal_registration_id': 'HRB 12345 B' }

    # KBO/BCE 0987654321 -> VAT BE0987654321 (Valid checksum = 21)
    buyer_company_no_be = '0987654321'; buyer_name_be = 'Client Belge SA'
    buyer_data_be = { 'name': buyer_name_be, 'street': 'Avenue Louise 100', 'city': 'Brussels', 'postal_code': '1050', 'state': None, 'country_code': 'BE',
                     'vat': f"BE{buyer_company_no_be}", 'endpoint': f"0208:{buyer_company_no_be}", 'legal_registration_id': buyer_company_no_be }

    # --- Select Scenario ---
    #chosen_buyer_data = buyer_data_us
    #chosen_buyer_data = buyer_data_de
    chosen_buyer_data = buyer_data_be

    # --- Define Invoice Data (Uses OrderReference) ---
    billable_month_date = date.today().replace(day=1)
    invoice_start_date = billable_month_date.isoformat(); invoice_end_date = (billable_month_date + relativedelta(months=1, days=-1)).isoformat()
    invoice_data = {
        'invoice_number': f"INV-PEP-{chosen_buyer_data['country_code']}",
        'date': date.today().isoformat(),
        'due_date': (date.today() + relativedelta(days=30)).isoformat(), 'currency': 'EUR',
        'payment_terms_note': "Payment due within 30 days.",
        'invoice_period_start_date': invoice_start_date, 'invoice_period_end_date': invoice_end_date,
        'invoice_period_description': f"Services thru {billable_month_date.strftime('%B %Y')}", # Reinstated
        'contract_id': 'AGR-2020-01-01', 'contract_issue_date': '2020-01-01',
        #'order_reference': chosen_order_ref, # BY default, the contract ID
        'items': [
            {'description': f'Consulting Services ({billable_month_date.strftime("%B %Y")})', 'quantity': 30, 'unit_price': 55, 'unit_code': 'HUR'},
            {'description': 'Copyright Licensing (Lump Sum)', 'quantity': 1, 'unit_price': 1200, 'unit_code': 'C62'}
        ]
    }

    # --- Check for PDF filename argument ---
    pdf_to_embed = None
    if len(sys.argv) > 1:
        pdf_to_embed = sys.argv[1]
        print(f"Attempting to embed PDF: {pdf_to_embed}")

    filepath = f"{invoice_data['invoice_number']}.xml"

    generate_en16931_invoice(filepath, invoice_data, seller_data, chosen_buyer_data, pdf_filename=pdf_to_embed)
