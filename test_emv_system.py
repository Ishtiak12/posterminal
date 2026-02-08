"""
EMV System Integration Tests
Comprehensive tests for offline payment processing
"""

import unittest
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from emv_kernel import (
    create_emv_kernel, CardData, TransactionData, TransactionType,
    TerminalData, DecisionCode
)
from offline_storage import create_storage
from pin_verification import OfflinePINVerifier, PINVerificationFlow
from batch_processing import (
    BatchProcessor, SettlementProcessor, ReconciliationProcessor,
    ReversalProcessor
)
from receipt_generator import generate_receipt


class TestEMVKernel(unittest.TestCase):
    """Test EMV kernel functionality"""
    
    def setUp(self):
        """Initialize EMV kernel for testing"""
        self.kernel = create_emv_kernel({
            'terminal_id': 'TEST001',
            'merchant_id': 'TESTMERCH',
            'merchant_name': 'Test Store',
            'floor_limit': 500.0,
            'country_code': '840',
            'currency_code': '840'
        })
    
    def test_kernel_initialization(self):
        """Test kernel initializes correctly"""
        self.assertIsNotNone(self.kernel)
        self.assertEqual(self.kernel.terminal.terminal_id, 'TEST001')
        self.assertEqual(self.kernel.terminal.floor_limit, 500.0)
    
    def test_card_validation_valid_pan(self):
        """Test valid PAN validation"""
        valid_pan = '4111111111111111'  # Valid test Visa
        result = self.kernel._luhn_check(valid_pan)
        self.assertTrue(result)
    
    def test_card_validation_invalid_pan(self):
        """Test invalid PAN validation"""
        invalid_pan = '4111111111111112'
        result = self.kernel._luhn_check(invalid_pan)
        self.assertFalse(result)
    
    def test_expiry_validation_valid(self):
        """Test valid expiry date"""
        valid_expiry = '2512'  # Valid future date
        result = self.kernel._validate_expiry(valid_expiry)
        self.assertTrue(result)
    
    def test_expiry_validation_expired(self):
        """Test expired card"""
        expired_expiry = '2001'
        result = self.kernel._validate_expiry(expired_expiry)
        self.assertFalse(result)
    
    def test_offline_transaction_processing(self):
        """Test complete offline transaction"""
        card_data = CardData(
            pan='4111111111111111',
            track2='4111111111111111=2512123456789012',
            expiry='2512',
            cvc='123',
            cardholder_name='TEST USER',
            icc_data=b'test_icc_data',
            afl='08010102',
            aip='9800',
            cvm_list='01059F34020102',
            iac_default='0000000000',
            iac_denial='FFFFFFFFFF',
            iac_online='8000008000',
            iss_script_processing=False,
            pin_try_limit=3,
            iac_ddol='9F3704',
            iac_tdol='9F270101'
        )
        
        transaction_data = TransactionData(
            amount=100.0,
            amount_other=0.0,
            transaction_type=TransactionType.PURCHASE,
            transaction_currency_code='USD',
            transaction_currency_exponent=2,
            transaction_date='260208',
            transaction_time='100000',
            transaction_reference='TEST123456'
        )
        
        result = self.kernel.process_offline_transaction(
            card_data,
            transaction_data,
            pin='1234'
        )
        
        self.assertIsNotNone(result)
        self.assertIn('transaction_id', result)
        self.assertIn('status', result)
        self.assertIn('decision', result)
        self.assertTrue(result['status'] in ['APPROVED', 'REFERRAL', 'DECLINED', 'FAILED'])


