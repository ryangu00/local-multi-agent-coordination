"""Optional HTTP middleware; the card endpoint remains public."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from token_store import load_or_create_token, PUBLIC_PATHS
import secrets

class BearerTokenMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        header = request.headers.get('authorization', '')
        scheme, _, value = header.partition(' ')
        if scheme.lower() != 'bearer' or not secrets.compare_digest(value, self._token):
            return JSONResponse({'error': {'code': -32001, 'message': 'Unauthorized'}}, status_code=401)
        return await call_next(request)
