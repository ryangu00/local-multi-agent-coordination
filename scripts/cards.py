"""Generate official SDK cards from the neutral example registry on every read."""
import os
from pathlib import Path
import tomllib

REGISTRY = Path(os.environ.get('COORD_REGISTRY', 'configs/agents.example.toml'))


def _load_registry():
    with REGISTRY.open('rb') as stream:
        return tomllib.load(stream)


def build_card(name, spec):
    from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
    from a2a.utils import TransportProtocol
    return AgentCard(
        name=name, description=spec.get('description', ''), version='0.1.0',
        supported_interfaces=[AgentInterface(
            url=f"http://127.0.0.1:{spec['port']}/",
            protocol_binding=TransportProtocol.JSONRPC)],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=['text'], default_output_modes=['text'],
        skills=[AgentSkill(id=s, name=s, description=s, tags=[s])
                for s in spec.get('skills', [])])


def card_to_dict(card):
    from google.protobuf.json_format import MessageToDict
    return MessageToDict(card, preserving_proto_field_name=True)
