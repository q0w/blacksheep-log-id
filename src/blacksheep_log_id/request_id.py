from collections.abc import Awaitable
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from dataclasses import field
from logging import Filter
from logging import getLogger
from logging import LogRecord
from typing import Optional
from uuid import UUID
from uuid import uuid4

from blacksheep.messages import Request
from blacksheep.messages import Response

request_id: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
logger = getLogger('blacksheep_request_id')


class RequestIdFilter(Filter):
    def filter(self, record: LogRecord) -> bool:
        record.request_id = request_id.get()  # type: ignore[attr-defined]
        return True


def is_valid_uuid(uuid_: str) -> bool:
    try:
        return bool(UUID(uuid_, version=4))
    except ValueError:
        return False


@dataclass
class RequestIdMiddleware:
    header_name: bytes = b'X-Request-ID'
    generator: Callable[[], str] = field(default=lambda: uuid4().hex)
    validator: Callable[[str], bool] = field(default=is_valid_uuid)
    transformer: Callable[[str], str] = field(default=lambda a: a)

    async def __call__(
        self,
        request: Request,
        handler: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        header_value = request.get_first_header(self.header_name)
        if header_value:
            header_value = header_value.decode('utf-8')
        if not header_value:
            id_value: str = self.transformer(self.generator())
        elif self.validator and not self.validator(header_value):
            logger.warning(
                "Generating new ID, since header value '%s' is invalid",
                header_value,
            )
            id_value = self.transformer(self.generator())
        else:
            id_value = self.transformer(header_value)

        request_id.set(id_value.encode('utf-8'))  # type: ignore[arg-type]

        request.headers[self.header_name] = request_id.get()
        response = await handler(request)

        return response
