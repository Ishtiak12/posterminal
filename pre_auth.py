"""
Open Banking Pre-Authentication Implementation
Implements OpenAPI specification for Pre-Authentication flows
"""
import uuid
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class PreAuthenticationStatus(Enum):
    """Pre-authentication status enum"""
    OPEN = "Open"
    PENDING = "Pending"
    REJECTED = "Rejected"
    AUTHORISED = "Authorised"
    EXPIRED = "Expired"
    REVOKED = "Revoked"
    ERROR = "Error"


class SCAMethodType(Enum):
    """Strong Customer Authentication method types"""
    SMS_OTP = "SMS_OTP"
    CHIP_OTP = "CHIP_OTP"
    PHOTO_OTP = "PHOTO_OTP"
    PUSH_OTP = "PUSH_OTP"
    SMTP_OTP = "SMTP_OTP"


class PreAuthentication:
    """Pre-authentication session management"""
    
    def __init__(self, psu_id: str, aspsp_id: str, scope: str = "AIS+PIS",
                 consent_id: str = None, payment_id: str = None):
        self.pre_auth_id = str(uuid.uuid4())
        self.psu_id = psu_id
        self.aspsp_id = aspsp_id
        self.scope = scope
        self.consent_id = consent_id
        self.payment_id = payment_id
        self.status = PreAuthenticationStatus.OPEN.value
        self.created_at = datetime.utcnow()
        self.expires_at = self.created_at + timedelta(hours=24)
        self.updated_at = self.created_at
        
        self.psu_data = {}
        self.psu_credentials = []
        self.permitted_accounts = []
        
        self.sca_methods = []
        self.chosen_sca_method = None
        self.authorization_required_data = None
        
        self.psu_message = None
        self.approval_code = None
        self.auth_challenge_data = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'PreAuthenticationId': self.pre_auth_id,
            'PreAuthenticationStatus': self.status,
            'PsuId': self.psu_id,
            'AspspId': self.aspsp_id,
            'Scope': self.scope,
            'ConsentId': self.consent_id,
            'PaymentId': self.payment_id,
            'CreatedAt': self.created_at.isoformat(),
            'ExpiresAt': self.expires_at.isoformat(),
            'UpdatedAt': self.updated_at.isoformat(),
            'PsuMessage': self.psu_message
        }
    
    def is_expired(self) -> bool:
        """Check if pre-authentication has expired"""
        return datetime.utcnow() > self.expires_at
    
    def can_be_updated(self) -> bool:
        """Check if pre-authentication can be updated"""
        return self.status in [
            PreAuthenticationStatus.OPEN.value,
            PreAuthenticationStatus.PENDING.value
        ] and not self.is_expired()
    
    def update_status(self, new_status: PreAuthenticationStatus):
        """Update pre-authentication status"""
        self.status = new_status.value
        self.updated_at = datetime.utcnow()


