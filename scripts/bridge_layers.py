"""Platform-neutral form of the four early bridge layers; simulated clocks."""
from collections import defaultdict
import re

LOOP_THRESHOLD = 3
LOOP_WINDOW_S = 60
LOOP_MUTE_S = 300
LOW_CONTENT = re.compile(r'^(?:\[?ack\]?|\.{2,}|ok|okay|thx|thanks?)$', re.I)
BOT_PREFIX = ('Be terse. Reply [ACK] only when there is nothing new. '
              'Do not reply to an incoming ack. End the discussion.')


def low_input(text):
    clean = re.sub(r'<@!?\d+>', '', text).strip()
    return not clean or bool(LOW_CONTENT.fullmatch(clean)) or bool(re.fullmatch(r'[\W_]+', clean))


def low_output(text):
    return len(text.strip()) < 5 or low_input(text)


class Bridge:
    def __init__(self):
        self.history = defaultdict(list)
        self.mute_until = {}

    def rate_allows(self, sender, channel, now):
        key = (sender, channel)
        if now < self.mute_until.get(key, 0):
            return False
        self.history[key] = [t for t in self.history[key] if t >= now - LOOP_WINDOW_S]
        self.history[key].append(now)
        if len(self.history[key]) >= LOOP_THRESHOLD:
            self.mute_until[key] = now + LOOP_MUTE_S
            return False
        return True

    def receive(self, text, *, sender, channel, now, is_bot, model):
        if low_input(text):
            return {'reaction': 'input filtered'}
        if is_bot and not self.rate_allows(sender, channel, now):
            return {'reaction': 'loop muted'}
        prompt = BOT_PREFIX + '\n' + text if is_bot else text
        reply = model(prompt)
        if low_output(reply):
            return {'reaction': 'done'}
        return {'text': reply}


if __name__ == '__main__':
    bridge = Bridge()
    # Synthetic uniform cadence derived from 0.6 messages/minute/sender.
    step = 60 / 0.6
    allowed = [bridge.rate_allows('111', 'fixture', i * step) for i in range(90)]
    assert all(allowed)
    print('uniform cadence at 0.6 messages/minute/sender: burst rule never fires')
