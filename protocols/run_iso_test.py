"""
Simple test client to send a sample ISO-like message to the TCP scaffold.
"""
import socket


def send_message(host='127.0.0.1', port=5001, message=None):
    message = message or 'PAN=4111111111111111|AMOUNT=25.50|CURRENCY=USD|EXPIRY=2512|CVC=123|CARDHOLDER_NAME=TEST USER\n'
    with socket.create_connection((host, port), timeout=5) as s:
        s.sendall(message.encode('utf-8'))
        resp = s.recv(1024)
        print('Response:', resp.decode())


if __name__ == '__main__':
    send_message()
