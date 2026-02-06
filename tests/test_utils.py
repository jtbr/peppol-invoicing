"""
Unit tests for peppol_invoicing.utils module.
"""

import unittest
import sys
import os
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from io import StringIO

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from peppol_invoicing.utils import (
    validate_belgian_company_number,
    format_belgian_company_number,
    format_currency,
    get_currency_decimals,
    get_currency_symbol,
    get_decimal_quantizer,
    get_currency_quantizer,
    format_street_address,
    get_relevant_month,
    format_ein,
    CURRENCY_DECIMALS,
    CURRENCY_SYMBOLS,
)


class TestBelgianCompanyNumber(unittest.TestCase):
    """Tests for Belgian company number validation and formatting."""

    def test_valid_company_numbers(self):
        """Valid Belgian company numbers should pass validation."""
        valid_numbers = [
            '0123456749',  # 97 - (1234567 % 97) = 49
            '0987654394',  # 97 - (9876543 % 97) = 94
            '0441797980',  # Real format example
            '0000000196',  # Edge case with leading zeros
        ]
        for num in valid_numbers:
            with self.subTest(num=num):
                self.assertTrue(
                    validate_belgian_company_number(num),
                    f"{num} should be valid"
                )

    def test_invalid_company_numbers(self):
        """Invalid Belgian company numbers should fail validation."""
        invalid_numbers = [
            '0123456746',  # Wrong checksum (should be 49)
            '0987654321',  # Wrong checksum (should be 94)
            '1234567890',  # Doesn't start with 0, wrong checksum
            '0000000000',  # All zeros - checksum would be 97, invalid
        ]
        for num in invalid_numbers:
            with self.subTest(num=num):
                self.assertFalse(
                    validate_belgian_company_number(num),
                    f"{num} should be invalid"
                )

    def test_invalid_formats(self):
        """Non-numeric or wrong-length inputs should fail."""
        invalid_inputs = [
            '123456789',    # Only 9 digits
            '12345678901',  # 11 digits
            'ABCDEFGHIJ',   # Letters
            '01234567.49',  # Contains dot
            '',             # Empty
            None,           # None
        ]
        for inp in invalid_inputs:
            with self.subTest(inp=inp):
                self.assertFalse(validate_belgian_company_number(inp))

    def test_integer_input(self):
        """Should accept integer input."""
        # 123456749 as int (leading zero implicit)
        self.assertTrue(validate_belgian_company_number(123456749))

    def test_format_valid_number(self):
        """Formatting valid numbers should return dotted format."""
        result = format_belgian_company_number('0123456749')
        self.assertEqual(result, '0123.456.749')

    def test_format_invalid_number_with_validation(self):
        """Formatting invalid numbers with validation should return None."""
        result = format_belgian_company_number('0123456746', validate=True)
        self.assertIsNone(result)

    def test_format_invalid_number_without_validation(self):
        """Formatting invalid numbers without validation should still format."""
        result = format_belgian_company_number('0123456746', validate=False)
        self.assertEqual(result, '0123.456.746')


