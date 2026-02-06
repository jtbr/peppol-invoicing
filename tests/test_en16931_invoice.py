"""
Unit tests for peppol_invoicing.en16931_invoice module.
"""

import unittest
import sys
import os
import tempfile
from decimal import Decimal
from datetime import date
from lxml import etree

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from peppol_invoicing.en16931_invoice import (
    determine_vat_details,
    generate_en16931_invoice,
    InvoiceValidationError,
    _validate_date,
    _validate_country_code,
    _validate_currency_code,
    EU_COUNTRY_CODES,
    VALID_COUNTRY_CODES,
    VALID_CURRENCY_CODES,
    DEFAULT_VAT_RATE,
)


class TestDetermineVatDetails(unittest.TestCase):
    """Tests for VAT determination based on buyer/seller countries."""

    def test_domestic_sale_belgium(self):
        """Domestic BE-to-BE sale should have standard VAT."""
        result = determine_vat_details('BE', 'BE')
        self.assertEqual(result['rate'], Decimal('21.00'))
        self.assertEqual(result['category_code'], 'S')
        self.assertIsNone(result['reason'])

    def test_intra_eu_sale(self):
        """Intra-EU B2B sale should be reverse charge."""
        result = determine_vat_details('DE', 'BE')  # German buyer, Belgian seller
        self.assertEqual(result['rate'], Decimal('0.00'))
        self.assertEqual(result['category_code'], 'AE')
        self.assertIn('Reverse charge', result['reason'])

    def test_export_outside_eu(self):
        """Export outside EU should be out of scope."""
        result = determine_vat_details('US', 'BE')  # US buyer, Belgian seller
        self.assertEqual(result['rate'], Decimal('0.00'))
        self.assertEqual(result['category_code'], 'O')
        self.assertIn('Out of scope', result['reason'])

    def test_custom_vat_rate(self):
        """Custom domestic VAT rate should be applied."""
        result = determine_vat_details('DE', 'DE', domestic_vat_rate=Decimal('19.00'))
        self.assertEqual(result['rate'], Decimal('19.00'))
        self.assertEqual(result['category_code'], 'S')

    def test_custom_vat_category(self):
        """Custom VAT category should be applied."""
        result = determine_vat_details('BE', 'BE', domestic_vat_category='Z')
        self.assertEqual(result['category_code'], 'Z')

    def test_case_insensitive_country_codes(self):
        """Country codes should be case-insensitive."""
        result1 = determine_vat_details('be', 'BE')
        result2 = determine_vat_details('BE', 'be')
        self.assertEqual(result1['category_code'], 'S')
        self.assertEqual(result2['category_code'], 'S')


class TestValidationFunctions(unittest.TestCase):
    """Tests for input validation functions."""

    def test_validate_date_valid(self):
        """Valid ISO dates should not raise."""
        # Should not raise
        _validate_date('2025-01-15', 'test_date')
        _validate_date('2025-12-31', 'test_date')
        _validate_date(None, 'test_date')  # None is allowed

    def test_validate_date_invalid(self):
        """Invalid date formats should raise InvoiceValidationError."""
        with self.assertRaises(InvoiceValidationError):
            _validate_date('2025/01/15', 'test_date')
        with self.assertRaises(InvoiceValidationError):
            _validate_date('15-01-2025', 'test_date')
        with self.assertRaises(InvoiceValidationError):
            _validate_date('Jan 15, 2025', 'test_date')

    def test_validate_country_code_valid(self):
        """Valid country codes should not raise."""
        for code in ['BE', 'DE', 'US', 'JP']:
            _validate_country_code(code, 'test_country')

    def test_validate_country_code_invalid_length(self):
        """Invalid length country codes should raise."""
        with self.assertRaises(InvoiceValidationError):
            _validate_country_code('BEL', 'test_country')
        with self.assertRaises(InvoiceValidationError):
            _validate_country_code('B', 'test_country')

    def test_validate_currency_code_valid(self):
        """Valid currency codes should not raise."""
        for code in ['EUR', 'USD', 'GBP', 'JPY']:
            _validate_currency_code(code, 'test_currency')

    def test_validate_currency_code_invalid_length(self):
        """Invalid length currency codes should raise."""
        with self.assertRaises(InvoiceValidationError):
            _validate_currency_code('EU', 'test_currency')
        with self.assertRaises(InvoiceValidationError):
            _validate_currency_code('EURO', 'test_currency')


