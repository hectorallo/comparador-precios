## Cambios recientes (v2026-11-02-a)

- Sesión HTTP por hilo (evita cuelgues con `requests.Session` compartida).
- Reintentos automáticos con backoff en 429/5xx.
- Timeout de conexión separado del de lectura (4s / 10s).
- Cache con límite de tamaño (512 entradas, 10 min) — no crece sin control.
- Rate limit de 30 consultas/min por IP en `/api/search`.
- `/api/health` para uptime checks de Render.
- Campo `cached: true/false` en la respuesta de `/api/search`.
- Mejor variante por producto: elige la más barata **con stock** cuando hay varias.
- Service worker + PWA instalable.