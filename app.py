from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import requests
import secrets
import hashlib
from datetime import datetime
import uuid
import threading
import os
import logging
from dotenv import load_dotenv

# Import vPOS and Pre-Authentication modules
from vpos_integrations import get_vpos_provider
from pre_auth import PreAuthenticationService

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize Pre-Authentication Service
pre_auth_service = PreAuthenticationService()

# Configuration
PAYMENT_API_URL = os.getenv('PAYMENT_API_URL', 'https://api.payment-gateway.com')
PAYMENT_API_KEY = os.getenv('PAYMENT_API_KEY', 'your_api_key_here')
OUTLET_ID = os.getenv('OUTLET_ID', '5edab6d7-5946-43f4-b8c7-06b29c272bdd')
REDIRECT_URL = os.getenv('REDIRECT_URL', 'http://localhost:5000/payment-success')

# vPOS Configuration
VPOS_PROVIDER = os.getenv('VPOS_PROVIDER', 'DSK')  # DSK, FIBANK, KBC, PAYSERA
VPOS_MERCHANT_ID = os.getenv('VPOS_MERCHANT_ID', 'merchant_001')
VPOS_API_KEY = os.getenv('VPOS_API_KEY', 'your_vpos_key_here')
VPOS_OUTLET_ID = os.getenv('VPOS_OUTLET_ID', OUTLET_ID)

# In-memory storage for transactions
transactions = {}
orders = {}
vpos_sessions = {}  # Store vPOS provider instances per session

# ============ ROUTES ============

@app.route('/')
def index():
    return render_template('index.html')

# ============ ROUTES - vPOS TERMINAL ============

@app.route('/api/vpos/initialize', methods=['POST'])
def initialize_vpos():
    """Initialize vPOS provider session"""
    try:
        data = request.json
        provider_name = data.get('provider', VPOS_PROVIDER)
        session_id = str(uuid.uuid4())
        
        # Get vPOS provider
        vpos_provider = get_vpos_provider(
            provider_name=provider_name,
            merchant_id=VPOS_MERCHANT_ID,
            api_key=VPOS_API_KEY,
            outlet_id=VPOS_OUTLET_ID,
            **data.get('config', {})
        )
        
        if not vpos_provider:
            return jsonify({
                'success': False,
                'error': f'Unknown vPOS provider: {provider_name}'
            }), 400
        
        # Authenticate with provider
        if not vpos_provider.authenticate():
            return jsonify({
                'success': False,
                'error': f'Failed to authenticate with {provider_name}'
            }), 401
        
        # Store session
        vpos_sessions[session_id] = {
            'provider': vpos_provider,
            'provider_name': provider_name,
            'created_at': datetime.now().isoformat(),
            'status': 'ACTIVE'
        }
        
        socketio.emit('terminal_log', {
            'message': f'vPOS Terminal initialized: {provider_name}',
            'type': 'info'
        })
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'provider': provider_name,
            'message': f'Connected to {provider_name} vPOS Terminal'
        }), 201
        
    except Exception as e:
        logger.error(f'vPOS initialization error: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/vpos/create-payment', methods=['POST'])
