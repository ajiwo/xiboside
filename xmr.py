from Crypto import Random
import zmq


class Subscriber:
    def __init__(self, url, channel, callback):
        self._url = url
        self._heartbeat = "H"
        self._channel = channel
        self._callback = callback
        self._context = zmq.Context()
        self._push = None
        self._stop_command = Random.new().read(16)

    def run(self):
        sub = self._context.socket(zmq.SUB)
        sub.connect(self._url)
        sub.setsockopt_string(zmq.SUBSCRIBE, self._heartbeat.decode('ascii'))
        sub.setsockopt_string(zmq.SUBSCRIBE, self._channel.decode('ascii'))

        push = self._context.socket(zmq.PUSH)
        port = push.bind_to_random_port('tcp://127.0.0.1')
        self._push = push

        pull = self._context.socket(zmq.PULL)
        pull.connect('tcp://127.0.0.1:%d' % port)

        poller = zmq.Poller()
        poller.register(pull, zmq.POLLIN)
        poller.register(sub, zmq.POLLIN)

        while True:
            socks = dict(poller.poll())
            if sub in socks and socks[sub] == zmq.POLLIN:
                message = sub.recv_multipart()
                if len(message) == 3 and message[0] in (self._heartbeat, self._channel):
                    if callable(self._callback):
                        self._callback(message[1:])
            if pull in socks and socks[pull] == zmq.POLLIN:
                control = pull.recv()
                if self._stop_command == control:
                    break

    def stop(self):
        self._push.send(self._stop_command)

