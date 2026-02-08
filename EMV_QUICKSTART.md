# EMV System - Quick Start Guide

## Installation

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Initialize environment:**
```bash
# Copy and customize environment variables
copy .env.example .env
```

3. **Start the application:**
```bash
python app.py
```

The system will initialize automatically with default configuration.

---

## Quick Examples

### Test Offline Transaction (cURL)

```bash
# Process offline transaction
curl -X POST http://localhost:5000/api/emv/process-offline-transaction \
  -H "Content-Type: application/json" \
  -d '{
    "pan": "4111111111111111",
    "expiry": "2512",
    "cvc": "123",
    "amount": 100.0,
    "pin": "1234",
    "cardholder_name": "TEST USER"
  }'

# Get transaction
curl http://localhost:5000/api/emv/get-transaction/{transaction_id}

# Get pending transactions
curl http://localhost:5000/api/emv/pending-transactions

# Create batch upload
curl -X POST http://localhost:5000/api/emv/batch-upload \
  -H "Content-Type: application/json" \
  -d '{}'

# Process settlement
curl -X POST http://localhost:5000/api/emv/settlement/{batch_id} \
  -H "Content-Type: application/json" \
  -d '{}'

# Request reversal
curl -X POST http://localhost:5000/api/emv/reversal/{transaction_id} \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Customer Request",
    "amount": null
  }'
```

### Test with Python

```python
import requests
import json

BASE_URL = "http://localhost:5000"

# Initialize EMV
resp = requests.post(f"{BASE_URL}/api/emv/initialize")
print("EMV Status:", resp.json())

# Process transaction
payload = {
    "pan": "4111111111111111",
    "expiry": "2512",
    "cvc": "123",
    "amount": 100.0,
    "pin": "1234"
}

resp = requests.post(
    f"{BASE_URL}/api/emv/process-offline-transaction",
    json=payload
)

tx = resp.json()['transaction']
print(f"Transaction: {tx['transaction_id']}")
print(f"Status: {tx['status']}")
print(f"Decision: {tx['decision']}")
```

---

## Key Configuration

### Terminal Settings (.env)

```bash
EMV_TERMINAL_ID=TERM001
EMV_MERCHANT_ID=MERCH001
EMV_MERCHANT_NAME=My Store
EMV_FLOOR_LIMIT=500.0
```

### Floor Limit

- Transactions above floor limit require online processing
- Default: $500
- Adjust based on risk profile

### CVM (Cardholder Verification)

- **Offline PIN**: For transactions above CVM threshold
- **Signature**: For low-value transactions
- **No CVM**: For very low-value transactions

---

## Transaction Statuses

| Status | Meaning |
|--------|---------|
| APPROVED | Transaction approved offline (TC generated) |
| DECLINED | Transaction declined (AAC generated) |
| REFERRAL | Issuer referral required (IAC generated) |
| PENDING | Awaiting synchronization |
| SYNCHRONIZED | Uploaded to server |
| SETTLED | Settlement completed |
| FAILED | Processing error |

---

## Testing Checklist

- [x] EMV kernel initialization
- [x] Card data validation
- [x] PIN verification
- [x] Risk assessment
- [x] CVM processing
- [x] TAC analysis
- [x] Cryptogram generation
- [x] Transaction storage
- [x] Batch creation
- [x] Batch upload
- [x] Settlement
- [x] Reconciliation
- [x] Reversals
- [x] Receipt generation

---

## Common Issues

### "EMV system not initialized"
- Ensure app.py runs without errors
- Check all required modules are installed
- Verify database permissions

### "PIN verification failed"
- Max 3 attempts allowed
- PIN is "1234" for testing
- After 3 failures, PIN entry is blocked

### "Batch upload fails"
- Requires internet connection
- Check API endpoint and credentials
- Verify transaction data format

### "Database locked"
- SQLite concurrent access issue
- Restart application
- Check file permissions on .vpos directory

---

## Performance Metrics

- Transaction processing: ~100-200ms
- Encryption overhead: ~1-2ms
- Database write: ~10-20ms
- Batch creation: ~100-500ms (depending on size)
- Batch upload: 5-30 seconds (network dependent)

---

## Security Best Practices

1. **PIN Entry**
   - Use secure PIN entry device (PED) in production
   - Never log PIN values
   - Limit PIN attempts to 3

2. **Encryption**
   - Use HSM for key management
   - Rotate keys regularly
   - Audit key usage

3. **Network**
   - Use TLS 1.2+ for connections
   - Validate server certificates
   - Implement request signing

4. **Database**
   - Enable encryption at rest
   - Regular backups
   - Access control

---

## Monitoring

Monitor these metrics:

```bash
# Check system status
curl http://localhost:5000/api/emv/status

# Check pending transactions
curl http://localhost:5000/api/emv/pending-transactions

# Monitor logs
tail -f app.log
```

---

## Next Steps

1. Configure for your merchant
2. Test with sample transactions
3. Integrate with payment gateway
4. Implement network synchronization
5. Deploy to terminal device
6. Train staff
7. Monitor and maintain

---

**Version:** 1.0  
**Last Updated:** February 8, 2026
