import base64
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fief_client import FiefAccessTokenInfo
from pydantic import BaseModel, Field

from api.auth_api import auth
from core.logging_core import setup_logger
from handler.image_handler import (
    handle_generate_image,
)

logger = setup_logger(__name__)

router = APIRouter(
    prefix="/image",
    tags=["image"],
)

### tags_metadata -> resources/openapi_tags_metadata.py
router_metadata = {
    "name": "image",
    "description": "Image generation endpoints.",
}

class GenerateImageRequest(BaseModel):
    workflow_id: UUID = Field(
        ...,
        description="ID of the workflow to be used to generate the image.",
    )
    folder_id: UUID | None = Field(
        default=None,
        description="ID of the folder to save the image in. "
                    "If not provided, the image will not be saved.",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters to fill the workflow "
                    "(e.g.: {'positive_prompt': 'astronaut cat', 'seed': 123})",
    )


@router.post("/generate", description="Generate an image using a workflow. ")
async def generate(
    request_data: GenerateImageRequest,
    retrieve_image: bool = False,
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),  # noqa: B008
):
    user_id = access_token_info["id"]
    job_id = str(uuid4())
    folder_id = request_data.folder_id

    try:
        images_data = await handle_generate_image(
            user_id=user_id,
            folder_id=folder_id,
            job_id=job_id,
            workflow_id=request_data.workflow_id,
            params=request_data.parameters,
        )

        if images_data:
            if retrieve_image:
                image_bytes = images_data[0]["processed_image"]
                if isinstance(image_bytes, str):
                    image_bytes = base64.b64decode(image_bytes)
                return StreamingResponse(BytesIO(image_bytes), media_type="image/png")
            return images_data
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate image or workflow did not produce expected output.",
            ) from None
    except ValueError as err:
        logger.error(
            f"Value error while generating image for user {user_id} "
            f"with workflow {request_data.workflow_id}: {err}"
        )
        raise HTTPException(
            status_code=400,
            detail=str(err),
        ) from err
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow '{request_data.workflow_id}' not found.",
        ) from err
    except KeyError as err:
        raise HTTPException(
            status_code=400,
            detail=f"Required parameter '{err}' missing for workflow "
                   f"'{request_data.workflow_id}'.",
        ) from err
    except Exception as err:
        logger.error(
            f"Unexpected error while generating image for user {user_id} "
            f"with workflow {request_data.workflow_id}: {err}"
        )
        raise HTTPException(status_code=500, detail=str(err)) from err