class TestCountryCodeLists(unittest.TestCase):
    """Tests for country and currency code lists."""

    def test_eu_country_codes(self):
        """EU country codes list should contain all EU members."""
        expected_eu = ['AT', 'BE', 'BG', 'CY', 'CZ', 'DE', 'DK', 'EE', 'ES',
                       'FI', 'FR', 'GR', 'HR', 'HU', 'IE', 'IT', 'LT', 'LU',
                       'LV', 'MT', 'NL', 'PL', 'PT', 'RO', 'SE', 'SI', 'SK']
        for code in expected_eu:
            self.assertIn(code, EU_COUNTRY_CODES, f"{code} should be in EU_COUNTRY_CODES")

    def test_eu_codes_in_valid_codes(self):
        """All EU codes should be in valid country codes."""
        for code in EU_COUNTRY_CODES:
            self.assertIn(code, VALID_COUNTRY_CODES)

    def test_common_currencies(self):
        """Common currencies should be in valid list."""
        for code in ['EUR', 'USD', 'GBP', 'CHF', 'JPY']:
            self.assertIn(code, VALID_CURRENCY_CODES)


class TestGenerateInvoice(unittest.TestCase):
    """Tests for invoice generation."""

    def setUp(self):
        """Set up test data."""
        self.seller_data = {
            'name': 'Test Seller SPRL',
            'street': 'Test Street 1',
            'city': 'Brussels',
            'postal_code': '1000',
            'country_code': 'BE',
            'vat': 'BE0123456749',
            'legal_registration_id': '0123456749',
            'iban': 'BE68539007547034',
            'bic': 'KREDBEBB',
            'endpoint': '0208:0123456749',
        }
        self.buyer_data = {
            'name': 'Test Buyer SA',
            'street': 'Buyer Street 10',
            'city': 'Brussels',
            'postal_code': '1050',
            'country_code': 'BE',
            'vat': 'BE0987654394',
            'endpoint': '0208:0987654394',
            'legal_registration_id': '0987654394',
        }
        self.invoice_data = {
            'invoice_number': 'TEST-001',
            'date': '2025-01-15',
            'due_date': '2025-02-15',
            'currency': 'EUR',
            'items': [
                {'description': 'Test Service', 'quantity': 10, 'unit_price': 100},
            ],
        }

    def test_generate_invoice_creates_file(self):
        """Invoice generation should create an XML file."""
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as f:
            filepath = f.name

        try:
            result = generate_en16931_invoice(
                filepath, self.invoice_data, self.seller_data, self.buyer_data
            )
            self.assertTrue(os.path.exists(filepath))
            self.assertIn('total_excl_vat', result)
            self.assertIn('total_vat', result)
            self.assertIn('total_incl_vat', result)
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_generate_invoice_valid_xml(self):
        """Generated invoice should be valid XML."""
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as f:
            filepath = f.name

        try:
            generate_en16931_invoice(
                filepath, self.invoice_data, self.seller_data, self.buyer_data
            )
            # Should parse without error
            tree = etree.parse(filepath)
            root = tree.getroot()
            self.assertIn('Invoice', root.tag)
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_generate_invoice_totals_domestic(self):
        """Domestic invoice totals should include VAT."""
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as f:
            filepath = f.name

        try:
            result = generate_en16931_invoice(
                filepath, self.invoice_data, self.seller_data, self.buyer_data
            )
            # 10 * 100 = 1000 EUR excl VAT
            self.assertEqual(result['total_excl_vat'], Decimal('1000.00'))
            # 1000 * 21% = 210 EUR VAT
            self.assertEqual(result['total_vat'], Decimal('210.00'))
            # Total incl VAT = 1210 EUR
            self.assertEqual(result['total_incl_vat'], Decimal('1210.00'))
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_generate_invoice_totals_export(self):
        """Export invoice totals should have zero VAT."""
        self.buyer_data['country_code'] = 'US'
        self.buyer_data['vat'] = None
        self.buyer_data['endpoint'] = None

        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as f:
            filepath = f.name

        try:
            result = generate_en16931_invoice(
                filepath, self.invoice_data, self.seller_data, self.buyer_data
            )
            self.assertEqual(result['total_excl_vat'], Decimal('1000.00'))
            self.assertEqual(result['total_vat'], Decimal('0.00'))
            self.assertEqual(result['total_incl_vat'], Decimal('1000.00'))
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_generate_invoice_missing_items(self):
        """Invoice without items should raise error."""
        self.invoice_data['items'] = []
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as f:
            filepath = f.name

        try:
            with self.assertRaises(InvoiceValidationError):
                generate_en16931_invoice(
                    filepath, self.invoice_data, self.seller_data, self.buyer_data
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_generate_invoice_missing_invoice_number(self):
        """Invoice without invoice number should raise error."""
        del self.invoice_data['invoice_number']
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as f:
            filepath = f.name

        try:
            with self.assertRaises(InvoiceValidationError):
                generate_en16931_invoice(
                    filepath, self.invoice_data, self.seller_data, self.buyer_data
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_generate_invoice_invalid_date(self):
        """Invoice with invalid date format should raise error."""
        self.invoice_data['date'] = '15/01/2025'
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as f:
            filepath = f.name

        try:
            with self.assertRaises(InvoiceValidationError):
                generate_en16931_invoice(
                    filepath, self.invoice_data, self.seller_data, self.buyer_data
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)


class TestVatRounding(unittest.TestCase):
    """Tests for VAT rounding (per-rate, not per-line)."""

    def setUp(self):
        """Set up test data with multiple lines."""
        self.seller_data = {
            'name': 'Test Seller',
            'street': 'Test Street 1',
            'city': 'Brussels',
            'postal_code': '1000',
            'country_code': 'BE',
            'vat': 'BE0123456749',
            'legal_registration_id': '0123456749',
            'endpoint': '0208:0123456749',
        }
        self.buyer_data = {
            'name': 'Test Buyer',
            'street': 'Buyer Street 10',
            'city': 'Brussels',
            'postal_code': '1050',
            'country_code': 'BE',
            'vat': 'BE0987654394',
            'endpoint': '0208:0987654394',
            'legal_registration_id': '0987654394',
        }

    def test_vat_rounded_per_rate_not_per_line(self):
        """VAT should be rounded once per rate, not per line.

        Per-line rounding: 3 * round(10.01 * 0.21) = 3 * 2.10 = 6.30
        Per-rate rounding: round(30.03 * 0.21) = round(6.3063) = 6.31
        """
        invoice_data = {
            'invoice_number': 'TEST-ROUND',
            'date': '2025-01-15',
            'currency': 'EUR',
            'items': [
                {'description': 'Item 1', 'quantity': 1, 'unit_price': Decimal('10.01')},
                {'description': 'Item 2', 'quantity': 1, 'unit_price': Decimal('10.01')},
                {'description': 'Item 3', 'quantity': 1, 'unit_price': Decimal('10.01')},
            ],
        }

        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as f:
            filepath = f.name

        try:
            result = generate_en16931_invoice(
                filepath, invoice_data, self.seller_data, self.buyer_data
            )
            # Total excl VAT: 30.03
            self.assertEqual(result['total_excl_vat'], Decimal('30.03'))
            # VAT per-rate (correct): round(30.03 * 0.21) = 6.31
            # VAT per-line (wrong): 3 * round(10.01 * 0.21) = 6.30
            self.assertEqual(result['total_vat'], Decimal('6.31'))
            self.assertEqual(result['total_incl_vat'], Decimal('36.34'))
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)


if __name__ == '__main__':
    unittest.main(verbosity=2)
