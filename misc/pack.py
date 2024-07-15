import os
import platform
import shutil
import stat
import subprocess
import sys
import importlib.util

OUTPUT = 'dist'
BUNDLE_DEST = os.path.join(OUTPUT, 'chess')
INSTALLER_OUTPUT = os.getcwd()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Load engine for version.
from sturddle_chess_engine import chess_engine

is_windows = platform.system() == 'Windows'


modules = [
    'chess',
    'chess.syzygy',
]

if is_windows:
    modules += [
        'win32timezone',
    ]

data_files = [
    ('*.bin', '.'),
    ('*.kv', '.'),
    ('annembed', 'annembed'),
    ('speech', 'speech'),
    ('eco', 'eco'),
    ('fonts', 'fonts'),
    ('images', 'images'),
    ('intent-model', 'intent-model'),
    ('openings.idx', 'openings.idx'),
]

if is_windows:
    data_files += [
        ('say.ps1', '.')
    ]
else:
    data_files += [
        ('say.py', '.')
    ]

def find_whisper_path():
    spec = importlib.util.find_spec("whisper")
    if spec is not None:
        return os.path.dirname(spec.origin)
    return None

def on_rm_error(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)

def remove_unwanted_files_and_dirs():
    unwanted_patterns = [
        '.buildozer'
        '.git',
        '.gitignore',
        '*.log',
        '__pycache__',
        'misc',
        'pocketsphinx-data'
    ]

    for root, dirs, files in os.walk(BUNDLE_DEST):
        for pattern in unwanted_patterns:
            for dir_name in dirs[:]:
                if dir_name == pattern or dir_name.endswith(pattern):
                    dir_path = os.path.join(root, dir_name)
                    print(f"Removing directory: {dir_path}")
                    shutil.rmtree(dir_path, onexc=on_rm_error)
                    dirs.remove(dir_name)
            for file_name in files:
                if file_name == pattern or file_name.endswith(pattern):
                    file_path = os.path.join(root, file_name)
                    print(f"Removing file: {file_path}")
                    os.remove(file_path)

def post_bundle():
    remove_unwanted_files_and_dirs()
    if is_windows:
        shutil.copy(os.path.join('misc', 'AppxManifest.xml'), BUNDLE_DEST)

def run_cmd(command):
    subprocess.run(command, shell=True, check=True, capture_output=False, text=True)

def cleanup():
    paths = ['build', OUTPUT]
    for p in paths:
        if os.path.exists(p):
            shutil.rmtree(p, onexc=on_rm_error)
    if os.path.exists('chess.spec'):
        os.remove('chess.spec')
    if os.path.exists('installer.iss'):
        os.remove('installer.iss')

def create_inno_script():
    version=chess_engine.version()
    inno_script = f"""
[Setup]
AppPublisher=Cristian Vlasceanu
AppPublisherURL=https://github.com/cristivlas/sturddle-chess-app
AppName=Sturddle Chess
AppVersion={version}
DefaultDirName={{autopf64}}\\SturddleChess
DefaultGroupName=Sturddle Chess
OutputDir={INSTALLER_OUTPUT}
OutputBaseFilename=SturddleChessInstaller
Compression=lzma
SolidCompression=yes
SourceDir={BUNDLE_DEST}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "*"; DestDir: "{{app}}"; Flags: recursesubdirs

[Icons]
Name: "{{group}}\\Sturddle Chess"; Filename: "{{app}}\\chess.exe"; WorkingDir: {{app}}
Name: "{{group}}\\Uninstall Sturddle Chess"; Filename: "{{uninstallexe}}"; IconFilename: "{{app}}\\chess.exe"

[Run]
Filename: "{{app}}\\chess.exe"; Description: "Launch Sturddle Chess"; Flags: postinstall nowait

[UninstallDelete]
Type: filesandordirs; Name: "{{app}}"
    """

    with open('installer.iss', 'w') as f:
        f.write(inno_script)

def main():
    if not os.path.exists('eco/dist'):
        raise RuntimeError('Missing ECO distribution.')

    # Clean up before starting
    cleanup()

    # Detect Whisper installation
    whisper_path = find_whisper_path()

    # Add Whisper assets to data_files if found
    if whisper_path:
        whisper_assets_dir = os.path.join(whisper_path, "assets")
        if os.path.exists(whisper_assets_dir):
            data_files.append((whisper_assets_dir, 'whisper/assets'))
            print(f"Added Whisper assets to data files: {whisper_assets_dir}")
        else:
            print("Whisper assets directory not found")

    # Create the initial bundle
    cmd = ['pyinstaller',
           '--clean',
           '--icon=images/chess.ico',
           '-y',
           '-w',
           '--log-level=INFO',
           f'--distpath={OUTPUT}',
           '--name=chess',
           'main.py'
        ]

    for src, dest in data_files:
        cmd.extend(['--add-data', f'{src}:{dest}'])

    for m in modules:
        cmd.extend(['--hidden-import', m])

    # Add Whisper as a hidden import if found
    if whisper_path:
        cmd.extend(['--hidden-import', 'whisper'])

    run_cmd(' '.join(cmd))

    post_bundle()

    if is_windows:
        # Create Inno Setup script
        create_inno_script()

        # Create installer output directory
        os.makedirs(INSTALLER_OUTPUT, exist_ok=True)

        # Run Inno Setup to create the installer
        run_cmd('iscc installer.iss')

    # Final cleanup
    #cleanup()

if __name__ == '__main__':
    main()
