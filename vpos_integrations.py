"""
vPOS Terminal Integrations for multiple banking partners
Supports: DSK, Fibank, KBC, Paysera, and other ASPSP providers
"""
import requests
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class VPOSProvider(ABC):
    """Abstract base class for vPOS providers"""
    
    def __init__(self, merchant_id: str, api_key: str, outlet_id: str = None, 
                 base_url: str = None, **kwargs):
        self.merchant_id = merchant_id
        self.api_key = api_key
        self.outlet_id = outlet_id
        self.base_url = base_url
        self.extra_config = kwargs
        
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the provider"""
        pass
    
    @abstractmethod
    def create_payment(self, amount: float, currency: str, reference: str, 
                       email: str = None, **kwargs) -> Dict[str, Any]:
        """Create a payment transaction"""
        pass
    
    @abstractmethod
    def authorize_payment(self, transaction_id: str, auth_code: str) -> Dict[str, Any]:
        """Authorize a payment"""
        pass
    
    @abstractmethod
    def get_transaction_status(self, transaction_id: str) -> Dict[str, Any]:
        """Get transaction status"""
        pass
    
    @abstractmethod
    def refund_transaction(self, transaction_id: str, amount: float = None) -> Dict[str, Any]:
        """Refund a transaction"""
        pass


class DSKVPOSProvider(VPOSProvider):
    """DSK Bank vPOS Terminal Integration"""
    
    def __init__(self, merchant_id: str, api_key: str, outlet_id: str, **kwargs):
        super().__init__(merchant_id, api_key, outlet_id, 
                        base_url='https://api.dsk.bg/vpos', **kwargs)
        self.auth_token = None
        
    def authenticate(self) -> bool:
        """Authenticate with DSK API"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
            response = requests.post(
                f'{self.base_url}/auth/token',
                headers=headers,
                json={'merchant_id': self.merchant_id},
                timeout=10
            )
            if response.status_code == 200:
                self.auth_token = response.json().get('access_token')
                return True
            logger.error(f'DSK authentication failed: {response.text}')
            return False
        except Exception as e:
            logger.error(f'DSK authentication error: {str(e)}')
            return False
    
    def create_payment(self, amount: float, currency: str, reference: str, 
                       email: str = None, **kwargs) -> Dict[str, Any]:
        """Create DSK vPOS payment"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.auth_token}'
            }
            payload = {
                'action': 'PURCHASE',
                'amount': {
                    'value': amount,
                    'currencyCode': currency
                },
                'reference': reference,
                'outletId': self.outlet_id,
                'merchantId': self.merchant_id,
                'language': 'en-US',
                'emailAddress': email,
                'paymentMethods': {
                    'card': ['VISA', 'MASTERCARD', 'AMERICAN_EXPRESS'],
                    'wallet': ['APPLE_PAY', 'SAMSUNG_PAY']
                }
            }
            response = requests.post(
                f'{self.base_url}/transactions',
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code in [200, 201]:
                return {
                    'success': True,
                    'transaction_id': response.json().get('transactionId'),
                    'status': 'INITIATED',
                    'payment_url': response.json().get('paymentUrl'),
                    'response': response.json()
                }
            return {
                'success': False,
                'error': f'DSK API error: {response.status_code}',
                'response': response.text
            }
        except Exception as e:
            logger.error(f'DSK create_payment error: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    def authorize_payment(self, transaction_id: str, auth_code: str) -> Dict[str, Any]:
        """Authorize DSK payment"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.auth_token}'
            }
            payload = {
                'authorizationCode': auth_code,
                'scaData': auth_code
            }
            response = requests.post(
                f'{self.base_url}/transactions/{transaction_id}/authorize',
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                return {
                    'success': True,
                    'status': 'AUTHORIZED',
                    'transaction_id': transaction_id,
                    'response': response.json()
                }
            return {
                'success': False,
                'error': f'Authorization failed: {response.status_code}',
                'response': response.text
            }
        except Exception as e:
            logger.error(f'DSK authorize_payment error: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    def get_transaction_status(self, transaction_id: str) -> Dict[str, Any]:
        """Get DSK transaction status"""
        try:
            headers = {
                'Authorization': f'Bearer {self.auth_token}'
            }
            response = requests.get(
                f'{self.base_url}/transactions/{transaction_id}',
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                return {
                    'success': True,
                    'status': response.json().get('status'),
                    'response': response.json()
                }
            return {'success': False, 'error': 'Transaction not found'}
        except Exception as e:
            logger.error(f'DSK get_transaction_status error: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    def refund_transaction(self, transaction_id: str, amount: float = None) -> Dict[str, Any]:
        """Refund DSK transaction"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.auth_token}'
            }
            payload = {}
            if amount:
                payload['amount'] = amount
            
            response = requests.post(
                f'{self.base_url}/transactions/{transaction_id}/refund',
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                return {
                    'success': True,
                    'status': 'REFUNDED',
                    'response': response.json()
                }
            return {
                'success': False,
                'error': f'Refund failed: {response.status_code}',
                'response': response.text
            }
        except Exception as e:
            logger.error(f'DSK refund_transaction error: {str(e)}')
            return {'success': False, 'error': str(e)}


class FibankVPOSProvider(VPOSProvider):
    """Fibank vPOS Terminal Integration"""
    
    def __init__(self, merchant_id: str, api_key: str, outlet_id: str, **kwargs):
        super().__init__(merchant_id, api_key, outlet_id,
                        base_url='https://api.fibank.bg/vpos', **kwargs)
        self.session_token = None
    
    def authenticate(self) -> bool:
        """Authenticate with Fibank API"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'X-API-Key': self.api_key
            }
            response = requests.post(
                f'{self.base_url}/authenticate',
                headers=headers,
                json={'merchantId': self.merchant_id},
                timeout=10
            )
            if response.status_code == 200:
                self.session_token = response.json().get('sessionToken')
                return True
            logger.error(f'Fibank authentication failed: {response.text}')
            return False
        except Exception as e:
            logger.error(f'Fibank authentication error: {str(e)}')
            return False
    
    def create_payment(self, amount: float, currency: str, reference: str,
                       email: str = None, **kwargs) -> Dict[str, Any]:
        """Create Fibank vPOS payment"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Session {self.session_token}'
            }
            payload = {
                'merchantId': self.merchant_id,
                'outletId': self.outlet_id,
                'amount': int(amount * 100),  # Fibank uses cents
                'currency': currency,
                'reference': reference,
                'email': email,
                'description': f'Payment for order {reference}'
            }
            response = requests.post(
                f'{self.base_url}/payments',
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code in [200, 201]:
                return {
                    'success': True,
                    'transaction_id': response.json().get('paymentId'),
                    'status': 'CREATED',
                    'payment_url': response.json().get('redirectUrl'),
                    'response': response.json()
                }
            return {
                'success': False,
                'error': f'Fibank API error: {response.status_code}',
                'response': response.text
            }
        except Exception as e:
            logger.error(f'Fibank create_payment error: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    def authorize_payment(self, transaction_id: str, auth_code: str) -> Dict[str, Any]:
        """Authorize Fibank payment"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Session {self.session_token}'
            }
            payload = {
                'otp': auth_code
            }
            response = requests.post(
                f'{self.base_url}/payments/{transaction_id}/confirm',
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                return {
                    'success': True,
                    'status': 'CONFIRMED',
                    'transaction_id': transaction_id,
                    'response': response.json()
                }
            return {
                'success': False,
                'error': f'Confirmation failed: {response.status_code}',
                'response': response.text
            }
        except Exception as e:
            logger.error(f'Fibank authorize_payment error: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    def get_transaction_status(self, transaction_id: str) -> Dict[str, Any]:
        """Get Fibank transaction status"""
        try:
            headers = {
                'Authorization': f'Session {self.session_token}'
            }
            response = requests.get(
                f'{self.base_url}/payments/{transaction_id}',
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                return {
                    'success': True,
                    'status': response.json().get('status'),
                    'response': response.json()
                }
            return {'success': False, 'error': 'Payment not found'}
        except Exception as e:
            logger.error(f'Fibank get_transaction_status error: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    def refund_transaction(self, transaction_id: str, amount: float = None) -> Dict[str, Any]:
        """Refund Fibank transaction"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Session {self.session_token}'
            }
            payload = {}
            if amount:
                payload['amount'] = int(amount * 100)
            
            response = requests.post(
                f'{self.base_url}/payments/{transaction_id}/refund',
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                return {
                    'success': True,
                    'status': 'REFUNDED',
                    'response': response.json()
                }
            return {
                'success': False,
                'error': f'Refund failed: {response.status_code}',
                'response': response.text
            }
        except Exception as e:
            logger.error(f'Fibank refund_transaction error: {str(e)}')
            return {'success': False, 'error': str(e)}


class KCBVPOSProvider(VPOSProvider):
    """KBC Bank vPOS Terminal Integration"""
    
    def __init__(self, merchant_id: str, api_key: str, outlet_id: str, **kwargs):
        super().__init__(merchant_id, api_key, outlet_id,
                        base_url='https://api.kbc.bg/vpos', **kwargs)
        self.access_token = None
    
    def authenticate(self) -> bool:
        """Authenticate with KBC API"""
        try:
            auth_tuple = (self.merchant_id, self.api_key)
            response = requests.post(
                f'{self.base_url}/auth',
                auth=auth_tuple,
                timeout=10
            )
            if response.status_code == 200:
                self.access_token = response.json().get('token')
                return True
            logger.error(f'KBC authentication failed: {response.text}')
            return False
        except Exception as e:
            logger.error(f'KBC authentication error: {str(e)}')
            return False
    
    def create_payment(self, amount: float, currency: str, reference: str,
                       email: str = None, **kwargs) -> Dict[str, Any]:
        """Create KBC vPOS payment"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.access_token}'
            }
            payload = {
                'merchant': self.merchant_id,
                'outlet': self.outlet_id,
                'amount': amount,
                'currency': currency,
                'orderId': reference,
                'email': email
            }
            response = requests.post(
                f'{self.base_url}/payment/create',
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code in [200, 201]:
                return {
                    'success': True,
                    'transaction_id': response.json().get('transactionId'),
                    'status': 'INITIATED',
                    'payment_url': response.json().get('redirectUrl'),
                    'response': response.json()
                }
            return {
                'success': False,
                'error': f'KBC API error: {response.status_code}',
                'response': response.text
            }
        except Exception as e:
            logger.error(f'KBC create_payment error: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    def authorize_payment(self, transaction_id: str, auth_code: str) -> Dict[str, Any]:
        """Authorize KBC payment"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.access_token}'
            }
            payload = {
                'authCode': auth_code,
                'scaMethod': 'OTP'
            }
            response = requests.post(
                f'{self.base_url}/payment/{transaction_id}/authorize',
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                return {
                    'success': True,
                    'status': 'AUTHORIZED',
                    'transaction_id': transaction_id,
                    'response': response.json()
                }
            return {
                'success': False,
                'error': f'Authorization failed: {response.status_code}',
                'response': response.text
            }
        except Exception as e:
            logger.error(f'KBC authorize_payment error: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    def get_transaction_status(self, transaction_id: str) -> Dict[str, Any]:
        """Get KBC transaction status"""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            response = requests.get(
                f'{self.base_url}/payment/{transaction_id}',
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                return {
                    'success': True,
                    'status': response.json().get('status'),
                    'response': response.json()
                }
            return {'success': False, 'error': 'Transaction not found'}
        except Exception as e:
            logger.error(f'KBC get_transaction_status error: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    def refund_transaction(self, transaction_id: str, amount: float = None) -> Dict[str, Any]:
        """Refund KBC transaction"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.access_token}'
            }
            payload = {}
            if amount:
                payload['amount'] = amount
            
            response = requests.post(
                f'{self.base_url}/payment/{transaction_id}/refund',
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                return {
                    'success': True,
                    'status': 'REFUNDED',
                    'response': response.json()
                }
            return {
                'success': False,
                'error': f'Refund failed: {response.status_code}',
                'response': response.text
            }
        except Exception as e:
            logger.error(f'KBC refund_transaction error: {str(e)}')
            return {'success': False, 'error': str(e)}


class PayseraVPOSProvider(VPOSProvider):
    """Paysera vPOS Terminal Integration"""
    
    def __init__(self, merchant_id: str, api_key: str, outlet_id: str, **kwargs):
        super().__init__(merchant_id, api_key, outlet_id,
                        base_url='https://www.paysera.com/api/v1', **kwargs)
        self.project_id = kwargs.get('project_id', merchant_id)
    
    def authenticate(self) -> bool:
        """Authenticate with Paysera API"""
        try:
            headers = {
                'Content-Type': 'application/json'
            }
            payload = {
                'projectId': self.project_id,
                'apiKey': self.api_key
            }
            response = requests.post(
                f'{self.base_url}/authenticate',
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                return True
            logger.error(f'Paysera authentication failed: {response.text}')
            return False
        except Exception as e:
            logger.error(f'Paysera authentication error: {str(e)}')
            return False
    
    def create_payment(self, amount: float, currency: str, reference: str,
                       email: str = None, **kwargs) -> Dict[str, Any]:
        """Create Paysera payment"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
            payload = {
                'projectId': self.project_id,
                'amount': int(amount * 100),  # Paysera uses cents
                'currency': currency,
                'orderId': reference,
                'customerEmail': email,
                'paymentMethod': 'CARD',
                'locale': 'en'
            }
            response = requests.post(
                f'{self.base_url}/payment',
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code in [200, 201]:
                return {
                    'success': True,
                    'transaction_id': response.json().get('orderId'),
                    'status': 'PENDING',
                    'payment_url': response.json().get('paymentUrl'),
                    'response': response.json()
                }
            return {
                'success': False,
                'error': f'Paysera API error: {response.status_code}',
                'response': response.text
            }
        except Exception as e:
            logger.error(f'Paysera create_payment error: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    def authorize_payment(self, transaction_id: str, auth_code: str) -> Dict[str, Any]:
        """Authorize Paysera payment"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
            payload = {
                'status': 'CONFIRM',
                'authCode': auth_code
            }
            response = requests.post(
                f'{self.base_url}/payment/{transaction_id}',
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                return {
                    'success': True,
                    'status': 'CONFIRMED',
                    'transaction_id': transaction_id,
                    'response': response.json()
                }
            return {
                'success': False,
                'error': f'Confirmation failed: {response.status_code}',
                'response': response.text
            }
        except Exception as e:
            logger.error(f'Paysera authorize_payment error: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    def get_transaction_status(self, transaction_id: str) -> Dict[str, Any]:
        """Get Paysera transaction status"""
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}'
            }
            response = requests.get(
                f'{self.base_url}/payment/{transaction_id}',
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                return {
                    'success': True,
                    'status': response.json().get('status'),
                    'response': response.json()
                }
            return {'success': False, 'error': 'Payment not found'}
        except Exception as e:
            logger.error(f'Paysera get_transaction_status error: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    def refund_transaction(self, transaction_id: str, amount: float = None) -> Dict[str, Any]:
        """Refund Paysera transaction"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
            payload = {
                'refundAmount': int(amount * 100) if amount else None
            }
            response = requests.post(
                f'{self.base_url}/payment/{transaction_id}/refund',
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                return {
                    'success': True,
                    'status': 'REFUNDED',
                    'response': response.json()
                }
            return {
                'success': False,
                'error': f'Refund failed: {response.status_code}',
                'response': response.text
            }
        except Exception as e:
            logger.error(f'Paysera refund_transaction error: {str(e)}')
            return {'success': False, 'error': str(e)}


# Factory for creating provider instances
PROVIDERS = {
    'DSK': DSKVPOSProvider,
    'FIBANK': FibankVPOSProvider,
    'KBC': KCBVPOSProvider,
    'PAYSERA': PayseraVPOSProvider,
}


def get_vpos_provider(provider_name: str, merchant_id: str, api_key: str, 
                     outlet_id: str, **kwargs) -> Optional[VPOSProvider]:
    """Factory function to get a vPOS provider instance"""
    provider_class = PROVIDERS.get(provider_name.upper())
    if provider_class:
        return provider_class(merchant_id, api_key, outlet_id, **kwargs)
    logger.error(f'Unknown vPOS provider: {provider_name}')
    return None
