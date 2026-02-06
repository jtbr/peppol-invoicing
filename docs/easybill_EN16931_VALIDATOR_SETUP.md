# EN16931 / PEPPOL BIS 3.0 Validator Setup

A simple guide to running and using the easybill local EN16931 + PEPPOL BIS 3.0 validation service for UBL 2.1 invoices.

## Quick Start

### 1. Start the Validator (Docker)

```bash
docker run -d --name peppol-validator \
  -p 8080:8080 \
  --restart unless-stopped \
  easybill/peppol-bis-billing-validator:latest
```

Or with docker-compose:

```yaml
# docker-compose.yml
version: '3'
services:
  validator:
    image: easybill/peppol-bis-billing-validator:latest
    ports:
      - "8080:8080"
    environment:
      - JAVA_OPTS=-Xmx512m
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### 2. Validate Invoices

**From Python** (using the included client):

```python
from peppol_invoicing.validate_peppol import validate_invoice, format_validation_report

result = validate_invoice('invoices/INV-2026-001.xml')
print(format_validation_report(result))
```

Output:
```
✅ Invoice is valid (EN16931 + PEPPOL BIS 3.0)

   ⚠️  1 warning(s):
   [UBL-SR-09] Seller tax registration identifier should be present.
```

Or with errors:
```
❌ Invoice has 2 validation error(s):

   [PEPPOL-EN16931-R003] A buyer reference or purchase order reference MUST be provided.

   [BR-16] An Invoice shall have at least one Invoice line (BG-25).
```

**From command line**:

```bash
python -m peppol_invoicing.validate_peppol invoices/INV-2026-001.xml
```

**Direct curl** (returns SVRL XML):

```bash
curl -X POST http://localhost:8080/validation \
  -H "Content-Type: application/xml" \
  -d @invoices/INV-2026-001.xml
```

## What Gets Validated

The validator runs two Schematron rule sets in sequence:

1. **EN16931 rules** (~150 business rules from the European standard)
   - Rule IDs: `BR-*`, `BR-CO-*`, `BR-S-*`, `BR-AE-*`, `BR-O-*`, etc.
   - Example: *"An Invoice shall have at least one Invoice line (BG-25)."*

2. **PEPPOL BIS 3.0 rules** (additional PEPPOL requirements)
   - Rule IDs: `PEPPOL-EN16931-*`, `PEPPOL-COMMON-*`
   - Example: *"A buyer reference or purchase order reference MUST be provided."*

Plus country-specific rules for NO, SE, DK, IT, NL, GR, etc.

## API Reference

### Python Client

```python
from peppol_invoicing.validate_peppol import (
    validate_invoice,           # Validate from file path
    validate_invoice_string,    # Validate from XML string
    format_validation_report,   # Format result as human-readable text
    ValidationError             # Dataclass for individual errors
)

# Basic validation
result = validate_invoice('invoice.xml')
# result = {
#     'valid': True/False/None,
#     'errors': [ValidationError, ...],
#     'warnings': [ValidationError, ...],
#     'raw_response': '<svrl:output>...'
# }

# Access individual errors
for error in result['errors']:
    print(f"{error.rule_id}: {error.message}")
    # error.location contains XPath if needed

# Custom validator URL
result = validate_invoice('invoice.xml',
                          validator_url='http://validator.example.com/validation')
```

### REST API (easybill validator)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/validation` | POST | Validate XML invoice, returns SVRL |
| `/health` | GET | Health check |
| `/swagger` | GET | OpenAPI documentation |

**Response codes:**
- `200` - Valid invoice (SVRL with no `failed-assert`)
- `400` - Invalid invoice (SVRL with `failed-assert` elements)

## Troubleshooting

**"Could not connect to validator"**
```bash
# Check if container is running
docker ps | grep peppol-validator

# Check logs
docker logs peppol-validator

# Restart if needed
docker restart peppol-validator
```

**Validation is slow (first request)**
- The validator loads Schematron rules on first request
- First validation may take 5-10 seconds; subsequent ones are fast

**Memory issues**
```bash
# Increase memory limit
docker run -e JAVA_OPTS="-Xmx1g" ...
```

## References

- [easybill/peppol-bis-billing-validator](https://github.com/easybill/peppol-bis-billing-validator)
- [PEPPOL BIS Billing 3.0 Rules](https://docs.peppol.eu/poacc/billing/3.0/)
- [EN16931 Business Rules](https://github.com/ConnectingEurope/eInvoicing-EN16931)
