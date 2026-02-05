# common code for invoicing automation

import os
import re
import sys
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
import lxml.etree as ET
from decimal import Decimal, ROUND_HALF_UP


# ANSI escape codes for some common colors
RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
# colors for print. eg: print(f"This is {RED}red hot{RESET}.")


# --- Helper function to format currency ---
def format_currency(amount:int|float|Decimal, currency_symbol:str='', currency_first:bool=False):
    """
    Formats a Decimal or number to a string with 2 decimal places.
    If provided, includes the currency symbol (eg, '$', 'EUR', etc) before or after the number
    """
    # Convert via str() to avoid float precision issues (e.g., Decimal(0.1) != Decimal('0.1'))
    amount_dec = Decimal(str(amount)) if not isinstance(amount, Decimal) else amount
    currency_text = f"{amount_dec.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"
    if currency_symbol:
        return f"{currency_symbol} {currency_text}" if currency_first else f"{currency_text} {currency_symbol}"
    else:
        return currency_text


def validate_invoice(xml_path, xsd_path):
    xml_doc = ET.parse(xml_path)
    xsd_doc = ET.parse(xsd_path)
    xmlschema = ET.XMLSchema(xsd_doc)

    succeeded = xmlschema.validate(xml_doc)
    errors = []
    for error in xmlschema.error_log:
        errors.append(f"  Line {error.line}: {error.message}")

    return (succeeded, errors)


def get_next_invoice_id(invoice_dir):
    """
    Determines the next invoice ID based on existing files in a directory.

    Scans the directory for files matching the pattern "INV-YYYY-NNN.*",
    where YYYY is the current year and NNN is a sequence number.
    Finds the highest sequence number for the current year and returns
    the next ID in the sequence, formatted as "INV-YYYY-NNN" (with at least
    3 digits for NNN, zero-padded).

    Args:
        invoice_dir (str): The path to the directory containing invoice files.

    Returns:
        str: The next invoice ID string (e.g., "INV-2024-001", "INV-2024-012").
             Returns None if the path is not a valid directory or an error occurs.
    """
    if not os.path.isdir(invoice_dir):
        print(f"Error: Provided path '{invoice_dir}' is not a valid directory.", file=sys.stderr)
        return None

    current_year = date.today().year
    # Regex to match the pattern:
    # - ^INV- : Starts with "INV-"
    # - (YYYY) : Capture the 4-digit year
    # - -      : Separator
    # - (NNN)  : Capture the sequence number (one or more digits)
    # - \.     : Match a literal dot before the extension
    # - .*     : Match any extension
    # We specifically check the captured year against the current year later.
    pattern = re.compile(r"^INV-(\d{4})-(\d+)\..*$")
    max_sequence_num = 0

    try:
        filenames = os.listdir(invoice_dir)

        for filename in filenames:
            match = pattern.match(filename)
            if match:
                file_year_str, seq_num_str = match.groups()
                try:
                    file_year = int(file_year_str)
                    # Only consider files from the CURRENT year
                    if file_year == current_year:
                        seq_num = int(seq_num_str)
                        max_sequence_num = max(max_sequence_num, seq_num)
                except ValueError:
                    # Ignore files where year or sequence number are not valid integers
                    print(f"Warning: Found file '{filename}' matching invoice pattern but contains non-integer year or sequence number. Ignoring.")
                    continue

    except FileNotFoundError:
        print(f"Invoice directory not found: '{invoice_dir}'", file=sys.stderr)
        # return first for the year
    except OSError as e:
        print(f"Error accessing directory '{invoice_dir}': {e}", file=sys.stderr)
        return None

    # Calculate the next sequence number
    next_sequence_num = max_sequence_num + 1

    # Format the next invoice ID string with at least 3 digits for the sequence number
    # Example: 1 -> 001, 15 -> 015, 123 -> 123, 1000 -> 1000
    next_id = f"INV-{current_year}-{next_sequence_num:03d}"

    return next_id


def get_relevant_month(a_date:str=""):
    """
    returns the start of the billable calendar month:
        if a_date is provided as YYYY-MM, the first day of that month is returned as the start date
        if a_date is in the form YYY-MM-DD, that day is provided.
        if a_date is empty, it's based on today's date: - last calendar month, or this month if it's after the 20th.

    do t.strftime('%B') to get text version
    """
    # determine from string
    if a_date:
        if len(a_date) == 10:
            return datetime.strptime(a_date, "%Y-%m-%d").date()
        elif len(a_date) == 7:
            return datetime.strptime(a_date, "%Y-%m").date().replace(day=1)
        else:
            print(f"{RED}ERROR: Invalid start date format.{RESET} Use YYYY-MM or YYYY-MM-DD.\n")
            return None

    # determine based on current date
    today = date.today()
    if today.day >= 20:
        return today.replace(day=1)
    else:
        previous_month = today - relativedelta(months=1)
        return previous_month.replace(day=1)


