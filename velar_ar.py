"""Modelo VEL-Ar v2.0 (IGN Argentina / Ohio State University) para llevar coordenadas
geodesicas de una epoca a otra sobre el territorio argentino, incluyendo los saltos
cosismicos y la relajacion postsismica logaritmica de los terremotos de Maule (2010.159)
e Illapel (2015.710). Marco oficial: POSGAR07 (epoca 2006.632).

Modulo puro, sin dependencias de QGIS/PyQt, para poder probarlo con Python estandar
(test_core.py / test_velar.py) sin necesidad de arrancar QGIS -- mismo patron que vemos.py.

Fuente del algoritmo: reproducido ejecutando el programa oficial "velar"
(https://github.com/fjfernandezc/VEL-Ar), NO transcrito literalmente del manual (la formula
de la seccion 3.1.1 del manual, basada en una funcion escalon H(t - tj), no reproduce al
programa cuando ambas epocas (ti y tf) son posteriores al sismo: en ese caso el aporte
postsismico sigue siendo la DIFERENCIA de trayectorias entre ambas epocas, no cero).
Validado contra 120 puntos aleatorios + 708 puntos de control del territorio continental
argentino: diferencia maxima 1.33 cm, p99 0.77 cm, mediana 0.023 cm frente a la salida del
binario oficial; POSGAR07 dentro de 0.4 cm.

Referencias: Instituto Geografico Nacional (Argentina) y Ohio State University;
Bevis & Brown (2014); Gomez et al. (2015); Manual VEL-Ar v2.0 (IGN, 2022).
Calculadora oficial: https://www.ign.gob.ar/NuestrasActividades/Geodesia/VEL-Ar/Calculadora
"""

import heapq
import math
import os

_A = 6378137.0
_F = 1.0 / 298.257223563
_E2 = _F * (2.0 - _F)
_EP2 = _E2 / (1.0 - _E2)

EPOCA_POSGAR07 = 2006.632
T_MAULE = 2010.159
T_ILLAPEL = 2015.710
T_RELAJACION = 0.5
CORTE_M = 30000.0
MERIDIANO_CENTRAL = -63.0
COBERTURA_MAX_M = 80000.0

ARCHIVOS = {
    "lin": "vel-ar-lin.txt",
    "cos_maule": "vel-ar-cos-maule.txt",
    "cos_illapel": "vel-ar-cos-illapel.txt",
    "log_maule": "vel-ar-log-maule.txt",
    "log_illapel": "vel-ar-log-illapel.txt",
}
_CON_CORTE = {"cos_maule", "log_maule", "log_illapel"}

# zona donde VEMOS puede dar error grande si el intervalo cruza un sismo (ver vemos.py)
T_MAULE_VEMOS = T_MAULE
T_ILLAPEL_VEMOS = T_ILLAPEL
ZONA_MAULE_ILLAPEL = (-42.0, -27.0, -75.0, -63.0)  # lat_min, lat_max, lon_min, lon_max

# POSGAR07b -> POSGAR07: dX = T + s*X + R x X (metros, geocentrico)
_HELMERT_T = (-0.00103003, -0.00099998, -0.00062002)
_HELMERT_S = 1.8101031e-09
_HELMERT_R = (7.19998e-10, -4.40003e-10, 5.0e-11)


def zona_sismica_maule_illapel(lat, lon, t_obs, t_ref):
    """True si el punto cae en la zona de Maule/Illapel y el intervalo [t_obs, t_ref]
    contiene alguno de los dos sismos -- en ese caso VEMOS puede dar un error grande y
    conviene recomendar VEL-Ar en su lugar (solo aplica si el punto esta en Argentina)."""
    la0, la1, lo0, lo1 = ZONA_MAULE_ILLAPEL
    if not (la0 <= lat <= la1 and lo0 <= lon <= lo1):
        return False
    a, b = min(t_obs, t_ref), max(t_obs, t_ref)
    return any(a < t <= b for t in (T_MAULE_VEMOS, T_ILLAPEL_VEMOS))


def geodetica_a_geocentrica(lat, lon, h=0.0):
    p, longitud = math.radians(lat), math.radians(lon)
    n = _A / math.sqrt(1.0 - _E2 * math.sin(p) ** 2)
    return ((n + h) * math.cos(p) * math.cos(longitud), (n + h) * math.cos(p) * math.sin(longitud),
            (n * (1.0 - _E2) + h) * math.sin(p))


