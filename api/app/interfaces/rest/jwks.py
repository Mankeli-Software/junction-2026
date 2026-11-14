"""`GET /.well-known/jwks.json`: the public key quotes are signed with (#40, vision §12).

Anyone may fetch it, from any origin, to check a quote's JWS with a standard JOSE library.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services import signing

router = APIRouter()


@router.get("/.well-known/jwks.json", include_in_schema=False)
async def jwks() -> JSONResponse:
    return JSONResponse(
        signing.jwks(),
        media_type="application/jwk-set+json",
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=300"},
    )
