"""
Configuration and initialization helper for vPOS Terminal
Run this once to validate and setup your environment
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()


class VPOSConfiguration:
    """Validate and manage vPOS configuration"""
    
    REQUIRED_KEYS = {
        'DSK': ['VPOS_PROVIDER', 'DSK_MERCHANT_ID', 'DSK_API_KEY', 'DSK_OUTLET_ID'],
        'FIBANK': ['VPOS_PROVIDER', 'FIBANK_MERCHANT_ID', 'FIBANK_API_KEY', 'FIBANK_OUTLET_ID'],
        'KBC': ['VPOS_PROVIDER', 'KBC_MERCHANT_ID', 'KBC_API_KEY', 'KBC_OUTLET_ID'],
        'PAYSERA': ['VPOS_PROVIDER', 'PAYSERA_PROJECT_ID', 'PAYSERA_MERCHANT_ID', 'PAYSERA_API_KEY']
    }
    
    PROVIDER_NAMES = ['DSK', 'FIBANK', 'KBC', 'PAYSERA']
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.valid = True
    
    def validate_environment(self) -> bool:
        """Validate environment variables"""
        print("\n" + "="*60)
        print("vPOS Terminal Configuration Validator")
        print("="*60 + "\n")
        
        # Check provider
        provider = os.getenv('VPOS_PROVIDER', 'DSK').upper()
        
        if provider not in self.PROVIDER_NAMES:
            self.errors.append(f"Unknown VPOS_PROVIDER: {provider}")
            self.errors.append(f"Must be one of: {', '.join(self.PROVIDER_NAMES)}")
            self.valid = False
            return False
        
        print(f"✓ Provider: {provider}\n")
        
        # Check required keys for this provider
        required = self.REQUIRED_KEYS.get(provider, [])
        
        for key in required:
            value = os.getenv(key)
            if not value or value.startswith('your_'):
                self.errors.append(f"Missing or invalid {key}")
                self.valid = False
            else:
                # Mask sensitive values
                display_value = value[:10] + '...' if len(value) > 10 else value
                print(f"  ✓ {key}: {display_value}")
        
        if self.valid:
            print(f"\n✓ All required configuration for {provider} is present")
        
        return self.valid
    
    def validate_pre_auth_config(self) -> bool:
        """Validate pre-authentication configuration"""
        print("\n" + "-"*60)
        print("Pre-Authentication Configuration")
        print("-"*60 + "\n")
        
        enabled = os.getenv('OPEN_BANKING_ENABLED', 'True').lower() == 'true'
        timeout = int(os.getenv('PRE_AUTH_SESSION_TIMEOUT', '86400'))
        sca_method = os.getenv('SCA_METHOD_DEFAULT', 'SMS_OTP')
        
        print(f"  ✓ Open Banking Enabled: {enabled}")
        print(f"  ✓ Session Timeout: {timeout} seconds ({timeout/3600:.1f} hours)")
        print(f"  ✓ Default SCA Method: {sca_method}")
        
        valid_methods = ['SMS_OTP', 'SMTP_OTP', 'PUSH_OTP']
        if sca_method not in valid_methods:
            self.warnings.append(f"SCA_METHOD_DEFAULT '{sca_method}' is non-standard")
        
        return True
    
    def test_imports(self) -> bool:
        """Test if required modules can be imported"""
        print("\n" + "-"*60)
        print("Module Import Test")
        print("-"*60 + "\n")
        
        try:
            from vpos_integrations import get_vpos_provider, PROVIDERS
            print("  ✓ vpos_integrations module loaded")
            print(f"    Available providers: {', '.join(PROVIDERS.keys())}")
        except ImportError as e:
            self.errors.append(f"Failed to import vpos_integrations: {str(e)}")
            self.valid = False
        
        try:
            from pre_auth import PreAuthenticationService, PreAuthenticationStatus
            print("  ✓ pre_auth module loaded")
            print(f"    Status options: {', '.join([s.value for s in PreAuthenticationStatus])}")
        except ImportError as e:
            self.errors.append(f"Failed to import pre_auth: {str(e)}")
            self.valid = False
        
        return self.valid
    
    def test_provider_instantiation(self) -> bool:
        """Test if providers can be instantiated"""
        print("\n" + "-"*60)
        print("Provider Instantiation Test")
        print("-"*60 + "\n")
        
        provider_name = os.getenv('VPOS_PROVIDER', 'DSK').upper()
        
        try:
            from vpos_integrations import get_vpos_provider
            
            provider = get_vpos_provider(
                provider_name=provider_name,
                merchant_id=os.getenv(f'{provider_name}_MERCHANT_ID'),
                api_key=os.getenv(f'{provider_name}_API_KEY'),
                outlet_id=os.getenv(f'{provider_name}_OUTLET_ID')
            )
            
            if provider:
                print(f"  ✓ {provider_name} provider instantiated successfully")
                print(f"    Class: {provider.__class__.__name__}")
            else:
                self.errors.append(f"Failed to instantiate {provider_name} provider")
                self.valid = False
        
        except Exception as e:
            self.errors.append(f"Provider instantiation error: {str(e)}")
            self.valid = False
        
        return self.valid
    
    def generate_report(self):
        """Generate validation report"""
        print("\n" + "="*60)
        print("VALIDATION REPORT")
        print("="*60 + "\n")
        
        if self.errors:
            print("❌ ERRORS:")
            for error in self.errors:
                print(f"  • {error}")
            print()
        
        if self.warnings:
            print("⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  • {warning}")
            print()
        
        if self.valid and not self.errors:
            print("✅ VALIDATION PASSED")
            print("\nYour vPOS Terminal is properly configured!")
            print("\nYou can now:")
            print("  1. Start the Flask app: python app.py")
            print("  2. Test vPOS endpoints")
            print("  3. Create pre-authentication sessions")
            print("\nSee QUICKSTART.md for example API calls")
        else:
            print("❌ VALIDATION FAILED")
            print("\nPlease fix the above errors before proceeding.")
            print("\nSteps:")
            print("  1. Review the errors above")
            print("  2. Update .env file with correct values")
            print("  3. Run this validator again")
        
        print("\n" + "="*60 + "\n")
        
        return self.valid


def print_configuration_template():
    """Print a configuration template"""
    print("\n" + "="*60)
    print("CONFIGURATION TEMPLATE")
    print("="*60 + "\n")
    
    provider = os.getenv('VPOS_PROVIDER', 'DSK').upper()
    
    if provider == 'DSK':
        template = """
