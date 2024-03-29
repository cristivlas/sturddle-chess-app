# sturddle-chess-app
## Casual Offline Chess App
- Original <a href="https://github.com/cristivlas/sturddle-chess-engine">hybrid chess engine</a> (C++/Cython)
- Built-in board editor
- Turn AI off / on
- Copy / paste game in PGN format (including comments)
- Voice interaction (optional offline speech recognition on desktop via OpenAI-Whisper)
- Optional opening book(s)
- Built-in puzzle collection
- Built with Kivy and Python Chess

![Menu](/screenshots/Screenshot_Menu.png?raw=true "Menu")
![Game](/screenshots/Screenshot_Game.png?raw=true "Game")
![Edit](/screenshots/Screenshot_EditMode.png?raw=true "Editor")
![Viewer](/screenshots/Screenshot_PNGViewer.png?raw=true "PGN Viewer")
![Settings](/screenshots/Screenshot_Settings.png?raw=true "Settings")
![Advanced](/screenshots/Screenshot_AdvSettings.png?raw=true "Advanced Settings")
<img src="https://raw.githubusercontent.com/cristivlas/sturddle-chess-app/master/screenshots/Screenshot_assistant.png" height="400px"/>
<a href="https://en.wikipedia.org/wiki/Sturddlefish"><img src="images/sturddlefish.png" height="240px"><a/>
# Build on desktop (requires Python3.8 or higher)

```
git clone --recursive https://github.com/cristivlas/sturddle-chess-app sturddle
cd sturddle
python3 -m pip install -r requirements.txt

# build the engine (requires C++ compiler on the machine)
cd sturddle_chess_engine                                               
python3 setup.py build_ext --inplace 
cd ..

# Build the openings:
cd eco/
make
cd ..

# now run it
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
