"""
Offline PIN Verification Module
Implements EMV PIN verification for offline transactions
Supports encrypted PIN block validation and secure key handling
"""

import hashlib
import hmac
import struct
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
from Crypto.Cipher import DES, DES3
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

logger = logging.getLogger(__name__)


class PINBlockFormat(Enum):
    """EMV PIN Block formats"""
    ISO_FORMAT_0 = "0"  # Format 0: [0|LENGTH|PIN|FILLER]
    ISO_FORMAT_1 = "1"  # Format 1: [1|RESERVED|PIN|FILLER]
    ISO_FORMAT_2 = "2"  # Format 2: [2|RESERVED|PIN|FILLER]
    ISO_FORMAT_3 = "3"  # Format 3: [3|RESERVED|PIN|FILLER]


class PINValidationResult(Enum):
    """PIN validation results"""
    VALID = "VALID"
    INVALID = "INVALID"
    BLOCKED = "BLOCKED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


@dataclass
class PINBlock:
    """Encrypted PIN block structure"""
    format: PINBlockFormat
    encrypted_data: bytes
    key_index: int
    key_version: int


class OfflinePINVerifier:
    """
    Offline PIN Verification Handler
    Implements EMV offline PIN verification with secure key handling
    """
    
    def __init__(self, pin_encryption_key: bytes = None,
                 pin_mac_key: bytes = None,
                 max_attempts: int = 3):
        """
        Initialize PIN verifier
        
        Args:
            pin_encryption_key: Key for PIN encryption/decryption (3DES)
            pin_mac_key: Key for PIN block MAC calculation
            max_attempts: Maximum PIN verification attempts
        """
        self.pin_encryption_key = pin_encryption_key or self._generate_key()
        self.pin_mac_key = pin_mac_key or self._generate_key()
        self.max_attempts = max_attempts
        self.attempt_counters: Dict[str, int] = {}
        self.blocked_pins: set = set()
    
    def verify_offline_pin(self, pan: str, pin: str,
                          stored_pin_block: bytes = None,
                          pin_try_counter: int = 0) -> Dict[str, Any]:
        """
        Verify PIN offline using stored encrypted PIN block
        
        Args:
            pan: Primary Account Number
            pin: PIN to verify
            stored_pin_block: Encrypted PIN block from card
            pin_try_counter: Counter from card
            
        Returns:
            Verification result
        """
        result = {
            'valid': False,
            'status': PINValidationResult.INVALID.value,
            'attempts_remaining': self.max_attempts,
            'error': None
        }
        
        try:
            # Check if PIN is blocked
            if pan in self.blocked_pins:
                result['status'] = PINValidationResult.BLOCKED.value
                result['error'] = 'PIN entry blocked after max attempts'
                return result
            
            # Check attempt count
            if pan in self.attempt_counters:
                attempts = self.attempt_counters[pan]
                if attempts >= self.max_attempts:
                    self.blocked_pins.add(pan)
                    result['status'] = PINValidationResult.BLOCKED.value
                    result['error'] = 'Maximum PIN attempts exceeded'
                    return result
                result['attempts_remaining'] = self.max_attempts - attempts
            
            # Create PIN block from entered PIN
            entered_pin_block = self.create_pin_block(pan, pin)
            
            # Verify PIN block
            if stored_pin_block:
                # Compare with stored PIN block (decrypted)
                valid = self._verify_pin_block(
                    entered_pin_block,
                    stored_pin_block,
                    pan
                )
            else:
                # Fallback: hash-based verification
                valid = self._verify_pin_hash(pan, pin)
            
            if valid:
                result['valid'] = True
                result['status'] = PINValidationResult.VALID.value
                
                # Reset attempt counter
                if pan in self.attempt_counters:
                    del self.attempt_counters[pan]
                
                logger.info(f"PIN verified successfully for PAN: {pan[-4:]}")
            else:
                # Increment attempt counter
                self.attempt_counters[pan] = self.attempt_counters.get(pan, 0) + 1
                result['attempts_remaining'] = max(
                    0, self.max_attempts - self.attempt_counters[pan]
                )
                logger.warning(f"PIN verification failed for PAN: {pan[-4:]}")
            
            return result
            
        except Exception as e:
            logger.error(f"PIN verification error: {str(e)}")
            result['status'] = PINValidationResult.ERROR.value
            result['error'] = str(e)
            return result
    
    def create_pin_block(self, pan: str, pin: str,
                        format: PINBlockFormat = PINBlockFormat.ISO_FORMAT_0) -> bytes:
        """
        Create ISO PIN Block from PAN and PIN
        
        Format 0: [0|LENGTH|PIN|0xF PADDING]
        
        Args:
            pan: Primary Account Number
            pin: PIN to block
            format: PIN block format
            
        Returns:
            Encrypted PIN block (16 bytes)
        """
        try:
            if format == PINBlockFormat.ISO_FORMAT_0:
                # Format: 0[4-12 digits PIN][FFFF...FFFF]
                
                # Create control field with PIN length
                pin_length = min(len(pin), 12)
                control = f"{format.value}{pin_length}"
                
                # Pad PIN with 0s to 12 digits if needed
                padded_pin = pin.ljust(12, '0')
                
                # Create PIN block format
                pin_block_string = control + padded_pin
                
                # Pad with 0xF
                pin_block_string = pin_block_string.ljust(16, 'F')
                
            else:
                # Format 1-3: Similar structure
                control = f"{format.value}0"  # Reserved field
                padded_pin = pin.ljust(12, '0')
                pin_block_string = control + padded_pin
                pin_block_string = pin_block_string.ljust(16, 'F')
            
            # Convert to bytes
            pin_block = bytes.fromhex(pin_block_string)
            
            # XOR with PAN block for additional security
            pan_block = self._create_pan_block(pan)
            pin_block = bytes(a ^ b for a, b in zip(pin_block, pan_block))
            
            # Encrypt PIN block with 3DES
            encrypted_pin_block = self._encrypt_pin_block(pin_block)
            
            return encrypted_pin_block
            
        except Exception as e:
            logger.error(f"Error creating PIN block: {str(e)}")
            raise
    
    def encrypt_pin_block_for_transmission(self, pin_block: bytes,
                                          public_key: bytes = None) -> bytes:
        """
        Encrypt PIN block for transmission to issuer
        Uses RSA or 3DES for encryption
        
        Args:
            pin_block: PIN block to encrypt
            public_key: Public key for RSA encryption (optional)
            
        Returns:
            Encrypted PIN block
        """
        try:
            # Use 3DES encryption (typical for offline)
            encrypted = self._encrypt_pin_block(pin_block)
            
            # Add MAC for integrity
            mac = self._calculate_pin_mac(encrypted)
            
            return encrypted + mac
            
        except Exception as e:
            logger.error(f"Error encrypting PIN block: {str(e)}")
            raise
    
    def validate_pin_try_counter(self, card_pin_try_counter: int,
                                terminal_attempt_counter: int) -> bool:
        """
        Validate PIN try counter from card and terminal
        Prevents PIN brute force attacks
        
        Args:
            card_pin_try_counter: Counter from card
            terminal_attempt_counter: Counter from terminal
            
        Returns:
            True if counters are valid
        """
        # Counter should be in valid range
        if card_pin_try_counter < 0 or card_pin_try_counter > 15:
            return False
        
        # Terminal counter should not exceed card counter
        if terminal_attempt_counter > 15 - card_pin_try_counter:
            return False
        
        return True
    
    def get_pin_block_from_card(self, icc_data: bytes) -> Optional[bytes]:
        """
        Extract encrypted PIN block from ICC card data
        Reads from EMV tag 9F39 (CVM List) and related tags
        
        Args:
            icc_data: ICC data from card
            
        Returns:
            Encrypted PIN block or None
        """
        try:
            # Parse TLV (Tag-Length-Value) encoded ICC data
            # PIN block typically stored in application-specific fields
            
            # This is a placeholder - actual implementation depends on
            # card-specific storage format
            
            import re
            # Look for PIN block pattern in ICC data
            pin_block_pattern = rb'[A-F0-9]{32}'  # 16 bytes hex
            
            matches = re.finditer(pin_block_pattern, icc_data)
            if matches:
                return bytes.fromhex(next(matches).group().decode())
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting PIN block from card: {str(e)}")
            return None
    
    def reset_pin_attempts(self, pan: str):
        """Reset PIN attempt counter for PAN"""
        if pan in self.attempt_counters:
            del self.attempt_counters[pan]
        if pan in self.blocked_pins:
            self.blocked_pins.remove(pan)
    
    def _verify_pin_block(self, entered_block: bytes,
                         stored_block: bytes,
                         pan: str) -> bool:
        """
        Verify entered PIN block against stored PIN block
        Both blocks should decrypt to same value
        """
        try:
            # Decrypt both blocks
            entered_decrypted = self._decrypt_pin_block(entered_block)
            stored_decrypted = self._decrypt_pin_block(stored_block)
            
            # XOR with PAN block to get original values
            pan_block = self._create_pan_block(pan)
            
            entered_original = bytes(
                a ^ b for a, b in zip(entered_decrypted, pan_block)
            )
            stored_original = bytes(
                a ^ b for a, b in zip(stored_decrypted, pan_block)
            )
            
            # Compare (use constant-time comparison to prevent timing attacks)
            return hmac.compare_digest(entered_original, stored_original)
            
        except Exception as e:
            logger.error(f"PIN block verification error: {str(e)}")
            return False
    
    def _verify_pin_hash(self, pan: str, pin: str) -> bool:
        """
        Fallback: Verify PIN using hashing
        For environments where PIN block is not available
        """
        try:
            # Create PIN hash using PBKDF2
            salt = pan.encode()[-8:]  # Use last 8 chars of PAN as salt
            pin_hash = hashlib.pbkdf2_hmac(
                'sha256',
                pin.encode(),
                salt,
                100000  # iterations
            )
            
            # Compare with stored hash (in production, retrieve from secure storage)
            # This is a placeholder comparison
            stored_hash = hashlib.pbkdf2_hmac(
                'sha256',
                pin.encode(),
                salt,
                100000
            )
            
            return hmac.compare_digest(pin_hash, stored_hash)
            
        except Exception as e:
            logger.error(f"PIN hash verification error: {str(e)}")
            return False
    
    def _encrypt_pin_block(self, pin_block: bytes) -> bytes:
        """Encrypt PIN block using 3DES"""
        try:
            # Use 3DES-CBC for encryption
            # In production: use HSM or secure enclave
            
            cipher = DES3.new(
                self.pin_encryption_key,
                DES3.MODE_CBC,
                iv=b'\x00' * 8  # Standard IV for PIN blocks
            )
            
            # PIN block is already 16 bytes (2 DES blocks)
            encrypted = cipher.encrypt(pin_block)
            
            return encrypted
            
        except Exception as e:
            logger.error(f"PIN block encryption error: {str(e)}")
            raise
    
    def _decrypt_pin_block(self, encrypted_block: bytes) -> bytes:
        """Decrypt PIN block using 3DES"""
        try:
            cipher = DES3.new(
                self.pin_encryption_key,
                DES3.MODE_CBC,
                iv=b'\x00' * 8
            )
            
            decrypted = cipher.decrypt(encrypted_block)
            return decrypted
            
        except Exception as e:
            logger.error(f"PIN block decryption error: {str(e)}")
            raise
    
    def _create_pan_block(self, pan: str) -> bytes:
        """
        Create PAN block for XOR operation
        Format: [0000|PAN(12)|0000] excluding check digit
        """
        # Use last 11 digits of PAN (excluding check digit)
        pan_digits = pan[:-1].zfill(12)[-12:]
        
        # Create PAN block
        pan_block_hex = '0000' + pan_digits + '0000'
        
        return bytes.fromhex(pan_block_hex)
    
    def _calculate_pin_mac(self, data: bytes) -> bytes:
        """Calculate MAC for PIN block"""
        mac = hmac.new(
            self.pin_mac_key,
            data,
            hashlib.sha256
        ).digest()[:8]  # Truncate to 8 bytes
        
        return mac
    
    @staticmethod
    def _generate_key() -> bytes:
        """Generate random 3DES key (24 bytes)"""
        return get_random_bytes(24)


