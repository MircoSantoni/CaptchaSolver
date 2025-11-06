def get_frontend_html() -> str:
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Alícuotas SRT</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {
                background-color: #f8f9fa;
                padding: 2rem 0;
            }
            
            .main-container {
                max-width: 900px;
            }
            
            .status-badge {
                font-size: 0.875rem;
            }
            
            textarea {
                font-family: 'Courier New', monospace;
            }
            
            .cuit {
                font-family: 'Courier New', monospace;
            }
        </style>
    </head>
    <body>
        <div class="container main-container">
            <div class="card shadow-sm">
                <div class="card-body p-4">
                    <h1 class="h4 mb-4">Alícuotas SRT</h1>
                    
                    <div class="mb-3">
                        <span class="badge bg-secondary status-badge" id="statusText">Verificando...</span>
                    </div>
                    
                    <form id="cuitForm">
                        <div class="mb-3">
                            <textarea 
                                class="form-control" 
                                id="cuits" 
                                name="cuits" 
                                rows="8" 
                                placeholder="30717692221"
                                required
                            ></textarea>
                        </div>
                        <button type="submit" class="btn btn-primary" id="submitBtn">Consultar</button>
                    </form>
                    
                    <div class="text-center mt-4" id="loading" style="display: none;">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Cargando...</span>
                        </div>
                        <div class="mt-2 text-muted small" id="timerValue">0s</div>
                    </div>
                    
                    <div class="mt-4" id="results" style="display: none;">
                        <div class="table-responsive">
                            <table class="table table-striped table-hover">
                                <thead class="table-dark">
                                    <tr>
                                        <th>CUIT</th>
                                        <th>Nombre</th>
                                        <th>Alícuota</th>
                                    </tr>
                                </thead>
                                <tbody id="resultsBody">
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            const form = document.getElementById('cuitForm');
            const loading = document.getElementById('loading');
            const results = document.getElementById('results');
            const resultsBody = document.getElementById('resultsBody');
            const submitBtn = document.getElementById('submitBtn');
            const timerValue = document.getElementById('timerValue');
            const statusText = document.getElementById('statusText');
            
            let timerInterval = null;
            let startTime = null;
            let captchaCheckInterval = null;
            
            async function checkCaptchaStatus() {
                try {
                    const response = await fetch('/api/alicuotas/captcha-status');
                    const data = await response.json();
                    
                    statusText.className = 'badge status-badge';
                    
                    if (data.captcha_resolviendo) {
                        statusText.textContent = 'Resolviendo...';
                        statusText.classList.add('bg-warning');
                    } else if (data.captcha_resuelto) {
                        statusText.textContent = 'Listo';
                        statusText.classList.add('bg-success');
                        if (captchaCheckInterval) {
                            clearInterval(captchaCheckInterval);
                            captchaCheckInterval = null;
                        }
                    } else if (data.session_ready) {
                        statusText.textContent = 'Iniciando...';
                        statusText.classList.add('bg-info');
                    } else {
                        statusText.textContent = 'Verificando...';
                        statusText.classList.add('bg-secondary');
                    }
                } catch (error) {
                    statusText.textContent = 'Error';
                    statusText.className = 'badge bg-danger status-badge';
                }
            }
            
            checkCaptchaStatus();
            captchaCheckInterval = setInterval(checkCaptchaStatus, 1000);
            
            function startTimer() {
                startTime = Date.now();
                timerInterval = setInterval(() => {
                    const elapsed = Math.floor((Date.now() - startTime) / 1000);
                    const minutes = Math.floor(elapsed / 60);
                    const seconds = elapsed % 60;
                    timerValue.textContent = minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
                }, 100);
            }
            
            function stopTimer() {
                if (timerInterval) {
                    clearInterval(timerInterval);
                    timerInterval = null;
                }
            }
            
            function validateCuit(cuit) {
                const cleaned = cuit.replace(/[-\\s]/g, '');
                return /^\\d{11}$/.test(cleaned);
            }
            
            function normalizeCuit(cuit) {
                return cuit.replace(/[-\\s]/g, '');
            }
            
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                
                const cuitsText = document.getElementById('cuits').value.trim();
                if (!cuitsText) {
                    alert('Ingresa al menos un CUIT');
                    return;
                }
                
                const cuitsRaw = cuitsText
                    .split(/[\\n,]+/)
                    .map(c => c.trim())
                    .filter(c => c.length > 0);
                
                const cuits = cuitsRaw.map(normalizeCuit);
                
                const invalidCuits = cuits.filter(c => !validateCuit(c));
                if (invalidCuits.length > 0) {
                    alert('Formato inválido');
                    return;
                }
                
                results.style.display = 'none';
                resultsBody.innerHTML = '';
                
                loading.style.display = 'block';
                submitBtn.disabled = true;
                timerValue.textContent = '0s';
                startTimer();
                
                try {
                    const response = await fetch('/api/alicuotas/async', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ cuits: cuits })
                    });
                    
                    if (!response.ok) {
                        throw new Error(`Error: ${response.status}`);
                    }
                    
                    const data = await response.json();
                    displayResults(data);
                    
                } catch (error) {
                    alert('Error: ' + error.message);
                } finally {
                    stopTimer();
                    loading.style.display = 'none';
                    submitBtn.disabled = false;
                }
            });
            
            function displayResults(data) {
                resultsBody.innerHTML = '';
                
                data.forEach(item => {
                    const row = document.createElement('tr');
                    
                    if (item.error) {
                        row.innerHTML = `
                            <td class="cuit">${item.cuit}</td>
                            <td>-</td>
                            <td><span class="text-danger">Error</span></td>
                        `;
                    } else {
                        row.innerHTML = `
                            <td class="cuit">${item.cuit}</td>
                            <td>${item.nombre || '-'}</td>
                            <td>${item.alicuota || '-'}</td>
                        `;
                    }
                    
                    resultsBody.appendChild(row);
                });
                
                results.style.display = 'block';
            }
        </script>
    </body>
    </html>
    """

