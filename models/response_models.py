from pydantic import BaseModel
from typing import Optional


class CuitResponse(BaseModel):
    cuit: str
    alicuota: Optional[str] = None
    nombre: Optional[str] = None
    error: Optional[str] = None

