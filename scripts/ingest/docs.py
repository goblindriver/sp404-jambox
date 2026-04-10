"""Doc deliverable detection, routing, and Chat delivery handling."""
import os
import sys
import shutil
import zipfile
import yaml

from . import _state


def _is_doc_deliverable(filename):
    """Check if a file is a Chat/Cowork doc deliverable based on naming convention.

    Handles .md, .txt, .pdf, .doc, .docx files. Routes by pattern matching.
    """
    name = os.path.basename(filename)
    ext = os.path.splitext(name)[1].lower()
    if ext not in _state.DOC_EXTENSIONS:
        return None
    if name in _state.DOC_ROOT_FILES:
        return _state.REPO_DIR
    for pattern, dest_dir in _state.DOC_DELIVERABLE_PATTERNS.items():
        if pattern in name:
            return os.path.join(_state.REPO_DIR, dest_dir)
    if ext in ('.pdf', '.docx', '.doc'):
        name_lower = name.lower()
        if any(kw in name_lower for kw in ('sp-404', 'sp404', 'jambox', 'manual', 'reference', 'field_manual')):
            return os.path.join(_state.REPO_DIR, 'docs')
    return None


def ingest_doc_deliverables(dry_run=False):
    """Scan ~/Downloads for Chat/Cowork doc deliverables and copy to repo.

    Returns (copied, skipped) counts.
    """
    if not os.path.isdir(_state.DOWNLOADS):
        return 0, 0

    copied = 0
    skipped = 0

    for item in _state._download_entries():
        filepath = os.path.join(_state.DOWNLOADS, item)
        if os.path.isdir(filepath):
            continue

        dest_dir = _is_doc_deliverable(item)
        if dest_dir is None:
            continue

        dest_path = os.path.join(dest_dir, item)

        if os.path.exists(dest_path):
            try:
                if os.path.getsize(filepath) == os.path.getsize(dest_path):
                    if not dry_run:
                        os.remove(filepath)
                    print(f"  Already in repo, {'would clean' if dry_run else 'cleaned'}: {item}")
                    skipped += 1
                    continue
            except OSError:
                pass

        rel_dest = os.path.relpath(dest_path, _state.REPO_DIR)
        print(f"  {'Would copy' if dry_run else 'Copying'}: {item} \u2192 {rel_dest}")
        if not dry_run:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(filepath, dest_path)
            os.remove(filepath)
        copied += 1

    return copied, skipped


def _ingest_doc_zip(filepath):
    """Extract a zip of doc deliverables (no audio) and route them to the repo.

    Returns the number of docs copied.
    """
    if not zipfile.is_zipfile(filepath):
        return 0

    count = 0
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            for name in zf.namelist():
                basename = os.path.basename(name)
                if not basename:
                    continue
                dest_dir = _is_doc_deliverable(basename)
                if dest_dir is None:
                    continue

                dest_path = os.path.join(dest_dir, basename)
                if os.path.exists(dest_path):
                    continue

                os.makedirs(dest_dir, exist_ok=True)
                with zf.open(name) as src, open(dest_path, 'wb') as dst:
                    dst.write(src.read())
                rel_dest = os.path.relpath(dest_path, _state.REPO_DIR)
                print(f"  [DOC] {basename} \u2192 {rel_dest}")
                count += 1
    except Exception as e:
        print(f"  [DOC] Error processing {os.path.basename(filepath)}: {e}")

    if count > 0:
        try:
            archive_dest = os.path.join(_state.RAW_ARCHIVE, os.path.basename(filepath))
            shutil.move(filepath, archive_dest)
        except Exception:
            pass
        _state._log_ingest(
            "Doc zip: %s" % os.path.basename(filepath),
            count, {'docs': count}, source_type='doc-delivery',
        )

    return count


def check_chat_delivery(filepath):
    """Check if a zip contains a _DELIVERY.yaml manifest from Chat.

    Returns the delivery manifest dict, or None if not a Chat delivery.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext != '.zip':
        return None
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            names = zf.namelist()
            manifest_name = None
            for name in names:
                if os.path.basename(name) == '_DELIVERY.yaml':
                    manifest_name = name
                    break
            if not manifest_name:
                return None
            with zf.open(manifest_name) as mf:
                manifest = yaml.safe_load(mf)
            if isinstance(manifest, dict) and manifest.get('from') == 'chat':
                return manifest
    except Exception:
        return None
    return None


def handle_chat_delivery(filepath, manifest):
    """Process a Chat delivery zip based on its manifest."""
    if _state.SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, _state.SCRIPTS_DIR)
    from preset_utils import save_preset, CATEGORIES

    delivery_type = manifest.get('type', '')
    message = manifest.get('message', '')

    print(f"\n{'='*60}")
    print(f"[DELIVERY] \U0001f4ec Message in a bottle from Chat!")
    if message:
        print(f'[DELIVERY] "{message}"')
    print(f"[DELIVERY] Type: {delivery_type}")

    if delivery_type == 'presets':
        category = manifest.get('category', 'community')
        return _install_preset_delivery(filepath, category)
    else:
        print(f"[DELIVERY] Unknown delivery type: {delivery_type} \u2014 skipping")
        return 0


def _install_preset_delivery(filepath, default_category='community'):
    """Extract and install preset YAML files from a Chat delivery zip."""
    from preset_utils import save_preset, CATEGORIES

    count = 0
    installed = []

    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            for name in zf.namelist():
                if not name.endswith('.yaml') or os.path.basename(name) == '_DELIVERY.yaml':
                    continue

                try:
                    with zf.open(name) as yf:
                        preset = yaml.safe_load(yf)
                except Exception as e:
                    print(f"[DELIVERY] Failed to parse {name}: {e}")
                    continue

                if not isinstance(preset, dict) or 'name' not in preset:
                    print(f"[DELIVERY] Skipping {name} \u2014 not a valid preset (missing 'name')")
                    continue

                cat = preset.get('category', None)
                if not cat:
                    parts = name.replace('\\', '/').split('/')
                    if len(parts) >= 2 and parts[-2] in CATEGORIES:
                        cat = parts[-2]
                    else:
                        cat = default_category

                ref = save_preset(preset, category=cat)
                preset_name = preset.get('name', name)
                installed.append(f"{cat}/{preset.get('slug', name)}")
                count += 1
                print(f"[DELIVERY] \u2705 Installed preset: {preset_name} \u2192 presets/{cat}/")

    except Exception as e:
        print(f"[DELIVERY] Error processing delivery: {e}")
        return 0

    if count > 0:
        print(f"[DELIVERY] \U0001f4e6 {count} preset(s) installed: {', '.join(installed)}")
        _log_delivery(filepath, 'presets', installed)

    return count


def _log_delivery(filepath, delivery_type, items):
    """Log a Chat delivery using the standard ingest log + watcher feed."""
    _state._log_ingest(
        source_name=f"\U0001f4ec Chat delivery: {os.path.basename(filepath)}",
        num_samples=len(items),
        categories={delivery_type: len(items)},
        source_type='chat-delivery',
    )
