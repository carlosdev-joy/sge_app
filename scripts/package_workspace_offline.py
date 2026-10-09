#!/usr/bin/env python3
"""Empacota e ensaia o workspace sem egress; exige imagens fixadas já presentes no Docker."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import xml.etree.ElementTree as ET
import zipfile


def digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run(*args):
    subprocess.run(args, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache', type=Path, default=Path.home() / '.nuget/packages')
    parser.add_argument('--image', default='orquestra-workspace-f1:offline')
    parser.add_argument('--sdk-metadata', type=Path)
    parser.add_argument('--sdk-archive', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root / 'backend-dotnet'
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit('Destino deve estar vazio; não sobrescrever um pacote já existente.')
    output.mkdir(parents=True, exist_ok=True)
    context = output / 'context'
    staged = context / 'src'
    feed = context / 'feed'
    staged.mkdir(parents=True)
    feed.mkdir()
    # Allowlist: não transportar envs, caches, arquivos locais de credencial ou artefatos de build.
    allowed = {'.cs', '.csproj', '.sln', '.json', '.slnx', '.props', '.targets'}
    for path in source.rglob('*'):
        rel = path.relative_to(source)
        if not path.is_file() or any(part in {'bin', 'obj'} for part in rel.parts):
            continue
        if path.suffix not in allowed:
            continue
        if path.suffix == '.json' and path.name not in {'packages.lock.json', 'global.json'} and 'Fixtures' not in rel.parts:
            continue
        target = staged / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    migration_dir = context / 'sql' / 'migrations'
    migration_dir.mkdir(parents=True)
    for migration in sorted((root / 'sql/migrations').glob('*workspace*.sql')):
        shutil.copyfile(migration, migration_dir / migration.name)
    packages = {}
    for lock in source.glob('*/packages.lock.json'):
        for dependencies in json.loads(lock.read_text())['dependencies'].values():
            for name, details in dependencies.items():
                if details['type'] == 'Project':
                    continue
                key = (name.lower(), details['resolved'].lower())
                if key in packages and packages[key]['contentHash'] != details['contentHash']:
                    raise SystemExit('Hashes conflitantes nos locks: ' + name)
                packages[key] = {'id': name, 'version': details['resolved'],
                                 'contentHash': details['contentHash']}
    components = []
    for (name, version), details in sorted(packages.items()):
        filename = f'{name}.{version}.nupkg'
        package = args.cache / name / version / filename
        actual_hash = base64.b64encode(bytes.fromhex(digest(package, 'sha512'))).decode()
        # NuGet contentHash considera assinatura; não equivale ao SHA512 bruto do ZIP.
        metadata = json.loads((package.parent / '.nupkg.metadata').read_text())
        if metadata['contentHash'] != details['contentHash']:
            raise SystemExit('ContentHash NuGet diverge do lock: ' + filename)
        if actual_hash != (package.parent / (filename + '.sha512')).read_text().strip():
            raise SystemExit('SHA512 bruto diverge do cache: ' + filename)
        shutil.copyfile(package, feed / filename)
        license_info = None
        with zipfile.ZipFile(package) as archive:
            nuspec = next(n for n in archive.namelist() if n.endswith('.nuspec'))
            metadata = ET.fromstring(archive.read(nuspec))
            for element in metadata.iter():
                if element.tag.split('}')[-1] in {'license', 'licenseUrl'}:
                    license_info = {'type': element.attrib.get('type', 'url'), 'value': element.text}
                    if element.attrib.get('type') == 'file' and element.text in archive.namelist():
                        licenses = output / 'licenses'
                        licenses.mkdir(exist_ok=True)
                        (licenses / (filename + '.license.txt')).write_bytes(archive.read(element.text))
                    if element.tag.split('}')[-1] == 'license':
                        break
        components.append({**details, 'sha256': digest(package), 'license': license_info,
                           'purl': f'pkg:nuget/{details["id"]}@{details["version"]}'})
    (context / 'NuGet.Config').write_text('''<configuration><packageSources><clear/><add key="offline" value="/feed"/></packageSources><config><add key="globalPackagesFolder" value="/packages"/></config></configuration>''')
    dockerfile = (source / 'Dockerfile').read_text()
    bases = re.findall(r'^FROM (\S+)', dockerfile, re.MULTILINE)
    if len(bases) != 2 or any('@sha256:' not in image for image in bases):
        raise SystemExit('Dockerfile deve fixar duas imagens por digest.')
    for image in bases:
        run('docker', 'image', 'inspect', '--format', '{{.Id}}', image)
    (context / 'Dockerfile').write_text(f'''FROM {bases[0]} AS build
WORKDIR /src
COPY src/ ./
COPY feed/ /feed/
COPY NuGet.Config /offline/NuGet.Config
RUN dotnet restore Orquestra.sln --locked-mode --configfile /offline/NuGet.Config -p:NuGetAudit=false && dotnet test Orquestra.sln -c Release --no-restore -m:1 && dotnet publish Orquestra.Api/Orquestra.Api.csproj -c Release --no-restore -o /out /p:UseAppHost=false
FROM {bases[1]}
WORKDIR /app
COPY --from=build /out/ ./
ENV ASPNETCORE_HTTP_PORTS=8080
USER $APP_UID
EXPOSE 8080
ENTRYPOINT ["dotnet", "Orquestra.Api.dll"]
''')
    (output / 'dependencies.json').write_text(json.dumps({'format': 'Orquestra dependency inventory v1',
        'scope': 'NuGet resolved packages from all committed project locks; OS/base-image dependencies require separate vendor SBOM',
        'components': components}, indent=2) + '\n')
    sbom_components = []
    for item in components:
        component = {'type': 'library', 'name': item['id'], 'version': item['version'],
                     'purl': item['purl'], 'hashes': [{'alg': 'SHA-256', 'content': item['sha256']}]}
        if item['license']:
            license_info = item['license']
            if license_info['type'] == 'expression':
                component['licenses'] = [{'expression': license_info['value']}]
            else:
                component['licenses'] = [{'license': {'name': license_info['value']}}]
        sbom_components.append(component)
    (output / 'sbom.cdx.json').write_text(json.dumps({'bomFormat': 'CycloneDX',
        'specVersion': '1.6', 'version': 1, 'components': sbom_components}, indent=2) + '\n')
    sdk = None
    if args.sdk_metadata or args.sdk_archive:
        if not args.sdk_metadata or not args.sdk_archive:
            raise SystemExit('Informar metadata e archive juntos.')
        sdk = json.loads(args.sdk_metadata.read_text())
        if digest(args.sdk_archive, 'sha512') != sdk['hash']:
            raise SystemExit('SHA512 SDK diverge da metadata Microsoft.')
        (output / 'sdk-verification.json').write_text(json.dumps({**sdk, 'verifiedSha512': sdk['hash']}, indent=2) + '\n')
    run('docker', 'build', '--network', 'none', '--pull=false', '--no-cache', '-t', args.image, str(context))
    image_id = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', args.image], text=True).strip()
    transport_tags = ['orquestra-workspace-offline-sdk:10.0.401', 'orquestra-workspace-offline-aspnet:10.0.12']
    base_ids = []
    for base, tag in zip(bases, transport_tags):
        base_ids.append(subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', base], text=True).strip())
        run('docker', 'tag', base, tag)
    consumer = (context / 'Dockerfile').read_text()
    for base, tag in zip(bases, transport_tags):
        consumer = consumer.replace(base, tag)
    (context / 'Dockerfile.consumer').write_text(consumer)
    (output / 'REBUILD.md').write_text('''# Consumo offline

Verificar SHA256SUMS antes do consumo: `sha256sum -c SHA256SUMS`.
Carregar `docker load -i images.tar`; não remover imagens existentes.
O tar contém imagem final e bases com tags de transporte. Conferir os IDs de ambas
contra manifest.json antes do build; tags não substituem verificação de identidade.
Extrair `tar -xzf source-feed.tar.gz` em diretório isolado e executar:
`docker build --network none --pull=false --no-cache -f context/Dockerfile.consumer -t orquestra-workspace-f1:rebuild context`.
O NuGet.Config limpa fontes externas e usa somente /feed; o cache de pacotes começa vazio.
O teste SQL vivo é omitido nesse ensaio sem banco; não equivale ao gate SQL separado.
O inventário/SBOM cobre NuGet; componentes Linux das bases exigem SBOM do fornecedor.
'''.replace('orquestra-workspace-f1:rebuild', args.image.split(':')[0] + ':rebuild'))
    run('docker', 'save', '-o', str(output / 'images.tar'), *transport_tags, args.image)
    # Ensaio load sem remoção de imagens compartilhadas.
    run('docker', 'load', '-i', str(output / 'images.tar'))
    loaded_id = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', args.image], text=True).strip()
    if image_id != loaded_id:
        raise SystemExit('Imagem recarregada diverge do build.')
    run('docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'dotnet', args.image, '--list-runtimes')
    manifest = {'image': args.image, 'imageId': image_id, 'baseImages': bases,
                'transportBaseTags': transport_tags, 'transportBaseImageIds': base_ids,
                'buildNetwork': 'none', 'pull': False, 'nugetSources': ['/feed'],
                'nugetPackages': len(components), 'sdkArchiveVerified': sdk is not None,
                'sourceGitHead': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
                'sourceWorkingTreeMayContainChanges': True,
                'loadVerified': True, 'runtimeNoNetworkVerified': True}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    with tarfile.open(output / 'source-feed.tar.gz', 'w:gz') as archive:
        archive.add(context, arcname='context')
    checksums = []
    for path in sorted(output.rglob('*')):
        if path.is_file() and path.name != 'SHA256SUMS':
            checksums.append(f'{digest(path)}  {path.relative_to(output)}')
    (output / 'SHA256SUMS').write_text('\n'.join(checksums) + '\n')
    print(f'Pacote validado: {output}; {len(components)} dependências; {image_id}')


if __name__ == '__main__':
    main()
