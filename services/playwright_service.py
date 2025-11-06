import os
import random
import time
import re
from typing import List, Optional, Dict
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, expect
import logging

# Intentar importar playwright_stealth (versión < 2.0.0 usa stealth_sync como función)
STEALTH_AVAILABLE = False
stealth_sync_func = None

try:
    # Para playwright-stealth < 2.0.0: stealth_sync es una función
    from playwright_stealth import stealth_sync as stealth_sync_func
    STEALTH_AVAILABLE = True
except ImportError:
    try:
        # Alternativa: desde el submódulo
        from playwright_stealth.stealth import stealth_sync as stealth_sync_func
        STEALTH_AVAILABLE = True
    except (ImportError, AttributeError):
        try:
            # Intentar importar el módulo completo
            import playwright_stealth
            if hasattr(playwright_stealth, 'stealth_sync'):
                stealth_sync_func = playwright_stealth.stealth_sync
                STEALTH_AVAILABLE = True
        except (ImportError, AttributeError):
            logging.warning("playwright_stealth no disponible, continuando sin stealth")

from services.twocaptcha_service import TwoCaptchaService

class Timer:
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        elapsed = self.end_time - self.start_time
        logger.info(f"⏱️  [{self.operation_name}] Tiempo: {elapsed:.2f}s")

load_dotenv()
logger = logging.getLogger(__name__)


