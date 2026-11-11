"""Build WorkBuddy distribution assets. This is packaging code, not an agent runtime."""
from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
import zipfile
from pathlib import Path, PurePosixPath
from posixpath import dirname, join, normpath
from urllib.parse import unquote

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / '.codebuddy/skills/ai-intro-course'
SETUP = ROOT / 'bootstrap/ai-intro-course-setup'
DIST = ROOT / 'dist'
REQUIRED = {'name', 'display_name', 'display_name_en', 'description', 'description_zh',
            'description_en', 'version', 'author'}
MATERIAL_SHARE_URL = re.compile(r'https?://(?:www\.)?workbuddy\.cn/space/[sd]/[A-Za-z0-9]{12,}')
SOURCE_SUFFIXES = {'.md', '.json', '.py', '.txt', '.png', '.jpg', '.jpeg'}
PRIVATE_DIRECTORIES = {'private', 'local', 'runtime-output', 'teacher-materials',
                       'teacher-answers', 'dist', '__pycache__', '.git'}


def publishable(relative: PurePosixPath) -> bool:
    name = relative.name.casefold()
    if any(part.casefold() in PRIVATE_DIRECTORIES for part in relative.parts):
        return False
    if name.startswith('.env') or '.local.' in name or name.endswith('.local'):
        return False
    return relative.suffix.casefold() in SOURCE_SUFFIXES or name == '.gitignore'


def metadata(path: Path) -> dict:
    text = path.read_text(encoding='utf-8')
    match = re.match(r'^---\n(.*?)\n---', text, re.S)
    if not match:
        raise ValueError(f'Missing frontmatter: {path.relative_to(ROOT)}')
    return yaml.safe_load(match[1])


def read_files(folder: Path, prefix: str = '') -> dict[str, bytes]:
    result = {}
    for path in sorted(folder.rglob('*')):
        if path.is_file():
            relative = PurePosixPath(path.relative_to(folder).as_posix())
            if not publishable(relative):
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
                raise ValueError(f'Unsafe source: {path}')
            result[(PurePosixPath(prefix) / path.relative_to(folder).as_posix()).as_posix()] = path.read_bytes()
    return result


def validate_inputs() -> tuple[dict, str]:
    manifest = json.loads((ROOT / 'packaging/plugin.json').read_text(encoding='utf-8'))
    version = manifest['version']
    required_manifest = {'name', 'expertType', 'version', 'description', 'author', 'agents',
                         'agentName', 'teamInfo', 'skills', 'displayName', 'profession',
                         'displayDescription', 'avatar', 'categoryId', 'defaultInitPrompt',
                         'plugin', 'tags', 'quickPrompts', 'members'}
    assert required_manifest <= manifest.keys()
    assert manifest['name'] == manifest['plugin'] == 'ai-intro-course-team'
    assert manifest['expertType'] == 'team'
    assert re.fullmatch(r'\d+\.\d+\.\d+', version)
    assert manifest['author']['email'] and '@' in manifest['author']['email']
    assert manifest['displayName'] == manifest['profession']
    assert 40 <= len(manifest['displayDescription']['zh']) <= 50
    assert len(manifest['tags']) == len(manifest['quickPrompts']) == 3
    assert manifest['defaultInitPrompt'] == manifest['quickPrompts'][0]
    assert manifest['skills'] == ['./skills/ai-intro-course']
    assert not manifest.get('dependencies'), 'No external connector required by this suite'

    for folder in (SKILL, SETUP):
        fm = metadata(folder / 'SKILL.md')
        assert REQUIRED <= fm.keys(), f'Missing skill fields: {folder}'
        assert all(isinstance(fm[k], str) and fm[k].strip() for k in REQUIRED)
        assert fm['name'] == folder.name and fm['version'] == version

    expected_agents = {Path(rel).stem for rel in manifest['agents']}
    actual_agents = list((ROOT / '.codebuddy/agents').glob('*.md'))
    assert len(expected_agents) == len(actual_agents) == 5
    assert {p.stem for p in actual_agents} == expected_agents
    for path in actual_agents:
        fm = metadata(path)
        assert fm['name'] == path.stem
        assert fm['skills'] == ['ai-intro-course']
        assert fm['displayName'] == fm['profession']
        assert 'tools' not in fm
    assert manifest['agentName'] in expected_agents
    assert manifest['teamInfo']['leadAgent'] == manifest['agentName']
    assert set(manifest['teamInfo']['memberAgents']) == expected_agents - {manifest['agentName']}
    assert {m['id'] for m in manifest['members']} == expected_agents
    assert sum(m['role'] == 'lead' for m in manifest['members']) == 1

    for name in ('settings.json', 'setting.json'):
        assert json.loads((ROOT / 'packaging' / name).read_text(encoding='utf-8')) == {'agent': manifest['agentName']}
    for rel in {manifest['avatar']} | {m['avatar'] for m in manifest['members']}:
        data = (ROOT / 'packaging' / rel).read_bytes()
        assert data[:8] == b'\x89PNG\r\n\x1a\n'
        assert struct.unpack('>II', data[16:24]) == (512, 512)
        assert len(data) <= 500 * 1024
    return manifest, version