class TestOfflineStorage(unittest.TestCase):
    """Test offline storage functionality"""
    
    def setUp(self):
        """Initialize storage for testing"""
        self.db_path = Path.home() / '.vpos' / 'test_offline.db'
        if self.db_path.exists():
            self.db_path.unlink()
        self.storage = create_storage(str(self.db_path))
    
    def tearDown(self):
        """Cleanup test database"""
        if self.db_path.exists():
            self.db_path.unlink()
    
    def test_storage_initialization(self):
        """Test storage initializes correctly"""
        self.assertIsNotNone(self.storage)
        self.assertTrue(self.db_path.exists())
    
    def test_store_and_retrieve_transaction(self):
        """Test storing and retrieving transaction"""
        transaction = {
            'transaction_id': 'TX001',
            'terminal_id': 'TERM001',
            'merchant_id': 'MERCH001',
            'card_last_four': '1111',
            'amount': 100.0,
            'currency': 'USD',
            'transaction_date': '260208',
            'transaction_time': '100000',
            'reference': 'REF001',
            'cvm_method': 'OFFLINE_PIN',
            'decision': 'APPROVED',
            'cryptogram': 'A1B2C3D4E5F6G7H8',
            'tvr': '0000000000000000',
            'timestamp': datetime.now().isoformat()
        }
        
        # Store
        stored = self.storage.store_transaction(transaction)
        self.assertTrue(stored)
        
        # Retrieve
        retrieved = self.storage.retrieve_transaction('TX001')
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved['transaction_id'], 'TX001')
        self.assertEqual(retrieved['amount'], 100.0)
    
    def test_get_pending_transactions(self):
        """Test retrieving pending transactions"""
        # Store multiple transactions
        for i in range(5):
            self.storage.store_transaction({
                'transaction_id': f'TX{i:03d}',
                'terminal_id': 'TERM001',
                'merchant_id': 'MERCH001',
                'card_last_four': '1111',
                'amount': 100.0 + i,
                'currency': 'USD',
                'transaction_date': '260208',
                'transaction_time': '100000',
                'reference': f'REF{i:03d}',
                'cvm_method': 'OFFLINE_PIN',
                'decision': 'APPROVED',
                'cryptogram': 'ABC123',
                'tvr': '0000000000000000',
                'timestamp': datetime.now().isoformat()
            })
        
        # Retrieve pending
        pending = self.storage.get_pending_transactions(limit=10)
        self.assertEqual(len(pending), 5)
    
    def test_batch_operations(self):
        """Test batch creation and management"""
        # Store transactions
        tx_ids = []
        for i in range(3):
            tx_id = f'TX{i:03d}'
            self.storage.store_transaction({
                'transaction_id': tx_id,
                'terminal_id': 'TERM001',
                'merchant_id': 'MERCH001',
                'card_last_four': '1111',
                'amount': 100.0,
                'currency': 'USD',
                'transaction_date': '260208',
                'transaction_time': '100000',
                'reference': f'REF{i:03d}',
                'cvm_method': 'OFFLINE_PIN',
                'decision': 'APPROVED',
                'cryptogram': 'ABC123',
                'tvr': '0000000000000000',
                'timestamp': datetime.now().isoformat()
            })
            tx_ids.append(tx_id)
        
        # Create batch
        batch_id = self.storage.create_batch_upload('TERM001', 'MERCH001', tx_ids)
        self.assertIsNotNone(batch_id)
        
        # Update batch status
        updated = self.storage.update_batch_status(batch_id, 'UPLOADED')
        self.assertTrue(updated)


class TestPINVerification(unittest.TestCase):
    """Test PIN verification"""
    
    def setUp(self):
        """Initialize PIN verifier"""
        self.verifier = OfflinePINVerifier()
        self.pan = '4111111111111111'
    
    def test_pin_block_creation(self):
        """Test PIN block creation"""
        pin = '1234'
        pin_block = self.verifier.create_pin_block(self.pan, pin)
        
        self.assertIsNotNone(pin_block)
        self.assertEqual(len(pin_block), 16)  # 16 bytes
    
    def test_pin_verification(self):
        """Test PIN verification"""
        pin = '1234'
        
        result = self.verifier.verify_offline_pin(
            self.pan,
            pin,
            stored_pin_block=None
        )
        
        self.assertIsNotNone(result)
        self.assertIn('valid', result)
        self.assertIn('status', result)


class TestBatchProcessing(unittest.TestCase):
    """Test batch processing"""
    
    def setUp(self):
        """Initialize batch processor"""
        self.db_path = Path.home() / '.vpos' / 'test_batch.db'
        if self.db_path.exists():
            self.db_path.unlink()
        self.storage = create_storage(str(self.db_path))
        self.batch_processor = BatchProcessor(self.storage)
    
    def tearDown(self):
        """Cleanup"""
        if self.db_path.exists():
            self.db_path.unlink()
    
    def test_batch_file_creation(self):
        """Test batch file creation"""
        # Store transaction
        tx_id = 'TX001'
        self.storage.store_transaction({
            'transaction_id': tx_id,
            'terminal_id': 'TERM001',
            'merchant_id': 'MERCH001',
            'card_last_four': '1111',
            'amount': 100.0,
            'currency': 'USD',
            'transaction_date': '260208',
            'transaction_time': '100000',
            'reference': 'REF001',
            'cvm_method': 'OFFLINE_PIN',
            'decision': 'APPROVED',
            'cryptogram': 'ABC123',
            'tvr': '0000000000000000',
            'timestamp': datetime.now().isoformat()
        })
        
        # Create batch
        batch = self.batch_processor.create_batch_file(
            'TERM001', 'MERCH001', [tx_id]
        )
        
        self.assertIsNotNone(batch)
        self.assertIn('batch_id', batch)
        self.assertIn('transaction_count', batch)
        self.assertEqual(batch['transaction_count'], 1)


