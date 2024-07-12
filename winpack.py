"""
Create PyInstaller bundle and wrap with NSIS Windows
"""
import os
import shutil
import stat

OUTPUT = 'dist'
BUNDLE_DEST = os.path.join(OUTPUT, 'chess')

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
    #paths = ['build', 'dist']
    paths = ['build']
    for p in paths:
        if os.path.exists(p):
            shutil.rmtree(p, onexc=on_rm_error)
    if os.path.exists('chess.spec'):
        os.remove('chess.spec')

def create_nsis_script():
    nsis_script = r"""
    !include "MUI2.nsh"

    Name "Sturddle Chess"
    OutFile "SturddleChessInstaller.exe"
    InstallDir "$PROGRAMFILES64\SturddleChess"

    !insertmacro MUI_PAGE_DIRECTORY
    !insertmacro MUI_PAGE_INSTFILES

    !insertmacro MUI_UNPAGE_CONFIRM
    !insertmacro MUI_UNPAGE_INSTFILES

    !insertmacro MUI_LANGUAGE "English"

    Section "Install"
        SetOutPath $INSTDIR
        File /r "${BUNDLE_DEST}\*.*"
        CreateShortCut "$DESKTOP\Chess.lnk" "$INSTDIR\chess.exe"
        WriteUninstaller "$INSTDIR\Uninstall.exe"
    SectionEnd

    Section "Uninstall"
        Delete "$DESKTOP\Chess.lnk"
        RMDir /r "$INSTDIR"
    SectionEnd
    """

    # Replace ${BUNDLE_DEST} with the actual path
    nsis_script = nsis_script.replace("${BUNDLE_DEST}", BUNDLE_DEST.replace("\\", "/"))

    with open('installer.nsi', 'w') as f:
        f.write(nsis_script)

def main():
    if not os.path.exists('eco/dist'):
        raise RuntimeError('Missing ECO distribution.')

    # Clean up before starting
    cleanup()

    # Create the initial bundle
    cmd = ['pyinstaller',
           '--clean',
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

    run_cmd(' '.join(cmd))

    post_bundle()

    # Create NSIS script
    create_nsis_script()

    # Run NSIS to create the installer
    run_cmd('makensis installer.nsi')

    # Final cleanup
    cleanup()
    if os.path.exists('installer.nsi'):
        os.remove('installer.nsi')

if __name__ == '__main__':
    main()