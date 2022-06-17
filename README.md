# sturddle-chess-app
Casual Chess App

- Original chess engine (C++ / Cython submodule)
- Built-in board editor
- Turn AI off / on
- Copy / paste game in PGN format (including comments)
- Voice interaction (optional offline speech recognition on desktop via Deepspeech)
- Optional opening book(s)
- Built-in puzzle collection
- Built with Kivy and Python Chess

![Alt text](/screenshots/Screenshot_Menu.png?raw=true "Menu")
![Alt text](/screenshots/Screenshot_Game.png?raw=true "Game")
![Alt text](/screenshots/Screenshot_EditMode.png?raw=true "Editor")
![Alt text](/screenshots/Screenshot_PNGViewer.png?raw=true "PGN Viewer")
![Alt text](/screenshots/Screenshot_Settings.png?raw=true "Settings")
![Alt text](/screenshots/Screenshot_AdvSettings.png?raw=true "Advanced Settings")

# Build on desktop
```
git clone --recursive https://github.com/cristivlas/sturddle-chess-app sturddle
cd sturddle
python3 -m pip install -r requirements.txt

# build the engine (requires C++ compiler on the machine)
cd sturddle_chess_engine                                               
python3 setup.py build_ext --inplace 

# now run it
cd ..
python3 main.py
```

# Build Android image
```
git clone --recursive https://github.com/cristivlas/sturddle-chess-app sturddle
python3 -m pip install buildozer
cd sturddle
python3 -m buildozer android debug

# image should now be in sturddle/bin, use adb to deploy it
# adb install bin/<image-file>.apk

```
