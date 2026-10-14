# -*- coding: utf-8 -*-
"""
test_velar.py
==============

Pruebas del modulo puro velar_ar.py (cambio de epoca con el modelo VEL-Ar v2.0,
IGN Argentina). No depende de QGIS/PyQt: se puede correr con "python3 test_velar.py".

Sigue la seccion "Pruebas minimas VEL-Ar" de la skill vemos-cambio-de-epoca (valores
oficiales transcritos de capturas del manual/calculadora del IGN, tolerancia 2 cm por
tratarse de una reimplementacion independiente), mas pruebas adicionales sobre la
cobertura, los casos de borde (misma epoca, ida y vuelta) y la zona sismica.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import velar_ar  # noqa: E402

DIR_DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "velar_data")

_fallos = []
_total = 0


def verificar(nombre, condicion, detalle=""):
    global _total
    _total += 1
    if condicion:
        print("OK   {}".format(nombre))
    else:
        msg = "FALLO {}  {}".format(nombre, detalle)
        print(msg)
        _fallos.append(msg)


# ---------------------------------------------------------------------
# 1. Lectura de las 5 grillas reales.
# ---------------------------------------------------------------------

try:
    _modelo = velar_ar.ModeloVelAr.desde_carpeta(DIR_DATOS)
    verificar("ModeloVelAr.desde_carpeta: se leen las 5 grillas", len(_modelo.grillas) == 5)
    for _clave in velar_ar.ARCHIVOS:
        verificar(
            "grilla '{}': tiene nodos".format(_clave),
            len(_modelo.grillas[_clave].nodos) > 0,
            "obtenido {}".format(len(_modelo.grillas[_clave].nodos)),
        )
except (OSError, ValueError) as exc:
    _modelo = None
    verificar("ModeloVelAr.desde_carpeta: se lee sin error", False, repr(exc))

# ---------------------------------------------------------------------
# 2. Puntos oficiales (manual/calculadora IGN), tolerancia 2 cm en
#    lat/lon (convertida aproximadamente a partir de la diferencia en
#    grados, comparando directamente las coordenadas resultantes).
# ---------------------------------------------------------------------

_TOL_GRADOS = 0.0000002  # ~2 cm en latitud

if _modelo is not None:
    # Mendoza: POSGAR07b y POSGAR07 esperados, con desplazamiento N/E esperado.
    _res = velar_ar.cambiar_epoca(_modelo, -33.97594582, -69.06060325, 50.351, 2015.180, velar_ar.EPOCA_POSGAR07)
    verificar("cambiar_epoca Mendoza 2015.180->POSGAR07: no es None", _res is not None)
    if _res is not None:
        verificar(
            "Mendoza: POSGAR07b lat esperado",
            abs(_res.lat - (-33.97594606504391)) < _TOL_GRADOS,
            "obtenido {}".format(_res.lat),
        )
        verificar(
            "Mendoza: POSGAR07b lon esperado",
            abs(_res.lon - (-69.06059965490816)) < _TOL_GRADOS,
            "obtenido {}".format(_res.lon),
        )
        verificar(
            "Mendoza: POSGAR07 (final oficial) disponible y correcto",
            _res.lat_p07 is not None
            and abs(_res.lat_p07 - (-33.97594609609877)) < _TOL_GRADOS
            and abs(_res.lon_p07 - (-69.06059964069073)) < _TOL_GRADOS,
            "obtenido lat_p07={}, lon_p07={}".format(_res.lat_p07, _res.lon_p07),
        )
        _n_total = sum(c[0] for c in _res.componentes.values())
        _e_total = sum(c[1] for c in _res.componentes.values())
        verificar(
            "Mendoza: desplazamiento N esperado (-0.0272 m aprox.)",
            abs(_n_total - (-0.0271809640557927)) < 0.02,
            "obtenido {:.6f} m".format(_n_total),
        )
        verificar(
            "Mendoza: desplazamiento E esperado (+0.3322 m aprox.)",
            abs(_e_total - 0.3322279995126379) < 0.02,
            "obtenido {:.6f} m".format(_e_total),
        )

    # Punto 2: fuera de zonas sismicas relevantes.
    _res2 = velar_ar.cambiar_epoca(_modelo, -38.938897, -57.209418, 1077.071, 2021.641, 2009.004)
    verificar("cambiar_epoca punto 2: no es None", _res2 is not None)
    if _res2 is not None:
        verificar(
            "punto 2: lat esperada",
            abs(_res2.lat - (-38.93889831812029)) < _TOL_GRADOS,
            "obtenido {}".format(_res2.lat),
        )

    # Punto 3.
    _res3 = velar_ar.cambiar_epoca(_modelo, -30.144281, -68.654468, 627.112, 2012.4, 2020.0)
    verificar("cambiar_epoca punto 3: no es None", _res3 is not None)
    if _res3 is not None:
        verificar(
            "punto 3: lat esperada",
            abs(_res3.lat - (-30.144280281051334)) < _TOL_GRADOS,
            "obtenido {}".format(_res3.lat),
        )

    # Punto 4: destino POSGAR07, con POSGAR07b y POSGAR07 esperados.
    _res4 = velar_ar.cambiar_epoca(_modelo, -46.38788, -58.166694, 423.349, 2020.001, velar_ar.EPOCA_POSGAR07)
    verificar("cambiar_epoca punto 4: no es None", _res4 is not None)
    if _res4 is not None:
        verificar(
            "punto 4: POSGAR07b lat esperada",
            abs(_res4.lat - (-46.38788132998439)) < _TOL_GRADOS,
            "obtenido {}".format(_res4.lat),
        )
        verificar(
            "punto 4: POSGAR07 (final oficial) lat esperada",
            _res4.lat_p07 is not None and abs(_res4.lat_p07 - (-46.38788135323263)) < _TOL_GRADOS,
            "obtenido {}".format(_res4.lat_p07),
        )

    # ---------------------------------------------------------------------
    # 3. Casos de borde.
    # ---------------------------------------------------------------------

    # Misma epoca -> desplazamiento nulo.
    _res_igual = velar_ar.cambiar_epoca(_modelo, -33.0, -68.0, 500.0, 2015.0, 2015.0)
    verificar(
        "cambiar_epoca con ti==tf: desplazamiento == 0",
        _res_igual is not None and _res_igual.desplazamiento_m < 1e-9,
        "obtenido {}".format(_res_igual.desplazamiento_m if _res_igual else None),
    )

    # ti == tf == POSGAR07: la salida POSGAR07 debe coincidir con la entrada.
    _lat0, _lon0, _h0 = -33.5, -68.5, 700.0
    _res_p07_igual = velar_ar.cambiar_epoca(_modelo, _lat0, _lon0, _h0, velar_ar.EPOCA_POSGAR07, velar_ar.EPOCA_POSGAR07)
    verificar(
        "cambiar_epoca con ti==tf==POSGAR07: POSGAR07 final == entrada",
        _res_p07_igual is not None
        and abs(_res_p07_igual.lat_p07 - _lat0) < 1e-9
        and abs(_res_p07_igual.lon_p07 - _lon0) < 1e-9,
        "obtenido lat_p07={}, lon_p07={}".format(
            _res_p07_igual.lat_p07 if _res_p07_igual else None,
            _res_p07_igual.lon_p07 if _res_p07_igual else None,
        ),
    )

    # Ida y vuelta: 2019.5 -> 2012.0 -> 2019.5 debe volver a < 1 cm.
    _lat1, _lon1, _h1 = -35.0, -68.0, 600.0
    _ida = velar_ar.cambiar_epoca(_modelo, _lat1, _lon1, _h1, 2019.5, 2012.0)
    if _ida is not None:
        _vuelta = velar_ar.cambiar_epoca(_modelo, _ida.lat, _ida.lon, _ida.h, 2012.0, 2019.5)
        _dist_m = math.hypot(
            math.radians(_vuelta.lat - _lat1) * 6371000.0,
            math.radians(_vuelta.lon - _lon1) * 6371000.0 * math.cos(math.radians(_lat1)),
        ) if _vuelta is not None else None
        verificar(
            "ida y vuelta (2019.5->2012.0->2019.5): diferencia < 1 cm",
            _vuelta is not None and _dist_m < 0.01,
            "obtenido {} m".format(_dist_m),
        )
    else:
        verificar("ida y vuelta: el punto de ida no es None", False, "cambiar_epoca devolvio None")

    # Cruzar 2010.159 en Mendoza agrega > 10 cm; en el sur (-50,-69) agrega < 10 cm.
    _mendoza_sin = velar_ar.cambiar_epoca(_modelo, -33.0, -68.8, 0.0, 2009.0, 2011.0)
    verificar(
        "Mendoza cruzando Maule (2009->2011): desplazamiento > 10 cm",
        _mendoza_sin is not None and _mendoza_sin.desplazamiento_m > 0.10,
        "obtenido {}".format(_mendoza_sin.desplazamiento_m if _mendoza_sin else None),
    )
    _sur_sin = velar_ar.cambiar_epoca(_modelo, -50.0, -69.0, 0.0, 2009.0, 2011.0)
    verificar(
        "Sur (-50,-69) cruzando Maule (2009->2011): desplazamiento < 10 cm",
        _sur_sin is not None and _sur_sin.desplazamiento_m < 0.10,
        "obtenido {}".format(_sur_sin.desplazamiento_m if _sur_sin else None),
    )

    # Bogota: fuera de cobertura.
    verificar(
        "cambiar_epoca(Bogota): None (fuera de cobertura)",
        velar_ar.cambiar_epoca(_modelo, 4.6, -74.1, 2600.0, 2018.0, velar_ar.EPOCA_POSGAR07) is None,
    )
    verificar(
        "esta_en_cobertura(Bogota): False",
        velar_ar.esta_en_cobertura(_modelo, 4.6, -74.1) is False,
    )
    verificar(
        "esta_en_cobertura(Mendoza): True",
        velar_ar.esta_en_cobertura(_modelo, -33.0, -68.8) is True,
    )

    # La altura no cambia en POSGAR07b (solo el Helmert la toca al pedir POSGAR07).
    _res_h = velar_ar.cambiar_epoca(_modelo, -35.0, -65.0, 321.0, 2018.0, 2020.0)
    verificar(
        "altura conservada en POSGAR07b (sin Helmert de por medio)",
        _res_h is not None and abs(_res_h.h - 321.0) < 0.001,
        "obtenido {}".format(_res_h.h if _res_h else None),
    )

    # texto_cobertura: formato legible.
    _txt_cob = velar_ar.texto_cobertura(_modelo)
    verificar(
        "texto_cobertura(VEL-Ar) contiene 'S' y 'W'",
        "S" in _txt_cob and "W" in _txt_cob,
        repr(_txt_cob),
    )

# ---------------------------------------------------------------------
# 4. zona_sismica_maule_illapel.
# ---------------------------------------------------------------------

verificar(
    "zona_sismica_maule_illapel: Mendoza cruzando Maule -> True",
    velar_ar.zona_sismica_maule_illapel(-33.0, -68.8, 2009.0, 2011.0) is True,
)
verificar(
    "zona_sismica_maule_illapel: Mendoza sin cruzar ningun sismo -> False",
    velar_ar.zona_sismica_maule_illapel(-33.0, -68.8, 2011.0, 2012.0) is False,
)
verificar(
    "zona_sismica_maule_illapel: Bogota (fuera de la zona) -> False",
    velar_ar.zona_sismica_maule_illapel(4.6, -74.1, 2009.0, 2011.0) is False,
)
verificar(
    "zona_sismica_maule_illapel: cruzando Illapel -> True",
    velar_ar.zona_sismica_maule_illapel(-33.0, -68.8, 2014.0, 2017.0) is True,
)

# ---------------------------------------------------------------------
# 5. geodetica_a_geocentrica / geocentrica_a_geodetica: ida y vuelta.
# ---------------------------------------------------------------------

for _lat_t, _lon_t, _h_t in ((-33.4, -70.6, 500.0), (-54.8, -68.3, 10.0), (0.0, 0.0, 0.0)):
    _x, _y, _z = velar_ar.geodetica_a_geocentrica(_lat_t, _lon_t, _h_t)
    _lat2, _lon2, _h2 = velar_ar.geocentrica_a_geodetica(_x, _y, _z)
    verificar(
        "ida y vuelta geodesica<->geocentrica en ({}, {}, {})".format(_lat_t, _lon_t, _h_t),
        abs(_lat2 - _lat_t) < 1e-9 and abs(_lon2 - _lon_t) < 1e-9 and abs(_h2 - _h_t) < 1e-6,
        "obtenido ({}, {}, {})".format(_lat2, _lon2, _h2),
    )

# ---------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------

print()
print("{} pruebas, {} fallos".format(_total, len(_fallos)))
if _fallos:
    sys.exit(1)
