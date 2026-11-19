import json
import shutil
import subprocess

import pytest
from PIL import Image

from crewcut import approvals, db, episodes, paths, team
from crewcut.conductor import prompts, queue
from crewcut.motion import custom, quality


@pytest.fixture
def craft(crew, tmp_path, monkeypatch):
    eid = episodes.create('Craft fixture')['id']
    ep = paths.episode_dir(eid)
    source = tmp_path / 'reference.png'
    Image.new('RGB', (320, 180), '#bcbcbc').save(source)
    entry = quality.add('fixture', str(source), ['Defined shape', 'Intentional surface', 'Clear action'], 'Synthetic user selection')
    brief = ep / 'brief.md'
    brief.write_text('A specific object and action, 2 seconds, landscape.')
    folder = custom.new(eid, 'object', brief)
    frame = folder / 'ours.png'
    Image.new('RGB', (320, 180), '#dcdcdc').save(frame)
    jid = queue.add(eid, 'critic', 'edit', 'Independent comparison')
    monkeypatch.setenv('CREWCUT_IDENTITY', 'critic')
    monkeypatch.setenv('CREWCUT_JOB', str(jid))
    report = {'verdict': 'pass', 'reviewer_job': jid, 'benchmark': entry['id'],
              'benchmark_sha256': entry['frame']['sha256'], 'frame_sha256': [approvals.sha256(frame)],
              'criteria': {k: {'pass': True, 'observation': 'Synthetic observation', 'comparison': 'Synthetic comparison'} for k in quality.CRITERIA},
              'improvement': {'what': 'Synthetic improvement', 'evidence': 'Synthetic location'}, 'unresolved': []}
    rp = folder / 'review/style-craft.json'
    rp.write_text(json.dumps(report))
    return eid, frame, rp, report


def test_benchmarks_reach_every_edit_job_and_sources_stay_private(craft):
    eid, frame, _, _ = craft
    text = prompts.system_prompt(team.get('designer'), eid, 'edit')
    assert 'Defined shape' in text and 'motion-quality/fixture/frame.png' in text
    assert 'separate Critic' in text
    assert frame.is_file()


def test_cannot_propose_without_independent_complete_review(craft, monkeypatch):
    eid, frame, rp, report = craft
    with pytest.raises(ValueError, match='separate Critic'):
        custom.style_frame(eid, 'object', [str(frame)])
    monkeypatch.setenv('CREWCUT_IDENTITY', 'designer')
    with pytest.raises(ValueError, match='assigned Critic'):
        custom.style_frame(eid, 'object', [str(frame)], craft_review=str(rp))
    monkeypatch.setenv('CREWCUT_IDENTITY', 'critic')
    report['criteria']['shape_detail']['pass'] = False
    rp.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='shape_detail'):
        custom.style_frame(eid, 'object', [str(frame)], craft_review=str(rp))
    with pytest.raises(ValueError, match='independent craft review'):
        approvals.propose(eid, 'edit', 'style-frame', 'Bypass attempt', file=str(frame))


def test_card_binds_all_frames_benchmark_and_report(craft):
    eid, frame, rp, report = craft
    card = custom.style_frame(eid, 'object', [str(frame)], craft_review=str(rp))
    assert card['data']['frames'][0]['ref']
    quality.check_card(card)
    report['improvement']['what'] = 'Changed after proposal'
    rp.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='review changed'):
        approvals.decide(card['id'], True)
    assert approvals.get(card['id'])['status'] == 'open'


def test_changed_reference_cannot_pass_even_with_an_old_valid_report(craft):
    eid, frame, rp, _ = craft
    ref = quality.asset(quality.catalog()['benchmarks'][0]['frame'])
    Image.new('RGB', (320, 180), '#ffffff').save(ref)
    with pytest.raises(ValueError, match='missing or changed'):
        custom.style_frame(eid, 'object', [str(frame)], craft_review=str(rp))


def test_still_review_never_approves_animation(craft):
    eid, frame, rp, _ = craft
    card = custom.style_frame(eid, 'object', [str(frame)], craft_review=str(rp))
    db.update('cards', card['id'], status='accepted')
    with pytest.raises(ValueError, match='frame-by-frame'):
        quality.check_animations(eid)


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg unavailable')
def test_native_frame_comparison_and_changed_output_rejection(craft, tmp_path):
    eid, frame, rp, report = craft
    ep = paths.episode_dir(eid)
    clip = ep / 'sample.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10:duration=2',
                    '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p', str(clip)], check=True)
    quality.add('moving', str(frame), ['Shape', 'Depth', 'Motion'], 'Synthetic selection', str(clip))
    entry = quality.catalog()['benchmarks'][-1]
    report.update(benchmark='moving', benchmark_sha256=entry['frame']['sha256'])
    rp.write_text(json.dumps(report))
    card = custom.style_frame(eid, 'object', [str(frame)], craft_review=str(rp))
    db.update('cards', card['id'], status='accepted')
    comparisons = []
    for moment, start in [('entrance', 0), ('main_action', .6), ('exit', 1.2)]:
        item = quality.compare(eid, 'object', 'sample.mp4', 'moving', start, start, 5)
        manifest = json.loads((ep / item['manifest']).read_text())
        assert manifest['native_frames'] and manifest['ours']['fps'] == 10
        assert len(manifest['ours']['frames']) == 5
        comparisons.append({'moment': moment, 'manifest': item['manifest'], 'sha256': item['sha256']})
    report.update(style_frame_card=card['id'], output='sample.mp4', comparisons=comparisons,
                  frame_sha256=[approvals.sha256(clip)])
    animation = rp.with_name('animation-craft.json')
    animation.write_text(json.dumps(report))
    quality.check_animations(eid)
    # An unused historical draft must not block a separately reviewed, exact production manifest.
    unused = approvals.propose(eid, 'edit', 'other', 'Retired draft')
    db.update('cards', unused['id'], kind='style-frame', status='accepted',
              data={'insert': 'retired', 'craft_review': card['data']['craft_review']})
    with pytest.raises(ValueError, match='retired'):
        quality.check_animations(eid)
    plan = ep / 'edit/production.json'
    plan.write_text(json.dumps({'inserts': [{'id': 'mounted', 'kind': 'clip', 'file': 'sample.mp4'}]}))
    revision = animation.with_name('animation-revision.json')
    revision.write_text(animation.read_text())
    def bound(p):
        return {'file': p.relative_to(ep).as_posix(), 'sha256': approvals.sha256(p)}
    production = ep / 'review/production.json'
    data = {'reviewer_job': report['reviewer_job'], 'verdict': 'pass', 'unresolved': [],
            'plan': bound(plan), 'video': bound(clip), 'inserts': [
                {'id': 'mounted', 'clip': bound(clip), 'style_frame_card': card['id'],
                 'animation_review': bound(revision)}]}
    production.write_text(json.dumps(data))
    candidate = {'file': 'sample.mp4', 'sha256': approvals.sha256(clip),
                 'data': {'production_review': bound(production)}}
    quality.check_animations(eid, candidate)
    data['inserts'] = []
    production.write_text(json.dumps(data))
    candidate['data']['production_review'] = bound(production)
    with pytest.raises(ValueError, match='every plan insert'):
        quality.check_animations(eid, candidate)
    db.update('cards', unused['id'], status='declined')
    clip.write_bytes(clip.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='exact frames'):
        quality.check_animations(eid)
