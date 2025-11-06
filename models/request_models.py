from pydantic import BaseModel, Field
from typing import List


class CuitRequest(BaseModel):
    cuits: List[str] = Field(..., min_length=1, description="Lista de CUITs a consultar")

