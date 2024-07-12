import os
import shutil
import stat

OUTPUT = 'dist'
BUNDLE_DEST = os.path.join(OUTPUT, 'chess')
INSTALLER_OUTPUT = os.getcwd()

modules = [
    'chess',
    'chess.syzygy',
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
    ('say.ps1', '.')
]

def on_rm_error(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)

def remove_unwanted_files_and_dirs():
    unwanted_patterns = ['game.dat', '.git', '.gitignore', '*.log', '__pycache__']

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

def run_cmd(command):
    print(command)
    return os.system(command)

def cleanup():
    paths = ['build', 'dist']
    for p in paths:
        if os.path.exists(p):
            shutil.rmtree(p, onexc=on_rm_error)
    if os.path.exists('chess.spec'):
        os.remove('chess.spec')

def create_inno_script():
    inno_script = f"""
[Setup]
AppPublisher=Cristian Vlasceanu
AppPublisherURL=https://github.com/cristivlas/sturddle-chess-app
AppName=Sturddle Chess for Windows
AppVersion=0.9.0
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

    # Create the initial bundle
    cmd = ['pyinstaller',
           '--clean',
           '--icon=images/chess.ico',
           '-y',
           #'-w',
           '--log-level=INFO',
           f'--distpath={OUTPUT}',
           '--name=chess',
           'main.py'
        ]

    for src, dest in data_files:
        cmd.extend(['--add-data', f'{src}:{dest}'])

    for m in modules:
        cmd.extend(['--hidden-import', m])

    run_cmd(' '.join(cmd))

    post_bundle()

    # Create Inno Setup script
    create_inno_script()

    # Create installer output directory
    os.makedirs(INSTALLER_OUTPUT, exist_ok=True)

    # Run Inno Setup to create the installer
    run_cmd('iscc installer.iss')

    # Final cleanup
    # cleanup()

    if os.path.exists('installer.iss'):
        os.remove('installer.iss')

if __name__ == '__main__':
    main()