class PreAuthenticationService:
    """Service for managing pre-authentication flows"""
    
    def __init__(self):
        self.pre_authentications: Dict[str, PreAuthentication] = {}
        self.audit_log: List[Dict[str, Any]] = []
    
    def create_pre_authentication(self, psu_id: str, psu_data: Dict[str, Any],
                                psu_credentials: List[Dict[str, Any]],
                                permitted_accounts: List[str] = None,
                                scope: str = "AIS+PIS",
                                consent_id: str = None,
                                payment_id: str = None) -> Dict[str, Any]:
        """Create a new pre-authentication session"""
        try:
            # Validate required data
            if not psu_id or not psu_data.get('AspspId'):
                return {
                    'success': False,
                    'error': 'Missing required PSU data',
                    'code': '001'
                }
            
            # Create pre-authentication
            pre_auth = PreAuthentication(
                psu_id=psu_id,
                aspsp_id=psu_data.get('AspspId'),
                scope=scope,
                consent_id=consent_id,
                payment_id=payment_id
            )
            
            pre_auth.psu_data = psu_data
            pre_auth.psu_credentials = psu_credentials
            pre_auth.permitted_accounts = permitted_accounts or []
            pre_auth.status = PreAuthenticationStatus.PENDING.value
            
            # Generate available SCA methods
            pre_auth.sca_methods = self._get_available_sca_methods()
            
            # Build authorization required data
            pre_auth.authorization_required_data = {
                'PsuCredentials': self._build_credential_details(psu_credentials),
                'ScaMethods': pre_auth.sca_methods,
                'ChallengeData': None
            }
            
            # Store pre-authentication
            self.pre_authentications[pre_auth.pre_auth_id] = pre_auth
            
            # Log
            self._log_audit(
                'PRE_AUTH_CREATED',
                pre_auth.pre_auth_id,
                psu_id,
                {'scope': scope}
            )
            
            return {
                'success': True,
                'PreAuthenticationId': pre_auth.pre_auth_id,
                'PreAuthenticationStatus': pre_auth.status,
                'AuthorisationRequiredData': pre_auth.authorization_required_data,
                'Links': self._build_pre_auth_links(pre_auth.pre_auth_id),
                'PsuMessage': 'Pre-authentication initiated. Please select SCA method.'
            }
        except Exception as e:
            logger.error(f'Error creating pre-authentication: {str(e)}')
            return {
                'success': False,
                'error': str(e),
                'code': '004'
            }
    
    def update_pre_authentication(self, pre_auth_id: str,
                                 psu_credentials: List[Dict[str, Any]] = None,
                                 auth_method_id: str = None,
                                 sca_auth_data: str = None) -> Dict[str, Any]:
        """Update pre-authentication with credentials and SCA data"""
        try:
            pre_auth = self.pre_authentications.get(pre_auth_id)
            if not pre_auth:
                return {
                    'success': False,
                    'error': 'Pre-authentication not found',
                    'code': '150'
                }
            
            if not pre_auth.can_be_updated():
                return {
                    'success': False,
                    'error': 'Pre-authentication cannot be updated',
                    'code': '001'
                }
            
            # Update credentials if provided
            if psu_credentials:
                pre_auth.psu_credentials = psu_credentials
                # Verify credentials (simplified)
                if not self._verify_credentials(psu_credentials):
                    pre_auth.update_status(PreAuthenticationStatus.REJECTED)
                    return {
                        'success': False,
                        'error': 'Invalid credentials provided',
                        'code': '001'
                    }
            
            # Select SCA method
            if auth_method_id:
                sca_method = next(
                    (m for m in pre_auth.sca_methods
                     if m.get('AuthenticationMethodId') == auth_method_id),
                    None
                )
                if sca_method:
                    pre_auth.chosen_sca_method = sca_method
                    pre_auth.status = PreAuthenticationStatus.PENDING.value
                    
                    # Generate challenge data based on SCA method
                    pre_auth.auth_challenge_data = \
                        self._generate_challenge_data(sca_method.get('AuthenticationType'))
            
            # Process SCA authentication data
            if sca_auth_data:
                if self._validate_otp(sca_auth_data):
                    pre_auth.approval_code = sca_auth_data
                    pre_auth.update_status(PreAuthenticationStatus.AUTHORISED)
                    self._log_audit(
                        'PRE_AUTH_AUTHORISED',
                        pre_auth_id,
                        pre_auth.psu_id,
                        {}
                    )
                else:
                    return {
                        'success': False,
                        'error': 'Invalid OTP provided',
                        'code': '001'
                    }
            
            pre_auth.updated_at = datetime.utcnow()
            
            return {
                'success': True,
                'PreAuthenticationId': pre_auth_id,
                'PreAuthenticationStatus': pre_auth.status,
                'AuthorisationRequiredData': pre_auth.authorization_required_data,
                'Links': self._build_update_pre_auth_links(pre_auth_id),
                'PsuMessage': self._get_status_message(pre_auth.status)
            }
        except Exception as e:
            logger.error(f'Error updating pre-authentication: {str(e)}')
            return {
                'success': False,
                'error': str(e),
                'code': '004'
            }
    
    def get_pre_authentication_status(self, pre_auth_id: str) -> Dict[str, Any]:
        """Get pre-authentication status"""
        try:
            pre_auth = self.pre_authentications.get(pre_auth_id)
            if not pre_auth:
                return {
                    'success': False,
                    'error': 'Pre-authentication not found',
                    'code': '150'
                }
            
            if pre_auth.is_expired():
                pre_auth.update_status(PreAuthenticationStatus.EXPIRED)
            
            return {
                'success': True,
                'PreAuthenticationId': pre_auth_id,
                'PreAuthenticationStatus': pre_auth.status,
                'PsuMessage': self._get_status_message(pre_auth.status)
            }
        except Exception as e:
            logger.error(f'Error getting pre-authentication status: {str(e)}')
            return {
                'success': False,
                'error': str(e),
                'code': '004'
            }
    
    def delete_pre_authentication(self, pre_auth_id: str) -> Dict[str, Any]:
        """Delete/revoke pre-authentication"""
        try:
            pre_auth = self.pre_authentications.get(pre_auth_id)
            if not pre_auth:
                return {
                    'success': False,
                    'error': 'Pre-authentication not found',
                    'code': '150'
                }
            
            pre_auth.update_status(PreAuthenticationStatus.REVOKED)
            
            self._log_audit(
                'PRE_AUTH_REVOKED',
                pre_auth_id,
                pre_auth.psu_id,
                {}
            )
            
            return {'success': True}
        except Exception as e:
            logger.error(f'Error deleting pre-authentication: {str(e)}')
            return {
                'success': False,
                'error': str(e),
                'code': '004'
            }
    
    def _get_available_sca_methods(self) -> List[Dict[str, Any]]:
        """Get available SCA methods"""
        return [
            {
                'AuthenticationMethodId': 'sms_otp_001',
                'AuthenticationType': 'SMS_OTP',
                'Name': 'SMS OTP',
                'Explanation': 'Receive One Time Password via SMS'
            },
            {
                'AuthenticationMethodId': 'email_otp_001',
                'AuthenticationType': 'SMTP_OTP',
                'Name': 'Email OTP',
                'Explanation': 'Receive One Time Password via Email'
            },
            {
                'AuthenticationMethodId': 'push_otp_001',
                'AuthenticationType': 'PUSH_OTP',
                'Name': 'Push Notification',
                'Explanation': 'Receive OTP via push notification on your mobile device'
            }
        ]
    
    def _build_credential_details(self, psu_credentials: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build credential details structure"""
        return {
            'CredentialsDetails': [
                {
                    'IsSecret': cred.get('IsSecret', True),
                    'CredentialId': cred.get('CredentialId', 'username'),
                    'LabelList': [
                        {
                            'Label': cred.get('Label', 'Username'),
                            'Language': 'en'
                        }
                    ]
                } for cred in psu_credentials
            ]
        }
    
    def _generate_challenge_data(self, sca_type: str) -> Dict[str, Any]:
        """Generate challenge data based on SCA type"""
        import random
        import string
        
        otp = ''.join(random.choices(string.digits, k=6))
        
        return {
            'AdditionalInformation': f'Please enter the OTP sent via {sca_type}',
            'Data': [otp[:3], otp[3:]],
            'OtpFormat': 'NUMERIC',
            'OtpMaxLength': 6
        }
    
    def _verify_credentials(self, psu_credentials: List[Dict[str, Any]]) -> bool:
        """Verify PSU credentials (simplified)"""
        # In production, this would call the actual ASPSP
        return len(psu_credentials) > 0 and all(
            cred.get('CredentialValue') for cred in psu_credentials
        )
    
    def _validate_otp(self, otp: str) -> bool:
        """Validate OTP (simplified - accept 6 digits)"""
        return len(otp) == 6 and otp.isdigit()
    
    def _build_pre_auth_links(self, pre_auth_id: str) -> Dict[str, Dict[str, str]]:
        """Build HATEOAS links for pre-authentication response"""
        return {
            'UpdatePsuCredentialsForPreAuthentication': {
                'Href': f'/xs2a/routingservice/services/ob/auth/v3/psus/{{psuId}}/pre-authentication/{pre_auth_id}'
            },
            'SelectScaMethodsForPreAuthentication': {
                'Href': f'/xs2a/routingservice/services/ob/auth/v3/psus/{{psuId}}/pre-authentication/{pre_auth_id}'
            },
            'AuthorizePreAuthentication': {
                'Href': f'/xs2a/routingservice/services/ob/auth/v3/psus/{{psuId}}/pre-authentication/{pre_auth_id}'
            },
            'GetPreAuthenticationStatus': {
                'Href': f'/xs2a/routingservice/services/ob/auth/v3/psus/{{psuId}}/pre-authentication/{pre_auth_id}/status'
            }
        }
    
    def _build_update_pre_auth_links(self, pre_auth_id: str) -> Dict[str, Dict[str, str]]:
        """Build HATEOAS links for update response"""
        return {
            'SelectScaMethodsForPreAuthentication': {
                'Href': f'/xs2a/routingservice/services/ob/auth/v3/psus/{{psuId}}/pre-authentication/{pre_auth_id}'
            },
            'AuthorizePreAuthentication': {
                'Href': f'/xs2a/routingservice/services/ob/auth/v3/psus/{{psuId}}/pre-authentication/{pre_auth_id}'
            },
            'GetPreAuthenticationStatus': {
                'Href': f'/xs2a/routingservice/services/ob/auth/v3/psus/{{psuId}}/pre-authentication/{pre_auth_id}/status'
            }
        }
    
    def _get_status_message(self, status: str) -> str:
        """Get user-friendly message for status"""
        messages = {
            'Open': 'Pre-authentication session is open',
            'Pending': 'Awaiting PSU authentication',
            'Rejected': 'Pre-authentication was rejected',
            'Authorised': 'Pre-authentication successfully authorised',
            'Expired': 'Pre-authentication session has expired',
            'Revoked': 'Pre-authentication has been revoked',
            'Error': 'An error occurred during pre-authentication'
        }
        return messages.get(status, 'Unknown status')
    
    def _log_audit(self, event_type: str, pre_auth_id: str, psu_id: str,
                   details: Dict[str, Any]):
        """Log audit event"""
        self.audit_log.append({
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'pre_auth_id': pre_auth_id,
            'psu_id': psu_id,
            'details': details
        })
    
    def get_audit_log(self, pre_auth_id: str = None) -> List[Dict[str, Any]]:
        """Get audit log"""
        if pre_auth_id:
            return [log for log in self.audit_log if log['pre_auth_id'] == pre_auth_id]
        return self.audit_log
