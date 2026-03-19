"""
Airbnb Location Finder
Busca alojamientos de Airbnb cerca de unas coordenadas dadas usando la API de RapidAPI.
"""

import requests
import json
import argparse
from datetime import date, timedelta


RAPIDAPI_KEY = "TU_RAPIDAPI_KEY_AQUI"  # Reemplaza con tu API Key de RapidAPI


def buscar_airbnbs(lat: float, lon: float, radio_km: float = 5.0,
                   checkin: str = None, checkout: str = None,
                   adultos: int = 2, moneda: str = "USD"):
    """
    Busca Airbnbs cerca de las coordenadas dadas.

    Args:
        lat: Latitud del punto de búsqueda
        lon: Longitud del punto de búsqueda
        radio_km: Radio de búsqueda en kilómetros
        checkin: Fecha de entrada (YYYY-MM-DD), por defecto mañana
        checkout: Fecha de salida (YYYY-MM-DD), por defecto pasado mañana
        adultos: Número de adultos
        moneda: Moneda para precios (USD, MXN, EUR, etc.)

    Returns:
        Lista de alojamientos encontrados
    """
    if checkin is None:
        checkin = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    if checkout is None:
        checkout = (date.today() + timedelta(days=2)).strftime("%Y-%m-%d")

    url = "https://airbnb13.p.rapidapi.com/search-location"

    querystring = {
        "location": f"{lat},{lon}",
        "checkin": checkin,
        "checkout": checkout,
        "adults": str(adultos),
        "children": "0",
        "infants": "0",
        "pets": "0",
        "page": "1",
        "currency": moneda,
    }

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "airbnb13.p.rapidapi.com"
    }

    print(f"\n🔍 Buscando Airbnbs en ({lat}, {lon}) con radio de {radio_km} km...")
    print(f"   Fechas: {checkin} → {checkout} | Adultos: {adultos}\n")

    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.HTTPError as e:
        print(f"Error HTTP: {e}")
        print("Verifica que tu RAPIDAPI_KEY sea válida y tengas suscripción a airbnb13.")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Error de conexión: {e}")
        return []

    resultados = data.get("results", [])
    if not resultados:
        print("No se encontraron alojamientos para esas coordenadas.")
        return []

    return resultados


def filtrar_por_radio(resultados: list, lat: float, lon: float, radio_km: float) -> list:
    """Filtra resultados dentro del radio especificado usando distancia Haversine."""
    from math import radians, sin, cos, sqrt, atan2

    def haversine(lat1, lon1, lat2, lon2):
        R = 6371  # Radio de la Tierra en km
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
        return R * 2 * atan2(sqrt(a), sqrt(1 - a))

    filtrados = []
    for item in resultados:
        lat2 = item.get("lat") or item.get("coordinate", {}).get("lat")
        lon2 = item.get("lng") or item.get("coordinate", {}).get("lng")
        if lat2 and lon2:
            dist = haversine(lat, lon, float(lat2), float(lon2))
            if dist <= radio_km:
                item["_distancia_km"] = round(dist, 2)
                filtrados.append(item)
        else:
            filtrados.append(item)

    return sorted(filtrados, key=lambda x: x.get("_distancia_km", 999))


def mostrar_resultados(resultados: list, limite: int = 10):
    """Imprime los resultados de forma legible en la terminal."""
    print(f"{'='*60}")
    print(f"  Se encontraron {len(resultados)} alojamiento(s)")
    print(f"{'='*60}\n")

    for i, lugar in enumerate(resultados[:limite], 1):
        nombre = lugar.get("name") or lugar.get("title", "Sin nombre")
        tipo = lugar.get("type") or lugar.get("roomType", "N/A")
        precio = lugar.get("price", {})
        precio_noche = (
            precio.get("rate") or
            precio.get("total") or
            lugar.get("price") or
            "N/A"
        )
        rating = lugar.get("rating") or lugar.get("avgRating", "N/A")
        reviews = lugar.get("reviewsCount") or lugar.get("totalReviews", "N/A")
        url = lugar.get("url") or lugar.get("deeplink", "")
        distancia = lugar.get("_distancia_km", "N/A")

        print(f"[{i}] {nombre}")
        print(f"     Tipo       : {tipo}")
        print(f"     Precio/noche: {precio_noche}")
        print(f"     Rating     : {rating} ({reviews} reseñas)")
        if distancia != "N/A":
            print(f"     Distancia  : {distancia} km del punto buscado")
        if url:
            print(f"     URL        : {url}")
        print()


def guardar_json(resultados: list, archivo: str = "airbnbs_encontrados.json"):
    """Guarda los resultados en un archivo JSON."""
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print(f"Resultados guardados en '{archivo}'")


def main():
    parser = argparse.ArgumentParser(
        description="Busca Airbnbs cercanos a unas coordenadas geográficas"
    )
    parser.add_argument("lat", type=float, help="Latitud (ej: 19.4326)")
    parser.add_argument("lon", type=float, help="Longitud (ej: -99.1332)")
    parser.add_argument("--radio", type=float, default=5.0,
                        help="Radio de búsqueda en km (default: 5)")
    parser.add_argument("--checkin", type=str, default=None,
                        help="Fecha de entrada YYYY-MM-DD")
    parser.add_argument("--checkout", type=str, default=None,
                        help="Fecha de salida YYYY-MM-DD")
    parser.add_argument("--adultos", type=int, default=2,
                        help="Número de adultos (default: 2)")
    parser.add_argument("--moneda", type=str, default="USD",
                        help="Moneda (default: USD)")
    parser.add_argument("--limite", type=int, default=10,
                        help="Máximo de resultados a mostrar (default: 10)")
    parser.add_argument("--guardar", action="store_true",
                        help="Guarda los resultados en un archivo JSON")

    args = parser.parse_args()

    resultados = buscar_airbnbs(
        lat=args.lat,
        lon=args.lon,
        radio_km=args.radio,
        checkin=args.checkin,
        checkout=args.checkout,
        adultos=args.adultos,
        moneda=args.moneda
    )

    if resultados:
        resultados = filtrar_por_radio(resultados, args.lat, args.lon, args.radio)
        mostrar_resultados(resultados, limite=args.limite)
        if args.guardar:
            guardar_json(resultados)


if __name__ == "__main__":
    main()
