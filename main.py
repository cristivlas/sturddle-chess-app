__version__ = '2.6'

import os
import sys

if getattr(sys, 'frozen', False):
    # If the application is run as a bundle, the PyInstaller bootloader
    # extends the sys module by a flag frozen=True and sets the app
    # path into variable _MEIPASS'.
    os.chdir(sys._MEIPASS)

if __name__ == '__main__':
    from chessapp import ChessApp
    ChessApp().run()
