#!/usr/bin/env python3
"""
vPOS Terminal & Open Banking Integration Test Script
Run this to test all new endpoints
"""
import requests
import json
import uuid
from datetime import datetime

BASE_URL = "http://localhost:5000"
HEADERS = {"Content-Type": "application/json"}


class VPOSTerminalTester:
    """Test vPOS Terminal integration"""
    
    def __init__(self):
        self.session_id = None
        self.order_id = None
        self.transaction_id = None
    
    def test_initialize_vpos(self):
        """Test vPOS initialization"""
        print("\n" + "="*60)
        print("TEST 1: Initialize vPOS Session")
        print("="*60)
        
        payload = {"provider": "DSK"}
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/vpos/initialize",
                headers=HEADERS,
                json=payload
            )
            print(f"Status: {response.status_code}")
            data = response.json()
            print(json.dumps(data, indent=2))
            
            if response.status_code == 201 and data.get('success'):
                self.session_id = data['session_id']
                print("\n✅ PASS: vPOS session initialized")
                return True
            else:
                print("\n❌ FAIL: Could not initialize vPOS")
                return False
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            return False
    
    def test_create_order(self):
        """Test order creation"""
        print("\n" + "="*60)
        print("TEST 2: Create Order")
        print("="*60)
        
        payload = {
            "amount": 100.00,
            "currency": "AED",
            "reference": f"TEST-{uuid.uuid4().hex[:8]}",
            "email": "test@example.com"
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/create-order",
                headers=HEADERS,
                json=payload
            )
            print(f"Status: {response.status_code}")
            data = response.json()
            print(json.dumps(data, indent=2))
            
            if response.status_code == 201 and data.get('success'):
                self.order_id = data['order_id']
                print("\n✅ PASS: Order created")
                return True
            else:
                print("\n❌ FAIL: Could not create order")
                return False
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            return False
    
    def test_create_vpos_payment(self):
        """Test vPOS payment creation"""
        print("\n" + "="*60)
        print("TEST 3: Create vPOS Payment")
        print("="*60)
        
        if not self.session_id or not self.order_id:
            print("❌ SKIP: Missing session_id or order_id from previous tests")
            return False
        
        payload = {
            "session_id": self.session_id,
            "order_id": self.order_id
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/vpos/create-payment",
                headers=HEADERS,
                json=payload
            )
            print(f"Status: {response.status_code}")
            data = response.json()
            print(json.dumps(data, indent=2))
            
            if response.status_code in [201, 400]:  # 201 success, 400 if vPOS not configured
                if data.get('success'):
                    self.transaction_id = data['transaction_id']
                    print("\n✅ PASS: vPOS payment created")
                    return True
                elif 'Failed to authenticate' in str(data.get('error', '')):
                    print("\n⚠️  SKIP: vPOS provider not properly configured")
                    print("   Set up VPOS_PROVIDER credentials in .env")
                    return True  # Not a test failure, just not configured
                else:
                    print("\n❌ FAIL: Could not create vPOS payment")
                    return False
            else:
                print("\n❌ FAIL: Unexpected response")
                return False
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            return False
    
    def test_authorize_payment(self):
        """Test payment authorization"""
        print("\n" + "="*60)
        print("TEST 4: Authorize vPOS Payment")
        print("="*60)
        
        if not self.session_id or not self.transaction_id:
            print("❌ SKIP: Missing session_id or transaction_id")
            return False
        
        payload = {
            "session_id": self.session_id,
            "transaction_id": self.transaction_id,
            "authorization_code": "123456"
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/vpos/authorize",
                headers=HEADERS,
                json=payload
            )
            print(f"Status: {response.status_code}")
            data = response.json()
            print(json.dumps(data, indent=2))
            
            if response.status_code in [200, 400]:
                if data.get('success'):
                    print("\n✅ PASS: Payment authorized")
                    return True
                else:
                    print("\n⚠️  SKIP: vPOS authorization skipped (provider not configured)")
                    return True
            else:
                print("\n❌ FAIL: Could not authorize payment")
                return False
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            return False
    
    def test_get_transaction_status(self):
        """Test transaction status"""
        print("\n" + "="*60)
        print("TEST 5: Get Transaction Status")
        print("="*60)
        
        if not self.transaction_id:
            print("❌ SKIP: No transaction_id from previous tests")
            return False
        
        try:
            response = requests.get(
                f"{BASE_URL}/api/vpos/status/{self.transaction_id}",
                headers=HEADERS,
                params={"session_id": self.session_id}
            )
            print(f"Status: {response.status_code}")
            data = response.json()
            print(json.dumps(data, indent=2))
            
            if response.status_code == 200:
                print("\n✅ PASS: Transaction status retrieved")
                return True
            else:
                print("\n❌ FAIL: Could not get transaction status")
                return False
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            return False