def format_belgian_company_number(company_number:int|str) -> str|None:
    """
    Formats a 10-digit Belgian company number (KBO/BCE number) into a string
    with the format "####.###.###", *preserving leading zeros*.

    Args:
        company_number (int or str): The 10-digit company number

    Returns:
        str: The formatted company number string (e.g., "0001.234.567") or None
             if the input is invalid (not 10 digits).
    """

    try:
        # Attempt to convert to integer
        company_number = int(company_number)
    except ValueError:
        print("Error: Input must be a valid integer or string representation of an integer.")
        return None

    # Check if the number is exactly 10 digits long when treated as a string
    company_number_str = f"{company_number:010}" # Format to 10 digits with leading zeros

    if len(company_number_str) != 10:
        print("Error: Company number must be exactly 10 digits.")
        return None

    # Format the number string
    formatted_number = f"{company_number_str[:4]}.{company_number_str[4:7]}.{company_number_str[7:]}"

    return formatted_number


def format_ein(ein:str) -> str:
    if len(ein) != 9:
        print("Invalid EIN, not 9 digits")
        return ein

    return f"{ein[:2]}-{ein[2:]}"



def format_street_address(address_data, use_linefeeds=False, country_alone=False):
    """
    Generates a formatted street address string from a dictionary, handling
    optional building name, floor, and suite information.

    Args:
        address_data (dict): A dictionary containing address components.
                             Required keys: 'street', 'city', 'postal_code', 'country_code'.
                             Optional keys: 'building_name', 'floor', 'suite', 'state'
        use_linefeeds (bool, optional): If True, insert linefeeds (\n) between
                                         address components. Defaults to False.

    Returns:
        str: A formatted address string, or None if required fields are missing.
    """

    street = address_data.get('street')
    city = address_data.get('city')
    postal_code = address_data.get('postal_code')
    country_code = address_data.get('country_code')
    building_name = address_data.get('building_name')
    floor = address_data.get('floor')
    suite = address_data.get('suite')
    state = address_data.get('state')

    if not all([street, city, postal_code, country_code]):
        print("Error: Missing required address fields (street, city, postal_code, country_code).")
        return None  # Or raise an exception if that's more appropriate
    if country_code == 'US' and not state:
        print("Error: Missing State for a US address")

    separator = "\n" if use_linefeeds else ", " # Decide if linefeeds or commas are used

    address_lines = []

    # Add building name if present
    if building_name:
        address_lines.append(building_name)

    # Add street address (always present due to initial check)
    address_lines.append(street)

    # Add floor and suite info to street if available
    floor_suite = []
    if floor:
        floor_suite.append(f"Floor {floor}")
    if suite:
        floor_suite.append(suite) # Might include "Suite" "Apt" or similar

    if floor_suite: # Only add floor_suite to street line if present
        # Need to replace existing street before adding floor_suite to avoid double adding it
        address_lines[-1] += " " + ", ".join(floor_suite)

    # Postal code, city and country code
    if country_code == 'US':
        address_lines.append(f"{city}, {state} {postal_code}")
    else:
        address_lines.append(f"{postal_code} {city}")

    if country_alone:
        address_lines.append(country_code)
    else:
        address_lines[-1] += f", {country_code}"

    # Join the lines using the selected separator
    formatted_address = separator.join(address_lines)

    return formatted_address


# --- Example Usage ---
if __name__ == "__main__":
    buyer_name_de = "Deutsche Kunden AG"
    buyer_data_de = {
         'name': buyer_name_de, 'building_name': "OfficePark Alpha", 'floor': '12', 'suite': "1205",
         'street': 'Musterstraße 1', 'city': 'Berlin', 'postal_code': '10117', 'state': None, 'country_code': 'DE'
    }

    address_with_linefeeds = format_street_address(buyer_data_de, use_linefeeds=True)
    address_with_commas = format_street_address(buyer_data_de, use_linefeeds=False)
    missing_address = { 'name': "Incomplete", 'city': 'Nowhere', 'country_code': 'XX'} # street and postal_code are missing

    print("Address with linefeeds:\n", address_with_linefeeds)
    print("\nAddress with commas:", address_with_commas)
    print(f"\nMissing Data Example, returns None: {format_street_address(missing_address)}")

    # More realistically, remove those linefeeds that appear before () information, even if other linefeeds exist
    address_with_linefeeds_no_floor = buyer_data_de.copy()
    address_with_linefeeds_no_floor['floor'] = None
    address_with_linefeeds_no_suite = buyer_data_de.copy()
    address_with_linefeeds_no_suite['suite'] = None

    address_linefeeds_no_floor = format_street_address(address_with_linefeeds_no_floor, True)
    print(f"Here's no floor/suite information:\n{address_linefeeds_no_floor}")

    address_linefeeds_no_suite = format_street_address(address_with_linefeeds_no_suite, True)
    print(f"Here's no floor/suite information:\n{address_linefeeds_no_suite}")