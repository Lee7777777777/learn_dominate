"""Build a standalone, windowed executable and publishable versioned artifacts."""
import hashlib
import json
import math
import os
import struct
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import __version__


def make_icon(path):
    size = 64
    pixels = bytearray()
    points = ((18, 43), (33, 19), (49, 39))
    for y in range(size):
        pixels.append(0)
        for x in range(size):
            color = (18, 34, 59, 255)
            if (x < 9 or x > 54) and (y < 9 or y > 54):
                cx, cy = (9 if x < 32 else 54), (9 if y < 32 else 54)
                if math.hypot(x-cx, y-cy) > 9:
                    color = (0, 0, 0, 0)
            for a, b in zip(points, points[1:]):
                dx, dy = b[0]-a[0], b[1]-a[1]
                t = max(0, min(1, ((x-a[0])*dx + (y-a[1])*dy)/(dx*dx+dy*dy)))
                if math.hypot(x-a[0]-t*dx, y-a[1]-t*dy) < 1.8:
                    color = (115, 163, 239, 255)
            for i, (cx, cy) in enumerate(points):
                if math.hypot(x-cx, y-cy) < 5.5:
                    color = ((83, 220, 188, 255), (236, 244, 255, 255), (115, 163, 239, 255))[i]
            pixels.extend(color)
    def chunk(name, data):
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(bytes(pixels))) + chunk(b'IEND', b'')
    path.write_bytes(struct.pack('<HHH', 0, 1, 1) + struct.pack('<BBBBHHII', size, size, 0, 0, 1, 32, len(png), 22) + png)


def main():
    if sys.platform != 'win32' or struct.calcsize('P') != 8:
        raise SystemExit('Build this Windows x64 app with 64-bit Python on Windows.')
    os.chdir(ROOT)
    build = ROOT / 'build' / __version__
    build.mkdir(parents=True, exist_ok=True)
    output = ROOT / 'dist' / __version__
    output.mkdir(parents=True, exist_ok=True)
    icon = build / 'app.ico'
    make_icon(icon)
    version = tuple(map(int, __version__.split('.'))) + (0,)
    metadata = build / 'version_info.txt'
    metadata.write_text(f'''VSVersionInfo(ffi=FixedFileInfo(filevers={version}, prodvers={version}, mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)), kids=[StringFileInfo([StringTable('040904B0', [StringStruct('CompanyName','LEE'), StringStruct('FileDescription','ZhiLu Learning Map'), StringStruct('FileVersion','{__version__}'), StringStruct('ProductName','ZhiLu'), StringStruct('ProductVersion','{__version__}')])]), VarFileInfo([VarStruct('Translation',[1033,1200])])])''', encoding='utf-8')
    name = f'ZhiLu-{__version__}-Windows-x64'
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed',
                    '--name', name, '--icon', str(icon), '--add-data', f'{icon}{os.pathsep}.',
                    '--version-file', str(metadata), '--distpath', str(output),
                    '--workpath', str(build / 'work'), '--specpath', str(build), 'start.pyw'], check=True)
    executable = output / (name + '.exe')
    # Test the actual executable with isolated data, not the user's maps.
    from test_support import TestDirectory
    with TestDirectory() as temp:
        from test_paper import fixture
        from paper_agent import write_json
        task, _, _, paper_result = fixture(temp)
        write_json(task / 'result.json', paper_result)
        marker = Path(temp) / 'result.json'
        subprocess.run([str(executable), '--db', str(Path(temp) / 'smoke.db'), '--smoke-test', str(marker), '--paper-smoke-task', str(task)], check=True, timeout=90)
        result = json.loads(marker.read_text(encoding='utf-8'))
        expected = dict(version=__version__, visible=True, console=0, nodes=6, editor=True, paper=True)
        if result != expected:
            raise RuntimeError(f'Packaged app smoke test failed: {result}')
    archive = output / (name + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(executable, executable.name)
        for file in ('README.md', 'LICENSE', 'CHANGELOG.md', 'PAPER_ASSISTANT.md'):
            bundle.write(ROOT / file, file)
    checksum = output / 'SHA256SUMS.txt'
    checksum.write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in (executable, archive)), encoding='utf-8')
    print(f'Build and packaged GUI test passed: {output}')


if __name__ == '__main__':
    main()
