# Quick Start Guide - vPOS & Open Banking Integration

## What's New

Your POS terminal now has two major new features:

### 1. **vPOS Terminal Integration**
   - Connect to multiple banks (DSK, Fibank, KBC, Paysera)
   - Process payments through official bank terminals
   - Full transaction lifecycle management
   - Real-time status tracking

### 2. **Open Banking Pre-Authentication**
   - OpenAPI 3.0.1 compliant
   - SCA (Strong Customer Authentication) support
   - Session-based PSU pre-authentication
   - Audit trail for all operations

## Files Added

```
d:\pos_crypto_terminal\
├── vpos_integrations.py          # Bank provider implementations
├── pre_auth.py                   # Pre-authentication service
├── .env.example                  # Configuration template
├── README.md                      # Full documentation
└── app.py                         # Updated with new endpoints
```

## Quick Setup (5 minutes)

### Step 1: Install Dependencies
No additional packages needed - using existing requirements

### Step 2: Configure Credentials
```bash
# Copy template
copy .env.example .env

# Edit .env with your bank details:
VPOS_PROVIDER=DSK
DSK_MERCHANT_ID=your_merchant_id
DSK_API_KEY=your_api_key
DSK_OUTLET_ID=your_outlet_id
```

### Step 3: Run Server
```bash
python app.py
```

Server starts at `http://localhost:5000`

## Test API Calls

### Test vPOS Integration

```bash
# 1. Initialize vPOS session
curl -X POST http://localhost:5000/api/vpos/initialize \
  -H "Content-Type: application/json" \
  -d '{"provider": "DSK"}'

# Response:
# {"success": true, "session_id": "uuid", "provider": "DSK"}

# 2. Create order (existing endpoint)
curl -X POST http://localhost:5000/api/create-order \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 100,
    "currency": "AED",
    "email": "customer@example.com"
  }'

# 3. Create payment via vPOS
curl -X POST http://localhost:5000/api/vpos/create-payment \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "YOUR_SESSION_ID",
    "order_id": "YOUR_ORDER_ID"
  }'

# 4. Authorize payment
curl -X POST http://localhost:5000/api/vpos/authorize \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "YOUR_SESSION_ID",
    "transaction_id": "YOUR_TX_ID",
    "authorization_code": "123456"
  }'
```

### Test Pre-Authentication

```bash
# 1. Create pre-authentication
curl -X POST \
  http://localhost:5000/xs2a/routingservice/services/ob/auth/v3/psus/psu-user1/pre-authentication \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: $(uuidgen)" \
  -H "MessageCreateDateTime: 2023-09-25T08:15:00.856Z" \
  -H "Scope: AIS+PIS" \
  -d '{
    "PsuData": {
      "AspspId": "DSK",
      "AspspPsuId": "user123"
    },
    "PsuCredentials": [
      {
        "CredentialId": "username",
        "CredentialValue": "myusername"
      }
    ]
  }'

# Response includes PreAuthenticationId

# 2. Update pre-authentication with SCA
curl -X PUT \
  http://localhost:5000/xs2a/routingservice/services/ob/auth/v3/psus/psu-user1/pre-authentication/YOUR_PRE_AUTH_ID \
  -H "Content-Type: application/json" \
  -d '{
    "AuthenticationMethodId": "sms_otp_001",
    "ScaAuthenticationData": "123456"
  }'

# 3. Check status
curl -X GET \
  http://localhost:5000/xs2a/routingservice/services/ob/auth/v3/psus/psu-user1/pre-authentication/YOUR_PRE_AUTH_ID/status

# 4. Get audit log
curl -X GET \
  http://localhost:5000/api/pre-auth/audit/YOUR_PRE_AUTH_ID
```

## Key Endpoints Summary

### vPOS Terminal
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/vpos/initialize` | Create vPOS session |
| POST | `/api/vpos/create-payment` | Initiate payment |
| POST | `/api/vpos/authorize` | Authorize with SCA code |
| GET | `/api/vpos/status/{id}` | Check transaction status |
| POST | `/api/vpos/refund` | Refund transaction |

### Open Banking Pre-Auth
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/xs2a/.../pre-authentication` | Create session |
| PUT | `/xs2a/.../pre-authentication/{id}` | Update with credentials |
| GET | `/xs2a/.../pre-authentication/{id}/status` | Get status |
| DELETE | `/xs2a/.../pre-authentication/{id}` | Revoke session |
| GET | `/api/pre-auth/audit/{id}` | View audit log |

## Bank Provider Details

### DSK Bank
- **File**: `vpos_integrations.py` → `DSKVPOSProvider`
- **Auth**: Bearer token
- **Features**: PURCHASE, REFUND, status check
- **Currency**: All standard

