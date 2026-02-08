"""
Receipt Generation Module
Generates EMV transaction receipts for customer and merchant
"""

from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ReceiptGenerator:
    """
    Receipt generation for EMV transactions
    Supports both thermal printer and digital formats
    """
    
    def __init__(self, terminal_name: str = "EMV Terminal",
                 merchant_name: str = "Test Merchant",
                 terminal_id: str = "TERM001"):
        """
        Initialize receipt generator
        
        Args:
            terminal_name: Terminal device name
            merchant_name: Merchant name
            terminal_id: Terminal identifier
        """
        self.terminal_name = terminal_name
        self.merchant_name = merchant_name
        self.terminal_id = terminal_id
        self.paper_width = 40  # characters for 80mm thermal printer
    
    def generate_receipt(self, transaction_data: Dict[str, Any],
                        receipt_type: str = "BOTH") -> Dict[str, str]:
        """
        Generate receipt in multiple formats
        
        Args:
            transaction_data: Complete transaction details
            receipt_type: "MERCHANT", "CUSTOMER", or "BOTH"
            
        Returns:
            Dictionary with receipt text and HTML
        """
        try:
            # Generate customer receipt
            customer_receipt = self._generate_customer_receipt(transaction_data)
            
            # Generate merchant receipt
            merchant_receipt = self._generate_merchant_receipt(transaction_data)
            
            # Generate HTML format
            html_receipt = self._generate_html_receipt(transaction_data)
            
            result = {
                'customer_receipt': customer_receipt,
                'merchant_receipt': merchant_receipt,
                'html_receipt': html_receipt,
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"Receipt generated for transaction {transaction_data.get('transaction_id')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Receipt generation error: {str(e)}")
            return {
                'error': str(e),
                'customer_receipt': 'Error generating receipt',
                'merchant_receipt': 'Error generating receipt'
            }
    
    def _generate_customer_receipt(self, tx: Dict[str, Any]) -> str:
        """Generate customer copy of receipt"""
        receipt_lines = []
        
        # Header
        receipt_lines.append(self._center("CUSTOMER COPY"))
        receipt_lines.append(self._center("=" * 38))
        receipt_lines.append("")
        
        # Merchant info
        receipt_lines.append(self._center(self.merchant_name))
        receipt_lines.append(self._center(f"Terminal: {self.terminal_id}"))
        receipt_lines.append("")
        
        # Transaction status
        status = tx.get('decision', 'UNKNOWN').upper()
        if status == 'APPROVED':
            status_text = "✓ TRANSACTION APPROVED"
        elif status == 'DECLINED':
            status_text = "✗ TRANSACTION DECLINED"
        else:
            status_text = f"! {status}"
        
        receipt_lines.append(self._center(status_text))
        receipt_lines.append("")
        receipt_lines.append(self._center("=" * 38))
        
        # Transaction details
        receipt_lines.append("Transaction Details:")
        receipt_lines.append(self._line("Date/Time", 
                                       f"{tx.get('transaction_date')} {tx.get('transaction_time')}"))
        receipt_lines.append(self._line("Reference",
                                       tx.get('reference', 'N/A')))
        receipt_lines.append("")
        
        # Card information
        receipt_lines.append("Card Information:")
        card_last_four = tx.get('card_last_four', '****')
        receipt_lines.append(self._line("Card Number",
                                       f"**** **** **** {card_last_four}"))
        receipt_lines.append(self._line("CVM Method",
                                       self._format_cvm(tx.get('cvm_method', 'UNKNOWN'))))
        receipt_lines.append("")
        
        # Amount
        receipt_lines.append(self._center("=" * 38))
        amount = tx.get('amount', 0)
        currency = tx.get('currency', 'USD')
        receipt_lines.append(self._line("Amount",
                                       f"{currency} {amount:,.2f}"))
        receipt_lines.append(self._center("=" * 38))
        receipt_lines.append("")
        
        # EMV details
        receipt_lines.append("EMV Details:")
        receipt_lines.append(self._line("AID", "A0000000031010"))  # Visa AID
        receipt_lines.append(self._line("TVR", tx.get('tvr', 'N/A')[:8]))
        receipt_lines.append(self._line("Cryptogram", tx.get('cryptogram', 'N/A')[:16]))
        receipt_lines.append("")
        
        # Footer
        receipt_lines.append(self._center("Please retain for your records"))
        receipt_lines.append(self._center("No signature required - Offline PIN verified"))
        receipt_lines.append("")
        receipt_lines.append(self._center("=" * 38))
        receipt_lines.append(self._center("Thank you!"))
        receipt_lines.append("")
        
        return "\n".join(receipt_lines)
    
    def _generate_merchant_receipt(self, tx: Dict[str, Any]) -> str:
        """Generate merchant copy of receipt"""
        receipt_lines = []
        
        # Header
        receipt_lines.append(self._center("MERCHANT COPY"))
        receipt_lines.append(self._center("=" * 38))
        receipt_lines.append("")
        
        # Merchant info
        receipt_lines.append(self._center(self.merchant_name))
        receipt_lines.append(self._center(f"Terminal: {self.terminal_id}"))
        receipt_lines.append(self._center(f"Merchant ID: {tx.get('merchant_id', 'N/A')}"))
        receipt_lines.append("")
        
        # Transaction status
        status = tx.get('decision', 'UNKNOWN').upper()
        if status == 'APPROVED':
            status_text = "✓ TRANSACTION APPROVED"
        elif status == 'DECLINED':
            status_text = "✗ TRANSACTION DECLINED"
        else:
            status_text = f"! {status}"
        
        receipt_lines.append(self._center(status_text))
        receipt_lines.append("")
        receipt_lines.append(self._center("=" * 38))
        
        # Complete transaction details
        receipt_lines.append("Transaction Details:")
        receipt_lines.append(self._line("Transaction ID",
                                       tx.get('transaction_id', 'N/A')[:20]))
        receipt_lines.append(self._line("Date/Time",
                                       f"{tx.get('transaction_date')} {tx.get('transaction_time')}"))
        receipt_lines.append(self._line("Reference",
                                       tx.get('reference', 'N/A')))
        receipt_lines.append("")
        
        # Card information
        receipt_lines.append("Card Information:")
        card_last_four = tx.get('card_last_four', '****')
        receipt_lines.append(self._line("Card Number",
                                       f"**** **** **** {card_last_four}"))
        receipt_lines.append(self._line("CVM Method",
                                       self._format_cvm(tx.get('cvm_method', 'UNKNOWN'))))
        receipt_lines.append("")
        
        # Amount
        receipt_lines.append(self._center("=" * 38))
        amount = tx.get('amount', 0)
        currency = tx.get('currency', 'USD')
        receipt_lines.append(self._line("Amount",
                                       f"{currency} {amount:,.2f}"))
        receipt_lines.append(self._center("=" * 38))
        receipt_lines.append("")
        
        # EMV details - Full
        receipt_lines.append("EMV Details:")
        receipt_lines.append(self._line("AID", "A0000000031010"))
        receipt_lines.append(self._line("TVR", tx.get('tvr', 'N/A')))
        receipt_lines.append(self._line("Cryptogram", tx.get('cryptogram', 'N/A')))
        receipt_lines.append(self._line("Decision", tx.get('decision', 'N/A')))
        
        # Transaction Certificate (if approved)
        tc = tx.get('transaction_certificate', {})
        if tc and tx.get('decision') == 'APPROVED':
            receipt_lines.append("")
            receipt_lines.append("Transaction Certificate:")
            if isinstance(tc, dict):
                receipt_lines.append(self._line("TC ID", tc.get('reference', 'N/A')[:16]))
                receipt_lines.append(self._line("TC Signature",
                                               tc.get('signature', 'N/A')[:20]))
        
        receipt_lines.append("")
        receipt_lines.append(self._center("Offline Transaction"))
        receipt_lines.append(self._center("Will be synchronized when online"))
        receipt_lines.append("")
        receipt_lines.append(self._center("=" * 38))
        
        return "\n".join(receipt_lines)
    
    def _generate_html_receipt(self, tx: Dict[str, Any]) -> str:
        """Generate HTML format receipt"""
        status = tx.get('decision', 'UNKNOWN').upper()
        
        if status == 'APPROVED':
            status_color = '#00aa00'
            status_icon = '✓'
        elif status == 'DECLINED':
            status_color = '#aa0000'
            status_icon = '✗'
        else:
            status_color = '#aaaa00'
            status_icon = '!'
        
        amount = tx.get('amount', 0)
        currency = tx.get('currency', 'USD')
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>EMV Transaction Receipt</title>
    <style>
        body {{
            font-family: 'Courier New', monospace;
            background-color: #f5f5f5;
            padding: 20px;
        }}
        .receipt {{
            background-color: white;
            width: 80mm;
            max-width: 500px;
            margin: 0 auto;
            padding: 20px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
            border-radius: 5px;
        }}
        .header {{
            text-align: center;
            border-bottom: 1px solid #000;
            padding-bottom: 10px;
            margin-bottom: 10px;
        }}
        .status {{
            text-align: center;
            font-size: 18px;
            font-weight: bold;
            color: {status_color};
            margin: 10px 0;
        }}
        .section {{
            margin: 15px 0;
            padding-bottom: 10px;
            border-bottom: 1px solid #ddd;
        }}
        .section-title {{
            font-weight: bold;
            margin-bottom: 8px;
        }}
        .line {{
            display: flex;
            justify-content: space-between;
            margin: 5px 0;
            font-size: 12px;
        }}
        .label {{
            text-align: left;
        }}
        .value {{
            text-align: right;
        }}
        .amount {{
            text-align: center;
            font-size: 20px;
            font-weight: bold;
            margin: 10px 0;
        }}
        .footer {{
            text-align: center;
            font-size: 11px;
            margin-top: 20px;
            color: #666;
        }}
        .divider {{
            border-bottom: 1px solid #000;
            margin: 10px 0;
        }}
    </style>
