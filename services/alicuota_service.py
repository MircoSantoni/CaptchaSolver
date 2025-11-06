import asyncio
from typing import List, Dict, Optional
import logging
from services.playwright_service import PlaywrightService

logger = logging.getLogger(__name__)


class AlicuotaService:
    def __init__(self, playwright_service: PlaywrightService):
        self.playwright_service = playwright_service
    
    async def obtener_alicuotas_async(self, cuits: List[str]) -> List[Dict[str, Optional[str]]]:
        """Obtiene las alícuotas de forma asíncrona ejecutando en el thread pool por defecto."""
        loop = asyncio.get_event_loop()
        # Usar None para usar el thread pool por defecto de asyncio
        resultados = await loop.run_in_executor(
            None,
            self.playwright_service.obtener_alicuotas,
            cuits
        )
        return resultados