### Fibank
- **File**: `vpos_integrations.py` → `FibankVPOSProvider`
- **Auth**: Session token
- **Features**: Payment creation, OTP confirmation, refund
- **Amount**: In cents (multiply by 100)

### KBC Bank
- **File**: `vpos_integrations.py` → `KCBVPOSProvider`
- **Auth**: Basic auth (merchant:key)
- **Features**: Full transaction lifecycle
- **SCA**: OTP based

### Paysera
- **File**: `vpos_integrations.py` → `PayseraVPOSProvider`
- **Auth**: Bearer token
- **Features**: Payment, refund, status
- **Amount**: In cents (multiply by 100)

## Pre-Authentication Status Flow

```
┌─────────────────────────────────────────┐
│ CREATE Pre-Auth Session (Open)          │
│ - PSU provides data                      │
│ - System offers SCA methods             │
└────────────┬────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────┐
│ UPDATE with Credentials (Pending)       │
│ - Select SCA method                     │
│ - Send OTP                              │
└────────────┬────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────┐
│ AUTHORIZE with OTP (Authorised)         │
│ - Validate OTP code                     │
│ - Grant pre-auth access                 │
└────────────┬────────────────────────────┘
             │
             ├─→ REVOKE (delete endpoint)
             ├─→ EXPIRED (24h timeout)
             └─→ Can now use for payments
```

## Environment Variables Needed

```env
# Minimum for vPOS
VPOS_PROVIDER=DSK
DSK_MERCHANT_ID=merchant_001
DSK_API_KEY=your_api_key
DSK_OUTLET_ID=your_outlet_id

# Optional for other banks
FIBANK_MERCHANT_ID=
FIBANK_API_KEY=
KBC_MERCHANT_ID=
KBC_API_KEY=
PAYSERA_PROJECT_ID=
PAYSERA_MERCHANT_ID=
PAYSERA_API_KEY=

# Pre-Auth settings
OPEN_BANKING_ENABLED=True
PRE_AUTH_SESSION_TIMEOUT=86400
SCA_METHOD_DEFAULT=SMS_OTP
```

## Common Issues & Solutions

### "Unknown vPOS provider"
- Check `VPOS_PROVIDER` matches: DSK, FIBANK, KBC, or PAYSERA
- Case-insensitive but must be exact

### "Failed to authenticate"
- Verify merchant ID and API key
- Check bank API endpoint accessibility
- Test credentials with bank directly

### "Pre-authentication not found"
- Confirm pre-auth ID is correct
- Session expires after 24 hours
- Check audit log for revocation

### "Invalid OTP provided"
- OTP must be exactly 6 digits
- Only numeric allowed
- Test format: 123456

## Web Socket Events

Listen for real-time updates:

```javascript
const socket = io();

// Payment status changes
socket.on('status_update', (data) => {
  console.log(`Transaction ${data.transaction_id}: ${data.status}`);
});

// Terminal events
socket.on('terminal_log', (data) => {
  console.log(`[${data.type}] ${data.message}`);
});
```

## Next Steps

1. **Configure Bank Credentials**: Update `.env` with your bank's details
2. **Test vPOS**: Use curl/Postman to test `/api/vpos/initialize`
3. **Test Pre-Auth**: Create a pre-authentication session
4. **Integrate Frontend**: Update `templates/index.html` with new endpoints
5. **Production Setup**: 
   - Use HTTPS
   - Secure environment variables
   - Configure CORS properly
   - Enable audit logging

## Support Resources

- **Full Docs**: See `README.md`
- **Bank Specs**: Check each bank's integration documentation
- **OpenAPI Spec**: Pre-auth follows XS2A standard (included in original request)
- **Logs**: Check Flask console for detailed error messages

## Architecture Overview

```
Flask App (app.py)
├── vPOS Routes
│   ├── /api/vpos/initialize
│   ├── /api/vpos/create-payment
│   └── /api/vpos/authorize
│   └── [vpos_integrations.py]
│       ├── DSKVPOSProvider
│       ├── FibankVPOSProvider
│       ├── KCBVPOSProvider
│       └── PayseraVPOSProvider
│
├── Pre-Auth Routes
│   ├── /xs2a/.../pre-authentication (POST, PUT, DELETE)
│   └── [pre_auth.py]
│       ├── PreAuthenticationService
│       └── PreAuthentication
│
├── Order & Transaction Routes
│   ├── /api/create-order
│   ├── /api/process-card-payment
│   └── [Existing endpoints]
│
└── WebSocket Events
    ├── status_update
    └── terminal_log
```

## Performance Notes

- vPOS provider authentication cached per session
- Pre-auth sessions stored in-memory (24h TTL)
- Production: Consider Redis for sessions
- WebSocket updates real-time via Socket.IO

---

Ready to integrate! Start with Step 1 of Quick Setup above. 🚀