</head>
<body>
    <div class="receipt">
        <div class="header">
            <div>{self.merchant_name}</div>
            <div>Terminal: {self.terminal_id}</div>
        </div>
        
        <div class="status">{status_icon} {status}</div>
        
        <div class="section">
            <div class="section-title">Transaction Details</div>
            <div class="line">
                <span class="label">Date/Time:</span>
                <span class="value">{tx.get('transaction_date')} {tx.get('transaction_time')}</span>
            </div>
            <div class="line">
                <span class="label">Reference:</span>
                <span class="value">{tx.get('reference', 'N/A')}</span>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">Card Information</div>
            <div class="line">
                <span class="label">Card:</span>
                <span class="value">**** **** **** {tx.get('card_last_four', '****')}</span>
            </div>
            <div class="line">
                <span class="label">CVM:</span>
                <span class="value">{self._format_cvm(tx.get('cvm_method', 'UNKNOWN'))}</span>
            </div>
        </div>
        
        <div class="divider"></div>
        
        <div class="amount">{currency} {amount:,.2f}</div>
        
        <div class="divider"></div>
        
        <div class="section">
            <div class="section-title">EMV Details</div>
            <div class="line">
                <span class="label">AID:</span>
                <span class="value">A0000000031010</span>
            </div>
            <div class="line">
                <span class="label">TVR:</span>
                <span class="value">{tx.get('tvr', 'N/A')[:8]}</span>
            </div>
            <div class="line">
                <span class="label">Cryptogram:</span>
                <span class="value">{tx.get('cryptogram', 'N/A')[:16]}</span>
            </div>
        </div>
        
        <div class="footer">
            <p>No signature required - Offline PIN verified</p>
            <p>Offline Transaction - Will sync when online</p>
            <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>