def check_bundle(files: dict[str, bytes]) -> int:
    links = 0
    for name, data in files.items():
        assert '..' not in PurePosixPath(name).parts and not PurePosixPath(name).is_absolute()
        nested_package = name.startswith('assets/packages/') and name.endswith('.zip')
        assert publishable(PurePosixPath(name)) or nested_package, f'Non-distributable path: {name}'
        if PurePosixPath(name).suffix in {'.md', '.json', '.py', '.txt'}:
            text = data.decode('utf-8')
            assert not MATERIAL_SHARE_URL.search(text), f'Populated materials URL: {name}'
            assert '\ufffd' not in text, name
        if not name.endswith('.md'):
            continue
        for target in re.findall(r'\]\(([^)]+)\)', data.decode('utf-8')):
            if re.match(r'^[a-z][a-z0-9+.-]*:', target, re.I) or target.startswith('#'):
                continue
            target = unquote(target.split('#', 1)[0].strip('<>'))
            resolved = normpath(join(dirname(name), target))
            assert resolved in files, f'Broken packaged link: {name} -> {target}'
            links += 1
    return links


def archive(name: str, root: str, files: dict[str, bytes]) -> dict:
    links = check_bundle(files)
    dest = DIST / name
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for rel, data in sorted(files.items()):
            info = zipfile.ZipInfo(f'{root}/{rel}', (2026, 11, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, data)
    with zipfile.ZipFile(dest) as bundle:
        assert bundle.testzip() is None
        assert len(bundle.namelist()) == len(files)
    return {'name': name, 'files': len(files), 'relative_links_checked': links,
            'bytes': dest.stat().st_size, 'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()}


def build() -> dict:
    manifest, version = validate_inputs()
    DIST.mkdir(exist_ok=True)
    runtime = read_files(SKILL)
    codebuddy = read_files(ROOT / '.codebuddy/agents', '.codebuddy/agents')
    codebuddy.update(read_files(SKILL, '.codebuddy/skills/ai-intro-course'))
    payload = dict(codebuddy)
    payload['configs/teacher-project.md'] = (ROOT / 'configs/teacher-project.md').read_bytes()
    for name in ('plugin.json', 'settings.json', 'setting.json'):
        payload['packaging/' + name] = (ROOT / 'packaging' / name).read_bytes()
    payload.update(read_files(ROOT / 'packaging/avatars', 'packaging/avatars'))
    payload['USER_GUIDE.md'] = (ROOT / 'docs/user-guide.md').read_bytes()

    experts = []
    for m in manifest['members']:
        rel = '.codebuddy/agents/' + m['id'] + '.md'
        experts.append({'id': m['id'], 'name': m['name']['zh'], 'role': m['role'],
                        'source': rel, 'sha256': hashlib.sha256(payload[rel]).hexdigest(),
                        'skill_ids': ['ai-intro-course'],
                        'avatar': 'packaging/' + m['avatar']})
    plan = {
        'schema_version': 1, 'suite_id': manifest['name'], 'version': version,
        'payload_root': 'assets/course-suite', 'runtime_skill': {
            'id': 'ai-intro-course', 'source': '.codebuddy/skills/ai-intro-course',
            'name': metadata(SKILL / 'SKILL.md')['display_name']},
        'experts': experts, 'team_manifest': 'packaging/plugin.json',
        'project_type': 'teacher', 'project_config': 'configs/teacher-project.md',
        'recommended_selection': {'expert_ids': [manifest['agentName']], 'skill_ids': ['ai-intro-course']},
        'local_installer': 'scripts/install_project.py',
        'registration': 'Prefer actual native management tools; filesystem installation does not verify selectors.',
        'file_hashes': {path: hashlib.sha256(data).hexdigest() for path, data in sorted(payload.items())}
    }
    team = read_files(ROOT / '.codebuddy/agents', 'agents')
    team.update(read_files(SKILL, 'skills/ai-intro-course'))
    team.update(read_files(ROOT / 'packaging/avatars', 'avatars'))
    team['.codebuddy-plugin/plugin.json'] = (ROOT / 'packaging/plugin.json').read_bytes()
    for name in ('settings.json', 'setting.json', 'README.md'):
        team[name] = (ROOT / 'packaging' / name).read_bytes()

    # Bundle ready-to-import assets as well as unpacked sources. A native manager
    # that requires a ZIP must not be given source-layout manifest paths alone.
    runtime_record = archive(f'ai-intro-course-{version}-workbuddy.zip', 'ai-intro-course', runtime)
    team_record = archive(f'ai-intro-course-team-{version}.zip', 'ai-intro-course-team', team)
    plan['artifacts'] = {
        'runtime_skill_archive': 'assets/packages/' + runtime_record['name'],
        'runtime_skill_sha256': runtime_record['sha256'],
        'native_team_archive': 'assets/packages/' + team_record['name'],
        'native_team_sha256': team_record['sha256']
    }
    setup = read_files(SETUP)
    setup.update({'assets/course-suite/' + k: v for k, v in payload.items()})
    setup['assets/install-plan.json'] = (json.dumps(plan, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    setup['scripts/install_project.py'] = (ROOT / 'tools/install_project.py').read_bytes()
    for record in (runtime_record, team_record):
        setup['assets/packages/' + record['name']] = (DIST / record['name']).read_bytes()

    source = {name: (ROOT / name).read_bytes() for name in ('README.md', '.gitignore', 'requirements-dev.txt')}
    source.update(codebuddy)
    for folder in ('bootstrap', 'packaging', 'tools', 'docs', 'tests'):
        for name, data in read_files(ROOT / folder, folder).items():
            if '__pycache__' not in PurePosixPath(name).parts and not name.endswith('.pyc'):
                source[name] = data
    source['configs/teacher-project.md'] = (ROOT / 'configs/teacher-project.md').read_bytes()

    records = [
        archive(f'ai-intro-course-setup-{version}.zip', 'ai-intro-course-setup', setup),
        team_record,
        runtime_record,
        archive(f'ai-intro-course-source-{version}.zip', 'ai-intro-course-skill', source)
    ]
    report = {'version': version, 'project_type': 'teacher', 'native_experts': 5, 'runtime_skills': 1,
              'setup_skills': 1, 'source_structure': 'passed', 'archives': records,
              'workbuddy_registry': 'not_executed', 'project_selector': 'not_executed',
              'live_retrieval': 'not_executed', 'live_permissions': 'not_executed'}
    (DIST / 'build-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    try:
        print(json.dumps(build(), ensure_ascii=False, indent=2))
    except (AssertionError, ValueError, OSError) as error:
        print(f'Build failed: {error}', file=sys.stderr)
        raise SystemExit(1)
