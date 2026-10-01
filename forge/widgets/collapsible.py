# A remake of simonxeko's collapseable widget CollapseButton.h 
# https://stackoverflow.com/questions/32476006/how-to-make-an-expandable-collapsable-section-widget-in-qt
from ..qt_compat import QPushButton, QVBoxLayout, QWidget

_OPEN_MARK = "▾"    # ▾
_CLOSED_MARK = "▸"  # ▸


class CollapsibleWidget(QWidget):
    """A titled section that shows or hides its child.

    Sections start collapsed: only the controls needed for every generation
    stay open, and pass ``expanded=True`` to keep one of those open.
    """

    def __init__(self, text="Toggle", child:QWidget=None, expanded:bool=False):
        super().__init__()
        self.child = child
        self.title = text
        self.setLayout(QVBoxLayout())
        # self.setStyleSheet('background: none;')
        self.layout().setContentsMargins(0,0,0,0)

        self.toggle_label = QPushButton(text)
        self.toggle_label.setObjectName("CollapsibleToggle")
        self.toggle_label.setCheckable(True)
        self.toggle_label.setChecked(bool(expanded))
        self.toggle_label.clicked.connect(self.toggle)
        self.layout().addWidget(self.toggle_label)

        self.layout().addWidget(self.child)
        self.toggle()

    def toggle(self):
        expanded = self.toggle_label.isChecked()
        if expanded:
            self.child.show()
        else:
            self.child.hide()
        # The mark is what tells a collapsed section apart from a plain heading.
        self.toggle_label.setText(
            "%s  %s" % (_OPEN_MARK if expanded else _CLOSED_MARK, self.title)
        )
        self.update()