class PlaywrightService:
    # Constantes
    LOGIN_URL = "https://arca.gob.ar/landing/default.asp"
    ALICUOTAS_URL = "https://eservicios.srt.gob.ar/Consultas/Alicuotas/Default.aspx"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    
    # Selectores
    SELECTOR_CUIT_FIELD = "#txtCuilCuit"
    SELECTOR_RESULT_IFRAME = "#ifrmResultadoPorCuit"
    SELECTOR_ALICUOTA_LABEL = "#lblAlicuota"
    SELECTOR_SERVICIOS_BUTTON = "[id=\"\\31 1\"]"
    
    # Timeouts (en segundos)
    TIMEOUT_PAGE_LOAD = 30000
    TIMEOUT_FIELD_WAIT = 15000
    TIMEOUT_FRAME_WAIT = 20000
    TIMEOUT_EXTRACTION = 5.0
    TIMEOUT_LOGIN = 60000  # Timeout para el proceso completo de login
    
    # Delays (en segundos)
    DELAY_SHORT = 0.1
    DELAY_MEDIUM = 0.3
    DELAY_LONG = 0.5
    
    def __init__(self):
        self.username = os.getenv("PLAYWRIGHT_USERNAME")
        if not self.username:
            raise ValueError("PLAYWRIGHT_USERNAME no está configurado")
        
        self.password = os.getenv("PLAYWRIGHT_PASSWORD")
        if not self.password:
            raise ValueError("PLAYWRIGHT_PASSWORD no está configurado")
        
        headless_env = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower()
        self.headless = headless_env == "true"
        
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.login_page = None
        self.servicios_page = None
        self.session_ready = False
        self.captcha_resuelto = False
        self.captcha_token = None
        self.captcha_resolviendo = False
        
        self._inicializar_twocaptcha()
    
    def _inicializar_twocaptcha(self):
        """Inicializa el servicio 2Captcha si está configurado."""
        twocaptcha_api_key = os.getenv("TWOCAPTCHA_API_KEY")
        self.twocaptcha_service = None
        
        if twocaptcha_api_key:
            try:
                logger.info("Inicializando servicio 2Captcha...")
                self.twocaptcha_service = TwoCaptchaService(twocaptcha_api_key)
                logger.info("2Captcha configurado correctamente")
            except ImportError as e:
                logger.error(f"Error de importación al inicializar 2Captcha: {e}")
                logger.error("Asegúrate de tener instalado: pip install 2captcha-python")
            except Exception as e:
                logger.error(f"No se pudo inicializar 2Captcha: {e}", exc_info=True)
        else:
            logger.warning("API key de 2Captcha no configurada. El servicio funcionará sin resolver captchas automáticamente.")
    
    def _get_context_options(self) -> Dict:
        """Retorna las opciones de contexto del navegador con anti-detección."""
        return {
            "ignore_https_errors": True,
            "user_agent": self.USER_AGENT,
            "viewport": {"width": 1920, "height": 1080},
            "locale": "es-AR",
            "timezone_id": "America/Argentina/Buenos_Aires",
            # Anti-detección: propiedades adicionales
            "permissions": ["geolocation"],
            "geolocation": {"latitude": -34.6037, "longitude": -58.3816},  # Buenos Aires
            "color_scheme": "light",
            "reduced_motion": "no-preference",
            "forced_colors": "none",
            # Headers adicionales para parecer más real
            "extra_http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0"
            }
        }
    
    def _apply_stealth(self, context: BrowserContext):
        """Aplica configuración stealth al contexto."""
        if STEALTH_AVAILABLE and stealth_sync_func:
            try:
                stealth_sync_func(context)
                logger.info("Stealth aplicado correctamente")
            except Exception as e:
                logger.warning(f"No se pudo aplicar stealth: {e}")
        
        # Aplicar scripts adicionales anti-detección mejorados
        try:
            context.add_init_script("""
                // Ocultar webdriver completamente
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Eliminar rastros de webdriver
                delete navigator.__proto__.webdriver;
                
                // Modificar plugins para parecer real
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        const plugins = [];
                        for (let i = 0; i < 5; i++) {
                            plugins.push({
                                name: `Plugin ${i}`,
                                description: `Plugin ${i} Description`,
                                filename: `plugin${i}.dll`,
                                length: 1
                            });
                        }
                        return plugins;
                    }
                });
                
                // Modificar languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['es-AR', 'es', 'en-US', 'en']
                });
                
                // Modificar permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Chrome runtime completo
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
                
                // Ocultar automation
                Object.defineProperty(navigator, 'automation', {
                    get: () => undefined
                });
                
                // Modificar platform
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Win32'
                });
                
                // Modificar hardwareConcurrency
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8
                });
                
                // Modificar deviceMemory
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: () => 8
                });
                
                // Modificar connection
                Object.defineProperty(navigator, 'connection', {
                    get: () => ({
                        effectiveType: '4g',
                        rtt: 50,
                        downlink: 10,
                        saveData: false
                    })
                });
            """)
        except Exception as e:
            logger.debug(f"Error aplicando scripts anti-detección: {e}")
    
    def _realizar_login(self, page: Page) -> Page:
        """Realiza el proceso de login y retorna la página de servicios."""
        try:
            logger.info(f"Accediendo a {self.LOGIN_URL}...")
            page.goto(self.LOGIN_URL, wait_until="networkidle", timeout=self.TIMEOUT_PAGE_LOAD)
            logger.info("Página de login cargada")
            
            logger.info("Buscando enlace 'Iniciar sesión'...")
            login_link = page.get_by_role("link", name="Iniciar sesión")
            
            # Esperar a que el enlace esté listo
            login_link.wait_for(state="visible", timeout=self.TIMEOUT_FIELD_WAIT)
            time.sleep(self.DELAY_SHORT)  # Pequeño delay antes de hacer click
            
            # Intentar click normal, si falla usar JavaScript
            try:
                with page.expect_popup(timeout=self.TIMEOUT_PAGE_LOAD) as popup_info:
                    login_link.click(timeout=self.TIMEOUT_FIELD_WAIT)
                login_page = popup_info.value
            except Exception as e:
                logger.warning(f"Click normal falló, intentando con JavaScript: {e}")
                # Usar JavaScript como alternativa
                login_link.evaluate("element => element.click()")
                time.sleep(1)
                # Esperar a que aparezca el popup
                pages = page.context.pages
                if len(pages) > 1:
                    login_page = pages[-1]  # La última página es el popup
                else:
                    # Esperar un poco más y buscar el popup
                    time.sleep(2)
                    pages = page.context.pages
                    if len(pages) > 1:
                        login_page = pages[-1]
                    else:
                        raise Exception("No se pudo abrir el popup de login")
            logger.info("Popup de login abierto")
            
            logger.info("Ingresando usuario...")
            login_page.get_by_role("spinbutton").fill(self.username, timeout=self.TIMEOUT_FIELD_WAIT)
            login_page.get_by_role("spinbutton").click(timeout=self.TIMEOUT_FIELD_WAIT)
            login_page.get_by_role("button", name="Siguiente").click(timeout=self.TIMEOUT_FIELD_WAIT)
            time.sleep(self.DELAY_LONG)
            logger.info("Usuario ingresado, esperando campo de contraseña...")
            
            logger.info("Ingresando contraseña...")
            login_page.get_by_label("TU CLAVE").click(timeout=self.TIMEOUT_FIELD_WAIT)
            login_page.get_by_label("TU CLAVE").fill(self.password, timeout=self.TIMEOUT_FIELD_WAIT)
            login_page.get_by_role("button", name="Ingresar").click(timeout=self.TIMEOUT_FIELD_WAIT)
            logger.info("Contraseña ingresada, esperando respuesta del servidor...")
            
            # Esperar más tiempo después del login para que la página procese
            time.sleep(3)
            
            # Verificar que el login fue exitoso - esperar a que aparezca algún elemento de la página post-login
            logger.info("Verificando que el login fue exitoso...")
            try:
                # Esperar a que la página cambie o aparezca algún elemento característico
                login_page.wait_for_load_state("networkidle", timeout=self.TIMEOUT_PAGE_LOAD)
                logger.info("Página post-login cargada")
            except Exception as e:
                logger.warning(f"Timeout esperando carga de página post-login: {e}")
            
            # Esperar más tiempo para que el portal cargue completamente y simular comportamiento humano
            logger.info("Esperando a que el portal cargue completamente...")
            # Simular comportamiento humano: scroll y movimientos del mouse
            try:
                login_page.evaluate("window.scrollTo(0, Math.random() * 300)")
                time.sleep(random.uniform(1, 2))
                login_page.mouse.move(random.randint(100, 800), random.randint(100, 600))
                time.sleep(random.uniform(0.5, 1))
                login_page.evaluate("window.scrollTo(0, 0)")
                time.sleep(random.uniform(1, 2))
            except:
                pass
            time.sleep(random.uniform(2, 4))  # Delay aleatorio adicional
            
            # Intentar múltiples formas de encontrar el enlace a e-Servicios SRT
            logger.info("Buscando enlace 'e-Servicios SRT'...")
            servicios_link = None
            servicios_page = None
            link_found = False
            
            # Intentar diferentes selectores y estrategias
            selectores = [
                lambda p: p.locator("a:has-text('e-Servicios SRT')"),
                lambda p: p.locator("a:has-text('e-Servicios')"),
                lambda p: p.locator("a:has-text('SRT')"),
                lambda p: p.locator("a[href*='srt']"),
                lambda p: p.locator("a[href*='SRT']"),
                lambda p: p.locator("a[href*='servicios']"),
                lambda p: p.locator("a[href*='Servicios']"),
            ]
            
            for i, selector_func in enumerate(selectores):
                try:
                    servicios_link = selector_func(login_page)
                    count = servicios_link.count()
                    if count > 0:
                        logger.info(f"Enlace encontrado con selector {i+1}")
                        link_found = True
                        break
                except Exception as e:
                    logger.debug(f"Selector {i+1} falló: {e}")
                    continue
            
            # Si no se encuentra el enlace, intentar buscar todos los enlaces y filtrar
            if not link_found:
                logger.info("No se encontró con selectores específicos, buscando en todos los enlaces...")
                try:
                    # Esperar un poco más y buscar en iframes también
                    time.sleep(2)
                    all_links = login_page.locator("a").all()
                    logger.info(f"Encontrados {len(all_links)} enlaces en la página")
                    for link in all_links:
                        try:
                            text = link.inner_text(timeout=1000).lower()
                            href = link.get_attribute("href") or ""
                            if "srt" in text or "servicios" in text or "srt" in href.lower() or "eservicios" in href.lower():
                                logger.info(f"Enlace encontrado por texto/href: {text[:50]} - {href[:50]}")
                                servicios_link = link
                                link_found = True
                                break
                        except:
                            continue
                except Exception as e:
                    logger.debug(f"Error buscando en todos los enlaces: {e}")
            
            # Si no encontramos el enlace, intentar buscar en iframes o esperar más
            if not link_found:
                logger.info("Esperando más tiempo para que el portal cargue completamente...")
                time.sleep(random.uniform(3, 5))
                
                # Intentar buscar de nuevo después de esperar
                for i, selector_func in enumerate(selectores):
                    try:
                        servicios_link = selector_func(login_page)
                        count = servicios_link.count()
                        if count > 0:
                            logger.info(f"Enlace encontrado con selector {i+1} después de esperar")
                            link_found = True
                            break
                    except:
                        continue
            
            # Si aún no encontramos el enlace, intentar navegar directamente (último recurso)
            if not link_found:
                logger.warning("No se encontró el enlace 'e-Servicios SRT', intentando navegar directamente...")
                try:
                    # ESTRATEGIA: Usar la misma página del portal en lugar de crear una nueva
                    # Esto mantiene las cookies y la sesión, reduciendo detección de bot
                    logger.info("Usando la misma página del portal para mantener sesión...")
                    
                    # Simular comportamiento humano más realista antes de navegar
                    logger.info("Simulando comportamiento humano antes de navegar...")
                    try:
                        # Múltiples movimientos de scroll y mouse para parecer más humano
                        for _ in range(random.randint(2, 4)):
                            scroll_y = random.randint(50, 400)
                            login_page.evaluate(f"window.scrollTo(0, {scroll_y})")
                            time.sleep(random.uniform(0.3, 0.8))
                            login_page.mouse.move(random.randint(100, 900), random.randint(100, 700))
                            time.sleep(random.uniform(0.2, 0.5))
                        login_page.evaluate("window.scrollTo(0, 0)")
                        time.sleep(random.uniform(1, 2))
                    except:
                        pass
                    
                    # Esperar un tiempo aleatorio antes de navegar (simula tiempo de lectura)
                    wait_time = random.uniform(3, 6)
                    logger.info(f"Esperando {wait_time:.1f}s antes de navegar (simulando lectura)...")
                    time.sleep(wait_time)
                    
                    # Intentar navegar usando la misma página (mantiene cookies/sesión)
                    logger.info(f"Navegando a {self.ALICUOTAS_URL} usando la misma sesión...")
                    servicios_page = login_page
                    servicios_page.goto(self.ALICUOTAS_URL, wait_until="domcontentloaded", timeout=self.TIMEOUT_PAGE_LOAD)
                    time.sleep(random.uniform(1, 2))  # Esperar después de navegar
                    
                    # Verificar que no fuimos redirigidos (detección de bot)
                    final_url = servicios_page.url
                    page_title = servicios_page.title()
                    logger.info(f"URL final después de navegación: {final_url}")
                    logger.info(f"Título de la página: {page_title}")
                    
                    # Detectar si fuimos redirigidos a una página de error
                    if "errorvalidate" in final_url.lower() or "error" in page_title.lower():
                        logger.error(f"Redirección a página de error detectada: {final_url} - {page_title}")
                        logger.error("El sitio está detectando el bot y bloqueando el acceso")
                        logger.info("Intentando estrategia alternativa: usar el contexto de la sesión del portal...")
                        
                        # ESTRATEGIA: Usar la misma página del portal (mantiene cookies/sesión)
                        logger.info("Usando la misma página del portal para mantener cookies y sesión...")
                        servicios_page = login_page
                        
                        # Simular comportamiento humano antes de navegar
                        logger.info("Simulando interacción humana...")
                        try:
                            # Hacer scroll
                            servicios_page.evaluate("window.scrollTo(0, Math.random() * 200)")
                            time.sleep(random.uniform(1, 2))
                            # Mover mouse (simulado)
                            servicios_page.mouse.move(random.randint(100, 500), random.randint(100, 500))
                            time.sleep(random.uniform(0.5, 1.5))
                        except:
                            pass
                        
                        # Esperar un poco más para simular comportamiento humano
                        time.sleep(random.uniform(2, 4))
                        
                        # Intentar navegar de nuevo usando la misma página
                        logger.info("Reintentando navegación con la misma sesión...")
                        servicios_page.goto(self.ALICUOTAS_URL, wait_until="networkidle", timeout=self.TIMEOUT_PAGE_LOAD)
                        final_url = servicios_page.url
                        page_title = servicios_page.title()
                        logger.info(f"URL después de segundo intento: {final_url}")
                        logger.info(f"Título después de segundo intento: {page_title}")
                        
                        if "errorvalidate" in final_url.lower() or "error" in page_title.lower():
                            logger.error("Segundo intento también resultó en error. El sitio está bloqueando el acceso.")
                            raise Exception(f"El sitio está bloqueando el acceso (redirigido a: {final_url}). Puede ser detección de bot.")
                    
                    if "alicuotas" not in final_url.lower() and "srt" not in final_url.lower() and "error" not in final_url.lower():
                        logger.warning(f"URL final diferente a la esperada: {final_url}")
                        logger.warning("Esto puede indicar detección de bot. Intentando esperar y recargar...")
                        time.sleep(3)
                        servicios_page.reload(wait_until="networkidle", timeout=self.TIMEOUT_PAGE_LOAD)
                        final_url = servicios_page.url
                        logger.info(f"URL después de recargar: {final_url}")
                    
                    if final_url == self.ALICUOTAS_URL or "alicuotas" in final_url.lower():
                        logger.info("Navegación directa exitosa, estamos en la página correcta")
                    elif "error" not in final_url.lower():
                        logger.warning(f"URL final diferente a la esperada, pero continuando: {final_url}")
                        
                except Exception as e:
                    logger.error(f"Error al navegar directamente: {e}")
                    # Si falla, intentar desde la página actual
                    try:
                        servicios_page = login_page.context.new_page()
                        servicios_page.goto("https://eservicios.srt.gob.ar", wait_until="networkidle", timeout=self.TIMEOUT_PAGE_LOAD)
                        logger.info("Navegación a dominio SRT exitosa")
                        time.sleep(2)  # Esperar antes de continuar
                    except Exception as e2:
                        logger.error(f"Error al navegar al dominio SRT: {e2}")
                        # Intentar obtener el HTML de la página para debugging
                        page_content = login_page.content()
                        logger.error(f"No se encontró el enlace 'e-Servicios SRT'. URL actual: {login_page.url}")
                        logger.error(f"Título de la página: {login_page.title()}")
                        # Log solo una porción del contenido para no saturar los logs
                        logger.debug(f"Contenido de la página (primeros 500 chars): {page_content[:500]}")
                        raise Exception("No se pudo encontrar el enlace 'e-Servicios SRT' ni navegar directamente. El login puede haber fallado o la página cambió.")
            
            # Si encontramos el enlace, hacer clic en él (MEJOR que navegar directamente)
            if link_found and servicios_link is not None and servicios_page is None:
                logger.info("Enlace encontrado, simulando comportamiento humano antes de hacer clic...")
                # Simular comportamiento humano antes de hacer clic
                try:
                    # Mover el mouse sobre el enlace
                    if hasattr(servicios_link, 'first'):
                        link_element = servicios_link.first
                    else:
                        link_element = servicios_link
                    
                    # Obtener posición del elemento y mover el mouse
                    box = link_element.bounding_box()
                    if box:
                        login_page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
                        time.sleep(random.uniform(0.5, 1.5))
                    
                    # Hacer hover sobre el enlace
                    link_element.hover(timeout=self.TIMEOUT_FIELD_WAIT)
                    time.sleep(random.uniform(0.3, 0.8))
                except Exception as e:
                    logger.debug(f"Error simulando hover: {e}")
                
                logger.info("Haciendo clic en enlace 'e-Servicios SRT'...")
                try:
                    with login_page.expect_popup(timeout=self.TIMEOUT_PAGE_LOAD) as popup_info:
                        if hasattr(servicios_link, 'first'):
                            servicios_link.first.click(timeout=self.TIMEOUT_FIELD_WAIT, delay=random.randint(50, 150))
                        else:
                            servicios_link.click(timeout=self.TIMEOUT_FIELD_WAIT, delay=random.randint(50, 150))
                    servicios_page = popup_info.value
                    logger.info("Página de servicios abierta desde popup")
                    time.sleep(random.uniform(1, 2))  # Esperar después de abrir popup
                except Exception as e:
                    logger.warning(f"Error al hacer clic en el enlace, intentando navegar directamente: {e}")
                    # Si falla el click, intentar navegar directamente como último recurso
                    try:
                        servicios_page = login_page.context.new_page()
                        servicios_page.goto(self.ALICUOTAS_URL, wait_until="domcontentloaded", timeout=self.TIMEOUT_PAGE_LOAD)
                        logger.info("Navegación directa después de fallo de click exitosa")
                    except Exception as e2:
                        logger.error(f"Error en navegación directa: {e2}")
                        raise
            
            # Verificar que tenemos una página de servicios antes de continuar
            if servicios_page is None:
                raise Exception("No se pudo obtener la página de servicios después del login")
            
            # Si navegamos directamente, ya estamos en la página de alícuotas, no necesitamos hacer clic en botones
            if not link_found:
                logger.info("Navegación directa realizada, verificando que estamos en la página correcta...")
                # Ya estamos en la URL de alícuotas, solo verificamos que cargó
                try:
                    servicios_page.wait_for_load_state("networkidle", timeout=self.TIMEOUT_PAGE_LOAD)
                    logger.info("Página de alícuotas cargada correctamente")
                    
                    # Verificar que la página tiene el contenido esperado (no fue bloqueada)
                    page_title = servicios_page.title()
                    logger.info(f"Título de la página: {page_title}")
                    
                    # Esperar un poco más para que cualquier script de detección se ejecute
                    time.sleep(2)
                    
                except Exception as e:
                    logger.warning(f"Timeout esperando carga de página: {e}")
            else:
                # Si encontramos el enlace y lo clickeamos, entonces sí necesitamos hacer clic en el botón
                logger.info("Haciendo clic en botón de servicios...")
                try:
                    servicios_page.locator(self.SELECTOR_SERVICIOS_BUTTON).click(timeout=self.TIMEOUT_FIELD_WAIT)
                    logger.info("Botón de servicios clickeado")
                except Exception as e:
                    logger.warning(f"No se pudo hacer clic en el botón de servicios: {e}")
                    # Continuar de todas formas, puede que ya estemos en la página correcta
            
            # Esperar a que el captcha aparezca y resolverlo inmediatamente
            logger.info("Esperando a que el captcha aparezca para resolverlo...")
            try:
                captcha_selector = None
                for intento in range(6):  # 6 intentos de 5 segundos = 30 segundos total
                    captcha_selector = self._encontrar_captcha_iframe(servicios_page)
                    if captcha_selector:
                        servicios_page.wait_for_selector(captcha_selector, state="visible", timeout=5000)
                        logger.info("Captcha visible, resolviendo ahora...")
                        break
                    time.sleep(1)
                
                if captcha_selector:
                    self._resolver_captcha(servicios_page)
                    time.sleep(self.DELAY_MEDIUM)
                    token = self._obtener_token_captcha(servicios_page)
                    if token and len(token) > 50:
                        self.captcha_token = token[:50] + "..."
                        self.captcha_resuelto = True
                        logger.info("✅ Captcha resuelto exitosamente durante el startup")
                    else:
                        self.captcha_resuelto = False
                else:
                    logger.info("Captcha no apareció aún, se resolverá cuando se ingrese un CUIT")
                    self.captcha_resuelto = False
            except Exception as e:
                logger.warning(f"Error al resolver captcha durante startup: {e}")
                self.captcha_resuelto = False
            
            logger.info("Página de servicios cargada")
            
            return servicios_page
            
        except Exception as e:
            logger.error(f"Error durante el proceso de login: {e}", exc_info=True)
            # Intentar capturar el estado de la página para debugging
            try:
                if 'login_page' in locals():
                    logger.error(f"URL de login_page al error: {login_page.url}")
                    logger.error(f"Título: {login_page.title()}")
            except:
                pass
            raise
    
    def inicializar_sesion(self):
        """Inicializa la sesión del navegador y realiza el login."""
        try:
            logger.info("Inicializando sesión del navegador...")
            
            context_options = self._get_context_options()
            
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.firefox.launch(headless=self.headless)
            self.context = self.browser.new_context(**context_options)
            self._apply_stealth(self.context)
            self.page = self.context.new_page()
            
            logger.info("Iniciando sesión...")
            self.servicios_page = self._realizar_login(self.page)
            
            self.session_ready = True
            logger.info("Sesión del navegador inicializada y lista para recibir requests")
            
            # El captcha ya debería estar resuelto si apareció durante el login
            if self.captcha_resuelto:
                logger.info("✅ Captcha ya resuelto y listo para usar")
            else:
                logger.info("Captcha se resolverá cuando aparezca o en la primera consulta")
            
        except Exception as e:
            logger.error(f"Error al inicializar sesión: {e}", exc_info=True)
            self.session_ready = False
            raise
    
    
    def _obtener_token_captcha(self, page: Page) -> Optional[str]:
        """Obtiene el token del captcha desde el textarea."""
        return page.evaluate("""() => {
            const textarea = document.querySelector('textarea[id="g-recaptcha-response"]');
            return textarea ? textarea.value : '';
        }""")
    
    def _verificar_sesion_vencida(self, page: Page) -> bool:
        """Verifica si la sesión ha expirado."""
        try:
            # Verificar en contenido de la página (método más rápido)
            page_content = page.content()
            if "Clave Fiscal" in page_content and "Ingresar" in page_content:
                h4_con_texto = page.locator("h4").filter(has_text="Clave Fiscal")
                if h4_con_texto.count() > 0:
                    logger.warning("Sesión vencida detectada")
                    return True
            return False
        except Exception as e:
            logger.warning(f"Error al verificar sesión vencida: {e}")
            return False
    
    def _rehacer_login(self):
        """Re-hace el login cuando la sesión ha expirado."""
        try:
            logger.info("Sesión vencida detectada. Re-haciendo login...")
            
            try:
                if self.servicios_page:
                    self.servicios_page.close()
                if self.login_page:
                    self.login_page.close()
            except:
                pass
            
            self.servicios_page = self._realizar_login(self.page)
            self.session_ready = True
            logger.info("Sesión restaurada correctamente")
            
        except Exception as e:
            logger.error(f"Error al re-hacer login: {e}", exc_info=True)
            self.session_ready = False
            raise
    
    def cerrar_sesion(self):
        """Cierra la sesión del navegador."""
        try:
            if self.servicios_page:
                self.servicios_page.close()
            if self.login_page:
                self.login_page.close()
            if self.page:
                self.page.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            
            self.servicios_page = None
            self.login_page = None
            self.page = None
            self.browser = None
            self.context = None
            self.playwright = None
            self.session_ready = False
            
            logger.info("Sesión del navegador cerrada")
        except Exception as e:
            logger.error(f"Error al cerrar sesión: {e}", exc_info=True)
    
    def obtener_alicuotas(self, cuits: List[str]) -> List[Dict[str, Optional[str]]]:
        """Obtiene las alícuotas para una lista de CUITs."""
        if not self.session_ready or not self.servicios_page:
            logger.warning("La sesión no está inicializada. Inicializando ahora...")
            try:
                self.inicializar_sesion()
            except Exception as e:
                logger.error(f"Error al inicializar sesión: {e}", exc_info=True)
                raise RuntimeError(f"Error al inicializar sesión del navegador: {str(e)}") from e
        
        logger.info(f"Procesando {len(cuits)} CUITs secuencialmente...")
        return self._obtener_alicuotas_secuencial(cuits)
    
    def _obtener_alicuotas_secuencial(self, cuits: List[str]) -> List[Dict[str, Optional[str]]]:
        """Procesa CUITs secuencialmente usando la sesión existente."""
        resultados = []
        
        try:
            servicios_page = self.servicios_page
            
            logger.info("Procesando CUITs usando sesión existente...")
            
            for i, cuit in enumerate(cuits, 1):
                    try:
                        logger.info(f"Procesando CUIT {i}/{len(cuits)}: {cuit}")
                        
                        self._verificar_y_renovar_sesion(servicios_page)
                        
                        if i > 1:
                            self._resetear_formulario(servicios_page)
                        
                        self._verificar_y_corregir_url(servicios_page)
                        self._ingresar_cuit(servicios_page, cuit)
                        
                        # Resolver captcha ANTES de hacer la consulta
                        logger.info(f"Gestionando captcha para CUIT {cuit}...")
                        self._gestionar_captcha(servicios_page, cuit)
                        
                        # Verificar que el captcha se resolvió antes de continuar
                        if not self.captcha_resuelto:
                            logger.warning(f"Captcha no resuelto para CUIT {cuit}, reintentando...")
                            time.sleep(2)
                            self._gestionar_captcha(servicios_page, cuit)
                        
                        if not self.captcha_resuelto:
                            logger.error(f"No se pudo resolver el captcha para CUIT {cuit}")
                            resultados.append({
                                "cuit": cuit,
                                "alicuota": None,
                                "nombre": None,
                                "error": "No se pudo resolver el captcha"
                            })
                            continue
                        
                        logger.info(f"Captcha resuelto, procediendo con consulta para CUIT {cuit}")
                        self._consultar_alicuota(servicios_page)
                        
                        resultado = self._extraer_alicuota(servicios_page)
                        resultados.append({
                            "cuit": cuit,
                            "alicuota": resultado.get("alicuota"),
                            "nombre": resultado.get("nombre"),
                            "error": None
                        })
                        
                        logger.info(f"CUIT {cuit} procesado exitosamente: {resultado.get('alicuota')} - {resultado.get('nombre')}")
                        time.sleep(self.DELAY_MEDIUM)
                        
                    except Exception as e:
                        logger.error(f"Error al obtener la alícuota para CUIT {cuit}: {e}", exc_info=True)
                        resultados.append({
                            "cuit": cuit,
                            "alicuota": None,
                            "nombre": None,
                            "error": f"Error: {str(e)}"
                        })
                        if not self._intentar_resetear_pagina(servicios_page):
                            break
        
        except Exception as e:
            logger.error(f"Error al procesar CUITs: {e}", exc_info=True)
            if len(resultados) < len(cuits):
                for cuit in cuits[len(resultados):]:
                    resultados.append({
                        "cuit": cuit,
                        "alicuota": None,
                        "nombre": None,
                        "error": f"Error: {str(e)}"
                    })
        
        return resultados
    
    def _verificar_y_renovar_sesion(self, servicios_page: Page):
        """Verifica si la sesión está vencida y la renueva si es necesario."""
        try:
            if servicios_page and self._verificar_sesion_vencida(servicios_page):
                logger.warning("Sesión vencida detectada. Re-haciendo login...")
                self._rehacer_login()
                time.sleep(1)
        except Exception as e:
            logger.warning(f"Error al verificar sesión: {e}. Continuando...")
    
    def _cerrar_modal(self, page: Page):
        """Cierra cualquier modal abierto."""
        try:
            page.evaluate("""() => {
                document.querySelectorAll('.modal').forEach(m => {
                    m.classList.remove('in', 'show', 'fade');
                    m.style.display = 'none';
                });
                document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
            }""")
        except:
            pass
    
    def _resetear_formulario(self, servicios_page: Page):
        """Resetea el formulario para el siguiente CUIT."""
        with Timer("Resetear formulario y cerrar modal"):
            try:
                logger.info("Reseteando formulario para siguiente CUIT...")
                
                try:
                    servicios_page.url  # Verificar que la página sigue disponible
                except Exception as e:
                    logger.error(f"La página se cerró inesperadamente: {e}")
                    raise RuntimeError("La página del navegador se cerró") from e
                
                self._cerrar_modal(servicios_page)
                time.sleep(self.DELAY_SHORT)
                
                self._verificar_y_corregir_url(servicios_page)
                
            except Exception as e:
                logger.warning(f"Error al resetear para siguiente CUIT: {e}")
                if "Connection closed" in str(e) or "closed" in str(e).lower():
                    logger.error("Conexión con el navegador perdida, no se puede continuar")
                    raise
    
    def _verificar_y_corregir_url(self, page: Page):
        """Verifica y corrige la URL si es necesario."""
        try:
            current_url = page.url
            if "/home/Servicios.aspx" in current_url or ("Servicios.aspx" in current_url and "/Consultas/Alicuotas" not in current_url):
                logger.warning("Se detectó redirección a página principal, navegando de vuelta...")
                page.goto(self.ALICUOTAS_URL, timeout=self.TIMEOUT_PAGE_LOAD)
                time.sleep(self.DELAY_MEDIUM)
                logger.info("Navegación de vuelta completada")
            elif "/Consultas/Alicuotas/Default.aspx" not in current_url:
                logger.warning(f"URL inesperada: {current_url}, navegando a página de consulta...")
                page.goto(self.ALICUOTAS_URL, timeout=self.TIMEOUT_PAGE_LOAD)
                time.sleep(self.DELAY_MEDIUM)
        except Exception as e:
            logger.warning(f"Error al verificar URL: {e}")
    
    def _ingresar_cuit(self, page: Page, cuit: str):
        """Ingresa el CUIT en el campo correspondiente."""
        with Timer("Esperar campo CUIT disponible"):
            cuit_field = page.locator(self.SELECTOR_CUIT_FIELD)
            logger.info("Esperando a que el campo de CUIT esté disponible...")
            cuit_field.wait_for(state="visible", timeout=self.TIMEOUT_FIELD_WAIT)
            
            try:
                cuit_field.scroll_into_view_if_needed(timeout=2000)
            except:
                pass
            
        
        with Timer("Limpiar e ingresar CUIT"):
            try:
                page.evaluate(f"""() => {{
                    const field = document.getElementById('txtCuilCuit');
                    if (field) {{
                        field.value = '{cuit}';
                        field.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        field.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}""")
                logger.info(f"CUIT {cuit} ingresado")
            except:
                cuit_field.fill(cuit, timeout=self.TIMEOUT_FIELD_WAIT)
    
    def _gestionar_captcha(self, page: Page, cuit: str):
        """Gestiona la resolución del captcha."""
        # Verificar si el captcha ya está resuelto
        token_existente = self._obtener_token_captcha(page)
        if token_existente and len(token_existente) > 50:
            logger.info(f"Captcha ya resuelto para CUIT {cuit}, reutilizando...")
            self.captcha_token = token_existente[:50] + "..."
            self.captcha_resuelto = True
            return
        
        # Si no está resuelto, resolverlo
        logger.info(f"Resolviendo captcha para CUIT {cuit}...")
        self.captcha_resolviendo = True
        try:
            captcha_selector = self._encontrar_captcha_iframe(page)
            if captcha_selector:
                page.wait_for_selector(captcha_selector, state="visible", timeout=self.TIMEOUT_PAGE_LOAD)
                time.sleep(1)
            
            with Timer("Resolver captcha"):
                self._resolver_captcha(page)
                time.sleep(self.DELAY_MEDIUM)
                token = self._obtener_token_captcha(page)
                if token and len(token) > 50:
                    self.captcha_token = token[:50] + "..."
                    self.captcha_resuelto = True
                    logger.info(f"Captcha resuelto exitosamente para CUIT {cuit}")
                else:
                    logger.warning(f"Captcha resuelto pero token no encontrado para CUIT {cuit}")
                    self.captcha_resuelto = False
        except Exception as e:
            logger.error(f"Error al resolver captcha para CUIT {cuit}: {e}", exc_info=True)
            self.captcha_resuelto = False
        finally:
            self.captcha_resolviendo = False
    
    def _consultar_alicuota(self, page: Page):
        """Ejecuta la consulta de alícuota."""
        with Timer("Cerrar modal y hacer clic en Consultar"):
            # Cerrar modal y hacer clic en Consultar usando JavaScript
            page.evaluate("""() => {
                const modals = document.querySelectorAll('.modal');
                modals.forEach(modal => {
                    modal.classList.remove('in', 'show', 'fade');
                    modal.style.display = 'none';
                });
                
                const backdrops = document.querySelectorAll('.modal-backdrop');
                backdrops.forEach(backdrop => backdrop.remove());
                
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
                document.body.style.paddingRight = '';
                
                const btn = document.getElementById('btnConsultar');
                if (btn && typeof btn.onclick === 'function') {
                    btn.onclick();
                } else if (btn) {
                    btn.click();
                }
            }""")
            
            # Esperar frame de resultado
            logger.info("Esperando a que aparezca el resultado...")
            try:
                page.wait_for_selector(self.SELECTOR_RESULT_IFRAME, state="attached", timeout=self.TIMEOUT_FRAME_WAIT)
                logger.info("Frame de resultado detectado")
                time.sleep(self.DELAY_MEDIUM)
                
                frame_ready = False
                for intento in range(2):
                    frame_ready = page.evaluate("""() => {
                        const iframe = document.getElementById('ifrmResultadoPorCuit');
                        if (!iframe) return false;
                        try {
                            const frameDoc = iframe.contentDocument || iframe.contentWindow.document;
                            return frameDoc && frameDoc.body && frameDoc.body.textContent.length > 0;
                        } catch(e) {
                            return false;
                        }
                    }""")
                    if frame_ready:
                        break
                    time.sleep(0.2)
                
                if not frame_ready:
                    logger.warning("Frame detectado pero sin contenido, continuando de todas formas...")
            except Exception as e:
                logger.warning(f"No se encontró el frame de resultado rápidamente: {e}")
                time.sleep(self.DELAY_LONG)
    
    def _intentar_resetear_pagina(self, servicios_page: Page) -> bool:
        """Intenta resetear la página después de un error."""
        try:
            try:
                servicios_page.url
            except:
                logger.error("La página se cerró, no se puede continuar")
                return False
            
            servicios_page.locator(self.SELECTOR_SERVICIOS_BUTTON).click(timeout=2000)
            time.sleep(self.DELAY_MEDIUM)
            return True
        except Exception as reset_error:
            logger.warning(f"No se pudo resetear después del error: {reset_error}")
            if "closed" in str(reset_error).lower() or "Connection" in str(reset_error):
                logger.error("Conexión perdida, deteniendo procesamiento")
                return False
            return True
    
    def _encontrar_captcha_iframe(self, page: Page) -> Optional[str]:
        """Busca el iframe del captcha usando el método más confiable (div g-recaptcha)."""
        # Método principal: Buscar el div g-recaptcha (más confiable y rápido)
        try:
            g_recaptcha = page.locator('.g-recaptcha, [data-sitekey]')
            if g_recaptcha.count() > 0:
                iframe_info = page.evaluate("""
                    () => {
                        const gRecaptcha = document.querySelector('.g-recaptcha, [data-sitekey]');
                        if (gRecaptcha) {
                            const iframe = gRecaptcha.querySelector('iframe');
                            if (iframe) {
                                return {
                                    found: true,
                                    name: iframe.getAttribute('name'),
                                    title: iframe.getAttribute('title'),
                                    src: iframe.getAttribute('src')
                                };
                            }
                        }
                        return { found: false };
                    }
                """)
                
                if iframe_info.get('found'):
                    name = iframe_info.get('name')
                    if name:
                        selector = f'iframe[name="{name}"]'
                        logger.info(f"✅ Captcha encontrado: {selector}")
                        return selector
        except Exception as e:
            logger.debug(f"Búsqueda por div g-recaptcha falló: {e}")
        
        # Fallback: Buscar iframes con src que contenga 'recaptcha'
        try:
            iframe_info = page.evaluate("""
                () => {
                    const iframes = document.querySelectorAll('iframe');
                    for (const iframe of iframes) {
                        const src = iframe.getAttribute('src') || '';
                        const name = iframe.getAttribute('name') || '';
                        if (src.includes('recaptcha') || src.includes('googleapis') || 
                            name.startsWith('a-') || name.startsWith('c-')) {
                            return {
                                found: true,
                                name: name,
                                src: src
                            };
                        }
                    }
                    return { found: false };
                }
            """)
            
            if iframe_info.get('found'):
                name = iframe_info.get('name')
                if name:
                    selector = f'iframe[name="{name}"]'
                    logger.info(f"Captcha encontrado (fallback): {selector}")
                    return selector
        except Exception as e:
            logger.debug(f"Búsqueda fallback falló: {e}")
        
        logger.warning("No se pudo encontrar el iframe del captcha")
        return None
    
    def _resolver_captcha(self, page: Page):
        """Resuelve el captcha usando 2Captcha o método manual."""
        captcha_selector = self._encontrar_captcha_iframe(page)
        if not captcha_selector:
            raise Exception("Captcha iframe no está presente")
        
        iframe_locator = page.frame_locator(captcha_selector)
        
        if self.twocaptcha_service and self._resolver_captcha_con_servicio(page, iframe_locator):
            return
        
        logger.warning("Usando método manual para resolver captcha")
        self._resolver_captcha_manual(iframe_locator)
    
    def _resolver_captcha_con_servicio(self, page: Page, iframe_locator) -> bool:
        """Intenta resolver el captcha usando 2Captcha."""
        try:
            if not self.twocaptcha_service:
                logger.info("2Captcha no está disponible, usando método manual")
                return False
            
            page_url = page.url
            site_key = self._extraer_site_key(page, iframe_locator)
            
            if not site_key:
                logger.warning("No se pudo extraer el site_key del captcha, usando método manual")
                return False
            
            logger.info(f"Resolviendo reCAPTCHA con 2Captcha (site_key: {site_key[:20]}...)")
            with Timer("Resolver captcha con 2Captcha"):
                token = self.twocaptcha_service.solve_recaptcha_v2(page_url, site_key)
            
            if not token:
                logger.warning("2Captcha no pudo resolver el captcha, usando método manual")
                return False
            
            logger.info(f"Token obtenido (longitud: {len(token)})")
            result = self._inyectar_token_completo(page, token)
            
            if result.get('textareaFound', False):
                self.captcha_token = token[:50] + "..."
                self.captcha_resuelto = True
                time.sleep(self.DELAY_LONG)
                logger.info("reCAPTCHA resuelto exitosamente con 2Captcha")
                return True
            else:
                logger.warning(f"Token inyectado pero textarea no encontrado. Result: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error al resolver con 2Captcha: {e}", exc_info=True)
            return False
    
    def _inyectar_token_completo(self, page: Page, token: str) -> Dict:
        """Inyecta el token completo con todos los callbacks."""
        token_escaped = token.replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")
        
        return page.evaluate(f"""
            (function() {{
                const textarea = document.querySelector('textarea[id="g-recaptcha-response"]');
                
                if (textarea) {{
                    textarea.value = '{token_escaped}';
                    textarea.innerHTML = '{token_escaped}';
                    textarea.innerText = '{token_escaped}';
                    textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
                
                if (window.grecaptcha) {{
                    try {{
                        if (window.grecaptcha.callback) {{
                            const callbackName = window.grecaptcha.callback;
                            if (typeof window[callbackName] === 'function') {{
                                window[callbackName]('{token_escaped}');
                            }}
                        }}
                        
                        ['___grecaptcha_cfg', 'grecaptcha'].forEach(pattern => {{
                            if (window[pattern] && window[pattern].callback) {{
                                const cb = window[pattern].callback;
                                if (typeof cb === 'function') {{
                                    cb('{token_escaped}');
                                }} else if (typeof window[cb] === 'function') {{
                                    window[cb]('{token_escaped}');
                                }}
                            }}
                        }});
                    }} catch(e) {{
                        // Error silencioso
                    }}
                }}
                
                window.grecaptcha_response = '{token_escaped}';
                
                document.querySelectorAll('form').forEach(form => {{
                    const callbackAttr = form.getAttribute('data-callback');
                    if (callbackAttr && typeof window[callbackAttr] === 'function') {{
                        window[callbackAttr]('{token_escaped}');
                    }}
                }});
                
                return {{
                    textareaFound: !!textarea,
                    textareaValue: textarea ? textarea.value.substring(0, 50) : null,
                    grecaptchaAvailable: !!window.grecaptcha
                }};
            }})();
        """)
    
    def _resolver_captcha_manual(self, iframe_locator):
        """Resuelve el captcha manualmente."""
        logger.info("Iniciando resolución manual del captcha...")
        numeros_captcha = self._generar_secuencia_captcha()
        logger.info(f"Secuencia de números generada: {numeros_captcha}")
        
        try:
            for i, numero in enumerate(numeros_captcha, 1):
                logger.debug(f"Haciendo clic en número {i}/{len(numeros_captcha)}: {numero}")
                try:
                    elemento = iframe_locator.locator(f"[id=\"\\3{numero}\"]")
                    elemento.wait_for(state="visible", timeout=5000)
                    elemento.click(timeout=5000)
                    time.sleep(random.uniform(0.3, 0.6))  # Delay aleatorio entre clicks
                except Exception as e:
                    logger.warning(f"Error al hacer clic en número {numero}: {e}")
                    # Continuar con el siguiente número
                    continue
            
            logger.info("Haciendo clic en botón Verificar...")
            try:
                boton_verificar = iframe_locator.get_by_role("button", name="Verificar")
                boton_verificar.wait_for(state="visible", timeout=5000)
                boton_verificar.click(timeout=5000)
                logger.info("Botón Verificar clickeado")
                time.sleep(2)  # Esperar a que el captcha se procese
            except Exception as e:
                logger.error(f"Error al hacer clic en botón Verificar: {e}")
                raise
        except Exception as e:
            logger.error(f"Error durante resolución manual del captcha: {e}", exc_info=True)
            raise
    
    def _extraer_site_key(self, page: Page, iframe_locator) -> Optional[str]:
        """Extrae el site key del captcha."""
        try:
            # Método 1: Iframe src - buscar el captcha de manera flexible
            captcha_selector = self._encontrar_captcha_iframe(page)
            if captcha_selector:
                iframe_element = page.locator(captcha_selector)
                if iframe_element.count() > 0:
                    iframe_src = iframe_element.get_attribute("src")
                    if iframe_src:
                        for pattern in [r'[?&]k=([^&]+)', r'sitekey=([^&]+)', r'[?&]sitekey=([^&]+)']:
                            match = re.search(pattern, iframe_src)
                            if match:
                                logger.info(f"Site key encontrado: {match.group(1)[:20]}...")
                                return match.group(1)
            
            # Método 2: HTML content (extraer desde el div g-recaptcha o data-sitekey)
            page_content = page.content()
            patterns = [
                r'data-sitekey=["\']([^"\']+)["\']',
                r'sitekey=["\']([^"\']+)["\']',
                r'k=["\']([^"\']+)["\']',
                r'[?&]k=([^&\s"\']+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, page_content)
                if match:
                    logger.info(f"Site key encontrado: {match.group(1)[:20]}...")
                    return match.group(1)
            
            return None
        except Exception as e:
            logger.warning(f"Error al extraer site_key: {e}")
            return None
    
    
    def _generar_secuencia_captcha(self) -> List[str]:
        """Genera una secuencia aleatoria de números para el captcha manual."""
        cantidad_numeros = 5 + random.randint(0, 2)
        return [str(random.randint(0, 9)) for _ in range(cantidad_numeros)]
    
    def _extraer_alicuota(self, page: Page) -> Dict[str, str]:
        """Extrae la alícuota y nombre del resultado."""
        try:
            inicio = time.time()
            
            # Verificar que el iframe existe
            try:
                iframe_exists = page.locator(self.SELECTOR_RESULT_IFRAME).count() > 0
                if not iframe_exists:
                    logger.warning("El iframe de resultado no existe en la página")
                    return self._resultado_error("No se pudo extraer la alícuota", "No disponible")
            except:
                pass
            
            resultado_frame = page.frame_locator(self.SELECTOR_RESULT_IFRAME)
            
            # Esperar a que el frame esté listo
            try:
                page.wait_for_selector(self.SELECTOR_RESULT_IFRAME, state="attached", timeout=3000)
                logger.info("Frame de resultado detectado en el DOM")
                time.sleep(self.DELAY_SHORT)
                
                if time.time() - inicio > self.TIMEOUT_EXTRACTION:
                    return self._resultado_error("No se pudo extraer la alícuota (timeout)", "No disponible")
                
                try:
                    resultado_frame.locator(self.SELECTOR_ALICUOTA_LABEL).wait_for(state="attached", timeout=1000)
                    logger.info("Elemento lblAlicuota encontrado en el frame")
                except:
                    try:
                        resultado_frame.locator("text=Variable:").wait_for(state="attached", timeout=1000)
                        logger.info("Texto 'Variable:' encontrado en el frame")
                    except:
                        logger.warning("No se encontró 'Variable:' en el frame, intentando extraer rápidamente...")
            except Exception as e:
                logger.warning(f"Error esperando frame: {e}")
                return self._resultado_error("No se pudo extraer la alícuota", "No disponible")
            
            if time.time() - inicio > self.TIMEOUT_EXTRACTION:
                return self._resultado_error("No se pudo extraer la alícuota (timeout)", "No disponible")
            
            # Extraer datos
            try:
                contenido_completo = self._extraer_contenido_frame(page)
                texto_completo = self._extraer_texto_alicuota(page)
                
                if time.time() - inicio > self.TIMEOUT_EXTRACTION:
                    nombre = self._extraer_nombre_desde_contenido(contenido_completo)
                    return self._resultado_error("No se pudo extraer la alícuota (timeout)", nombre if nombre else "No disponible")
                
                alicuota = None
                if texto_completo and "Variable:" in texto_completo:
                    alicuota = texto_completo.split("Variable:")[1].split("/")[0].strip()
                
                nombre = self._extraer_nombre_desde_contenido(contenido_completo)
                
                return {
                    "alicuota": alicuota if alicuota else "No se pudo extraer la alícuota",
                    "nombre": nombre if nombre else "No disponible"
                }
                
            except Exception as e:
                logger.warning(f"Error al extraer información completa: {e}")
                return self._resultado_error("No se pudo extraer la alícuota", "No disponible")
            
        except Exception as e:
            logger.warning(f"Error en _extraer_alicuota: {e}")
            return self._resultado_error(f"Error: {str(e)}", "No disponible")
    
    def _extraer_contenido_frame(self, page: Page) -> Optional[str]:
        """Extrae el contenido completo del frame."""
        try:
            return page.evaluate("""() => {
                try {
                    const iframe = document.getElementById('ifrmResultadoPorCuit');
                    if (!iframe) return null;
                    const frameDoc = iframe.contentDocument || iframe.contentWindow.document;
                    if (!frameDoc || !frameDoc.body) return null;
                    return frameDoc.body.textContent || frameDoc.body.innerText || '';
                } catch(e) {
                    return null;
                }
            }""")
        except:
            return None
    
    def _extraer_texto_alicuota(self, page: Page) -> Optional[str]:
        """Extrae el texto que contiene la alícuota."""
        try:
            return page.evaluate("""() => {
                try {
                    const iframe = document.getElementById('ifrmResultadoPorCuit');
                    if (!iframe) return null;
                    const frameDoc = iframe.contentDocument || iframe.contentWindow.document;
                    const lblAlicuota = frameDoc.getElementById('lblAlicuota');
                    if (lblAlicuota) {
                        return lblAlicuota.textContent || lblAlicuota.innerText || '';
                    }
                    const elements = frameDoc.querySelectorAll('*');
                    for (let el of elements) {
                        if (el.textContent && el.textContent.includes('Variable:')) {
                            return el.textContent;
                        }
                    }
                    return null;
                } catch(e) {
                    return null;
                }
            }""")
        except:
            return None
    
    def _extraer_nombre_desde_contenido(self, contenido: Optional[str]) -> Optional[str]:
        """Extrae el nombre desde el contenido del frame."""
        if not contenido:
            return None
        
        lineas = contenido.split('\n')
        for linea in lineas:
            linea = linea.strip()
            if linea and "Variable:" not in linea and "%" not in linea and "$" not in linea:
                if len(linea) > 3 and not linea.isdigit():
                    return linea
        
        partes = contenido.split('\n')
        for parte in partes:
            parte = parte.strip()
            if parte and len(parte) > 5 and "Variable" not in parte and "%" not in parte:
                return parte
        
        return None
    
    def _resultado_error(self, alicuota: str, nombre: str) -> Dict[str, str]:
        """Retorna un diccionario de resultado con error."""
        return {
            "alicuota": alicuota,
            "nombre": nombre
        }
