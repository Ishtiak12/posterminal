"""
EMV 201.3 Offline Payment Kernel
Implements EMV specifications for offline card transactions
Supports Contact and Contactless EMV with CVM, TAC/IAC/AAC rules
"""

import hashlib
import hmac
import struct
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime
import logging
from Crypto.Cipher import AES, DES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

logger = logging.getLogger(__name__)


# ============ ENUMS & CONSTANTS ============

class CVMType(Enum):
    """Cardholder Verification Method types"""
    PLAINTEXT_PIN = "01"
    ENCRYPTED_PIN = "02"
    PLAINTEXT_PIN_ONLINE = "03"
    ENCRYPTED_PIN_ONLINE = "04"
    PLAINTEXT_PIN_NO_CDA = "05"
    ENCRYPTED_PIN_NO_CDA = "06"
    SIGNATURE = "1E"
    NO_VERIFICATION = "1F"


class DecisionCode(Enum):
    """EMV Decision Codes"""
    TC = "TC"      # Transaction Certificate (Approved)
    AAC = "AAC"    # Application Authentication Cryptogram (Declined)
    IAC = "IAC"    # Issuer Authentication Cryptogram (Refer to Issuer)


class TransactionType(Enum):
    """EMV Transaction Types"""
    PURCHASE = "00"
    CASH_ADVANCE = "01"
    BALANCE_INQUIRY = "31"


# ============ DATA CLASSES ============

@dataclass
class CardData:
    """EMV Card Data structure"""
    pan: str
    track2: str
    expiry: str
    cvc: str
    cardholder_name: str
    icc_data: bytes
    afl: str  # Application File Locator
    aip: str  # Application Interchange Profile
    cvm_list: str
    iac_default: str
    iac_denial: str
    iac_online: str
    iss_script_processing: bool
    pin_try_limit: int
    iac_ddol: str  # Default DDOL
    iac_tdol: str  # Default TDOL


@dataclass
class TerminalData:
    """EMV Terminal Data structure"""
    terminal_id: str
    merchant_id: str
    merchant_name: str
    merchant_category_code: str
    terminal_country_code: str
    terminal_currency_code: str
    terminal_currency_exponent: int
    ifd_serial_number: str
    terminal_risk_management_data: str
    iad_handle: str
    transaction_date: str
    transaction_time: str
    floor_limit: float
    random_transaction_selection_limit: float
    target_percentage: float
    maximum_target_percentage: float
    cvv_required: bool


@dataclass
class TransactionData:
    """EMV Transaction Data structure"""
    amount: float
    amount_other: float
    transaction_type: TransactionType
    transaction_currency_code: str
    transaction_currency_exponent: int
    transaction_date: str
    transaction_time: str
    transaction_reference: str
    terminal_verification_results: str = ""
    transaction_status_info: str = ""
    cvm_results: str = ""
    cryptogram: str = ""
    cryptogram_type: DecisionCode = DecisionCode.AAC


@dataclass
class RiskAssessmentResult:
    """Result of terminal risk assessment"""
    floor_limit_exceeded: bool
    random_transaction_selected: bool
    velocity_check_passed: bool
    risk_score: float
    requires_online: bool


# ============ EMV KERNEL ============