def geocentrica_a_geodetica(x, y, z):
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1.0 - _E2))
    h = 0.0
    for _ in range(10):
        n = _A / math.sqrt(1.0 - _E2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - n
        nueva = math.atan2(z, p * (1.0 - _E2 * n / (n + h)))
        if abs(nueva - lat) < 1e-15:
            lat = nueva
            break
        lat = nueva
    return math.degrees(lat), math.degrees(lon), h


def _utm(lat, lon, lon0=MERIDIANO_CENTRAL, k0=0.9996):
    """(este, norte) UTM sin falsos origenes, con meridiano central lon0 -- solo se usa
    como metrica interna para la interpolacion IDW, no como salida del modulo."""
    phi = math.radians(lat)
    dl = math.radians(lon - lon0)
    s, c, t = math.sin(phi), math.cos(phi), math.tan(phi)
    n = _A / math.sqrt(1.0 - _E2 * s * s)
    t2, c2, a = t * t, _EP2 * c * c, dl * c
    e4, e6 = _E2 * _E2, _E2 ** 3
    m = _A * ((1 - _E2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
              - (3 * _E2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
              + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi)
              - (35 * e6 / 3072) * math.sin(6 * phi))
    x = k0 * n * (a + (1 - t2 + c2) * a ** 3 / 6 + (5 - 18 * t2 + t2 * t2 + 72 * c2 - 58 * _EP2) * a ** 5 / 120)
    y = k0 * (m + n * t * (a * a / 2 + (5 - t2 + 9 * c2 + 4 * c2 * c2) * a ** 4 / 24
                           + (61 - 58 * t2 + t2 * t2 + 600 * c2 - 330 * _EP2) * a ** 6 / 720))
    return x, y


def _neu_a_xyz(lat, lon, n, e, u):
    p, longitud = math.radians(lat), math.radians(lon)
    sp, cp, sl, cl = math.sin(p), math.cos(p), math.sin(longitud), math.cos(longitud)
    return (-sl * e - sp * cl * n + cp * cl * u,
            cl * e - sp * sl * n + cp * sl * u,
            cp * n + sp * u)


def _helmert(x, y, z, signo):
    """POSGAR07b -> POSGAR07 (signo=+1) o la transformacion inversa (signo=-1)."""
    tx, ty, tz = _HELMERT_T
    rx, ry, rz = _HELMERT_R
    s = _HELMERT_S
    dx = tx + s * x + (-rz * y + ry * z)
    dy = ty + s * y + (rz * x - rx * z)
    dz = tz + s * z + (-ry * x + rx * y)
    return x + signo * dx, y + signo * dy, z + signo * dz


class _Grilla:
    """Nodos (x, y UTM, N, E) con un indice espacial por celdas de 100 km, para ubicar
    rapido los 4 nodos mas cercanos a un punto sin recorrer toda la grilla cada vez."""

    CELDA = 100000.0

    def __init__(self, nodos, lats, lons):
        self.nodos, self.lats, self.lons = nodos, lats, lons
        self.indice = {}
        for i, (x, y, _, _) in enumerate(nodos):
            self.indice.setdefault((int(x // self.CELDA), int(y // self.CELDA)), []).append(i)

    def _candidatos(self, cx, cy, radio):
        cand = []
        for ix in range(cx - radio, cx + radio + 1):
            for iy in range(cy - radio, cy + radio + 1):
                cand.extend(self.indice.get((ix, iy), ()))
        return cand

    def cuatro_cercanos(self, x, y):
        cx, cy = int(x // self.CELDA), int(y // self.CELDA)
        radio = 1
        while True:
            cand = self._candidatos(cx, cy, radio)
            if len(cand) >= 4 or radio > 60:
                break
            radio += 1
        if len(cand) >= 4:      # un anillo mas para no perder un nodo justo afuera
            cand = self._candidatos(cx, cy, radio + 1)
        dist = ((math.hypot(self.nodos[i][0] - x, self.nodos[i][1] - y), i) for i in cand)
        return heapq.nsmallest(4, dist)

    def interpolar(self, x, y, con_corte):
        """(VN, VE) interpolados por IDW (p=2) de los 4 nodos mas cercanos; None si no hay
        4 nodos disponibles, o si con_corte=True y el 4o nodo esta a mas de CORTE_M."""
        c = self.cuatro_cercanos(x, y)
        if len(c) < 4:
            return None
        if con_corte and c[-1][0] > CORTE_M:
            return None
        if c[0][0] < 1e-6:
            nodo = self.nodos[c[0][1]]
            return nodo[2], nodo[3]
        pesos = [1.0 / (d * d) for d, _ in c]
        tot = sum(pesos)
        vn = sum(p * self.nodos[i][2] for p, (_, i) in zip(pesos, c)) / tot
        ve = sum(p * self.nodos[i][3] for p, (_, i) in zip(pesos, c)) / tot
        return vn, ve


def _leer_grilla(ruta):
    nodos, lats, lons = [], [], []
    with open(ruta, "r", encoding="latin-1") as fh:
        for linea in fh:
            partes = linea.split()
            if len(partes) < 4:
                continue
            try:
                lat, lon, vn, ve = (float(p) for p in partes[:4])
            except ValueError:
                continue
            x, y = _utm(lat, lon)
            nodos.append((x, y, vn, ve))
            lats.append(lat)
            lons.append(lon)
    if not nodos:
        raise ValueError("velar_sin_datos")
    return _Grilla(nodos, lats, lons)


class ModeloVelAr:
    def __init__(self, grillas):
        self.grillas = grillas

    def __len__(self):
        return sum(len(g.nodos) for g in self.grillas.values())

    @classmethod
    def desde_carpeta(cls, carpeta):
        return cls({k: _leer_grilla(os.path.join(carpeta, f)) for k, f in ARCHIVOS.items()})

    def cobertura(self):
        g = self.grillas["lin"]
        return min(g.lats), max(g.lats), min(g.lons), max(g.lons)


class ResultadoVelAr:
    def __init__(self, lat, lon, h, desplazamiento_m, componentes, lat_p07=None, lon_p07=None, h_p07=None):
        self.lat, self.lon, self.h = lat, lon, h            # POSGAR07b en la epoca destino
        self.desplazamiento_m = desplazamiento_m
        self.componentes = componentes                      # {"intersismica"|"maule"|"illapel": (n, e)} en m
        # solo se llenan si la epoca destino es POSGAR07 (2006.632): coordenada final oficial
        self.lat_p07, self.lon_p07, self.h_p07 = lat_p07, lon_p07, h_p07


def _salto(t, tj):
    return 1.0 if t >= tj else 0.0


def _log(t, tj):
    return math.log10(1.0 + (t - tj) / T_RELAJACION) if t >= tj else 0.0


def esta_en_cobertura(modelo, lat, lon):
    """True si el punto tiene al menos un nodo lineal a <= COBERTURA_MAX_M (80 km)."""
    x, y = _utm(lat, lon)
    c = modelo.grillas["lin"].cuatro_cercanos(x, y)
    return bool(c) and c[0][0] <= COBERTURA_MAX_M


def desplazamiento_neu(modelo, lat, lon, ti, tf):
    """Desplazamiento (N, E) en metros entre las epocas ti y tf, descompuesto por
    componente (intersismica + saltos/relajacion de Maule e Illapel). None si el punto
    esta fuera de cobertura."""
    if not esta_en_cobertura(modelo, lat, lon):
        return None
    x, y = _utm(lat, lon)
    g = modelo.grillas
    v = g["lin"].interpolar(x, y, False) or (0.0, 0.0)
    comp = {"intersismica": (v[0] * (tf - ti), v[1] * (tf - ti))}
    for nombre, tj in (("maule", T_MAULE), ("illapel", T_ILLAPEL)):
        cs = g["cos_" + nombre].interpolar(x, y, "cos_" + nombre in _CON_CORTE) or (0.0, 0.0)
        lg = g["log_" + nombre].interpolar(x, y, True) or (0.0, 0.0)
        ds = _salto(tf, tj) - _salto(ti, tj)
        dl = _log(tf, tj) - _log(ti, tj)
        comp[nombre] = (cs[0] * ds + lg[0] * dl, cs[1] * ds + lg[1] * dl)
    return comp


def cambiar_epoca(modelo, lat, lon, h, ti, tf):
    """Lleva (lat, lon, h) de la epoca ti a la epoca tf con el modelo VEL-Ar.
    None si el punto esta fuera de cobertura.
    Si ti == EPOCA_POSGAR07 (2006.632), la entrada se toma como POSGAR07 (se aplica el
    Helmert inverso antes de desplazar). Si tf == EPOCA_POSGAR07, el resultado trae
    ademas lat_p07/lon_p07/h_p07: la coordenada final oficial en POSGAR07 (con Helmert
    directo aplicado despues de desplazar) -- la que corresponde usar como salida cuando
    la epoca destino es la oficial del marco argentino. La altura no se modifica salvo
    por ese Helmert (~1 cm), igual que hace el programa oficial."""
    comp = desplazamiento_neu(modelo, lat, lon, ti, tf)
    if comp is None:
        return None
    x, y, z = geodetica_a_geocentrica(lat, lon, h)
    if abs(ti - EPOCA_POSGAR07) < 5e-4:
        x, y, z = _helmert(x, y, z, -1.0)
    n = sum(c[0] for c in comp.values())
    e = sum(c[1] for c in comp.values())
    dx, dy, dz = _neu_a_xyz(lat, lon, n, e, 0.0)
    xf, yf, zf = x + dx, y + dy, z + dz
    lat2, lon2, h2 = geocentrica_a_geodetica(xf, yf, zf)
    resultado = ResultadoVelAr(lat2, lon2, h2, math.hypot(n, e), comp)
    if abs(tf - EPOCA_POSGAR07) < 5e-4:
        resultado.lat_p07, resultado.lon_p07, resultado.h_p07 = geocentrica_a_geodetica(*_helmert(xf, yf, zf, 1.0))
    return resultado


def texto_cobertura(modelo):
    """Describe la cobertura real de ``modelo`` (grilla lineal) en texto
    legible, p. ej. "55°S a 18°S, 75°W a 40°W" -- mismo formato que
    ``vemos.texto_cobertura``, usado para avisar al usuario cuando un punto
    queda fuera de esa zona."""
    la0, la1, lo0, lo1 = modelo.cobertura()

    def _lat(v):
        return "{:g}°{}".format(abs(round(v)), "N" if v >= 0 else "S")

    def _lon(v):
        return "{:g}°{}".format(abs(round(v)), "E" if v >= 0 else "W")

    return "{} a {}, {} a {}".format(_lat(la0), _lat(la1), _lon(lo0), _lon(lo1))
