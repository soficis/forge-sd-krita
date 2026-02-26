from krita import DockWidgetFactory, DockWidgetFactoryBase, Krita

from .forge import ForgeDocker

Krita.instance().addDockWidgetFactory(
    DockWidgetFactory(
        "forgeSD",
        DockWidgetFactoryBase.DockTornOff,
        ForgeDocker,
    )
)

__all__ = ["ForgeDocker"]
