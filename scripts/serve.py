"""Serve an official-SDK adapter on loopback. Stop file checked before SDK imports."""
import os
from pathlib import Path
import sys

if (Path(os.environ.get('COORD_STATE_DIR', './state')) / 'disabled').exists():
    print('hub disabled; exiting cleanly')
    raise SystemExit(0)


def build_app(name, spec):
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.routes import (add_a2a_routes_to_fastapi,
                                   create_agent_card_routes, create_jsonrpc_routes)
    from a2a.server.tasks import InMemoryTaskStore
    from a2a.utils import AGENT_CARD_WELL_KNOWN_PATH, DEFAULT_RPC_URL
    from fastapi import FastAPI
    from auth import BearerTokenMiddleware, load_or_create_token
    from cli_agent_executor import CliAgentExecutor
    import cards
    card = cards.build_card(name, spec)
    executor = CliAgentExecutor(name, spec['command'],
        timeout_s=spec.get('timeout_s', 600),
        max_concurrency=spec.get('max_concurrency', 6),
        env_unset=tuple(spec.get('env_unset', ())), env_set=spec.get('env_set'),
        cwd=spec.get('cwd', ''), drop_line_regex=spec.get('drop_line_regex', ''))
    handler = DefaultRequestHandler(agent_executor=executor,
        task_store=InMemoryTaskStore(), agent_card=card)
    app = FastAPI(title='local coordination')
    app.add_middleware(BearerTokenMiddleware, token=load_or_create_token())
    add_a2a_routes_to_fastapi(app,
        agent_card_routes=create_agent_card_routes(card, card_url=AGENT_CARD_WELL_KNOWN_PATH),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url=DEFAULT_RPC_URL))
    return app


if __name__ == '__main__':
    import cards
    import uvicorn
    name = sys.argv[1]
    spec = cards._load_registry()[name]
    uvicorn.run(build_app(name, spec), host='127.0.0.1', port=spec['port'])
