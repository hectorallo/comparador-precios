"""Comparador de precios de supermercados (Argentina).

Consulta en paralelo:
  - Tiendas VTEX (Carrefour, Jumbo, Disco, Vea, Día, ChangoMás), por código de
    barras (EAN) o por nombre.
  - Coto Digital, que usa el buscador Constructor.io (necesita la variable de
    entorno COTO_KEY, ver README).

Agrupa los resultados por producto (mismo EAN) para poder comparar.

Uso:  python server.py   ->  http://localhost:8000
"""
import concurrent.futures as cf
import json
import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import requests
from flask import Flask, jsonify, request, send_from_directory

# ---------- configuración ----------

# Tiendas VTEX. Para agregar otra, sumá una línea acá.
STORES = {
    "Carrefour": "https://www.carrefour.com.ar",
    "Jumbo": "https://www.jumbo.com.ar",
    "Disco": "https://www.disco.com.ar",
    "Vea": "https://www.vea.com.ar",
    "Día": "https://diaonline.supermercadosdia.com.ar",
    "ChangoMás": "https://www.masonline.com.ar",
}

# Coto (Constructor.io). La clave es la clave pública que el sitio de Coto
# manda desde el navegador; ver README para encontrarla.
COTO_KEY = os.environ.get("COTO_KEY", "").strip()
COTO_STORE_ID = os.environ.get("COTO_STORE_ID", "200").strip()  # sucursal de referencia
COTO_API = "https://ac.cnstrc.com"
COTO_SITE = "https://www.cotodigital.com.ar/sitios/cdigi/productos/"
COTO_CLIENT_ID = str(uuid.uuid4())

TIMEOUT = 10          # segundos por tienda
CACHE_TTL = 600       # 10 minutos
MAX_PER_STORE = 8     # resultados por tienda en búsqueda por nombre

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; comparador-precios/1.1)",
    "Accept": "application/json",
})

app = Flask(__name__, static_folder="static")
_cache = {}


# ---------- utilidades ----------

def is_ean(q: str) -> bool:
    """True si parece un código de barras (EAN-8/UPC-12/EAN-13/GTIN-14)."""
    return q.isdigit() and len(q) in (8, 12, 13, 14)


def canon(ean):
    """Código sin ceros a la izquierda: EAN-13 y GTIN-14 del mismo producto coinciden."""
    return (ean or "").strip().lstrip("0") or None


UNIT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kgs?|grs?|g|lts?|l|ml|cc)\b", re.I)


def unit_price(name: str, price: float):
    """Precio por kg o por litro, estimado desde el nombre (ej. 'Leche 1 L')."""
    m = UNIT_RE.search(name or "")
    if not m or not price:
        return None
    qty = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    if unit.startswith("k"):
        base = "kg"
    elif unit.startswith("g"):
        base, qty = "kg", qty / 1000
    elif unit in ("ml", "cc"):
        base, qty = "L", qty / 1000
    else:
        base = "L"
    if qty <= 0:
        return None
    return {"value": round(price / qty, 2), "per": base}


