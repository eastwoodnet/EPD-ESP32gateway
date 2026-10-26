from typing import TypeVar

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


async def read_limited_body(request: Request, max_bytes: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="无效的 Content-Length") from exc
        if declared_length < 0:
            raise HTTPException(status_code=400, detail="无效的 Content-Length")
        if declared_length > max_bytes:
            raise HTTPException(status_code=413, detail="请求体过大")

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > max_bytes:
            raise HTTPException(status_code=413, detail="请求体过大")
        body.extend(chunk)
    return bytes(body)


async def parse_json_model(request: Request, model_type: type[ModelT], max_bytes: int) -> ModelT:
    body = await read_limited_body(request, max_bytes)
    try:
        return model_type.model_validate_json(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
