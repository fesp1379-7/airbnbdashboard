"""
Scraper de Airbnbs en Cuenca, Ecuador
Sin API key - usa web scraping directo a airbnb.com

Uso:
    python cuenca_airbnb_scraper.py
    python cuenca_airbnb_scraper.py --checkin 2026-04-10 --checkout 2026-04-15 --adultos 2
    python cuenca_airbnb_scraper.py --paginas 3 --guardar
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import argparse
from datetime import date, timedelta

# ── Configuración de Cuenca, Ecuador ────────────────────────────────────────
CUENCA_CONFIG = {
    "nombre": "Cuenca, Ecuador",
    "url_base": "https://www.airbnb.com/s/Cuenca--Ecuador/homes",
    "lat_ne": -2.8336,
    "lon_ne": -78.9452,
    "lat_sw": -2.9668,
    "lon_sw": -79.0606,
    "place_id": "ChIJiZmSf-NNeZIRbj88_kAD-tU",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-EC,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}


# ── Funciones de scraping ────────────────────────────────────────────────────

def construir_params(checkin: str, checkout: str, adultos: int, pagina: int) -> dict:
    cfg = CUENCA_CONFIG
    return {
        "checkin": checkin,
        "checkout": checkout,
        "adults": adultos,
        "children": 0,
        "infants": 0,
        "pets": 0,
        "place_id": cfg["place_id"],
        "ne_lat": cfg["lat_ne"],
        "ne_lng": cfg["lon_ne"],
        "sw_lat": cfg["lat_sw"],
        "sw_lng": cfg["lon_sw"],
        "zoom": 13,
        "search_type": "AUTOSUGGEST",
        "items_per_grid": 20,
        "page": pagina,
        "refinement_paths[]": "/homes",
        "tab_id": "home_tab",
        "query": "Cuenca, Ecuador",
        "flexible_trip_lengths[]": "one_week",
        "monthly_start_date": checkin[:7],
        "monthly_length": "3",
        "price_filter_input_type": "0",
        "channel": "EXPLORE",
        "date_picker_type": "calendar",
        "source": "structured_search_input_header",
        "search_mode": "regular_search",
    }


def fetch_pagina(session: requests.Session, checkin: str, checkout: str,
                 adultos: int, pagina: int) -> str | None:
    params = construir_params(checkin, checkout, adultos, pagina)
    try:
        resp = session.get(
            CUENCA_CONFIG["url_base"],
            headers=HEADERS,
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.HTTPError as e:
        print(f"  Error HTTP {e.response.status_code}: Airbnb puede estar bloqueando el scraper.")
        print("  Consejo: Usa una VPN o un proxy residencial.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"  Error de conexión: {e}")
        return None


# ── Extracción de datos del HTML ─────────────────────────────────────────────

def _buscar_en_dict(obj, claves_objetivo: set, resultados: list, profundidad=0):
    """Recorre recursivamente el JSON buscando objetos con las claves buscadas."""
    if profundidad > 25:
        return
    if isinstance(obj, dict):
        if claves_objetivo.issubset(obj.keys()):
            resultados.append(obj)
            return
        for v in obj.values():
            _buscar_en_dict(v, claves_objetivo, resultados, profundidad + 1)
    elif isinstance(obj, list):
        for item in obj:
            _buscar_en_dict(item, claves_objetivo, resultados, profundidad + 1)


def _extraer_de_next_data(html: str) -> list:
    """Intenta extraer listings del bloque __NEXT_DATA__ de Next.js."""
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not tag:
        return []
    try:
        data = json.loads(tag.string)
    except (json.JSONDecodeError, TypeError):
        return []

    # Busca objetos que parezcan listings (tienen 'name' y algún campo de precio)
    candidatos = []
    _buscar_en_dict(data, {"name", "id"}, candidatos)

    listings = []
    for c in candidatos:
        # Filtra objetos que parezcan alojamientos de verdad
        if not any(k in c for k in ("avgRating", "price", "roomTypeCategory", "pdpType")):
            continue
        listings.append(c)

    return listings


def _extraer_de_json_embebido(html: str) -> list:
    """Busca bloques JSON embebidos con regex como fallback."""
    patrones = [
        r'"listings"\s*:\s*(\[.+?\])\s*[,}]',
        r'"staysSearch"\s*:\s*\{[^}]*"results"\s*:\s*(\[.+?\])',
        r'"searchResults"\s*:\s*(\[.+?\])',
    ]
    for patron in patrones:
        match = re.search(patron, html, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    return []


def _extraer_de_html(html: str) -> list:
    """Extrae datos de las tarjetas HTML visibles como último recurso."""
    soup = BeautifulSoup(html, "lxml")
    listados = []

    # Airbnb renderiza tarjetas con itemprop o data-testid
    cards = soup.select("[itemprop='itemListElement']")
    if not cards:
        cards = soup.select("div[data-testid='card-container']")

    for card in cards:
        nombre_tag = card.select_one("[itemprop='name'], ._1y74zjx")
        precio_tag = card.select_one("[data-testid='price-and-discounted-price'], ._tyxjp1")
        url_tag = card.select_one("a[href*='/rooms/']")

        listados.append({
            "name": nombre_tag.get_text(strip=True) if nombre_tag else "Sin nombre",
            "precio_texto": precio_tag.get_text(strip=True) if precio_tag else "N/A",
            "url": "https://www.airbnb.com" + url_tag["href"] if url_tag else "N/A",
        })

    return listados


def extraer_listings(html: str) -> list:
    """Intenta los tres métodos de extracción en orden."""
    # Método 1: __NEXT_DATA__
    listings = _extraer_de_next_data(html)
    if listings:
        print(f"  [OK] Datos extraídos de __NEXT_DATA__ ({len(listings)} items)")
        return listings

    # Método 2: JSON embebido con regex
    listings = _extraer_de_json_embebido(html)
    if listings:
        print(f"  [OK] Datos extraídos de JSON embebido ({len(listings)} items)")
        return listings

    # Método 3: HTML directo
    listings = _extraer_de_html(html)
    if listings:
        print(f"  [OK] Datos extraídos del HTML ({len(listings)} items)")
        return listings

    print("  [!] No se pudieron extraer datos. Airbnb puede requerir JavaScript o estar bloqueando.")
    return []


# ── Normalización y presentación ─────────────────────────────────────────────

def normalizar(listing: dict) -> dict:
    """Convierte distintos formatos de listing a uno uniforme."""
    def get_precio(d):
        for key in ("price", "formattedPrice", "rate", "amount"):
            if key in d and d[key]:
                val = d[key]
                if isinstance(val, dict):
                    return get_precio(val)
                return str(val)
        return "N/A"

    listing_info = listing.get("listing", listing)

    nombre = (
        listing_info.get("name") or
        listing_info.get("title") or
        listing.get("name", "Sin nombre")
    )
    rating = (
        listing_info.get("avgRating") or
        listing_info.get("stars") or
        listing.get("avgRating", "N/A")
    )
    reviews = (
        listing_info.get("reviewsCount") or
        listing_info.get("numberOfGuests") or
        listing.get("reviewsCount", "N/A")
    )
    tipo = (
        listing_info.get("roomTypeCategory") or
        listing_info.get("pdpType") or
        listing_info.get("roomAndPropertyType") or
        "N/A"
    )

    precio_raw = listing.get("pricingQuote") or listing.get("price") or listing
    precio = get_precio(precio_raw)

    room_id = listing_info.get("id") or listing.get("id", "")
    url = (
        listing_info.get("contextualPictures", [{}])[0].get("url", "") or
        (f"https://www.airbnb.com/rooms/{room_id}" if room_id else listing.get("url", "N/A"))
    )
    if room_id and "airbnb.com" not in url:
        url = f"https://www.airbnb.com/rooms/{room_id}"

    return {
        "nombre": nombre,
        "tipo": tipo,
        "precio": precio,
        "rating": rating,
        "reviews": reviews,
        "url": url,
    }


def mostrar_resultados(todos_listings: list, checkin: str, checkout: str):
    noches = (
        date.fromisoformat(checkout) - date.fromisoformat(checkin)
    ).days

    print(f"\n{'='*65}")
    print(f"  Airbnbs en Cuenca, Ecuador")
    print(f"  {checkin} → {checkout}  ({noches} noche{'s' if noches != 1 else ''})")
    print(f"  Total encontrados: {len(todos_listings)}")
    print(f"{'='*65}\n")

    for i, raw in enumerate(todos_listings, 1):
        d = normalizar(raw)
        print(f"[{i:02d}] {d['nombre']}")
        print(f"      Tipo    : {d['tipo']}")
        print(f"      Precio  : {d['precio']}")
        estrellas = f"{d['rating']} estrellas" if d['rating'] != "N/A" else "Sin calificación"
        reviews = f"({d['reviews']} reseñas)" if d['reviews'] != "N/A" else ""
        print(f"      Rating  : {estrellas} {reviews}".rstrip())
        print(f"      Ver en  : {d['url']}")
        print()


def guardar_json(listings: list, archivo="cuenca_airbnbs.json"):
    normalizados = [normalizar(l) for l in listings]
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(normalizados, f, ensure_ascii=False, indent=2)
    print(f"Resultados guardados en '{archivo}'")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scraper de Airbnbs en Cuenca, Ecuador (sin API key)"
    )
    parser.add_argument("--checkin", default=None,
                        help="Fecha de entrada YYYY-MM-DD (default: próxima semana)")
    parser.add_argument("--checkout", default=None,
                        help="Fecha de salida YYYY-MM-DD (default: 3 días después)")
    parser.add_argument("--adultos", type=int, default=2,
                        help="Número de adultos (default: 2)")
    parser.add_argument("--paginas", type=int, default=1,
                        help="Páginas a scrapear (20 resultados por página, default: 1)")
    parser.add_argument("--guardar", action="store_true",
                        help="Guarda los resultados en cuenca_airbnbs.json")
    args = parser.parse_args()

    if args.checkin is None:
        args.checkin = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")
    if args.checkout is None:
        args.checkout = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")

    print(f"\nBuscando Airbnbs en {CUENCA_CONFIG['nombre']}...")
    print(f"Fechas: {args.checkin} → {args.checkout} | Adultos: {args.adultos}")

    session = requests.Session()
    # Obtener cookies visitando la home primero
    try:
        session.get("https://www.airbnb.com", headers=HEADERS, timeout=15)
        time.sleep(1.5)
    except requests.exceptions.RequestException:
        pass

    todos = []
    for pagina in range(1, args.paginas + 1):
        print(f"\nPágina {pagina}/{args.paginas}...")
        html = fetch_pagina(session, args.checkin, args.checkout, args.adultos, pagina)
        if not html:
            break
        listings = extraer_listings(html)
        todos.extend(listings)
        if pagina < args.paginas:
            time.sleep(2)  # Pausa para no ser bloqueado

    if todos:
        mostrar_resultados(todos, args.checkin, args.checkout)
        if args.guardar:
            guardar_json(todos)
    else:
        print("\nNo se encontraron resultados.")
        print("\nPosibles causas:")
        print("  1. Airbnb detectó el scraper (prueba con una VPN)")
        print("  2. No hay disponibilidad en esas fechas")
        print("  3. Cambió la estructura del HTML")
        print(f"\nPuedes buscar manualmente en:")
        print(f"  https://www.airbnb.com/s/Cuenca--Ecuador/homes"
              f"?checkin={args.checkin}&checkout={args.checkout}&adults={args.adultos}")


if __name__ == "__main__":
    main()
