import logging
from typing import Optional

try:
    from twocaptcha import TwoCaptcha
except ImportError:
    TwoCaptcha = None

logger = logging.getLogger(__name__)


class TwoCaptchaService:
    def __init__(self, api_key: str, polling_interval: int = 3):
        if TwoCaptcha is None:
            raise ImportError("2captcha-python no está instalado. Ejecuta: pip install 2captcha-python")
        
        self.api_key = api_key
        self.solver = TwoCaptcha(
            api_key,
            pollingInterval=polling_interval,
            recaptchaTimeout=600
        )
    
    def solve_recaptcha_v2(self, page_url: str, site_key: str, timeout: int = 120) -> Optional[str]:
        try:
            logger.info(f"Intentando resolver reCAPTCHA v2 con 2Captcha")
            logger.info(f"  - URL: {page_url}")
            logger.info(f"  - Site Key: {site_key}")
            logger.info(f"  - Timeout: {timeout}s")
            
            result = self.solver.recaptcha(
                sitekey=site_key,
                url=page_url
            )
            
            logger.info(f"Respuesta recibida de 2Captcha: {type(result)}")
            logger.info(f"Contenido de la respuesta: {str(result)[:200]}...")
            
            token = None
            
            if result:
                if isinstance(result, dict):
                    if "code" in result:
                        token = result["code"]
                        logger.info("Token encontrado en result['code']")
                    elif "token" in result:
                        token = result["token"]
                        logger.info("Token encontrado en result['token']")
                    else:
                        for key, value in result.items():
                            if isinstance(value, str) and len(value) > 50:
                                token = value
                                logger.info(f"Token encontrado en result['{key}']")
                                break
                
                elif isinstance(result, str):
                    if len(result) > 50:
                        token = result
                        logger.info("Token recibido como string directo")
            
            if token and len(token) > 50:
                logger.info(f"reCAPTCHA v2 resuelto exitosamente con 2Captcha (token length: {len(token)})")
                logger.info(f"Token (primeros 50 caracteres): {token[:50]}...")
                return token
            else:
                logger.error(f"No se encontró código válido en la respuesta de 2Captcha. Result: {result}")
                return None
                
        except Exception as e:
            logger.error(f"Error al resolver reCAPTCHA v2 con 2Captcha: {e}", exc_info=True)
            return None
    
    def solve_hcaptcha(self, page_url: str, site_key: str, timeout: int = 120) -> Optional[str]:
        try:
            logger.info(f"Intentando resolver hCaptcha con 2Captcha para {page_url} con site_key: {site_key}")
            
            result = self.solver.hcaptcha(
                sitekey=site_key,
                url=page_url
            )
            
            if result and "code" in result:
                token = result["code"]
                logger.info("hCaptcha resuelto exitosamente con 2Captcha")
                return token
            else:
                logger.error("No se encontró código en la respuesta de 2Captcha")
                return None
                
        except Exception as e:
            logger.error(f"Error al resolver hCaptcha con 2Captcha: {e}", exc_info=True)
            return None

