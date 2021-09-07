import datetime
from typing import Optional

import pydantic

__all__ = ['Connection', 'Endpoint']


class Connection(pydantic.BaseModel):
    success: Optional[bool]
    endpoint: Optional[str]
    new: Optional[bool]


class Endpoint(pydantic.BaseModel):
    identity: str
    name: str 
    created_date: datetime.datetime
    key_source: str
    config: dict
    url: str

class Plan(pydantic.BaseModel):
    identity: str
    name: str 
    description: str
    api_stages: list