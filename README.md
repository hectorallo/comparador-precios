# Comparador de precios de supermercados

Busca un producto en Carrefour, Jumbo, Disco, Vea, Día y ChangoMás a la vez y
muestra cuál lo tiene más barato. Funciona por **código de barras (EAN)** o por **nombre**.

Hay tres formas de usarlo en el teléfono. Elegí una.

---

## Opción A: directo en el teléfono Android (Termux) — recomendada

Es la única que no depende de nada más y donde **el escáner de cámara funciona**
(la cámara requiere `localhost` o `https`, y esto es `localhost`).

1. Instalá **Termux desde F-Droid** (f-droid.org). La versión de Play Store está desactualizada y falla.
2. Pasá `comparador-precios.zip` al teléfono (WhatsApp, Drive, cable...) y que quede en Descargas.
3. Abrí Termux y pegá, línea por línea:

```bash
pkg update -y && pkg install -y python unzip
termux-setup-storage          # aceptá el permiso de archivos
cd ~
unzip ~/storage/downloads/comparador-precios.zip
cd comparador
pip install -r requirements.txt
python server.py
```

4. Dejá Termux abierto y en Chrome entrá a **http://localhost:8000**.
5. Menú de Chrome (⋮) → **Agregar a la pantalla principal / Instalar app**.

Para usarlo otro día: abrí Termux y corré
`cd ~/comparador && python server.py`.
Si Android cierra Termux en segundo plano, en la notificación de Termux tocá "Acquire wakelock".

---

## Opción B: en tu PC, usando el teléfono por Wi-Fi

Sirve para iPhone también, pero **el botón Escanear no anda** (el teléfono entra por http,
no por localhost): se escribe el código a mano.

1. En la PC: `pip install -r requirements.txt` y `python server.py`.
2. Averiguá la IP de la PC: en Windows `ipconfig` (IPv4), en Mac/Linux `ip a` o `ifconfig`
   (algo como `192.168.1.35`).
3. Con el teléfono en el mismo Wi-Fi, abrí `http://192.168.1.35:8000`.
4. Si no carga, permití Python en el firewall de Windows cuando lo pregunte.

---

## Opción C: publicarlo online (https, anda en iPhone y Android, con escáner)

El proyecto ya trae `Procfile` y `gunicorn`. Por ejemplo en Render (tiene plan gratis):

1. Subí esta carpeta a un repositorio de GitHub.
2. En render.com: New → Web Service → elegí el repo.
3. Build command: `pip install -r requirements.txt`
   Start command: `gunicorn server:app`
4. Te da una URL `https://...onrender.com`. Abrila en el teléfono y "Agregar a pantalla principal".

Ojo: algunos supermercados pueden bloquear pedidos que vienen de servidores en la nube.
Si desde ahí todas las tiendas salen "Sin respuesta", usá la opción A.

---

## Cómo funciona

- Estas tiendas usan VTEX, que expone un endpoint público de catálogo:
  `/api/catalog_system/pub/products/search`.
  - Por código de barras: `?fq=alternateIds_Ean:<codigo>`
  - Por nombre: `?ft=<texto>`
- El backend consulta todas las tiendas en paralelo, muestra como "Sin respuesta" las que
  fallen y agrupa por EAN, así el mismo producto de distintas tiendas aparece junto, ordenado por precio.
- Los resultados se guardan 10 minutos en memoria.
- El precio por kg/litro se estima leyendo el tamaño del nombre ("1 L", "500 g"); es
  aproximado y en packs ("x6") puede no ser exacto.

## Agregar tiendas

Si la tienda usa VTEX, agregá una línea en `STORES` de `server.py`.
Coto, La Anónima y otras tienen sistema propio y necesitarían un adaptador aparte.

## Aviso

Usa endpoints públicos no documentados oficialmente; las tiendas pueden cambiarlos o
limitar pedidos. Para uso personal, con el caché y sin consultas masivas, debería andar bien.
