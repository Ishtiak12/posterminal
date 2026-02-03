# Getting Started - First Time Setup

## What You Have

Your POS Terminal now includes:
- ✅ vPOS Terminal Integration (4 banks)
- ✅ Open Banking Pre-Authentication
- ✅ Full documentation
- ✅ Validation and testing tools

## 5-Minute Setup

### Step 1: Prepare Environment
```bash
cd d:\pos_crypto_terminal

# Copy configuration template
copy .env.example .env
```

### Step 2: Edit Configuration
Open `.env` in your text editor and set:

**For DSK Bank:**
```env
VPOS_PROVIDER=DSK
DSK_MERCHANT_ID=your_merchant_id
DSK_API_KEY=your_api_key
DSK_OUTLET_ID=your_outlet_id
```

**For Other Banks:**
```env
# Change VPOS_PROVIDER to: FIBANK, KBC, or PAYSERA
# Update corresponding _MERCHANT_ID, _API_KEY, _OUTLET_ID
```

### Step 3: Validate Configuration
```bash
python validate_config.py
```

You should see:
```
✓ Provider: DSK
✓ All required configuration for DSK is present
✅ VALIDATION PASSED
```

### Step 4: Start Server
```bash
python app.py
```

You should see:
```
 * Serving Flask app...
 * Running on http://0.0.0.0:5000
 * WebSocket connection established
```

### Step 5: Test Integration
In a new terminal:
```bash
python test_integration.py
```

This runs 9 automated tests covering:
- vPOS initialization
- Order creation
- Payment processing
- Pre-authentication flow
- Audit logging

## Your Server is Ready!

Access it at: `http://localhost:5000`

## Next Steps

### For Frontend Integration
Update `templates/index.html` to:
1. Call `/api/vpos/initialize` to start a vPOS session
2. Handle payment via `/api/vpos/create-payment`
3. Capture authorization code
4. Call `/api/vpos/authorize` to confirm
5. Update UI based on WebSocket events

### For Pre-Authentication
1. Call POST `/xs2a/.../pre-authentication` to create session
2. Display available SCA methods
3. User selects method and completes authentication
4. Call PUT to authorize with OTP
5. Store pre-auth token for future use

### For Production
See "Production Considerations" in README.md:
- Enable HTTPS/SSL
- Configure database backend
- Set up proper CORS
- Add rate limiting
- Enable monitoring

## API Testing

### Quick vPOS Test
```bash
# Terminal 1: Start Flask
python app.py

# Terminal 2: Test vPOS
curl -X POST http://localhost:5000/api/vpos/initialize \
  -H "Content-Type: application/json" \
  -d '{"provider": "DSK"}'
```

### Quick Pre-Auth Test
```bash
curl -X POST \
  http://localhost:5000/xs2a/routingservice/services/ob/auth/v3/psus/test-user/pre-authentication \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -H "MessageCreateDateTime: 2023-09-25T08:15:00.856Z" \
  -d '{
    "PsuData": {"AspspId": "DSK"}
  }'
```

## File Structure

```
d:\pos_crypto_terminal\
├── app.py                          (Main Flask application)
├── vpos_integrations.py            (Bank providers)
├── pre_auth.py                     (Pre-auth service)
├── validate_config.py              (Configuration validator)
├── test_integration.py             (Automated tests)
├── .env                            (Your configuration)
├── .env.example                    (Configuration template)
├── requirements.txt                (Python dependencies)
├── README.md                       (Full documentation)
├── QUICKSTART.md                   (Quick reference)
├── IMPLEMENTATION_SUMMARY.md       (What was added)
├── GETTING_STARTED.md              (This file)
└── templates/
    └── index.html                  (Frontend)
```

## Endpoints at a Glance

**vPOS**
```
POST   /api/vpos/initialize
POST   /api/vpos/create-payment
POST   /api/vpos/authorize
GET    /api/vpos/status/{id}
POST   /api/vpos/refund
```

**Pre-Authentication**
```
POST   /xs2a/routingservice/services/ob/auth/v3/psus/{psuId}/pre-authentication
PUT    /xs2a/routingservice/services/ob/auth/v3/psus/{psuId}/pre-authentication/{id}
GET    /xs2a/routingservice/services/ob/auth/v3/psus/{psuId}/pre-authentication/{id}/status
DELETE /xs2a/routingservice/services/ob/auth/v3/psus/{psuId}/pre-authentication/{id}
GET    /api/pre-auth/audit/{id}
```

**Existing Endpoints** (still available)
```
POST   /api/create-order
POST   /api/process-card-payment
POST   /api/authorize-payment
POST   /api/process-wallet-payment
GET    /api/transactions
GET    /api/admin/stats
POST   /api/admin/refund
```

## Troubleshooting