# DSK Bank Configuration
VPOS_PROVIDER=DSK
DSK_MERCHANT_ID=your_dsk_merchant_id
DSK_API_KEY=your_dsk_api_key
DSK_OUTLET_ID=your_dsk_outlet_id
DSK_BASE_URL=https://api.dsk.bg/vpos
"""
    elif provider == 'FIBANK':
        template = """
# Fibank Configuration
VPOS_PROVIDER=FIBANK
FIBANK_MERCHANT_ID=your_fibank_merchant_id
FIBANK_API_KEY=your_fibank_api_key
FIBANK_OUTLET_ID=your_fibank_outlet_id
FIBANK_BASE_URL=https://api.fibank.bg/vpos
"""
    elif provider == 'KBC':
        template = """
# KBC Bank Configuration
VPOS_PROVIDER=KBC
KBC_MERCHANT_ID=your_kbc_merchant_id
KBC_API_KEY=your_kbc_api_key
KBC_OUTLET_ID=your_kbc_outlet_id
KBC_BASE_URL=https://api.kbc.bg/vpos
"""
    else:  # PAYSERA
        template = """
# Paysera Configuration
VPOS_PROVIDER=PAYSERA
PAYSERA_PROJECT_ID=your_project_id
PAYSERA_MERCHANT_ID=your_paysera_merchant_id
PAYSERA_API_KEY=your_paysera_api_key
PAYSERA_OUTLET_ID=your_paysera_outlet_id
PAYSERA_BASE_URL=https://www.paysera.com/api/v1
"""
    
    print(f"Update your .env file with the following for {provider}:")
    print(template)
    print("="*60 + "\n")


def main():
    """Run all validations"""
    config = VPOSConfiguration()
    
    # Run all tests
    config.validate_environment()
    config.validate_pre_auth_config()
    config.test_imports()
    config.test_provider_instantiation()
    
    # Generate report
    config.generate_report()
    
    # Show template if not configured
    if not config.valid:
        print_configuration_template()
    
    return 0 if config.valid else 1


if __name__ == '__main__':
    exit(main())