class TestReceiptGeneration(unittest.TestCase):
    """Test receipt generation"""
    
    def test_receipt_generation(self):
        """Test receipt generation"""
        transaction = {
            'transaction_id': 'TX001',
            'terminal_id': 'TERM001',
            'merchant_id': 'MERCH001',
            'merchant_name': 'Test Store',
            'card_last_four': '1111',
            'amount': 100.0,
            'currency': 'USD',
            'transaction_date': '2026-02-08',
            'transaction_time': '10:00:00',
            'reference': 'REF001',
            'decision': 'APPROVED',
            'cvm_method': 'OFFLINE_PIN',
            'cryptogram': 'ABC123',
            'tvr': '0000000000000000'
        }
        
        receipt = generate_receipt(transaction)
        
        self.assertIsNotNone(receipt)
        self.assertIn('customer_receipt', receipt)
        self.assertIn('merchant_receipt', receipt)
        self.assertIn('html_receipt', receipt)
        
        # Check content
        self.assertIn('TEST STORE', receipt['customer_receipt'].upper())
        self.assertIn('APPROVED', receipt['customer_receipt'])


class TestIntegration(unittest.TestCase):
    """Integration tests for complete flow"""
    
    def setUp(self):
        """Initialize all components"""
        self.kernel = create_emv_kernel({
            'terminal_id': 'INT001',
            'merchant_id': 'INTMERCH',
            'merchant_name': 'Integration Test',
            'floor_limit': 500.0
        })
        
        self.db_path = Path.home() / '.vpos' / 'test_integration.db'
        if self.db_path.exists():
            self.db_path.unlink()
        
        self.storage = create_storage(str(self.db_path))
        self.pin_verifier = OfflinePINVerifier()
        self.batch_processor = BatchProcessor(self.storage)
    
    def tearDown(self):
        """Cleanup"""
        if self.db_path.exists():
            self.db_path.unlink()
    
    def test_complete_offline_flow(self):
        """Test complete offline transaction flow"""
        # 1. Create transaction
        card_data = CardData(
            pan='4111111111111111',
            track2='4111111111111111=2512123456789012',
            expiry='2512',
            cvc='123',
            cardholder_name='TEST USER',
            icc_data=b'test',
            afl='08010102',
            aip='9800',
            cvm_list='01059F34020102',
            iac_default='0000000000',
            iac_denial='FFFFFFFFFF',
            iac_online='8000008000',
            iss_script_processing=False,
            pin_try_limit=3,
            iac_ddol='9F3704',
            iac_tdol='9F270101'
        )
        
        transaction_data = TransactionData(
            amount=100.0,
            amount_other=0.0,
            transaction_type=TransactionType.PURCHASE,
            transaction_currency_code='USD',
            transaction_currency_exponent=2,
            transaction_date='260208',
            transaction_time='100000',
            transaction_reference='INT001'
        )
        
        # 2. Process transaction
        result = self.kernel.process_offline_transaction(
            card_data, transaction_data, pin='1234'
        )
        
        self.assertEqual(result['status'], 'APPROVED')
        
        # 3. Store transaction
        result['terminal_id'] = 'INT001'
        result['merchant_id'] = 'INTMERCH'
        result['currency'] = 'USD'
        
        stored = self.storage.store_transaction(result)
        self.assertTrue(stored)
        
        # 4. Verify storage
        retrieved = self.storage.retrieve_transaction(result['transaction_id'])
        self.assertIsNotNone(retrieved)
        
        # 5. Generate batch
        batch = self.batch_processor.create_batch_file(
            'INT001', 'INTMERCH', [result['transaction_id']]
        )
        
        self.assertIsNotNone(batch)
        
        # 6. Generate receipt
        result_with_tx_id = result.copy()
        result_with_tx_id['terminal_id'] = 'INT001'
        result_with_tx_id['merchant_name'] = 'Test'
        
        receipt = generate_receipt(result_with_tx_id)
        self.assertIsNotNone(receipt)
        self.assertIn('customer_receipt', receipt)


def run_tests():
    """Run all tests"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestEMVKernel))
    suite.addTests(loader.loadTestsFromTestCase(TestOfflineStorage))
    suite.addTests(loader.loadTestsFromTestCase(TestPINVerification))
    suite.addTests(loader.loadTestsFromTestCase(TestBatchProcessing))
    suite.addTests(loader.loadTestsFromTestCase(TestReceiptGeneration))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == '__main__':
    result = run_tests()
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)
    
    sys.exit(0 if result.wasSuccessful() else 1)
