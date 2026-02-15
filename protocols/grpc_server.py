"""
gRPC server scaffold for processing transactions via protobuf

This module expects generated Python modules from `protos/transaction.proto`:
  - protos/transaction_pb2.py
  - protos/transaction_pb2_grpc.py

Generate them with:

  python -m grpc_tools.protoc -I./protos --python_out=. --grpc_python_out=. protos/transaction.proto

The service implementation below forwards requests to the local Flask REST
endpoint (`/api/emv/process-offline-transaction`) so application logic is
reused.
"""
import logging
import requests
import grpc
from concurrent import futures

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

try:
    from protos import transaction_pb2, transaction_pb2_grpc
except Exception as e:
    transaction_pb2 = None
    transaction_pb2_grpc = None
    logger.warning("Generated gRPC modules not found. Run grpc_tools.protoc to generate them.")


class TransactionServicer(transaction_pb2_grpc.TransactionServiceServicer if transaction_pb2_grpc else object):
    def ProcessTransaction(self, request, context):
        # Map protobuf request to REST payload
        payload = {
            'pan': request.pan,
            'expiry': request.expiry,
            'cvc': request.cvc,
            'cardholder_name': request.cardholder_name,
            'amount': request.amount,
            'pin': request.pin
        }
        try:
            resp = requests.post('http://127.0.0.1:5000/api/emv/process-offline-transaction', json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return transaction_pb2.TransactionResponse(
                    success=True,
                    transaction_id=data.get('transaction', {}).get('transaction_id', request.transaction_id),
                    status=data.get('transaction', {}).get('status', 'UNKNOWN'),
                    message='Processed'
                )
            return transaction_pb2.TransactionResponse(success=False, transaction_id=request.transaction_id, status='ERROR', message=f'HTTP {resp.status_code}')
        except Exception as e:
            return transaction_pb2.TransactionResponse(success=False, transaction_id=request.transaction_id, status='ERROR', message=str(e))


def start_server(host: str = '0.0.0.0', port: int = 50051):
    if not transaction_pb2_grpc:
        logger.error('gRPC generated modules are missing. Generate them before running the gRPC server.')
        return None

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    transaction_pb2_grpc.add_TransactionServiceServicer_to_server(TransactionServicer(), server)
    server.add_insecure_port(f"{host}:{port}")
    server.start()
    logger.info(f"gRPC server started on {host}:{port}")
    return server


if __name__ == '__main__':
    start_server()
    import time
    while True:
        time.sleep(1)