class TestCurrencyFunctions(unittest.TestCase):
    """Tests for currency-related functions."""

    def test_get_currency_decimals_standard(self):
        """Standard currencies should have 2 decimals."""
        self.assertEqual(get_currency_decimals('EUR'), 2)
        self.assertEqual(get_currency_decimals('USD'), 2)
        self.assertEqual(get_currency_decimals('GBP'), 2)

    def test_get_currency_decimals_zero(self):
        """Zero-decimal currencies."""
        self.assertEqual(get_currency_decimals('JPY'), 0)
        self.assertEqual(get_currency_decimals('KRW'), 0)

    def test_get_currency_decimals_three(self):
        """Three-decimal currencies."""
        self.assertEqual(get_currency_decimals('KWD'), 3)
        self.assertEqual(get_currency_decimals('BHD'), 3)

    def test_get_currency_decimals_unknown(self):
        """Unknown currencies should default to 2."""
        self.assertEqual(get_currency_decimals('XYZ'), 2)

    def test_get_currency_symbol(self):
        """Known currencies should return their symbols."""
        self.assertEqual(get_currency_symbol('EUR'), '€')
        self.assertEqual(get_currency_symbol('USD'), '$')
        self.assertEqual(get_currency_symbol('GBP'), '£')

    def test_get_currency_symbol_unknown(self):
        """Unknown currencies should return the code itself."""
        self.assertEqual(get_currency_symbol('XYZ'), 'XYZ')

    def test_get_decimal_quantizer(self):
        """Quantizers should produce correct decimal places when used with ROUND_HALF_UP."""
        # Test by applying quantizer and checking result
        # All currency formatting in the codebase uses ROUND_HALF_UP
        eur_q = get_decimal_quantizer('EUR')
        jpy_q = get_decimal_quantizer('JPY')
        kwd_q = get_decimal_quantizer('KWD')

        # EUR: 2 decimal places
        self.assertEqual(Decimal('1.234').quantize(eur_q, rounding=ROUND_HALF_UP), Decimal('1.23'))
        # JPY: 0 decimal places
        self.assertEqual(Decimal('1234.5').quantize(jpy_q, rounding=ROUND_HALF_UP), Decimal('1235'))
        # KWD: 3 decimal places
        self.assertEqual(Decimal('1.2345').quantize(kwd_q, rounding=ROUND_HALF_UP), Decimal('1.235'))

    def test_get_currency_quantizer(self):
        """Currency quantizer function should include ROUND_HALF_UP automatically."""
        # get_currency_quantizer returns a function with ROUND_HALF_UP baked in
        eur_quantize = get_currency_quantizer('EUR')
        jpy_quantize = get_currency_quantizer('JPY')
        kwd_quantize = get_currency_quantizer('KWD')

        # EUR: 2 decimal places, ROUND_HALF_UP
        self.assertEqual(eur_quantize(Decimal('1.234')), Decimal('1.23'))
        self.assertEqual(eur_quantize(Decimal('1.235')), Decimal('1.24'))  # .5 rounds up

        # JPY: 0 decimal places, ROUND_HALF_UP
        self.assertEqual(jpy_quantize(Decimal('1234.4')), Decimal('1234'))
        self.assertEqual(jpy_quantize(Decimal('1234.5')), Decimal('1235'))  # .5 rounds up

        # KWD: 3 decimal places, ROUND_HALF_UP
        self.assertEqual(kwd_quantize(Decimal('1.2344')), Decimal('1.234'))
        self.assertEqual(kwd_quantize(Decimal('1.2345')), Decimal('1.235'))  # .5 rounds up

    def test_format_currency_basic(self):
        """Basic currency formatting."""
        result = format_currency(Decimal('1234.567'), currency_code='EUR')
        self.assertEqual(result, '€1234.57')  # Rounded, with symbol

    def test_format_currency_no_symbol(self):
        """Currency formatting without symbol."""
        result = format_currency(Decimal('1234.56'), currency_symbol='', currency_code='EUR')
        self.assertEqual(result, '1234.56')

    def test_format_currency_symbol_after(self):
        """Currency formatting with symbol after amount."""
        result = format_currency(Decimal('1234.56'), currency_symbol='€', currency_first=False)
        # Check that amount and symbol are present (space type may vary)
        self.assertIn('1234.56', result)
        self.assertIn('€', result)
        self.assertTrue(result.endswith('€'))

    def test_format_currency_jpy_no_decimals(self):
        """JPY should have no decimal places."""
        result = format_currency(Decimal('1234.56'), currency_symbol='', currency_code='JPY')
        self.assertEqual(result, '1235')  # Rounded to integer

    def test_format_currency_kwd_three_decimals(self):
        """KWD should have 3 decimal places."""
        result = format_currency(Decimal('1234.5678'), currency_symbol='', currency_code='KWD')
        self.assertEqual(result, '1234.568')

    def test_format_currency_rounding(self):
        """Should use ROUND_HALF_UP."""
        # 1234.565 should round to 1234.57 (not 1234.56)
        result = format_currency(Decimal('1234.565'), currency_symbol='', currency_code='EUR')
        self.assertEqual(result, '1234.57')

        # 1234.564 should round to 1234.56
        result = format_currency(Decimal('1234.564'), currency_symbol='', currency_code='EUR')
        self.assertEqual(result, '1234.56')

    def test_format_currency_float_input(self):
        """Should handle float input (converted via str to avoid precision loss)."""
        result = format_currency(1234.56, currency_symbol='', currency_code='EUR')
        self.assertEqual(result, '1234.56')


