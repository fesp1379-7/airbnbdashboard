"""
TripAdvisor Scraper - Hotel Oro Verde Cuenca, Ecuador
Extrae masivamente: info del hotel, TODAS las reseñas, amenidades y calificaciones.

Uso:
    python tripadvisor_oro_verde.py
    python tripadvisor_oro_verde.py --max-paginas 50 --idioma es
    python tripadvisor_oro_verde.py --formato csv json
    python tripadvisor_oro_verde.py --pausas 3
"""

import requests
from bs4 import BeautifulSoup
import json
import csv
import re
import time
import random
import argparse
from datetime import datetime
from pathlib import Path

# ── URL del Hotel Oro Verde en Cuenca ──────────────────────────────────────
HOTEL_URL = (
    "https://www.tripadvisor.com/Hotel_Review-g294518-d300958-"
    "Reviews-Oro_Verde_Hotel_Cuenca-Cuenca_Azuay_Province.html"
)
HOTEL_URL_ES = (
    "https://www.tripadvisor.com/Hotel_Review-g294518-d300958-"
    "Reviews-Oro_Verde_Hotel_Cuenca-Cuenca_Azuay_Province.html"
)
BASE_URL = "https://www.tripadvisor.com"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
]


def get_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-EC,es;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Referer": "https://www.tripadvisor.com/",
    }


# ── HTTP Session ─────────────────────────────────────────────────────────────

def crear_session() -> requests.Session:
    session = requests.Session()
    # Visita la home para obtener cookies legítimas
    try:
        session.get(BASE_URL, headers=get_headers(), timeout=15)
        time.sleep(random.uniform(1.5, 3.0))
    except requests.exceptions.RequestException:
        pass
    return session


def fetch(session: requests.Session, url: str, pausa: float = 2.0) -> BeautifulSoup | None:
    for intento in range(3):
        try:
            resp = session.get(url, headers=get_headers(), timeout=20)
            if resp.status_code == 429:
                espera = (intento + 1) * 10
                print(f"    Rate limited. Esperando {espera}s...")
                time.sleep(espera)
                continue
            if resp.status_code == 403:
                print("    Bloqueado (403). TripAdvisor detectó el scraper.")
                print("    Consejo: Usa una VPN o espera unos minutos.")
                return None
            resp.raise_for_status()
            time.sleep(pausa + random.uniform(0.5, 1.5))
            return BeautifulSoup(resp.text, "lxml")
        except requests.exceptions.RequestException as e:
            print(f"    Error (intento {intento+1}/3): {e}")
            time.sleep(5 * (intento + 1))
    return None


# ── Extracción: Info General del Hotel ───────────────────────────────────────

def extraer_info_hotel(soup: BeautifulSoup) -> dict:
    info = {}

    # Nombre
    for sel in ["h1[data-automation='mainH1']", "h1.QdLfr", "h1"]:
        tag = soup.select_one(sel)
        if tag:
            info["nombre"] = tag.get_text(strip=True)
            break

    # Rating general (1-5)
    for sel in ["span.uwJeR", "span[data-automation='bubbleRatingValue']",
                "span.bvcwU", "div.biGQs span"]:
        tag = soup.select_one(sel)
        if tag:
            texto = tag.get_text(strip=True)
            match = re.search(r"(\d[\.,]\d)", texto)
            if match:
                info["rating_general"] = match.group(1).replace(",", ".")
                break

    # Total de reseñas
    for sel in ["span[data-automation='reviewCount']", "span.IlqaV",
                "a.widCB", "span.hkxYU"]:
        tag = soup.select_one(sel)
        if tag:
            texto = tag.get_text(strip=True)
            match = re.search(r"([\d,\.]+)", texto)
            if match:
                info["total_resenas"] = match.group(1).replace(",", "").replace(".", "")
                break

    # Dirección
    for sel in ["span[data-automation='address']", "div.biGQs.ogfYpFl",
                "a.AYHFM", "span.fHvkI"]:
        tag = soup.select_one(sel)
        if tag:
            info["direccion"] = tag.get_text(strip=True)
            break

    # Teléfono
    phone_tag = soup.find(string=re.compile(r"\+593|593"))
    if phone_tag:
        match = re.search(r"(\+?593[\s\-\d]+)", str(phone_tag))
        if match:
            info["telefono"] = match.group(1).strip()

    # Precio promedio por noche
    for sel in ["div[data-automation='avgPricePerNight']", "span.clyBe",
                "div.uwJeR span"]:
        tag = soup.select_one(sel)
        if tag:
            info["precio_promedio"] = tag.get_text(strip=True)
            break

    # Subcalificaciones (Limpieza, Servicio, etc.)
    subcals = {}
    for fila in soup.select("div.DzMcu, div.WdWxQ, li.slim_ranking_bar_item"):
        label = fila.select_one("span.McqKF, div.biGQs")
        valor = fila.select_one("span.ui_bubble_rating, span.McqKF + span")
        if label and valor:
            key = label.get_text(strip=True).lower().replace(" ", "_")
            val = valor.get("class", [])
            # Clase bubble_XX donde XX/10 = rating
            for cls in val:
                m = re.search(r"bubble_(\d+)", cls)
                if m:
                    subcals[key] = int(m.group(1)) / 10
    if subcals:
        info["subcalificaciones"] = subcals

    # Amenidades
    amenidades = []
    for tag in soup.select("div.OsCbb span, div.ibkCM div.biGQs, span.yplav"):
        texto = tag.get_text(strip=True)
        if texto and len(texto) > 2:
            amenidades.append(texto)
    if amenidades:
        info["amenidades"] = list(dict.fromkeys(amenidades))  # deduplica

    # Fecha de extracción
    info["extraido_en"] = datetime.now().isoformat()

    return info