"""
        
        return html
    
    @staticmethod
    def _center(text: str, width: int = 40) -> str:
        """Center text within specified width"""
        padding = max(0, (width - len(text)) // 2)
        return " " * padding + text
    
    @staticmethod
    def _line(label: str, value: str, width: int = 40) -> str:
        """Format label-value line with proper spacing"""
        label = label[:20]
        value = str(value)[-16:]
        space = width - len(label) - len(value)
        return label + " " * space + value
    
    @staticmethod
    def _format_cvm(cvm: str) -> str:
        """Format CVM method for display"""
        cvm_map = {
            'PLAINTEXT_PIN': 'PIN (Offline)',
            'ENCRYPTED_PIN': 'PIN (Encrypted)',
            'SIGNATURE': 'Signature',
            'NO_VERIFICATION': 'No CVM',
            'OFFLINE_PIN': 'PIN (Offline)',
            '01': 'PIN (Plaintext)',
            '02': 'PIN (Encrypted)',
            '1E': 'Signature',
            '1F': 'No Verification'
        }
        return cvm_map.get(cvm, cvm)


def generate_receipt(transaction_data: Dict[str, Any],
                     receipt_type: str = "BOTH") -> Dict[str, str]:
    """
    Convenience function to generate receipt
    
    Args:
        transaction_data: Transaction details
        receipt_type: Receipt type ("MERCHANT", "CUSTOMER", or "BOTH")
        
    Returns:
        Receipt dictionary with text and HTML formats
    """
    generator = ReceiptGenerator(
        terminal_name=transaction_data.get('terminal_name', 'EMV Terminal'),
        merchant_name=transaction_data.get('merchant_name', 'Test Merchant'),
        terminal_id=transaction_data.get('terminal_id', 'TERM001')
    )
    
    return generator.generate_receipt(transaction_data, receipt_type)