def _num(v):
    """Convierte 1234.5, '1234.5' o '1.234,50' en float; None si no se puede."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = re.sub(r"[^\d.,-]", "", v)
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _as_list(v):
    """Constructor a veces devuelve listas/objetos como texto JSON."""
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return []
    if isinstance(v, dict):
        return [v]
    return v if isinstance(v, list) else []


# ---------- tiendas VTEX ----------

def parse_products(store, base, data, wanted_ean=None):
    out = []
    for p in data or []:
        for item in p.get("items", []):
            ean = (item.get("ean") or "").strip() or None
            if wanted_ean and ean and canon(ean) != canon(wanted_ean):
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
                "promo": None,
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
        raise RuntimeError(f"la tienda respondió con error {r.status_code}")
    return parse_products(store, base, r.json(), q if by_ean else None)


# ---------- Coto (Constructor.io) ----------

def _coto_request(term, per_page):
    if not COTO_KEY:
        raise RuntimeError("falta configurar COTO_KEY (ver README)")
    params = {
        "key": COTO_KEY,
        "i": COTO_CLIENT_ID,
        "s": 1,
        "c": "ciojs-client-2.35.2",
        "page": 1,
        "num_results_per_page": per_page,
    }
    r = SESSION.get(
        f"{COTO_API}/search/{quote(term, safe='')}",
        params=params,
        headers={"Referer": "https://www.cotodigital.com.ar/", "Origin": "https://www.cotodigital.com.ar"},
        timeout=TIMEOUT,
    )
    if r.status_code in (401, 403):
        raise RuntimeError("Coto rechazó la clave; revisá COTO_KEY")
    if r.status_code != 200:
        raise RuntimeError(f"Coto respondió con error {r.status_code}")
    return (r.json().get("response") or {}).get("results") or []


def _coto_price(data):
    """Precio de lista en la sucursal de referencia."""
    entries = [e for e in _as_list(data.get("price")) if isinstance(e, dict)]
    chosen = next((e for e in entries if str(e.get("store")) == COTO_STORE_ID), None)
    if chosen is None and entries:
        chosen = entries[0]
    if chosen:
        for k in ("listPrice", "list_price", "price_list"):
            v = _num(chosen.get(k))
            if v:
                return v
    return _num(data.get("product_list_price"))


def _coto_available(data):
    val = data.get("store_availability")
    if isinstance(val, bool):
        return val
    val = _as_list(val) if not isinstance(val, list) else val
    if val:
        return COTO_STORE_ID in json.dumps(val)
    return True  # sin dato: asumimos disponible


def _coto_promo(data):
    for d in _as_list(data.get("discounts")):
        if isinstance(d, dict):
            text = d.get("discountText") or d.get("discount_text")
            if text:
                return str(text)
    return None


def parse_coto(results, wanted_ean=None):
    out = []
    for item in results:
        data = item.get("data") or {}
        ean = (data.get("product_main_ean") or "").strip() or None
        if wanted_ean and canon(ean) != canon(wanted_ean):
            continue
        price = _coto_price(data)
        if not price:
            continue
        name = (item.get("value") or data.get("sku_display_name")
                or data.get("sku_description") or "").strip()
        url = data.get("url") or ""
        url = url if url.startswith("http") else COTO_SITE + url.lstrip("/")
        out.append({
            "store": "Coto",
            "ean": ean,
            "name": name,
            "brand": data.get("product_brand"),
            "image": data.get("product_large_image_url") or data.get("image_url"),
            "price": round(price, 2),
            "list_price": round(price, 2),
            "in_stock": _coto_available(data),
            "url": url or COTO_SITE,
            "promo": _coto_promo(data),
            "unit_price": unit_price(name, price),
        })
    return out


def fetch_coto(q, by_ean):
    if not by_ean:
        return parse_coto(_coto_request(q, MAX_PER_STORE))
    # Coto guarda los códigos como GTIN-14 (con ceros a la izquierda)
    for term in dict.fromkeys([q, q.zfill(14)]):
        found = parse_coto(_coto_request(term, 20), wanted_ean=q)
        if found:
            return found[:1]
    return []


# ---------- agrupar y buscar ----------

def group_products(results):
    """Agrupa ofertas del mismo producto (mismo EAN) de distintas tiendas."""
    groups = {}
    for r in results:
        key = canon(r["ean"]) or f"{r['store']}::{r['name']}"
        g = groups.setdefault(key, {
            "ean": r["ean"], "name": r["name"], "brand": r["brand"],
            "image": r["image"], "offers": [],
        })
        if not g["image"] and r["image"]:
            g["image"] = r["image"]
        g["offers"].append({k: r[k] for k in (
            "store", "price", "list_price", "in_stock", "url", "promo", "unit_price")})
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
    out.sort(key=lambda g: (-len(g["offers"]), g["offers"][0]["price"]))
    return out


def search(q):
    by_ean = is_ean(q)
    key = (q.lower(), by_ean)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]

    jobs = {s: (fetch_store, (s, b, q, by_ean)) for s, b in STORES.items()}
    jobs["Coto"] = (lambda: fetch_coto(q, by_ean), ())

    stores_status, results = [], []
    with cf.ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        futs = {ex.submit(fn, *args): s for s, (fn, args) in jobs.items()}
        for fut in cf.as_completed(futs):
            s = futs[fut]
            try:
                res = fut.result()
                results.extend(res)
                stores_status.append({"store": s, "ok": True, "count": len(res)})
            except Exception as e:  # una tienda caída no rompe el resto
                stores_status.append({"store": s, "ok": False, "error": str(e)[:140]})
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
        return jsonify(error="Escribí al menos 2 letras o un código de barras."), 400
    return jsonify(search(q))


@app.get("/api/debug/coto")
def api_debug_coto():
    """Muestra la respuesta cruda de Coto para ajustar el parseo. Solo con DEBUG_COTO=1."""
    if os.environ.get("DEBUG_COTO") != "1":
        return jsonify(error="desactivado"), 404
    q = request.args.get("q", "leche")
    try:
        raw = _coto_request(q, 2)
    except Exception as e:
        return jsonify(error=str(e)), 502
    return jsonify(results=raw[:2])


@app.get("/")
def index():
    return send_from_directory(Path(app.static_folder), "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)
