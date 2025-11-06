from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from typing import List
import logging

from models import CuitRequest, CuitResponse
from views import get_frontend_html

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alicuotas", tags=["alicuotas"])

_playwright_service = None
_alicuota_service = None


def setup_controller(playwright_service, alicuota_service):
    global _playwright_service, _alicuota_service
    _playwright_service = playwright_service
    _alicuota_service = alicuota_service


@router.post("/async", response_model=List[CuitResponse])
async def obtener_alicuotas_async(request: CuitRequest):
    logger.info(f"Recibida solicitud ASYNC para consultar {len(request.cuits)} CUITs")
    
    try:
        respuestas = await _alicuota_service.obtener_alicuotas_async(request.cuits)
        return respuestas
    except Exception as e:
        logger.error(f"Error al procesar la solicitud async: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "Servicio de alícuotas funcionando correctamente"}


@router.get("/captcha-status")
async def captcha_status():
    return {
        "session_ready": _playwright_service.session_ready,
        "captcha_resuelto": _playwright_service.captcha_resuelto,
        "captcha_resolviendo": _playwright_service.captcha_resolviendo,
        "token_preview": _playwright_service.captcha_token if _playwright_service.captcha_token else None
    }