def vpos_create_payment():
    """Create payment via vPOS terminal"""
    try:
        data = request.json
        session_id = data.get('session_id')
        order_id = data.get('order_id')
        
        # Validate session
        if session_id not in vpos_sessions:
            return jsonify({'success': False, 'error': 'Invalid session'}), 401
        
        if order_id not in orders:
            return jsonify({'success': False, 'error': 'Order not found'}), 404
        
        order = orders[order_id]
        vpos_provider = vpos_sessions[session_id]['provider']
        
        # Create payment via provider
        result = vpos_provider.create_payment(
            amount=order['amount'],
            currency=order['currency'],
            reference=order['reference'],
            email=order.get('email')
        )
        
        if not result['success']:
            socketio.emit('terminal_log', {
                'message': f'vPOS payment creation failed: {result.get("error")}',
                'type': 'error'
            })
            return jsonify(result), 400
        
        # Store transaction
        tx_id = result['transaction_id']
        transactions[tx_id] = {
            'id': tx_id,
            'order_id': order_id,
            'type': 'VPOS',
            'vpos_provider': vpos_sessions[session_id]['provider_name'],
            'amount': order['amount'],
            'currency': order['currency'],
            'status': 'INITIATED',
            'payment_link': result.get('payment_url'),
            'response_data': result.get('response'),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        # Update order
        order['status'] = 'PAYMENT_INITIATED'
        order['transaction_id'] = tx_id
        order['updated_at'] = datetime.now().isoformat()
        
        socketio.emit('status_update', {
            'transaction_id': tx_id,
            'status': 'INITIATED',
            'message': f'Payment initiated via {vpos_sessions[session_id]["provider_name"]}'
        })
        
        socketio.emit('terminal_log', {
            'message': f'vPOS payment created: {tx_id}',
            'type': 'info'
        })
        
        return jsonify({
            'success': True,
            'transaction_id': tx_id,
            'status': 'INITIATED',
            'payment_link': result.get('payment_url')
        }), 201
        
    except Exception as e:
        logger.error(f'vPOS create_payment error: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/vpos/authorize', methods=['POST'])
def vpos_authorize_payment():
    """Authorize vPOS payment"""
    try:
        data = request.json
        session_id = data.get('session_id')
        tx_id = data.get('transaction_id')
        auth_code = data.get('authorization_code')
        
        if session_id not in vpos_sessions:
            return jsonify({'success': False, 'error': 'Invalid session'}), 401
        
        if tx_id not in transactions:
            return jsonify({'success': False, 'error': 'Transaction not found'}), 404
        
        tx = transactions[tx_id]
        vpos_provider = vpos_sessions[session_id]['provider']
        
        # Authorize payment
        result = vpos_provider.authorize_payment(tx_id, auth_code)
        
        if not result['success']:
            return jsonify(result), 400
        
        # Update transaction
        tx['status'] = result.get('status', 'AUTHORIZED')
        tx['approval_code'] = auth_code
        tx['updated_at'] = datetime.now().isoformat()
        
        # Update order
        order = orders[tx['order_id']]
        order['status'] = 'AUTHORIZED'
        order['updated_at'] = datetime.now().isoformat()
        
        socketio.emit('status_update', {
            'transaction_id': tx_id,
            'status': 'AUTHORIZED',
            'message': 'Payment authorized'
        })
        
        socketio.emit('terminal_log', {
            'message': f'vPOS payment authorized: {tx_id}',
            'type': 'success'
        })
        
        return jsonify({
            'success': True,
            'transaction_id': tx_id,
            'status': 'AUTHORIZED'
        })
        
    except Exception as e:
        logger.error(f'vPOS authorize error: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/vpos/status/<tx_id>', methods=['GET'])
def vpos_transaction_status(tx_id):
    """Get vPOS transaction status"""
    try:
        if tx_id not in transactions:
            return jsonify({'success': False, 'error': 'Transaction not found'}), 404
        
        tx = transactions[tx_id]
        session_id = request.args.get('session_id')
        
        if session_id and session_id in vpos_sessions:
            vpos_provider = vpos_sessions[session_id]['provider']
            result = vpos_provider.get_transaction_status(tx_id)
            
            if result['success']:
                tx['status'] = result.get('status', tx['status'])
                tx['updated_at'] = datetime.now().isoformat()
        
        return jsonify({
            'success': True,
            'transaction': tx
        })
        
    except Exception as e:
        logger.error(f'vPOS status error: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/vpos/refund', methods=['POST'])
def vpos_refund():
    """Refund vPOS transaction"""
    try:
        data = request.json
        session_id = data.get('session_id')
        tx_id = data.get('transaction_id')
        amount = data.get('amount')
        
        if session_id not in vpos_sessions:
            return jsonify({'success': False, 'error': 'Invalid session'}), 401
        
        if tx_id not in transactions:
            return jsonify({'success': False, 'error': 'Transaction not found'}), 404
        
        tx = transactions[tx_id]
        vpos_provider = vpos_sessions[session_id]['provider']
        
        # Refund transaction
        result = vpos_provider.refund_transaction(tx_id, amount)
        
        if not result['success']:
            return jsonify(result), 400
        
        # Update transaction
        tx['status'] = result.get('status', 'REFUNDED')
        tx['updated_at'] = datetime.now().isoformat()
        
        # Update order
        order = orders[tx['order_id']]
        order['status'] = 'REFUNDED'
        
        socketio.emit('terminal_log', {
            'message': f'vPOS transaction refunded: {tx_id}',
            'type': 'warning'
        })
        
        return jsonify({
            'success': True,
            'transaction_id': tx_id,
            'status': 'REFUNDED'
        })
        
    except Exception as e:
        logger.error(f'vPOS refund error: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/create-order', methods=['POST'])
def create_order():
    """Create a new order in the payment system"""
    try:
        data = request.json
        order_id = str(uuid.uuid4())
        
        amount = float(data['amount'])
        currency = data.get('currency', 'AED')
        reference = data.get('reference', order_id)
        email = data.get('email', '')
        
        # Store order locally
        orders[order_id] = {
            'id': order_id,
            'reference': reference,
            'amount': amount,
            'currency': currency,
            'email': email,
            'status': 'created',
            'payment_methods': data.get('payment_methods', ['CARD', 'APPLE_PAY', 'SAMSUNG_PAY']),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        # Prepare payment API request
        payment_payload = {
            'action': 'PURCHASE',
            'amount': {
                'currencyCode': currency,
                'value': amount
            },
            'reference': reference,
            'outletId': OUTLET_ID,
            'language': 'en-US',
            'emailAddress': email,
            'merchantAttributes': {
                'redirectUrl': REDIRECT_URL
            },
            'paymentMethods': {
                'card': ['VISA', 'MASTERCARD', 'AMERICAN_EXPRESS', 'DINERS_CLUB_INTERNATIONAL'],
                'wallet': ['APPLE_PAY', 'SAMSUNG_PAY']
            }
        }
        
        # Log to terminal
        socketio.emit('terminal_log', {
            'message': f'Order created: {order_id}',
            'type': 'info'
        })
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'reference': reference,
            'amount': amount,
            'currency': currency,
            'payment_methods': data.get('payment_methods', ['CARD', 'APPLE_PAY', 'SAMSUNG_PAY'])
        }), 201
        
    except Exception as e:
        socketio.emit('terminal_log', {
            'message': f'Error creating order: {str(e)}',
            'type': 'error'
        })
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/order/<order_id>')
def get_order(order_id):
    """Get order details"""
    if order_id not in orders:
        return jsonify({'success': False, 'error': 'Order not found'}), 404
    
    order = orders[order_id]
    return jsonify({
        'success': True,
        'order': order
    })

