"""GUI de escritorio (PySide6/Qt) para Axolotl Docking.

Esta capa es una *interfaz* sobre el paquete `axd` ya existente: no duplica la
lógica de dominio (axd.config, axd.runner, axd.entorno, axd.domain.*), sólo la
expone con ventanas y diálogos. Las funciones nuevas que no existían en el CLI
(checkpoints, calibración de dispositivo, perfiles de cómputo, búsqueda de
dianas por nombre, auto-actualización) viven en `axd.gui.services` y sí son
reutilizables desde el CLI el día de mañana si hiciera falta.
"""
