from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

from ..services import checkpoints as CK


class RestaurarCheckpointDialog(QDialog):
    def __init__(self, proyecto: str, parent=None):
        super().__init__(parent)
        self.proyecto = proyecto
        self.setWindowTitle("Restaurar checkpoint")
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Elegí un checkpoint para restaurar la configuración del proyecto a ese "
                                 "punto. No se puede deshacer."))

        self.list = QListWidget()
        self.checkpoints = CK.list_checkpoints(proyecto)
        for cp in self.checkpoints:
            item = QListWidgetItem(f"{cp.created_at}  ·  {cp.label}  ·  {cp.done}/{cp.total} corridas "
                                    f"({cp.pct}%)")
            item.setData(1, cp)
            self.list.addItem(item)
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        manual_btn = QPushButton("+ Guardar checkpoint ahora")
        manual_btn.clicked.connect(self._save_manual)
        row.addWidget(manual_btn)
        layout.addLayout(row)

        buttons = QDialogButtonBox()
        self.restore_btn = buttons.addButton("Restaurar…", QDialogButtonBox.ButtonRole.AcceptRole)
        self.restore_btn.setObjectName("Primary")
        self.restore_btn.clicked.connect(self._restore)
        cancel = buttons.addButton("Cerrar", QDialogButtonBox.ButtonRole.RejectRole)
        cancel.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _save_manual(self) -> None:
        CK.manual_checkpoint(self.proyecto)
        QMessageBox.information(self, "Checkpoint guardado", "Se guardó un checkpoint manual.")
        self.accept()  # el llamador puede reabrir el diálogo para ver la lista actualizada

    def _restore(self) -> None:
        item = self.list.currentItem()
        if not item:
            return
        cp = item.data(1)
        lost = CK.files_lost_on_restore(self.proyecto, cp)
        msg = f"Se va a restaurar la configuración a '{cp.label}' ({cp.created_at}). No se puede deshacer."
        delete = False
        if lost:
            msg += f"\n\n{len(lost)} archivo(s) de resultado son posteriores a este checkpoint:\n" + \
                   "\n".join(f"  · {p}" for p in lost[:10]) + ("\n  …" if len(lost) > 10 else "")
            box = QMessageBox(self)
            box.setWindowTitle("Confirmar restauración")
            box.setText(msg)
            box.setIcon(QMessageBox.Icon.Warning)
            keep = box.addButton("Restaurar y conservarlos", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Restaurar y borrarlos", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is None or box.buttonRole(clicked) == QMessageBox.ButtonRole.RejectRole:
                return
            delete = box.buttonRole(clicked) == QMessageBox.ButtonRole.DestructiveRole
        else:
            if QMessageBox.question(self, "Confirmar restauración", msg) != QMessageBox.StandardButton.Yes:
                return
        CK.restore_checkpoint(self.proyecto, cp, delete_newer_results=delete)
        QMessageBox.information(self, "Restaurado", "La configuración del proyecto se restauró.")
        self.accept()