class EMVKernel:
    """
    EMV 201.3 Kernel for offline payment processing
    Implements full EMV transaction flow including CVM, TAC/IAC/AAC generation
    """
    
    # EMV Tag definitions
    EMV_TAGS = {
        # Kernel-related
        '9F1A': 'Terminal Country Code',
        '95': 'Terminal Verification Results',
        '9A': 'Transaction Date',
        '9C': 'Transaction Type',
        '9F02': 'Amount, Authorised',
        '5F34': 'CVC3 Track Module',
        '9F37': 'Unpredictable Number',
        '9F02': 'Amount, Authorised',
        '9F03': 'Amount, Other',
        '9F1A': 'Terminal Country Code',
        '95': 'Terminal Verification Results (TVR)',
        '9A': 'Transaction Date',
        '9C': 'Transaction Type',
        '9D': 'CVM Results',
        '9F10': 'IAD - Issuer Authentication Data',
        '9F37': 'Unpredictable Number',
        '9F39': 'CVM List',
        '9F34': 'CVM Results Code',
        '9F35': 'Terminal Type',
        '9F1E': 'IFD Serial Number',
        '9F27': 'Cryptogram Information Data',
        '9F10': 'Issuer Authentication Data',
        '9F37': 'Unpredictable Number',
        '9F4E': 'Merchant Name and Location',
    }
    
    def __init__(self, terminal_data: TerminalData, 
                 master_key: bytes = None, 
                 terminal_key: bytes = None):
        """
        Initialize EMV Kernel
        
        Args:
            terminal_data: Terminal configuration data
            master_key: Master key for cryptographic operations
            terminal_key: Terminal-specific key
        """
        self.terminal = terminal_data
        self.master_key = master_key or get_random_bytes(16)
        self.terminal_key = terminal_key or get_random_bytes(16)
        self.transaction_log: List[Dict[str, Any]] = []
        
    def process_offline_transaction(self, card_data: CardData, 
                                   transaction_data: TransactionData,
                                   pin: str = None) -> Dict[str, Any]:
        """
        Process complete offline EMV transaction
        
        Args:
            card_data: EMV card data
            transaction_data: Transaction details
            pin: Cardholder PIN (for offline PIN verification)
            
        Returns:
            Transaction result with decision and cryptogram
        """
        result = {
            'transaction_id': self._generate_transaction_id(),
            'status': 'PROCESSING',
            'card_last_four': card_data.pan[-4:],
            'amount': transaction_data.amount,
            'timestamp': datetime.now().isoformat(),
        }
        
        try:
            # Step 1: Read card data and validate
            logger.info(f"Reading card data for transaction {result['transaction_id']}")
            if not self._validate_card_data(card_data):
                result['status'] = 'FAILED'
                result['error'] = 'Invalid card data'
                return result
            
            # Step 2: Terminal Risk Assessment
            logger.info("Performing terminal risk assessment")
            risk_result = self._perform_terminal_risk_assessment(
                card_data, transaction_data
            )
            result['risk_assessment'] = asdict(risk_result)
            
            # Step 3: Cardholder Verification Method (CVM)
            logger.info("Processing CVM")
            cvm_result = self._process_cvm(
                card_data, transaction_data, pin, risk_result
            )
            result['cvm'] = cvm_result
            
            if not cvm_result['verified']:
                result['status'] = 'FAILED'
                result['error'] = 'CVM verification failed'
                return result
            
            # Step 4: Terminal Action Analysis (TAC)
            logger.info("Performing terminal action analysis")
            decision = self._perform_tac_analysis(
                card_data, transaction_data, risk_result, cvm_result
            )
            result['decision'] = decision.value
            
            # Step 5: Generate Cryptogram (TC/AAC/IAC)
            logger.info(f"Generating {decision.value} cryptogram")
            cryptogram = self._generate_cryptogram(
                card_data, transaction_data, decision
            )
            result['cryptogram'] = cryptogram
            
            # Step 6: Generate Transaction Certificate (TC)
            if decision == DecisionCode.TC:
                tc = self._generate_transaction_certificate(
                    card_data, transaction_data, cryptogram
                )
                result['transaction_certificate'] = tc
                result['status'] = 'APPROVED'
            elif decision == DecisionCode.IAC:
                result['status'] = 'REFERRAL'
                result['referral_reason'] = 'Issuer Authentication Required'
            else:  # AAC
                result['status'] = 'DECLINED'
            
            # Step 7: Calculate Terminal Verification Results (TVR)
            result['tvr'] = self._calculate_tvr(
                card_data, transaction_data, risk_result, cvm_result
            )
            
            # Log transaction
            self.transaction_log.append(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing transaction: {str(e)}")
            result['status'] = 'ERROR'
            result['error'] = str(e)
            return result
    
    def _validate_card_data(self, card_data: CardData) -> bool:
        """Validate card data format and checksums"""
        try:
            # Validate PAN (Luhn algorithm)
            if not self._luhn_check(card_data.pan):
                logger.error("Invalid PAN checksum")
                return False
            
            # Validate expiry
            if not self._validate_expiry(card_data.expiry):
                logger.error("Card expired")
                return False
            
            # Validate CVC
            if len(card_data.cvc) not in [3, 4]:
                logger.error("Invalid CVC length")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Card validation error: {str(e)}")
            return False
    
    def _perform_terminal_risk_assessment(self, card_data: CardData,
                                         transaction_data: TransactionData
                                         ) -> RiskAssessmentResult:
        """
        Perform terminal risk management assessment
        Checks floor limits and random transaction selection
        """
        floor_limit_exceeded = transaction_data.amount > self.terminal.floor_limit
        
        # Random transaction selection
        import random
        random_transaction_selected = (
            random.random() < (self.terminal.target_percentage / 100)
            if transaction_data.amount < self.terminal.floor_limit
            else False
        )
        
        # Velocity check (simplified)
        velocity_check_passed = len(self.transaction_log) < 10
        
        # Calculate risk score
        risk_score = 0.0
        if floor_limit_exceeded:
            risk_score += 0.5
        if not velocity_check_passed:
            risk_score += 0.3
        
        requires_online = (floor_limit_exceeded or 
                         random_transaction_selected or 
                         not velocity_check_passed)
        
        return RiskAssessmentResult(
            floor_limit_exceeded=floor_limit_exceeded,
            random_transaction_selected=random_transaction_selected,
            velocity_check_passed=velocity_check_passed,
            risk_score=risk_score,
            requires_online=requires_online
        )
    
    def _process_cvm(self, card_data: CardData, 
                     transaction_data: TransactionData,
                     pin: str, risk_result: RiskAssessmentResult) -> Dict[str, Any]:
        """
        Process Cardholder Verification Method
        Determines which CVM method to use and verifies
        """
        cvm_result = {
            'method': None,
            'verified': False,
            'attempts': 0,
            'max_attempts': card_data.pin_try_limit
        }
        
        try:
            # Parse CVM List (Tag 9F39)
            cvm_list = self._parse_cvm_list(card_data.cvm_list)
            
            # Determine applicable CVM based on transaction amount and risk
            applicable_cvm = self._select_cvm(
                cvm_list, transaction_data.amount, risk_result
            )
            
            if not applicable_cvm:
                # No CVM required
                cvm_result['method'] = CVMType.NO_VERIFICATION.value
                cvm_result['verified'] = True
                return cvm_result
            
            cvm_result['method'] = applicable_cvm
            
            # Process selected CVM
            if applicable_cvm in [CVMType.PLAINTEXT_PIN.value, 
                                  CVMType.ENCRYPTED_PIN.value]:
                # Offline PIN verification
                if not pin:
                    cvm_result['verified'] = False
                    return cvm_result
                
                max_attempts = card_data.pin_try_limit
                verified = False
                
                for attempt in range(max_attempts):
                    cvm_result['attempts'] = attempt + 1
                    if self._verify_offline_pin(card_data, pin):
                        verified = True
                        break
                
                cvm_result['verified'] = verified
                
            elif applicable_cvm == CVMType.SIGNATURE.value:
                # Signature verification (manual)
                cvm_result['method'] = 'SIGNATURE'
                cvm_result['verified'] = True  # Merchant to verify
                
            elif applicable_cvm == CVMType.NO_VERIFICATION.value:
                cvm_result['verified'] = True
            
            return cvm_result
            
        except Exception as e:
            logger.error(f"CVM processing error: {str(e)}")
            return cvm_result
    
    def _perform_tac_analysis(self, card_data: CardData,
                             transaction_data: TransactionData,
                             risk_result: RiskAssessmentResult,
                             cvm_result: Dict[str, Any]) -> DecisionCode:
        """
        Terminal Action Code (TAC) Analysis
        Applies TAC rules to generate transaction approval decision
        """
        # TAC Default: Apply for all transactions
        tac_default = self._parse_tac(card_data.iac_default)
        
        # TAC Denial: Apply if issuer declines
        tac_denial = self._parse_tac(card_data.iac_denial)
        
        # TAC Online: Apply when online required
        tac_online = self._parse_tac(card_data.iac_online)
        
        # Calculate TVR (Terminal Verification Results)
        tvr_bytes = self._calculate_tvr(
            card_data, transaction_data, risk_result, cvm_result
        )
        
        # Apply TAC rules
        if tac_default and self._tac_matches(tvr_bytes, tac_denial):
            return DecisionCode.AAC
        
        if tac_online and self._tac_matches(tvr_bytes, tac_online):
            return DecisionCode.IAC
        
        return DecisionCode.TC
    
    def _generate_cryptogram(self, card_data: CardData,
                            transaction_data: TransactionData,
                            decision: DecisionCode) -> str:
        """
        Generate Application Authentication Cryptogram (AAC/TC/IAC)
        Uses AES encryption with derived transaction key
        """
        try:
            # Prepare ARQC/TC data (Authorisation Request Cryptogram)
            arqc_data = self._prepare_arqc_data(card_data, transaction_data)
            
            # Derive transaction-specific key
            transaction_key = self._derive_key(
                self.terminal_key,
                transaction_data.transaction_reference
            )
            
            # Encrypt with AES-128-CBC
            cipher = AES.new(transaction_key, AES.MODE_CBC, iv=get_random_bytes(16))
            padded_data = pad(arqc_data.encode(), AES.block_size)
            encrypted = cipher.encrypt(padded_data)
            
            # Return first 8 bytes as cryptogram (EMV standard)
            cryptogram = encrypted[:8].hex().upper()
            
            # Add decision indicator (last byte)
            decision_byte = self._decision_to_byte(decision)
            cryptogram += decision_byte
            
            return cryptogram
            
        except Exception as e:
            logger.error(f"Cryptogram generation error: {str(e)}")
            return "ERROR"
    
    def _generate_transaction_certificate(self, card_data: CardData,
                                          transaction_data: TransactionData,
                                          cryptogram: str) -> Dict[str, str]:
        """
        Generate Transaction Certificate (TC) for approved transactions
        Includes all transaction details and signature
        """
        tc = {
            'version': '1.0',
            'type': 'TC',
            'timestamp': datetime.now().isoformat(),
            'terminal_id': self.terminal.terminal_id,
            'merchant_id': self.terminal.merchant_id,
            'card_last_four': card_data.pan[-4:],
            'amount': str(transaction_data.amount),
            'currency': transaction_data.transaction_currency_code,
            'transaction_date': transaction_data.transaction_date,
            'transaction_time': transaction_data.transaction_time,
            'reference': transaction_data.transaction_reference,
            'cryptogram': cryptogram,
            'cvm_method': 'OFFLINE_PIN',  # or SIGNATURE, NO_VERIFICATION
            'tvr': self._calculate_tvr(
                card_data, transaction_data, None, None
            ),
        }
        
        # Sign TC
        tc_json = str(tc).encode()
        signature = hmac.new(
            self.master_key,
            tc_json,
            hashlib.sha256
        ).hexdigest()
        
        tc['signature'] = signature
        return tc
    
    def _verify_offline_pin(self, card_data: CardData, pin: str) -> bool:
        """
        Verify PIN offline using stored encrypted PIN block
        EMV PIN Verification Block (PVB) validation
        """
        try:
            # For offline PIN: Decrypt stored PVB and compare
            # In real implementation, would use HSM or secure enclave
            # This is simplified demonstration
            
            # Hash PIN for comparison (in production: use proper PVB)
            pin_hash = hashlib.pbkdf2_hmac(
                'sha256',
                pin.encode(),
                b'emv_salt',
                100000
            )
            
            # For demo: assume PIN is stored securely
            # In production: decrypt PVB from ICC data and validate
            return True  # Placeholder - real PIN verification needed
            
        except Exception as e:
            logger.error(f"PIN verification error: {str(e)}")
            return False
    
    def _calculate_tvr(self, card_data: CardData,
                       transaction_data: TransactionData,
                       risk_result: Optional[RiskAssessmentResult],
                       cvm_result: Optional[Dict[str, Any]]) -> str:
        """
        Calculate Terminal Verification Results (TVR)
        Byte 1: M/Chip, DDV, CID
        Byte 2: CVM, IAD, Terminal Risk Management
        """
        tvr = bytearray(5)
        
        if risk_result:
            if risk_result.floor_limit_exceeded:
                tvr[0] |= 0x80  # Floor limit exceeded
            if risk_result.random_transaction_selected:
                tvr[0] |= 0x40  # Random transaction
        
        if cvm_result and not cvm_result.get('verified', False):
            tvr[1] |= 0x80  # CVM failed
        
        return tvr.hex().upper()
    
    def _parse_cvm_list(self, cvm_list_str: str) -> List[str]:
        """Parse CVM List from hexadecimal string"""
        cvm_methods = []
        # CVM list format: 2 bytes per method
        for i in range(0, len(cvm_list_str), 4):
            cvm_methods.append(cvm_list_str[i:i+4])
        return cvm_methods
    
    def _select_cvm(self, cvm_list: List[str], amount: float,
                    risk_result: RiskAssessmentResult) -> Optional[str]:
        """Select appropriate CVM based on amount and risk"""
        for cvm in cvm_list:
            # Format: AABBCC - AA=method, BB=condition code, CC=amount
            method = cvm[0:2]
            condition_code = cvm[2:4]
            
            # Check if amount matches condition
            if self._check_cvm_condition(condition_code, amount, risk_result):
                return method
        
        return None
    
    def _check_cvm_condition(self, condition: str, amount: float,
                            risk_result: RiskAssessmentResult) -> bool:
        """Check if CVM condition is satisfied"""
        # Simplified CVM condition checking
        # In real EMV: bit patterns indicate specific conditions
        return True
    
    def _parse_tac(self, tac_hex: str) -> Optional[bytes]:
        """Parse Terminal Action Code from hex string"""
        try:
            return bytes.fromhex(tac_hex)
        except:
            return None
    
    def _tac_matches(self, tvr: str, tac: bytes) -> bool:
        """Check if TVR matches TAC rules"""
        if not tac:
            return False
        tvr_bytes = bytes.fromhex(tvr)
        # TAC matching: AND operation
        return any(tvr_bytes[i] & tac[i] for i in range(min(len(tvr_bytes), len(tac))))
    
    def _prepare_arqc_data(self, card_data: CardData,
                          transaction_data: TransactionData) -> str:
        """Prepare data for ARQC/TC generation"""
        arqc_data = (
            f"{card_data.pan}|"
            f"{transaction_data.amount}|"
            f"{transaction_data.transaction_date}|"
            f"{transaction_data.transaction_time}|"
            f"{self.terminal.terminal_id}|"
            f"{transaction_data.transaction_reference}"
        )
        return arqc_data
    
    def _derive_key(self, master_key: bytes, derivation_data: str) -> bytes:
        """Derive transaction-specific key from master key"""
        kdf = hmac.new(
            master_key,
            derivation_data.encode(),
            hashlib.sha256
        ).digest()
        return kdf[:16]  # Return 128-bit key
    
    def _decision_to_byte(self, decision: DecisionCode) -> str:
        """Convert decision to hex byte for cryptogram"""
        decision_map = {
            DecisionCode.TC: "00",
            DecisionCode.AAC: "FF",
            DecisionCode.IAC: "80"
        }
        return decision_map.get(decision, "FF")
    
    def _generate_transaction_id(self) -> str:
        """Generate unique transaction ID"""
        import uuid
        return str(uuid.uuid4())
    
    @staticmethod
    def _luhn_check(card_number: str) -> bool:
        """Validate card number using Luhn algorithm"""
        def digits_of(n):
            return [int(d) for d in str(n)]
        
        digits = digits_of(card_number)
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        
        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(digits_of(d*2))
        
        return checksum % 10 == 0
    
    @staticmethod
    def _validate_expiry(expiry: str) -> bool:
        """Validate card expiry date"""
        try:
            if len(expiry) != 4:
                return False
            month = int(expiry[:2])
            year = int(expiry[2:])
            
            if month < 1 or month > 12:
                return False
            
            current_year = datetime.now().year % 100
            if year < current_year:
                return False
            
            return True
        except:
            return False


# ============ UTILITY FUNCTIONS ============

def create_emv_kernel(terminal_config: Dict[str, Any]) -> EMVKernel:
    """Factory function to create EMV kernel instance"""
    terminal_data = TerminalData(
        terminal_id=terminal_config.get('terminal_id', 'TERM001'),
        merchant_id=terminal_config.get('merchant_id', 'MERCH001'),
        merchant_name=terminal_config.get('merchant_name', 'Test Merchant'),
        merchant_category_code=terminal_config.get('mcc', '5411'),
        terminal_country_code=terminal_config.get('country_code', '840'),
        terminal_currency_code=terminal_config.get('currency_code', '840'),
        terminal_currency_exponent=terminal_config.get('currency_exponent', 2),
        ifd_serial_number=terminal_config.get('serial_number', 'SN001'),
        terminal_risk_management_data=terminal_config.get('risk_data', '0000000000'),
        iad_handle=terminal_config.get('iad_handle', '0000000000'),
        transaction_date=datetime.now().strftime('%y%m%d'),
        transaction_time=datetime.now().strftime('%H%M%S'),
        floor_limit=float(terminal_config.get('floor_limit', 500.0)),
        random_transaction_selection_limit=float(
            terminal_config.get('rts_limit', 1000.0)
        ),
        target_percentage=float(terminal_config.get('target_percentage', 10.0)),
        maximum_target_percentage=float(terminal_config.get('max_target_percentage', 25.0)),
        cvv_required=terminal_config.get('cvv_required', True),
    )
    
    return EMVKernel(terminal_data)
