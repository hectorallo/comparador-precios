# Comparador de precios de supermercados

Busca un producto en Carrefour, Jumbo, Disco, Vea, Día, ChangoMás, Toledo y Coto a la vez y
muestra cuál lo tiene más barato. Funciona por **código de barras (EAN)** o por **nombre**.

## Carrito: cuánto estoy pagando en el súper

En la pestaña **Carrito**:
1. Elegí en qué súper estás ("Comprando en").
2. Tocá "Escanear productos" y pasá la cámara por cada cosa que ponés en el carrito (o
   escribí el código a mano). Si escaneás el mismo producto otra vez, suma una unidad.
3. Abajo, siempre a la vista, aparece el **total aproximado**.

Detalles:
- Usa el precio de la web de esa tienda. Si el producto no está ahí, te lo marca y podés
  **escribir el precio de la góndola a mano** (vale solo para esa tienda).
- Si la tienda informa una promo (por ejemplo "2da al 50%"), la muestra, pero **no la
  descuenta** del total: normalmente se aplica en caja.
- Te dice si ese mismo carrito habría salido más barato en otra tienda.
- Es aproximado: puede diferir del ticket por promos, por la sucursal o por cambios de precio.
- Cambiar de tienda recalcula todo con los precios de la nueva tienda.

## Historial de precios y lista de compras

- **Historial:** cada vez que buscás un producto se guarda su menor precio del día. En cada
  producto, "Historial de precios" muestra el gráfico y si hoy está más barato o más caro que
  lo habitual. Mientras más días lo busques, más útil es.
- **Mi lista:** en cada producto tocá "Agregar a mi lista". En la pestaña "Mi lista" ponés
  cantidades y tocás "Revisar precios": te dice cuánto sale todo en cada tienda y cuánto
  gastás si repartís la compra comprando cada cosa donde está más barata.
- Todo esto se guarda **en el teléfono** (no en el servidor), así que no se pierde cuando
  Render se reinicia. Cada dispositivo tiene su propia lista e historial. Si borrás los datos
  del navegador se pierden: usá "Copia de seguridad" en Mi lista para guardar un archivo y
  cargarlo en otro dispositivo.

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

## Coto: configurar la clave (una sola vez)

Coto no usa la misma plataforma que las otras tiendas: su buscador es Constructor.io y
necesita una clave pública que el sitio de Coto manda desde el navegador. No es secreta,
pero hay que copiarla. Hacelo desde una PC:

1. Abrí https://www.cotodigital.com.ar en Chrome.
2. Apretá F12 (herramientas de desarrollador) y abrí la pestaña **Network** (Red).
3. Buscá cualquier producto en el sitio de Coto, por ejemplo "leche".
4. En la lista de pedidos filtrá por `cnstrc`. Hacé clic en uno que empiece con `search/`.
5. En la dirección (Request URL) vas a ver `...?key=key_XXXXXXXXXXXX&...`. Copiá lo que va
   después de `key=` hasta el siguiente `&`.

Cargala como variable de entorno llamada `COTO_KEY`:

- **Render:** en tu servicio, pestaña **Environment** → **Add Environment Variable**
  → nombre `COTO_KEY`, valor la clave → guardá (se vuelve a publicar solo).
- **Termux o PC:** `export COTO_KEY=key_XXXX` y después `python server.py`.
  En Windows: `set COTO_KEY=key_XXXX`.

Sin la clave, el resto de las tiendas funciona igual y Coto aparece como "Sin datos" con el motivo.

Opcional: `COTO_STORE_ID` cambia la sucursal de referencia para los precios de Coto
(por defecto `200`).

**Si Coto responde pero no aparecen precios o aparecen mal:** activá `DEBUG_COTO=1`,
abrí `/api/debug/coto?q=leche` y mandame lo que muestra para ajustar la lectura.

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
