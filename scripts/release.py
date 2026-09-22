"""Publish a new version from committed main: python scripts/release.py 1.0.1 --notes ..."""
import argparse
import re
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import __version__


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, encoding='utf-8').strip()


def main():
    parser = argparse.ArgumentParser(description='更新版本号和更新日志，推送标签，由 GitHub Actions 打包发布')
    parser.add_argument('version', help='新的版本号，例如 1.0.1')
    parser.add_argument('--notes', required=True, help='本次更新内容')
    args = parser.parse_args()
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', args.version):
        parser.error('版本号必须是 X.Y.Z')
    if tuple(map(int, args.version.split('.'))) <= tuple(map(int, __version__.split('.'))):
        parser.error('新版本号必须大于当前版本')
    if git('branch', '--show-current') != 'main' or git('status', '--porcelain'):
        parser.error('请先在 main 分支提交代码修改，确保工作目录干净')
    tag = 'v' + args.version
    if git('tag', '--list', tag) or git('ls-remote', '--tags', 'origin', 'refs/tags/' + tag):
        parser.error('此版本标签已存在；请使用新的版本号')
    git('fetch', 'origin', 'main')
    if subprocess.call(['git', 'merge-base', '--is-ancestor', 'origin/main', 'HEAD'], cwd=ROOT) != 0:
        parser.error('本地分支落后或已分叉，请先同步远程代码')
    subprocess.run([sys.executable, '-m', 'unittest', 'test_storage', 'test_library', 'test_runtime', 'test_ui', 'test_launcher', 'test_paper', '-v'], cwd=ROOT, check=True)
    (ROOT / 'version.py').write_text(f'"""Single source of truth for the app and release version."""\n__version__ = "{args.version}"\n', encoding='utf-8')
    changelog = ROOT / 'CHANGELOG.md'
    previous = changelog.read_text(encoding='utf-8').split('\n', 1)[1].lstrip()
    changelog.write_text(f'# 更新日志\n\n## {args.version}\n\n- {args.notes.strip()}\n\n{previous}', encoding='utf-8')
    git('add', 'version.py', 'CHANGELOG.md')
    git('commit', '-m', f'Release {tag}')
    git('tag', '-a', tag, '-m', f'ZhiLu {tag}')
    # Atomic push leaves neither branch nor tag partially published.
    git('push', '--atomic', 'origin', 'main', tag)
    print(f'已推送 {tag}。GitHub Actions 将测试、打包并发布：')
    print('https://github.com/Lee7777777777/learn_dominate/actions')


if __name__ == '__main__':
    main()
