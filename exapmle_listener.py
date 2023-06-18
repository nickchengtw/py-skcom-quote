import zmq

context = zmq.Context()
socket = context.socket(zmq.REP)

LISTEN_PORT = 38888
socket.bind("tcp://127.0.0.1:" + str(LISTEN_PORT))

while True:
    msg = socket.recv_pyobj()
    socket.send(b'')

    if msg['type'] == 'HIST':
        print(msg['symbol'], msg['timeframe'], len(msg['kline']))
    elif msg['type'] == 'LIVE':
        print(msg['symbol'], msg['timeframe'], msg['kbar'].to_json())