# ── Extracción: URL de páginas de reseñas ────────────────────────────────────

def construir_url_pagina(pagina: int) -> str:
    """
    TripAdvisor pagina reseñas de 10 en 10.
    Página 1 → Reviews-or0-...
    Página 2 → Reviews-or10-...
    Página N → Reviews-or{(N-1)*10}-...
    """
    offset = (pagina - 1) * 10
    if offset == 0:
        return HOTEL_URL
    base = HOTEL_URL.replace("Reviews-", f"Reviews-or{offset}-")
    return base


def obtener_total_paginas(soup: BeautifulSoup) -> int:
    """Calcula el total de páginas de reseñas."""
    # Busca el total de reseñas
    for sel in ["span[data-automation='reviewCount']", "a.widCB",
                "span.hkxYU", "span.IlqaV"]:
        tag = soup.select_one(sel)
        if tag:
            match = re.search(r"([\d,\.]+)", tag.get_text())
            if match:
                total = int(match.group(1).replace(",", "").replace(".", ""))
                return max(1, -(-total // 10))  # ceil division

    # Busca paginación directa
    pag_tags = soup.select("a[data-page-number], span.pageNum")
    numeros = []
    for t in pag_tags:
        txt = t.get_text(strip=True)
        if txt.isdigit():
            numeros.append(int(txt))
    if numeros:
        return max(numeros)

    return 1


# ── Extracción: Reseñas ───────────────────────────────────────────────────────

def extraer_resenas(soup: BeautifulSoup) -> list[dict]:
    resenas = []

    # Selector principal de contenedor de reseña
    contenedores = soup.select(
        "div[data-automation='reviewCard'], "
        "div.YibKl, "
        "div.review-container, "
        "div._c"
    )

    for contenedor in contenedores:
        resena = {}

        # ── Autor ──
        for sel in ["a.BMQDV span", "span.mdemT", "span.ui_header_link",
                    "a[href*='Profile']", "div.info_text div"]:
            tag = contenedor.select_one(sel)
            if tag:
                resena["autor"] = tag.get_text(strip=True)
                break

        # ── Ubicación del autor ──
        for sel in ["span.dGnXh", "div.sm\\:hidden span", "span.default"]:
            tag = contenedor.select_one(sel)
            if tag:
                texto = tag.get_text(strip=True)
                if texto and texto != resena.get("autor"):
                    resena["ubicacion_autor"] = texto
                    break

        # ── Fecha ──
        for sel in ["span[data-automation='reviewDate']", "span.teHYY",
                    "span.ratingDate", "div.prw_reviews_stay_date_hsx"]:
            tag = contenedor.select_one(sel)
            if tag:
                texto = tag.get("title") or tag.get_text(strip=True)
                resena["fecha"] = texto
                break

        # ── Rating (burbujas 1-5) ──
        for sel in ["svg title", "span.ui_bubble_rating", "div.Hlmiy span"]:
            tag = contenedor.select_one(sel)
            if tag:
                texto = tag.get_text(strip=True)
                m = re.search(r"(\d[\.,]?\d?)\s*(de\s*5|out of 5|/5)?", texto)
                if m:
                    resena["rating"] = m.group(1).replace(",", ".")
                    break
        # Fallback: clase bubble_XX
        if "rating" not in resena:
            bubble = contenedor.select_one("[class*='bubble_']")
            if bubble:
                for cls in bubble.get("class", []):
                    m = re.search(r"bubble_(\d+)", cls)
                    if m:
                        resena["rating"] = str(int(m.group(1)) / 10)
                        break

        # ── Título ──
        for sel in ["a.Qwuub", "span[data-automation='reviewTitle']",
                    "span.noQuotes", "a.title"]:
            tag = contenedor.select_one(sel)
            if tag:
                resena["titulo"] = tag.get_text(strip=True)
                break

        # ── Texto de la reseña ──
        for sel in ["div[data-automation='reviewText'] span",
                    "div.biGQs._P span", "q.QewHA span",
                    "p.partial_entry", "div.prw_reviews_text_summary_hsx"]:
            tag = contenedor.select_one(sel)
            if tag:
                texto = tag.get_text(strip=True)
                if len(texto) > 10:
                    resena["texto"] = texto
                    break

        # ── Tipo de viaje ──
        for sel in ["span[data-automation='travelType']", "span.TDKzw",
                    "div.recommend-titleInline"]:
            tag = contenedor.select_one(sel)
            if tag:
                resena["tipo_viaje"] = tag.get_text(strip=True)
                break

        # ── Votos útiles ──
        for sel in ["span[data-automation='helpfulVotes']", "span.oETBfkHU"]:
            tag = contenedor.select_one(sel)
            if tag:
                m = re.search(r"\d+", tag.get_text())
                if m:
                    resena["votos_utiles"] = int(m.group())
                break

        # ── Fecha de estadía ──
        for sel in ["span[data-automation='stayDate']", "div.stay_date_hsx"]:
            tag = contenedor.select_one(sel)
            if tag:
                resena["fecha_estadia"] = tag.get_text(strip=True)
                break

        # Solo guarda si tiene al menos título o texto
        if resena.get("titulo") or resena.get("texto"):
            resenas.append(resena)

    return resenas


# ── Guardado de datos ─────────────────────────────────────────────────────────

def guardar_json(info_hotel: dict, resenas: list, archivo: str):
    datos = {
        "hotel": info_hotel,
        "total_resenas_extraidas": len(resenas),
        "resenas": resenas,
    }
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    print(f"  JSON guardado: {archivo}")


def guardar_csv(resenas: list, archivo: str):
    if not resenas:
        return
    campos = [
        "autor", "ubicacion_autor", "fecha", "fecha_estadia",
        "rating", "tipo_viaje", "titulo", "texto", "votos_utiles"
    ]
    with open(archivo, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(resenas)
    print(f"  CSV guardado: {archivo}")


def guardar_info_csv(info_hotel: dict, archivo: str):
    with open(archivo, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Campo", "Valor"])
        for k, v in info_hotel.items():
            if isinstance(v, dict):
                for k2, v2 in v.items():
                    writer.writerow([f"{k}.{k2}", v2])
            elif isinstance(v, list):
                writer.writerow([k, " | ".join(str(i) for i in v)])
            else:
                writer.writerow([k, v])
    print(f"  CSV hotel guardado: {archivo}")


# ── Reporte en pantalla ────────────────────────────────────────────────────────

def mostrar_resumen(info_hotel: dict, resenas: list):
    print(f"\n{'='*65}")
    print(f"  {info_hotel.get('nombre', 'Hotel Oro Verde Cuenca')}")
    print(f"  TripAdvisor - Cuenca, Ecuador")
    print(f"{'='*65}")
    print(f"  Rating general  : {info_hotel.get('rating_general', 'N/A')} / 5.0")
    print(f"  Total reseñas   : {info_hotel.get('total_resenas', 'N/A')}")
    print(f"  Dirección       : {info_hotel.get('direccion', 'N/A')}")
    print(f"  Teléfono        : {info_hotel.get('telefono', 'N/A')}")
    print(f"  Precio promedio : {info_hotel.get('precio_promedio', 'N/A')}")

    subcals = info_hotel.get("subcalificaciones", {})
    if subcals:
        print(f"\n  Subcalificaciones:")
        for k, v in subcals.items():
            print(f"    {k:<20}: {v}")

    amenidades = info_hotel.get("amenidades", [])
    if amenidades:
        print(f"\n  Amenidades ({len(amenidades)}):")
        for a in amenidades[:15]:
            print(f"    • {a}")
        if len(amenidades) > 15:
            print(f"    ... y {len(amenidades) - 15} más")

    print(f"\n  Reseñas extraídas: {len(resenas)}")
    if resenas:
        print(f"\n  Últimas 3 reseñas:")
        for r in resenas[:3]:
            print(f"\n  [{r.get('rating','?')}/5] {r.get('titulo','Sin título')}")
            print(f"  Autor   : {r.get('autor','N/A')} ({r.get('ubicacion_autor','?')})")
            print(f"  Fecha   : {r.get('fecha','N/A')}")
            texto = r.get("texto", "")
            if texto:
                print(f"  Reseña  : {texto[:200]}{'...' if len(texto)>200 else ''}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scraper masivo TripAdvisor - Hotel Oro Verde Cuenca, Ecuador"
    )
    parser.add_argument("--max-paginas", type=int, default=0,
                        help="Máximo de páginas (0 = todas, cada página = 10 reseñas)")
    parser.add_argument("--formato", nargs="+", choices=["json", "csv"], default=["json", "csv"],
                        help="Formato(s) de salida (default: json csv)")
    parser.add_argument("--pausas", type=float, default=2.5,
                        help="Segundos de pausa entre páginas (default: 2.5)")
    parser.add_argument("--salida", type=str, default="oro_verde_cuenca",
                        help="Prefijo del archivo de salida (default: oro_verde_cuenca)")
    args = parser.parse_args()

    print("\n" + "="*65)
    print("  TripAdvisor Scraper - Hotel Oro Verde Cuenca, Ecuador")
    print("="*65)
    print(f"  URL: {HOTEL_URL}")

    session = crear_session()

    # ── 1. Página principal: info del hotel ──
    print("\n[1/3] Obteniendo información general del hotel...")
    soup = fetch(session, HOTEL_URL, pausa=args.pausas)
    if not soup:
        print("\nNo se pudo conectar a TripAdvisor.")
        print(f"Visita manualmente: {HOTEL_URL}")
        return

    info_hotel = extraer_info_hotel(soup)
    total_paginas = obtener_total_paginas(soup)

    print(f"  Hotel: {info_hotel.get('nombre', 'N/A')}")
    print(f"  Rating: {info_hotel.get('rating_general', 'N/A')}")
    print(f"  Total reseñas en TripAdvisor: {info_hotel.get('total_resenas', '?')}")
    print(f"  Páginas de reseñas detectadas: {total_paginas}")

    if args.max_paginas > 0:
        total_paginas = min(total_paginas, args.max_paginas)
        print(f"  Páginas a scrapear (límite): {total_paginas}")

    # ── 2. Scrapear todas las páginas de reseñas ──
    print(f"\n[2/3] Extrayendo reseñas ({total_paginas} páginas × 10 reseñas)...")
    todas_resenas = []

    # Reseñas de la página 1 ya descargada
    resenas_p1 = extraer_resenas(soup)
    todas_resenas.extend(resenas_p1)
    print(f"  Página 1/{total_paginas}: {len(resenas_p1)} reseñas")

    # Páginas restantes
    for pagina in range(2, total_paginas + 1):
        url = construir_url_pagina(pagina)
        soup_p = fetch(session, url, pausa=args.pausas)
        if not soup_p:
            print(f"  Página {pagina}: Error al obtener. Continuando...")
            continue
        resenas_p = extraer_resenas(soup_p)
        todas_resenas.extend(resenas_p)
        print(f"  Página {pagina}/{total_paginas}: {len(resenas_p)} reseñas "
              f"(total acumulado: {len(todas_resenas)})")

        # Pausa aleatoria extra cada 10 páginas para evitar bloqueos
        if pagina % 10 == 0:
            extra = random.uniform(5, 10)
            print(f"  Pausa larga ({extra:.1f}s) para evitar bloqueo...")
            time.sleep(extra)

    # ── 3. Guardar resultados ──
    print(f"\n[3/3] Guardando {len(todas_resenas)} reseñas...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if "json" in args.formato:
        guardar_json(info_hotel, todas_resenas, f"{args.salida}_{ts}.json")
    if "csv" in args.formato:
        guardar_csv(todas_resenas, f"{args.salida}_resenas_{ts}.csv")
        guardar_info_csv(info_hotel, f"{args.salida}_hotel_{ts}.csv")

    # ── Resumen final ──
    mostrar_resumen(info_hotel, todas_resenas)
    print(f"Extracción completa. {len(todas_resenas)} reseñas guardadas.")


if __name__ == "__main__":
    main()