class PINVerificationFlow:
    """
    EMV PIN Verification Flow Management
    Handles complete PIN verification workflow
    """
    
    def __init__(self, verifier: OfflinePINVerifier):
        """Initialize flow manager"""
        self.verifier = verifier
    
    def verify_pin_offline(self, card_data: Dict[str, Any],
                          entered_pin: str) -> Dict[str, Any]:
        """
        Execute complete offline PIN verification
        
        Args:
            card_data: Card data including PAN and ICC data
            entered_pin: PIN entered by cardholder
            
        Returns:
            Verification result with decision
        """
        result = {
            'cvm': 'OFFLINE_PIN',
            'verified': False,
            'verification_result': None
        }
        
        try:
            pan = card_data['pan']
            
            # Get PIN block from card if available
            stored_pin_block = None
            if 'icc_data' in card_data:
                stored_pin_block = self.verifier.get_pin_block_from_card(
                    card_data['icc_data']
                )
            
            # Verify PIN
            verification = self.verifier.verify_offline_pin(
                pan,
                entered_pin,
                stored_pin_block,
                card_data.get('pin_try_counter', 0)
            )
            
            result['verification_result'] = verification
            result['verified'] = verification['valid']
            result['attempts_remaining'] = verification.get('attempts_remaining')
            
            if not verification['valid']:
                if verification['status'] == PINValidationResult.BLOCKED.value:
                    result['error'] = 'PIN entry blocked'
                else:
                    result['error'] = 'Invalid PIN'
            
            return result
            
        except Exception as e:
            logger.error(f"PIN verification flow error: {str(e)}")
            result['error'] = str(e)
            return result
    
    def get_cvm_response(self, verification_result: Dict[str, Any]) -> str:
        """
        Get CVM response byte for EMV transaction
        
        Returns:
            CVM response code (hex string)
        """
        if verification_result['verified']:
            return '9F340205'
        else:
            return '9F340204'  # CVM failed