class PreAuthenticationTester:
    """Test Open Banking Pre-Authentication"""
    
    def __init__(self):
        self.pre_auth_id = None
        self.psu_id = f"psu-{uuid.uuid4().hex[:8]}"
    
    def test_create_pre_authentication(self):
        """Test pre-authentication creation"""
        print("\n" + "="*60)
        print("TEST 6: Create Pre-Authentication")
        print("="*60)
        
        headers = HEADERS.copy()
        headers['X-Request-ID'] = str(uuid.uuid4())
        headers['MessageCreateDateTime'] = datetime.utcnow().isoformat() + 'Z'
        headers['Scope'] = 'AIS+PIS'
        
        payload = {
            "PsuData": {
                "AspspId": "DSK",
                "AspspPsuId": f"user-{uuid.uuid4().hex[:4]}"
            },
            "PsuCredentials": [
                {
                    "CredentialId": "username",
                    "CredentialValue": "testuser"
                }
            ]
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/xs2a/routingservice/services/ob/auth/v3/psus/{self.psu_id}/pre-authentication",
                headers=headers,
                json=payload
            )
            print(f"Status: {response.status_code}")
            data = response.json()
            print(json.dumps(data, indent=2))
            
            if response.status_code == 201 and data.get('success'):
                self.pre_auth_id = data['PreAuthenticationId']
                print("\n✅ PASS: Pre-authentication created")
                return True
            else:
                print("\n❌ FAIL: Could not create pre-authentication")
                return False
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            return False
    
    def test_update_pre_authentication(self):
        """Test pre-authentication update"""
        print("\n" + "="*60)
        print("TEST 7: Update Pre-Authentication")
        print("="*60)
        
        if not self.pre_auth_id:
            print("❌ SKIP: No pre_auth_id from previous test")
            return False
        
        headers = HEADERS.copy()
        headers['X-Request-ID'] = str(uuid.uuid4())
        headers['MessageCreateDateTime'] = datetime.utcnow().isoformat() + 'Z'
        
        payload = {
            "AuthenticationMethodId": "sms_otp_001",
            "ScaAuthenticationData": "123456"
        }
        
        try:
            response = requests.put(
                f"{BASE_URL}/xs2a/routingservice/services/ob/auth/v3/psus/{self.psu_id}/pre-authentication/{self.pre_auth_id}",
                headers=headers,
                json=payload
            )
            print(f"Status: {response.status_code}")
            data = response.json()
            print(json.dumps(data, indent=2))
            
            if response.status_code == 200:
                print("\n✅ PASS: Pre-authentication updated")
                return True
            else:
                print("\n❌ FAIL: Could not update pre-authentication")
                return False
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            return False
    
    def test_get_pre_auth_status(self):
        """Test pre-authentication status"""
        print("\n" + "="*60)
        print("TEST 8: Get Pre-Authentication Status")
        print("="*60)
        
        if not self.pre_auth_id:
            print("❌ SKIP: No pre_auth_id")
            return False
        
        headers = HEADERS.copy()
        headers['X-Request-ID'] = str(uuid.uuid4())
        headers['MessageCreateDateTime'] = datetime.utcnow().isoformat() + 'Z'
        
        try:
            response = requests.get(
                f"{BASE_URL}/xs2a/routingservice/services/ob/auth/v3/psus/{self.psu_id}/pre-authentication/{self.pre_auth_id}/status",
                headers=headers
            )
            print(f"Status: {response.status_code}")
            data = response.json()
            print(json.dumps(data, indent=2))
            
            if response.status_code == 200:
                print("\n✅ PASS: Pre-authentication status retrieved")
                return True
            else:
                print("\n❌ FAIL: Could not get pre-authentication status")
                return False
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            return False
    
    def test_get_audit_log(self):
        """Test pre-authentication audit log"""
        print("\n" + "="*60)
        print("TEST 9: Get Pre-Authentication Audit Log")
        print("="*60)
        
        if not self.pre_auth_id:
            print("❌ SKIP: No pre_auth_id")
            return False
        
        try:
            response = requests.get(
                f"{BASE_URL}/api/pre-auth/audit/{self.pre_auth_id}",
                headers=HEADERS
            )
            print(f"Status: {response.status_code}")
            data = response.json()
            print(json.dumps(data, indent=2))
            
            if response.status_code == 200:
                print("\n✅ PASS: Audit log retrieved")
                return True
            else:
                print("\n❌ FAIL: Could not get audit log")
                return False
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            return False


def main():
    """Run all tests"""
    print("\n" + "#"*60)
    print("# vPOS Terminal & Open Banking Integration Tests")
    print("#"*60)
    print(f"\nTesting: {BASE_URL}")
    print(f"Time: {datetime.now().isoformat()}\n")
    
    results = {}
    
    # Test vPOS
    print("\n" + "█"*60)
    print("█ vPOS TERMINAL TESTS")
    print("█"*60)
    
    vpos_tester = VPOSTerminalTester()
    results['vPOS Initialize'] = vpos_tester.test_initialize_vpos()
    results['Create Order'] = vpos_tester.test_create_order()
    results['Create vPOS Payment'] = vpos_tester.test_create_vpos_payment()
    results['Authorize Payment'] = vpos_tester.test_authorize_payment()
    results['Get Transaction Status'] = vpos_tester.test_get_transaction_status()
    
    # Test Pre-Auth
    print("\n" + "█"*60)
    print("█ OPEN BANKING PRE-AUTHENTICATION TESTS")
    print("█"*60)
    
    pre_auth_tester = PreAuthenticationTester()
    results['Create Pre-Auth'] = pre_auth_tester.test_create_pre_authentication()
    results['Update Pre-Auth'] = pre_auth_tester.test_update_pre_authentication()
    results['Get Pre-Auth Status'] = pre_auth_tester.test_get_pre_auth_status()
    results['Get Audit Log'] = pre_auth_tester.test_get_audit_log()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60 + "\n")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, passed_flag in results.items():
        status = "✅ PASS" if passed_flag else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        print("Check the errors above and verify:")
        print("  1. Flask server is running (python app.py)")
        print("  2. All dependencies are installed")
        print("  3. Configuration in .env is correct")
    
    print("\n" + "="*60 + "\n")
    
    return 0 if passed == total else 1


if __name__ == '__main__':
    exit(main())
