"""Main entry point: python -m app.main"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from .ui import Window

def app_data_dir():
    base=os.environ.get('LOCALAPPDATA')
    return (Path(base)/'GuiaLankaPhotoManager') if base else (Path.home()/'.guialanka-photo-manager')

def main():
    app=QApplication(sys.argv)
    app.setApplicationName('Guia Lanka Photo Manager')
    app.setOrganizationName('Guia Lanka Tours')
    window=Window(app_data_dir())
    window.show()
    return app.exec()

if __name__=='__main__': sys.exit(main())
