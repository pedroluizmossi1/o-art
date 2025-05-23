import hmac
import json
import time
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from core.db_core import get_db_session
from core.env_core import Envs, get_env_variable
from handler.user_handler import handle_user_webhook

user_webhook_secret = get_env_variable(Envs.FIEF_USER_WEBHOOK_SECRET)

router = APIRouter(
    prefix="/webhook",
    tags=["webhook"],
)

### tags_metadata -> resources/openapi_tags_metadata.py
router_metadata = {
    "name": "webhook",
    "description": "Webhook endpoints for external services.",
}


@router.post("/user")
async def user_webhook(request: Request, session: AsyncSession = Depends(get_db_session)):  # noqa: B008
    payload = await webhook_signature(request)
    return await handle_user_webhook(payload, session)


async def webhook_signature(request):
    timestamp = request.headers.get("X-Fief-Webhook-Timestamp")
    signature = request.headers.get("X-Fief-Webhook-Signature")
    payload = (await request.body()).decode("utf-8")
    # Check if timestamp and signature are there
    if timestamp is None or signature is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    # Check if timestamp is not older than 5 minutes
    if int(time.time()) - int(timestamp) > 5 * 60:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    # Compute signature
    message = f"{timestamp}.{payload}"
    hashed = hmac.new(
        user_webhook_secret.encode("utf-8"),
        msg=message.encode("utf-8"),
        digestmod=sha256,
    )
    computed_signature = hashed.hexdigest()
    # Check if the signatures match
    if not hmac.compare_digest(signature, computed_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    # Convert payload to dictionary
    return json.loads(payload)
