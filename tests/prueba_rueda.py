"""Prueba de interfaz (necesita PySide6): la rueda del mouse no cambia números ni listas, y sigue desplazando la página."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QScrollArea, QVBoxLayout, QWidget  # noqa: E402

import app  # noqa: E402

qa = QApplication(sys.argv)
filtro = app.SinRueda(qa); qa.installEventFilter(filtro)
sa = QScrollArea(); inner = QWidget(); lay = QVBoxLayout(inner)
sp = QDoubleSpinBox(); sp.setValue(50); cb = QComboBox(); cb.addItems(["a", "b", "c"])
lay.addWidget(sp); lay.addWidget(cb)
for _ in range(40):
    lay.addWidget(QDoubleSpinBox())
sa.setWidget(inner); sa.resize(300, 200); sa.show(); qa.processEvents()


def rueda(w):
    ev = QWheelEvent(QPointF(5, 5), QPointF(w.mapToGlobal(QPoint(5, 5))), QPoint(0, 0), QPoint(0, -120), Qt.NoButton,
                     Qt.NoModifier, Qt.ScrollUpdate, False)
    QApplication.sendEvent(w, ev); qa.processEvents()


sp.setFocus(); rueda(sp); rueda(sp.lineEdit()); rueda(cb)
print("número", sp.value(), "lista", cb.currentIndex(), "desplazamiento", sa.verticalScrollBar().value())
assert sp.value() == 50 and cb.currentIndex() == 0, "la rueda cambió un campo"
assert sa.verticalScrollBar().value() > 0, "la rueda no desplazó la página"
print("8) rueda del mouse: no cambia campos y desplaza la página")
