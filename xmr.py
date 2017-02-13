import zmq


class Subscriber:
    def __init__(self, url, channel, callback):
        self._url = url
        self._channel = channel
        self._callback = callback
        self._stop = False

    def run(self):
        with zmq.Context() as c:
            socket = c.socket(zmq.SUB)
            socket.connect(self._url)
            socket.setsockopt_string(zmq.SUBSCRIBE, self._channel.decode('ascii'))
            messages = []
            while not self._stop:
                message = socket.recv_string()
                if message == self._channel:
                    messages = [message]
                elif len(messages) > 0:
                    messages.append(message)
                if len(messages) == 3:
                    if callable(self._callback):
                        self._callback(messages[1:])

    def set_stop(self):
        self._stop = True

