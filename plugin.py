# -*- coding: utf-8 -*-
"""
plugin.py
=========

Clase principal del complemento: registra el ícono/menú en QGIS y abre
el diálogo de recálculo.
"""

import os

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon

from .recalculo_dialog import RecalculoRTKDialog


class RecalculoRTKPlugin:
    """Recalcula coordenadas de campo (base RTK libre) hacia
    coordenadas ajustadas por postproceso estático."""

    MENU = "&Recálculo RTK a Ajustada"

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.dialog = None

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        self.action = QAction(
            QIcon(icon_path),
            "Recalcular coordenadas RTK (libre → ajustada)",
            self.iface.mainWindow(),
        )
        self.action.setWhatsThis(
            "Recalcula un CSV de puntos levantados con RTK, trasladándolos "
            "desde una base de coordenadas libres hacia la coordenada "
            "ajustada obtenida por postproceso estático."
        )
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.MENU, self.action)
        self.actions.append(self.action)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.MENU, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []
        if self.dialog is not None:
            self.dialog.close()
            self.dialog = None

    def run(self):
        if self.dialog is None:
            self.dialog = RecalculoRTKDialog(self.iface, self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