# ============ API ENDPOINTS - PAYMENT PROCESSING ============

@app.route('/api/process-card-payment', methods=['POST'])
def process_card_payment():
    """Process card payment"""
    try:
        data = request.json
        order_id = data.get('order_id')
        
        if order_id not in orders:
            return jsonify({'success': False, 'error': 'Order not found'}), 404
        
        order = orders[order_id]
        
        # Create transaction record
        tx_id = f"TXN-{secrets.token_hex(8).upper()}"
        transactions[tx_id] = {
            'id': tx_id,
            'order_id': order_id,
            'type': 'CARD',
            'card_last4': data['card_number'][-4:],
            'cardholder_name': data['cardholder_name'],
            'amount': order['amount'],
            'currency': order['currency'],
            'status': 'PROCESSING',
            'approval_code': None,
            'payment_link': None,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        # Update order status
        order['status'] = 'PROCESSING'
        order['transaction_id'] = tx_id
        order['updated_at'] = datetime.now().isoformat()
        
        socketio.emit('status_update', {
            'transaction_id': tx_id,
            'status': 'PROCESSING',
            'message': 'Validating card...'
        })
        
        socketio.emit('terminal_log', {
            'message': f'Card payment processing: {tx_id}',
            'type': 'info'
        })
        
        return jsonify({
            'success': True,
            'transaction_id': tx_id,
            'status': 'PROCESSING'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/authorize-payment', methods=['POST'])
def authorize_payment():
    """Authorize payment with OTP/code"""
    try:
        data = request.json
        tx_id = data['transaction_id']
        auth_code = data['authorization_code']
        
        if tx_id not in transactions:
            return jsonify({'success': False, 'error': 'Transaction not found'}), 404
        
        tx = transactions[tx_id]
        
        # Verify authorization code (mock)
        if len(auth_code) < 4:
            return jsonify({'success': False, 'error': 'Invalid authorization code'}), 400
        
        # Update transaction
        tx['approval_code'] = auth_code
        tx['status'] = 'AUTHORIZED'
        tx['updated_at'] = datetime.now().isoformat()
        
        # Update order
        order = orders[tx['order_id']]
        order['status'] = 'AUTHORIZED'
        order['updated_at'] = datetime.now().isoformat()
        
        socketio.emit('status_update', {
            'transaction_id': tx_id,
            'status': 'AUTHORIZED',
            'message': 'Payment authorized'
        })
        
        socketio.emit('terminal_log', {
            'message': f'Payment authorized: {tx_id}',
            'type': 'success'
        })
        
        # Auto-complete after delay
        def complete_payment():
            import time
            time.sleep(2)
            tx['status'] = 'COMPLETED'
            tx['updated_at'] = datetime.now().isoformat()
            order['status'] = 'COMPLETED'
            order['updated_at'] = datetime.now().isoformat()
            
            socketio.emit('status_update', {
                'transaction_id': tx_id,
                'status': 'COMPLETED',
                'message': 'Payment completed successfully'
            })
            
            socketio.emit('terminal_log', {
                'message': f'Payment completed: {tx_id}',
                'type': 'success'
            })
        
        threading.Thread(target=complete_payment).start()
        
        return jsonify({
            'success': True,
            'status': 'AUTHORIZED',
            'transaction_id': tx_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/process-wallet-payment', methods=['POST'])
def process_wallet_payment():
    """Process wallet payment (Apple Pay, Samsung Pay)"""
    try:
        data = request.json
        order_id = data.get('order_id')
        wallet_type = data.get('wallet_type')  # APPLE_PAY or SAMSUNG_PAY
        
        if order_id not in orders:
            return jsonify({'success': False, 'error': 'Order not found'}), 404
        
        order = orders[order_id]
        
        # Create transaction record
        tx_id = f"TXN-{secrets.token_hex(8).upper()}"
        transactions[tx_id] = {
            'id': tx_id,
            'order_id': order_id,
            'type': wallet_type,
            'wallet_token': data.get('wallet_token', '****'),
            'amount': order['amount'],
            'currency': order['currency'],
            'status': 'PROCESSING',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        order['status'] = 'PROCESSING'
        order['transaction_id'] = tx_id
        order['updated_at'] = datetime.now().isoformat()
        
        socketio.emit('status_update', {
            'transaction_id': tx_id,
            'status': 'PROCESSING',
            'message': f'{wallet_type.replace("_", " ")} payment processing...'
        })
        
        socketio.emit('terminal_log', {
            'message': f'Wallet payment processing: {tx_id}',
            'type': 'info'
        })
        
        # Auto-complete wallet payment
        def complete_wallet_payment():
            import time
            time.sleep(3)
            transactions[tx_id]['status'] = 'COMPLETED'
            transactions[tx_id]['updated_at'] = datetime.now().isoformat()
            order['status'] = 'COMPLETED'
            order['updated_at'] = datetime.now().isoformat()
            
            socketio.emit('status_update', {
                'transaction_id': tx_id,
                'status': 'COMPLETED',
                'message': 'Wallet payment completed'
            })
            
            socketio.emit('terminal_log', {
                'message': f'Wallet payment completed: {tx_id}',
                'type': 'success'
            })
        
        threading.Thread(target=complete_wallet_payment).start()
        
        return jsonify({
            'success': True,
            'transaction_id': tx_id,
            'status': 'PROCESSING'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/transaction/<tx_id>')
def get_transaction(tx_id):
    """Get transaction details"""
    if tx_id not in transactions:
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404
    
    return jsonify({
        'success': True,
        'transaction': transactions[tx_id]
    })

# ============ API ENDPOINTS - CARD PAYMENT ============

@app.route('/api/submit-card', methods=['POST'])
def submit_card():
    """Submit card for payment processing"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['cardholder_name', 'card_number', 'expiry_date', 'cvv', 
                          'amount', 'crypto_type', 'wallet_address']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing field: {field}'}), 400
        
        # Create transaction
        transaction_id = str(uuid.uuid4())
        
        transaction = {
            'id': transaction_id,
            'cardholder_name': data['cardholder_name'],
            'card_number': f"****{data['card_number'][-4:]}",  # Mask card number
            'amount_usd': float(data['amount']),
            'crypto_type': data['crypto_type'],
            'crypto_amount': float(data.get('crypto_amount', 0)),
            'wallet_address': data['wallet_address'],
            'status': 'validating',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        transactions[transaction_id] = transaction
        
        # Emit event to connected clients
        socketio.emit('status_update', {
            'transaction_id': transaction_id,
            'status': 'validating'
        })
        
        socketio.emit('terminal_log', {
            'message': f'Card submission received: {transaction_id}',
            'type': 'info'
        })
        
        return jsonify({
            'success': True,
            'transaction_id': transaction_id,
            'status': 'validating'
        })
        
    except Exception as e:
        logger.error(f'Card submission error: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    """Verify authorization code"""
    try:
        data = request.json
        transaction_id = data.get('transaction_id')
        approval_code = data.get('approval_code')
        
        if not transaction_id or transaction_id not in transactions:
            return jsonify({'success': False, 'error': 'Invalid transaction ID'}), 404
        
        if not approval_code:
            return jsonify({'success': False, 'error': 'Missing approval code'}), 400
        
        # Update transaction status
        tx = transactions[transaction_id]
        tx['status'] = 'authorized'
        tx['updated_at'] = datetime.now().isoformat()
        tx['authorization_code'] = approval_code
        
        # Emit update
        socketio.emit('status_update', {
            'transaction_id': transaction_id,
            'status': 'authorized'
        })
        
        socketio.emit('terminal_log', {
            'message': f'Authorization verified: {transaction_id}',
            'type': 'info'
        })
        
        return jsonify({
            'success': True,
            'transaction_id': transaction_id,
            'status': 'authorized'
        })
        
    except Exception as e:
        logger.error(f'Verification error: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/status/<tx_id>', methods=['GET'])
def get_transaction_status(tx_id):
    """Get transaction status"""
    try:
        if tx_id not in transactions:
            return jsonify({'success': False, 'error': 'Transaction not found'}), 404
        
        tx = transactions[tx_id]
        
        # Generate mock blockchain TXID if transaction is successful
        blockchain_txid = None
        if tx['status'] == 'success':
            blockchain_txid = hashlib.sha256(f"{tx_id}:crypto".encode()).hexdigest()
        
        return jsonify({
            'success': True,
            'transaction_id': tx_id,
            'status': tx['status'],
            'amount_usd': tx['amount_usd'],
            'crypto_amount': tx['crypto_amount'],
            'crypto_type': tx['crypto_type'],
            'blockchain_txid': blockchain_txid,
            'created_at': tx['created_at']
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/transactions')
def get_transactions():
    """Get recent transactions"""
    recent_txs = list(transactions.values())[-20:]
    recent_txs.reverse()
    
    return jsonify({
        'success': True,
        'transactions': recent_txs,
        'total': len(transactions)
    })

# ============ API ENDPOINTS - ADMIN ============

@app.route('/api/admin/update-status', methods=['POST'])
def admin_update_status():
    """Admin endpoint to update transaction status"""
    try:
        data = request.json
        transaction_id = data.get('transaction_id')
        status = data.get('status')
        
        if not transaction_id or transaction_id not in transactions:
            return jsonify({'success': False, 'error': 'Transaction not found'}), 404
        
        if status not in ['validating', 'authorized', 'releasing', 'success', 'failed']:
            return jsonify({'success': False, 'error': 'Invalid status'}), 400
        
        tx = transactions[transaction_id]
        tx['status'] = status
        tx['updated_at'] = datetime.now().isoformat()
        
        # If success, generate blockchain TXID
        if status == 'success':
            tx['blockchain_txid'] = hashlib.sha256(f"{transaction_id}:crypto".encode()).hexdigest()
        
        socketio.emit('status_update', {
            'transaction_id': transaction_id,
            'status': status
        })
        
        socketio.emit('terminal_log', {
            'message': f'Status updated to {status}: {transaction_id}',
            'type': 'info'
        })
        
        return jsonify({'success': True, 'status': status})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/admin/refund', methods=['POST'])
def refund_transaction():
    """Refund a transaction"""
    try:
        data = request.json
        tx_id = data['transaction_id']
        
        if tx_id not in transactions:
            return jsonify({'success': False, 'error': 'Transaction not found'}), 404
        
        tx = transactions[tx_id]
        tx['status'] = 'REFUNDED'
        tx['updated_at'] = datetime.now().isoformat()
        
        order = orders[tx['order_id']]
        order['status'] = 'REFUNDED'
        
        socketio.emit('status_update', {
            'transaction_id': tx_id,
            'status': 'REFUNDED'
        })
        
        socketio.emit('terminal_log', {
            'message': f'Transaction refunded: {tx_id}',
            'type': 'warning'
        })
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/admin/stats')
def get_stats():
    """Get transaction statistics"""
    completed = sum(1 for tx in transactions.values() if tx['status'] == 'COMPLETED')
    processing = sum(1 for tx in transactions.values() if tx['status'] == 'PROCESSING')
    total_amount = sum(tx['amount'] for tx in transactions.values() if tx['status'] == 'COMPLETED')
    
    return jsonify({
        'success': True,
        'total_transactions': len(transactions),
        'completed': completed,
        'processing': processing,
        'total_amount': total_amount,
        'total_orders': len(orders)
    })

# ============ API ENDPOINTS - OPEN BANKING PRE-AUTHENTICATION ============

@app.route('/xs2a/routingservice/services/ob/auth/v3/psus/<psu_id>/pre-authentication', methods=['POST'])
def pre_auth_create(psu_id):
    """Create pre-authentication session (OpenAPI compliant)"""
    try:
        data = request.json or {}
        
        # Extract parameters from request
        x_request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        recurring = request.args.get('recurring', 'true').lower() == 'true'
        consent_id = request.args.get('consentId')
        payment_id = request.args.get('paymentId')
        scope = request.headers.get('Scope', 'AIS+PIS')
        
        psu_data = data.get('PsuData', {})
        psu_credentials = data.get('PsuCredentials', [])
        permitted_accounts = data.get('PermittedAccountReferences', [])
        
        # Create pre-authentication
        result = pre_auth_service.create_pre_authentication(
            psu_id=psu_id,
            psu_data=psu_data,
            psu_credentials=psu_credentials,
            permitted_accounts=permitted_accounts,
            scope=scope,
            consent_id=consent_id,
            payment_id=payment_id
        )
        
        if not result['success']:
            return jsonify({
                'Code': result.get('code', '001'),
                'Message': result.get('error', 'Bad Request')
            }), 400
        
        socketio.emit('terminal_log', {
            'message': f'Pre-authentication created: {result["PreAuthenticationId"]}',
            'type': 'info'
        })
        
        return jsonify(result), 201
        
    except Exception as e:
        logger.error(f'Pre-auth create error: {str(e)}')
        return jsonify({
            'Code': '004',
            'Message': 'Internal server error'
        }), 500

@app.route('/xs2a/routingservice/services/ob/auth/v3/psus/<psu_id>/pre-authentication/<pre_auth_id>', methods=['PUT'])
def pre_auth_update(psu_id, pre_auth_id):
    """Update pre-authentication (OpenAPI compliant)"""
    try:
        data = request.json or {}
        
        x_request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        psu_credentials = data.get('PsuCredentials', [])
        auth_method_id = data.get('AuthenticationMethodId')
        sca_auth_data = data.get('ScaAuthenticationData')
        
        # Update pre-authentication
        result = pre_auth_service.update_pre_authentication(
            pre_auth_id=pre_auth_id,
            psu_credentials=psu_credentials,
            auth_method_id=auth_method_id,
            sca_auth_data=sca_auth_data
        )
        
        if not result['success']:
            return jsonify({
                'Code': result.get('code', '001'),
                'Message': result.get('error', 'Bad Request')
            }), 400
        
        socketio.emit('terminal_log', {
            'message': f'Pre-authentication updated: {pre_auth_id}',
            'type': 'info'
        })
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f'Pre-auth update error: {str(e)}')
        return jsonify({
            'Code': '004',
            'Message': 'Internal server error'
        }), 500

@app.route('/xs2a/routingservice/services/ob/auth/v3/psus/<psu_id>/pre-authentication/<pre_auth_id>', methods=['DELETE'])
def pre_auth_delete(psu_id, pre_auth_id):
    """Delete/revoke pre-authentication (OpenAPI compliant)"""
    try:
        result = pre_auth_service.delete_pre_authentication(pre_auth_id)
        
        if not result['success']:
            return jsonify({
                'Code': result.get('code', '110'),
                'Message': result.get('error', 'Not found')
            }), 404
        
        socketio.emit('terminal_log', {
            'message': f'Pre-authentication revoked: {pre_auth_id}',
            'type': 'info'
        })
        
        return '', 204
        
    except Exception as e:
        logger.error(f'Pre-auth delete error: {str(e)}')
        return jsonify({
            'Code': '004',
            'Message': 'Internal server error'
        }), 500

@app.route('/xs2a/routingservice/services/ob/auth/v3/psus/<psu_id>/pre-authentication/<pre_auth_id>/status', methods=['GET'])
def pre_auth_status(psu_id, pre_auth_id):
    """Get pre-authentication status (OpenAPI compliant)"""
    try:
        x_request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        
        result = pre_auth_service.get_pre_authentication_status(pre_auth_id)
        
        if not result['success']:
            return jsonify({
                'Code': result.get('code', '110'),
                'Message': result.get('error', 'Not found')
            }), 404
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f'Pre-auth status error: {str(e)}')
        return jsonify({
            'Code': '004',
            'Message': 'Internal server error'
        }), 500

@app.route('/api/pre-auth/audit/<pre_auth_id>', methods=['GET'])
def get_pre_auth_audit(pre_auth_id):
    """Get pre-authentication audit log"""
    try:
        audit_log = pre_auth_service.get_audit_log(pre_auth_id)
        
        return jsonify({
            'success': True,
            'pre_auth_id': pre_auth_id,
            'audit_log': audit_log,
            'total_events': len(audit_log)
        })
        
    except Exception as e:
        logger.error(f'Audit log error: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 400

# ============ WEBSOCKET EVENTS ============

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    socketio.emit('terminal_log', {
        'message': 'Connected to POS Terminal',
        'type': 'info'
    })

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('subscribe_transaction')
def handle_subscribe(data):
    tx_id = data.get('transaction_id')
    if tx_id:
        print(f'Client subscribed to transaction: {tx_id}')
        socketio.emit('terminal_log', {
            'message': f'Subscribed to {tx_id}',
            'type': 'info'
        })

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)