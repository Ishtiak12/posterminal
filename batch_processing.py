"""
Batch Processing, Settlement, and Reconciliation Module
Handles offline transaction batch upload, settlement, reconciliation, and reversals
"""

import json
import hashlib
import hmac
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import requests
from pathlib import Path

logger = logging.getLogger(__name__)


class BatchStatus(Enum):
    """Batch processing status"""
    PENDING = "PENDING"
    UPLOADED = "UPLOADED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    RECONCILED = "RECONCILED"


class SettlementStatus(Enum):
    """Settlement status"""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ReconciliationStatus(Enum):
    """Reconciliation status"""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    MATCHED = "MATCHED"
    DISCREPANCY = "DISCREPANCY"
    RESOLVED = "RESOLVED"


class ReversalStatus(Enum):
    """Reversal status"""
    PENDING = "PENDING"
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


@dataclass
class BatchHeader:
    """Batch file header"""
    batch_id: str
    terminal_id: str
    merchant_id: str
    batch_sequence: int
    batch_date: str
    transaction_count: int
    total_amount: float
    currency_code: str
    timestamp: str
    version: str = "1.0"


@dataclass
class BatchTransaction:
    """Transaction record in batch"""
    transaction_id: str
    card_last_four: str
    amount: float
    currency: str
    transaction_date: str
    transaction_time: str
    cvm_method: str
    decision: str
    cryptogram: str
    tvr: str


@dataclass
class SettlementRecord:
    """Settlement record"""
    settlement_id: str
    batch_id: str
    settlement_date: str
    settlement_time: str
    transaction_count: int
    total_amount: float
    currency_code: str
    bank_reference: Optional[str] = None
    status: str = SettlementStatus.PENDING.value


