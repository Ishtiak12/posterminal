"""
Simple ISO-8583-like TCP listener (scaffold)

This module implements a minimal TCP server that accepts newline-terminated
messages. For simplicity the accepted payload can be either JSON or a
pipe-delimited key=value list (e.g. "PAN=411111...|AMOUNT=100.00|CURRENCY=USD\n").

On receiving a message it converts it to a JSON payload and POSTs to the
local Flask API (`/api/emv/process-offline-transaction`) so the rest of the
application can process the transaction without importing application
internals (avoids circular imports).

This is scaffold code — replace the parser with a proper ISO-8583 parser
for production (use `pyiso8583` or similar).
"""
import socketserver
import threading
import json
import logging
import requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def parse_message(msg: str) -> dict:
    msg = msg.strip()
    # Try JSON first
    try:
        return json.loads(msg)
    except Exception:
        pass

    # Fallback: pipe-delimited key=value pairs
    data = {}
    for part in msg.split('|'):
        if '=' in part:
            k, v = part.split('=', 1)
            data[k.strip().lower()] = v.strip()
    return data


class ISOHandler(socketserver.StreamRequestHandler):
    def handle(self):
        peer = self.client_address
        logger.info(f"Connection from {peer}")
        for line in self.rfile:
            try:
                raw = line.decode('utf-8')
            except Exception:
                raw = line
            if not raw:
                break
            payload = parse_message(raw)
            logger.info(f"Received payload: {payload}")

            # Map to the EMV endpoint expected fields (best-effort)
            emv_payload = {
                'pan': payload.get('pan') or payload.get('card_pan'),
                'track2': payload.get('track2', ''),
                'expiry': payload.get('expiry') or payload.get('exp', ''),
                'cvc': payload.get('cvc') or payload.get('cvv', ''),
                'cardholder_name': payload.get('cardholder_name') or payload.get('name', 'UNKNOWN'),
                'amount': float(payload.get('amount', payload.get('amt', 0))),
                'pin': payload.get('pin', '0000'),
                'icc_data': payload.get('icc_data', ''),
            }

            try:
                # Post to local Flask app; assumes app is running on port 5000
                resp = requests.post('http://127.0.0.1:5000/api/emv/process-offline-transaction', json=emv_payload, timeout=10)
                logger.info(f"Forwarded to app, response={resp.status_code}")
                self.wfile.write(f"OK {resp.status_code}\n".encode())
            except Exception as e:
                logger.error(f"Error forwarding to app: {e}")
                self.wfile.write(f"ERROR {str(e)}\n".encode())


def start_server(host: str = '0.0.0.0', port: int = 5001):
    server = socketserver.ThreadingTCPServer((host, port), ISOHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"ISO-8583 TCP scaffold running on {host}:{port}")
    return server


if __name__ == '__main__':
    start_server()
    # Keep main thread alive
    import time
    while True:
        time.sleep(1)
