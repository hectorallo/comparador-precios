"""Comparador de precios de supermercados (Argentina).

Consulta en paralelo las tiendas basadas en VTEX (Carrefour, Jumbo, Disco, Vea,
Día, ChangoMás) por código de barras (EAN) o por nombre, y agrupa los resultados
por producto para poder comparar.

Uso:  python server.py   ->  http://localhost:8000
"""
import concurrent.futures as cf
import re
import time
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_from_directory

# Para agregar otra tienda VTEX, sumá una línea acá.
STORES = {
    "Carrefour": "https://www.carrefour.com.ar",
    "Jumbo": "https://www.jumbo.com.ar",
    "Disco": "https://www.disco.com.ar",
    "Vea": "https://www.vea.com.ar",
    "Día": "https://diaonline.supermercadosdia.com.ar",
    "ChangoMás": "https://www.masonline.com.ar",
}

TIMEOUT = 10          # segundos por tienda
CACHE_TTL = 600       # 10 minutos
MAX_PER_STORE = 8     # resultados por tienda en búsqueda por nombre

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; comparador-precios/1.0)",
    "Accept": "application/json",
})

app = Flask(__name__, static_folder="static")
_cache = {}


# ---------- utilidades ----------

def is_ean(q: str) -> bool:
    """True si parece un código de barras (EAN-8/UPC-12/EAN-13/GTIN-14)."""
    return q.isdigit() and len(q) in (8, 12, 13, 14)


UNIT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kgs?|grs?|g|lts?|l|ml|cc)\b", re.I)


def unit_price(name: str, price: float):
    """Precio por kg o por litro, estimado desde el nombre (ej. 'Leche 1 L')."""
    m = UNIT_RE.search(name or "")
    if not m or not price:
        return None
    qty = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    if unit.startswith("k"):
        base, qty = "kg", qty
    elif unit.startswith("g"):
        base, qty = "kg", qty / 1000
    elif unit in ("ml", "cc"):
        base, qty = "L", qty / 1000
    else:
        base, qty = "L", qty
    if qty <= 0:
        return None
    return {"value": round(price / qty, 2), "per": base}


# ---------- consulta a cada tienda ----------

def parse_products(store, base, data, wanted_ean=None):
    out = []
    for p in data or []:
        for item in p.get("items", []):
            ean = (item.get("ean") or "").strip() or None
            if wanted_ean and ean and ean != wanted_ean:
                continue
            sellers = item.get("sellers") or []
            offer = (sellers[0].get("commertialOffer") or {}) if sellers else {}
            price = offer.get("Price") or 0
            if not price:
                continue
            images = item.get("images") or []
            link = p.get("link") or ""
            if link.startswith("/"):
                link = base + link
            elif not link and p.get("linkText"):
                link = f"{base}/{p['linkText']}/p"
            name = p.get("productName") or item.get("name") or ""
            list_price = offer.get("ListPrice") or price
            out.append({
                "store": store,
                "ean": ean,
                "name": name,
                "brand": p.get("brand"),
                "image": images[0].get("imageUrl") if images else None,
                "price": round(float(price), 2),
                "list_price": round(float(list_price), 2),
                "in_stock": (offer.get("AvailableQuantity") or 0) > 0,
                "url": link or base,
                "unit_price": unit_price(name, float(price)),
            })
            break  # una variante por producto alcanza
    return out


def fetch_store(store, base, q, by_ean):
    url = f"{base}/api/catalog_system/pub/products/search"
    if by_ean:
        params = {"fq": f"alternateIds_Ean:{q}"}
    else:
        params = {"ft": q, "_from": 0, "_to": MAX_PER_STORE - 1}
    r = SESSION.get(url, params=params, timeout=TIMEOUT)
    if r.status_code not in (200, 206):
        raise RuntimeError(f"HTTP {r.status_code}")
    results = parse_products(store, base, r.json(), q if by_ean else None)
    return results


def group_products(results):
    """Agrupa ofertas del mismo producto (mismo EAN) de distintas tiendas."""
    groups = {}
    for r in results:
        key = r["ean"] or f"{r['store']}::{r['name']}"
        g = groups.setdefault(key, {
            "ean": r["ean"], "name": r["name"], "brand": r["brand"],
            "image": r["image"], "offers": [],
        })
        if not g["image"] and r["image"]:
            g["image"] = r["image"]
        g["offers"].append({k: r[k] for k in (
            "store", "price", "list_price", "in_stock", "url", "unit_price")})
    out = []
    for g in groups.values():
        g["offers"].sort(key=lambda o: (not o["in_stock"], o["price"]))
        in_stock = [o for o in g["offers"] if o["in_stock"]]
        best = in_stock[0] if in_stock else None
        worst = in_stock[-1] if in_stock else None
        g["best_store"] = best["store"] if best else None
        g["savings_pct"] = (
            round((1 - best["price"] / worst["price"]) * 100, 1)
            if best and worst and len(in_stock) > 1 and worst["price"] else 0
        )
        out.append(g)
    # primero los que están en más tiendas, luego por precio más bajo
    out.sort(key=lambda g: (-len(g["offers"]), g["offers"][0]["price"]))
    return out


def search(q):
    by_ean = is_ean(q)
    key = (q.lower(), by_ean)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]

    stores_status, results = [], []
    with cf.ThreadPoolExecutor(max_workers=len(STORES)) as ex:
        futs = {ex.submit(fetch_store, s, b, q, by_ean): s for s, b in STORES.items()}
        for fut in cf.as_completed(futs):
            s = futs[fut]
            try:
                res = fut.result()
                results.extend(res)
                stores_status.append({"store": s, "ok": True, "count": len(res)})
            except Exception as e:  # una tienda caída no rompe el resto
                stores_status.append({"store": s, "ok": False, "error": str(e)[:120]})
    stores_status.sort(key=lambda s: s["store"])

    payload = {
        "query": q,
        "mode": "ean" if by_ean else "name",
        "products": group_products(results),
        "stores": stores_status,
    }
    # no cachear si falló todo (probablemente un problema de red)
    if any(s["ok"] for s in stores_status):
        _cache[key] = (time.time(), payload)
    return payload


# ---------- rutas ----------

@app.get("/api/search")
def api_search():
    q = re.sub(r"\s+", " ", request.args.get("q", "")).strip()
    if len(q) < 2:
        return jsonify(error="Escribí al menos 2 caracteres o un código de barras."), 400
    return jsonify(search(q))


@app.get("/")
def index():
    return send_from_directory(Path(app.static_folder), "index.html")


if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)
