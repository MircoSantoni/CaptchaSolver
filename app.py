from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import asyncio
from dotenv import load_dotenv

from services.playwright_service import PlaywrightService
from services.alicuota_service import AlicuotaService
from controllers.alicuota_controller import router, setup_controller

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="CaptchaSolver API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

playwright_service = PlaywrightService()
alicuota_service = AlicuotaService(playwright_service)

setup_controller(playwright_service, alicuota_service)

app.include_router(router)

from fastapi.responses import HTMLResponse
from views import get_frontend_html

@app.get("/", response_class=HTMLResponse)
async def frontend():
    return HTMLResponse(content=get_frontend_html())


@app.on_event("startup")
async def startup_event():
    try:
        logger.info("=== INICIANDO APLICACIÓN ===")
        logger.info("Inicializando sesión del navegador en startup...")
        # Ejecutar en el mismo thread usando run_in_executor con None (thread pool por defecto)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, playwright_service.inicializar_sesion)
        logger.info("=== Sesión del navegador inicializada correctamente ===")
    except Exception as e:
        logger.error(f"Error crítico al inicializar sesión del navegador: {e}", exc_info=True)
        logger.warning("La aplicación continuará sin sesión inicializada. La sesión se creará en el primer request.")


@app.on_event("shutdown")
async def shutdown_event():
    try:
        logger.info("Cerrando sesión del navegador...")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, playwright_service.cerrar_sesion)
        logger.info("Sesión del navegador cerrada correctamente")
    except Exception as e:
        logger.error(f"Error al cerrar sesión del navegador: {e}", exc_info=True)


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
