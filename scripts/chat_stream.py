"""Neutral buffered stream integration; no platform imports or identifiers."""
import chat_gates


class FinalStream:
    def __init__(self, sink, *, me, channel, state):
        self.sink, self.me, self.channel, self.state = sink, me, channel, state
        self.parts = []
        self.finished = False
        self.delivered = False

    def delta(self, text):
        if self.finished:
            raise RuntimeError('stream already finalized')
        self.parts.append(text)

    def finalize(self):
        if self.finished:
            return self.delivered
        self.finished = True
        text = ''.join(self.parts)
        decision = chat_gates.evaluate_outbound(text, me=self.me,
                            channel=self.channel, state=self.state)
        if decision.act not in (chat_gates.Act.SUPPRESS, chat_gates.Act.BLOCK):
            self.sink(decision.content if decision.content is not None else text)
            self.delivered = True
        return self.delivered
