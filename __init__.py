# -*- coding: utf-8 -*-
"""
Punto de entrada del complemento para QGIS.

QGIS busca en este archivo la función classFactory() al cargar el
complemento.
"""


def classFactory(iface):
    from .plugin import RecalculoRTKPlugin
    return RecalculoRTKPlugin(iface)
