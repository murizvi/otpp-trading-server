import socket
import argparse
import sys

parser = argparse.ArgumentParser()
parser.add_argument('-ip', '--server_address', default='127.0.0.1:8000', help='Address of server to connect to')
parser.add_argument('-p', '--price', help='Get price info as of time specified')
parser.add_argument('-s', '--signal', help='Get signal info as of time specified')
parser.add_argument('-a', '--add_ticker', help='Start tracking ticker specified')
parser.add_argument('-d', '--del_ticker', help='Stop tracking ticker specified')
parser.add_argument('-r', '--reset', help='Stop tracking ticker specified')
# Assume server address always specified and exactly one command given at a time
# Connection is not persisted, rather each command requires running the client

args = parser.parse_args()

HOST, PORT = args.server_address.split(':')

command = ''
if args.price:
    command = 'price,{}'.format(args.price)
elif args.signal:
    command = 'signal,{}'.format(args.signal)
elif args.del_ticker:
    command = 'delete,{}'.format(args.del_ticker)
elif args.add_ticker:
    command = 'add,{}'.format(args.add_ticker)
else:
    command = 'reset,'

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    try:
        print((HOST, int(PORT)))
        s.connect((HOST, int(PORT)))
    except ConnectionRefusedError:
        print('Unable to connect to server. Sending email alert...')
        # TODO: implement email alert
        sys.exit(1)
    s.sendall(command.encode())
    data = s.recv(1024)
print(repr(data))
if args.price or args.signal:
    result = dict(data)
    print(result)
else:
    print(repr(data))