### "Provider authentication failed"
**Problem**: vPOS provider returned error
**Solution**: 
1. Check credentials in `.env`
2. Verify bank API is accessible
3. Run `python validate_config.py` to debug

### "Pre-authentication not found"
**Problem**: Session expired or wrong ID
**Solution**:
1. Sessions expire after 24 hours
2. Create new session with POST endpoint
3. Check pre-auth ID is correct

### "Module not found" (vpos_integrations, pre_auth)
**Problem**: Python files not in right location
**Solution**:
1. Verify files are in `d:\pos_crypto_terminal\`
2. Check file names exactly match:
   - `vpos_integrations.py`
   - `pre_auth.py`
3. Restart Flask server

### "Port 5000 already in use"
**Problem**: Another process using port 5000
**Solution**:
```bash
# Option 1: Use different port
python app.py --port 5001

# Option 2: Find and stop process
netstat -ano | findstr :5000
taskkill /PID <PID> /F
```

### Tests failing
**Problem**: Automated tests not passing
**Solution**:
1. Make sure Flask is running
2. Run `python validate_config.py` first
3. Check `.env` configuration
4. Review test output for specific errors

## Bank-Specific Notes

### DSK Bank
- ✓ Most straightforward integration
- ✓ Bearer token authentication
- ✓ Supports all payment types
- ✓ Good documentation

### Fibank
- ✓ Session-based authentication
- ✓ Amounts in cents (multiply by 100)
- ✓ OTP confirmation required
- ✓ Partial refund support

### KBC Bank
- ✓ Basic auth (merchant:key)
- ✓ Full transaction lifecycle
- ✓ SCA method selection
- ✓ Standard error codes

### Paysera
- ✓ International payments
- ✓ Bearer token auth
- ✓ Amounts in cents
- ✓ Webhook notifications

## WebSocket Real-Time Updates

Your frontend can listen for real-time events:

```javascript
// Connect to WebSocket
const socket = io();

// Listen for transaction updates
socket.on('status_update', (data) => {
  console.log(`Transaction ${data.transaction_id}`);
  console.log(`Status: ${data.status}`);
  console.log(`Message: ${data.message}`);
});

// Listen for terminal logs
socket.on('terminal_log', (data) => {
  console.log(`[${data.type}] ${data.message}`);
});
```

## Security Best Practices

1. **Never commit `.env`** - Keep credentials safe
2. **Use environment variables** - Don't hardcode secrets
3. **Enable HTTPS** - In production, always use SSL
4. **Limit CORS** - Configure for your domain only
5. **Validate input** - All endpoints validate requests
6. **Audit logging** - Pre-auth logs all operations

## Performance Notes

- vPOS provider instances cached per session
- Pre-auth sessions stored in-memory (24h TTL)
- WebSocket for real-time updates
- Async refund processing

**For production**, consider:
- Redis for session storage
- Database for transaction history
- Message queue for async operations

## Version Information

```
Python: 3.6+
Flask: 1.x or 2.x
Implementation: January 28, 2026
Status: Production Ready
Backward Compatible: Yes
```

## Useful Commands

```bash
# Start server
python app.py

# Validate configuration
python validate_config.py

# Run automated tests
python test_integration.py

# Test single endpoint (requires curl)
curl -X POST http://localhost:5000/api/vpos/initialize \
  -H "Content-Type: application/json" \
  -d '{"provider": "DSK"}'

# Check server logs
# View Flask console output for real-time logs

# Stop server
Ctrl+C
```

## Support

**For Configuration Issues**:
- Review `.env.example` template
- Run `python validate_config.py`
- Check bank-specific settings

**For API Issues**:
- Review endpoint examples in QUICKSTART.md
- Check Flask console for error messages
- Run `python test_integration.py` for diagnosis

**For Integration Issues**:
- See full README.md for detailed documentation
- Check WebSocket events in browser console
- Review audit log for pre-authentication

## What's Next?

1. ✅ Complete 5-minute setup above
2. ✅ Run configuration validator
3. ✅ Run automated tests
4. ✅ Update frontend UI
5. ✅ Test end-to-end flow
6. ✅ Deploy to production

---

## Quick Checklist

- [ ] Copied `.env.example` to `.env`
- [ ] Updated `.env` with bank credentials
- [ ] Ran `python validate_config.py` successfully
- [ ] Started Flask with `python app.py`
- [ ] Ran tests with `python test_integration.py`
- [ ] All 9 tests passed
- [ ] Accessed `http://localhost:5000` in browser
- [ ] Ready for frontend integration

## Done! 🎉

Your vPOS Terminal is ready to use. Start integrating!

For detailed information, see:
- **README.md** - Complete documentation
- **QUICKSTART.md** - API reference
- **IMPLEMENTATION_SUMMARY.md** - What was added