class TestFormatStreetAddress(unittest.TestCase):
    """Tests for street address formatting."""

    def test_basic_eu_address(self):
        """Basic EU address formatting."""
        address = {
            'street': 'Rue de la Loi 1',
            'city': 'Brussels',
            'postal_code': '1000',
            'country_code': 'BE',
        }
        result = format_street_address(address)
        self.assertEqual(result, 'Rue de la Loi 1, 1000 Brussels, BE')

    def test_us_address(self):
        """US address formatting with state."""
        address = {
            'street': '123 Main Street',
            'city': 'Denver',
            'postal_code': '80202',
            'state': 'CO',
            'country_code': 'US',
        }
        result = format_street_address(address)
        self.assertEqual(result, '123 Main Street, Denver, CO 80202, US')

    def test_address_with_building_name(self):
        """Address with building name."""
        address = {
            'building_name': 'Tower One',
            'street': 'Business Park 10',
            'city': 'Amsterdam',
            'postal_code': '1012',
            'country_code': 'NL',
        }
        result = format_street_address(address)
        self.assertIn('Tower One', result)

    def test_address_with_floor_and_suite(self):
        """Address with floor and suite."""
        address = {
            'street': 'Main Street 1',
            'floor': '5',
            'suite': 'Suite 501',
            'city': 'Berlin',
            'postal_code': '10117',
            'country_code': 'DE',
        }
        result = format_street_address(address)
        self.assertIn('Floor 5', result)
        self.assertIn('Suite 501', result)

    def test_address_with_linefeeds(self):
        """Address with linefeeds instead of commas."""
        address = {
            'street': 'Rue de la Loi 1',
            'city': 'Brussels',
            'postal_code': '1000',
            'country_code': 'BE',
        }
        result = format_street_address(address, use_linefeeds=True)
        self.assertIn('\n', result)
        self.assertNotIn(', ', result.replace(', BE', '').replace('1000 Brussels', ''))

    def test_missing_required_fields(self):
        """Missing required fields should return None."""
        incomplete = {
            'city': 'Brussels',
            'country_code': 'BE',
        }
        result = format_street_address(incomplete)
        self.assertIsNone(result)


class TestFormatEIN(unittest.TestCase):
    """Tests for US EIN formatting."""

    def test_valid_ein(self):
        """Valid 9-digit EIN."""
        result = format_ein('123456789')
        self.assertEqual(result, '12-3456789')

    def test_invalid_ein_length(self):
        """Invalid EIN length should return input unchanged."""
        result = format_ein('12345678')  # 8 digits
        self.assertEqual(result, '12345678')


class TestGetRelevantMonth(unittest.TestCase):
    """Tests for billing month determination."""

    def test_explicit_date_yyyy_mm_dd(self):
        """Explicit date in YYYY-MM-DD format."""
        result = get_relevant_month('2025-06-15')
        self.assertEqual(result, date(2025, 6, 15))

    def test_explicit_date_yyyy_mm(self):
        """Explicit date in YYYY-MM format (first of month)."""
        result = get_relevant_month('2025-06')
        self.assertEqual(result, date(2025, 6, 1))

    def test_invalid_date_format(self):
        """Invalid date format should return None (wrong length)."""
        # Wrong length triggers None return
        result = get_relevant_month('2025-6-15')  # 9 chars, not 10 or 7
        self.assertIsNone(result)

    def test_invalid_date_value_raises(self):
        """Invalid date value (correct length) raises ValueError."""
        # Correct length but invalid format raises exception
        with self.assertRaises(ValueError):
            get_relevant_month('2025/06/15')  # 10 chars but wrong format


if __name__ == '__main__':
    unittest.main(verbosity=2)