class BatchProcessor:
    """
    Batch processing for offline transactions
    Manages creation, formatting, and upload of transaction batches
    """
    
    def __init__(self, storage, api_endpoint: str = None,
                 api_key: str = None):
        """
        Initialize batch processor
        
        Args:
            storage: OfflineTransactionStorage instance
            api_endpoint: Server endpoint for batch upload
            api_key: API key for authentication
        """
        self.storage = storage
        self.api_endpoint = api_endpoint or 'https://api.payment-gateway.com/batch'
        self.api_key = api_key or 'your_api_key'
        self.batch_sequence = 1
    
    def create_batch_file(self, terminal_id: str, merchant_id: str,
                         transaction_ids: List[str]) -> Dict[str, Any]:
        """
        Create batch file with all transaction details
        
        Args:
            terminal_id: Terminal identifier
            merchant_id: Merchant identifier
            transaction_ids: List of transaction IDs to include
            
        Returns:
            Batch file content and metadata
        """
        try:
            # Retrieve all transactions
            transactions = []
            total_amount = 0.0
            
            for tx_id in transaction_ids:
                tx = self.storage.retrieve_transaction(tx_id)
                if tx:
                    transactions.append(tx)
                    total_amount += tx.get('amount', 0)
            
            if not transactions:
                logger.warning("No transactions to batch")
                return None
            
            # Create batch header
            batch_id = self.storage.create_batch_upload(
                terminal_id, merchant_id, transaction_ids
            )
            
            batch_header = BatchHeader(
                batch_id=batch_id,
                terminal_id=terminal_id,
                merchant_id=merchant_id,
                batch_sequence=self.batch_sequence,
                batch_date=datetime.now().strftime('%Y%m%d'),
                transaction_count=len(transactions),
                total_amount=total_amount,
                currency_code='USD',
                timestamp=datetime.now().isoformat()
            )
            
            self.batch_sequence += 1
            
            # Format batch file
            batch_content = self._format_batch_file(batch_header, transactions)
            
            # Calculate batch checksum
            batch_checksum = self._calculate_batch_checksum(batch_content)
            
            logger.info(f"Batch created: {batch_id} with {len(transactions)} transactions")
            
            return {
                'batch_id': batch_id,
                'batch_header': asdict(batch_header),
                'transaction_count': len(transactions),
                'total_amount': total_amount,
                'checksum': batch_checksum,
                'file_content': batch_content
            }
            
        except Exception as e:
            logger.error(f"Error creating batch: {str(e)}")
            return None
    
    def upload_batch(self, batch_data: Dict[str, Any],
                     timeout: int = 30) -> Dict[str, Any]:
        """
        Upload batch to payment gateway
        
        Args:
            batch_data: Batch file data
            timeout: Request timeout
            
        Returns:
            Upload response
        """
        try:
            batch_id = batch_data['batch_id']
            
            # Prepare upload payload
            payload = {
                'batch_id': batch_id,
                'terminal_id': batch_data['batch_header']['terminal_id'],
                'merchant_id': batch_data['batch_header']['merchant_id'],
                'batch_date': batch_data['batch_header']['batch_date'],
                'transaction_count': batch_data['transaction_count'],
                'total_amount': batch_data['total_amount'],
                'checksum': batch_data['checksum'],
                'batch_content': batch_data['file_content']
            }
            
            # Add authentication
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}',
                'X-Batch-ID': batch_id,
                'X-Signature': self._sign_request(payload)
            }
            
            # Upload to server
            response = requests.post(
                f'{self.api_endpoint}/upload',
                json=payload,
                headers=headers,
                timeout=timeout
            )
            
            result = {
                'batch_id': batch_id,
                'status': 'FAILED',
                'response_code': response.status_code,
                'timestamp': datetime.now().isoformat()
            }
            
            if response.status_code == 200:
                response_data = response.json()
                result['status'] = 'UPLOADED'
                result['batch_reference'] = response_data.get('batch_reference')
                result['message'] = response_data.get('message')
                
                # Update storage
                self.storage.update_batch_status(
                    batch_id, 'UPLOADED',
                    response_code=str(response.status_code),
                    response_message=result.get('message')
                )
                
                logger.info(f"Batch uploaded successfully: {batch_id}")
            else:
                result['error'] = response.text
                logger.error(f"Batch upload failed: {response.text}")
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Upload request failed: {str(e)}")
            return {
                'batch_id': batch_data.get('batch_id'),
                'status': 'FAILED',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Upload error: {str(e)}")
            return {
                'status': 'FAILED',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _format_batch_file(self, header: BatchHeader,
                          transactions: List[Dict[str, Any]]) -> str:
        """Format batch file in ISO 8583 or JSON format"""
        # Create batch structure
        batch = {
            'header': {
                'batch_id': header.batch_id,
                'terminal_id': header.terminal_id,
                'merchant_id': header.merchant_id,
                'batch_date': header.batch_date,
                'batch_time': datetime.now().strftime('%H%M%S'),
                'transaction_count': header.transaction_count,
                'total_amount': header.total_amount,
                'currency': header.currency_code,
                'version': header.version
            },
            'transactions': []
        }
        
        # Add transactions
        for tx in transactions:
            batch['transactions'].append({
                'transaction_id': tx.get('id'),
                'card_last_four': tx.get('card_last_four'),
                'amount': tx.get('amount'),
                'currency': tx.get('currency'),
                'date': tx.get('transaction_date'),
                'time': tx.get('transaction_time'),
                'cvm': tx.get('cvm_method'),
                'decision': tx.get('decision'),
                'cryptogram': tx.get('cryptogram'),
                'tvr': tx.get('tvr')
            })
        
        return json.dumps(batch, indent=2)
    
    def _calculate_batch_checksum(self, content: str) -> str:
        """Calculate SHA256 checksum of batch content"""
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _sign_request(self, payload: Dict[str, Any]) -> str:
        """Sign request with HMAC-SHA256"""
        payload_json = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            self.api_key.encode(),
            payload_json.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature


class SettlementProcessor:
    """
    Settlement processing
    Handles settlement of batches and reconciliation with bank
    """
    
    def __init__(self, storage, api_endpoint: str = None,
                 api_key: str = None):
        """Initialize settlement processor"""
        self.storage = storage
        self.api_endpoint = api_endpoint or 'https://api.payment-gateway.com/settlement'
        self.api_key = api_key
    
    def initiate_settlement(self, batch_id: str) -> Dict[str, Any]:
        """
        Initiate settlement for batch
        
        Args:
            batch_id: Batch identifier
            
        Returns:
            Settlement initiation result
        """
        try:
            settlement_date = datetime.now().strftime('%Y%m%d')
            
            # Create settlement record
            settlement_id = self.storage.record_settlement(
                batch_id, settlement_date
            )
            
            if not settlement_id:
                return {
                    'status': 'FAILED',
                    'error': 'Unable to create settlement record'
                }
            
            logger.info(f"Settlement initiated: {settlement_id}")
            
            return {
                'settlement_id': settlement_id,
                'batch_id': batch_id,
                'status': SettlementStatus.PENDING.value,
                'date': settlement_date,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Settlement initiation error: {str(e)}")
            return {
                'status': 'FAILED',
                'error': str(e)
            }
    
    def process_settlement(self, batch_id: str, bank_reference: str = None,
                          timeout: int = 30) -> Dict[str, Any]:
        """
        Process settlement with bank
        
        Args:
            batch_id: Batch identifier
            bank_reference: Bank settlement reference
            timeout: Request timeout
            
        Returns:
            Settlement processing result
        """
        try:
            # Get batch reconciliation status
            status = self.storage.get_reconciliation_status(batch_id)
            
            if not status:
                return {
                    'status': 'FAILED',
                    'error': 'Batch not found'
                }
            
            # Prepare settlement request
            payload = {
                'batch_id': batch_id,
                'settlement_date': datetime.now().strftime('%Y%m%d'),
                'transaction_count': status['transaction_count'],
                'total_amount': status['total_amount'],
                'bank_reference': bank_reference
            }
            
            # Send settlement request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
            
            response = requests.post(
                f'{self.api_endpoint}/process',
                json=payload,
                headers=headers,
                timeout=timeout
            )
            
            if response.status_code == 200:
                response_data = response.json()
                
                logger.info(f"Settlement processed: {batch_id}")
                
                return {
                    'batch_id': batch_id,
                    'status': SettlementStatus.COMPLETED.value,
                    'bank_reference': response_data.get('bank_reference'),
                    'timestamp': datetime.now().isoformat()
                }
            else:
                logger.error(f"Settlement failed: {response.text}")
                return {
                    'batch_id': batch_id,
                    'status': SettlementStatus.FAILED.value,
                    'error': response.text
                }
            
        except Exception as e:
            logger.error(f"Settlement processing error: {str(e)}")
            return {
                'status': SettlementStatus.FAILED.value,
                'error': str(e)
            }


class ReconciliationProcessor:
    """
    Reconciliation processing
    Matches transactions with bank records and resolves discrepancies
    """
    
    def __init__(self, storage, api_endpoint: str = None,
                 api_key: str = None):
        """Initialize reconciliation processor"""
        self.storage = storage
        self.api_endpoint = api_endpoint or 'https://api.payment-gateway.com/reconciliation'
        self.api_key = api_key
    
    def reconcile_batch(self, batch_id: str, bank_data: Dict[str, Any] = None,
                       timeout: int = 30) -> Dict[str, Any]:
        """
        Reconcile batch with bank records
        
        Args:
            batch_id: Batch identifier
            bank_data: Bank transaction data for matching
            timeout: Request timeout
            
        Returns:
            Reconciliation result
        """
        try:
            # Get batch status
            batch_status = self.storage.get_reconciliation_status(batch_id)
            
            if not batch_status:
                return {
                    'status': ReconciliationStatus.FAILED.value,
                    'error': 'Batch not found'
                }
            
            # Fetch bank transaction data if not provided
            if not bank_data:
                bank_data = self._fetch_bank_transactions(batch_id)
            
            # Compare terminal and bank data
            reconciliation = self._match_transactions(batch_status, bank_data)
            
            logger.info(f"Reconciliation complete for batch {batch_id}")
            
            return {
                'batch_id': batch_id,
                'reconciliation_status': reconciliation['status'],
                'matched_count': reconciliation['matched'],
                'discrepancy_count': reconciliation['discrepancies'],
                'details': reconciliation,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Reconciliation error: {str(e)}")
            return {
                'status': ReconciliationStatus.FAILED.value,
                'error': str(e)
            }
    
    def _match_transactions(self, terminal_data: Dict[str, Any],
                           bank_data: Dict[str, Any]) -> Dict[str, Any]:
        """Match terminal transactions with bank data"""
        result = {
            'status': ReconciliationStatus.MATCHED.value,
            'matched': 0,
            'discrepancies': 0,
            'amount_matched': 0.0,
            'amount_discrepancies': 0.0
        }
        
        # Compare amounts and counts
        terminal_count = terminal_data['transaction_count']
        terminal_amount = terminal_data['total_amount']
        
        bank_count = bank_data.get('transaction_count', 0)
        bank_amount = bank_data.get('total_amount', 0.0)
        
        if terminal_count == bank_count and abs(terminal_amount - bank_amount) < 0.01:
            result['matched'] = terminal_count
            result['amount_matched'] = terminal_amount
        else:
            result['status'] = ReconciliationStatus.DISCREPANCY.value
            result['discrepancies'] = abs(terminal_count - bank_count)
            result['amount_discrepancies'] = abs(terminal_amount - bank_amount)
        
        return result
    
    def _fetch_bank_transactions(self, batch_id: str) -> Dict[str, Any]:
        """Fetch bank transaction data for batch"""
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}'
            }
            
            response = requests.get(
                f'{self.api_endpoint}/batch/{batch_id}',
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to fetch bank data: {response.text}")
                return {}
                
        except Exception as e:
            logger.error(f"Error fetching bank data: {str(e)}")
            return {}


class ReversalProcessor:
    """
    Reversal processing
    Handles transaction reversals and refunds
    """
    
    def __init__(self, storage, api_endpoint: str = None,
                 api_key: str = None):
        """Initialize reversal processor"""
        self.storage = storage
        self.api_endpoint = api_endpoint or 'https://api.payment-gateway.com/reversal'
        self.api_key = api_key
    
    def request_reversal(self, transaction_id: str, reason: str = None,
                        reversal_amount: float = None) -> Dict[str, Any]:
        """
        Request transaction reversal
        
        Args:
            transaction_id: Original transaction ID
            reason: Reason for reversal
            reversal_amount: Amount to reverse (for partial reversal)
            
        Returns:
            Reversal request result
        """
        try:
            # Get original transaction
            tx = self.storage.retrieve_transaction(transaction_id)
            
            if not tx:
                return {
                    'status': ReversalStatus.FAILED.value,
                    'error': 'Transaction not found'
                }
            
            # Record reversal
            reversal_id = self.storage.record_reversal(
                transaction_id, reason, reversal_amount
            )
            
            if not reversal_id:
                return {
                    'status': ReversalStatus.FAILED.value,
                    'error': 'Unable to record reversal'
                }
            
            # Send reversal request to payment gateway
            payload = {
                'reversal_id': reversal_id,
                'original_transaction_id': transaction_id,
                'original_reference': tx.get('reference'),
                'reversal_amount': reversal_amount or tx.get('amount'),
                'reason': reason or 'Customer Request'
            }
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
            
            response = requests.post(
                f'{self.api_endpoint}/request',
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                response_data = response.json()
                
                logger.info(f"Reversal requested: {reversal_id}")
                
                return {
                    'reversal_id': reversal_id,
                    'status': ReversalStatus.REQUESTED.value,
                    'approval_code': response_data.get('approval_code'),
                    'timestamp': datetime.now().isoformat()
                }
            else:
                logger.error(f"Reversal request failed: {response.text}")
                return {
                    'reversal_id': reversal_id,
                    'status': ReversalStatus.FAILED.value,
                    'error': response.text
                }
            
        except Exception as e:
            logger.error(f"Reversal request error: {str(e)}")
            return {
                'status': ReversalStatus.FAILED.value,
                'error': str(e)
            }
