from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class Timestamps(BaseModel):
    created_at: datetime
    updated_at: Optional[datetime] | None = None
