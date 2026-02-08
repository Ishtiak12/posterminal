"""
Offline Transaction Storage and Queue Management
Encrypts and stores offline transactions for later synchronization
Provides secure persistence and batch processing capabilities
"""

import os
import json
import sqlite3
import hashlib
import hmac
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import logging
from pathlib import Path
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad
import threading

logger = logging.getLogger(__name__)


@dataclass
class OfflineTransaction:
    """Offline transaction record"""
    id: str
    terminal_id: str
    merchant_id: str
    card_last_four: str
    amount: float
    currency: str
    transaction_date: str
    transaction_time: str
    reference: str
    cvm_method: str
    decision: str  # APPROVED, DECLINED, REFERRAL
    cryptogram: str
    transaction_certificate: str
    tvr: str
    timestamp: str
    status: str  # PENDING, SYNCHRONIZED, SETTLED, FAILED
    batch_id: Optional[str] = None
    settlement_date: Optional[str] = None
    reversal_reference: Optional[str] = None


class OfflineTransactionStorage:
    """
    Secure offline transaction storage with encryption
    Manages transaction persistence and batch operations
    """
    
    def __init__(self, db_path: str = None, encryption_key: bytes = None):
        """
        Initialize offline storage
        
        Args:
            db_path: Path to SQLite database file
            encryption_key: AES encryption key (256-bit)
        """
        self.db_path = db_path or os.path.join(
            Path.home(), '.vpos', 'offline_transactions.db'
        )
        self.encryption_key = encryption_key or get_random_bytes(32)
        self.lock = threading.RLock()
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Initialize database
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database schema"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Offline transactions table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS offline_transactions (
                        id TEXT PRIMARY KEY,
                        terminal_id TEXT NOT NULL,
                        merchant_id TEXT NOT NULL,
                        card_last_four TEXT NOT NULL,
                        amount REAL NOT NULL,
                        currency TEXT NOT NULL,
                        transaction_date TEXT NOT NULL,
                        transaction_time TEXT NOT NULL,
                        reference TEXT UNIQUE NOT NULL,
                        cvm_method TEXT,
                        decision TEXT NOT NULL,
                        cryptogram TEXT NOT NULL,
                        transaction_certificate TEXT,
                        tvr TEXT,
                        timestamp TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'PENDING',
                        batch_id TEXT,
                        settlement_date TEXT,
                        reversal_reference TEXT,
                        encrypted_data BLOB NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Batch transactions table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS batch_uploads (
                        id TEXT PRIMARY KEY,
                        terminal_id TEXT NOT NULL,
                        merchant_id TEXT NOT NULL,
                        batch_date TEXT NOT NULL,
                        transaction_count INTEGER NOT NULL,
                        total_amount REAL NOT NULL,
                        status TEXT NOT NULL DEFAULT 'PENDING',
                        upload_timestamp TEXT,
                        response_code TEXT,
                        response_message TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Settlement records table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS settlements (
                        id TEXT PRIMARY KEY,
                        batch_id TEXT NOT NULL,
                        settlement_date TEXT NOT NULL,
                        amount REAL NOT NULL,
                        transaction_count INTEGER NOT NULL,
                        status TEXT NOT NULL DEFAULT 'PENDING',
                        bank_reference TEXT,
                        reconciliation_status TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (batch_id) REFERENCES batch_uploads(id)
                    )
                ''')
                
                # Reversals table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reversals (
                        id TEXT PRIMARY KEY,
                        transaction_id TEXT NOT NULL,
                        original_reference TEXT NOT NULL,
                        reversal_amount REAL,
                        reason TEXT,
                        status TEXT NOT NULL DEFAULT 'PENDING',
                        approval_code TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (transaction_id) REFERENCES offline_transactions(id)
                    )
                ''')
                
                # Create indexes for performance
                cursor.execute(
                    'CREATE INDEX IF NOT EXISTS idx_status ON offline_transactions(status)'
                )
                cursor.execute(
                    'CREATE INDEX IF NOT EXISTS idx_batch ON offline_transactions(batch_id)'
                )
                cursor.execute(
                    'CREATE INDEX IF NOT EXISTS idx_terminal ON offline_transactions(terminal_id)'
                )
                cursor.execute(
                    'CREATE INDEX IF NOT EXISTS idx_date ON offline_transactions(transaction_date)'
                )
                
                conn.commit()
                logger.info(f"Database initialized: {self.db_path}")
                
        except Exception as e:
            logger.error(f"Database initialization error: {str(e)}")
            raise
    
    def store_transaction(self, transaction: Dict[str, Any]) -> bool:
        """
        Store offline transaction with encryption
        
        Args:
            transaction: Transaction data to store
            
        Returns:
            Success status
        """
        with self.lock:
            try:
                # Convert transaction to offline transaction object
                offline_tx = OfflineTransaction(
                    id=transaction.get('transaction_id'),
                    terminal_id=transaction.get('terminal_id', 'TERM001'),
                    merchant_id=transaction.get('merchant_id', 'MERCH001'),
                    card_last_four=transaction.get('card_last_four'),
                    amount=transaction.get('amount'),
                    currency=transaction.get('currency', 'USD'),
                    transaction_date=transaction.get('transaction_date'),
                    transaction_time=transaction.get('transaction_time'),
                    reference=transaction.get('reference'),
                    cvm_method=transaction.get('cvm_method'),
                    decision=transaction.get('decision'),
                    cryptogram=transaction.get('cryptogram'),
                    transaction_certificate=json.dumps(
                        transaction.get('transaction_certificate', {})
                    ),
                    tvr=transaction.get('tvr'),
                    timestamp=transaction.get('timestamp'),
                    status='PENDING'
                )
                
                # Encrypt sensitive data
                encrypted_data = self._encrypt_data(asdict(offline_tx))
                
                # Store in database
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO offline_transactions (
                            id, terminal_id, merchant_id, card_last_four,
                            amount, currency, transaction_date, transaction_time,
                            reference, cvm_method, decision, cryptogram,
                            transaction_certificate, tvr, timestamp, status,
                            encrypted_data
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        offline_tx.id, offline_tx.terminal_id, offline_tx.merchant_id,
                        offline_tx.card_last_four, offline_tx.amount, offline_tx.currency,
                        offline_tx.transaction_date, offline_tx.transaction_time,
                        offline_tx.reference, offline_tx.cvm_method, offline_tx.decision,
                        offline_tx.cryptogram, offline_tx.transaction_certificate,
                        offline_tx.tvr, offline_tx.timestamp, offline_tx.status,
                        encrypted_data
                    ))
                    conn.commit()
                
                logger.info(f"Transaction stored: {offline_tx.id}")
                return True
                
            except Exception as e:
                logger.error(f"Error storing transaction: {str(e)}")
                return False
    
    def retrieve_transaction(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt offline transaction"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        'SELECT encrypted_data FROM offline_transactions WHERE id = ?',
                        (transaction_id,)
                    )
                    row = cursor.fetchone()
                    
                    if not row:
                        return None
                    
                    encrypted_data = row[0]
                    decrypted_data = self._decrypt_data(encrypted_data)
                    
                    return decrypted_data
                    
            except Exception as e:
                logger.error(f"Error retrieving transaction: {str(e)}")
                return None
    
    def get_pending_transactions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get pending transactions for batch upload"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT id, encrypted_data FROM offline_transactions
                        WHERE status = 'PENDING'
                        ORDER BY created_at ASC
                        LIMIT ?
                    ''', (limit,))
                    
                    transactions = []
                    for row in cursor.fetchall():
                        tx_id, encrypted_data = row
                        decrypted = self._decrypt_data(encrypted_data)
                        transactions.append(decrypted)
                    
                    return transactions
                    
            except Exception as e:
                logger.error(f"Error retrieving pending transactions: {str(e)}")
                return []
    
    def update_transaction_status(self, transaction_id: str, 
                                 status: str, batch_id: str = None) -> bool:
        """Update transaction status after synchronization"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    if batch_id:
                        cursor.execute('''
                            UPDATE offline_transactions
                            SET status = ?, batch_id = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (status, batch_id, transaction_id))
                    else:
                        cursor.execute('''
                            UPDATE offline_transactions
                            SET status = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (status, transaction_id))
                    
                    conn.commit()
                    
                    logger.info(f"Transaction {transaction_id} status updated to {status}")
                    return True
                    
            except Exception as e:
                logger.error(f"Error updating transaction status: {str(e)}")
                return False
    
    def create_batch_upload(self, terminal_id: str, merchant_id: str,
                           transaction_ids: List[str]) -> str:
        """
        Create batch upload record
        
        Returns:
            Batch ID
        """
        with self.lock:
            import uuid
            batch_id = str(uuid.uuid4())
            
            try:
                # Calculate batch totals
                transactions = [
                    self.retrieve_transaction(tx_id) for tx_id in transaction_ids
                ]
                total_amount = sum(tx['amount'] for tx in transactions if tx)
                
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO batch_uploads (
                            id, terminal_id, merchant_id, batch_date,
                            transaction_count, total_amount, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        batch_id, terminal_id, merchant_id,
                        datetime.now().strftime('%Y%m%d'),
                        len(transaction_ids), total_amount, 'PENDING'
                    ))
                    
                    # Update transaction batch IDs
                    for tx_id in transaction_ids:
                        self.update_transaction_status(tx_id, 'PENDING', batch_id)
                    
                    conn.commit()
                
                logger.info(f"Batch created: {batch_id} with {len(transaction_ids)} transactions")
                return batch_id
                
            except Exception as e:
                logger.error(f"Error creating batch: {str(e)}")
                return None
    
    def update_batch_status(self, batch_id: str, status: str,
                           response_code: str = None,
                           response_message: str = None) -> bool:
        """Update batch upload status"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE batch_uploads
                        SET status = ?, response_code = ?, response_message = ?,
                            upload_timestamp = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (
                        status, response_code, response_message,
                        datetime.now().isoformat(), batch_id
                    ))
                    
                    if status == 'UPLOADED':
                        # Update all transactions in batch
                        cursor.execute('''
                            UPDATE offline_transactions
                            SET status = 'SYNCHRONIZED'
                            WHERE batch_id = ?
                        ''', (batch_id,))
                    
                    conn.commit()
                
                return True
                
            except Exception as e:
                logger.error(f"Error updating batch status: {str(e)}")
                return False
    
    def record_settlement(self, batch_id: str, settlement_date: str,
                         bank_reference: str = None) -> str:
        """Record settlement for batch"""
        with self.lock:
            import uuid
            settlement_id = str(uuid.uuid4())
            
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    # Get batch info
                    cursor.execute('''
                        SELECT transaction_count, total_amount FROM batch_uploads WHERE id = ?
                    ''', (batch_id,))
                    row = cursor.fetchone()
                    
                    if not row:
                        return None
                    
                    tx_count, total_amount = row
                    
                    # Create settlement record
                    cursor.execute('''
                        INSERT INTO settlements (
                            id, batch_id, settlement_date, amount,
                            transaction_count, status, bank_reference
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        settlement_id, batch_id, settlement_date,
                        total_amount, tx_count, 'PENDING', bank_reference
                    ))
                    
                    # Update transactions
                    cursor.execute('''
                        UPDATE offline_transactions
                        SET status = 'SETTLED', settlement_date = ?
                        WHERE batch_id = ?
                    ''', (settlement_date, batch_id))
                    
                    conn.commit()
                
                logger.info(f"Settlement recorded: {settlement_id}")
                return settlement_id
                
            except Exception as e:
                logger.error(f"Error recording settlement: {str(e)}")
                return None
    
    def record_reversal(self, transaction_id: str, reason: str = None,
                       reversal_amount: float = None) -> str:
        """Record transaction reversal"""
        with self.lock:
            import uuid
            reversal_id = str(uuid.uuid4())
            
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    # Get original transaction
                    cursor.execute(
                        'SELECT reference FROM offline_transactions WHERE id = ?',
                        (transaction_id,)
                    )
                    row = cursor.fetchone()
                    
                    if not row:
                        return None
                    
                    original_reference = row[0]
                    
                    # Create reversal record
                    cursor.execute('''
                        INSERT INTO reversals (
                            id, transaction_id, original_reference,
                            reversal_amount, reason, status
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        reversal_id, transaction_id, original_reference,
                        reversal_amount, reason, 'PENDING'
                    ))
                    
                    # Update original transaction
                    cursor.execute('''
                        UPDATE offline_transactions
                        SET reversal_reference = ?
                        WHERE id = ?
                    ''', (reversal_id, transaction_id))
                    
                    conn.commit()
                
                logger.info(f"Reversal recorded: {reversal_id}")
                return reversal_id
                
            except Exception as e:
                logger.error(f"Error recording reversal: {str(e)}")
                return None
    
    def get_reconciliation_status(self, batch_id: str) -> Dict[str, Any]:
        """Get reconciliation status for batch"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get batch info
                cursor.execute('''
                    SELECT id, transaction_count, total_amount, status
                    FROM batch_uploads WHERE id = ?
                ''', (batch_id,))
                batch_row = cursor.fetchone()
                
                if not batch_row:
                    return None
                
                batch_id, tx_count, total_amount, batch_status = batch_row
                
                # Get settlement info
                cursor.execute('''
                    SELECT id, settlement_date, status FROM settlements WHERE batch_id = ?
                ''', (batch_id,))
                settlement_row = cursor.fetchone()
                
                # Get transaction statuses
                cursor.execute('''
                    SELECT status, COUNT(*) FROM offline_transactions
                    WHERE batch_id = ?
                    GROUP BY status
                ''', (batch_id,))
                status_counts = dict(cursor.fetchall())
                
                return {
                    'batch_id': batch_id,
                    'batch_status': batch_status,
                    'transaction_count': tx_count,
                    'total_amount': total_amount,
                    'settlement_id': settlement_row[0] if settlement_row else None,
                    'settlement_date': settlement_row[1] if settlement_row else None,
                    'settlement_status': settlement_row[2] if settlement_row else None,
                    'transaction_statuses': status_counts
                }
                
        except Exception as e:
            logger.error(f"Error getting reconciliation status: {str(e)}")
            return None
    
    def _encrypt_data(self, data: Dict[str, Any]) -> bytes:
        """Encrypt transaction data"""
        try:
            # Convert to JSON
            json_data = json.dumps(data).encode()
            
            # Generate IV
            iv = get_random_bytes(16)
            
            # Create cipher
            cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv=iv)
            
            # Pad and encrypt
            padded_data = pad(json_data, AES.block_size)
            encrypted = cipher.encrypt(padded_data)
            
            # Return IV + encrypted data
            return iv + encrypted
            
        except Exception as e:
            logger.error(f"Encryption error: {str(e)}")
            raise
    
    def _decrypt_data(self, encrypted_data: bytes) -> Dict[str, Any]:
        """Decrypt transaction data"""
        try:
            # Extract IV (first 16 bytes)
            iv = encrypted_data[:16]
            encrypted_content = encrypted_data[16:]
            
            # Create cipher
            cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv=iv)
            
            # Decrypt and unpad
            decrypted = cipher.decrypt(encrypted_content)
            padded_json = unpad(decrypted, AES.block_size)
            
            # Parse JSON
            return json.loads(padded_json.decode())
            
        except Exception as e:
            logger.error(f"Decryption error: {str(e)}")
            raise


# ============ UTILITY FUNCTIONS ============

def create_storage(db_path: str = None,
                   encryption_key: bytes = None) -> OfflineTransactionStorage:
    """Factory function to create storage instance"""
    return OfflineTransactionStorage(db_path, encryption_key)
