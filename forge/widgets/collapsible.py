# A remake of simonxeko's collapseable widget CollapseButton.h 
# https://stackoverflow.com/questions/32476006/how-to-make-an-expandable-collapsable-section-widget-in-qt
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

class CollapsibleWidget(QWidget):
    def __init__(self, text="Toggle", child:QWidget=None):
        super().__init__()
        self.child = child
        self.setLayout(QVBoxLayout())
        # self.setStyleSheet('background: none;')
        self.layout().setContentsMargins(0,0,0,0)
        self.child = child

        self.toggle_label = QPushButton(text)
        self.toggle_label.setObjectName("CollapsibleToggle")
        self.toggle_label.setCheckable(True)
        self.toggle_label.setChecked(True)
        self.toggle_label.clicked.connect(self.toggle)
        self.layout().addWidget(self.toggle_label)

        self.layout().addWidget(self.child)

    def toggle(self):
        if self.toggle_label.isChecked():
            self.child.show()
        else:
            self.child.hide()
        self.update()