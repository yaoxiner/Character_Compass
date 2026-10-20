"""生成供 GitHub 上传的源码包，排除本机作品、Key、依赖和构建产物。"""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ('.github', 'docs', 'packaging', 'tests', 'tools', 'vendor', 'web')
ROOT_FILES = ('.gitignore', '.env.example', 'README.md', 'requirements-desktop.txt')
EXCLUDED = {'__pycache__', '.venv', '.git', '.agents', '.codex', '.aws'}


def source_files():
    files = [ROOT / name for name in ROOT_FILES]
    files.extend(ROOT.glob('*.py'))
    for directory in DIRECTORIES:
        files.extend((ROOT / directory).rglob('*'))
    return sorted({path for path in files if path.is_file()
        and not EXCLUDED.intersection(path.relative_to(ROOT).parts)
        and path.suffix not in ('.pyc', '.log', '.dmp')
        and (not path.name.startswith('.env') or path == ROOT / '.env.example')
        and path.relative_to(ROOT).as_posix() not in ('web/assets/icon.ico', 'web/assets/icon.png')})


def main():
    paths = source_files()
    # 如误把当前 Key 粘进源码，阻止生成上传包；只提示文件名，不输出 Key。
    env_file = ROOT / '.env'
    key = ''
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            if line.startswith('DEEPSEEK_API_KEY='):
                key = line.split('=', 1)[1].strip().strip('"\'')
    if key and len(key) >= 12:
        for path in paths:
            if key.encode('utf-8') in path.read_bytes():
                raise SystemExit(f'未生成源码包：请移除 {path.relative_to(ROOT)} 中的本机 API Key。')
    destination = ROOT / 'dist/CharacterCompass-GitHub-source.zip'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, 'CharacterCompass/' + path.relative_to(ROOT).as_posix())
    print(f'源码包：{destination}\n共 {len(paths)} 个文件；不含 .env、作品、桌面安装包或本机依赖。')


if __name__ == '__main__':
    main()
